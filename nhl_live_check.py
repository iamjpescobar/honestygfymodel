"""
The Live page, tested on last season (10-18) — run once by the manual
workflow `nhl-live-check.yml`; writes data/nhl/live_check.json, which the
Live page reads to decide which live calls may go above THIN.

WHAT IT ASKS
------------
At the end of the 1st and the 2nd period of every game in the last
DAYS days of 2025-26, what would the Live page (engines/live_props) have
said each skater's chance was over the REST of the game — for a goal,
2+ goals, a point, 2+ points, an assist — and what actually happened?

  - pregame chance: the model's own walk-forward mean for that game
    (nhl_model.rates / probs with the fitted ice-time factor), built only
    from games BEFORE it — what the page would have had that night;
  - what he had by the checkpoint: ESPN's scoring plays, period by period;
  - what happened: his final line in data/nhl/prior_season.json.

THE BAR (rule 1, the same one every prop clears)
-----------------------------------------------
Each market is paired against a naive live read — his own season rate
before that game, cut to the time left — on the same player-moments
(mm.paired_verdict on squared error). "beats" earns the market its
calibration curve on the Live page, and with it VALUE / STRONG; anything
else stays THIN. Calibration by checkpoint and by score state (his team
ahead / tied / behind) is reported too — score effects are the known
blind spot.

ESPN's NHL summary is read tolerantly (scoring plays from `plays` with
scoringPlay, or `scoringPlays`; scorer first, then assists when the
participants carry no type). The first game's shape is printed, and the
script refuses to write a file if no scoring plays could be read.
"""
import json
import math
import sys
import time
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "app"))

from engines import espn_feed as ef  # noqa: E402
from engines import game_model as gm  # noqa: E402
from engines import live_props as lp  # noqa: E402
from engines import model_math as mm  # noqa: E402
from engines import nhl_model as nm  # noqa: E402

PRIOR = ROOT / "data" / "nhl" / "prior_season.json"
OUT = ROOT / "data" / "nhl" / "live_check.json"
DAYS = 90
CHECKPOINTS = ((1, 2.0 / 3.0), (2, 1.0 / 3.0))        # (periods done, fraction left)
# (key, stat, line) — the markets the Live page prices from goals / assists
MARKETS = (("g1", "g", 0.5), ("g2", "g", 1.5), ("pt1", "pts", 0.5), ("pt2", "pts", 1.5),
           ("a1", "a", 0.5))


# ----------------------------------------------------------------------
# Pregame means, walk-forward (what the page would have had that night)
# ----------------------------------------------------------------------
def pregame_mu(prior, days=DAYS):
    """{(pid, date): mu} for every skater-game in the last `days` days."""
    pf = prior.get("finals") or []
    sk = prior.get("skaters") or {}
    model = nm.build([], prior, {}, {}, [], regular_ids=set())
    if not model:
        raise RuntimeError("the NHL model could not be fitted on the prior season")
    gk = model["params"]["shrink_k"]
    sk_k = (model.get("shots") or {}).get("params", {}).get("shrink_k") if model.get("shots") \
        else None
    toi = model.get("toi")
    priors = nm.fit_priors(sk)
    dates = sorted({x[0] for p in sk.values() for x in p["games"]})
    cut = dates[-days]
    g_env = nm._env_by_opp(gm.walk_forward(gm.clean_finals(nm.goal_rows(pf)), gk or 30.0))
    s_env = nm._env_by_opp(gm.walk_forward(gm.clean_finals(nm.shot_rows(pf)), sk_k or 30.0,
                                           score_only=True))
    out = {}
    for pid, p in sk.items():
        games = sorted(p["games"], key=lambda x: x[0])
        for i, (d, opp, _s, _g, _a, _t) in enumerate(games):
            if d < cut or i == 0:
                continue
            r = nm.rates(p, priors, before=d)
            if not r:
                continue
            ge, se = g_env.get((d, opp)), s_env.get((d, opp))
            gr = ge[0] / ge[1] if ge and ge[1] else 1.0
            sr = se[0] / se[1] if se and se[1] else 1.0
            sc = nm.toi_scales(games[:i], toi, p.get("pp"))
            pr = nm.probs(r, sr, gr, priors.get("sog_dispersion"),
                          toi_sog=sc["sog"], toi_pts=sc["pts"])
            if pr and pr.get("_mu"):
                out[(str(pid), d)] = pr["_mu"]
    return out, cut


# ----------------------------------------------------------------------
# ESPN scoring plays, period by period
# ----------------------------------------------------------------------
def _period(play):
    p = play.get("period")
    if isinstance(p, dict):
        p = p.get("number")
    try:
        return int(p)
    except (TypeError, ValueError):
        return None


def parse_scoring(summary):
    """{"pids": {pid: {period: {"g", "a"}}}, "teams": {team_id: {period: goals}},
    "n": scoring plays read}. Shootout 'goals' (period 5+) are dropped."""
    plays = [p for p in ((summary or {}).get("plays") or []) if p.get("scoringPlay")]
    if not plays:
        plays = list((summary or {}).get("scoringPlays") or [])
    pids, teams, n = {}, {}, 0
    for pl in plays:
        per = _period(pl)
        if per is None or per >= 5:
            continue
        parts = pl.get("participants") or []
        ids = []
        for x in parts:
            ath = (x or {}).get("athlete") or {}
            if ath.get("id"):
                ids.append((str(ath["id"]), str((x or {}).get("type") or "").lower()))
        if not ids:
            continue
        n += 1
        typed = any(t for _i, t in ids)
        for k, (pid, t) in enumerate(ids):
            if typed:
                kind = "g" if "scor" in t else ("a" if "assist" in t else None)
            else:
                kind = "g" if k == 0 else "a"
            if kind:
                slot = pids.setdefault(pid, {}).setdefault(per, {"g": 0, "a": 0})
                slot[kind] += 1
        tid = str(((pl.get("team") or {}).get("id")) or "")
        if tid:
            teams.setdefault(tid, {}).setdefault(per, 0)
            teams[tid][per] += 1
    return {"pids": pids, "teams": teams, "n": n}


def have_by(scoring_for_pid, periods_done):
    g = a = 0
    for per, x in (scoring_for_pid or {}).items():
        if per <= periods_done:
            g += x["g"]
            a += x["a"]
    return {"g": g, "a": a, "pts": g + a}


# ----------------------------------------------------------------------
# The test
# ----------------------------------------------------------------------
def own_rate(games_before, stat):
    vals = [{"g": x[3] or 0, "a": x[4] or 0, "pts": (x[3] or 0) + (x[4] or 0)}[stat]
            for x in games_before]
    return sum(vals) / len(vals) if vals else None


def evaluate(prior, mu_map, game_scoring):
    """game_scoring: {date: [parsed scoring dicts]} for the window.
    -> {"markets": {key: {...}}, "by_checkpoint": {...}, "by_state": {...}}"""
    sk = prior.get("skaters") or {}
    rows = {k: [] for k, *_ in MARKETS}
    base = {k: [] for k, *_ in MARKETS}
    by_cp, by_state = {}, {}
    for pid, p in sk.items():
        games = sorted(p["games"], key=lambda x: x[0])
        for i, (d, opp, _s, g, a, _t) in enumerate(games):
            mu = mu_map.get((str(pid), d))
            if not mu or d not in game_scoring:
                continue
            # his game that night: the one his opponent played in
            sc = next((s for s in game_scoring[d] if str(opp) in s.get("team_ids", ())), None)
            if sc is None:
                continue
            tm = next((t for t in sc["team_ids"] if t != str(opp)), None)
            final = {"g": int(g or 0), "a": int(a or 0)}
            final["pts"] = final["g"] + final["a"]
            for done, f in CHECKPOINTS:
                have = have_by(sc["pids"].get(str(pid)), done)
                us = sum(v for per, v in (sc["teams"].get(tm) or {}).items() if per <= done)
                them = sum(v for per, v in (sc["teams"].get(str(opp)) or {}).items()
                           if per <= done)
                state = "ahead" if us > them else ("behind" if us < them else "tied")
                for key, stat, line in MARKETS:
                    nd = lp.need(line, have[stat])
                    if nd <= 0:
                        continue                         # already cashed: nothing to price
                    ch, _ = lp.nhl_chance(mu, stat, line, have[stat], f)
                    rate = own_rate(games[:i], stat)
                    if ch is None or rate is None:
                        continue
                    naive = lp.over_chance(lp.rest_pmf("poisson", rate, f), nd)
                    y = 1 if final[stat] > line else 0
                    rows[key].append((ch, y))
                    base[key].append((naive, y))
                    by_cp.setdefault(f"{key}@P{done}", []).append((ch, y))
                    by_state.setdefault(f"{key}:{state}", []).append((ch, y))
    out = {"markets": {}, "by_checkpoint": {}, "by_state": {}}
    for key, *_ in MARKETS:
        m, b = mm.score_predictions(rows[key]), mm.score_predictions(base[key])
        out["markets"][key] = {
            "n": m["n"], "model_brier": m["brier"], "baseline_brier": b["brier"],
            "verdict": mm.paired_verdict([(q - y) ** 2 for q, y in rows[key]],
                                         [(q - y) ** 2 for q, y in base[key]]),
            "calibration": mm.calibration_bins(rows[key])}
    for name, src in (("by_checkpoint", by_cp), ("by_state", by_state)):
        for k, v in sorted(src.items()):
            out[name][k] = {"n": len(v), "predicted": round(sum(q for q, _ in v) / len(v), 4),
                            "actual": round(sum(y for _, y in v) / len(v), 4)}
    return out


# ----------------------------------------------------------------------
# Run
# ----------------------------------------------------------------------
def collect(dates, sb_fn, summary_fn, sleep=0.08, probe=None):
    out, seen, read = {}, 0, 0
    for d in dates:
        try:
            sb = sb_fn(date.fromisoformat(d))
        except Exception as exc:  # noqa: BLE001
            print(f"  scoreboard {d} failed: {exc}")
            continue
        for ev in (sb or {}).get("events") or []:
            st, done, _ = ef.status_of(ev)
            if st != "final":
                continue
            seen += 1
            try:
                summ = summary_fn(str(ev.get("id")))
            except Exception as exc:  # noqa: BLE001
                print(f"  summary {ev.get('id')} failed: {exc}")
                continue
            if probe is not None and not probe:
                plays = (summ or {}).get("plays") or []
                sp = [p for p in plays if p.get("scoringPlay")][:1]
                probe.update({"keys": sorted(summ or {})[:25], "plays": len(plays),
                              "first_scoring_play": json.dumps(sp[0])[:600] if sp else None,
                              "scoringPlays": len((summ or {}).get("scoringPlays") or [])})
            sc = parse_scoring(summ)
            sc["team_ids"] = sorted(str((c.get("team") or {}).get("id") or c.get("id") or "")
                                    for c in ((ev.get("competitions") or [{}])[0] or {})
                                    .get("competitors") or [])
            if sc["n"]:
                read += 1
                out.setdefault(d, []).append(sc)
            time.sleep(sleep)
    return out, seen, read


def main():
    prior = json.loads(PRIOR.read_text())
    t0 = time.time()
    mu_map, cut = pregame_mu(prior)
    print(f"  [verify] pregame means: {len(mu_map):,} skater-games from {cut} "
          f"({time.time() - t0:.0f}s)")
    dates = sorted({d for (_p, d) in mu_map})
    probe = {}
    games, seen, read = collect(dates, lambda d: ef.fetch_scoreboard("nhl", d.strftime("%Y%m%d"))[0],
                                lambda eid: ef.fetch_summary("nhl", eid), probe=probe)
    print(f"  [verify] ESPN summary probe: {probe}")
    print(f"  [verify] {seen} finals in the window, {read} with scoring plays read")
    if not read:
        print("::error::no scoring plays could be read - not writing live_check.json")
        return 1
    res = evaluate(prior, mu_map, games)
    for key, x in res["markets"].items():
        v = x.get("verdict") or {}
        print(f"  [verify] live {key}: n={x['n']} model {x['model_brier']} vs own-rate "
              f"{x['baseline_brier']} -> {v.get('verdict')} (z={v.get('z')})")
    for key, x in res["by_state"].items():
        print(f"  [verify] live {key}: n={x['n']} predicted {x['predicted']} actual {x['actual']}")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(dict(res, season=prior.get("season"), window_from=cut,
                                   games_read=read), indent=1))
    print(f"  wrote {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
