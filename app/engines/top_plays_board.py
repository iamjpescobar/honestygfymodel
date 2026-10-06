"""
TOP PLAYS — the most likely outcomes on tonight's slate that have PROVEN
themselves, each shown with the record that proves it, and every one
written down before the game and graded after it.

WHAT GETS IN
------------
A player prop is a candidate only on a line whose market BEAT the
player's own hit rate on games it had not seen (the nightly's walk-
forward verdict, "beats"). Its probability is then CALIBRATED: mapped
through that market's own walk-forward calibration curve — when the
model said 80-89% on Hits O0.5, how often did it actually happen — made
monotone by pooling adjacent violators (no knobs), the measured gap
carried past its ends, so the number shown
is what that kind of call has DELIVERED, not what the model claimed.

One play per player (Hits O0.5 and TB O0.5 are the same event; a
player's three lines are one opinion). Ranked most likely first. How
many are shown (SHOW_N) is a presentation choice, not a number about the
world (rule 1 governs those).

A prop has no posted price in the feeds, so each play carries the most
you should pay: its fair price at the calibrated chance. Better than
that at your book is value; worse is not, however likely it is.

THE RECORD
----------
Every play shown is logged before first pitch / puck drop (first writer
wins per game, player and market) to data/top_plays/{mlb,nhl}.json and
graded from the box score: hit, miss, or void (did not play / did not
start). The page leads with it: plays, hits, the hit rate DELIVERED next
to the average chance PROMISED. That pair is the honest answer to "can
my friends trust this page" — not a claim, a record.

One owner per file: slate-picks logs and grades MLB, the nightly logs
and grades NHL.

Pure — no streamlit, no requests.
"""
import json
from datetime import datetime, timezone
from pathlib import Path

from engines import model_math as mm

ROOT = Path(__file__).resolve().parents[2]
DIR = ROOT / "data" / "top_plays"
SPORTS = ("mlb", "nhl")
SHOW_N = 10
# Markets that are the SAME event as another one listed (TB O0.5 is a
# hit). Kept on the boards, never doubled in Top Plays.
SAME_EVENT = {"tb1": "h1"}


# ----------------------------------------------------------------------
# Calibration
# ----------------------------------------------------------------------
def _pav(points):
    """Pool-adjacent-violators on [(predicted, actual, n)] sorted by
    predicted -> monotone [(predicted, actual, n)]."""
    blocks = [[p, a * n, n] for p, a, n in points if n]
    i = 0
    while i < len(blocks) - 1:
        a0, a1 = blocks[i][1] / blocks[i][2], blocks[i + 1][1] / blocks[i + 1][2]
        if a0 > a1:
            p = (blocks[i][0] * blocks[i][2] + blocks[i + 1][0] * blocks[i + 1][2]) / (
                blocks[i][2] + blocks[i + 1][2])
            blocks[i] = [p, blocks[i][1] + blocks[i + 1][1], blocks[i][2] + blocks[i + 1][2]]
            del blocks[i + 1]
            i = max(i - 1, 0)
        else:
            i += 1
    return [(p, s / n, n) for p, s, n in blocks]


def calibrate(p, bins):
    """The probability a call of `p` has DELIVERED, from a market's
    walk-forward calibration bins ([{band, n, predicted, actual}]):
    monotone (PAV), then linear between bin centres.

    PAST THE MEASURED RANGE (above the highest bin's average call, below
    the lowest's) the gap measured at that end is carried forward instead
    of holding flat. Until 10-06 it held flat, which made every call above
    the top bin identical — four NHL players at raw 84-89% all printed
    84.4%, so the top of Top Plays was a tie. Measured on last season's
    NHL props (calibrate on the first half of the test window, score the
    second half, ends only): carrying the gap beat flat on 6 of 8 markets
    (z 2.1-8.4), one thin, one worse within noise. Clipped to (0, 1).
    No bins -> None (an uncalibrated number is not shown as calibrated)."""
    if p is None or not bins:
        return None
    raw = sorted((b["predicted"], b["actual"], b["n"]) for b in bins if b.get("n"))
    pts = _pav(raw)
    if not pts:
        return None
    lo_x, hi_x = raw[0][0], raw[-1][0]
    if p > hi_x:
        return min(max(p + (pts[-1][1] - pts[-1][0]), 0.0005), 0.9995)
    if p < lo_x:
        return min(max(p + (pts[0][1] - pts[0][0]), 0.0005), 0.9995)
    if p <= pts[0][0]:
        return pts[0][1]
    if p >= pts[-1][0]:
        return pts[-1][1]
    for (x0, y0, _n0), (x1, y1, _n1) in zip(pts, pts[1:]):
        if x0 <= p <= x1:
            return y0 + (y1 - y0) * (p - x0) / (x1 - x0) if x1 > x0 else y0
    return pts[-1][1]


def record_at(p, bins):
    """(band, n, actual) of the calibration bin `p` falls in, or None."""
    for b in bins or []:
        lo, hi = b["band"].rstrip("%").split("-")
        if int(lo) / 100.0 <= p < (int(hi) + 1) / 100.0:
            return b["band"], b["n"], b["actual"]
    return None


# ----------------------------------------------------------------------
# Selecting tonight's plays
# ----------------------------------------------------------------------
def select(cands, validation, n=SHOW_N):
    """cands: [{"sport","game_id","game","start","player_id","player",
    "team","market","label","p"}] (p = the model's raw probability).
    validation: {market: {"verdict": {...}, "calibration": [...]}}.
    Returns the plays, most likely first, each with p_cal, its record
    and the most to pay."""
    best = {}
    for c in cands:
        if c["market"] in SAME_EVENT:
            continue
        v = (validation or {}).get(c["market"]) or {}
        if ((v.get("verdict") or {}).get("verdict")) != "beats":
            continue
        pc = calibrate(c["p"], v.get("calibration"))
        if pc is None or not (0.0 < pc < 1.0):
            continue
        rec = record_at(c["p"], v.get("calibration"))
        play = dict(c, p_cal=round(pc, 4), fair=mm.fair_american(pc),
                    record=({"band": rec[0], "n": rec[1], "hit": rec[2]} if rec else None))
        key = (c["sport"], str(c["game_id"]), str(c["player_id"]))
        if key not in best or play["p_cal"] > best[key]["p_cal"]:
            best[key] = play
    return sorted(best.values(), key=lambda x: -x["p_cal"])[:n]


# ----------------------------------------------------------------------
# The record
# ----------------------------------------------------------------------
def _path(sport, root=None):
    return Path(root or DIR) / f"{sport}.json"


def load(sport, root=None):
    p = _path(sport, root)
    if not p.exists():
        return {"plays": []}
    try:
        return json.loads(p.read_text()) or {"plays": []}
    except Exception:
        return {"plays": []}


def save(sport, rec, root=None):
    p = _path(sport, root)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(rec, indent=1, sort_keys=True))


def log_plays(sport, plays, now=None, root=None):
    """Append plays not yet logged and not yet started. Returns count."""
    now = now or datetime.now(timezone.utc)
    rec = load(sport, root)
    have = {(p["game_id"], p["player_id"], p["market"]) for p in rec["plays"]}
    new = 0
    for p in plays:
        try:
            start = datetime.fromisoformat(str(p["start"]).replace("Z", "+00:00"))
        except (KeyError, ValueError):
            continue
        if start.tzinfo is None or start <= now:
            continue
        key = (str(p["game_id"]), str(p["player_id"]), p["market"])
        if key in have:
            continue
        have.add(key)
        rec["plays"].append({
            "game_id": str(p["game_id"]), "player_id": str(p["player_id"]),
            "date": p.get("date"), "start": p["start"], "game": p.get("game"),
            "player": p.get("player"), "team": p.get("team"), "market": p["market"],
            "label": p.get("label"), "stat": p.get("stat"), "at_least": p.get("at_least"),
            "p": round(p["p"], 4), "p_cal": p["p_cal"], "fair": p.get("fair"),
            # WHY and the MATCHUP as they stood when the play was logged
            # (10-06) — the page shows them; nothing grades on them.
            "why": p.get("why"), "matchup": p.get("matchup"),
            "matchup_tier": p.get("matchup_tier"),
            "logged_at": now.isoformat(timespec="seconds"), "result": None})
        new += 1
    if new:
        save(sport, rec, root)
    return new


def grade(sport, lines_for, root=None, today=None, void_after_days=3):
    """Grade pending plays. lines_for(game_id) -> None (not final / not
    fetchable: left pending) or {"final": True, "players": {player_id:
    {stat: value}}}. A player absent from a final box score did not play
    -> void. Returns (graded, voided)."""
    from datetime import date as _date
    rec = load(sport, root)
    today = today or datetime.now(timezone.utc).date()
    cache, graded, voided = {}, 0, 0
    for p in rec["plays"]:
        if p.get("result"):
            continue
        gid = p["game_id"]
        if gid not in cache:
            try:
                cache[gid] = lines_for(gid)
            except Exception:
                cache[gid] = None
        box = cache[gid]
        if not box or not box.get("final"):
            try:
                if (today - _date.fromisoformat(p["date"])).days > void_after_days:
                    p["result"] = "void"
                    voided += 1
            except (TypeError, ValueError):
                pass
            continue
        line = (box.get("players") or {}).get(str(p["player_id"]))
        val = None if line is None else line.get(p["stat"])
        if val is None:
            p["result"] = "void"
            voided += 1
            continue
        p["actual"] = val
        p["result"] = "hit" if val >= p["at_least"] else "miss"
        graded += 1
    if graded or voided:
        save(sport, rec, root)
    return graded, voided


def summary(plays):
    """{"n","hits","hit_rate","promised"} over graded plays, plus by
    band of promised chance — DELIVERED next to PROMISED."""
    g = [p for p in plays if p.get("result") in ("hit", "miss")]

    def agg(rows):
        n = len(rows)
        h = sum(1 for r in rows if r["result"] == "hit")
        return {"n": n, "hits": h,
                "hit_rate": round(h / n, 4) if n else None,
                "promised": round(sum(r["p_cal"] for r in rows) / n, 4) if n else None}
    out = {"all": agg(g), "pending": sum(1 for p in plays if not p.get("result")),
           "by_band": []}
    for lo, hi in ((0.5, 0.6), (0.6, 0.7), (0.7, 0.8), (0.8, 0.9), (0.9, 1.01)):
        rows = [r for r in g if lo <= r["p_cal"] < hi]
        if rows:
            out["by_band"].append(dict(agg(rows), band=f"{int(lo * 100)}-{min(int(hi * 100), 100) - 1}%"))
    return out
