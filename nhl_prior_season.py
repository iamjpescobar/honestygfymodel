"""
Last NHL season, once — the evidence the NHL model stands on in October.

WHY THIS EXISTS
---------------
On Oct 3 the 2026-27 season is five days old. Nothing can be FITTED on a
few dozen games, and a team's rating built from three games is noise. So
the NHL model fits its parameters on the 2025-26 regular season and
carries each team forward from it by a MEASURED carryover; this season's
own games take over as they accumulate (engines/game_model.build).

This script builds data/nhl/prior_season.json from ESPN's public API:
every 2025-26 regular-season final (team ids, score, OT/SO, shots) and
every skater's game-by-game line (date, opponent, SOG, G, A, TOI). It is
run by the manual workflow `nhl-prior-season.yml` and the file is
COMMITTED — last season does not change, so re-fetching ~1,300 box
scores every night would be pure cost. nhl_precompute reads it.

Keyed by ESPN TEAM ID, never display name: Utah changed its name between
the seasons and a name key would silently drop it from the carryover.

Prints [verify] lines; refuses to write a file with no box scores.
"""
import json
import sys
import time
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "app"))
from engines import espn_feed as ef  # noqa: E402
import nhl_precompute as nhp         # noqa: E402

LEAGUE = "nhl"
SEASON = "2025-26"
# Wide on both ends on purpose: the date window only decides which days
# are ASKED; ESPN's own season.type decides what counts (2 = regular).
START, END = date(2025, 9, 25), date(2026, 4, 25)
OUT = ROOT / "data" / "nhl" / "prior_season.json"
# Power-play minutes per skater-game (10-09), kept BESIDE prior_season.json
# rather than inside its game rows: every reader unpacks those rows as six
# fields, and a seventh would break them all. {pid: {date: PP minutes}}.
# nhl_precompute lays it over the skaters as "pp".
PP_OUT = ROOT / "data" / "nhl" / "prior_pp.json"
# 2025-26 regular season, opening night to the last scheduled game. Used
# ONLY when an event carries no season type of its own.
REGULAR = (date(2025, 10, 7), date(2026, 4, 16))


def _extra(g):
    d = str(g.get("detail") or "").upper()
    if "OT" in d or "SO" in d:
        return True
    if "FINAL" in d:
        return False
    return None


def collect(sb_fn, summary_fn, start=START, end=END, sleep=0.08):
    finals, skaters, goalies, names = [], {}, {}, {}
    d = start
    seen = parsed = 0
    while d <= end:
        try:
            sb = sb_fn(d)
        except Exception as exc:          # noqa: BLE001 — logged, day skipped
            print(f"  scoreboard {d} failed: {exc}")
            d += timedelta(days=1)
            continue
        for ev in (sb or {}).get("events") or []:
            stype = (ev.get("season") or {}).get("type") if isinstance(ev.get("season"), dict) else None
            # ESPN's own season type decides when it is present. Some
            # mirror shapes drop the season block (the header reshape in
            # espn_feed), and requiring it would skip EVERY game; then the
            # 2025-26 schedule's published regular-season window decides.
            if stype is None:
                stype = 2 if REGULAR[0] <= d <= REGULAR[1] else None
            if stype != 2:
                continue
            g = nhp.slate_game(ev, d)
            if not g or g["status"] != "final" or g.get("away_score") is None:
                continue
            seen += 1
            names[g["home_id"]], names[g["away_id"]] = g["home"], g["away"]
            name_to_id = {g["home"]: g["home_id"], g["away"]: g["away_id"]}
            sk, gk = {}, {}
            try:
                summ = summary_fn(g["event_id"])
                tb, n_s, n_g = nhp.parse_summary(summ, g["event_id"], d.isoformat(), sk, gk)
            except Exception as exc:      # noqa: BLE001
                print(f"  summary {g['event_id']} failed: {exc}")
                continue
            extra = nhp.went_to_extra(summ, g.get("detail") or "")
            if extra is None:
                extra = _extra(g)
            finals.append({
                "date": d.isoformat(), "home": g["home_id"], "away": g["away_id"],
                "hs": g["home_score"], "as": g["away_score"], "extra": extra,
                "home_sog": (tb.get(g["home"]) or {}).get("sog"),
                "away_sog": (tb.get(g["away"]) or {}).get("sog"),
            })
            if not (n_s and n_g):
                continue
            parsed += 1
            for pid, rec in sk.items():
                line = rec["games"].get(str(g["event_id"])) or {}
                team_id = name_to_id.get(rec.get("team"))
                opp_id = name_to_id.get(line.get("opp"))
                s = skaters.setdefault(pid, {"name": rec.get("name"), "pos": rec.get("pos") or "",
                                             "team": team_id, "games": []})
                s["team"] = team_id
                s["games"].append([d.isoformat(), opp_id, line.get("sog"), line.get("g"),
                                   line.get("a"), line.get("toi")])
                if line.get("pptoi") is not None:
                    s.setdefault("pp", {})[d.isoformat()] = round(line["pptoi"], 2)
            for pid, rec in gk.items():
                line = rec["games"].get(str(g["event_id"])) or {}
                gg = goalies.setdefault(pid, {"name": rec.get("name"), "team": None,
                                              "sa": 0, "sv": 0, "starts": 0, "gp": 0})
                gg["team"] = name_to_id.get(rec.get("team"))
                gg["gp"] += 1
                gg["sa"] += int(line.get("sa") or 0)
                gg["sv"] += int(line.get("sv") or 0)
                gg["starts"] += 1 if line.get("started") else 0
            time.sleep(sleep)
        d += timedelta(days=1)
    return finals, skaters, goalies, names, seen, parsed


def pp_file(skaters):
    """{pid: {date: PP minutes}} for every skater with any PP cell."""
    return {pid: s["pp"] for pid, s in skaters.items() if s.get("pp")}


def write_pp(skaters, path=None):
    """Write prior_pp.json; refuses when no line carried PP minutes (an
    empty file would read as 'nobody played the power play')."""
    pp = pp_file(skaters)
    n = sum(len(v) for v in pp.values())
    lines = sum(len(s["games"]) for s in skaters.values())
    print(f"  [verify] PP minutes on {n} of {lines} skater-games ({len(pp)} skaters)")
    if not n:
        print("Refusing to write prior_pp.json: no PP minutes in the feed.")
        return False
    path = Path(path or PP_OUT)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(pp, separators=(",", ":"), sort_keys=True))
    print(f"  wrote {path} ({path.stat().st_size / 1024:.0f} KB)")
    return True


def main(argv=None):
    """--pp-only: collect the season again but write ONLY prior_pp.json,
    leaving prior_season.json (and every number fitted on it) untouched."""
    argv = sys.argv[1:] if argv is None else argv
    finals, skaters, goalies, names, seen, parsed = collect(
        lambda d: ef.fetch_scoreboard(LEAGUE, d.strftime("%Y%m%d"))[0],
        lambda eid: ef.fetch_summary(LEAGUE, eid))
    if "--pp-only" in argv:
        print(f"  [verify] {SEASON}: {seen} finals seen, {parsed} box scores parsed (PP only)")
        return 0 if parsed and write_pp(skaters) else 1
    print(f"  [verify] {SEASON}: {seen} regular-season finals seen, {parsed} box scores parsed, "
          f"{len(skaters)} skaters, {len(goalies)} goalies, "
          f"{sum(1 for f in finals if f['extra'])} OT/SO, "
          f"{sum(1 for f in finals if f['home_sog'] is not None)} with team shots")
    if not finals or not parsed:
        print("Refusing to write: no box scores parsed.")
        return 1
    if skaters:
        top = max(skaters.values(), key=lambda s: sum(x[2] or 0 for x in s["games"]))
        print(f"  [verify] SOG leader: {top['name']} — {sum(x[2] or 0 for x in top['games'])} "
              f"shots in {len(top['games'])} GP")
    write_pp(skaters)
    skaters = {pid: {k: v for k, v in s.items() if k != "pp"} for pid, s in skaters.items()}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({"season": SEASON, "finals": finals, "skaters": skaters,
                               "goalies": goalies, "team_names": names},
                              separators=(",", ":")))
    print(f"  wrote {OUT} ({OUT.stat().st_size / 1024:.0f} KB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
