"""
NHL periods (10-22) — what a box score can't say: each period's score,
shots and every skater's goals, assists and shots on goal BY PERIOD, from
ESPN's game summary (the play-by-play).

parse(summary, goalie_ids) -> {
  "lines":   {team_id: [p1, p2, p3, (ot...)]}   team goals per period
  "sog":     {team_id: [p1, p2, p3]}            team shots on goal (plays)
  "players": {pid: [[g, a, sog] x 3]}           regulation periods only
  "first_goal": {"pid", "team", "period"} | None
}
A shot on goal is a "Shot" play (saved) or a "Goal"; the shooter is the
play's first participant. A goal's assisters are the next participants
that are NOT a goalie (ESPN lists the goalie on scoring plays too).
Missing is never zero: a shape this parser can't read leaves the field
empty, and the backfill's [verify] lines count, game by game, whether
each skater's periods add up to his box score.

ESPN's NHL summary: header.competitions[0].competitors[].linescores[];
plays[] ({type: {text}, text, period: {number}, team: {id},
participants: [{athlete: {id}}], scoringPlay}).

Pure — no requests.
"""
PERIODS = 3


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


def _pids(play):
    out = []
    for p in play.get("participants") or []:
        a = (p or {}).get("athlete") or {}
        if a.get("id") is not None:
            out.append(str(a["id"]))
    return out


def _period(play):
    p = play.get("period")
    return (p or {}).get("number") if isinstance(p, dict) else p


def _kind(play):
    t = (((play.get("type") or {}).get("text")) or "").strip().lower()
    if t == "goal" or (play.get("scoringPlay") and "shootout" not in t):
        return "goal"
    if t in ("shot", "shot on goal"):
        return "shot"
    return None


def parse(summary, goalie_ids=()):
    gk = {str(x) for x in goalie_ids or ()}
    plays = [p for p in (summary or {}).get("plays") or [] if isinstance(p, dict)]
    out = {"lines": lines(summary), "sog": {}, "players": {}, "first_goal": None}

    def slot(pid):
        return out["players"].setdefault(pid, [[0, 0, 0] for _ in range(PERIODS)])
    for pl in plays:
        k = _kind(pl)
        per = _period(pl)
        if k is None or not isinstance(per, int) or per < 1:
            continue
        team = str((pl.get("team") or {}).get("id") or "")
        ids = [x for x in _pids(pl) if x not in gk]
        if per <= PERIODS and team:
            s = out["sog"].setdefault(team, [0] * PERIODS)
            s[per - 1] += 1
        if not ids:
            continue
        if k == "goal" and out["first_goal"] is None and per <= PERIODS + 1:
            out["first_goal"] = {"pid": ids[0], "team": team or None, "period": per}
        if per > PERIODS:
            continue
        slot(ids[0])[per - 1][2] += 1                 # every goal is a shot on goal
        if k == "goal":
            slot(ids[0])[per - 1][0] += 1
            for a in ids[1:3]:
                slot(a)[per - 1][1] += 1
    return out


def check(rec, box):
    """{"players", "goals_ok", "assists_ok", "sog_ok"}: how many skaters'
    regulation periods add up to the box score's g / a / sog (box: {pid:
    {"g", "a", "sog"}}). OT goals make a few honest misses."""
    n = ok_g = ok_a = ok_s = 0
    for pid, b in (box or {}).items():
        per = (rec.get("players") or {}).get(pid) or [[0, 0, 0]] * PERIODS
        n += 1
        ok_g += int(sum(x[0] for x in per) == int(b.get("g") or 0))
        ok_a += int(sum(x[1] for x in per) == int(b.get("a") or 0))
        if b.get("sog") is not None:
            ok_s += int(sum(x[2] for x in per) == int(b.get("sog") or 0))
    return {"players": n, "goals_ok": ok_g, "assists_ok": ok_a, "sog_ok": ok_s}
