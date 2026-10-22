"""
Last NFL season's quarters, once (10-22) — what the quarter / half lines
and the 1st-quarter / 1st-half player props are fitted and TESTED on.

For every 2025 final in data/nfl/prior_logs.json (its event ids), the game
summary -> engines/nfl_quarters.parse: each quarter's points per team, and
every player's passing, rushing and receiving line by quarter, read from
the drives' play text and CHECKED against his own box score (the same
summary). Run by the manual workflow `nfl-quarters-prior.yml`; the file
is committed (last season does not change).

Writes data/nfl/prior_quarters.json: {"season", "games": {event_id:
{"date", "week", "home", "away", "lines", "players"}}}. Refuses to write
when fewer than 80% of games have quarter lines, or fewer than 80% of
players' quarters add up to their box-score rushing and receiving yards.
Prints play types and a few play texts the names were NOT found in, so a
new text shape can be read from the log.
"""
import json
import sys
import time
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "app"))
from engines import espn_feed as ef  # noqa: E402
from engines import nfl_quarters as nq  # noqa: E402
import nfl_precompute as pc  # noqa: E402

PRIOR = ROOT / "data" / "nfl" / "prior_logs.json"
OUT = ROOT / "data" / "nfl" / "prior_quarters.json"
MIN_SHARE = 0.80


def box_of(summary, eid):
    """{pid: {stat: total}} from the summary's own box score (the nightly's
    parser), in nfl_quarters' stat names."""
    logs = {}
    pc.parse_summary_final(summary, eid, "", 0, logs)
    out = {}
    for pid, rec in logs.items():
        g = (rec.get("games") or {}).get(str(eid)) or {}
        p, r, c = g.get("passing") or {}, g.get("rushing") or {}, g.get("receiving") or {}
        b = {"pass_yds": p.get("yds"), "pass_att": p.get("att"), "pass_cmp": p.get("cmp"),
             "pass_td": p.get("td"), "rush_yds": r.get("yds"), "carries": r.get("att"),
             "rec_yds": c.get("yds"), "rec": c.get("rec"), "targets": c.get("tgt")}
        if r or c:
            b["td"] = (r.get("td") or 0) + (c.get("td") or 0)
        out[pid] = {k: v for k, v in b.items() if v is not None}
    return out


def unnamed_samples(summary, k=3):
    """A few run / pass play texts no player name was found in."""
    names = nq.Names(nq.roster(summary))
    out = []
    for pl in nq._plays(summary):
        t = (((pl.get("type") or {}).get("text")) or "").lower()
        if ("pass" in t or t.startswith("rush")) and not names.find(pl.get("text") or ""):
            out.append(pl.get("text"))
        if len(out) >= k:
            break
    return out


def main():
    prior = json.loads(PRIOR.read_text())
    finals = prior.get("finals") or []
    games, chk, types, samples, qb_miss = {}, Counter(), Counter(), [], []
    plays = named = no_rcv = 0
    no_rcv_texts = []
    for k, f in enumerate(finals):
        eid = str(f.get("event_id") or "")
        if not eid:
            continue
        try:
            summ = ef.fetch_summary("nfl", eid)
        except Exception as exc:  # noqa: BLE001
            print(f"  summary {eid} failed: {exc}")
            continue
        rec = nq.parse(summ)
        box = box_of(summ, eid)
        chk.update(nq.check(rec, box))
        for pid, b in box.items():          # which quarterbacks miss, and by how much
            if b.get("pass_att") and len(qb_miss) < 8:
                got = sum(((rec["players"].get(pid) or {}).get("pass_yds")) or [0])
                if abs(got - (b.get("pass_yds") or 0)) > 1:
                    qb_miss.append((eid, pid, b.get("pass_yds"), got, b.get("pass_att"), sum(
                        ((rec["players"].get(pid) or {}).get("pass_att")) or [0])))
        types.update((((p.get("type") or {}).get("text")) or "?") for p in nq._plays(summ))
        plays += rec["plays"]
        named += rec["named"]
        no_rcv += rec.get("no_receiver", 0)
        if len(no_rcv_texts) < 6:
            no_rcv_texts += rec.get("no_receiver_texts", [])[:2]
        if len(samples) < 6:
            samples += unnamed_samples(summ, 2)
        games[eid] = {"date": f.get("date"), "week": f.get("week"),
                      "home": str(f.get("home_id")), "away": str(f.get("away_id")),
                      "lines": rec["lines"], "players": rec["players"]}
        if k and k % 50 == 0:
            print(f"  ... {k} games")
        time.sleep(0.06)
    n = len(games) or 1
    has_lines = sum(1 for g in games.values() if len(g["lines"]) == 2)
    print(f"  [verify] NFL quarters: {len(games)} of {len(finals)} finals read; quarter lines "
          f"{has_lines}; run / pass plays {plays}, a player named in {named} "
          f"({100 * named / max(1, plays):.1f}%)")
    print("  [verify] quarters that add up to his box score: " + ", ".join(
        f"{s} {100 * chk.get(s, 0) / max(1, chk.get(f'{s}_n', 0)):.1f}% (n={chk.get(f'{s}_n', 0)})"
        for s in nq.STATS))
    print(f"  [verify] play types seen: {dict(types.most_common(16))}")
    print(f"  [verify] run / pass texts with no name found (first few): {samples[:6]}")
    print(f"  [verify] completions whose catcher was not found: {no_rcv} (the passer still "
          f"credited); first few: {no_rcv_texts[:6]}")
    print(f"  [verify] quarterbacks whose quarters miss the box (event, id, box yds, quarters "
          f"yds, box att, quarters att): {qb_miss}")
    ry = chk.get("rush_yds", 0) / max(1, chk.get("rush_yds_n", 0))
    cy = chk.get("rec_yds", 0) / max(1, chk.get("rec_yds_n", 0))
    if has_lines < MIN_SHARE * n or ry < MIN_SHARE or cy < MIN_SHARE:
        print(f"Refusing to write: quarter lines in fewer than {int(100 * MIN_SHARE)}% of games, "
              f"or rushing / receiving yards adding up for fewer than {int(100 * MIN_SHARE)}% of "
              f"players — the play text shape may have changed. Send the log.")
        return 1
    OUT.write_text(json.dumps({"season": prior.get("season"), "games": games},
                              separators=(",", ":")))
    print(f"  wrote {OUT} ({OUT.stat().st_size / 1024:.0f} KB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
