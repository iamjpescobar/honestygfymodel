"""
The Daily 13 — the 13 best bets to get a hit TONIGHT.

This is a slate read, not a leaderboard. The original version ranked
by season-long hit rate, which barely moves day to day — the same
names appeared night after night regardless of who was pitching. This
version uses season consistency as a QUALIFICATION FLOOR and ranks on
tonight-specific factors.

FLOOR (must clear all):
  - playing today (confirmed lineup preferred; otherwise roster
    filtered to recent activity)
  - >= 50% of games with a hit this season
  - >= 25 games played

RANKING (0-100, weights declared here and printed on the page):
  RECENT FORM         40%  L15 hit rate, with L5 as a tiebreak signal
  PITCHER MATCHUP     35%  the opposing starter's real BA allowed and
                           K% (contact-friendly arms score higher),
                           plus career BvP when the sample clears the
                           floor
  CONTEXT             25%  the opposing BULLPEN's real BA allowed
                           (late at-bats matter) and LINEUP SLOT
                           (top-of-order bats get an extra PA)

L15 GATE: hitting in >= 12 of the last 15 is a genuine "locked in"
signal. Rather than filtering the board down to a handful of names on
quiet nights, those bats get a ranking BOOST and a badge, so the board
always fills 13 with the hottest bats pinned on top.

Every component is real, sample-floored, and attached to the row so
the page can show why each name is there. Nothing is fabricated: when
a factor can't be measured (no probable posted, thin bullpen data),
that component sits at neutral and says so.
"""
import json
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
import streamlit as st

from engines.weather_engine import get_todays_games_with_weather
from engines.roster import get_live_team_roster, get_confirmed_lineup
from engines.statcast_engine import (
    _read_local_parquet, _HIT_EVENTS, get_pitcher_advanced_splits,
)
from engines.team_abbreviations import team_abbr

EASTERN = ZoneInfo("America/New_York")

# ---- qualification floor ----
MIN_HIT_RATE = 50.0     # season share of games with >= 1 hit
MIN_GAMES = 25          # season games played
BOARD_SIZE = 13

# ---- L15 "locked in" gate (boost, not filter) ----
L15_GATE_HITS = 12
L15_GATE_GAMES = 15
L15_GATE_BOOST = 8.0    # points added to the tonight score

# ---- ranking weights (must sum to 1.0) ----
W_FORM = 0.40
W_MATCHUP = 0.35
W_CONTEXT = 0.25

# ---- component floors ----
BVP_MIN_PA = 8
# How many top candidates get a BvP lookup. Wider than the 13-man
# board so a bat can still climb in on career history, but far short
# of the whole slate — each lookup is a network call.
BVP_POOL = 30
PEN_MIN_ARMS = 5
PEN_MIN_IP = 40.0


def _data_stamp():
    try:
        p = Path(__file__).resolve().parents[1] / "data" / "statcast" / "manifest.json"
        m = json.loads(p.read_text())
        return m.get("through_date"), m.get("generated_at_utc")
    except Exception:
        return None, None


@st.cache_data(ttl=21600, max_entries=500, show_spinner=False)
def _hit_log(pid):
    """(games, hit_games, streak, last_date, per_game_hits) — per_game
    is oldest-to-newest booleans so windows can be sliced.

    CACHED, and this is the single most important cache on the board.
    It runs once per hitter on the slate (~400), and each call reads a
    parquet and does a groupby over a full season of pitches — roughly
    48ms each even with the file already in memory, so ~19 seconds of
    pure recomputation every time the board rebuilt. The result depends
    only on the player's completed game log, which changes once a day
    when the pipeline republishes, so a 6-hour TTL is safe and makes
    every rebuild after the first nearly instant."""
    df = _read_local_parquet("batters", pid)
    if df is None or df.empty:
        return None
    if "events" not in df.columns or "game_pk" not in df.columns:
        return None
    per_game = []
    sort_cols = [c for c in ("game_date", "game_pk") if c in df.columns]
    for gpk, gdf in df.sort_values(sort_cols).groupby("game_pk", sort=False):
        had_hit = bool(gdf["events"].dropna().isin(_HIT_EVENTS).any())
        gdate = str(gdf["game_date"].iloc[0])[:10] if "game_date" in gdf.columns else ""
        per_game.append((gdate, had_hit))
    if not per_game:
        return None
    per_game.sort(key=lambda x: x[0])
    games_n = len(per_game)
    hit_games = sum(1 for _d, h in per_game if h)
    streak = 0
    for _d, h in reversed(per_game):
        if h:
            streak += 1
        else:
            break
    return games_n, hit_games, streak, per_game[-1][0], [h for _d, h in per_game]


@st.cache_data(ttl=21600, max_entries=60, show_spinner=False)
def _pen_contact_json(team: str, starter_pid, date_str: str) -> str:
    """Opposing bullpen's pooled BA allowed — the late-innings half of
    a hit prop. Relievers only (roster pitchers minus tonight's
    starter), each from his own Statcast rows."""
    arms, hits, abs_ = 0, 0, 0
    for p in get_live_team_roster(team) or []:
        if not p.get("is_pitcher") or not p.get("id"):
            continue
        if starter_pid and p["id"] == starter_pid:
            continue
        sp = get_pitcher_advanced_splits(p["id"])
        ip = float(sp.get("IP") or 0.0)
        ba = sp.get("BA")
        if ip <= 0 or ba is None:
            continue
        # weight each arm's BA by its innings (a mop-up arm shouldn't
        # count the same as a setup man)
        arms += 1
        hits += ba * ip
        abs_ += ip
    if arms < PEN_MIN_ARMS or abs_ < PEN_MIN_IP:
        return json.dumps({"ba": None, "arms": arms, "ip": round(abs_, 1)})
    return json.dumps({"ba": round(hits / abs_, 3), "arms": arms, "ip": round(abs_, 1)})


def _scale(value, low, high):
    """Map a value onto 0-100 between two real anchors, clamped."""
    if value is None:
        return None
    try:
        v = (float(value) - low) / (high - low) * 100.0
    except Exception:
        return None
    return max(0.0, min(100.0, v))


# 2 hours, not 30 minutes. The board's inputs are the published game
# logs (rebuilt once nightly) and today's lineups (which firm up over
# the afternoon and are picked up by the roster cache's own shorter
# TTL). A 30-minute TTL meant a full slate-wide rebuild four times an
# hour for data that had not changed — the "loads from zero every
# time" symptom. Sync latest still forces an immediate rebuild.
@st.cache_data(ttl=7200, max_entries=4, show_spinner=False)
def _daily13_json(date_str: str) -> str:
    games, games_error = get_todays_games_with_weather()
    if not games:
        return json.dumps({"rows": [], "scanned": 0, "qualified": 0,
                           "warning": games_error or "No games on today's slate."},
                          default=str)

    teams = []
    for g in games:
        for side in ("away", "home"):
            t = g.get(side)
            if t:
                teams.append((t, g.get("game_pk"), side))

    # tonight's opposing starter + opposing team, per team
    opp_info = {}
    for g in games:
        if g.get("home_pitcher_id"):
            opp_info[g.get("away")] = (g["home_pitcher_id"], g.get("home_pitcher"), g.get("home"))
        if g.get("away_pitcher_id"):
            opp_info[g.get("home")] = (g["away_pitcher_id"], g.get("away_pitcher"), g.get("away"))

    through, _built = _data_stamp()
    cutoff = None
    if through:
        try:
            cutoff = (datetime.strptime(through, "%Y-%m-%d")
                      - timedelta(days=6)).strftime("%Y-%m-%d")
        except Exception:
            cutoff = None

    # ---- opposing starter profiles (one fetch each, reused) ----
    starter_cache = {}
    for team, _gpk, _side in teams:
        info = opp_info.get(team)
        if not info or info[0] in starter_cache:
            continue
        sp = get_pitcher_advanced_splits(info[0])
        starter_cache[info[0]] = {
            "ba": sp.get("BA"), "k_pct": sp.get("K%"), "name": info[1],
        }

    scanned, no_file, inactive, confirmed_teams = 0, 0, 0, 0
    qualified = []
    for team, gpk, side in teams:
        lineup, is_confirmed = get_confirmed_lineup(gpk, side)
        if is_confirmed and lineup:
            pool = [p for p in lineup if not p.get("is_pitcher")]
            confirmed_teams += 1
        else:
            pool = [p for p in (get_live_team_roster(team) or [])
                    if not p.get("is_pitcher")]

        info = opp_info.get(team)
        opp_pid, opp_name, opp_team = info if info else (None, None, None)
        starter = starter_cache.get(opp_pid, {})

        pen = {"ba": None}
        if opp_team:
            try:
                pen = json.loads(_pen_contact_json(opp_team, opp_pid, date_str))
            except Exception:
                pass

        for slot, p in enumerate(pool, start=1):
            if not p.get("id"):
                continue
            scanned += 1
            log = _hit_log(p["id"])
            if log is None:
                no_file += 1
                continue
            games_n, hit_games, streak, last_date, per_game = log
            if not is_confirmed and cutoff and last_date and last_date < cutoff:
                inactive += 1
                continue
            if games_n < MIN_GAMES:
                continue
            rate = hit_games / games_n * 100.0
            if rate < MIN_HIT_RATE:
                continue

            # ---- FORM (40%) ----
            l15 = per_game[-15:]
            l5 = per_game[-5:]
            l15_hits = sum(1 for h in l15 if h)
            l5_hits = sum(1 for h in l5 if h)
            l15_rate = l15_hits / len(l15) * 100.0 if l15 else rate
            l5_rate = l5_hits / len(l5) * 100.0 if l5 else rate
            # L15 carries the weight; L5 nudges it so a bat that's hot
            # RIGHT NOW edges one that cooled off last week.
            form_score = _scale(l15_rate * 0.75 + l5_rate * 0.25, 30.0, 90.0) or 0.0

            # ---- MATCHUP (35%) ----
            matchup_parts, matchup_notes = [], []
            if starter.get("ba") is not None:
                # higher BA allowed = better for a hit prop
                matchup_parts.append(_scale(starter["ba"], 0.200, 0.300))
                matchup_notes.append(f"{opp_name} allows {starter['ba']:.3f}")
            if starter.get("k_pct") is not None:
                # lower K% = more balls in play = better
                matchup_parts.append(_scale(starter["k_pct"], 32.0, 14.0))
                matchup_notes.append(f"{starter['k_pct']:.0f}% K")
            # BvP is deliberately NOT fetched here. career_bvp is a
            # network call to MLB, and this loop runs for every hitter
            # on the slate (~400) — that was hundreds of sequential
            # HTTPS round-trips on every cold load, which is what made
            # this board crawl. Instead the base score is computed for
            # everyone first, and BvP is applied in a second pass to
            # only the top candidates, who are the only ones whose
            # order it can actually change.
            bvp_line = None
            matchup_parts = [m for m in matchup_parts if m is not None]
            matchup_score = (sum(matchup_parts) / len(matchup_parts)
                             if matchup_parts else 50.0)
            if not matchup_parts:
                matchup_notes.append("starter not posted \u2014 neutral")

            # ---- CONTEXT (25%) ----
            context_parts, context_notes = [], []
            if pen.get("ba") is not None:
                context_parts.append(_scale(pen["ba"], 0.200, 0.300))
                context_notes.append(f"pen allows {pen['ba']:.3f}")
            else:
                context_notes.append("pen sample thin \u2014 neutral")
            if is_confirmed:
                # real lineup slot: 1-3 get the extra PA edge
                context_parts.append(_scale(10 - min(slot, 9), 1.0, 9.0))
                context_notes.append(f"bats {slot}{'st' if slot==1 else 'nd' if slot==2 else 'rd' if slot==3 else 'th'}")
            context_score = (sum(context_parts) / len(context_parts)
                             if context_parts else 50.0)

            tonight = (form_score * W_FORM + matchup_score * W_MATCHUP
                       + context_score * W_CONTEXT)

            locked = len(l15) >= L15_GATE_GAMES and l15_hits >= L15_GATE_HITS
            if locked:
                tonight += L15_GATE_BOOST

            qualified.append({
                "name": p.get("name", "?"),
                "id": p.get("id"),
                "team": team_abbr(team),
                "opp": team_abbr(opp_team) if opp_team else "\u2014",
                "gp": games_n,
                "rate": round(rate, 1),
                "l15": f"{l15_hits}/{len(l15)}",
                "l5": f"{l5_hits}/{len(l5)}",
                "streak": streak,
                "locked": locked,
                "tonight": round(min(100.0, tonight), 1),
                "form": round(form_score, 1),
                "matchup": round(matchup_score, 1),
                "context": round(context_score, 1),
                "bvp": bvp_line or "",
                "why": " \u00b7 ".join(matchup_notes + context_notes),
                # carried for the BvP second pass, stripped before return
                "_opp_pid": opp_pid,
                "_matchup_parts": matchup_parts,
                "today": "\u2713 lineup" if is_confirmed else "roster",
            })

    qualified.sort(key=lambda r: (-r["tonight"], -r["rate"]))

    # ---- BvP pass, top candidates only ----
    # Career BvP can move a player's matchup component, so it is only
    # worth fetching for players close enough to the cut for it to
    # matter. BVP_POOL is comfortably wider than the board itself, so
    # a bat can still climb in on BvP — but the cost is ~30 network
    # calls instead of ~400.
    from engines.bvp import career_bvp
    for r in qualified[:BVP_POOL]:
        opp_pid = r.pop("_opp_pid", None)
        if not opp_pid or not r.get("id"):
            continue
        try:
            d = career_bvp(r["id"], opp_pid)
        except Exception:
            continue
        if not d or not d.get("ab"):
            continue
        avg = d.get("avg")
        if d.get("pa", 0) >= BVP_MIN_PA and avg is not None:
            r["bvp"] = f'{d["h"]}-for-{d["ab"]} ({avg:.3f})'
            # Re-weight the matchup component with BvP included, using
            # the same averaging the first pass used.
            bvp_component = _scale(avg, 0.150, 0.400)
            if bvp_component is not None and r.get("_matchup_parts"):
                parts = r["_matchup_parts"] + [bvp_component]
                r["matchup"] = round(sum(parts) / len(parts), 1)
                r["tonight"] = round(min(100.0, (
                    r["form"] * W_FORM + r["matchup"] * W_MATCHUP
                    + r["context"] * W_CONTEXT
                    + (L15_GATE_BOOST if r.get("locked") else 0)
                )), 1)
                r["why"] = (r.get("why") or "") + f' \u00b7 BvP {r["bvp"]}'
        elif d.get("ab"):
            r["bvp"] = f'{d["h"]}-for-{d["ab"]} (small)'

    for r in qualified:
        r.pop("_opp_pid", None)
        r.pop("_matchup_parts", None)
        r.setdefault("bvp", "")

    # re-sort after the BvP pass, since it can change order
    qualified.sort(key=lambda r: (-r["tonight"], -r["rate"]))
    return json.dumps({
        "rows": qualified[:BOARD_SIZE],
        "data_through": through,
        "built": _built,
        "scanned": scanned,
        "no_file": no_file,
        "inactive": inactive,
        "confirmed_teams": confirmed_teams,
        "qualified": len(qualified),
        "warning": games_error,
    }, default=str)


def get_daily_13():
    """(rows, meta) for today's slate (US Eastern)."""
    date_str = datetime.now(EASTERN).strftime("%Y-%m-%d")
    try:
        payload = json.loads(_daily13_json(date_str))
    except Exception as e:
        return [], {"warning": f"Daily 13 cache error: {e}", "scanned": 0,
                    "qualified": 0, "no_file": 0}
    rows = payload.pop("rows", []) or []
    return rows, payload
