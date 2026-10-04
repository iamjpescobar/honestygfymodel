"""
MLB game model — fitted nightly from the season's real finals.

Writes data/mlb/model.json (committed by nightly-data.yml, like
lineup_lock.json), which the Game Card, the MLB Model page and the slate
builder all read. Nothing here runs on Render.

WHAT IT MEASURES
----------------
From statsapi's schedule (regular season, one call per month, hydrated
with linescore and probable pitchers):

  - every team's runs scored and allowed
  - the league run rate, home and road scoring multipliers
  - how often the home side wins a game that went to extra innings
  - shrink_k: how hard a team's own rate is pulled toward the league,
    FITTED by walk-forward log loss (engines/game_model.fit)
  - dispersion: negative-binomial size, measured on the residuals

And from each starting pitcher's statsapi game log:

  - how deep he goes (outs per start) and how many runs he allows per
    nine — each shrunk toward the league's starters by a gamma-Poisson
    prior FITTED by maximum likelihood across every starter
    (model_math.fit_gamma_prior). A 3-start call-up is mostly league
    average; a 30-start ace is mostly himself, by however much the
    season's own spread says.

THE STARTER LAYER HAS TO EARN ITS PLACE
---------------------------------------
The walk-forward is run twice — team rates only, and team rates with the
starter's share of the game replaced by his own record AS OF THE DAY
BEFORE. `use_starters` is true only if the second beats the first on log
loss. If it does not, the page shows the team-only number and says why.
A feature that does not beat the simpler model is not shown as if it
did (the NFL yardage lesson, 09-27).

One honest look-ahead: the two gamma priors are fitted on full-season
starter totals, so a walk-forward prediction in May borrows the
season's knowledge of how spread-out starters are (two numbers, not any
starter's own line). Stated in the validation block.

Run manually from Actions as part of the nightly; prints [verify] lines.
"""
import json
import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import requests

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "app"))
from engines import game_model as gm      # noqa: E402
from engines import model_math as mm      # noqa: E402
from engines.mlb_game_model import starter_layer  # noqa: E402

EASTERN = ZoneInfo("America/New_York")
OUT = ROOT / "data" / "mlb" / "model.json"
SCHEDULE = ("https://statsapi.mlb.com/api/v1/schedule?sportId=1&gameType=R"
            "&startDate={start}&endDate={end}&hydrate=linescore,probablePitcher")
GAMELOG = ("https://statsapi.mlb.com/api/v1/people/{pid}/stats"
           "?stats=gameLog&group=pitching&season={season}")


def _get(url, tries=3):
    for i in range(tries):
        try:
            r = requests.get(url, timeout=30, headers={"User-Agent": "loscappers/1.0"})
            if r.status_code == 200:
                return r.json()
        except Exception as exc:          # noqa: BLE001 — logged, retried
            print(f"  GET failed ({exc}); retry {i + 1}")
        time.sleep(1.5 * (i + 1))
    return None


def _ip_to_outs(ip):
    """'5.2' -> 17. statsapi prints thirds after the decimal point."""
    try:
        whole, _, frac = str(ip).partition(".")
        return int(whole) * 3 + (int(frac) if frac else 0)
    except (TypeError, ValueError):
        return None


def parse_schedule(payload):
    """Finals as game_model rows, plus starter ids and team names.

    Excludes anything not Final, ties (suspended-and-never-resumed games
    carry equal scores), and games with no score — MISSING IS NOT ZERO.
    """
    out = []
    for d in (payload or {}).get("dates") or []:
        for g in d.get("games") or []:
            st = g.get("status") or {}
            if st.get("abstractGameState") != "Final":
                continue
            if "postponed" in str(st.get("detailedState", "")).lower():
                continue
            t = g.get("teams") or {}
            h, a = t.get("home") or {}, t.get("away") or {}
            hs, as_ = h.get("score"), a.get("score")
            if hs is None or as_ is None or hs == as_:
                continue
            ls = g.get("linescore") or {}
            sched = ls.get("scheduledInnings") or 9
            inn = ls.get("currentInning")
            extra = (inn > sched) if isinstance(inn, int) else None
            out.append({
                "date": g.get("officialDate") or str(g.get("gameDate", ""))[:10],
                "game_pk": g.get("gamePk"),
                "home": (h.get("team") or {}).get("name"),
                "away": (a.get("team") or {}).get("name"),
                "hs": int(hs), "as": int(as_), "extra": extra,
                "home_sp": str((h.get("probablePitcher") or {}).get("id") or "") or None,
                "away_sp": str((a.get("probablePitcher") or {}).get("id") or "") or None,
                "home_sp_name": (h.get("probablePitcher") or {}).get("fullName"),
                "away_sp_name": (a.get("probablePitcher") or {}).get("fullName"),
            })
    return out


def parse_gamelog(payload):
    """[(date, runs, outs)] for STARTS only, date order."""
    starts = []
    for blk in (payload or {}).get("stats") or []:
        for sp in blk.get("splits") or []:
            s = sp.get("stat") or {}
            if not s.get("gamesStarted"):
                continue
            outs = s.get("outs")
            if outs is None:
                outs = _ip_to_outs(s.get("inningsPitched"))
            runs = s.get("runs")
            if outs is None or runs is None:
                continue
            starts.append((str(sp.get("date"))[:10], int(runs), int(outs)))
    starts.sort()
    return starts


# ----------------------------------------------------------------------
# LAST SEASON (10-04): finals, starters and every player's outcome counts
# ----------------------------------------------------------------------
# Fetched ONCE (the first night data/mlb/prior_season.json is missing),
# committed by the nightly's "Commit MLB game model" step, read after
# that — last season does not change. The game model fits a carryover on
# it, the starter layer and the prop model weigh it by FITTED weights.
PRIOR_PATH = ROOT / "data" / "mlb" / "prior_season.json"
SEASON_STATS = ("https://statsapi.mlb.com/api/v1/stats?stats=season&group={group}"
                "&season={season}&sportId=1&gameType=R&playerPool=ALL&limit=5000")
GAMELOG_FULL = GAMELOG
# A full regular season is 2,430 games. Well short of that is an outage
# mid-fetch, and a partial season written once would be read forever.
PRIOR_MIN_FINALS = 2000


def parse_gamelog_bf(payload):
    """[batters faced] per START, date order — the prop model's depth
    evidence for last season."""
    out = []
    for blk in (payload or {}).get("stats") or []:
        for sp in blk.get("splits") or []:
            st = sp.get("stat") or {}
            if st.get("gamesStarted") and st.get("battersFaced") is not None:
                out.append((str(sp.get("date"))[:10], int(st["battersFaced"])))
    return [bf for _d, bf in sorted(out)]


def parse_season_counts(payload, group):
    """{player_id: {1B,2B,3B,HR,BB,K,OUT,PA}} from statsapi season stats —
    the same seven outcomes the prop model classifies Statcast into
    (walks include intentional walks, hit-by-pitch and catcher's
    interference). A player whose line lacks doubles or triples is LEFT
    OUT rather than having his hits split by a guess. A traded player's
    splits: the largest one is kept (statsapi may send a combined line
    alongside the per-team ones; the largest is never a double count)."""
    best = {}
    for blk in (payload or {}).get("stats") or []:
        for sp in blk.get("splits") or []:
            pid = str((sp.get("player") or {}).get("id") or "")
            st = sp.get("stat") or {}
            pa = st.get("plateAppearances") if group == "hitting" else st.get("battersFaced")
            need = ("hits", "doubles", "triples", "homeRuns", "baseOnBalls", "strikeOuts")
            if not pid or pa is None or any(st.get(k) is None for k in need):
                continue
            h, d, t, hr = (int(st[k]) for k in ("hits", "doubles", "triples", "homeRuns"))
            bb = int(st["baseOnBalls"]) + int(st.get("hitByPitch") or 0) \
                + int(st.get("catchersInterference") or 0)
            k = int(st["strikeOuts"])
            single = h - d - t - hr
            out = int(pa) - h - bb - k
            if single < 0 or out < 0:
                continue
            row = {"1B": single, "2B": d, "3B": t, "HR": hr, "BB": bb, "K": k, "OUT": out,
                   "PA": int(pa)}
            if pid not in best or row["PA"] > best[pid]["PA"]:
                best[pid] = row
    return best


def fetch_prior_season(season, _get_json=_get, sleep=0.05):
    """Everything last season gives every MLB model, or None if short."""
    finals = []
    m, end = date(season, 3, 1), date(season, 10, 5)
    while m <= end:
        nxt = (m.replace(day=28) + timedelta(days=4)).replace(day=1)
        stop = min(nxt - timedelta(days=1), end)
        finals.extend(parse_schedule(_get_json(SCHEDULE.format(start=m.isoformat(),
                                                               end=stop.isoformat()))))
        m = nxt
    print(f"  [verify] MLB {season} prior season: {len(finals)} regular-season finals")
    if len(finals) < PRIOR_MIN_FINALS:
        print(f"::warning::MLB {season} prior season short ({len(finals)} < "
              f"{PRIOR_MIN_FINALS}) — not saved; tonight runs on {season + 1} alone.")
        return None
    pids = sorted({f[s] for f in finals for s in ("home_sp", "away_sp") if f[s]})
    starters = {}
    for i, pid in enumerate(pids):
        pl = _get_json(GAMELOG.format(pid=pid, season=season))
        st = parse_gamelog(pl)
        if st:
            starters[pid] = {"r": sum(r for _, r, _ in st), "outs": sum(o for *_, o in st),
                             "gs": len(st), "bf": parse_gamelog_bf(pl)}
        if i % 100 == 0:
            print(f"  prior game logs {i}/{len(pids)}")
        time.sleep(sleep)
    names = {}
    for f in finals:
        for sd in ("home", "away"):
            if f[f"{sd}_sp"]:
                names[f[f"{sd}_sp"]] = f[f"{sd}_sp_name"]
    for pid, rec in starters.items():
        rec["name"] = names.get(pid)
    batters = parse_season_counts(_get_json(SEASON_STATS.format(group="hitting", season=season)),
                                  "hitting")
    pitchers = parse_season_counts(_get_json(SEASON_STATS.format(group="pitching", season=season)),
                                   "pitching")
    print(f"  [verify] MLB {season}: {len(starters)} starters with logs, "
          f"{len(batters)} batters / {len(pitchers)} pitchers with full outcome lines")
    return {"season": season, "finals": finals, "starters": starters,
            "batters": batters, "pitchers": pitchers}


def load_or_fetch_prior(season, _get_json=_get, path=None):
    path = Path(path or PRIOR_PATH)
    if path.exists():
        try:
            d = json.loads(path.read_text())
            if d.get("season") == season:
                return d
        except Exception as exc:          # noqa: BLE001
            print(f"  prior season file unreadable ({exc}) — refetching")
    d = fetch_prior_season(season, _get_json)
    if d:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(d, separators=(",", ":")))
    return d


def fit_starter_prior_weight(logs, prior_starters, priors):
    """How much a starter's LAST season counts next to this one, FITTED:
    this season's runs (per 9) and depth (outs per start) predicted from
    last season alone for every starter who pitched both."""
    if not priors or not prior_starters:
        return {"ra": 0.0, "outs": 0.0}
    ra_pairs, out_pairs = [], []
    for pid, s in logs.items():
        p = prior_starters.get(pid)
        if not s or not p or not p.get("gs"):
            continue
        r1, o1 = sum(r for _, r, _ in s), sum(o for *_, o in s)
        ra_pairs.append(((p["r"], p["outs"] / 27.0), (r1, o1 / 27.0)))
        out_pairs.append(((p["outs"], p["gs"]), (o1, len(s))))
    ra = mm.fit_prior_weight([(ra_pairs, priors["ra9_mean"], priors["ra9_strength_games"])],
                             kind="poisson")
    ou = mm.fit_prior_weight([(out_pairs, priors["outs_mean"], priors["outs_strength_starts"])],
                             kind="poisson")
    out = {"ra": (ra or {}).get("weight", 0.0), "outs": (ou or {}).get("weight", 0.0),
           "n_both_seasons": len(ra_pairs),
           "ra_loglik_gain": (ra or {}).get("loglik_gain"),
           "outs_loglik_gain": (ou or {}).get("loglik_gain")}
    return out


def fit_starter_priors(logs):
    """Gamma-Poisson priors for runs per nine and outs per start, fitted
    across every starter's season. Returns {} if nothing to fit."""
    ra_obs = [(sum(r for _, r, _ in s), sum(o for *_, o in s) / 27.0)
              for s in logs.values() if s]
    out_obs = [(sum(o for *_, o in s), len(s)) for s in logs.values() if s]
    ra_mu, ra_s = mm.fit_gamma_prior([x for x in ra_obs if x[1] > 0])
    out_mu, out_s = mm.fit_gamma_prior(out_obs)
    if ra_mu is None or out_mu is None:
        return {}
    return {"ra9_mean": round(ra_mu, 4), "ra9_strength_games": round(ra_s, 3),
            "outs_mean": round(out_mu, 3), "outs_strength_starts": round(out_s, 3)}


def make_starter_fn(logs, priors, prior_starters=None, weights=None):
    """starter_fn for game_model.walk_forward — his record BEFORE the
    game's date only, plus last season at the fitted weights (last season
    is entirely before every date in this one, so it is never look-ahead)."""
    def fn(final, side, league_rate):
        pid = final.get(f"{side}_sp")
        if not pid:
            return None
        s = logs.get(pid) or []
        before = [x for x in s if x[0] < final["date"]]
        rec = {"r": sum(r for _, r, _ in before), "outs": sum(o for *_, o in before),
               "gs": len(before)}
        return starter_layer(rec, priors, league_rate,
                             (prior_starters or {}).get(pid), weights)
    return fn


def fit_market_blend(finals, model, logs, priors, use_sp, lines=None, prior_finals=None,
                     prior_starters=None, sp_w=None):
    """The model's weight against the market (engines/market_blend), from
    this season's walk-forward predictions — the SAME ones the validation
    scored, starter layer included when it was used — joined to the line
    ESPN recorded for each game (data/market_lines/mlb_2026.json, written
    by market_history.py). Keys go through mlb_run_rates.canonical on
    both sides because statsapi and ESPN name clubs differently."""
    from engines import market_blend as mb
    from engines.mlb_run_rates import canonical
    if lines is None:
        lines = mb.load_lines(f"mlb_{model['season']}")
    p = model["params"]
    pt = pl = None
    if prior_finals:
        _pf = gm.clean_finals(prior_finals)
        pt, pl = gm.team_totals(_pf), gm.league_constants(_pf)["league_rate"]
    preds = gm.walk_forward(gm.clean_finals(finals), p["shrink_k"], p.get("dispersion"),
                            prior_totals=pt, prior_league=pl, carryover=p.get("carryover"),
                            starter_fn=make_starter_fn(logs, priors, prior_starters, sp_w)
                            if use_sp else None)
    p_over, p_cover = gm.blend_fns(p.get("dispersion"))

    def key(pr):
        h, a = canonical(pr["home"]), canonical(pr["away"])
        return mb.line_key(pr["date"], h, a) if h and a else None
    block = mb.fit_all(preds, lines, p_over, p_cover, key_fn=key)
    print(f"  [verify] market lines on file: {len(lines)}; coverage {block['coverage']}")
    for m in mb.MARKETS:
        print(f"  [verify] MLB {mb.describe(block, m)}")
    return block


def main(today=None, _get_json=_get):
    today = today or datetime.now(EASTERN).date()
    season = today.year
    # Regular season is March-September. Postseason games are NOT fitted
    # on — a playoff rotation and a 162-game sample are different
    # populations — but they ARE projected, from the regular season.
    start = date(season, 3, 1)
    end = min(today - timedelta(days=1), date(season, 10, 5))
    finals = []
    m = start
    while m <= end:
        nxt = (m.replace(day=28) + timedelta(days=4)).replace(day=1)
        stop = min(nxt - timedelta(days=1), end)
        payload = _get_json(SCHEDULE.format(start=m.isoformat(), end=stop.isoformat()))
        got = parse_schedule(payload)
        print(f"  schedule {m:%b}: {len(got)} finals")
        finals.extend(got)
        m = nxt
    if len(finals) < 100:
        print(f"MLB model: only {len(finals)} finals — refusing to fit on that.")
        return 1
    ex_known = sum(1 for f in finals if f["extra"] is not None)
    print(f"  [verify] {len(finals)} finals, {ex_known} with an inning count, "
          f"{sum(1 for f in finals if f['extra'])} extra-inning; "
          f"{sum(1 for f in finals if f['home_sp'] and f['away_sp'])} with both starters")

    # Starter game logs.
    pids = sorted({f[s] for f in finals for s in ("home_sp", "away_sp") if f[s]})
    names = {}
    for f in finals:
        for s in ("home", "away"):
            if f[f"{s}_sp"]:
                names[f[f"{s}_sp"]] = f[f"{s}_sp_name"]
    logs = {}
    for i, pid in enumerate(pids):
        logs[pid] = parse_gamelog(_get_json(GAMELOG.format(pid=pid, season=season)))
        if i % 50 == 0:
            print(f"  game logs {i}/{len(pids)}")
        time.sleep(0.05)
    with_logs = sum(1 for v in logs.values() if v)
    print(f"  [verify] {with_logs} of {len(pids)} starters returned a start log")
    priors = fit_starter_priors(logs)
    print(f"  [verify] starter priors: {priors}")

    # LAST SEASON: team carryover (fitted by walk-forward inside
    # game_model.build) and the starters' prior-season weight (fitted on
    # the starters who pitched both). Either missing -> this season alone.
    prior = None
    try:
        prior = load_or_fetch_prior(season - 1, _get_json)
    except Exception as exc:  # noqa: BLE001
        print(f"::warning::MLB prior season unavailable: {type(exc).__name__}: {exc}")
    prior_finals = (prior or {}).get("finals") or None
    prior_starters = (prior or {}).get("starters") or {}
    sp_w = fit_starter_prior_weight(logs, prior_starters, priors)
    print(f"  [verify] starter last-season weight: {sp_w}")

    model = gm.build(finals, prior_finals=prior_finals)
    if model is None:
        print("MLB model: fit failed.")
        return 1
    _pt = _pl = None
    if prior_finals:
        _pf = gm.clean_finals(prior_finals)
        _pt, _pl = gm.team_totals(_pf), gm.league_constants(_pf)["league_rate"]
        print(f"  [verify] team carryover from {season - 1}: {model['params'].get('carryover')} "
              f"(fitted by walk-forward; 0 = last season ignored)")
    team_only = model["validation"]
    with_sp = None
    if priors:
        with_sp = gm.validate(finals, model["params"], prior_totals=_pt, prior_league=_pl,
                              starter_fn=make_starter_fn(logs, priors, prior_starters, sp_w))
    use_sp = bool(with_sp and with_sp.get("n") and team_only.get("n")
                  and with_sp["model"]["log_loss"] < team_only["model"]["log_loss"])
    model["validation"] = with_sp if use_sp else team_only
    model["validation_team_only"] = team_only
    model["validation_with_starters"] = with_sp
    model["use_starters"] = use_sp
    model["starter_priors"] = priors
    model["starter_prior_weight"] = sp_w
    model["prior_season"] = season - 1 if prior else None
    # last season's starter lines for anyone starting tonight (the page
    # weighs them at starter_prior_weight)
    model["starters_prior"] = {pid: {k: v for k, v in rec.items() if k != "bf"}
                               for pid, rec in prior_starters.items()}
    model["starters"] = {pid: {"name": names.get(pid), "gs": len(s),
                               "r": sum(r for _, r, _ in s),
                               "outs": sum(o for *_, o in s)}
                         for pid, s in logs.items() if s}
    model["sport"] = "mlb"
    model["season"] = season
    # A blend failure costs the blend (every Final then IS the market and
    # the page says "untested"), never the model.
    try:
        model["blend"] = fit_market_blend(finals, model, logs, priors, use_sp,
                                          prior_finals=prior_finals,
                                          prior_starters=prior_starters, sp_w=sp_w)
    except Exception as exc:  # noqa: BLE001
        print(f"::warning::MLB market blend failed: {type(exc).__name__}: {exc}")
        model["blend"] = {}
    model["generated_at_et"] = datetime.now(EASTERN).strftime("%Y-%m-%d %H:%M")
    model["source"] = "statsapi.mlb.com schedule + pitcher game logs (regular season)"
    model["look_ahead_note"] = ("Starter priors (two numbers: the league's spread in "
                                "starter run prevention and depth) are fitted on full-"
                                "season totals; every team and starter rate in the "
                                "walk-forward uses only earlier games.")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(model, indent=1, sort_keys=True))
    v = model["validation"]
    print(f"MLB model: k={model['params']['shrink_k']} dispersion={model['params']['dispersion']} "
          f"home_mult={model['league']['home_mult']} extras home win={model['league']['tie_home_win']}")
    print(f"  walk-forward over {v['n']} games: log loss {v['model']['log_loss']} vs coin "
          f"{v['coin_flip']['log_loss']} vs home-rate {v['home_rate']['log_loss']} "
          f"| starters used: {use_sp}"
          + (f" (team-only {team_only['model']['log_loss']}, with starters "
             f"{with_sp['model']['log_loss']})" if with_sp else ""))
    print(f"  totals MAE {v['total_mae_model']} vs league-average {v['total_mae_league_avg']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
