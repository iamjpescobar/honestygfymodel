"""
NBA play-by-play (10-21) — what a box score can't say: who won the tip,
who scored first, and every quarter's score, from ESPN's game summary.

parse(summary) -> {
  "lines":  {team_id: [q1, q2, q3, q4, (ot...)]}   team points per period
  "tip":    {"jumpers": [pid, pid], "team": team_id | None}
            the opening jump ball and the team with the first possession
            (the team of the first play after it that names a team)
  "first_fg":    {"pid", "team", "value", "period", "clock"} | None
            the first MADE FIELD GOAL (the usual "first basket" market —
            most books settle on the first field goal, not a free throw)
  "first_score": the same for the first point of any kind (FTs count)
  "starters": {team_id: [pid, ...]}                the five on the floor
  "qpts":     {pid: [q1, q2, q3, q4]}              each player's points
                                                    per quarter (OT left out)
}
Missing is never zero: a shape this parser can't read leaves the field
None / empty, and the backfill's [verify] lines count how often.

ESPN's NBA summary: header.competitions[0].competitors[].linescores[]
({displayValue}); plays[] ({type: {text}, text, period: {number}, clock:
{displayValue}, scoringPlay, scoreValue, team: {id}, participants:
[{athlete: {id}}]}); boxscore starters via engines/nba_box.

Pure — no requests.
"""
from engines import nba_box as nb


def _num(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def lines(summary):
    comp = (((summary or {}).get("header") or {}).get("competitions") or [{}])[0] or {}
    out = {}
    for c in comp.get("competitors") or []:
        tid = str((c.get("team") or {}).get("id") or c.get("id") or "")
        ls = [_num(x.get("displayValue") if isinstance(x, dict) else x)
              for x in c.get("linescores") or []]
        if tid and ls and None not in ls:
            out[tid] = ls
    return out


def _pid(play, k=0):
    parts = play.get("participants") or []
    if len(parts) > k:
        a = (parts[k] or {}).get("athlete") or {}
        return str(a.get("id")) if a.get("id") is not None else None
    return None


def _team(play):
    t = play.get("team") or {}
    return str(t.get("id")) if t.get("id") is not None else None


def _period(play):
    p = play.get("period")
    return (p or {}).get("number") if isinstance(p, dict) else p


def _is_ft(play):
    txt = (((play.get("type") or {}).get("text")) or "") + " " + (play.get("text") or "")
    return "free throw" in txt.lower()


def _is_jump(play):
    txt = (((play.get("type") or {}).get("text")) or "") + " " + (play.get("text") or "")
    return "jump" in txt.lower() and "ball" in txt.lower()


def parse(summary):
    plays = [p for p in (summary or {}).get("plays") or [] if isinstance(p, dict)]
    out = {"lines": lines(summary), "tip": None, "first_fg": None, "first_score": None,
           "starters": {}, "qpts": {}}
    # the tip: the first jump ball, and the first team named after it
    for i, p in enumerate(plays[:12]):
        if _is_jump(p):
            jumpers = [x for x in (_pid(p, 0), _pid(p, 1)) if x]
            team = next((_team(q) for q in plays[i + 1:i + 8] if _team(q)
                         and not _is_jump(q)), None)
            out["tip"] = {"jumpers": jumpers, "team": team}
            break
    for p in plays:
        if not p.get("scoringPlay"):
            continue
        v = _num(p.get("scoreValue")) or 0
        rec = {"pid": _pid(p), "team": _team(p), "value": v, "period": _period(p),
               "clock": (p.get("clock") or {}).get("displayValue")
               if isinstance(p.get("clock"), dict) else p.get("clock")}
        if out["first_score"] is None:
            out["first_score"] = rec
        if out["first_fg"] is None and not _is_ft(p) and v >= 2:
            out["first_fg"] = rec
        per = _period(p)
        pid = rec["pid"]
        if pid and isinstance(per, int) and 1 <= per <= 4 and v:
            out["qpts"].setdefault(pid, [0, 0, 0, 0])[per - 1] += int(v)
    for pid, ln in (nb.parse(summary) or {}).items():
        if ln.get("starter"):
            out["starters"].setdefault(str(ln.get("team_id")), []).append(str(pid))
    return out


def check(rec, hs=None, as_=None, home=None, away=None):
    """Self-check of one parsed game: quarter lines add up to the final;
    each team's players' quarter points add up to its quarter line."""
    bad = []
    L = rec.get("lines") or {}
    for tid, final in ((home, hs), (away, as_)):
        if tid and final is not None and tid in L and abs(sum(L[tid]) - final) > 0.5:
            bad.append(f"line {tid} {sum(L[tid])} != {final}")
    return bad
