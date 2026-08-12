"""
Pitchers to Target — slate-wide power-vulnerability board. Ranked by
HR/9 allowed (Brl% tiebreak); every column real and color-graded from
the batter's perspective. Formula and bars in
engines/pitchers_to_target.py.
"""
import pandas as pd
import streamlit as st

from styles.kc_theme import card, footer, COLOR
from styles.table_style import style_stat_table, render_html_table, team_logo_cell, sort_control, tier_legend
from engines.pitchers_to_target import get_pitchers_to_target
from engines.live_sync import sync_latest_button

# Theme injection lives in app.py, which renders once per script run
# before this view is exec'd. It used to be called here as well, so the
# same ~26KB of inline CSS was serialised, shipped and parsed TWICE on
# every rerun of every page. Same cascade either way (the two layers
# overlap only on properties resolved by specificity), so the second
# copy bought nothing.

st.markdown(
    f'<div style="display:flex; align-items:center; gap:8px; margin-bottom:var(--lc-space-sm);">'
    f'<span style="font-size:var(--lc-text-title); font-weight:800; letter-spacing:-0.02em; color:{COLOR["text"]};">PITCHERS TO</span>'
    f'<span style="font-size:var(--lc-text-title); font-weight:800; letter-spacing:-0.02em; color:{COLOR["stat_high"]};">TARGET</span>'
    f'</div>',
    unsafe_allow_html=True,
)

sync_latest_button(key="sync_targets")

# Basis — Season is the full body of work; L10 form is the same math on
# the last 10 appearances (who's giving it up RIGHT NOW).
_b_opts = {"Season": "season", "L10 form": "l10"}
_b_choice = st.segmented_control(
    "Basis", list(_b_opts.keys()), default="Season",
    key="targets_basis", label_visibility="collapsed",
)
_b_label = _b_choice or "Season"

rows, skipped, warning = get_pitchers_to_target(basis=_b_opts.get(_b_label, "season"))

if warning:
    st.warning(warning)

with card("targets"):
    st.markdown(
        f'<div class="pf-card-title" style="color:{COLOR["gold"]};">Most power allowed \u2014 today\'s probable starters</div>'
        f'<div class="pf-card-subtitle">Ranked by HR/9 allowed (Brl% tiebreak) \u00b7 every number is real, '
        f'from each pitcher\'s own Statcast rows \u00b7 color reads from the BATTER\'s perspective: '
        f'blue rows are the arms to target for power, red rows are the ones to avoid \u00b7 '
        f'Basis: <b>{_b_label}</b> \u2014 {"full season" if _b_label == "Season" else "last 10 appearances"} \u00b7 '
        f'a target board, not a prediction \u2014 cross it with the Game Card matchup work.</div>',
        unsafe_allow_html=True,
    )

    if not rows:
        st.info("No rankable starters yet \u2014 probables usually fill in through the morning.")
    else:
        df = pd.DataFrame([
            {
                "Pitcher": r["pitcher"],
                "Game": r["matchup"],
                "Team": r["team"],
                "Opp": r["opp"],
                "IP": f'{r["ip"]:.1f}',
                "HR": str(r["hr"]),
                "HR/9": f'{r["hr9"]:.2f}' if r["hr9"] is not None else "\u2014",
                "ISO": f'{r["iso"]:.3f}' if r["iso"] is not None else "\u2014",
                "SLG": f'{r["slg"]:.3f}' if r["slg"] is not None else "\u2014",
                "Brl%": f'{r["brl"]:.1f}' if r["brl"] is not None else "\u2014",
                "HH%": f'{r["hh"]:.1f}' if r["hh"] is not None else "\u2014",
                "FB%": f'{r["fb"]:.1f}' if r["fb"] is not None else "\u2014",
                "Meatball%": f'{r["meatball"]:.1f}' if r["meatball"] is not None else "\u2014",
            }
            for r in rows
        ])
        # Pitcher stays a COLUMN: render_html_table hides the index (see
        # _base_styler), so an indexed name would disappear entirely.
        df = df[["Pitcher"] + [c for c in df.columns if c != "Pitcher"]]
        # HTML rather than st.dataframe — the grid has drag-to-reorder
        # built in with no way to disable it (streamlit#11222), so a
        # scroll gesture on a phone scatters the columns.
        # Sorting, put back explicitly: moving off st.dataframe
        # removed click-to-sort along with drag-to-reorder. Sorts
        # on a numeric read of the column, so pre-formatted
        # strings order as numbers and blanks fall to the bottom.
        df = sort_control(df, "p2t", default="HR/9")
        # Colour key sits WITH the table. Five filled tiers look
        # authoritative whether or not anyone knows what they mean,
        # and which direction is "good" flips between boards.
        tier_legend(favor_note="Colour reads from the BATTER\u2019s side: gold and cyan are the arms to target.")
        render_html_table(
            style_stat_table(
                df,
                favor_high=["HR", "HR/9", "ISO", "SLG", "Brl%", "HH%", "FB%", "Meatball%"],
                gradient=True,
            # ONLY the logo formatters here. Every numeric column in this
            # frame is built as an ALREADY-FORMATTED STRING above
            # (f'{r["iso"]:.3f}'), so applying "{:.3f}" to it raised
            # ValueError: Unknown format code 'f' for object of type
            # 'str'. Nothing needed restating — unlike the Strikeout
            # Board, whose frame holds real floats.
            # na_rep passed for the same reason it is passed everywhere
            # else: this call resets it to None for every column, and a
            # missing value would then print as the literal "nan"
            # instead of the em dash the rest of the app uses.
            ).format({"Team": team_logo_cell(), "Opp": team_logo_cell()},
                     na_rep="\u2014"),
            key="pitchers_to_target",
        )
        st.caption(
            "IP estimated from Statcast out events (same basis as the Splits table). "
            "Minimum to rank: 3 appearances and 10 est IP in the chosen basis. "
            "Refreshes every 15 minutes \u2014 \u27f3 Sync latest forces it now."
        )

if skipped:
    with st.expander(f"\u26a0\ufe0f Not ranked ({len(skipped)})"):
        for r in skipped:
            st.caption(f"{r['matchup']} \u2014 {r['pitcher']} ({r['team']}): {r.get('status', 'no data')}")

footer()
