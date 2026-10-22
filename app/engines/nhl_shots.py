"""
NHL shot attempts and scoring chances (10-22) — iCF, iFF, iSF, iSCF,
iHDCF per skater per game, from the NHL's own play-by-play
(api-web.nhle.com/v1/gamecenter/{id}/play-by-play), which carries every
shot attempt with its x / y spot on the ice, its shooter and, for a
block, the blocker. ESPN's feed does not reliably carry the spot.

The definitions (Natural Stat Trick's, outside the shootout):
  iCF   every attempt: goals, shots on net, misses, attempts BLOCKED
  iFF   unblocked attempts: goals, shots on net, misses
  iSF   shots on net: goals + saved shots (= the SOG props settle on)
  iSCF  scoring chances: unblocked attempts from the home-plate area
        (goal line to the top of the circles, inside the lines from the
        posts to the faceoff dots)
  iHDCF high-danger chances: unblocked attempts from the inner slot
        (goal line out 25 ft, between the hash marks, |y| <= 9 ft)
Chances here are read from the SPOT only. Natural Stat Trick also
counts rebounds and rush shots and uses its own zone polygons, so these
are close to theirs, not identical — the pages say "chances (by shot
location)". A blocked attempt's spot is where it was blocked, so blocked
attempts count toward iCF only.

Per skater-game the row is SHOT_ROW: [icf, iff, isf, g, iscf, ihdcf,
g_sc, g_hd] (g_sc / g_hd: his goals from those spots — what the league's
goals per chance is measured from).

Players are NHL ids in the feed; match_game() maps them to the ESPN ids
the rest of the site uses, by name inside the same game.

Pure — no requests.
"""
import re
import unicodedata

SHOT_ROW = ("icf", "iff", "isf", "g", "iscf", "ihdcf", "g_sc", "g_hd")
KINDS = {"goal": "goal", "shot-on-goal": "sog", "missed-shot": "miss", "blocked-shot": "block"}
NET_X = 89.0


def _int(x):
    try:
        return int(x)
    except (TypeError, ValueError):
        return None


def _num(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def _name(spot):
    def part(k):
        v = spot.get(k)
        return (v.get("default") if isinstance(v, dict) else v) or ""
    return f"{part('firstName')} {part('lastName')}".strip()


def norm(name):
    """'Tim Stützle' -> 'tim stutzle'; punctuation dropped."""
    s = unicodedata.normalize("NFKD", str(name or "")).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z ]", "", s.lower().replace("-", " ")).strip()


def danger(x, y, net_x):
    """(scoring chance, high danger) for an attempt at (x, y) toward the
    net at net_x (+89 or -89)."""
    if x is None or y is None or not net_x:
        return False, False
    d = NET_X - x * (1 if net_x > 0 else -1)      # feet in front of the goal line
    ay = abs(y)
    hd = -2.0 <= d <= 25.0 and ay <= 9.0
    sc = hd or (-2.0 <= d <= 35.0 and ay <= min(22.0, 3.0 + 19.0 * max(d, 0.0) / 20.0))
    return sc, hd


def _net_x(play, shooter_home, x):
    """The net the shooter attacks: from the side the home team defends in
    this period when the feed gives it, else from the zone code."""
    side = str(play.get("homeTeamDefendingSide") or "").lower()
    if side in ("left", "right") and shooter_home is not None:
        home_attacks_right = side == "left"
        return NET_X if home_attacks_right == bool(shooter_home) else -NET_X
    zone = str(((play.get("details") or {}).get("zoneCode")) or "").upper()
    if x is None or x == 0:
        return None
    sign = 1 if x > 0 else -1
    if zone == "O":
        return NET_X * sign
    if zone == "D":
        return -NET_X * sign
    return None


def parse_pbp(pbp):
    """{"home", "away" (team ids), "players": {nhl_pid: {"name", "team",
    "pos"}}, "shots": {nhl_pid: SHOT_ROW list}, "kinds": {kind: n},
    "located": n attempts with a spot, "attempts": n}."""
    pbp = pbp or {}
    home = str(((pbp.get("homeTeam") or {}).get("id")) or "")
    away = str(((pbp.get("awayTeam") or {}).get("id")) or "")
    players = {}
    for sp in pbp.get("rosterSpots") or []:
        pid = sp.get("playerId")
        if pid is not None:
            players[str(pid)] = {"name": _name(sp), "team": str(sp.get("teamId") or ""),
                                 "pos": sp.get("positionCode")}
    out = {"home": home, "away": away, "players": players, "shots": {}, "kinds": {},
           "located": 0, "attempts": 0}
    for pl in pbp.get("plays") or []:
        if not isinstance(pl, dict):
            continue
        kind = KINDS.get(str(pl.get("typeDescKey") or "").lower())
        if not kind:
            continue
        pd_ = pl.get("periodDescriptor") or {}
        if str(pd_.get("periodType") or "").upper() == "SO":
            continue                                  # never the shootout
        det = pl.get("details") or {}
        shooter = det.get("scoringPlayerId") if kind == "goal" else det.get("shootingPlayerId")
        if shooter is None:
            continue
        shooter = str(shooter)
        out["kinds"][kind] = out["kinds"].get(kind, 0) + 1
        out["attempts"] += 1
        row = out["shots"].setdefault(shooter, [0] * len(SHOT_ROW))
        row[0] += 1                                   # iCF
        if kind == "block":
            continue
        row[1] += 1                                   # iFF
        if kind in ("goal", "sog"):
            row[2] += 1                               # iSF
        x, y = _num(det.get("xCoord")), _num(det.get("yCoord"))
        team = (players.get(shooter) or {}).get("team") or str(det.get("eventOwnerTeamId") or "")
        net = _net_x(pl, (team == home) if team else None, x)
        if x is not None and y is not None:
            out["located"] += 1
        sc, hd = danger(x, y, net)
        row[4] += int(sc)
        row[5] += int(hd)
        if kind == "goal":
            row[3] += 1
            row[6] += int(sc)
            row[7] += int(hd)
    return out


def match_game(rec, espn_players):
    """{nhl_pid: espn_pid} for one game. espn_players: {espn_pid: name} of
    the ESPN skaters in that same game. Full name first; else a last name
    that only one player in the game has, with the same first initial."""
    by_full, by_last = {}, {}
    for epid, nm in (espn_players or {}).items():
        n = norm(nm)
        by_full.setdefault(n, []).append(epid)
        parts = n.split()
        if parts:
            by_last.setdefault((parts[-1], parts[0][:1]), []).append(epid)
    out = {}
    for npid, p in (rec.get("players") or {}).items():
        if str(p.get("pos") or "").upper() == "G":
            continue
        n = norm(p.get("name"))
        hit = by_full.get(n) or []
        if len(hit) != 1:
            parts = n.split()
            hit = by_last.get((parts[-1], parts[0][:1]), []) if parts else []
        if len(hit) == 1:
            out[npid] = hit[0]
    return out


def best_game(rec, espn_games):
    """The ESPN game (key) whose skaters' names overlap this NHL game's
    most — so team abbreviations never have to agree between feeds."""
    names = {norm(p.get("name")) for p in (rec.get("players") or {}).values()}
    best, best_n = None, 0
    for key, pl in (espn_games or {}).items():
        n = len(names & {norm(x) for x in pl.values()})
        if n > best_n:
            best, best_n = key, n
    return best if best_n >= 8 else None


def check(rows, espn_sog):
    """{"skater_games", "sog_ok"}: his iSF from the NHL feed against ESPN's
    box-score shots (rows / espn_sog keyed (date, espn_pid))."""
    n = ok = 0
    for k, r in (rows or {}).items():
        s = (espn_sog or {}).get(k)
        if s is None:
            continue
        n += 1
        ok += int(r[2] == s)
    return {"skater_games": n, "sog_ok": ok}


def window(shots_map, dates):
    """Sums of SHOT_ROW over the dates (games he played) that carry a row:
    (n games, [sums])."""
    tot, n = [0] * len(SHOT_ROW), 0
    for d in dates:
        r = (shots_map or {}).get(d)
        if r is None:
            continue
        n += 1
        for i, v in enumerate(r[:len(SHOT_ROW)]):
            tot[i] += v or 0
    return n, tot


def league_rates(skaters, before=None, after=None):
    """{"onnet": iSF / iFF, "c_hd", "c_md", "c_ld" (goals per unblocked
    attempt by spot), "n"} pooled over every skater's rows dated in
    [after, before)."""
    t = [0] * len(SHOT_ROW)
    n = 0
    for p in (skaters or {}).values():
        for d, r in (p.get("shots") or {}).items():
            if (before and d >= before) or (after and d < after):
                continue
            n += 1
            for i, v in enumerate(r[:len(SHOT_ROW)]):
                t[i] += v or 0
    icf, iff, isf, g, sc, hd, gsc, ghd = t
    md, ld = sc - hd, iff - sc
    return {"onnet": isf / iff if iff else None,
            "c_hd": ghd / hd if hd else None,
            "c_md": (gsc - ghd) / md if md else None,
            "c_ld": (g - gsc) / ld if ld else None,
            "att_per_sog": icf / isf if isf else None, "n": n}
