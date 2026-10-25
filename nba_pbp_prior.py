"""
Last NBA season's play-by-play, once (10-21) — what the First Basket page
and the quarter / half lines are fitted and TESTED on.

For every 2025-26 final in data/nba/prior_season.json (its event ids), the
game summary from ESPN -> engines/nba_pbp.parse: tip, first field goal,
first point, each quarter's score per team, starters, each player's
points per quarter. Run by the manual workflow `nba-pbp-prior.yml`; the
file is committed (last season does not change).

Writes data/nba/prior_pbp.json: {"season", "games": {event_id: {"date",
"home", "away", ...parse()}}}. Refuses to write when fewer than 80% of
games have a first field goal, quarter lines and starters — a shape
change at ESPN must not become a quiet hole in a model.
"""
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "app"))

from engines import espn_feed as ef  # noqa: E402
from engines import nba_pbp as pb  # noqa: E402

PRIOR = ROOT / "data" / "nba" / "prior_season.json"
OUT = ROOT / "data" / "nba" / "prior_pbp.json"
MIN_SHARE = 0.80


def collect(finals, summary_fn, sleep=0.06):
    games, bad = {}, []
    for k, f in enumerate(finals):
        eid = f.get("event_id")
        if not eid:
            continue
        try:
            summ = summary_fn(eid)
        except Exception as exc:  # noqa: BLE001 — logged, game skipped
            print(f"  summary {eid} failed: {exc}")
            continue
        rec = pb.parse(summ)
        bad += [f"{eid}: {b}" for b in pb.check(rec, f.get("hs"), f.get("as"), f.get("home"),
                                                 f.get("away"))]
        games[eid] = dict(rec, date=f["date"], home=f.get("home"), away=f.get("away"))
        if k and k % 200 == 0:
            print(f"  ... {k} games")
        time.sleep(sleep)
    return games, bad


def summary(games, n_finals):
    n = len(games) or 1
    has = {k: sum(1 for g in games.values() if g.get(k)) for k in
           ("lines", "tip", "first_fg", "first_score", "starters", "qpts", "early",
            "team_first_fg")}
    tip_team = sum(1 for g in games.values() if (g.get("tip") or {}).get("team"))
    fg_starter = sum(1 for g in games.values() if g.get("first_fg") and g["first_fg"]["pid"]
                     in sum((g.get("starters") or {}).values(), []))
    tip_first = sum(1 for g in games.values() if (g.get("tip") or {}).get("team")
                    and g.get("first_fg") and g["tip"]["team"] == g["first_fg"]["team"])
    both = sum(1 for g in games.values() if (g.get("tip") or {}).get("team") and g.get("first_fg"))
    # 10-25: the first three minutes — how often a starter scores in them
    st_n = st_hit = 0
    for g in games.values():
        early = g.get("early") or {}
        for ps in (g.get("starters") or {}).values():
            for p_ in ps:
                st_n += 1
                st_hit += 1 if (early.get(p_) or [0])[0] > 0 else 0
    return {"games": len(games), "finals": n_finals, "has": has, "tip_team": tip_team,
            "starter_scores_early": st_hit / max(1, st_n),
            "first_fg_by_starter": fg_starter / max(1, has["first_fg"]),
            "tip_team_scores_first": tip_first / max(1, both),
            "ok": all(has[k] >= MIN_SHARE * n for k in ("lines", "first_fg", "starters"))}


def main():
    prior = json.loads(PRIOR.read_text())
    finals = prior.get("finals") or []
    games, bad = collect(finals, lambda eid: ef.fetch_summary("nba", eid))
    s = summary(games, len(finals))
    print(f"  [verify] NBA play-by-play: {s['games']} of {s['finals']} finals read; with quarter "
          f"lines {s['has']['lines']}, a tip {s['has']['tip']} (possession team "
          f"{s['tip_team']}), a first field goal {s['has']['first_fg']}, a first point "
          f"{s['has']['first_score']}, starters {s['has']['starters']}, quarter points "
          f"{s['has']['qpts']}")
    print(f"  [verify] first field goal by a starter: {100 * s['first_fg_by_starter']:.1f}%; "
          f"the team that won the tip scored the first field goal: "
          f"{100 * s['tip_team_scores_first']:.1f}%")
    print(f"  [verify] first 3 minutes: read in {s['has']['early']} games, each team's first "
          f"field goal in {s['has']['team_first_fg']}; a starter scored in the first 3 minutes "
          f"{100 * s['starter_scores_early']:.1f}% of the time")
    print(f"  [verify] quarter lines that don't add up to the final: {len(bad)}"
          + (f" (first: {bad[:3]})" if bad else ""))
    fg = {}
    for g in games.values():
        x = g.get("first_fg")
        if x and x.get("pid"):
            fg[x["pid"]] = fg.get(x["pid"], 0) + 1
    names = {pid: p.get("name") for pid, p in (prior.get("players") or {}).items()}
    top = sorted(fg.items(), key=lambda kv: -kv[1])[:5]
    print("  [verify] most first baskets: " + ", ".join(f"{names.get(p, p)} {n}" for p, n in top))
    if not s["ok"]:
        print(f"Refusing to write: fewer than {int(100 * MIN_SHARE)}% of games parsed — ESPN's "
              f"shape may have changed. Send the log.")
        return 1
    OUT.write_text(json.dumps({"season": prior.get("season"), "games": games},
                              separators=(",", ":")))
    print(f"  wrote {OUT} ({OUT.stat().st_size / 1024:.0f} KB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
