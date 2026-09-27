"""Does any of the projection engine actually predict? Walk-forward.

WHY THIS EXISTS

nfl_projection.py ships with no fitted weights, because standing rule 1
says every number on this site chosen by eye turned out wrong when it
was finally measured. But "no free parameters" is not the same as
"correct" — the engine still makes three claims it has never tested:

  1. THE MATCHUP MULTIPLIER. Multiplying a player's rate by what the
     defence allows over the league average is the standard move, and it
     may well overshoot: defensive rates are themselves noisy early, and
     a 1.3x multiplier on three games of opponent data could be mostly
     schedule. Measured here against projecting with NO adjustment.

  2. THE SHARE. A carry or target share measured over a few games is
     used as next week's share. Does it predict, or does last week's
     share beat it, or a flat league-average share?

  3. THE POISSON STEP. P(anytime) = 1 - exp(-lambda) is the one
     assumption in the engine. Measured by bucketing players by
     projected probability and counting how many actually scored — a
     calibration curve, which is the only honest test of a probability.

HOW IT MEASURES

Walk-forward, never with hindsight. For each week W, profiles are built
from weeks BEFORE W only, projections are made for W's games, and they
are scored against W's real box scores. A model tested on data it was
built from will look excellent and tell you nothing.

Prints mean absolute error per market against two baselines:

    season average  — the player's own per-game average, no matchup
    last game       — what he did last week

A projection that cannot beat "his season average" is not earning its
complexity, and this says so in as many words rather than leaving it to
be inferred.

    python nfl_projection_probe.py [THROUGH_DATE]

Touches nothing: no files, no commit, no deploy.
"""
import sys
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "app"))

import nfl_precompute as pc  # noqa: E402
from engines import espn_feed as ef  # noqa: E402
from engines import nfl_projection as proj  # noqa: E402
from engines.nfl_week import SEASON_START, week_of  # noqa: E402


def collect(through):
    """Every final of the season, parsed once. {week: [(game, logs-slice)]}"""
    finals, logs = [], {}
    d = SEASON_START
    seen = 0
    while d <= through:
        try:
            sb, _src = ef.fetch_scoreboard("nfl", d.strftime("%Y%m%d"))
        except Exception as exc:
            print(f"  scoreboard {d} failed: {exc}")
            d += timedelta(days=1)
            continue
        for ev in sb.get("events") or []:
            g = pc.slate_game(ev)
            if not g or g["status"] != "final" or g.get("away_score") is None:
                continue
            seen += 1
            try:
                summ = ef.fetch_summary("nfl", g["event_id"])
                lines, _n = pc.parse_summary_final(
                    summ, g["event_id"], d.isoformat(), week_of(d), logs)
            except Exception as exc:
                print(f"  summary {g['event_id']} failed: {exc}")
                continue
            box = {ln["team"]: ln for ln in lines}
            finals.append({"date": d.isoformat(), "week": week_of(d),
                           "event_id": g["event_id"],
                           "away": g["away"], "home": g["home"],
                           "away_abbr": g.get("away_abbr"), "home_abbr": g.get("home_abbr"),
                           "away_score": g["away_score"], "home_score": g["home_score"],
                           "away_box": box.get(g["away"]), "home_box": box.get(g["home"]),
                           "odds": g.get("odds") or {}})
        d += timedelta(days=1)
    print(f"parsed {len(finals)} of {seen} finals through {through}")
    return finals, logs


def slice_logs(logs, weeks):
    """A copy of `logs` holding only games from `weeks`."""
    out = {}
    for pid, rec in logs.items():
        games = {eid: g for eid, g in (rec.get("games") or {}).items()
                 if g.get("week") in weeks}
        if games:
            out[pid] = dict(rec, games=games)
    return out


def actuals(logs, week):
    """{(pid, market): real value} for one week's games."""
    out = {}
    for pid, rec in logs.items():
        for _eid, g in (rec.get("games") or {}).items():
            if g.get("week") != week:
                continue
            r, c, pa = g.get("rushing") or {}, g.get("receiving") or {}, g.get("passing") or {}
            vals = {
                "Rushing yards": r.get("yds"), "Carries": r.get("att"),
                "Receiving yards": c.get("yds"), "Receptions": c.get("rec"),
                "Targets": c.get("tgt"), "Passing yards": pa.get("yds"),
                "Pass attempts": pa.get("att"),
                "Rush + rec yards": ((r.get("yds") or 0) + (c.get("yds") or 0)
                                     if (r or c) else None),
                "Anytime TD": (1 if ((r.get("td") or 0) + (c.get("td") or 0)) >= 1 else 0
                               if (r or c) else None),
            }
            for m, v in vals.items():
                if v is not None:
                    out[(pid, m)] = float(v)
    return out


def build_week(finals, logs, weeks, target_week):
    """Profiles from `weeks`, and the target week's games to project."""
    prior = [f for f in finals if f["week"] in weeks]
    plogs = slice_logs(logs, weeks)
    usage = pc.team_game_usage(plogs)
    league = pc.league_constants(prior, usage)
    # FIT THE TD PRIOR TOO, from the same prior weeks.
    #
    # Without this, `league` carries no prior_a/prior_b, attach_td_shares
    # silently takes its fallback path, and the probe measures the OLD
    # realised-share estimator while appearing to test the current one.
    # It did exactly that on its first run after the rebuild: the
    # workflow went green and the calibration curve it printed belonged
    # to the model that had just been replaced.
    league.update(pc.td_opportunity_prior(plogs))
    teams = pc.attach_ranks(pc.team_research(prior, usage))
    players = pc.player_summaries(plogs, usage)

    games = []
    for f in finals:
        if f["week"] != target_week:
            continue
        g = {"away": f["away"], "home": f["home"], "status": "scheduled",
             "away_abbr": f.get("away_abbr"), "home_abbr": f.get("home_abbr"),
             "odds": f.get("odds") or {}, "window": ""}
        for side in ("away", "home"):
            g[f"{side}_profile"] = teams.get(f[side])
            g[f"{side}_players"] = [
                dict(p) for p in players.values() if p.get("team") == f[side]
            ]
            for p in g[f"{side}_players"]:
                p["role"] = pc.role_of(p)
        games.append(g)
    return games, league, players


def main(through=None):
    through = through or date.today()
    finals, logs = collect(through)
    if not finals:
        print("no finals — nothing to measure")
        return
    weeks = sorted({f["week"] for f in finals if f["week"]})
    if len(weeks) < 2:
        print(f"only week(s) {weeks} on the books — a walk-forward test needs "
              f"at least two. Re-run once week {max(weeks) + 1} is final.")
        return

    err = defaultdict(list)       # (market, method) -> [abs error]
    pois = defaultdict(lambda: [0, 0])   # probability bucket -> [scored, n]
    # WHICH ESTIMATOR IS ACTUALLY BEING MEASURED, printed rather than
    # assumed. A probe that reports on a code path nobody is running is
    # worse than no probe: it reads as evidence.
    estimator = None

    for w in weeks[1:]:
        prior = [x for x in weeks if x < w]
        games, league, players = build_week(finals, logs, prior, w)
        if not league:
            continue
        if estimator is None:
            estimator = ("opportunity + fitted shrinkage"
                         if league.get("prior_a") is not None
                         else "realised TD share (FALLBACK)")
            print(f"\nanytime TD estimator under test: {estimator}")
            if league.get("prior_a") is not None:
                print(f"  prior fitted on {league.get('players_fitted')} players / "
                      f"{league.get('touches_fitted')} touches: "
                      f"{league.get('td_per_opportunity')} TD per touch, "
                      f"shrink strength {league.get('prior_strength')}")
        real = actuals(logs, w)
        for market in proj.MARKETS:
            rows = proj.projection_rows(games, league, market)
            for r in rows:
                p = r["_p"]
                pid = p.get("pid")
                a = real.get((pid, market))
                if a is None:
                    continue
                if market == "Anytime TD":
                    b = min(int((r["Proj"] or 0) // 10) * 10, 90)
                    pois[b][0] += a
                    pois[b][1] += 1
                    continue
                err[(market, "projection")].append(abs(r["Proj"] - a))
                # Baseline 1: his own season average to date, no matchup.
                base_key = {"Rushing yards": "rush_yds", "Carries": "rush_att",
                            "Receiving yards": "rece_yds", "Receptions": "rece_rec",
                            "Targets": "rece_tgt", "Passing yards": "pass_yds",
                            "Pass attempts": "pass_att"}.get(market)
                if base_key and p.get(base_key) is not None:
                    err[(market, "season avg")].append(abs(p[base_key] - a))
                # Baseline 2: what he did in his most recent game.
                log = p.get("log") or []
                lk = {"Rushing yards": "rush_yds", "Receiving yards": "rec_yds",
                      "Receptions": "rec", "Targets": "tgt",
                      "Passing yards": "pass_yds"}.get(market)
                if log and lk and log[-1].get(lk) is not None:
                    err[(market, "last game")].append(abs(log[-1][lk] - a))

    print("\n" + "=" * 68)
    print("MEAN ABSOLUTE ERROR — lower is better. n = player-games scored.")
    print("=" * 68)
    for market in proj.MARKETS:
        if market == "Anytime TD":
            continue
        line = []
        for method in ("projection", "season avg", "last game"):
            vals = err[(market, method)]
            if vals:
                line.append(f"{method} {sum(vals) / len(vals):6.2f} (n={len(vals)})")
        if line:
            print(f"\n{market}")
            for x in line:
                print(f"    {x}")
            pj = err[(market, "projection")]
            sa = err[(market, "season avg")]
            if pj and sa:
                d = (sum(sa) / len(sa)) - (sum(pj) / len(pj))
                verdict = ("BEATS the season average"
                           if d > 0 else "DOES NOT beat the season average")
                print(f"    -> {verdict} by {abs(d):.2f} yards/attempts")

    print("\n" + "=" * 68)
    print("ANYTIME TD CALIBRATION — does the Poisson step tell the truth?")
    print("A bucket projected at 30-40% should hit close to 35%.")
    print("=" * 68)
    for b in sorted(pois):
        scored, n = pois[b]
        if n:
            print(f"  projected {b:2d}-{b + 9:2d}%  ->  actually scored "
                  f"{100.0 * scored / n:5.1f}%  (n={n})")
    print("\nA curve that runs consistently above or below the projected band "
          "means the\nPoisson assumption or the TD share is biased — fix it "
          "there, not with a fudge\nfactor on the board (rule 1).")
    print(f"\nMeasured against: {estimator or 'nothing — no week had a league fit'}")
    if estimator and "FALLBACK" in estimator:
        print("*** The board does NOT use this estimator. The prior failed to "
              "fit, so\n*** these numbers describe a code path production "
              "never runs. Fix that\n*** before reading anything above.")


if __name__ == "__main__":
    arg = sys.argv[1] if len(sys.argv) > 1 else None
    main(date.fromisoformat(arg) if arg else None)
