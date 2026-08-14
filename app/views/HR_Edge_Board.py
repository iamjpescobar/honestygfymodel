"""
HR Edge — every bat on the slate, ranked.

The Game Card shows HR Edge for the one game you're looking at. This
answers the different question: across ALL games today, who are the best
home-run plays? Same engine, same numbers — a bat's edge here equals its
edge on its game card. See engines/hr_edge_board.py.

Restricted to CONFIRMED lineups by default. A board built off projected
lineups isn't the board the site would stand behind, and this is the same
list the calibration logger records, so the two must agree.
"""
import pandas as pd
import streamlit as st

from styles.kc_theme import card, footer, COLOR
from styles.table_style import (style_stat_table, render_html_table, team_logo_cell,
                                score_bar, sort_control, tier_legend, stat_formats)
from engines.hr_edge_board import (get_hr_edge_board, cap_per_game,
                                   GAME_CAP, CAP_UNIT)
# Column headers come from the component, not from this file. Typing
# them here would let the board and engines/form disagree about what
# Form is called, which is the drift STAT_FORMATS and hr_floors both
# exist to stop.
from engines.form import FORM_COLUMNS
from engines.live_sync import sync_latest_button

# Theme injection lives in app.py, which renders once per script run
# before this view is exec'd. It used to be called here as well, so the
# same ~26KB of inline CSS was serialised, shipped and parsed TWICE on
# every rerun of every page. Same cascade either way (the two layers
# overlap only on properties resolved by specificity), so the second
# copy bought nothing.

st.markdown(
    f'<div style="display:flex; align-items:center; gap:8px; margin-bottom:var(--lc-space-sm);">'
    f'<span style="font-size:var(--lc-text-title); font-weight:800; letter-spacing:-0.02em; color:{COLOR["text"]};">HR</span>'
    f'<span style="font-size:var(--lc-text-title); font-weight:800; letter-spacing:-0.02em; color:{COLOR["stat_high"]};">EDGE</span>'
    f'<span style="font-size:var(--lc-text-caption); color:{COLOR["text_muted"]}; align-self:flex-end; padding-bottom:var(--lc-space-hair);">FULL SLATE</span>'
    f'</div>',
    unsafe_allow_html=True,
)

sync_latest_button(key="sync_hr_edge", include_data_package=True)

_show_all = st.toggle(
    "Include unconfirmed lineups",
    value=False,
    help="Off: only games with a posted lineup — the same board the "
         "calibration record logs. On: fills gaps with each team's last "
         "starting lineup, which is a weaker claim and flagged per row.",
)

with st.spinner("Ranking every bat on the slate\u2026 (first load does the real "
                "work; cached after)"):
    rows, meta = get_hr_edge_board(confirmed_only=not _show_all)

# CAPPED HERE TOO, and that is the whole point of capping at all.
#
# top_hr_edge() caps the top 5 that calibration logs. This page called
# get_hr_edge_board directly and did not, so for one commit the graded
# record and the board on screen were two different lists — the exact
# divergence the cap decision was made to prevent, reintroduced one
# layer up from where it was fixed.
#
# The overflow is rendered below rather than dropped: silently removing
# a hitter from a list people bet off is worse than the stacking.
_capped, _overflow = cap_per_game(rows)

if meta.get("error"):
    st.warning(meta["error"])
if meta.get("savant_error"):
    st.warning(
        f"Baseball Savant's percentile rankings aren't reachable right now "
        f"({meta['savant_error']}). HR Score is what HR Edge is built on, so "
        f"the board will be thin or empty until that's back."
    )

if not rows:
    st.info(
        "No rated bats yet. Lineups post 1\u20133 hours before first pitch, so "
        "this fills in through the afternoon. Toggle above to see projected "
        "lineups in the meantime."
    )
else:
    with card("hr_edge_board"):
        st.markdown(
            f'<div class="pf-card-title" style="color:{COLOR["gold"]};">'
            f'TOP HOME RUN PLAYS \u2014 {meta["date"]}</div>',
            unsafe_allow_html=True)

        _cg, _tg = meta.get("confirmed_games", 0), meta.get("total_games", 0)
        if _tg:
            st.caption(
                f"**{_cg} of {_tg} lineups confirmed.** Games without a "
                f"posted card are rated from that team's last starting "
                f"lineup, with anyone since placed on the IL removed, and "
                f"are marked *projected* below. Those rows can still "
                f"change \u2014 a projected bat may not be in tonight's "
                f"lineup at all."
            )
        st.caption(
            f"At most {GAME_CAP} bats per {'TEAM' if CAP_UNIT == 'team' else 'GAME'}. "
            f"Park, temperature, wind and "
            f"the opposing arsenal lift a whole lineup at once, so without "
            f"this one matinee can take over the board. "
            # THE CAPTION USED TO SAY "per game, not per team" WHILE THE
            # CODE COUNTED PER TEAM. CAP_UNIT moved to "team" for more
            # room at the top and this sentence did not follow, so the
            # board was showing up to six bats from one game under a
            # label that explicitly denied it could.
            #
            # Both halves are now generated from CAP_UNIT, so the label
            # cannot drift from the rule again. A right number under a
            # wrong label is the one error nobody downstream can catch.
            + (f"Per TEAM, so both sides of one game each get {GAME_CAP} "
               f"\u2014 up to {GAME_CAP * 2} bats from a single matchup. "
               if CAP_UNIT == "team" else
               f"Per game, not per team: both sides share that context. ")
            + (f"{len(_overflow)} bat(s) held back \u2014 listed below."
               if _overflow else "Nothing held back tonight."))

        table = []
        for i, r in enumerate(_capped[:40], start=1):
            # ctx_notes explains WHY the park/temperature moved this bat.
            # Showing the reason rather than a bare number is the point:
            # a +7 with no explanation is indistinguishable from a bug.
            ctx = "; ".join(r.get("ctx_notes") or []) or "\u2014"
            table.append({
                "#": i,
                "Player": r.get("name"),
                "Bats": r.get("bats"),
                "Team": r.get("team"),
                "vs": r.get("pitcher"),
                "Park": r.get("park"),
                "HR Edge": r.get("edge"),
                "HR Score": r.get("hr_score"),
                # 60% outcome (barrels per PA, no-doubt contact), 40%
                # process (bat speed, swing plane, pull tendency). Sits
                # next to HR Score rather than inside it: HR Score is the
                # scored skill number the board is ranked on, and folding
                # a second composite into it would double-count the same
                # barrel rate that already feeds both.
                "Threat": r.get("hr_threat"),
                # Contact on a trajectory that leaves ANY park, measured
                # off the league's own outcomes. Two decimals because the
                # league average is a fraction of a percent — this column
                # is meant to be near-empty, and a bat with a real number
                # in it is the point.
                "Clears%": r.get("clears_anywhere"),
                # HOW MANY QUALIFICATION FLOORS THIS BAT CLEARS.
                #
                # A tier, never a filter. Only 21 hitters in the league
                # clear all nine, which is roughly seven in any night's
                # lineups — a top-15 board cannot be built from that, and
                # 33 more miss by exactly one. Deleting the hitter at
                # 10.9% barrel with everything else elite is a cliff.
                # See engines/hr_floors.
                #
                # WHICH LINEUP THIS ROW RESTS ON. A bat from a posted
                # card and a bat from the team's last lineup are not the
                # same claim, and the board used to hide the difference
                # by dropping the second entirely. A column rather than a
                # footnote because it changes how much weight a row
                # deserves: a projected bat may not be in tonight's
                # lineup at all.
                # AVERAGE exit velocity beside the ceiling one. EV90 is
                # his BEST contact; this is his typical contact, and the
                # board only ever showed the first.
                "AvgEV": r.get("avg_ev"),
                # FORM, AS THE MEASUREMENTS THEMSELVES — his recent
                # AvgEV minus his season AvgEV in mph, his recent HH%
                # minus his season HH% in points. This was a single
                # 0-100 column with 50 at his own baseline: a real
                # deviation, but rendered as a number no hitter ever
                # recorded, in a row of LEAGUE percentiles it looked
                # identical to. The subtraction is checkable against
                # Savant; the index was not. See engines/form, including
                # why these two are NOT averaged into one column.
                **{c: r.get(c) for c in FORM_COLUMNS if r.get(c) is not None},
                "Lineup": "CONFIRMED" if r.get("confirmed") else "projected",
                "Floors": (f'{r.get("floors_met")}/{r.get("floors_total")}'
                           if r.get("floors_met") is not None else None),
                # THE DENOMINATOR. Inclusion is 50 PA and the scale core
                # is 150, so a part-timer and an everyday bat sat in this
                # table in identical type with nothing between them. The
                # regression protects the number; it does nothing for the
                # reader. Same argument that put G on the pitcher splits.
                "PA": r.get("hr_pa"),
                "Matchup": r.get("mx"),
                "Context": r.get("ctx_adj"),
                "Why": ctx,
                "Confirmed": "\u2713" if r.get("confirmed") else "proj",
            })

        # NOT set_index("#") — _base_styler hides the index, so the rank
        # column vanished from the rendered board exactly the way the
        # batter names vanished from the bullpen arsenal table. Same
        # cause, same fix: keep the row label as a real column.
        df = pd.DataFrame(table)
        # Sort BEFORE the styler is built. style_stat_table computes its
        # gradients from the frame it is handed, so sorting afterwards
        # reordered nothing — the styled object already held the old
        # order. Moving off st.dataframe removed click-to-sort along with
        # drag-to-reorder; this puts sorting back.
        df = sort_control(df, "hredge", default="HR Edge")
        styled = style_stat_table(
            df,
            # HR Edge / HR Score deliberately NOT here: score_bar draws
            # the value, and a gradient cell BEHIND the bar is a second
            # encoding of the same number. The blue cell fought the bar
            # and destroyed the track, which is the thing that makes bar
            # length readable. Same reason they were removed from the
            # Game Card lineup.
            favor_high=["Matchup", "Context", "Threat", "Clears%",
                        "AvgEV"],
            gradient=True,
        ).format(stat_formats(df, extra={
            # THE MAP FIRST, this dict on top of it.
            #
            # This second .format() call replaces the formatter for EVERY
            # column, not just the ones named here, so an omitted column
            # falls through to the precision floor — or, before that floor
            # existed, all the way to pandas' default of SIX decimals,
            # which is what printed PA as "543.000000" on a live board.
            #
            # Listing every column BY HAND was the original fix and it
            # only half worked: AvgEV and Form were added to this table
            # later and nobody came back to this dict, so they printed
            # 89.30 and 63.40 for weeks — the floor caught the six-decimal
            # case and hid the wrong-precision one behind it. STAT_FORMATS
            # already knew AvgEV was a one-decimal exit velocity; the
            # board just wasn't asking. stat_formats() answers for every
            # numeric column the map knows, and this dict overrides it for
            # the ones it can't know about — bars, logos, signed
            # adjustments. A column added tomorrow is formatted by
            # default instead of by memory.
            #
            # Safe on this frame: stat_formats only touches columns whose
            # dtype is numeric, so Floors ("8/9") and Lineup are skipped
            # rather than handed "{:.1f}".
            # Filled bars rather than bare numbers, same as the Game Card
            # lineup — these are the two columns the board is ranked on.
            "HR Edge": score_bar("gold"), "HR Score": score_bar("stat_high"),
            "Matchup": "{:+.1f}", "Context": "{:+.1f}",
            "Threat": "{:.0f}", "Clears%": "{:.2f}",
            # A COUNT, so no decimal point at all. get_hr_metric returns
            # float(val) for everything it reads out of the parquet, so
            # this arrives as 543.0 and has to be told it is a count —
            # the frame cannot tell the reader that on its own.
            "PA": "{:.0f}",
            # Logo beside the abbreviation; text stays so the column
            # still reads if an image fails to load.
            "Team": team_logo_cell(),
        }), na_rep="N/A")
        # Colour key sits WITH the table. Five filled tiers look
        # authoritative whether or not anyone knows what they mean,
        # and which direction is "good" flips between boards.
        tier_legend(favor_note="Higher is better \u2014 colour is the bat\u2019s grade in that column.")
        render_html_table(styled,
            key="hr_edge_board_100")

        _conf = sum(1 for r in rows if r.get("confirmed"))
        st.caption(
            f"{meta['rated']} bats rated across {meta['games']} games "
            f"({_conf} from confirmed lineups). HR Edge = HR Score + matchup "
            f"(BvP, zone fit, bullpen) + context (park by batter hand, "
            f"temperature). Park is deliberately NOT inside HR Score \u2014 the "
            f"skill number is park-neutral so a hitter doesn't get better by "
            f"travelling; tonight's building belongs here."
        )

    # THE BATS THE CAP HELD BACK, with the rule named.
    #
    # Not an afterthought. A capped-out bat is often a genuinely strong
    # play — it lost its place to two teammates in the same building, not
    # to a better hitter — and a board that made it disappear without
    # saying so would be hiding a pick rather than ranking one.
    if _overflow:
        with st.expander(f"Held back by the {GAME_CAP}-per-{CAP_UNIT} cap "
                         f"({len(_overflow)})"):
            st.caption(
                "These rank inside the board above on HR Edge. They sit here "
                "because their game already had its two bats \u2014 not "
                "because anything about them scored worse."
            )
            _ov = pd.DataFrame([{
                "Player": r.get("name"), "Team": r.get("team"),
                "vs": r.get("pitcher"), "Park": r.get("park"),
                "HR Edge": r.get("edge"), "HR Score": r.get("hr_score"),
                "Floors": (f'{r.get("floors_met")}/{r.get("floors_total")}'
                           if r.get("floors_met") is not None else None),
            } for r in _overflow[:20]])
            st.dataframe(_ov, hide_index=True, use_container_width=True)

    if meta.get("skipped"):
        with st.expander(f"Games not included ({len(meta['skipped'])})"):
            for s in meta["skipped"]:
                st.markdown(f"- {s}")
            st.caption(
                "Usually means the lineup or probable starter hasn't posted "
                "yet. These fill in as the afternoon goes."
            )

footer()
