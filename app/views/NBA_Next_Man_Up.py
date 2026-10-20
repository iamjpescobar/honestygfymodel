"""NBA Next Man Up (10-20) — when a big name sits, who has eaten his
minutes and shots before?

For every player OUT tonight who plays 20+ minutes a game, each teammate's
per-game line in the games that player missed vs the games he played —
this team's games only (a traded player's old team never counts), last
season + this one, with both sample sizes on every row. Plus WHAT IF: the
same board for each team's six biggest-minute players who ARE playing,
for a late scratch the nightly has not seen.

Descriptive, not a projection: the model does not move a teammate's
number for an absence (it has not been tested). A big bump on a real
sample, against a book that has not moved, is where to look.
"""
import pandas as pd
import streamlit as st

from styles.kc_theme import COLOR, card, footer, page_header
from engines import live_injuries as _li
from engines import nba_model as nm
from engines import nba_view as nv

page_header("NBA Next Man Up", "Who steps up when a star sits", eyebrow="NBA", align="left")
games, model, _pget = nv.load()
_li.render_note("nba")
st.markdown(
    f'<div style="font-size:var(--lc-text-body); line-height:1.6; color:{COLOR["text"]};">'
    f'A star out changes everyone else&rsquo;s night: more minutes, more shots, more touches. '
    f'Below, every teammate&rsquo;s line in the games the absent player <b>missed</b> vs the '
    f'games he <b>played</b>. Our projections do <b>not</b> move for an absence yet &mdash; '
    f'so a big bump here, on a real sample, is the thing a book may be slow on.<br>'
    f'<span style="color:{COLOR["text_muted"]};">Rows need {nm.NMU_MIN_WITHOUT}+ games without '
    f'him. Small samples are shown with their size; treat a 3-game split as a hint, a '
    f'15-game one as a pattern. It can also reflect the opponents those nights.</span></div>',
    unsafe_allow_html=True)


def _board(b, key):
    rows = b.get("rows") or []
    if not rows:
        st.caption("No teammate has enough games without him yet.")
        return
    df = pd.DataFrame([{
        "Teammate": x["name"],
        "Min without": x["without"].get("min"), "Min Δ": x["delta"].get("min"),
        "Pts without": x["without"].get("pts"), "Pts Δ": x["delta"].get("pts"),
        "Reb Δ": x["delta"].get("reb"), "Ast Δ": x["delta"].get("ast"),
        "PRA Δ": x["delta"].get("pra"),
        "Games without / with": f"{x['n_without']} / {x['n_with']}"} for x in rows])

    def _paint(frame):
        o = pd.DataFrame("", index=frame.index, columns=frame.columns)
        for i in frame.index:
            for c in ("Min Δ", "Pts Δ", "Reb Δ", "Ast Δ", "PRA Δ"):
                v = frame.at[i, c]
                if v is None or pd.isna(v):
                    continue
                if v >= 2:
                    o.at[i, c] = f"color: {COLOR['stat_high']}; font-weight: 800;"
                elif v <= -2:
                    o.at[i, c] = f"color: {COLOR['error']}; font-weight: 700;"
        return o
    from engines import model_view as mv
    st.dataframe(mv.painted(df, _paint), hide_index=True, width="stretch", key=key)


any_out = False
with card("nmu_out"):
    st.markdown(f'<div class="pf-card-title" style="color:{COLOR["gold"]};">'
                f'Out tonight</div>', unsafe_allow_html=True)
    for gi, g in enumerate(games or []):
        for side in ("away", "home"):
            for bi, b in enumerate(g.get(side + "_next_man_up") or []):
                any_out = True
                st.markdown(f"**{b['out_name']}** ({g.get(side + '_abbr')}, "
                            f"{b['out_min']:.0f} min a game) is out — "
                            f"{g.get('away_abbr')} @ {g.get('home_abbr')} {g.get('time_et') or ''}")
                _board(b, f"nmu_o_{gi}_{side}_{bi}")
    if not any_out:
        st.caption("No 20-minute player is listed out on tonight's slate (yet). Check What If "
                   "below when a late scratch hits.")

with card("nmu_whatif"):
    st.markdown(f'<div class="pf-card-title" style="color:{COLOR["gold"]};">'
                f'What if… (a late scratch)</div>', unsafe_allow_html=True)
    opts = []
    for gi, g in enumerate(games or []):
        for side in ("away", "home"):
            for b in g.get(side + "_what_if") or []:
                opts.append((f"{b['out_name']} ({g.get(side + '_abbr')}) sits", b))
    if not opts:
        st.caption("Boards appear after the nightly build, for each team's biggest-minute "
                   "players.")
    else:
        i = st.selectbox("If this player is ruled out…", range(len(opts)),
                         format_func=lambda k: opts[k][0], key="nmu_pick")
        _board(opts[i][1], "nmu_w")

footer()
