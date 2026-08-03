"""
WNBA slate + full matchup research data — real data from ESPN's public
WNBA API (scoreboard + game box scores, both verified from Actions).

What this produces, all computed from real games:
- Today's ET slate: teams (with their real brand colors), arena, tip
  time, status, records, leaders, and the betting line where present.
- Team research per side: points for/against per game, last-10 record,
  and average total points in their games (the totals read).
- TEAM H2H: the season series between tonight's two teams — record,
  every meeting's score, and the average total in those meetings.
- PLAYER research: per player, season + L5/L10 MIN/PTS/REB/AST from
  real box-score logs — plus PLAYER H2H: her averages specifically in
  games against tonight's opponent, with the meeting count shown.

Every number is read from the feed or is arithmetic on it. Absent
data is omitted, never estimated. Small samples are shipped with
their sample size so the reader can judge them honestly.
"""

import json
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import requests

EASTERN = ZoneInfo("America/New_York")
SEASON_START = date(2026, 4, 3)
BASE = "https://site.api.espn.com/apis/site/v2/sports/basketball/wnba"

UA = {
    "User-Agent": ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                   "AppleWebKit/537.36 (KHTML, like Gecko) "
                   "Chrome/126.0.0.0 Safari/537.36"),
}

OUT = Path("build_data") / "data" / "wnba"

STATUS_MAP = {
    "STATUS_SCHEDULED": "scheduled",
    "STATUS_IN_PROGRESS": "in progress",
    "STATUS_HALFTIME": "in progress",
    "STATUS_END_PERIOD": "in progress",
    "STATUS_FINAL": "final",
    "STATUS_POSTPONED": "postponed",
    "STATUS_CANCELED": "postponed",
}

LEADER_CATS = {"points": "PTS", "rebounds": "REB", "assists": "AST"}


def get_json(url):
    r = requests.get(url, headers=UA, timeout=25)
    r.raise_for_status()
    return r.json()


def _to_et(iso_utc: str) -> str:
    try:
        dt = datetime.fromisoformat(iso_utc.replace("Z", "+00:00"))
        return dt.astimezone(EASTERN).strftime("%-I:%M %p")
    except Exception:
        return "TBD"


def _record(competitor):
    out = {}
    for rec in competitor.get("records", []) or []:
        name = (rec.get("name") or rec.get("type") or "").lower()
        if rec.get("summary"):
            if name == "overall":
                out["overall"] = rec["summary"]
            elif name in ("home",):
                out["home"] = rec["summary"]
            elif name in ("road", "away"):
                out["road"] = rec["summary"]
    return out


TEAM_STAT_MAP = [
    ("fieldgoalpct", "fg_pct"), ("threepointfieldgoalpct", "tp_pct"),
    ("threepointpct", "tp_pct"), ("avgrebounds", "reb_g"),
    ("avgassists", "ast_g"), ("avgturnovers", "to_g"),
]


def _team_stats(competitor):
    """Selected season stats from the feed's own statistics block —
    stored only when present, matched defensively by name."""
    out = {}
    for s in competitor.get("statistics", []) or []:
        name = (s.get("name") or "").lower().replace(" ", "")
        val = s.get("displayValue")
        if val is None:
            continue
        for needle, key in TEAM_STAT_MAP:
            if name == needle and key not in out:
                out[key] = val
    return out


def _leaders(competitor):
    out = []
    for cat in competitor.get("leaders", []) or []:
        abbrev = LEADER_CATS.get(cat.get("name"))
        if not abbrev:
            continue
        entries = cat.get("leaders") or []
        if not entries:
            continue
        athlete = entries[0].get("athlete") or {}
        name = athlete.get("shortName") or athlete.get("displayName")
        val = entries[0].get("displayValue")
        if name and val is not None:
            out.append({"cat": abbrev, "name": name, "value": val})
    return out


def _team_logo(team):
    """ESPN's own logo URL for a team block, or None.

    Prefers `logo`, falls back to the first entry in `logos`, and returns
    None when neither is present so the caller can fall back to the
    id-built path and then to plain text. Never fabricates a URL.
    """
    t = team or {}
    u = t.get("logo")
    if not u:
        for cand in (t.get("logos") or []):
            if isinstance(cand, dict) and cand.get("href"):
                return cand["href"]
    return u or None


def parse_scoreboard_events(payload):
    for event in payload.get("events", []) or []:
        comps = event.get("competitions") or []
        if not comps:
            continue
        comp = comps[0]
        competitors = comp.get("competitors") or []
        home = next((c for c in competitors if c.get("homeAway") == "home"), None)
        away = next((c for c in competitors if c.get("homeAway") == "away"), None)
        if not home or not away:
            continue

        status_name = (((event.get("status") or {}).get("type")) or {}).get("name", "")
        status = STATUS_MAP.get(status_name, "scheduled")
        completed = (((event.get("status") or {}).get("type")) or {}).get("completed", False)

        g = {
            "away": (away.get("team") or {}).get("displayName", "TBD"),
            "home": (home.get("team") or {}).get("displayName", "TBD"),
            # ESPN's numeric team ids. Kept because the SUMMARY endpoint's
            # "rosters" block is empty for the WNBA feed — verified in a
            # nightly log: "0 announced starters" on every game, with only
            # the handful of injury-report entries present. So the only
            # way to learn who is actually on a team is the dedicated
            # /teams/{id}/roster endpoint, which needs these ids.
            "away_id": str((away.get("team") or {}).get("id") or ""),
            "home_id": str((home.get("team") or {}).get("id") or ""),
            "away_color": (away.get("team") or {}).get("color"),
            "home_color": (home.get("team") or {}).get("color"),
            # ESPN'S OWN LOGO URL, captured rather than constructed.
            #
            # Same fix already applied to the per-game logs (see
            # _logos in the box-score parser): engines/wnba_logos builds
            # a CDN path out of the team id, and that path does not
            # exist for every team — the expansion clubs in particular
            # 404, which is what renders a broken-image "?" in the
            # Team/Opp columns of the props and defense boards instead
            # of a mark. The competitor block already carries the exact
            # URL ESPN serves, so taking it removes the guess.
            "away_logo": _team_logo(away.get("team")),
            "home_logo": _team_logo(home.get("team")),
            "arena": (comp.get("venue") or {}).get("fullName", ""),
            "time_et": _to_et(comp.get("date", "")),
            "status": status,
        }
        for side, c in (("away", away), ("home", home)):
            for k, v in _team_stats(c).items():
                g[f"{side}_{k}"] = v
            recs = _record(c)
            if recs.get("overall"):
                g[f"{side}_record"] = recs["overall"]
            if recs.get("home"):
                g[f"{side}_home_record"] = recs["home"]
            if recs.get("road"):
                g[f"{side}_road_record"] = recs["road"]
            lds = _leaders(c)
            if lds:
                g[f"{side}_leaders"] = lds
        g["leaders_kind"] = "game" if completed else "season"

        if completed or status == "in progress":
            try:
                a_s, h_s = int(float(away.get("score", 0))), int(float(home.get("score", 0)))
                g["away_score"], g["home_score"] = a_s, h_s
                g["final" if completed else "score"] = (
                    f'{g["away"]} {a_s} - {h_s} {g["home"]}')
            except (TypeError, ValueError):
                pass

        odds_list = comp.get("odds") or []
        if odds_list:
            odds = odds_list[0]
            bits = []
            if odds.get("details"):
                bits.append(str(odds["details"]))
            if odds.get("overUnder") is not None:
                bits.append(f'O/U {odds["overUnder"]}')
            if bits:
                g["line"] = " \u00b7 ".join(bits)

        yield event.get("id"), status, completed, g


def _num(s):
    try:
        return float(s)
    except (TypeError, ValueError):
        return None


# ------------------------------------------------------------
# TODAY'S AVAILABILITY — from ESPN's own game summary
# ------------------------------------------------------------
# THE THING GAME LOGS CANNOT TELL YOU.
#
# Everything else in this file is a record of the PAST. Availability was
# being inferred from it — "she hasn't appeared in 9 days, so she's
# probably out" — which is backwards-looking by construction and can
# never answer "is she playing TONIGHT". A player returning today looks
# absent; a player who played yesterday and was ruled out this morning
# looks fine. Both are wrong, and no amount of cleverness on game logs
# fixes either, because the information simply isn't in there.
#
# ESPN's summary endpoint carries it directly, and this file already
# calls that endpoint for box scores (see parse_boxscore), so the shape
# and the auth story are both known-good:
#
#   injuries[]  per team, per athlete, with a status ("Out",
#               "Day-To-Day", "Questionable", "Active")
#   rosters[]   per team, each entry carrying starter true/false once
#               lineups are announced
#
# Written defensively on purpose. This is an undocumented endpoint whose
# shape can change without notice, so every field is probed rather than
# assumed, and the result is EMPTY rather than wrong when anything is
# unrecognisable — an empty result makes the app fall back to the old
# inference, which is worse but not misleading. The counts are printed so
# a silent shape change shows up in the workflow log instead of quietly
# degrading every board.
_OUT_STATUSES = {"out", "injured", "suspended", "not with team", "inactive"}


def fetch_team_roster(team_id, debug=False):
    """{pid: {"name", "pos"}} — every player on a team's roster.

    WHY THIS EXISTS. The summary endpoint's "rosters" block is empty for
    the WNBA feed. A nightly log showed "0 announced starters" on all
    three games, with only 4-7 entries per event, and those were the
    injury report. So availability data alone can never tell us who is on
    a team; it only tells us who is hurt.

    That mattered because every other list of players was derived from
    BOX SCORES, which by definition contain only players who have already
    played. A star who has been out — or who is early in a return — has no
    box-score rows, so she existed nowhere in the pipeline and no filter
    change could bring her back. This endpoint is the roster itself,
    independent of whether anyone has played a minute.

    Returns {} on any failure, and every caller treats that as "unknown"
    and falls back to box-score history, so a bad response degrades to
    the old behaviour rather than emptying a slate.
    """
    if not team_id:
        return {}
    try:
        data = get_json(f"{BASE}/teams/{team_id}/roster")
    except Exception as exc:
        print(f"  [roster] team {team_id}: fetch failed ({exc})")
        return {}

    # ESPN returns athletes either as a flat list or grouped into
    # position buckets ({"position": "guard", "items": [...]}) depending
    # on sport and endpoint version. Handle both rather than betting on
    # one shape.
    raw = data.get("athletes") or []
    flat = []
    for a in raw:
        if isinstance(a, dict) and isinstance(a.get("items"), list):
            flat.extend(a["items"])
        else:
            flat.append(a)

    out = {}
    for ath in flat:
        if not isinstance(ath, dict):
            continue
        pid = str(ath.get("id") or "")
        name = ath.get("displayName") or ath.get("fullName") or ath.get("shortName")
        if not pid or not name:
            continue
        pos = ((ath.get("position") or {}).get("abbreviation")
               if isinstance(ath.get("position"), dict) else "") or ""
        out[pid] = {"name": name, "pos": pos}

    print(f"  [roster] team {team_id}: {len(out)} players")
    return out


def fetch_game_availability(event_id, debug=False):
    """{pid: {"status", "out", "starter", "name", "pos"}} for one game, or {} on failure.

    name/pos are captured here because this is ESPN's OWN roster for this
    specific game — the authoritative answer to "who is on this team
    tonight". The slate builder needs it to show a player who is on the
    roster but has little or no game log: a star returning from injury
    has no season stats to rank on, so every stats-derived list drops her,
    and she vanished from the site while every other research site listed
    her. Carrying the name here is what lets her be shown at all.
    """
    try:
        data = get_json(f"{BASE}/summary?event={event_id}")
    except Exception as exc:
        print(f"  [avail] event {event_id}: summary fetch failed ({exc})")
        return {}

    out = {}

    def _remember(ath, entry):
        """Keep the display name and position off the athlete block."""
        nm = ath.get("displayName") or ath.get("shortName")
        if nm and not entry.get("name"):
            entry["name"] = nm
        pos = (ath.get("position") or {}).get("abbreviation")
        if pos and not entry.get("pos"):
            entry["pos"] = pos

    # --- injury report ------------------------------------------------
    for team_block in data.get("injuries") or []:
        for item in team_block.get("injuries") or []:
            ath = item.get("athlete") or {}
            pid = str(ath.get("id") or "")
            if not pid:
                continue
            status = (item.get("status")
                      or (item.get("type") or {}).get("description")
                      or (item.get("type") or {}).get("name") or "")
            entry = out.setdefault(pid, {})
            entry["status"] = str(status)
            entry["out"] = str(status).strip().lower() in _OUT_STATUSES
            _remember(ath, entry)

    # --- announced lineups --------------------------------------------
    for team_block in data.get("rosters") or []:
        _tname = ((team_block.get("team") or {}).get("displayName") or "")
        for item in team_block.get("roster") or []:
            ath = item.get("athlete") or {}
            pid = str(ath.get("id") or "")
            if not pid:
                continue
            entry = out.setdefault(pid, {})
            if "starter" in item:
                entry["starter"] = bool(item.get("starter"))
            # Being listed on a game roster is itself evidence she is
            # available, unless the injury block already said otherwise.
            entry.setdefault("out", False)
            _remember(ath, entry)
            # Which side she's on tonight, so the slate builder can place
            # a roster-only player on the correct team.
            if _tname:
                entry["team"] = _tname
            entry["rostered"] = True

    if debug or out:
        n_out = sum(1 for v in out.values() if v.get("out"))
        n_start = sum(1 for v in out.values() if v.get("starter"))
        print(f"  [avail] event {event_id}: {len(out)} players, "
              f"{n_out} out, {n_start} announced starters")
    return out


def parse_boxscore(event_id, game_date, logs, debug=False):
    data = get_json(f"{BASE}/summary?event={event_id}")
    blocks = (data.get("boxscore") or {}).get("players", []) or []
    names = [(b.get("team") or {}).get("displayName", "") for b in blocks]
    # ESPN's box-score team block carries the team id — capturing it
    # here is what lets the trend chart show opponent LOGOS instead of
    # long team names, matching the MLB charts.
    ids = [(b.get("team") or {}).get("id") for b in blocks]
    # ESPN's OWN logo URL, captured rather than constructed.
    #
    # wnba_logos builds a path from the team id, and that path does not
    # exist for every team — those games rendered a broken-image "?" under
    # the bar instead of a mark. The team block already carries the exact
    # URL ESPN serves, so using it removes the guesswork entirely.
    _logos = []
    for b in blocks:
        t = b.get("team") or {}
        u = t.get("logo")
        if not u:
            for cand in (t.get("logos") or []):
                if isinstance(cand, dict) and cand.get("href"):
                    u = cand["href"]
                    break
        _logos.append(u)
    for i, team_block in enumerate(blocks):
        team_name = names[i]
        opp_name = names[1 - i] if len(names) == 2 else ""
        opp_id = ids[1 - i] if len(ids) == 2 else None
        for stat_group in team_block.get("statistics", []) or []:
            labels = [l.upper() for l in (stat_group.get("labels") or stat_group.get("names") or [])]
            if "PTS" not in labels:
                continue
            idx = {k: labels.index(k) for k in ("MIN", "PTS", "REB", "AST",
                                                 "STL", "BLK", "TO") if k in labels}
            tpt_i = labels.index("3PT") if "3PT" in labels else None
            fg_i = labels.index("FG") if "FG" in labels else None
            ft_i = labels.index("FT") if "FT" in labels else None
            if debug:
                print(f"  [debug] labels for event {event_id}: {labels}")
            for entry in stat_group.get("athletes", []) or []:
                if entry.get("didNotPlay"):
                    continue
                athlete = entry.get("athlete") or {}
                stats = entry.get("stats") or []
                if not athlete.get("id") or len(stats) <= max(idx.values(), default=0):
                    continue
                line = {"date": game_date, "team": team_name, "opp": opp_name,
                        "opp_id": opp_id,
                        # Real URL from ESPN; the view prefers this and
                        # falls back to the id-built path.
                        "opp_logo": (_logos[1 - i] if len(_logos) == 2 else None)}
                for k, i2 in idx.items():
                    line[k.lower()] = _num(stats[i2])
                def _made_att(i, mk, ak):
                    if i is not None and len(stats) > i:
                        parts = str(stats[i]).split("-")
                        if len(parts) == 2:
                            line[mk], line[ak] = _num(parts[0]), _num(parts[1])
                _made_att(tpt_i, "tpm", "tpa")
                _made_att(fg_i, "fgm", "fga")
                _made_att(ft_i, "ftm", "fta")
                if line.get("pts") is not None:
                    line["pra"] = (line.get("pts") or 0) + (line.get("reb") or 0) + (line.get("ast") or 0)
                    line["pr"] = (line.get("pts") or 0) + (line.get("reb") or 0)
                    line["pa"] = (line.get("pts") or 0) + (line.get("ast") or 0)
                if line.get("reb") is not None and line.get("ast") is not None:
                    line["ra"] = (line.get("reb") or 0) + (line.get("ast") or 0)
                if line.get("stl") is not None or line.get("blk") is not None:
                    line["stocks"] = (line.get("stl") or 0) + (line.get("blk") or 0)
                if line.get("min") in (None, 0):
                    continue
                rec = logs.setdefault(str(athlete["id"]), {
                    "name": athlete.get("shortName") or athlete.get("displayName"),
                    "full_name": athlete.get("displayName"),
                    "pos": (athlete.get("position") or {}).get("abbreviation", ""),
                    "games": [],
                })
                rec["team"] = team_name
                rec["games"].append(line)


def _avg(vals):
    vals = [v for v in vals if v is not None]
    return round(sum(vals) / len(vals), 1) if vals else None


def positional_defense(logs):
    """How many points, rebounds, and assists each team ALLOWS to each
    position, per game — the WNBA analog of "which pitcher is easiest
    to hit". Built from the same real box-score logs already collected:
    every player line records who he played against, so crediting the
    opponent with what each position did to them is pure arithmetic on
    data we already have.

    Returns {team: {pos: {"pts": x, "reb": y, "ast": z, "gp": n}}}.
    Positions with fewer than MIN_POS_GAMES team-games of data are
    dropped rather than reported on a thin sample."""
    MIN_POS_GAMES = 5
    # allowed[team][pos] -> {"pts": [...per game...], ...}
    allowed = {}
    for pid, rec in logs.items():
        pos = (rec.get("pos") or "").upper()[:1]   # G / F / C
        if pos not in ("G", "F", "C"):
            continue
        for gl in rec.get("games", []):
            opp = gl.get("opp")
            date = gl.get("date")
            if not opp or not date:
                continue
            bucket = allowed.setdefault(opp, {}).setdefault(pos, {})
            day = bucket.setdefault(date, {"pts": 0.0, "reb": 0.0, "ast": 0.0})
            day["pts"] += gl.get("pts") or 0
            day["reb"] += gl.get("reb") or 0
            day["ast"] += gl.get("ast") or 0

    out = {}
    for team, by_pos in allowed.items():
        for pos, by_date in by_pos.items():
            gp = len(by_date)
            if gp < MIN_POS_GAMES:
                continue
            out.setdefault(team, {})[pos] = {
                "pts": round(sum(d["pts"] for d in by_date.values()) / gp, 1),
                "reb": round(sum(d["reb"] for d in by_date.values()) / gp, 1),
                "ast": round(sum(d["ast"] for d in by_date.values()) / gp, 1),
                "gp": gp,
            }
    return out


def team_research(finals):
    """Per-team: PF/PA per game, last-10 record, avg total — arithmetic
    on real final scores."""
    per = {}
    for g in sorted(finals, key=lambda x: x["date"]):
        for side, opp in (("home", "away"), ("away", "home")):
            t = per.setdefault(g[side], {"pf": [], "pa": [], "results": []})
            us, them = g[f"{side}_score"], g[f"{opp}_score"]
            t["pf"].append(us)
            t["pa"].append(them)
            t["results"].append("W" if us > them else "L")
    out = {}
    for team, t in per.items():
        last10 = t["results"][-10:]

        def _form(n=None, _t=t):
            pf = _t["pf"] if n is None else _t["pf"][-n:]
            pa = _t["pa"] if n is None else _t["pa"][-n:]
            res = _t["results"] if n is None else _t["results"][-n:]
            return {
                "pf_pg": _avg(pf), "pa_pg": _avg(pa),
                "avg_total": _avg([a + b for a, b in zip(pf, pa)]),
                "record": f'{res.count("W")}-{res.count("L")}',
                "gp": len(res),
            }

        out[team] = {
            "pf_pg": _avg(t["pf"]), "pa_pg": _avg(t["pa"]),
            "avg_total": _avg([a + b for a, b in zip(t["pf"], t["pa"])]),
            "l10": f'{last10.count("W")}-{last10.count("L")}',
            # Windowed scoring form from the same real final scores —
            # feeds the Season/L25/L15/L10/L5 grade windows. FG% and
            # TO/G can't be windowed (ESPN publishes them as season
            # team stats, not per-game logs) and stay season-based.
            "form": {"season": _form(), "l25": _form(25), "l15": _form(15),
                     "l10": _form(10), "l5": _form(5)},
        }
    return out


def team_h2h(finals, away, home):
    """Season series between tonight's two teams, from real finals."""
    meetings = [g for g in finals if {g["home"], g["away"]} == {away, home}]
    if not meetings:
        return None
    a_w = h_w = 0
    totals, scorelines = [], []
    for g in sorted(meetings, key=lambda x: x["date"]):
        winner = g["home"] if g["home_score"] > g["away_score"] else g["away"]
        if winner == away:
            a_w += 1
        else:
            h_w += 1
        totals.append(g["home_score"] + g["away_score"])
        scorelines.append(f'{g["away"]} {g["away_score"]}-{g["home_score"]} {g["home"]} ({g["date"][5:]})')
    if a_w > h_w:
        summary = f"{away} lead {a_w}-{h_w}"
    elif h_w > a_w:
        summary = f"{home} lead {h_w}-{a_w}"
    else:
        summary = f"Series tied {a_w}-{h_w}"
    return {"summary": summary, "meetings": len(meetings),
            "avg_total": _avg(totals), "scorelines": scorelines}


def _shooting_pct(subset, made_key, att_key):
    """Attempts-weighted shooting percentage over a set of game logs —
    total makes / total attempts, NOT an average of per-game
    percentages (which would let a 1-for-1 night count the same as a
    10-for-20 one). None when there are no attempts."""
    made = sum(g.get(made_key) or 0 for g in subset)
    att = sum(g.get(att_key) or 0 for g in subset)
    return round(made / att * 100, 1) if att > 0 else None


def player_summaries(logs):
    out = {}
    for pid, rec in logs.items():
        games = sorted(rec["games"], key=lambda g: g["date"])
        gp = len(games)
        if gp == 0:
            continue
        def col(key, subset):
            return _avg([g.get(key) for g in subset])
        out[pid] = {
            "pid": pid,
            "name": rec["name"], "full_name": rec["full_name"],
            "pos": rec["pos"], "team": rec["team"], "gp": gp,
            "min": col("min", games),
            "ppg": col("pts", games), "l5_ppg": col("pts", games[-5:]), "l10_ppg": col("pts", games[-10:]),
            "rpg": col("reb", games), "l5_rpg": col("reb", games[-5:]), "l10_rpg": col("reb", games[-10:]),
            "apg": col("ast", games), "l5_apg": col("ast", games[-5:]), "l10_apg": col("ast", games[-10:]),
            "tpm": col("tpm", games), "l5_tpm": col("tpm", games[-5:]), "l10_tpm": col("tpm", games[-10:]),
            "pra": col("pra", games), "l5_pra": col("pra", games[-5:]), "l10_pra": col("pra", games[-10:]),
            "l15_pra": col("pra", games[-15:]), "l25_pra": col("pra", games[-25:]),
            # Per-game log (last 25) — powers the Player Trend chart.
            # Slim on purpose: only what the chart plots.
            "log": [
                {"date": gl.get("date"), "opp": gl.get("opp"),
                 "opp_id": gl.get("opp_id"),
                 "opp_logo": gl.get("opp_logo"),
                 "pts": gl.get("pts"), "reb": gl.get("reb"),
                 "ast": gl.get("ast"), "tpm": gl.get("tpm"),
                 "stl": gl.get("stl"), "blk": gl.get("blk"),
                 "to": gl.get("to"), "min": gl.get("min"),
                 "pra": gl.get("pra")}
                for gl in games[-25:]
            ],
            "l15_ppg": col("pts", games[-15:]), "l25_ppg": col("pts", games[-25:]),
            "l15_rpg": col("reb", games[-15:]), "l25_rpg": col("reb", games[-25:]),
            "l15_apg": col("ast", games[-15:]), "l25_apg": col("ast", games[-25:]),
            "pr": col("pr", games), "l5_pr": col("pr", games[-5:]), "l10_pr": col("pr", games[-10:]),
            "pa": col("pa", games), "l5_pa": col("pa", games[-5:]), "l10_pa": col("pa", games[-10:]),
            "ra": col("ra", games), "l5_ra": col("ra", games[-5:]), "l10_ra": col("ra", games[-10:]),
            "stocks": col("stocks", games), "l5_stocks": col("stocks", games[-5:]),
            "l10_stocks": col("stocks", games[-10:]),
            "stl": col("stl", games), "blk": col("blk", games),
            "to": col("to", games), "l5_to": col("to", games[-5:]), "l10_to": col("to", games[-10:]),
            "fga": col("fga", games), "l5_fga": col("fga", games[-5:]), "l10_fga": col("fga", games[-10:]),
            "fta": col("fta", games), "l5_fta": col("fta", games[-5:]), "l10_fta": col("fta", games[-10:]),
            "fg_pct": _shooting_pct(games, "fgm", "fga"),
            "tp_pct": _shooting_pct(games, "tpm", "tpa"),
        }
    return out


def player_h2h(logs, pid, opponent):
    """A player's real averages specifically vs tonight's opponent."""
    games = [g for g in logs.get(pid, {}).get("games", []) if g.get("opp") == opponent]
    if not games:
        return None
    return {"h2h_gp": len(games),
            "h2h_ppg": _avg([g.get("pts") for g in games]),
            "h2h_rpg": _avg([g.get("reb") for g in games]),
            "h2h_apg": _avg([g.get("ast") for g in games]),
            "h2h_tpm": _avg([g.get("tpm") for g in games]),
            "h2h_pra": _avg([g.get("pra") for g in games]),
            "h2h_pr": _avg([g.get("pr") for g in games]),
            "h2h_pa": _avg([g.get("pa") for g in games]),
            "h2h_ra": _avg([g.get("ra") for g in games]),
            "h2h_stocks": _avg([g.get("stocks") for g in games]),
            "h2h_fga": _avg([g.get("fga") for g in games])}


def main():
    now_et = datetime.now(EASTERN)
    today = now_et.strftime("%Y-%m-%d")

    sb = get_json(f"{BASE}/scoreboard?dates={today.replace('-', '')}")
    # Keep the event id ON the game. parse_scoreboard_events yields it
    # separately, so it was being discarded here — and without it there's
    # no way to ask ESPN for tonight's injury report and lineups for this
    # specific game.
    todays = []
    for _eid, _st, _done, g in parse_scoreboard_events(sb):
        g["event_id"] = _eid
        todays.append(g)
    print(f"WNBA: slate for {today} ET — {len(todays)} games")

    logs, finals = {}, []
    finals_count = 0
    d = SEASON_START
    first_debug = True
    while d <= now_et.date():
        try:
            day_sb = get_json(f"{BASE}/scoreboard?dates={d.strftime('%Y%m%d')}")
        except Exception as exc:
            print(f"  scoreboard {d} failed: {exc}")
            d += timedelta(days=1)
            continue
        for event_id, status, completed, g in parse_scoreboard_events(day_sb):
            if not completed or not event_id:
                continue
            if g.get("away_score") is not None and g.get("home_score") is not None:
                finals.append({"date": d.isoformat(), "away": g["away"], "home": g["home"],
                               "away_score": g["away_score"], "home_score": g["home_score"]})
            try:
                parse_boxscore(event_id, d.isoformat(), logs, debug=first_debug)
                first_debug = False
                finals_count += 1
            except Exception as exc:
                print(f"  boxscore {event_id} ({d}) failed: {exc}")
        time.sleep(0.15)
        d += timedelta(days=1)

    players = player_summaries(logs)
    teams = team_research(finals)
    pos_def = positional_defense(logs)
    print(f"WNBA: parsed {finals_count} real box scores -> "
          f"{len(players)} players with game logs; {len(teams)} teams with research")
    if players:
        sample = sorted(players.values(), key=lambda p: -(p["ppg"] or 0))[0]
        print(f"  [verify] season PPG leader parsed: {sample['full_name']} "
              f"({sample['team']}) {sample['ppg']} PPG over {sample['gp']} GP, "
              f"L5 {sample['l5_ppg']} / L10 {sample['l10_ppg']}")

    by_team = {}
    for p in players.values():
        by_team.setdefault(p["team"], []).append(p)
    for plist in by_team.values():
        plist.sort(key=lambda p: -(p["ppg"] or 0))

    # Team rosters, fetched ONCE per team rather than once per game — a
    # team appears in only one game a night, but this also keeps the
    # request count to one per team even if that ever changes.
    _team_rosters = {}
    for g in todays:
        for side in ("away", "home"):
            tid = g.get(f"{side}_id")
            if tid and tid not in _team_rosters:
                _team_rosters[tid] = fetch_team_roster(tid)
    _roster_total = sum(len(v) for v in _team_rosters.values())
    print(f"WNBA: fetched {len(_team_rosters)} team rosters, "
          f"{_roster_total} players total")
    if not _roster_total:
        print("  *** WARNING: no team rosters returned. Slates will fall back "
              "to box-score history, which cannot include a player who has "
              "not appeared yet. ***")

    for g in todays:
        # TODAY'S availability, straight from ESPN's summary for THIS
        # game — the only source here that knows about tonight rather
        # than last week. See fetch_game_availability.
        _avail = fetch_game_availability(g.get("event_id")) if g.get("event_id") else {}
        if _avail:
            g["availability_source"] = "espn_summary"

        for side, opp_side in (("away", "home"), ("home", "away")):
            t = teams.get(g[side])
            if t:
                g[f"{side}_pf_pg"] = t["pf_pg"]
                g[f"{side}_pa_pg"] = t["pa_pg"]
                # Positional defense the OPPOSING team allows — powers
                # the Defense Matchup board and the per-player rating.
                g[f"{side}_pos_def_allowed"] = pos_def.get(g.get(side)) or {}
                g[f"{side}_avg_total"] = t["avg_total"]
                g[f"{side}_l10"] = t["l10"]
                g[f"{side}_form"] = t["form"]

            opponent = g[opp_side]
            # TONIGHT'S ROSTER DECIDES WHO APPEARS — not a scoring rank.
            #
            # This was `[p for p in by_team[...] if p["gp"] >= 3][:15]`,
            # sorted by season ppg. Three separate ways that hid real
            # players, all of them at BUILD time, so no page could show
            # them or say why no matter what the app did:
            #
            #   1. The [:15] cap was applied to every player who logged a
            #      minute for the team all season — waived players, 10-day
            #      contracts, hardship signings — so a full-season roster
            #      routinely ran past 15 and cut genuine rotation players.
            #   2. It ranked by POINTS, so a low-scoring starter playing 30
            #      minutes a night lost her slot to a bench scorer. The
            #      comment that used to sit here flagged exactly this
            #      "sorted before anyone knew who was available" problem
            #      when the cap was 9, and then kept the ppg sort.
            #   3. gp >= 3 erased anyone with fewer than three games —
            #      which is every star returning from a long injury. She
            #      has no season sample to rank on, so a stats-derived
            #      list can never contain her, and the site showed nothing
            #      while every other research site listed her.
            #
            # So: start from ESPN's own roster for THIS game, which is the
            # authoritative "who is on this team tonight", and attach
            # whatever season stats exist. A player with no log still gets
            # a row with None stats — visible, correctly named, honestly
            # empty — rather than being deleted. Anyone with a real sample
            # who is not on tonight's roster block (ESPN sometimes omits
            # it pre-game) is kept too, so a missing roster block can never
            # empty the slate.
            _stats_by_pid = {str(p["pid"]): p for p in by_team.get(g[side], [])}
            _team_name = g.get(side)

            # THE ROSTER ENDPOINT IS THE SOURCE OF TRUTH for who is on
            # this team. Not the summary block (empty for WNBA — see
            # fetch_team_roster) and not box-score history (contains only
            # players who have already played, which is precisely how a
            # returning star stayed invisible).
            _roster = _team_rosters.get(g.get(f"{side}_id")) or {}

            picks = []
            for pid, info in _roster.items():
                p = _stats_by_pid.get(pid)
                if p is None:
                    # On the roster, no box-score history. Name and
                    # position come from the roster; every stat stays None
                    # so the app renders "—" rather than inventing one.
                    p = {"pid": pid, "name": info["name"], "pos": info.get("pos") or "",
                         "team": _team_name, "gp": 0, "log": []}
                picks.append(p)

            # FALLBACK, not a supplement. Only when the roster endpoint
            # gave us nothing do we fall back to box-score history, so a
            # failed fetch degrades to the old behaviour instead of
            # emptying the slate. When a roster DOES exist it is the whole
            # answer: adding stats-only players on top would put waived and
            # traded names back on tonight's card.
            if not picks:
                picks = [p for p in _stats_by_pid.values()
                         if (p.get("gp") or 0) >= 3]

            # Minutes, not points — who actually plays tonight.
            picks.sort(key=lambda p: -((p.get("min") or 0)))
            # "pid" FIRST, and it was missing entirely.
            #
            # Without it every slate row was anonymous, which broke three
            # things silently: likely_starters had no id to key on and
            # always returned an empty set (so the Role column stayed
            # blank for everyone), the app couldn't match ESPN's per-game
            # availability back to a player, and wnba_defense logged its
            # calibration picks as {"id": None} — meaning that board's
            # record could never be graded against a box score at all.
            row_keys = ("pid", "name", "pos", "gp", "min",
                        "ppg", "l5_ppg", "l10_ppg",
                        "rpg", "l5_rpg", "l10_rpg",
                        "apg", "l5_apg", "l10_apg",
                        "tpm", "l5_tpm", "l10_tpm",
                        "pra", "l5_pra", "l10_pra",
                        "pr", "l5_pr", "l10_pr",
                        "pa", "l5_pa", "l10_pa",
                        "ra", "l5_ra", "l10_ra",
                        "stocks", "l5_stocks", "l10_stocks", "stl", "blk",
                        "to", "l5_to", "l10_to",
                        "fga", "l5_fga", "l10_fga",
                        "fta", "l5_fta", "l10_fta",
                        "fg_pct", "tp_pct",
                        "l15_pra", "l25_pra", "l15_ppg", "l25_ppg",
                        "l15_rpg", "l25_rpg", "l15_apg", "l25_apg", "log")
            h2h_keys = ("h2h_ppg", "h2h_rpg", "h2h_apg", "h2h_tpm", "h2h_pra",
                        "h2h_pr", "h2h_pa", "h2h_ra",
                        "h2h_stocks", "h2h_fga", "h2h_gp")
            rows = []
            for p in picks:
                row = {k: p.get(k) for k in row_keys}
                hh = player_h2h(logs, p["pid"], opponent) or {}
                for k in h2h_keys:
                    row[k] = hh.get(k)
                # Attach tonight's real status when ESPN has it. These
                # are AUTHORITATIVE and the app prefers them over the
                # game-log inference; absent, the keys stay None and the
                # old behaviour applies unchanged.
                a = _avail.get(str(p.get("pid"))) or {}
                row["today_status"] = a.get("status")
                row["today_out"] = a.get("out")
                row["today_starter"] = a.get("starter")
                rows.append(row)
            if rows:
                g[f"{side}_players"] = rows

        hh = team_h2h(finals, g["away"], g["home"])
        if hh:
            g["h2h"] = hh

    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "games.json").write_text(json.dumps({
        "generated_at_et": now_et.strftime("%Y-%m-%d %H:%M"),
        "source": "ESPN public WNBA API (scoreboard + game box scores)",
        "slate_date_et": today,
        "games": todays,
    }, ensure_ascii=False, indent=2))
    (OUT / "players.json").write_text(json.dumps({
        "generated_at_et": now_et.strftime("%Y-%m-%d %H:%M"),
        "players": players,
    }, ensure_ascii=False, indent=2))

    # Per-game logs, trimmed to what the without-player page needs.
    # Only players with real game lines are included, and each line
    # keeps just date/team/minutes/production — enough to split a
    # season by "did teammate X play", without shipping the full raw
    # box score for every game.
    slim_logs = {}
    for pid, rec in logs.items():
        games = [
            {"date": gl.get("date"), "min": gl.get("min"),
             "pts": gl.get("pts"), "reb": gl.get("reb"),
             "ast": gl.get("ast"), "pra": gl.get("pra")}
            for gl in (rec.get("games") or []) if gl.get("date")
        ]
        if not games:
            continue
        slim_logs[pid] = {
            "name": rec.get("name"), "team": rec.get("team"),
            "pos": rec.get("pos"), "games": games,
        }
    (OUT / "player_logs.json").write_text(
        json.dumps(slim_logs, ensure_ascii=False, indent=2))

    print(f"WNBA: wrote games.json ({len(todays)} games), players.json "
          f"({len(players)} players), player_logs.json ({len(slim_logs)} players)")


if __name__ == "__main__":
    main()
