"""
Who is actually playing (10-14) — one reading of an injury tag for every
sport, so no board can disagree with another about it.

WHY
---
Until today the NFL boards dropped only players tagged exactly "Out": a
receiver on Injured Reserve who had played earlier in the season kept
his row on the TD board and on Long Shots. The NHL had no injury feed at
all — only Player of the Day skipped a skater who had missed his team's
last game; Goal Edge, the model page and Long Shots still listed him.
MLB is not touched: its active-26 roster gate (engines/roster) already
does this properly.

THE TWO RULES
-------------
  is_out(status)  — the player will not play: Out, any Reserve list
                    (IR, LTIR, PUP, NFI, Reserve/COVID), Suspended.
                    Removed from the pool BEFORE the per-team cap, so a
                    healthy player takes the slot.
  flag(row)       — he may not play: Questionable / Doubtful /
                    Day-to-day, or he missed his team's last game (a
                    scratch or an injury shows up as a missed game
                    first). Kept, with the reason shown beside him.

A missing tag is not "healthy" and not "out" — it is no tag (rule 6).

Pure — no streamlit, no requests.
"""
import re
import unicodedata

# Substrings of a lower-cased status that mean "not playing". Order does
# not matter. "out" is matched as a word so "doubtful" never trips it.
_OUT_WORDS = ("injured reserve", "reserve", "suspen", "pup", "physically unable",
              "non-football", "nfi", "ltir", "inactive", "commissioner exempt")
_OUT_RE = re.compile(r"\b(out|ir)\b")

# Short labels for the ones that MAY play (shown beside the name).
_MAYBE = (("doubtful", "Doubtful"), ("questionable", "Questionable"),
          ("day-to-day", "Day-to-day"), ("day to day", "Day-to-day"),
          ("probable", "Probable"), ("game-time", "Game-time decision"),
          ("gtd", "Game-time decision"))


def _s(status):
    return str(status or "").strip().lower()


def is_out(status):
    s = _s(status)
    if not s:
        return False
    return bool(_OUT_RE.search(s)) or any(w in s for w in _OUT_WORDS)


def maybe_label(status):
    s = _s(status)
    if not s or is_out(s):
        return None
    for key, label in _MAYBE:
        if key in s:
            return label
    return None


def missed_last(row):
    """True when his last game is older than his team's last game."""
    lg, tl = (row or {}).get("last_game"), (row or {}).get("team_last_game")
    return bool(lg and tl and lg < tl)


def flag(row):
    """The one-line warning for a player who MAY not play, or ''."""
    bits = []
    lab = maybe_label((row or {}).get("status"))
    if lab:
        bits.append(lab)
    if missed_last(row):
        bits.append("missed last game")
    return " · ".join(bits)


# ----------------------------------------------------------------------
# ESPN's league injury list ({base}/injuries) — the NHL's only injury
# source, and a second one for the NFL. Shape read tolerantly: the
# athlete's id is on the athlete when ESPN sends it, else in his link.
# ----------------------------------------------------------------------
_ID_IN_LINK = re.compile(r"/id/(\d+)")


def name_key(name):
    """'Tim Stützle' and 'Tim Stutzle' are one key; so are 'J.T.' and 'JT'."""
    s = unicodedata.normalize("NFKD", str(name or "")).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]", "", s.lower())


def parse_injury_feed(data):
    """{"by_id": {pid: status}, "by_name": {name_key: status}} from ESPN's
    league injuries payload; empty dicts for anything unreadable."""
    by_id, by_name = {}, {}
    blocks = (data or {}).get("injuries") if isinstance(data, dict) else None
    for blk in blocks or []:
        if not isinstance(blk, dict):
            continue
        for it in blk.get("injuries") or []:
            if not isinstance(it, dict):
                continue
            a = it.get("athlete") or {}
            status = it.get("status") or (it.get("type") or {}).get("description")
            if not status:
                continue
            pid = a.get("id")
            if not pid:
                for ln in a.get("links") or []:
                    m = _ID_IN_LINK.search(str((ln or {}).get("href") or ""))
                    if m:
                        pid = m.group(1)
                        break
            if pid:
                by_id[str(pid)] = str(status)
            if a.get("displayName"):
                by_name[name_key(a["displayName"])] = str(status)
    return {"by_id": by_id, "by_name": by_name}


def status_for(pid, name, roster_status=None, feed=None):
    """The roster's own tag first, then the league list by id, then by name."""
    if roster_status:
        return roster_status
    feed = feed or {}
    return ((feed.get("by_id") or {}).get(str(pid))
            or (feed.get("by_name") or {}).get(name_key(name)) or None)


def held_out_note(names):
    """'3 held out (injured): A (IR), B (Out), C (Out)' or ''."""
    names = [n for n in names or [] if n]
    if not names:
        return ""
    return f"{len(names)} held out (injured): " + ", ".join(names)
