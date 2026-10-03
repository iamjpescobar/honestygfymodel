"""
MLB Model — every game on today's slate with its projected score, win
probability and fair line, and both lineups' props one tap away.

The model is fitted nightly (mlb_model_precompute.py -> data/mlb/model.json;
mlb_prop_precompute.py -> the archive's prop_model.json) and this page
only reads and projects. The slate itself is the live schedule call the
Game Card already makes (15-minute cache), because the model needs each
game's probable starters and those arrive through the day.
"""
from datetime import datetime
from zoneinfo import ZoneInfo

import streamlit as st

from styles.kc_theme import COLOR, card, footer, page_header
from engines.weather_engine import get_todays_games_with_weather
from engines.team_abbreviations import team_abbr
from engines import mlb_game_model as mgm
from engines import model_view as mv
from engines.roster import get_confirmed_lineup, get_last_starting_lineup
from engines.live_sync import sync_latest_button

EASTERN = ZoneInfo("America/New_York")

page_header("MLB Model", "Projected score · win % · fair line · player props",
            align="left")
sync_latest_button(key="sync_mlb_model")

model = mgm.load_model()
if not model:
    st.info("The MLB model is fitted by the nightly data run and is not on this "
            "deploy yet. Run the **Nightly Statcast Data** workflow once and it "
            "appears here and on every Game Card.")
    footer()
    st.stop()

_stk = mv.staking_controls("mlb")
_lines = mgm.posted_lines()

_today = datetime.now(EASTERN).strftime("%Y-%m-%d")
games, err = get_todays_games_with_weather(_today)
if err:
    st.warning(f"Schedule unavailable right now ({err}).")
if not games:
    st.info("No MLB games today.")

_sp_line = ("Starters are in the number." if model.get("use_starters")
            else "Starters are NOT in the number — on the season's walk-forward, adding "
                 "them did not beat team rates alone, so the card shows team rates.")
st.caption(f"Fitted {model.get('generated_at_et')} on {model['league']['games']:,} "
           f"regular-season finals. {_sp_line} Postseason games are projected from "
           f"regular-season rates.")
_tie = model["league"].get("tie_home_win")
_tie_txt = "an unmeasured share (taken as half)" if _tie is None else f"{_tie * 100:.0f}%"
mv.render_validation(
    model.get("validation"), key="mlb_model",
    extra=[model.get("look_ahead_note") or "",
           f"Fitted: a team's own rate is pulled toward the league by "
           f"{model['params']['shrink_k']:.0f} games of league-average evidence; "
           f"runs spread as a negative binomial with size "
           f"{model['params'].get('dispersion')}; home teams score "
           f"{(model['league']['home_mult'] - 1) * 100:+.1f}% vs league; home side "
           f"wins {_tie_txt} of extra-inning games. All measured from this "
           f"season's finals."],
    total_unit="runs")

for i, g in enumerate(games or []):
    away, home = g.get("away"), g.get("home")
    _odds = _lines.get(g.get("game_pk"))
    proj = mgm.project_game(home, away, g.get("home_pitcher_id"), g.get("away_pitcher_id"),
                            model=model, market=_odds)
    with card(f"mlbm_{i}"):
        st.markdown(
            f'<div class="pf-card-title" style="color:{COLOR["gold"]};">'
            f'{team_abbr(away)} @ {team_abbr(home)}</div>'
            f'<div class="pf-card-subtitle">{g.get("away_pitcher") or "TBD"} vs '
            f'{g.get("home_pitcher") or "TBD"}</div>',
            unsafe_allow_html=True)
        note = None
        if proj and model.get("use_starters") and not proj.get("starters_used"):
            note = "Starters not both on record — team rates only for this game."
        mv.render_game_projection(proj, team_abbr(away), team_abbr(home),
                                  key=f"mlbm_{i}", note=note)
        mv.render_value_panel(proj, _odds, team_abbr(away), team_abbr(home),
                              key=f"mlbm_{i}", staking=_stk)
        with st.expander("Player props", expanded=False):
            for side, team, opp_sp in (("away", away, g.get("home_pitcher_id")),
                                       ("home", home, g.get("away_pitcher_id"))):
                lineup, confirmed = get_confirmed_lineup(g.get("game_pk"), side)
                batters = [p for p in (lineup or []) if not p.get("is_pitcher")]
                src = "confirmed lineup"
                if not confirmed or not batters:
                    last, last_date, ok = get_last_starting_lineup(team)
                    batters = [p for p in (last or []) if not p.get("is_pitcher")] if ok else []
                    src = f"projected — last game's lineup ({last_date})" if ok else "no lineup"
                st.markdown(f"**{team_abbr(team)}** · {src}")
                rows, verdicts, pnote = mv.mlb_lineup_props(batters, opp_sp)
                mv.render_prop_table(rows, mv.MLB_PROP_COLUMNS, verdicts,
                                     key=f"mlbm_{i}_{side}", favor_note=pnote)
                mv.render_prop_value_tool(rows, mv.MLB_PROP_COLUMNS,
                                          key=f"mlbm_{i}_{side}", staking=_stk)
            st.caption(mv.MLB_PROP_FOOTNOTE)

footer()
