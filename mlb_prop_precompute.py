"""
MLB prop model — measured from the season's real plate appearances.

Called by precompute.main() with the season frame it already holds (no
second Statcast pull), writes data/statcast/prop_model.json into the
nightly archive. engines/mlb_props.py is the reader.

WHAT IT MEASURES (all from the same season frame)
-------------------------------------------------
  league_rates        per-PA rate of 1B/2B/3B/HR/BB/K/OUT
  batter_priors       beta-binomial (mean, strength) per outcome, FITTED
                      by maximum likelihood over every batter
  pitcher_priors      the same over every pitcher, outcomes allowed
  team_pa_hist        how many PAs a team gets in a game, as counts
  league_bf_hist      batters faced per START, as counts
  bf_strength_starts  gamma-Poisson strength for a starter's own BF vs
                      the league's, FITTED the same way
  starter_bf          every starter's batters-faced list, start by start

Who started and who batted where are not guessed: inning_topbot gives
each PA's batting side, the first pitcher a side faces is the opposing
starter, and the first nine distinct batters on a side are its lineup in
order. (inning_topbot is kept in the season frame for this and dropped
before the per-player files are written — it is not an engine column.)

WALK-FORWARD VALIDATION
-----------------------
For every lineup bat in the last VALIDATION_DAYS of the season, the
model is rebuilt from that batter's and that starter's PAs on EARLIER
dates only, and scored against what he actually did. The baseline is the
number a prop bettor already has: the share of his earlier games in
which he cleared the line ("he's had a hit in 71% of his games"). A
market is marked `beats_baseline` only if the model's Brier score is
lower. The page greys out the ones that are not.

Look-ahead stated: the priors, league rates and PA histograms are
measured on the full season (a few dozen league-level numbers); every
PLAYER number in the walk-forward uses only earlier dates.
"""
import json
from collections import Counter, defaultdict
from pathlib import Path

import pandas as pd

from engines import model_math as mm
from engines import mlb_props as mp

# Window the validation is scored over. Not a model parameter — it
# changes nothing that is projected, only how many games the report
# covers, and is printed beside the result.
VALIDATION_DAYS = 30

# Columns this builder needs beyond the engine set. precompute keeps
# them in the season frame and drops them before per-player files.
EXTRA_COLS = ["inning_topbot"]


def plate_appearances(season_df):
    """One row per completed PA with outcome and batting side."""
    need = {"game_pk", "at_bat_number", "events", "batter", "pitcher",
            "game_date", "inning_topbot"}
    if not need.issubset(season_df.columns):
        missing = sorted(need - set(season_df.columns))
        raise ValueError(f"season frame is missing {missing}")
    # bat_score / post_bat_score ride along when the frame has them (they
    # are ENGINE_COLS): their difference on the PA-ending pitch is the
    # runs that scored on the play — the RBI markets. Absent -> no RBI
    # column, and those markets are left out, never zero-filled.
    extra = [c for c in ("bat_score", "post_bat_score", "home_team") if c in season_df.columns]
    df = season_df[season_df["events"].notna()][list(need) + extra].copy()
    df = df.drop_duplicates(subset=["game_pk", "at_bat_number"])
    if "bat_score" in extra and "post_bat_score" in extra:
        d = pd.to_numeric(df["post_bat_score"], errors="coerce") - pd.to_numeric(
            df["bat_score"], errors="coerce")
        df["rbi"] = d.where((d >= 0) & (d <= 4))
    df["outcome"] = [mp.classify(e) for e in df["events"].astype(str)]
    df = df[df["outcome"].notna()]
    df["side"] = df["inning_topbot"].astype(str).str.lower().map(
        lambda s: "away" if s.startswith("top") else ("home" if s.startswith("bot") else None))
    df = df[df["side"].notna()]
    df["game_date"] = pd.to_datetime(df["game_date"]).dt.strftime("%Y-%m-%d")
    df["batter"] = df["batter"].astype("int64")
    df["pitcher"] = df["pitcher"].astype("int64")
    return df.sort_values(["game_date", "game_pk", "at_bat_number"]).reset_index(drop=True)


def _counts_by(df, key):
    tab = df.groupby([key, "outcome"]).size().unstack(fill_value=0)
    for o in mp.OUTCOMES:
        if o not in tab.columns:
            tab[o] = 0
    tab = tab[list(mp.OUTCOMES)]
    tab["PA"] = tab.sum(axis=1)
    return tab


def fit_priors(tab):
    out = {}
    for o in mp.OUTCOMES:
        mean, s = mm.fit_beta_prior(list(zip(tab[o].tolist(), tab["PA"].tolist())))
        if mean is None:
            return None
        out[o] = [round(mean, 6), round(s, 3)]
    return out


def starts_table(pa):
    """[(game_pk, side_batting, starter_id, date, bf)] — the first pitcher
    each batting side faced, and how many of its PAs he took."""
    rows = []
    for (gpk, side), g in pa.groupby(["game_pk", "side"], sort=False):
        sp = int(g["pitcher"].iloc[0])
        rows.append((int(gpk), side, sp, g["game_date"].iloc[0],
                     int((g["pitcher"] == sp).sum())))
    return rows


def lineups(pa):
    """{(game_pk, side): [batter ids in slot order]} — first nine
    distinct batters. Sides that never reached nine distinct are
    omitted (a rain-shortened game), not padded."""
    out = {}
    for (gpk, side), g in pa.groupby(["game_pk", "side"], sort=False):
        seen = []
        for b in g["batter"]:
            if b not in seen:
                seen.append(int(b))
            if len(seen) == 9:
                break
        if len(seen) == 9:
            out[(int(gpk), side)] = seen
    return out


def _line_of(g):
    oc = Counter(g["outcome"])
    out = {"h": sum(oc[o] for o in mp.TB), "tb": sum(mp.TB[o] * oc[o] for o in mp.TB),
           "hr": oc["HR"], "k": oc["K"], "bb": oc["BB"], "s": oc["1B"], "d": oc["2B"],
           "date": g["game_date"].iloc[0]}
    if "rbi" in g.columns:
        r = g["rbi"]
        # MISSING IS NOT ZERO: a game with an unmeasured PA has no RBI line
        out["rbi"] = int(r.sum()) if r.notna().all() else None
    return out


def _game_lines(pa):
    """{(batter, game_pk): {"h","tb","hr","k","bb","s","d","rbi"?}}"""
    return {(int(b), int(gpk)): _line_of(g)
            for (b, gpk), g in pa.groupby(["batter", "game_pk"], sort=False)}


def measure_rbi_given(pa, lus=None):
    """{slot: {outcome: [P(0 RBI) .. P(4)]}} plus "all", measured over the
    season: how often each kind of plate appearance drives in 0, 1, 2...
    runs from each lineup slot (a cleanup hitter's single comes with more
    runners on than a nine-hole hitter's). None if the frame carries no
    RBI column."""
    if "rbi" not in pa.columns:
        return None
    lus = lus if lus is not None else lineups(pa)
    slot_of = {}
    for (gpk, side), order in lus.items():
        for i, b in enumerate(order, start=1):
            slot_of[(gpk, side, b)] = i
    counts = {}
    for gpk, side, b, o, r in zip(pa["game_pk"], pa["side"], pa["batter"], pa["outcome"], pa["rbi"]):
        if r != r:                       # NaN: unmeasured, not zero
            continue
        r = int(r)
        for key in (str(slot_of.get((int(gpk), side, int(b)), "")), "all"):
            if not key:
                continue
            c = counts.setdefault(key, {}).setdefault(o, [0] * (mp.MAX_RBI + 1))
            c[min(r, mp.MAX_RBI)] += 1
    out = {}
    for key, by_o in counts.items():
        out[key] = {o: [round(x / sum(c), 6) for x in c] for o, c in by_o.items() if sum(c)}
    return out


PRIOR_PATH = Path(__file__).resolve().parent / "data" / "mlb" / "prior_season.json"


def load_prior(path=None):
    """Last season's per-player outcome counts and starters' batters-faced
    (mlb_model_precompute writes the file once), or {}."""
    p = Path(path or PRIOR_PATH)
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text()) or {}
    except Exception:
        return {}


def fit_prior_weights(btab, ptab, bpri, ppri, starter_bf, prior, league_bf_mean, bf_s):
    """How much last season counts, FITTED on everyone in both seasons:
    this season's outcome counts predicted from last season's alone
    (model_math.fit_prior_weight). One weight for batters, one for
    pitchers (outcomes allowed), one for a starter's depth."""
    out = {"batter": 0.0, "pitcher": 0.0, "bf": 0.0}
    rep = {}
    for kind, tab, pri, prev in (("batter", btab, bpri, prior.get("batters") or {}),
                                 ("pitcher", ptab, ppri, prior.get("pitchers") or {})):
        groups = []
        for o in mp.OUTCOMES:
            pairs = []
            for pid, row in tab.iterrows():
                p0 = prev.get(str(int(pid)))
                if not p0 or not p0.get("PA"):
                    continue
                pairs.append(((p0.get(o, 0), p0["PA"]), (int(row[o]), int(row["PA"]))))
            groups.append((pairs, pri[o][0], pri[o][1]))
        r = mm.fit_prior_weight(groups, kind="binomial")
        if r:
            out[kind] = r["weight"]
            rep[kind] = r
    bf_pairs = []
    for pid, lst in (starter_bf or {}).items():
        p0 = ((prior.get("starters") or {}).get(str(pid)) or {}).get("bf")
        if p0 and lst:
            bf_pairs.append(((sum(p0), len(p0)), (sum(lst), len(lst))))
    if bf_pairs and league_bf_mean and bf_s:
        r = mm.fit_prior_weight([(bf_pairs, league_bf_mean, bf_s)], kind="poisson")
        if r:
            out["bf"] = r["weight"]
            rep["bf"] = r
    return out, rep


def batting_teams(pa):
    """{(game_pk, side): team abbreviation} for the batting side.

    The home side is the game's home_team. The AWAY side is not in the
    feed, so it is read from its batters: each batter's team is the
    home_team of the latest game he batted in the bottom half, and the
    away side is whatever team most of its batters belong to. A side none
    of whose batters ever batted at home is left out, never guessed."""
    if "home_team" not in pa.columns:
        return {}
    home = pa[pa["side"] == "home"]
    bat_team = (home.sort_values("game_date").groupby("batter")["home_team"].last().to_dict())
    out = {}
    for (gpk, side), g in pa.groupby(["game_pk", "side"], sort=False):
        if side == "home":
            out[(int(gpk), side)] = str(g["home_team"].iloc[0])
            continue
        teams = Counter(bat_team.get(int(b)) for b in g["batter"].unique() if bat_team.get(int(b)))
        if teams:
            out[(int(gpk), side)] = teams.most_common(1)[0][0]
    return out


def matchup_tables(pa, ptab, model):
    """{"starter_allowed": ..., "team_batting": ...} for the matchup cards."""
    from engines import defense_matchup as dm
    cur = {str(int(pid)): {o: int(r[o]) for o in list(mp.OUTCOMES) + ["PA"]}
           for pid, r in ptab.iterrows()}
    starters = list((model.get("starter_bf") or {}).keys())
    weight = (model.get("prior_weight") or {}).get("pitcher") or 0.0
    out = {"starter_allowed": dm.mlb_starter_table(
        cur, model.get("prior_pitchers") or {}, weight, model.get("pitcher_priors"), starters)}
    bt = batting_teams(pa)
    if bt:
        keyed = pa.assign(team=[bt.get((int(g), s)) for g, s in zip(pa["game_pk"], pa["side"])])
        keyed = keyed[keyed["team"].notna()]
        tab = _counts_by(keyed, "team")
        lr = model["league_rates"]
        league = {st: sum(m * lr[o] for o, m in w.items()) for st, w in dm.MLB_STAT_OUTCOMES.items()}
        teams = {}
        for team, r in tab.iterrows():
            c = {o: int(r[o]) for o in list(mp.OUTCOMES) + ["PA"]}
            teams[str(team)] = {"pa": c["PA"], **{
                st: round(sum(m * c[o] for o, m in w.items()) / c["PA"], 4)
                for st, w in dm.MLB_STAT_OUTCOMES.items()}} if c["PA"] else {"pa": 0}
        out["team_batting"] = {"teams": teams,
                               "league": {k: round(v, 4) for k, v in league.items()}}
    return out


def build_prop_model(season_df, out_dir, validation_days=VALIDATION_DAYS, prior=None):
    """Write prop_model.json; returns the dict (or None, printing why)."""
    pa = plate_appearances(season_df)
    if len(pa) < 5000:
        print(f"  prop model skipped — only {len(pa)} plate appearances.")
        return None
    league_tab = pa["outcome"].value_counts()
    n = int(league_tab.sum())
    league = {o: round(float(league_tab.get(o, 0)) / n, 6) for o in mp.OUTCOMES}

    btab, ptab = _counts_by(pa, "batter"), _counts_by(pa, "pitcher")
    bpri, ppri = fit_priors(btab), fit_priors(ptab)
    if not bpri or not ppri:
        print("  prop model skipped — prior fit failed.")
        return None

    team_pa = pa.groupby(["game_pk", "side"]).size()
    team_hist = {int(k): int(v) for k, v in Counter(team_pa.tolist()).items()}
    starts = starts_table(pa)
    bf_hist = {int(k): int(v) for k, v in Counter(s[4] for s in starts).items()}
    starter_bf = defaultdict(list)
    for _gpk, _side, sp, d, bf in sorted(starts, key=lambda s: s[3]):
        starter_bf[str(sp)].append(bf)
    _mu, bf_s = mm.fit_gamma_prior([(sum(v), len(v)) for v in starter_bf.values()])

    rbi_given = measure_rbi_given(pa)
    model = {
        "rbi_given": rbi_given,
        "league_rates": league,
        "batter_priors": bpri, "pitcher_priors": ppri,
        "team_pa_hist": team_hist, "league_bf_hist": bf_hist,
        "bf_strength_starts": round(bf_s, 3) if bf_s else None,
        "starter_bf": dict(starter_bf),
        "n_pa": n, "n_games": int(pa["game_pk"].nunique()),
        "through": pa["game_date"].max(),
    }
    # LAST SEASON as evidence, at weights FITTED on the players in both.
    prior = load_prior() if prior is None else prior
    if prior.get("batters") or prior.get("pitchers"):
        _bft = sum(int(k) * v for k, v in bf_hist.items())
        _bfn = sum(bf_hist.values())
        pw, prep = fit_prior_weights(btab, ptab, bpri, ppri, starter_bf, prior,
                                     _bft / _bfn if _bfn else None, bf_s)
        model["prior_season"] = prior.get("season")
        model["prior_weight"] = pw
        model["prior_weight_report"] = prep
        model["prior_batters"] = prior.get("batters") or {}
        model["prior_pitchers"] = prior.get("pitchers") or {}
        model["prior_bf"] = {pid: r.get("bf") for pid, r in (prior.get("starters") or {}).items()
                             if r.get("bf")}
        print(f"  [verify] last-season weights {pw} (players in both seasons: "
              f"{ {k: v.get('n_players') for k, v in prep.items()} }; "
              f"log-lik gain {({k: v.get('loglik_gain') for k, v in prep.items()})})")
    else:
        print("  [verify] no last-season file — props run on this season alone")
    # DEFENSE CONTEXT (10-06): every starter's allowed rates (this season,
    # last, blended at the fitted pitcher weight) ranked among this
    # season's starters, and each team's batting rates — what the matchup
    # cards on the prop board read (engines/defense_matchup).
    try:
        model.update(matchup_tables(pa, ptab, model))
        _sa = model.get("starter_allowed") or {}
        print(f"  [verify] matchup tables: {_sa.get('of')} starters ranked; "
              f"{len((model.get('team_batting') or {}).get('teams') or {})} team batting lines")
    except Exception as exc:  # noqa: BLE001 — costs the cards, never the model
        print(f"::warning::MLB matchup tables failed: {type(exc).__name__}: {exc}")
    model["validation"] = validate(pa, model, validation_days)
    model["pitcher_validation"] = validate_pitchers(pa, model, validation_days)

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "prop_model.json").write_text(json.dumps(model))
    print(f"  prop model: {n:,} PA, league HR/PA {league['HR']:.4f}, K/PA {league['K']:.3f}; "
          f"batter HR prior strength {bpri['HR'][1]:.0f} PA, pitcher {ppri['HR'][1]:.0f} PA; "
          f"BF strength {model['bf_strength_starts']} starts")
    for vk, markets in (("validation", mp.MARKETS), ("pitcher_validation", mp.PITCHER_MARKETS)):
        for k, label, *_ in markets:
            v = model[vk].get(k) or {}
            print(f"  [verify] {label:18s} n={v.get('n')} model Brier {v.get('model_brier')} "
                  f"vs his-own-rate {v.get('baseline_brier')} -> "
                  f"{(v.get('verdict') or {}).get('verdict')}")
    print(f"  [verify] RBI table measured: {'yes' if rbi_given else 'NO (no score columns)'}"
          + (f"; slot 4 HR drives in 1/2/3/4: {rbi_given.get('4', {}).get('HR', [])[1:]}"
             if rbi_given else ""))
    return model


def validate(pa, model, validation_days):
    dates = sorted(pa["game_date"].unique())
    if len(dates) < validation_days + 14:
        return {"note": "season too short to validate"}
    cut = dates[-validation_days]

    # Cumulative per-batter / per-pitcher outcome counts BEFORE each date.
    def cum_before(key):
        daily = pa.groupby([key, "game_date", "outcome"]).size().unstack(fill_value=0)
        for o in mp.OUTCOMES:
            if o not in daily.columns:
                daily[o] = 0
        daily = daily[list(mp.OUTCOMES)]
        cum = daily.groupby(level=0).cumsum() - daily
        cum["PA"] = cum.sum(axis=1)
        return cum

    bcum, pcum = cum_before("batter"), cum_before("pitcher")
    lines = _game_lines(pa)
    # Prior games per batter for the baseline frequency.
    games_by_batter = defaultdict(list)
    for (b, _gpk), ln in sorted(lines.items(), key=lambda kv: kv[1]["date"]):
        games_by_batter[b].append(ln)
    starts = starts_table(pa)
    start_of = {(gpk, side): (sp, d) for gpk, side, sp, d, _bf in starts}
    sp_starts = defaultdict(list)
    for _gpk, _side, sp, d, bf in starts:
        sp_starts[sp].append((d, bf))
    lus = lineups(pa)

    preds = {k: [] for k, *_ in mp.MARKETS}
    base = {k: [] for k, *_ in mp.MARKETS}
    for (gpk, side), order in lus.items():
        info = start_of.get((gpk, side))
        if not info:
            continue
        sp, d = info
        if d < cut:
            continue
        try:
            prow = pcum.loc[(sp, d)]
            p_counts = {o: int(prow[o]) for o in mp.OUTCOMES}
            p_counts["PA"] = int(prow["PA"])
        except KeyError:
            p_counts = None
        p_counts = mp.player_counts(model, sp, p_counts, "pitcher")
        bf_before = [bf for dd, bf in sp_starts[sp] if dd < d]
        bf_dist = mp.starter_bf_dist(bf_before, model, (model.get("prior_bf") or {}).get(str(sp)))
        for slot, b in enumerate(order, start=1):
            try:
                brow = bcum.loc[(b, d)]
            except KeyError:
                continue
            b_counts = {o: int(brow[o]) for o in mp.OUTCOMES}
            b_counts["PA"] = int(brow["PA"])
            prior_games = [g for g in games_by_batter[b] if g["date"] < d]
            actual = lines.get((b, gpk))
            if not prior_games or not actual or not b_counts["PA"]:
                continue
            b_counts = mp.player_counts(model, b, b_counts, "batter")
            proj = mp.project_batter(slot, b_counts, p_counts, model, bf_dist)
            if not proj:
                continue
            for k, _label, stat, at_least in mp.MARKETS:
                if k not in proj["probs"] or actual.get(stat) is None:
                    continue
                hist = [g[stat] for g in prior_games if g.get(stat) is not None]
                if not hist:
                    continue
                y = 1 if actual[stat] >= at_least else 0
                preds[k].append((proj["probs"][k], y))
                base[k].append((sum(1 for x in hist if x >= at_least) / len(hist), y))
    return _score(preds, base, mp.MARKETS, cut, dates[-1], validation_days)


def _score(preds, base, markets, cut, last, validation_days):
    out = {"from": cut, "to": last, "days": validation_days}
    for k, *_ in markets:
        m, b = mm.score_predictions(preds[k]), mm.score_predictions(base[k])
        out[k] = {"verdict": mm.paired_verdict([(p_ - y) ** 2 for p_, y in preds[k]],
                                               [(q - y) ** 2 for q, y in base[k]]),
                  "n": m["n"], "model_brier": m["brier"], "baseline_brier": b["brier"],
                  "model_log_loss": m["log_loss"], "baseline_log_loss": b["log_loss"],
                  "beats_baseline": bool(m["brier"] is not None and b["brier"] is not None
                                         and m["brier"] < b["brier"]),
                  "calibration": mm.calibration_bins(preds[k])}
    return out


def _cum_before(pa, key):
    daily = pa.groupby([key, "game_date", "outcome"]).size().unstack(fill_value=0)
    for o in mp.OUTCOMES:
        if o not in daily.columns:
            daily[o] = 0
    daily = daily[list(mp.OUTCOMES)]
    cum = daily.groupby(level=0).cumsum() - daily
    cum["PA"] = cum.sum(axis=1)
    return cum


def _counts_at(cum, key, d):
    try:
        row = cum.loc[(key, d)]
    except KeyError:
        return None
    c = {o: int(row[o]) for o in mp.OUTCOMES}
    c["PA"] = int(row["PA"])
    return c


def validate_pitchers(pa, model, validation_days):
    """Walk-forward for the starter props: every start in the last
    `validation_days`, projected from the starter's and the nine
    batters' plate appearances BEFORE that date and his earlier batters-
    faced, scored against what he actually allowed (his own PAs only).
    Baseline: the share of his earlier starts that cleared the line."""
    dates = sorted(pa["game_date"].unique())
    if len(dates) < validation_days + 14:
        return {"note": "season too short to validate"}
    cut = dates[-validation_days]
    bcum, pcum = _cum_before(pa, "batter"), _cum_before(pa, "pitcher")
    lus = lineups(pa)
    starts = starts_table(pa)
    # his actual line per start, from his own PAs in that game
    by_start = {}
    for (gpk, side, p), g in pa.groupby(["game_pk", "side", "pitcher"], sort=False):
        oc = Counter(g["outcome"])
        by_start[(int(gpk), side, int(p))] = {
            "k": oc["K"], "h": sum(oc[o] for o in mp.TB), "bb": oc["BB"], "hr": oc["HR"]}
    history = defaultdict(list)
    for gpk, side, sp, d, bf in sorted(starts, key=lambda s: s[3]):
        history[sp].append((d, bf, by_start.get((gpk, side, sp))))
    preds = {k: [] for k, *_ in mp.PITCHER_MARKETS}
    base = {k: [] for k, *_ in mp.PITCHER_MARKETS}
    for gpk, side, sp, d, _bf in starts:
        if d < cut:
            continue
        order = lus.get((gpk, side))
        actual = by_start.get((gpk, side, sp))
        before = [x for x in history[sp] if x[0] < d]
        if not order or not actual or not before:
            continue
        p_counts = _counts_at(pcum, sp, d)
        if not p_counts or not p_counts["PA"]:
            continue
        p_counts = mp.player_counts(model, sp, p_counts, "pitcher")
        bf_dist = mp.starter_bf_dist([bf for _d, bf, _a in before], model,
                                     (model.get("prior_bf") or {}).get(str(sp)))
        oc = [mp.player_counts(model, b, _counts_at(bcum, b, d), "batter") for b in order]
        proj = mp.project_pitcher(oc, p_counts, model, bf_dist)
        if not proj:
            continue
        past = [a for _d, _bf, a in before if a]
        for k, _l, stat, n in mp.PITCHER_MARKETS:
            y = 1 if actual[stat] >= n else 0
            preds[k].append((proj["probs"][k], y))
            base[k].append((sum(1 for a in past if a[stat] >= n) / len(past), y))
    return _score(preds, base, mp.PITCHER_MARKETS, cut, dates[-1], validation_days)
