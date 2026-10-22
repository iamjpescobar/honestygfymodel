"""
NFL quarters (10-22) — each quarter's score, and every player's passing,
rushing and receiving line BY QUARTER, from ESPN's game summary (the
drives' plays). What the quarter / half lines and the 1st-quarter /
1st-half player props are fitted and tested on.

parse(summary) -> {
  "lines":   {team_id: [q1, q2, q3, q4, (ot)]}   team points per quarter
  "players": {pid: {stat: [q1, q2, q3, q4, ot]}}  stat in STATS
  "plays":   n plays read, "named": n of them a player was found in
}
ESPN's NFL plays name players only in the TEXT ("(Shotgun) J.Goff pass
short right to A.St. Brown to DET 45 for 12 yards (T.Smith)."), so each
team's box-score athletes are turned into the forms the text uses (first
initial(s) + "." + last name, suffix dropped too) and found in it:
  pass  -> passer = the first name in the text; att +1; a catch (not
           "incomplete" / "intercepted") -> cmp +1, his yards = the gain the
           text writes (play_yards); the receiver = the first name after " to "
           (targets +1 on every throw to him, a catch adds rec + yards)
  rush  -> the first name; carries +1, yards = the text's gain
  a touchdown on the play -> passer pass_td, receiver / rusher td
Skipped: "No Play" (penalty), two-point tries, sacks (not passing yards
in the box), kicks and returns.
Missing is never zero: the backfill checks, player by player, that his
quarters add up to his box score, and refuses to write when they don't.

Pure — no requests.
"""
import re

STATS = ("pass_yds", "pass_att", "pass_cmp", "pass_td", "rush_yds", "carries", "rec_yds",
         "rec", "targets", "td")
SLOTS = 5                       # Q1-Q4, then all overtime
SUFFIX = re.compile(r"\s+(jr\.?|sr\.?|ii|iii|iv|v)$", re.I)


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


def roster(summary):
    """{pid: (team_id, name)} for every athlete in the box score's groups."""
    out = {}
    for b in (((summary or {}).get("boxscore") or {}).get("players") or []):
        tid = str((b.get("team") or {}).get("id") or "")
        for grp in b.get("statistics") or []:
            for ent in grp.get("athletes") or []:
                a = ent.get("athlete") or {}
                if a.get("id") is not None and a.get("displayName"):
                    out[str(a["id"])] = (tid, a["displayName"])
    return out


def forms(name):
    """The ways play text writes a player: 'Amon-Ra St. Brown' ->
    'A.St. Brown', 'Am.St. Brown', ...; suffixes dropped too; and his full
    name (scoring plays: 'Deebo Samuel 10 Yd pass from Jayden Daniels')."""
    parts = str(name or "").strip().split()
    if len(parts) < 2:
        return set()
    first, last = parts[0], " ".join(parts[1:])
    lasts = {last, SUFFIX.sub("", last)}
    out = {f"{first} {ln}" for ln in lasts}
    for ln in lasts:
        for k in range(1, min(len(first), 4) + 1):
            out.add(f"{first[:k]}.{ln}")
            out.add(f"{first[:k]}. {ln}")
    return out


class Names:
    """Finds a game's athletes in play text."""

    def __init__(self, ros):
        self.by_form = {}
        self.team = {pid: str(t) for pid, (t, _nm) in (ros or {}).items()}
        self.teams = set(self.team.values())
        self.whole = {}               # form -> ids whose WHOLE first name it spells
        for pid, (_t, nm) in (ros or {}).items():
            for f in forms(nm):
                self.by_form.setdefault(f, set()).add(pid)
            parts = str(nm or "").split()
            if len(parts) >= 2:
                for f in forms(nm):
                    if f.split(".")[0] == parts[0] or f.startswith(parts[0] + " "):
                        self.whole.setdefault(f, set()).add(pid)
        # longest forms first: 'Am.St. Brown' before 'A.St. Brown'
        keys = sorted(self.by_form, key=len, reverse=True)
        self.rx = re.compile("|".join(r"(?<![A-Za-z.])" + re.escape(k) + r"(?![a-z])"
                                      for k in keys)) if keys else None

    def find(self, text, team=None):
        """[(position, pid)] of the unambiguous names in the text. With the
        OFFENSE's team id, only its players count: 'C.Williams' is the
        Bears' quarterback, not the defender of the same initials, and a
        tackler in parentheses is never taken for the receiver."""
        if not self.rx:
            return []
        team = str(team) if team is not None and str(team) in self.teams else None
        out = []
        for m in self.rx.finditer(text or ""):
            ids = self.by_form.get(m.group(0)) or set()
            if team:
                ids = {i for i in ids if self.team.get(i) == team}
            if len(ids) > 1:
                # 'Ty.Johnson' is Ty Johnson before Tyler Johnson
                w = ids & self.whole.get(m.group(0), set())
                ids = w if len(w) == 1 else ids
            if len(ids) == 1:
                out.append((m.start(), next(iter(ids))))
        return out


def _plays(summary):
    return [p for p, _t in _plays_with_offense(summary)]


def _plays_with_offense(summary):
    """[(play, offense team id or None)] — the drive's team has the ball."""
    d = (summary or {}).get("drives") or {}
    out = []
    for dr in (d.get("previous") or []) + ([d["current"]] if isinstance(d.get("current"),
                                                                       dict) else []):
        tm = (dr.get("team") or {}).get("id") if isinstance(dr.get("team"), dict) else None
        out += [(p, tm) for p in dr.get("plays") or [] if isinstance(p, dict)]
    return out


YARDS = re.compile(r"for (-?\d+) yards?|for no gain|(-?\d+)\s+(?:yd|yard)s?\s+(?:pass|run|rush)",
                   re.I)


def play_yards(play, text):
    """The play's own gain as the text writes it ('for 12 yards', 'for no
    gain', '22 Yd pass from'); statYardage only when the text has none —
    statYardage can carry a penalty's yards enforced after the play."""
    m = YARDS.search(text or "")
    if m:
        g = m.group(1) or m.group(2)
        return float(g) if g is not None else 0.0
    return _num(play.get("statYardage")) or 0.0


PAT = re.compile(r"\([^()]*(two-point|two point|kick|conversion)[^()]*\)", re.I)
SCORING = re.compile(r"\d+\s+yd\s+(pass from|run)\b", re.I)


def _period(play):
    p = play.get("period")
    return (p or {}).get("number") if isinstance(p, dict) else p


def parse(summary):
    names = Names(roster(summary))
    out = {"lines": lines(summary), "players": {}, "plays": 0, "named": 0, "no_receiver": 0,
           "no_receiver_texts": []}

    def add(pid, stat, q, v):
        rec = out["players"].setdefault(pid, {s: [0] * SLOTS for s in STATS})
        rec[stat][q] += v
    seen = set()
    for pl, off in _plays_with_offense(summary):
        pid_ = pl.get("id")
        if pid_ is not None:
            if pid_ in seen:
                continue
            seen.add(pid_)
        # the try after a touchdown, written in parentheses on the scoring
        # play, is not the play (the touchdown itself still counts)
        txt = PAT.sub("", pl.get("text") or "")
        low = txt.lower()
        typ = (((pl.get("type") or {}).get("text")) or "").lower()
        per = _period(pl)
        if not isinstance(per, int) or per < 1:
            continue
        q = min(per, SLOTS) - 1
        if "no play" in low or "two-point" in low or "two point" in low:
            continue
        is_pass = (" pass " in f" {low} " or "pass" in typ) and "sack" not in low \
            and "sack" not in typ
        is_rush = (typ.startswith("rush") or "rushing" in typ) and not is_pass
        if not (is_pass or is_rush):
            continue
        out["plays"] += 1
        found = names.find(txt, off)
        if not found:
            continue
        out["named"] += 1
        yds = play_yards(pl, txt)
        td = "touchdown" in typ or "touchdown" in low
        sc = SCORING.search(txt)
        if sc and is_pass and "from" in sc.group(1).lower():
            # 'Deebo Samuel 10 Yd pass from Jayden Daniels': receiver first
            at = sc.end()
            passer = next((p for pos, p in found if pos >= at), None)
            rcv = next((p for pos, p in found if pos < sc.start()), None)
            if passer and rcv:
                for who, st in ((passer, "pass_att"), (passer, "pass_cmp"), (rcv, "targets"),
                                (rcv, "rec")):
                    add(who, st, q, 1)
                add(passer, "pass_yds", q, yds)
                add(rcv, "rec_yds", q, yds)
                add(passer, "pass_td", q, 1)
                add(rcv, "td", q, 1)
            continue
        if is_rush:
            r = found[0][1]
            add(r, "carries", q, 1)
            add(r, "rush_yds", q, yds)
            if td:
                add(r, "td", q, 1)
            continue
        passer = found[0][1]
        at = low.find(" to ", low.find("pass"))
        rcv = next((p for pos, p in found if at >= 0 and pos > at and p != passer), None)
        add(passer, "pass_att", q, 1)
        caught = "incomplete" not in low and "intercepted" not in low
        if rcv:
            add(rcv, "targets", q, 1)
        if caught:
            # the passer's completion counts even when the catcher's name
            # is not found (his box does); the catch only when it is
            add(passer, "pass_cmp", q, 1)
            add(passer, "pass_yds", q, yds)
            if td:
                add(passer, "pass_td", q, 1)
            if rcv:
                add(rcv, "rec", q, 1)
                add(rcv, "rec_yds", q, yds)
                if td:
                    add(rcv, "td", q, 1)
            else:
                out["no_receiver"] += 1
                if len(out["no_receiver_texts"]) < 3:
                    out["no_receiver_texts"].append(txt[:160])
    return out


def check(rec, box):
    """{"players", stat: n that add up} — his quarters against his box
    line (box: {pid: {stat: total}}); yards within 1 for rounding."""
    out = {"players": 0}
    for pid, b in (box or {}).items():
        per = (rec.get("players") or {}).get(pid) or {}
        out["players"] += 1
        for st, v in b.items():
            if v is None:
                continue
            got = sum((per.get(st) or [0])) if per else 0
            tol = 1.0 if st.endswith("yds") else 0.0
            out[st] = out.get(st, 0) + int(abs(got - v) <= tol)
            out[f"{st}_n"] = out.get(f"{st}_n", 0) + 1
    return out
