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
GameCard makes, in the same order. If the scoring changes, both follow.

ONE DELIBERATE DIFFERENCE FROM THE CARD, stated because this docstring
used to claim there were none while two had accumulated underneath it:
`batter_vs_pitch` is omitted here. Fetching per-pitch profiles for every
hitter on the slate is hundreds of extra dataframe slices per render,
and the arsenal mix term alone is still real information. So the
pitch-matchup term can differ from the card's by a few points.

(The other difference, a missing `batting_order`, was NOT deliberate —
it was an omission, and it is fixed below. The slot term is worth up to
five points and this is the board that gets logged for calibration.)

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
                            get_active_player_ids, prefetch_slate)
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
def get_hr_edge_board(_date_str=None, confirmed_only=False):
    """(rows, meta) — every batter on the slate, ranked by HR Edge.

    confirmed_only=False by DEFAULT — see the note at the guard below.
    Passing True restricts to games with a posted lineup, which
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

    # Warm the per-game boxscore and per-team roster calls concurrently
    # before the serial loop below — same reasoning as the identical
    # call in engines/daily_13.py. Optimisation only; removing it costs
    # speed, never correctness.
    _sides = []
    _clubs = []
    for _g in games:
        for _s in ("away", "home"):
            if _g.get("game_pk"):
                _sides.append((_g.get("game_pk"), _s))
            if _g.get(_s):
                _clubs.append(_g.get(_s))
    prefetch_slate(team_names=_clubs, game_sides=_sides)

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
            # PROJECTED LINEUPS STAY ON THE BOARD, BADGED.
            #
            # confirmed_only used to default True, so before a lineup
            # posted the game simply was not there. At 1 PM on a 15-game
            # slate that meant a two-game board — and because the list
            # was rebuilt from scratch at 5 and 7 PM as lineups arrived,
            # it reordered wholesale under anyone reading it.
            #
            # _lineup_for already falls back to the team's last posted
            # lineup and already drops anyone since placed on the IL, and
            # it reports confirmed=False upward precisely so the weaker
            # claim stays visible. Dropping those games threw away good
            # information to avoid labelling it.
            #
            # Now every game is rated from the morning and the row says
            # which lineup it rests on. The board REFINES through the day
            # instead of appearing.
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
                # Carried so edge_components can price the slot. Only
                # meaningful on a CONFIRMED card — see the guard below.
                "batting_order": b.get("battingOrder"),
                "profile": get_batter_profile_windowed(b.get("id"), window="season", unit="bbe"),
            } for b in batters]
            ranked = rank_batters(profiles, savant_df) if profiles else []
            if not ranked:
                continue

            pitcher_team = game.get("home") if side == "away" else game.get("away")
            for r in ranked:
                # Per batter, not per game: the pen adjustment now folds
                # in how THIS hitter does against the hand the pen
                # actually throws. The team profile and slate baseline
                # underneath are both cached, so this is a dict lookup
                # after the first batter.
                pen_adj, pen_note = pen_context(pitcher_team, opp_id,
                                                batter_id=r.get("id"))
                r.update(edge_components(
                    r.get("id"), opp_id, r.get("hr_score"), pen_adj, pen_note,
                    home_team=park,
                    bats=_effective_hand(r.get("bats"), p_throws),
                    temp=temp, wind=wind, arsenal=arsenal,
                    # THE FIDELITY GAP THIS CLOSES. The Game Card passes
                    # batting_order and this board did not, so the slot
                    # term (+/-5) was on the card and absent here — and
                    # it is this board that gets logged for calibration.
                    # The docstring above promised the two agreed while
                    # the code made them differ by up to five points.
                    #
                    # Only on a confirmed lineup. An unposted card has no
                    # batting order, and yesterday's order is a guess
                    # about tonight that would price a slot the hitter
                    # may not be in.
                    batting_order=(r.get("batting_order") if confirmed else None),
                ))
                r["team"] = batting_team
                # Carried so cap_per_game has a real key. Without it the
                # cap fails open on every row and does nothing — silently,
                # since "no key" is deliberately treated as uncappable.
                r["game_pk"] = game.get("game_pk")
                r["opponent"] = pitcher_team
                r["pitcher"] = opp_name
                r["park"] = park
                r["confirmed"] = confirmed
                # None edge means no Savant sample — the bat can't be
                # rated at all, and dropping it is more honest than
                # sorting it to the bottom as if it had been evaluated.
                if r.get("edge") is not None:
                    rows.append(r)

    # SORTED ON THE UNCLAMPED FLOAT, with the tiebreak SAID OUT LOUD.
    #
    # This was `key=r["edge"]` — an integer, on a stable sort. Ties
    # resolved by the order this loop happened to build rows in (game
    # order, away before home, lineup order), so the top of the board was
    # partly the schedule. Teammates share ctx_adj exactly and therefore
    # tie more often than strangers, which put whole lineups adjacent.
    #
    # HR Score then HR Threat as the declared tiebreak: when the matchup
    # layer cannot separate two bats, the better hitter goes first. That
    # is a choice, and it belongs in the code as one rather than being
    # inherited from iteration order.
    rows.sort(key=lambda r: (r.get("edge_raw") if r.get("edge_raw") is not None
                             else (r.get("edge") or 0),
                             r.get("hr_score") or 0,
                             r.get("hr_threat") or 0), reverse=True)
    meta = {"date": date_str, "games": len(games), "rated": len(rows),
            "skipped": skipped, "savant_error": savant_error,
            "confirmed_only": confirmed_only,
            # How much of the board rests on a real posted card. The page
            # shows this so "6 of 15 lineups confirmed" is readable at a
            # glance rather than inferred from a column.
            "confirmed_games": len({r.get("game_pk") for r in rows
                                    if r.get("confirmed")}),
            "total_games": len({r.get("game_pk") for r in rows})}
    return rows, meta


# Most bats from any ONE GAME allowed in the capped view.
#
# Per GAME, not per team. The context that lifts a whole lineup — park
# factor, temperature, wind, the opposing arsenal — applies to BOTH
# sides of the same game, so a team cap of two still lets a hitter-park
# matinee put four bats in a top fifteen. The game is the unit the
# correlation actually travels on.
GAME_CAP = 2


def cap_per_game(rows, cap=GAME_CAP):
    """(kept, overflow) — at most `cap` bats from any one game.

    ORDER IS PRESERVED. This is a filter over an already-ranked list,
    never a re-rank: the bats that survive stay in exactly the order
    they were in, so the capped view is a subset of the board rather
    than a second, differently-sorted board.

    THE OVERFLOW IS RETURNED, NOT DISCARDED. A bat pushed out has to
    stay reachable underneath the board with the rule named, because
    silently dropping a hitter from a list people bet off is worse than
    the stacking this exists to fix.

    A row with no game key is never capped away. That means an unknown
    key fails OPEN — it can only ever show MORE bats, never hide one on
    the strength of a field that wasn't there.
    """
    kept, overflow, seen = [], [], {}
    for r in rows:
        key = r.get("game_pk") or r.get("game_key")
        if key is None:
            kept.append(r)
            continue
        if seen.get(key, 0) < cap:
            seen[key] = seen.get(key, 0) + 1
            kept.append(r)
        else:
            overflow.append(r)
    return kept, overflow


def top_hr_edge(n=5, confirmed_only=False, cap_games=True):
    """The slate's top n by HR Edge — the real board, all games.

    cap_games=True by default, and that INCLUDES the calibration record.
    The board's job is to answer "who are the best home-run plays
    tonight", and a record graded on a list the page no longer shows
    would be measuring a claim the site stopped making — the same fault
    this module was built to fix, one layer up.

    It is a selection-rule change, not a metric change: what is graded
    (did the bat homer) and the baseline it is graded against (share of
    league starters with a home run) are both unchanged, exactly as when
    HRThreat and Clears% entered the scoring. Dated in HANDOFF.md.

    ON A THIN SLATE THE LIST CAN COME BACK SHORT. Two confirmed games at
    5 PM means four bats, not five. The cap is absolute on purpose: a
    rule that stops applying when it is inconvenient cannot be read off
    the page, and a short honest list beats a fifth pick that only
    exists because the rule was relaxed to reach a round number.
    """
    rows, meta = get_hr_edge_board(confirmed_only=confirmed_only)
    if cap_games:
        rows, overflow = cap_per_game(rows)
        meta = {**meta, "game_cap": GAME_CAP, "capped_out": len(overflow)}
    return rows[:n], meta
