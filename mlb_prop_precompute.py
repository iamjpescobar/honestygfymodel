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
    df = season_df[season_df["events"].notna()][list(need)].copy()
    df = df.drop_duplicates(subset=["game_pk", "at_bat_number"])
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


def _game_lines(pa):
    """{(batter, game_pk): {"h","tb","hr","k"}}"""
    out = {}
    for (b, gpk), g in pa.groupby(["batter", "game_pk"], sort=False):
        oc = Counter(g["outcome"])
        out[(int(b), int(gpk))] = {
            "h": sum(oc[o] for o in mp.TB), "tb": sum(mp.TB[o] * oc[o] for o in mp.TB),
            "hr": oc["HR"], "k": oc["K"], "date": g["game_date"].iloc[0]}
    return out


def build_prop_model(season_df, out_dir, validation_days=VALIDATION_DAYS):
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

    model = {
        "league_rates": league,
        "batter_priors": bpri, "pitcher_priors": ppri,
        "team_pa_hist": team_hist, "league_bf_hist": bf_hist,
        "bf_strength_starts": round(bf_s, 3) if bf_s else None,
        "starter_bf": dict(starter_bf),
        "n_pa": n, "n_games": int(pa["game_pk"].nunique()),
        "through": pa["game_date"].max(),
    }
    model["validation"] = validate(pa, model, validation_days)

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "prop_model.json").write_text(json.dumps(model))
    print(f"  prop model: {n:,} PA, league HR/PA {league['HR']:.4f}, K/PA {league['K']:.3f}; "
          f"batter HR prior strength {bpri['HR'][1]:.0f} PA, pitcher {ppri['HR'][1]:.0f} PA; "
          f"BF strength {model['bf_strength_starts']} starts")
    for k, label, *_ in mp.MARKETS:
        v = model["validation"].get(k) or {}
        print(f"  [verify] {label:10s} n={v.get('n')} model Brier {v.get('model_brier')} "
              f"vs his-own-rate {v.get('baseline_brier')} -> "
              f"{'BEATS' if v.get('beats_baseline') else 'does not beat'} baseline")
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
        bf_before = [bf for dd, bf in sp_starts[sp] if dd < d]
        bf_dist = mp.starter_bf_dist(bf_before, model)
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
            proj = mp.project_batter(slot, b_counts, p_counts, model, bf_dist)
            if not proj:
                continue
            for k, _label, stat, at_least in mp.MARKETS:
                y = 1 if actual[stat] >= at_least else 0
                preds[k].append((proj["probs"][k], y))
                freq = sum(1 for g in prior_games if g[stat] >= at_least) / len(prior_games)
                base[k].append((freq, y))
    out = {"from": cut, "to": dates[-1], "days": validation_days}
    for k, *_ in mp.MARKETS:
        m, b = mm.score_predictions(preds[k]), mm.score_predictions(base[k])
        out[k] = {"verdict": mm.paired_verdict([(p_ - y) ** 2 for p_, y in preds[k]],
                                               [(q - y) ** 2 for q, y in base[k]]),
                  "n": m["n"], "model_brier": m["brier"], "baseline_brier": b["brier"],
                  "model_log_loss": m["log_loss"], "baseline_log_loss": b["log_loss"],
                  "beats_baseline": bool(m["brier"] is not None and b["brier"] is not None
                                         and m["brier"] < b["brier"]),
                  "calibration": mm.calibration_bins(preds[k])}
    return out
