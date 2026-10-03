"""
NFL Model — the site's own projected score, win %, fair spread and fair
total for every game this week, set beside the posted line.

Built by nfl_precompute in CI (engines/nfl_game_model) and read off the
week file through nfl_week.load_week — this page fetches and fits
nothing. Player props live on the Projections tab; this page says where
the model's view of each team's scoring differs from the market's, which
is the number those props are anchored to.
"""
from datetime import datetime

import streamlit as st

from styles.kc_theme import COLOR, SPORT_ACCENTS, card, footer, page_header
from engines.live_sync import sync_latest_button
from engines.nfl_week import EASTERN, load_week, staleness_note
from engines import model_math as mm
from engines import model_view as mv

_ACCENT = SPORT_ACCENTS.get("NFL") or COLOR["stat_high"]

page_header("NFL Model", "Projected score · win % · fair spread and total "
            "vs the posted line", eyebrow="MODEL", align="left")
sync_latest_button(key="sync_nfl_model", include_data_package=True)


@st.cache_data(ttl=900, show_spinner=False)
def _load_week_for(day):
    return load_week()


payload, state = _load_week_for(datetime.now(EASTERN).date().isoformat())
model = (payload or {}).get("model")
games = (payload or {}).get("games") or []

if state != "current":
    st.info(staleness_note(payload or {}, state))
if not model:
    st.info("The NFL model is built by the nightly run (the first run also fetches the "
            "2025 season it fits on). It appears here after the next one.")
    footer()
    st.stop()

p, lg = model["params"], model["league"]
_fit = "the 2025 season" if p.get("fit_on") == "prior" else "this season"
st.caption(
    f"Fitted on {_fit} ({model.get('prior_finals') if p.get('fit_on') == 'prior' else model.get('current_finals')} "
    f"games); this season's {model.get('current_finals', 0)} finals move each team off its "
    f"carried-over rating. Margins and totals treated as normal around the projection, with "
    f"spreads MEASURED: ±{p['sd_margin']:.1f} pts on the margin, ±{p['sd_total']:.1f} "
    f"on the total.")
v = model.get("validation") or {}
mv.render_validation(
    v, key="nfl_model", total_unit="points",
    extra=[f"Projected margin: average miss {v.get('margin_mae_model')} pts vs "
           f"{v.get('margin_mae_home_edge')} for “home team by the league's usual edge” "
           f"— {'better' if v.get('margin_beats_home_edge') else 'NOT better'}.",
           f"Fitted, not chosen: each team starts from 2025 regressed by a measured carryover of "
           f"{p.get('carryover')}, and its own games pull it by {p.get('shrink_k')} games of "
           f"evidence. Home teams score {(lg.get('home_mult', 1) - 1) * 100:+.1f}% vs league. "
           f"The test above is on the season the fit came from."])

_stk = mv.staking_controls("nfl")
if not games:
    st.info("No games in this week's file yet.")

for i, g in enumerate(games):
    pj = g.get("model")
    a, h = g.get("away_abbr") or g.get("away"), g.get("home_abbr") or g.get("home")
    with card(f"nflm_{i}"):
        st.markdown(
            f'<div class="pf-card-title" style="color:{_ACCENT};">{a} @ {h}</div>'
            f'<div class="pf-card-subtitle">{g.get("window") or ""} · '
            f'{g.get("kick_time_et") or ""} · {g.get("network") or ""}</div>',
            unsafe_allow_html=True)
        if not pj:
            st.caption("No projection — a team here has no finals on record.")
            continue
        mv.render_game_projection(pj, a, h, key=f"nflm_{i}")
        mv.render_value_panel(pj, g.get("odds"), a, h, key=f"nflm_{i}", staking=_stk)
        bits = [f"Model line: {h} {pj['fair_spread_home']:+.1f}"]
        if pj.get("market_spread_home") is not None:
            bits.append(f"posted {h} {pj['market_spread_home']:+g} → {h} covers "
                        f"{100 * pj['p_home_cover']:.0f}% (fair {mm.fmt_american(pj['fair_cover_home'])}) / "
                        f"{a} {100 * (1 - pj['p_home_cover']):.0f}% (fair {mm.fmt_american(pj['fair_cover_away'])})")
        if pj.get("market_home_pts") is not None:
            bits.append(f"market implies {a} {pj['market_away_pts']:g} – {h} {pj['market_home_pts']:g}; "
                        f"model {pj['away_score']:g} – {pj['home_score']:g}")
        if pj.get("market_note"):
            bits.append(pj["market_note"])
        st.caption(" · ".join(bits))

st.caption("Player props for these games are on the **Projections** tab — they anchor "
           "touchdowns to the market's implied points shown above, so where the model's score "
           "and the market's differ, lean on that gap before the prop.")
footer()
