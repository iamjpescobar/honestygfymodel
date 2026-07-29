"""
KBO strikeout projections — the same model the MLB Strikeout Board uses,
fed by the KBO precompute's pitcher leaderboard + team batting data.

    proj_K = (K/9 / 9) * (IP per start) * opp_factor

  - K/9         = starter's season strikeouts / IP * 9
  - IP/start    = starter's IP / games
  - opp_factor  = opponent team K rate / league-average K rate,
                  clamped to [0.85, 1.15] so a single soft/tough
                  matchup can't swing a projection more than 15%,
                  exactly like the MLB board.

Opponent K rate uses team SO/PA when PA is available in the team feed,
otherwise SO/game — the same shape either way (compare the team to the
league and clamp). Anything without enough real data to project
honestly is returned with a reason instead of a guessed number,
mirroring the MLB board's behaviour.

This engine only READS the JSON the KBO precompute already writes; it
never scrapes and never mutates that data, so it cannot affect the
starter/stats display even if a projection can't be computed.
"""
import re

# A starter needs at least this much real season work before a K/9 and
# IP/start are stable enough to publish a projection off. Deliberately
# conservative — early-season or just-called-up arms show a reason, not
# a number.
_MIN_GAMES = 3
_MIN_IP = 15.0

# The opponent factor is clamped to this band, same as MLB.
_FACTOR_LO, _FACTOR_HI = 0.85, 1.15


def _parse_ip(raw):
    """KBO renders innings as e.g. '101 1/3' (a space then a fraction).
    Convert to a float; None if unparseable."""
    if raw is None:
        return None
    s = str(raw).strip()
    m = re.match(r"(\d+)\s+(\d)/(\d)", s)
    if m:
        whole, num, den = int(m.group(1)), int(m.group(2)), int(m.group(3))
        return round(whole + num / den, 3) if den else float(whole)
    try:
        return float(s)
    except ValueError:
        return None


def _num(v):
    """Coerce a leaderboard value to float, or None."""
    if v is None:
        return None
    try:
        return float(str(v).replace(",", "").strip())
    except (ValueError, AttributeError):
        return None


def _team_k_rates(team_batting):
    """Map each team -> its strikeout rate, plus the league average.

    Prefers SO/PA (true K%); falls back to SO/game when PA isn't in the
    team feed. Returns (rates_by_team, league_avg, basis_label). Either
    can be empty/None if the data isn't there — callers then skip the
    opponent adjustment rather than invent one.
    """
    rates, basis = {}, None
    if not team_batting:
        return rates, None, None
    have_pa = any(_num((v or {}).get("pa")) for v in team_batting.values())
    basis = "so_pa" if have_pa else "so_game"
    for team, v in team_batting.items():
        v = v or {}
        so = _num(v.get("so"))
        if so is None:
            continue
        denom = _num(v.get("pa")) if basis == "so_pa" else _num(v.get("games"))
        if not denom:
            continue
        rates[team] = so / denom
    league_avg = (sum(rates.values()) / len(rates)) if rates else None
    return rates, league_avg, basis


def _name_key(name):
    """Order-, case- and punctuation-insensitive key for a Korean name.

    The schedule page and the leaderboard write the same pitcher three
    different ways, and an exact dict lookup matched none of them:

        schedule                leaderboard
        James Naile             NAILE James        (order + case)
        Koo Chang-mo            KOO Chang Mo       (hyphen vs space)
        Choi Min-seok           CHOI Min Seok      (both)

    So every KBO starter came back "not on the season pitching
    leaderboard yet" while sitting on the leaderboard directly above,
    and no strikeout projection was ever produced for a real game.

    Normalising to a SORTED SET of lowercased tokens makes all three
    forms identical: {james, naile} either way round, and Chang-mo
    splits to {chang, mo} exactly like Chang Mo.
    """
    if not name:
        return ()
    cleaned = re.sub(r"[^\w\s]", " ", str(name)).lower()
    return tuple(sorted(t for t in cleaned.split() if t))


def _find_pitcher(pitchers, name):
    """Leaderboard entry for this starter, or None.

    Exact key first (cheapest and unambiguous), then the normalised form.
    A normalised key matching MORE than one pitcher is treated as no
    match: two men whose names differ only by word order can't be told
    apart this way, and attaching one's ERA to the other would be worse
    than showing nothing — the same rule NPB uses for duplicate surnames.
    """
    if not name:
        return None
    direct = pitchers.get(name)
    if direct:
        return direct
    key = _name_key(name)
    if not key:
        return None
    hits = [v for k, v in pitchers.items() if _name_key(k) == key]
    return hits[0] if len(hits) == 1 else None


def project_kbo_slate(games, pitchers, team_stats):
    """Return (rows, warning) for the KBO slate.

    games        list of game dicts (away/home + away_starter/home_starter)
    pitchers     dict keyed by pitcher name -> season line
    team_stats   dict with a "batting" sub-dict keyed by team name

    Each row: {game, team, opponent, pitcher, k9, ip_gs, opp_k, factor,
    proj, status}. proj is None when status explains why (thin sample,
    unmatched name, etc.) — never a guessed number.
    """
    rows = []
    if not games:
        return rows, None

    pitchers = pitchers or {}
    team_batting = (team_stats or {}).get("batting") or {}
    k_rates, league_k, _basis = _team_k_rates(team_batting)

    warning = None
    if not league_k:
        warning = ("No team strikeout data yet — projections shown without the "
                   "opponent adjustment (factor 1.0).")

    for g in games or []:
        away, home = g.get("away"), g.get("home")
        for side, opp_side in (("away", "home"), ("home", "away")):
            name = g.get(f"{side}_starter")
            team = g.get(side)
            opp = g.get(opp_side)
            row = {
                "game": f"{away} @ {home}",
                "team": team, "opponent": opp,
                "pitcher": name or "TBD",
                "k9": None, "ip_gs": None, "opp_k": None,
                "factor": None, "proj": None, "status": None,
            }
            if not name or name == "TBD":
                row["status"] = "No probable starter posted yet"
                rows.append(row)
                continue

            sp = _find_pitcher(pitchers, name)
            if not sp:
                row["status"] = "Starter not on the season pitching leaderboard yet"
                rows.append(row)
                continue

            ip = _parse_ip(sp.get("innings_pitched"))
            so = _num(sp.get("strikeouts"))
            games_n = _num(sp.get("games"))
            if ip is None or so is None or not games_n:
                row["status"] = "Missing IP / SO / games on the leaderboard line"
                rows.append(row)
                continue
            if games_n < _MIN_GAMES or ip < _MIN_IP:
                row["status"] = (f"Not enough season work to project honestly "
                                 f"({int(games_n)} G, {ip:.1f} IP)")
                rows.append(row)
                continue

            k9 = so / ip * 9.0

            # INNINGS PER START, not per appearance.
            #
            # This was ip / games_n, where games_n is total games PITCHED.
            # For a pure starter those are the same number. For a swingman
            # — say 10 starts and 15 relief outings — dividing 100 IP by
            # 25 appearances gives 4.0 IP "per start" when his actual
            # starts run near 6. The projection is innings x K rate, so
            # the strikeout number came out roughly a third light, and the
            # column was labelled ip_gs ("per game started"), which made
            # the wrong number look like the right one.
            #
            # Use GS when the leaderboard publishes it. When it doesn't,
            # fall back to appearances but SAY SO in the status, rather
            # than printing a diluted number under an honest-looking label.
            gs = _num(sp.get("games_started"))
            relief_apps = (_num(sp.get("saves")) or 0) + (_num(sp.get("holds")) or 0)
            ip_basis_note = None
            if gs and gs > 0:
                ip_per_start = ip / gs
            else:
                ip_per_start = ip / games_n
                if relief_apps > 0:
                    # Positive evidence of relief work with no GS column:
                    # the innings figure is diluted and we can't correct it.
                    ip_basis_note = (f"IP/start estimated from {int(games_n)} "
                                     f"appearances (no GS published; "
                                     f"{int(relief_apps)} relief outings on file)")

            factor = 1.0
            opp_k = k_rates.get(opp) if k_rates else None
            if opp_k and league_k:
                factor = min(max(opp_k / league_k, _FACTOR_LO), _FACTOR_HI)

            row.update({
                "k9": round(k9, 2),
                "ip_gs": round(ip_per_start, 1),
                "opp_k": round(opp_k, 3) if opp_k is not None else None,
                "factor": round(factor, 3),
                "proj": round((k9 / 9.0) * ip_per_start * factor, 1),
                "status": ip_basis_note,
                "ip_basis": "GS" if (gs and gs > 0) else "appearances",
            })
            rows.append(row)

    # Projected rows first, highest projection on top; unprojected rows
    # follow, so the board leads with the actual plays.
    rows.sort(key=lambda r: (r["proj"] is None, -(r["proj"] or 0)))
    return rows, warning
