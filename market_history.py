"""
The market's recorded line for every past game the models are fitted on
— what engines/market_blend measures the models AGAINST.

WHY THIS EXISTS (10-04)
-----------------------
A model's weight against the market can only be measured on games where
both exist: the model's walk-forward prediction and the line the market
posted. The models' history files hold scores only. This script walks
ESPN's scoreboards for the seasons the models fit on and records each
final's line:

    nfl   2025 regular season   -> data/market_lines/nfl_2025.json
    nhl   2025-26 regular season -> data/market_lines/nhl_2025-26.json
    mlb   2026 regular season   -> data/market_lines/mlb_2026.json

The line is read off the scoreboard event (espn_feed.odds_of — every
published shape) and, when the scoreboard carries none for a final, off
that game's summary `pickcenter`, the same block nfl_precompute already
reads pre-game. What ESPN recorded for a finished game is whatever its
odds provider left on the event; the file says "recorded line", never
"closing line", because that is all it can promise (rule 9).

KEYS MATCH THE MODELS' OWN
--------------------------
    nfl   kick date (ET) | home ESPN id | away ESPN id   (nfl_prior_season)
    nhl   scoreboard date | home ESPN id | away ESPN id  (nhl_prior_season)
    mlb   scoreboard date | home abbr  | away abbr       (mlb_run_rates.canonical
                                                         on both feeds' names)

A doubleheader puts two MLB games under one key; both are DROPPED rather
than one guessed (rule 9), and the count is printed.

THIS SEASON'S NFL AND NHL LINES are not here: the nightly already reads
every current final (and its summary) and carries the line on the row,
so they never need a second fetch. One owner per file: only this script
(workflow: market-history, manual) writes data/market_lines/.

Prints [verify] lines; writes nothing for a sport whose walk produced no
finals at all.
"""
import json
import sys
import time
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "app"))
from engines import espn_feed as ef        # noqa: E402
from engines import market_blend as mb     # noqa: E402

OUT_DIR = ROOT / "data" / "market_lines"

SEASONS = {
    # sport: (file stem, first date, last date)
    "nfl": ("nfl_2025", date(2025, 9, 4), date(2026, 1, 4)),
    "nhl": ("nhl_2025-26", date(2025, 10, 7), date(2026, 4, 16)),
    "mlb": ("mlb_2026", date(2026, 3, 25), date(2026, 9, 28)),
}


def _has_line(o):
    return bool(o) and (o.get("home_ml") is not None or o.get("total") is not None
                        or o.get("spread") is not None)


def event_record(ev, query_day, league, summary_fn=None):
    """{"key_date","event_id","home","away","home_id","away_id",
    "home_abbr","away_abbr","hs","as","odds","source"} for a FINAL, else
    None. summary_fn(event_id) is called only when the scoreboard event
    carries no line."""
    comp, away, home = ef.event_sides(ev)
    if comp is None:
        return None
    status, completed, _detail = ef.status_of(ev)
    if status != "final" and not completed:
        return None
    hs, as_ = ef.num(home.get("score")), ef.num(away.get("score"))
    if hs is None or as_ is None:
        return None
    ht, at = home.get("team") or {}, away.get("team") or {}
    rec = {"event_id": str(ev.get("id") or ""),
           "home": ht.get("displayName"), "away": at.get("displayName"),
           "home_id": str(ht.get("id") or ""), "away_id": str(at.get("id") or ""),
           "home_abbr": ht.get("abbreviation") or "", "away_abbr": at.get("abbreviation") or "",
           "hs": int(hs), "as": int(as_)}
    kick = ef.to_et(comp.get("date") or ev.get("date"))
    # NFL keys on the KICK date (that is what nfl_prior_season stores);
    # NHL and MLB on the day the scoreboard was asked for (what their
    # history files store).
    rec["key_date"] = (kick.date().isoformat() if (league == "nfl" and kick)
                       else query_day.isoformat())
    o = ef.odds_of(comp)
    src = "scoreboard"
    if not _has_line(o) and summary_fn and rec["event_id"]:
        try:
            summ = summary_fn(rec["event_id"]) or {}
            pc = summ.get("pickcenter") or []
            if isinstance(pc, list) and pc and isinstance(pc[0], dict):
                o = ef.odds_of({"odds": pc})
                src = "summary"
        except Exception as exc:          # noqa: BLE001 — logged, line left out
            print(f"  summary {rec['event_id']} failed: {exc}")
    if not _has_line(o):
        return dict(rec, odds=None, source=None)
    return dict(rec, odds=o, source=src)


def collect(league, start, end, sb_fn, summary_fn=None, sleep=0.05, key_fn=None):
    """{line_key: {...}} for every final in [start, end] with a line, plus
    a coverage report."""
    seen, lines, dupes = {}, {}, set()
    cov = {"finals": 0, "with_line": 0, "via_summary": 0, "ml": 0, "total": 0,
           "total_priced": 0, "spread": 0, "spread_priced": 0, "doubleheaders_dropped": 0}
    d = start
    while d <= end:
        try:
            sb = sb_fn(d)
        except Exception as exc:          # noqa: BLE001 — logged, day skipped
            print(f"  scoreboard {d} failed: {exc}")
            d += timedelta(days=1)
            continue
        for ev in (sb or {}).get("events") or []:
            eid = str(ev.get("id") or "")
            if eid and eid in seen:
                continue                  # NFL answers a date with its week
            rec = event_record(ev, d, league, summary_fn)
            if not rec:
                continue
            if eid:
                seen[eid] = True
            if league == "nfl" and not (start.isoformat() <= rec["key_date"] <= end.isoformat()):
                continue
            cov["finals"] += 1
            if not rec["odds"]:
                continue
            key = (key_fn or _id_key)(rec)
            if key is None:
                continue
            if key in lines or key in dupes:
                dupes.add(key)
                lines.pop(key, None)
                continue
            lines[key] = {"odds": rec["odds"], "home_abbr": rec["home_abbr"],
                          "away_abbr": rec["away_abbr"], "event_id": rec["event_id"],
                          "hs": rec["hs"], "as": rec["as"], "source": rec["source"]}
        time.sleep(sleep)
        d += timedelta(days=1)
    for v in lines.values():
        o = v["odds"]
        cov["with_line"] += 1
        cov["via_summary"] += v["source"] == "summary"
        cov["ml"] += o.get("home_ml") is not None and o.get("away_ml") is not None
        cov["total"] += o.get("total") is not None
        cov["total_priced"] += o.get("over_price") is not None and o.get("under_price") is not None
        cov["spread"] += o.get("spread") is not None
        cov["spread_priced"] += (o.get("home_spread_price") is not None
                                 and o.get("away_spread_price") is not None)
    cov["doubleheaders_dropped"] = len(dupes)
    return lines, cov


def _id_key(rec):
    if not rec["home_id"] or not rec["away_id"]:
        return None
    return mb.line_key(rec["key_date"], rec["home_id"], rec["away_id"])


def _mlb_key(rec):
    from engines.mlb_run_rates import canonical
    h, a = canonical(rec["home"]), canonical(rec["away"])
    if not h or not a:
        return None
    return mb.line_key(rec["key_date"], h, a)


def run(sport, sb_fn=None, summary_fn=None, out_dir=None, sleep=0.05):
    stem, start, end = SEASONS[sport]
    sb_fn = sb_fn or (lambda d: ef.fetch_scoreboard(sport, d.strftime("%Y%m%d"))[0])
    summary_fn = summary_fn or (lambda eid: ef.fetch_summary(sport, eid))
    key_fn = _mlb_key if sport == "mlb" else _id_key
    lines, cov = collect(sport, start, end, sb_fn, summary_fn, sleep=sleep, key_fn=key_fn)
    print(f"  [verify] {sport.upper()} {stem}: {cov['finals']} finals walked, "
          f"{cov['with_line']} with a recorded line ({cov['via_summary']} from the summary); "
          f"moneyline {cov['ml']}, total {cov['total']} ({cov['total_priced']} priced), "
          f"spread {cov['spread']} ({cov['spread_priced']} priced); "
          f"{cov['doubleheaders_dropped']} doubleheader keys dropped")
    if not cov["finals"]:
        print(f"::warning::{sport.upper()}: no finals walked — nothing written.")
        return None
    out = Path(out_dir or OUT_DIR) / f"{stem}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"sport": sport, "season": stem, "from": start.isoformat(),
                               "to": end.isoformat(), "coverage": cov,
                               "note": "ESPN's recorded line for each final (not "
                                       "guaranteed to be the closing line)",
                               "lines": lines}, separators=(",", ":"), sort_keys=True))
    print(f"  wrote {out} ({len(lines)} games)")
    return lines


def main(argv=None):
    sports = [s for s in (argv if argv is not None else sys.argv[1:]) if s] or list(SEASONS)
    bad = [s for s in sports if s not in SEASONS]
    if bad:
        print(f"unknown sport(s): {bad}; choose from {list(SEASONS)}")
        return 2
    wrote = 0
    for s in sports:
        print(f"{s.upper()}: walking {SEASONS[s][1]} .. {SEASONS[s][2]}")
        if run(s) is not None:
            wrote += 1
    return 0 if wrote else 1


if __name__ == "__main__":
    sys.exit(main())
