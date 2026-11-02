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
  "qstats":   {pid: {"reb"|"ast"|"tpm": [q1, q2, q3, q4, ot]}} (10-29)
            rebounds (a play whose type says rebound, the first participant),
            assists (a made field goal's SECOND participant when the text
            says assist), made threes (a made field goal worth 3)
  "qstats_ok": the stats whose per-player sums equal the box score for
            EVERY player in the game — a stat this parser misread for this
            game's format is left out of every test, never guessed
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


EARLY_SECONDS = 180        # 10-25: "score in the first 3 minutes" (Izzy bets it)
QUARTER_SECONDS = 720


def clock_seconds(clock):
    """Seconds LEFT in the period from ESPN's display clock ("11:26",
    "9:00", "45.2"), or None."""
    if clock is None:
        return None
    c = str(clock).strip()
    try:
        if ":" in c:
            m, sec = c.split(":", 1)
            return int(m) * 60 + float(sec)
        return float(c)
    except ValueError:
        return None


def parse(summary):
    plays = [p for p in (summary or {}).get("plays") or [] if isinstance(p, dict)]
    out = {"lines": lines(summary), "tip": None, "first_fg": None, "first_score": None,
           "starters": {}, "qpts": {}, "early": {}, "early_team": {}, "team_first_fg": {},
           "qstats": {}, "qstats_ok": []}
    # the tip: the first jump ball, and the first team named after it
    for i, p in enumerate(plays[:12]):
        if _is_jump(p):
            jumpers = [x for x in (_pid(p, 0), _pid(p, 1)) if x]
            team = next((_team(q) for q in plays[i + 1:i + 8] if _team(q)
                         and not _is_jump(q)), None)
            out["tip"] = {"jumpers": jumpers, "team": team}
            break
    for p in plays:
        _q_stats(out["qstats"], p)
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
        # 10-25: the first three minutes (period 1, 9:00 or more left) —
        # each player's [points, made field goals] and each team's points;
        # and each TEAM's first field goal (the team first-basket market)
        left = clock_seconds(rec["clock"])
        if per == 1 and left is not None and left >= QUARTER_SECONDS - EARLY_SECONDS and v:
            if pid:
                e = out["early"].setdefault(pid, [0, 0])
                e[0] += int(v)
                e[1] += 0 if _is_ft(p) else 1
            if rec["team"]:
                out["early_team"][rec["team"]] = out["early_team"].get(rec["team"], 0) + int(v)
        if rec["team"] and rec["team"] not in out["team_first_fg"] and not _is_ft(p) and v >= 2:
            out["team_first_fg"][rec["team"]] = rec
        if pid and isinstance(per, int) and 1 <= per <= 4 and v:
            out["qpts"].setdefault(pid, [0, 0, 0, 0])[per - 1] += int(v)
    box = nb.parse(summary) or {}
    for pid, ln in box.items():
        if ln.get("starter"):
            out["starters"].setdefault(str(ln.get("team_id")), []).append(str(pid))
    out["qstats_ok"] = qstats_ok(out["qstats"], box)
    out.update(shots(summary, box))
    out["team_box"] = team_box(box)
    return out


QSTATS = ("reb", "ast", "tpm")


def _q_slot(qstats, pid, stat, per):
    if not pid or not isinstance(per, int) or per < 1:
        return
    q = qstats.setdefault(pid, {}).setdefault(stat, [0, 0, 0, 0, 0])
    q[min(per, 5) - 1] += 1


def _q_stats(qstats, p):
    """Count one play's rebound / assist / made three into qstats."""
    txt = ((((p.get("type") or {}).get("text")) or "") + " " + (p.get("text") or "")).lower()
    per = _period(p)
    if "rebound" in txt and not p.get("scoringPlay"):
        _q_slot(qstats, _pid(p, 0), "reb", per)
        return
    if p.get("scoringPlay") and not _is_ft(p):
        v = _num(p.get("scoreValue")) or 0
        if v >= 3:
            _q_slot(qstats, _pid(p, 0), "tpm", per)
        if v >= 2 and "assist" in txt:
            _q_slot(qstats, _pid(p, 1), "ast", per)


def qstats_ok(qstats, box):
    """The stats whose per-player play-by-play sums (OT included) equal the
    box score for every player who played — [] without a box score."""
    if not box:
        return []
    ok = []
    for st in QSTATS:
        good = True
        for pid, ln in box.items():
            want = ln.get(st)
            if want is None:
                good = False
                break
            got = sum(((qstats.get(str(pid)) or {}).get(st)) or [0])
            if abs(got - float(want)) > 0.5:
                good = False
                break
        if good:
            ok.append(st)
    return ok


def check(rec, hs=None, as_=None, home=None, away=None):
    """Self-check of one parsed game: quarter lines add up to the final;
    each team's players' quarter points add up to its quarter line."""
    bad = []
    L = rec.get("lines") or {}
    for tid, final in ((home, hs), (away, as_)):
        if tid and final is not None and tid in L and abs(sum(L[tid]) - final) > 0.5:
            bad.append(f"line {tid} {sum(L[tid])} != {final}")
    return bad


# ----------------------------------------------------------------------
# 11-02 — the shot profile: where each player's field goals came from
# ----------------------------------------------------------------------
# Zones (NBA.com's): RIM = restricted area (within 4 ft of the basket),
# PAINT = the rest of the lane, MID = every other two, CORNER3 = a three
# below the break (within ~14 ft of the baseline), ABOVE3 = every other
# three. From ESPN's shot coordinates when they check out against the
# distance written in the play ("26-foot three point jumper"); otherwise
# from that distance alone, where a three's side is unknown ("THREE") and
# a two with no distance and no rim word is "TWO" — missing is never a zone.
import re as _re

ZONES = ("rim", "paint", "mid", "corner3", "above3")
UNKNOWN = ("three", "two")
_FT_RE = _re.compile(r"(\d+)-foot")
_BLOCK_RE = _re.compile(r"blocks\s+(.+?)\s*'s\s", _re.I)
_RIM_WORDS = ("layup", "dunk", "tip", "alley oop", "putback", "finger roll")
RIM_FT, PAINT_HALF, PAINT_LEN, CORNER_LEN = 4.0, 8.0, 14.0, 9.0
XY_AGREE_FT = 3.0          # coordinate distance within 3 ft of the written one
XY_MIN_AGREE = 0.70        # share of a game's shots that must agree to use x/y


def _txt(p):
    return ((((p.get("type") or {}).get("text")) or "") + " " + (p.get("text") or "")).lower()


def _is_shot(p):
    if _is_ft(p) or not p.get("participants"):
        return False
    if p.get("shootingPlay") is not None:
        return bool(p.get("shootingPlay"))
    t = _txt(p)
    return ("makes" in t or "misses" in t or "blocks" in t) and "free throw" not in t


def _xy(p):
    c = p.get("coordinate") or {}
    x, y = _num(c.get("x")), _num(c.get("y"))
    if x is None or y is None or not (-5 <= x <= 100 and -5 <= y <= 100):
        return None
    return x, y


def _is_three(p):
    pa = _num(p.get("pointsAttempted"))
    if pa is not None and pa in (2, 3):
        return pa == 3
    t = _txt(p)
    if "three point" in t or "3-pt" in t or "3pt" in t:
        return True
    return p.get("scoringPlay") and (_num(p.get("scoreValue")) or 0) >= 3


def _shooter(p, names):
    """The shooter's id. A blocked shot names the blocker first in some
    feeds ("X blocks Y 's layup"): the shooter is the participant whose
    box-score name is Y."""
    m = _BLOCK_RE.search(p.get("text") or "")
    if m and names:
        want = m.group(1).strip().lower()
        for k in range(len(p.get("participants") or [])):
            pid = _pid(p, k)
            if pid and (names.get(pid) or "").lower() == want:
                return pid
    return _pid(p, 0)


def _calibrate(pts):
    """The basket(s) from where rim shots sit: (lateral axis 0/1, [basket
    positions along the court]) or None when the coordinates do not look
    like a court (no axis whose rim shots sit mid-court at ~25)."""
    if len(pts) < 5:
        return None
    med = lambda v: sorted(v)[len(v) // 2]  # noqa: E731
    for lat in (0, 1):
        ln = 1 - lat
        if abs(med([q[lat] for q in pts]) - 25.0) > 4.0:
            continue
        along = sorted(q[ln] for q in pts)
        if along[-1] - along[0] > 40:            # both ends of the floor
            mid = (along[0] + along[-1]) / 2
            lo = [a for a in along if a < mid]
            hi = [a for a in along if a >= mid]
            return lat, [med(lo), med(hi)]
        return lat, [med(along)]
    return None


def _zone_xy(xy, cal, three):
    lat, baskets = cal
    dx = xy[lat] - 25.0
    dl = min(abs(xy[1 - lat] - b) for b in baskets)
    d = (dx * dx + dl * dl) ** 0.5
    if three:
        return ("corner3" if dl <= CORNER_LEN else "above3"), d
    if d <= RIM_FT:
        return "rim", d
    if abs(dx) <= PAINT_HALF and dl <= PAINT_LEN:
        return "paint", d
    return "mid", d


def _zone_text(t, dist, three):
    if three:
        return "three"
    if (dist is not None and dist <= RIM_FT) or (dist is None and any(w in t for w in _RIM_WORDS)):
        return "rim"
    if dist is None:
        return "two"
    return "paint" if dist <= PAINT_LEN else "mid"


def shots(summary, box=None):
    """{"shots": {pid: {zone: [att, made]}}, "shot_team": {pid: team},
    "shot_src": "xy" | "text" | None, "shots_ok": [pids whose att / made
    equal the box score's FGA / FGM], "teams_shots_ok": [teams whose every
    player checks out], "shot_check": {"n", "xy", "agree", "dist"}}."""
    box = box if box is not None else (nb.parse(summary) or {})
    names = {pid: (ln.get("name") or "") for pid, ln in box.items()}
    raw = []
    for p in (summary or {}).get("plays") or []:
        if not isinstance(p, dict) or not _is_shot(p):
            continue
        pid = _shooter(p, names)
        if not pid:
            continue
        t = _txt(p)
        m = _FT_RE.search(t)
        raw.append((pid, bool(p.get("scoringPlay")), _is_three(p), _xy(p),
                    float(m.group(1)) if m else None, t))
    rim = [r[3] for r in raw if r[3] and not r[2] and ((r[4] is not None and r[4] <= 2)
                                                        or (r[4] is None and any(
                                                            w in r[5] for w in _RIM_WORDS)))]
    cal = _calibrate(rim)
    agree = with_d = 0
    if cal:
        for r in raw:
            if r[3] and r[4] is not None:
                with_d += 1
                agree += abs(_zone_xy(r[3], cal, r[2])[1] - r[4]) <= XY_AGREE_FT
    use_xy = bool(cal) and with_d >= 20 and agree / with_d >= XY_MIN_AGREE
    out = {"shots": {}, "shot_team": {}, "shot_src": None, "shots_ok": [], "teams_shots_ok": [],
           "shot_check": {"n": len(raw), "xy": sum(1 for r in raw if r[3]),
                          "dist": with_d, "agree": agree, "cal": bool(cal)}}
    if not raw:
        return out
    out["shot_src"] = "xy" if use_xy else "text"
    for pid, made, three, xy, dist, t in raw:
        z = _zone_xy(xy, cal, three)[0] if (use_xy and xy) else _zone_text(t, dist, three)
        c = out["shots"].setdefault(pid, {}).setdefault(z, [0, 0])
        c[0] += 1
        c[1] += int(made)
        if pid in box:
            out["shot_team"][pid] = str(box[pid].get("team_id"))
    by_team = {}
    for pid, ln in box.items():
        fga, fgm = ln.get("fga"), ln.get("fgm")
        z = out["shots"].get(pid) or {}
        ok = (fga is not None and fgm is not None
              and abs(sum(v[0] for v in z.values()) - fga) < 0.5
              and abs(sum(v[1] for v in z.values()) - fgm) < 0.5)
        if ok:
            out["shots_ok"].append(pid)
        by_team.setdefault(str(ln.get("team_id")), []).append(ok)
    out["teams_shots_ok"] = sorted(t for t, oks in by_team.items() if oks and all(oks))
    return out


TEAM_BOX = ("pts", "fgm", "fga", "tpm", "tpa", "ftm", "fta", "oreb", "reb", "tov", "min")


def team_box(box):
    """{team: {stat: sum}} from the box score; a stat any player lacks is
    left out for that team (missing is never zero)."""
    out = {}
    for ln in (box or {}).values():
        t = str(ln.get("team_id"))
        d = out.setdefault(t, {})
        for k in TEAM_BOX:
            v = ln.get(k)
            if v is None:
                d[k] = None
            elif d.get(k, 0) is not None:
                d[k] = d.get(k, 0) + v
    return {t: {k: v for k, v in d.items() if v is not None} for t, d in out.items()}
