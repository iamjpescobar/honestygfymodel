"""
Last NHL season's shot attempts and scoring chances, once (10-22) — what
the attempt (iCF / iFF) and chance (iSCF / iHDCF) factors in
engines/nhl_model are fitted and TESTED on.

For every 2025-26 regular-season game: the NHL's own play-by-play
(api-web.nhle.com) -> engines/nhl_shots.parse_pbp -> each skater's
[icf, iff, isf, g, iscf, ihdcf, g_sc, g_hd], matched by name to the ESPN
ids in data/nhl/prior_season.json (the ESPN game is found by the most
skater names in common, so team abbreviations never have to agree).
Run by the manual workflow `nhl-shots-prior.yml`; the file is committed
(last season does not change).

Writes data/nhl/prior_shots.json: {"season", "players": {espn_pid:
{date: row}}}. Refuses to write when fewer than 85% of the skater-games
with an attempt are matched to ESPN, or fewer than 90% of matched
skater-games' shots on goal equal ESPN's box score — a shape change must
not become a quiet hole in a model.

collect() is shared with the nightly (nhl_precompute.current_shots).
"""
import json
import sys
import time
from collections import Counter
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "app"))
from engines import nhl_shots as ns  # noqa: E402

API = "https://api-web.nhle.com/v1"
PRIOR = ROOT / "data" / "nhl" / "prior_season.json"
OUT = ROOT / "data" / "nhl" / "prior_shots.json"
REGULAR = (date(2025, 10, 7), date(2026, 4, 16))
MIN_MATCH = 0.85
MIN_SOG_OK = 0.90


def schedule_games(get, start, end):
    """[(date iso, NHL game id)] — regular-season games that are over,
    one schedule call a week (each returns a seven-day gameWeek)."""
    out, seen = [], set()
    d = start
    while d <= end:
        try:
            sched = get(f"{API}/schedule/{d.isoformat()}")
        except Exception as exc:  # noqa: BLE001
            print(f"  schedule {d} failed: {exc}")
            d += timedelta(days=7)
            continue
        for wk in sched.get("gameWeek") or []:
            day = str(wk.get("date") or "")
            if not day or day < start.isoformat() or day > end.isoformat():
                continue
            for g in wk.get("games") or []:
                gid = g.get("id")
                if gid in seen or str(g.get("gameType")) != "2" \
                        or str(g.get("gameState") or "").upper() not in ("OFF", "FINAL"):
                    continue
                seen.add(gid)
                out.append((day, gid))
        d += timedelta(days=7)
    return sorted(out)


def collect(get, games, espn_by_date, sleep=0.05):
    """(rows {(date, espn_pid): SHOT_ROW}, stats Counter, samples [str]).
    espn_by_date: {date: {game_key: {espn_pid: name}}}."""
    rows, st, samples = {}, Counter(), []
    for day, gid in games:
        try:
            pbp = get(f"{API}/gamecenter/{gid}/play-by-play")
        except Exception as exc:  # noqa: BLE001
            print(f"  play-by-play {gid} failed: {exc}")
            st["failed"] += 1
            continue
        rec = ns.parse_pbp(pbp)
        st["games"] += 1
        st["attempts"] += rec["attempts"]
        st["located"] += rec["located"]
        for k, v in rec["kinds"].items():
            st[k] += v
        key = ns.best_game(rec, espn_by_date.get(day) or {})
        if key is None:
            st["games_unmatched"] += 1
            continue
        m = ns.match_game(rec, espn_by_date[day][key])
        for npid, row in rec["shots"].items():
            if str((rec["players"].get(npid) or {}).get("pos") or "").upper() == "G":
                continue
            st["skater_games"] += 1
            e = m.get(npid)
            if e is None:
                st["skater_games_unmatched"] += 1
                if len(samples) < 6:
                    samples.append((rec["players"].get(npid) or {}).get("name"))
                continue
            rows[(day, e)] = row
        time.sleep(sleep)
    return rows, st, samples


def prior_espn(prior):
    """({date: {game_key: {pid: name}}}, {(date, pid): sog}) from last
    season's file: a skater's game is the final that day his opponent
    played in."""
    games_on = {}
    for f in prior.get("finals") or []:
        games_on.setdefault(f["date"], []).append((str(f["home"]), str(f["away"])))
    by_date, sog = {}, {}
    for pid, p in (prior.get("skaters") or {}).items():
        for row in p.get("games") or []:
            d, opp = row[0], str(row[1])
            g = next((x for x in games_on.get(d, []) if opp in x), None)
            if not g:
                continue
            by_date.setdefault(d, {}).setdefault(g, {})[pid] = p.get("name")
            if row[2] is not None:
                sog[(d, pid)] = int(row[2])
    return by_date, sog


def report(rows, st, samples, espn_sog, label):
    ck = ns.check(rows, espn_sog)
    sg = max(1, st["skater_games"])
    print(f"  [verify] {label}: {st['games']} games read ({st['failed']} failed, "
          f"{st['games_unmatched']} not found on ESPN); attempts {st['attempts']} "
          f"({100 * st['located'] / max(1, st['attempts']):.1f}% with a spot on the ice); "
          f"kinds {dict((k, st[k]) for k in ('goal', 'sog', 'miss', 'block'))}")
    print(f"  [verify] {label}: skater-games with an attempt {st['skater_games']}, matched to "
          f"ESPN {100 * (sg - st['skater_games_unmatched']) / sg:.1f}%; shots on goal equal to "
          f"ESPN's box {100 * ck['sog_ok'] / max(1, ck['skater_games']):.1f}% of "
          f"{ck['skater_games']}; unmatched names (first few): {samples}")
    if rows:
        t = [sum(r[i] for r in rows.values()) for i in range(len(ns.SHOT_ROW))]
        print(f"  [verify] {label}: per skater-game iCF {t[0] / len(rows):.2f}, iFF "
              f"{t[1] / len(rows):.2f}, iSF {t[2] / len(rows):.2f}, iSCF {t[4] / len(rows):.2f}, "
              f"iHDCF {t[5] / len(rows):.2f}; goals per attempt: high-danger "
              f"{t[7] / max(1, t[5]):.3f}, other chances {(t[6] - t[7]) / max(1, t[4] - t[5]):.3f}"
              f", the rest {(t[3] - t[6]) / max(1, t[1] - t[4]):.3f}")
    return ck


def main():
    from engines import espn_feed as ef
    prior = json.loads(PRIOR.read_text())
    by_date, sog = prior_espn(prior)
    games = schedule_games(ef.get_json, *REGULAR)
    print(f"  [verify] NHL schedule: {len(games)} regular-season games")
    rows, st, samples = collect(ef.get_json, games, by_date)
    ck = report(rows, st, samples, sog, "NHL prior shots")
    sg = max(1, st["skater_games"])
    match = (sg - st["skater_games_unmatched"]) / sg
    ok = ck["sog_ok"] / max(1, ck["skater_games"])
    if match < MIN_MATCH or ok < MIN_SOG_OK:
        print(f"Refusing to write: {100 * match:.1f}% of skater-games matched (need "
              f"{int(100 * MIN_MATCH)}%), {100 * ok:.1f}% of shots on goal agree with ESPN (need "
              f"{int(100 * MIN_SOG_OK)}%) - the feed's shape may have changed. Send the log.")
        return 1
    players = {}
    for (d, pid), row in rows.items():
        players.setdefault(pid, {})[d] = row
    OUT.write_text(json.dumps({"season": prior.get("season"), "players": players},
                              separators=(",", ":")))
    print(f"  wrote {OUT} ({OUT.stat().st_size / 1024:.0f} KB, {len(players)} skaters)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
