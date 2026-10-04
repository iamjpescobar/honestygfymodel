"""
NHL Model — projected goals, win % (OT/SO included), fair line against
the market, and skater props (shots, points, goals, assists) for every
game on the slate.

Everything is built by nhl_precompute in CI (engines/nhl_model) and read
off data/nhl/games.json through slate_guard — this page makes no network
calls and fits nothing.
"""
import streamlit as st

from styles.kc_theme import COLOR, SPORT_ACCENTS, card, footer, page_header
from engines.slate_guard import load_slate, payload_field, today_for, generated_at, staleness_note
from engines import model_view as mv
from engines import nhl_model as nm
from engines.live_sync import sync_latest_button

_ACCENT = SPORT_ACCENTS.get("NHL") or COLOR["stat_high"]

page_header("NHL Model", "Projected goals · win % · fair line · skater props",
            eyebrow="MODEL", align="left")
sync_latest_button(key="sync_nhl_model", include_data_package=True)


@st.cache_data(ttl=900, show_spinner=False)
def _load(day):
    games, slate_date, current = load_slate("nhl")
    return games, slate_date, payload_field("nhl", "model"), generated_at("nhl")


_today = today_for("nhl")
games, slate_date, model, built = _load(_today)

if not model:
    _note = staleness_note("nhl", _today)
    if _note:
        st.info(_note)
    st.info("The NHL model is built by the nightly run. If it has not appeared after "
            "one, run the **NHL prior season** workflow once — the model stands on "
            "last season's finals until this one has enough games of its own.")
    footer()
    st.stop()

_p, _lg = model.get("params") or {}, model.get("league") or {}
_fit = ("last season (" + str(model.get("prior_season")) + ")"
        if _p.get("fit_on") == "prior" else "this season")
st.caption(
    f"Fitted on {_fit}; this season's {model.get('current_finals', 0)} finals move each team "
    f"off its carried-over rating. Built {built or '—'} ET.")
_tie = _lg.get("tie_home_win")
mv.render_validation(
    model.get("validation"), key="nhl_model", total_unit="goals",
    extra=[f"Fitted, not chosen: each team starts from last season regressed by a measured "
           f"carryover of {_p.get('carryover')}, then its own games pull it by "
           f"{_p.get('shrink_k')} games of evidence; home teams score "
           f"{((_lg.get('home_mult') or 1) - 1) * 100:+.1f}% vs league; the home side wins "
           f"{'an unmeasured share' if _tie is None else f'{_tie * 100:.0f}%'} of games that "
           f"reach OT/shootout. The test above is on the season the fit came from."])

_stk = mv.staking_controls("nhl")
pv = model.get("props_validation") or {}
verdicts = {k: mv.prop_trust(pv, k) for k, *_ in nm.MARKETS}
_sv_verdicts = {k: mv.prop_trust(model.get("saves_validation") or {}, k)
                for k, *_ in nm.SAVE_MARKETS}
_sog_disp = (model.get("skater_priors") or {}).get("sog_dispersion")
_shot_disp = (model.get("shots") or {}).get("dispersion")
_cols = tuple((k, label) for k, label, *_ in nm.MARKETS)
_val = model.get("validation")
_blend = model.get("blend")

if not games:
    st.info("No NHL games on the current slate.")
else:
    mv.render_trust_row([("Moneyline", mv.market_trust(_blend, "moneyline")),
                         ("Puck line", mv.market_trust(_blend, "spread")),
                         ("Total", mv.market_trust(_blend, "total"))], market=True)
    mv.render_best_value(
        [{"label": f"{g.get('away_abbr') or g.get('away')} @ {g.get('home_abbr') or g.get('home')}",
          "away": g.get("away_abbr") or g.get("away"), "home": g.get("home_abbr") or g.get("home"),
          "proj": g.get("model"), "odds": g.get("odds")}
         for g in games if g.get("game_type") != "preseason"], _blend, _stk, key="nhl")
    with st.expander("Colour key", expanded=False):
        mv.render_model_legend()

for i, g in enumerate(games or []):
    if g.get("game_type") == "preseason":
        continue
    a, h = g.get("away_abbr") or g.get("away"), g.get("home_abbr") or g.get("home")
    with card(f"nhlm_{i}"):
        st.markdown(
            f'<div class="pf-card-title" style="color:{_ACCENT};">{a} @ {h}</div>'
            f'<div class="pf-card-subtitle">{g.get("time_et") or ""} · '
            f'{g.get("venue") or ""}</div>', unsafe_allow_html=True)
        mv.render_game_projection(g.get("model"), a, h, key=f"nhlm_{i}")
        mv.render_value_panel(g.get("model"), g.get("odds"), a, h, key=f"nhlm_{i}",
                              staking=_stk, validation=_val, blend=_blend)
        mv.render_alt_lines(g.get("model"), a, h, key=f"nhlm_{i}", sport="nhl")
        with st.expander("Skater & goalie props \u2014 any line", expanded=False):
            for side, lab in (("away", a), ("home", h)):
                env = g.get(f"{side}_env") or {}
                st.markdown(f"**{lab}** · shot environment "
                            f"{(env.get('shot_ratio') or 1) * 100 - 100:+.0f}% · goal environment "
                            f"{(env.get('goal_ratio') or 1) * 100 - 100:+.0f}% vs their norm")
                rows = []
                for p in g.get(f"{side}_props") or []:
                    row = {"Skater": p.get("name"), "Pos": p.get("pos"), "GP": p.get("gp"),
                           "Exp SOG": p.get("exp_sog"), "Exp Pts": p.get("exp_pts"),
                           "_name": p.get("name"), "_probs": p.get("probs") or {},
                           "_pmfs": nm.skater_pmfs(p.get("mu"), _sog_disp)}
                    for k, *_ in nm.MARKETS:
                        row[k] = mv.prob_cell((p.get("probs") or {}).get(k))
                    rows.append(row)
                if any(r["_pmfs"] for r in rows):
                    mv.render_prop_board(rows, nm.STATS, nm.MARKETS, verdicts,
                                         key=f"nhlm_{i}_{side}", staking=_stk,
                                         info_cols=("Skater", "Pos", "GP"))
                else:
                    # a games.json from before the any-line build: the
                    # fixed lines it carries, until the next nightly
                    mv.render_prop_table(rows, _cols, verdicts, key=f"nhlm_{i}_{side}")
                    mv.render_prop_value_tool(rows, _cols, key=f"nhlm_{i}_{side}", staking=_stk)
                grows = []
                for gp in g.get(f"{side}_goalie_props") or []:
                    grows.append({"Goalie": gp.get("name"), "Starts": gp.get("starts"),
                                  "Last 10": gp.get("crease"),
                                  "SV% (model)": f"{100 * gp['sv_pct']:.1f}%",
                                  "Exp SA": gp.get("exp_sa"), "_name": gp.get("name"),
                                  "_pmfs": {"sv": nm.saves_pmf(gp.get("exp_sa"), _shot_disp,
                                                               gp.get("sv_pct"))}})
                if grows:
                    st.markdown(f"**{lab} goalies** \u2014 saves")
                    mv.render_prop_board(grows, nm.SAVE_STATS, nm.SAVE_MARKETS, _sv_verdicts,
                                         key=f"nhlm_{i}_{side}_g", staking=_stk,
                                         info_cols=("Goalie", "Starts", "Last 10", "SV% (model)",
                                                    "Exp SA"),
                                         footnote="Who starts is not known until the morning "
                                                  "skate \u2014 both of the team's goalies are "
                                                  "priced (Last 10 = starts in the team's last "
                                                  "10 games). Shots against: the shots model's "
                                                  "expectation for the opponent tonight; save rate: "
                                                  "his last season + this one, shrunk toward the "
                                                  "league by a fitted prior. Tested at TEAM level "
                                                  "(team saves) on last season.")
            st.caption(
                "Each cell: chance he clears the line, and the fair price at that chance. "
                "His shots, goals and assists per game (last season + this one, shrunk toward "
                "his position by a fitted prior), scaled by how many shots and goals the model "
                "expects his team to get tonight. NOT in the number: tonight's lines and PP "
                "units, late scratches, the opposing goalie. GP counts both seasons.")

footer()
