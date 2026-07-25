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

            sp = pitchers.get(name)
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
            ip_per_start = ip / games_n

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
            })
            rows.append(row)

    # Projected rows first, highest projection on top; unprojected rows
    # follow, so the board leads with the actual plays.
    rows.sort(key=lambda r: (r["proj"] is None, -(r["proj"] or 0)))
    return rows, warning
