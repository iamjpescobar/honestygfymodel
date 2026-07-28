"""
HR Edge across the whole slate, not one game card.

WHY THIS EXISTS
---------------
HR Edge was only ever computed inside views/GameCard.py, for the ONE
game the user had selected and against that game's one pitcher. Two
consequences:

  1. There was no slate-wide HR Edge board. The "top 5 HR Edge" the app
     logged for calibration was the top 5 bats in whichever game card
     happened to be open — so the record answered "who were the best
     bats in the game you were looking at", while the page implied "who
     are the best HR plays today". Those are different questions, and
     the record was quietly answering the wrong one.

  2. It couldn't be logged headlessly. calibration_picks.py deliberately
     skipped hr_edge for exactly this reason: reproducing it would have
     meant choosing a game arbitrarily and recording it as if it were
     the board.

This module computes the same thing the Game Card does — same profile
engine, same rank_batters, same edge_components, same park and
temperature context — for EVERY game on the slate, both sides, then
ranks the field. The view keeps its per-game table; this answers the
slate question.

FIDELITY
--------
Nothing is reimplemented. Every number comes from the same engine calls
GameCard makes, in the same order, so a bat's edge here equals its edge
on the card. If the scoring changes, both follow.

COST
----
One pass over the slate touches every lineup and every probable pitcher,
so it is not cheap. Cached for the day like the other boards. Lineups
firm up over the afternoon, so the cache is keyed on the date and a
short TTL rather than held forever.
"""
import streamlit as st
from datetime import datetime
from zoneinfo import ZoneInfo

from engines.weather_engine import get_todays_games_with_weather
from engines.roster import (get_confirmed_lineup, get_last_starting_lineup,
                            get_active_player_ids)
from engines.savant_leaderboard import load_percentile_ranks
from engines.statcast_engine import get_batter_profile_windowed, get_pitcher_statcast
from engines.top_plays import rank_batters
from engines.edge import edge_components, pen_context
from engines.team_abbreviations import team_abbr

EASTERN = ZoneInfo("America/New_York")


def _effective_hand(bats, p_throws):
    """The side this batter will actually hit from tonight.

    A switch hitter bats opposite the pitcher's throwing hand. Park HR
    factors split hard by hand, so passing a raw "S" downstream would
    apply the wrong split to precisely the hitters whose splits differ
    most. Returns None when the pitcher's hand is unknown, which makes
    the park adjustment sit out rather than guess.
    """
    b = (bats or "").upper()
    if b != "S":
        return b or None
    if p_throws == "R":
        return "L"
    if p_throws == "L":
        return "R"
    return None


def _lineup_for(game_pk, side, team_name):
    """(batters, confirmed). Falls back to the last posted lineup.

    `confirmed` is carried all the way to the caller on purpose: a board
    built from yesterday's lineup is a genuinely weaker claim than one
    built from today's posted card, and the difference has to stay
    visible rather than being flattened into a single ranked list.
    """
    lineup, ok = get_confirmed_lineup(game_pk, side)
    if ok and lineup:
        return [p for p in lineup if not p.get("is_pitcher")], True

    # get_last_starting_lineup returns a THREE-tuple
    # (lineup, game_date, confirmed) — not a bare list. Unpacking it as
    # one iterated over the tuple itself and handed the list to .get(),
    # crashing the page with "AttributeError: 'list' object has no
    # attribute 'get'".
    #
    # `last_ok` means "a real posted lineup was found for that PAST
    # game", which is not the same as today's lineup being confirmed —
    # so this always reports False upward. The caller needs to know this
    # board rests on yesterday's card.
    last, _game_date, last_ok = get_last_starting_lineup(team_name)
    if not last_ok or not last:
        return [], False
    batters = [p for p in last if not p.get("is_pitcher")]

    # That lineup can be up to FOURTEEN days old, so anyone who has since
    # gone on the IL is still in it. Drop them against MLB's own active
    # roster. An empty set means the roster call failed — unknown, not
    # "nobody is active" — so fail open rather than emptying the board.
    active = get_active_player_ids(team_name)
    if active:
        batters = [p for p in batters if str(p.get("id")) in active]
    return batters, False


@st.cache_data(ttl=1800, max_entries=4, show_spinner=False)
def get_hr_edge_board(_date_str=None, confirmed_only=True):
    """(rows, meta) — every batter on the slate, ranked by HR Edge.

    confirmed_only=True restricts to games with a posted lineup, which
    is what calibration should log: a pick made off a projected lineup
    isn't the pick the site would have shown, and grading it would
    measure something the model never actually claimed.

    Returns rows carrying the same keys the Game Card table uses, plus
    opponent/park/confirmed, so the UI and the pick logger can share one
    source without either reshaping the other's data.
    """
    date_str = _date_str or datetime.now(EASTERN).strftime("%Y-%m-%d")
    games, games_error = get_todays_games_with_weather()
    if not games:
        return [], {"error": games_error or "No games on the slate.",
                    "date": date_str, "games": 0}

    savant_df, savant_error = load_percentile_ranks()
    rows, skipped = [], []

    for game in games:
        temp = game.get("weather_temp")
        wind = game.get("weather_wind")
        # build_park_hr_factors groups on Statcast's team CODE, while
        # the schedule feed gives full club names ("New York Yankees").
        # Without the abbreviation every park lookup misses silently and
        # returns no adjustment — the failure looks like "this park is
        # neutral" rather than like an error.
        park = team_abbr(game.get("home") or "")
        # Both halves: each side's batters face the OTHER side's probable.
        for side, batting_team, pitcher_id, pitcher_name in (
            ("away", game.get("away"), game.get("away_pitcher_id"), game.get("away_pitcher")),
            ("home", game.get("home"), game.get("home_pitcher_id"), game.get("home_pitcher")),
        ):
            # The pitcher a side FACES is the opposing team's starter.
            opp_id = (game.get("home_pitcher_id") if side == "away"
                      else game.get("away_pitcher_id"))
            opp_name = (game.get("home_pitcher") if side == "away"
                        else game.get("away_pitcher"))
            if not opp_id:
                skipped.append(f"{batting_team} (no probable posted)")
                continue

            batters, confirmed = _lineup_for(game.get("game_pk"), side, batting_team)
            if not batters:
                skipped.append(f"{batting_team} (no lineup)")
                continue
            if confirmed_only and not confirmed:
                skipped.append(f"{batting_team} (lineup not confirmed)")
                continue

            pdata = get_pitcher_statcast(opp_id) or {}
            p_throws = pdata.get("p_throws") or pdata.get("Throws")
            # Mix-only on this board: batter_vs_pitch is deliberately
            # omitted. Fetching per-pitch profiles for every hitter on
            # the slate would mean hundreds of extra dataframe slices per
            # render. The arsenal term alone is still real information.
            # Key is "Pitch Arsenal" — {pitch_type: usage_percent}. Not
            # "arsenal"; that guess would have returned {} for every
            # pitcher and produced a silent zero rather than an error.
            arsenal = pdata.get("Pitch Arsenal") or {}

            profiles = [{
                "name": b["name"], "bats": b.get("bats") or "?", "id": b.get("id"),
                "profile": get_batter_profile_windowed(b.get("id"), window="season", unit="bbe"),
            } for b in batters]
            ranked = rank_batters(profiles, savant_df) if profiles else []
            if not ranked:
                continue

            pitcher_team = game.get("home") if side == "away" else game.get("away")
            pen_adj, pen_note = pen_context(pitcher_team, opp_id)

            for r in ranked:
                r.update(edge_components(
                    r.get("id"), opp_id, r.get("hr_score"), pen_adj, pen_note,
                    home_team=park,
                    bats=_effective_hand(r.get("bats"), p_throws),
                    temp=temp, wind=wind, arsenal=arsenal,
                ))
                r["team"] = batting_team
                r["opponent"] = pitcher_team
                r["pitcher"] = opp_name
                r["park"] = park
                r["confirmed"] = confirmed
                # None edge means no Savant sample — the bat can't be
                # rated at all, and dropping it is more honest than
                # sorting it to the bottom as if it had been evaluated.
                if r.get("edge") is not None:
                    rows.append(r)

    rows.sort(key=lambda r: r.get("edge") or 0, reverse=True)
    meta = {"date": date_str, "games": len(games), "rated": len(rows),
            "skipped": skipped, "savant_error": savant_error,
            "confirmed_only": confirmed_only}
    return rows, meta


def top_hr_edge(n=5, confirmed_only=True):
    """The slate's top n by HR Edge — the real board, all games."""
    rows, meta = get_hr_edge_board(confirmed_only=confirmed_only)
    return rows[:n], meta
