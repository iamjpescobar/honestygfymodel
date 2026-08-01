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

from styles.kc_theme import inject_kc_theme, card, footer, COLOR
from styles.table_style import style_stat_table, render_html_table, team_logo_cell, score_bar, sort_control, tier_legend
from engines.hr_edge_board import get_hr_edge_board
from engines.live_sync import sync_latest_button

inject_kc_theme()

st.markdown(
    f'<div style="display:flex; align-items:center; gap:8px; margin-bottom:6px;">'
    f'<span style="font-size:20px; font-weight:800; letter-spacing:-0.02em; color:{COLOR["text"]};">HR</span>'
    f'<span style="font-size:20px; font-weight:800; letter-spacing:-0.02em; color:{COLOR["stat_high"]};">EDGE</span>'
    f'<span style="font-size:11px; color:{COLOR["text_muted"]}; align-self:flex-end; padding-bottom:3px;">FULL SLATE</span>'
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

        table = []
        for i, r in enumerate(rows[:40], start=1):
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
                "Matchup": r.get("mx"),
                "Context": r.get("ctx_adj"),
                "Why": ctx,
                "Confirmed": "\u2713" if r.get("confirmed") else "proj",
            })

        df = pd.DataFrame(table).set_index("#")
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
            favor_high=["Matchup", "Context"],
            gradient=True,
        ).format({
            # Explicit formats for every numeric column — style_stat_table
            # applies a global precision=2, and anything unlisted falls
            # through to it and renders out of step with its neighbours.
            # Filled bars rather than bare numbers, same as the Game Card
            # lineup — these are the two columns the board is ranked on.
            "HR Edge": score_bar("gold"), "HR Score": score_bar("stat_high"),
            "Matchup": "{:+.1f}", "Context": "{:+.1f}",
            # Logo beside the abbreviation; text stays so the column
            # still reads if an image fails to load.
            "Team": team_logo_cell(),
        }, na_rep="N/A")
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

    if meta.get("skipped"):
        with st.expander(f"Games not included ({len(meta['skipped'])})"):
            for s in meta["skipped"]:
                st.markdown(f"- {s}")
            st.caption(
                "Usually means the lineup or probable starter hasn't posted "
                "yet. These fill in as the afternoon goes."
            )

footer()
