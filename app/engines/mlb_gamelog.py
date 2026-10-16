"""
MLB game logs WITH the postseason (10-16).

THE BUG
-------
The Stats API's gameLog defaults to the REGULAR season. Every game-log
read on the site asked for it that way, so in October:

  - the trend windows (2026 / L25 / L15 / L5, batter and pitcher) stopped
    at the last regular-season game;
  - grading looked for a postseason pick's date in a regular-season log,
    did not find it, and closed the pick as DID NOT PLAY — so no
    postseason pick has ever counted toward any board's record.

THE FIX
-------
splits() reads the regular-season log as before, then the postseason log
(gameType "P"; "F,D,L,W" — wild card, division, LCS, World Series — if
"P" returns nothing), and merges them, one row per game. A postseason
read that fails costs the postseason rows only, never the regular ones:
a failed regular read still raises, exactly as before, so callers keep
telling "the request failed" apart from "he did not play".

Pure — the caller hands in its own getter (get(url, params) -> json).
"""
POSTSEASON_TYPES = ("P", "F,D,L,W")


def _rows(data):
    stats = (data or {}).get("stats") or []
    # EVERY stats entry: a traded player comes back as more than one
    return [sp for entry in stats for sp in ((entry or {}).get("splits") or [])]


def _key(sp):
    gpk = ((sp.get("game") or {}).get("gamePk"))
    return (sp.get("date"), gpk if gpk is not None else id(sp))


def splits(get, url, group, season):
    """[split, ...] date order, regular season + postseason; each split
    gets "_post": True/False. Raises if the REGULAR read raises."""
    base = {"stats": "gameLog", "group": group, "season": season}
    out = [dict(sp, _post=False) for sp in _rows(get(url, dict(base)))]
    for gt in POSTSEASON_TYPES:
        try:
            post = _rows(get(url, dict(base, gameType=gt)))
        except Exception:  # noqa: BLE001 — costs the postseason rows only
            continue
        if post:
            out += [dict(sp, _post=True) for sp in post]
            break
    seen, merged = set(), []
    for sp in out:
        k = _key(sp)
        if k in seen:
            continue
        seen.add(k)
        merged.append(sp)
    merged.sort(key=lambda sp: str(sp.get("date") or ""))
    return merged


def requests_getter(timeout=15):
    """get(url, params) over requests, raising on HTTP errors."""
    import requests

    def get(url, params):
        r = requests.get(url, params=params, timeout=timeout)
        r.raise_for_status()
        return r.json()
    return get
