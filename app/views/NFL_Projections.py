"""NFL — Projections.

Every skill player on the slate, projected for every market the box
score supports: anytime touchdown, rushing and receiving yards,
receptions, targets, carries, passing yards and attempts.

A projection here is a volume times a rate, both measured, with a
matchup multiplier that is a ratio of two measured numbers. Nothing on
this page is fitted and nothing is tuned — see engines/nfl_projection.py
for why, and the caption at the bottom for what that costs.
"""
from datetime import datetime

import pandas as pd
import streamlit as st

from styles.kc_theme import (page_header, badge, footer, card, how_to_read,
                             COLOR, SPORT_ACCENTS)
from styles.table_style import style_stat_table
from engines.live_sync import sync_latest_button
from engines.nfl_week import EASTERN, load_week, staleness_note
from engines.nfl_projection import MARKETS, projection_rows, why
from engines.nfl_prop_odds import p_over
from engines import model_math as _mm
from engines import model_view as _mv
from engines import value as _vl

_ACCENT = SPORT_ACCENTS.get("NFL") or COLOR["stat_high"]

page_header("NFL Projections", "Every market, every player, with the "
            "arithmetic behind each number", eyebrow="SLATE DAY", align="left")
sync_latest_button(key="sync_nfl_proj", include_data_package=True)


@st.cache_data(ttl=900, show_spinner=False)
def _load_week_for(day):
    return load_week()


# Columns worth showing beside the projection, per market. Kept short on
# purpose: the full arithmetic is in the WHY line above the table, and a
# table wide enough to hold all of it is one nobody reads on a phone.
_EXTRA = {
    "Anytime TD": ["TD exp", "TD sample", "TD/touch", "Implied pts"],
    "Rushing yards": ["Carries", "Matchup"],
    "Carries": ["Rush yds", "Matchup"],
    "Receiving yards": ["Targets", "Rec", "Matchup"],
    "Receptions": ["Targets", "Rec yds", "Matchup"],
    "Targets": ["Rec", "Rec yds", "Matchup"],
    "Passing yards": ["Implied pts", "Matchup"],
    "Pass attempts": ["Pass yds", "Implied pts"],
    "Rush + rec yards": ["Rush yds", "Rec yds", "Carries", "Targets"],
}

_today = datetime.now(EASTERN).date()
payload, state = _load_week_for(_today.isoformat())

if state != "current":
    st.info(staleness_note(payload or {}, state, _today))
else:
    games = payload.get("games") or []
    league = payload.get("league") or {}

    if not league:
        st.info("The league baselines this page divides by are built by the "
                "nightly and aren't on disk yet. Nothing is projected until "
                "they are \u2014 a projection measured against a made-up league "
                "average is worse than no projection.")
    else:
        how_to_read([
            ("What a projection is here",
             "A volume times a rate. How much of his team's work he gets "
             "(carries or targets), times how many his team runs a game, times "
             "what he does with each one — every figure measured from real "
             "box scores."),
            ("Matchup",
             "What the defence across from him allows per attempt, divided by "
             "the league average. 1.20 means it gives up 20% more per carry "
             "than a typical defence, so his own rate is multiplied by 1.20. "
             "Below 1.00 is a hard matchup."),
            ("Implied pts",
             "What the posted line says that team scores: the total and the "
             "spread solved for each side. Exact arithmetic on the market's "
             "own numbers, not our estimate."),
            ("TD exp and Anytime %",
             "Implied points converted to touchdowns at the measured rate, "
             "then split by his share of his team's scores. The percentage "
             "assumes scores arrive independently — that is the ONE "
             "modelling assumption on this page, and it is the first thing "
             "the probe checks."),
            ("TD sample",
             "The raw fraction the anytime figure rests on \u2014 \u201c2 of "
             "4\u201d means two of his team's four scores this season are his. "
             "Two-of-two and nine-of-eighteen both read as a high share and "
             "are not the same claim, so the counts are shown rather than "
             "shrunk by some factor chosen by eye."),
            ("GP",
             "Games behind his numbers. Early in a season a share rests on two "
             "or three games and can move a lot; the count is on every row for "
             "that reason."),
            ("Measured against outcomes",
             "The anytime numbers were rebuilt after a walk-forward test over "
             "weeks 1–3 showed the first version was about twice as "
             "confident as reality at the top end. The yardage projections "
             "test within noise of simply using a player's season average "
             "— worth reading for the matchup context they show, not "
             "because they are known to be sharper."),
            ("What this is not",
             "Not compared against a sportsbook's posted prop — those are "
             "not in the public feed. Use it to find where the volume and the "
             "matchup agree, then check the number against your own book."),
        ])

        c1, c2 = st.columns([3, 2])
        with c1:
            market = st.selectbox("Market", list(MARKETS), key="nfl_proj_market")
        with c2:
            hide_final = st.toggle("Hide games already final", value=True,
                                   key="nfl_proj_final")

        rows = projection_rows(games, league, market)
        if hide_final:
            rows = [r for r in rows if not r["_final"]]

        _notes = sorted({r["_note"] for r in rows if r.get("_note")})
        for n in _notes:
            st.caption(f"⚠ {n}")

        if not rows:
            st.info("Nothing to project for that market yet — it fills in once "
                    "the players involved have a game on the books.")
        else:
            st.markdown(
                f'<div style="color:{_ACCENT}; font-weight:800; letter-spacing:0.12em; '
                f'text-transform:uppercase; font-size:var(--lc-text-caption); '
                f'margin:var(--lc-space-lg) 0 var(--lc-space-sm);">'
                f'Top of the board — {market}</div>', unsafe_allow_html=True)
            # KEYED BY POSITION IN THE LIST, not by name. A player's name
            # is not unique — the league has had two Michael Thomases and
            # two Josh Allens — and Streamlit raises on a duplicate key,
            # which takes the WHOLE page down rather than drawing one card
            # oddly. A board bug should never be able to do that.
            for _i, r in enumerate(rows[:5]):
                with card(f'nfl_proj_{_i}'):
                    unit = "%" if market == "Anytime TD" else ""
                    st.markdown(
                        f'<div style="display:flex; justify-content:space-between; '
                        f'align-items:baseline; gap:10px; flex-wrap:wrap;">'
                        f'<div style="font-weight:800; font-size:var(--lc-text-body-lg);">'
                        f'{r["Player"]} <span style="color:{COLOR["text_faint"]}; '
                        f'font-size:var(--lc-text-tiny);">{r["Pos"]} · {r["Team"]} '
                        f'vs {r["Opp"]} · {r["_window"]} · {r["GP"]} GP</span></div>'
                        f'<div style="font-family:\'JetBrains Mono\',monospace; '
                        f'font-size:1.3rem; font-weight:800; color:{_ACCENT};">'
                        f'{r["Proj"]:g}{unit}</div></div>'
                        f'<div style="color:{COLOR["text_muted"]}; '
                        f'font-size:var(--lc-text-small); line-height:1.7;">'
                        f'{why(r, market)}</div>', unsafe_allow_html=True)
                    chips = []
                    if r.get("Status"):
                        chips.append(badge(r["Status"], "bad"))
                    if (r.get("_proj") or {}).get("unadjusted"):
                        chips.append(badge("no opponent sample — unadjusted", "neutral"))
                    if chips:
                        st.markdown(" ".join(chips), unsafe_allow_html=True)

            cols = ["Player", "Pos", "Team", "Opp", "Status", "GP", "Proj"] + _EXTRA[market]
            df = pd.DataFrame([{c: r.get(c) for c in cols} for r in rows])
            df = df.dropna(axis=1, how="all")
            sty = style_stat_table(
                df, favor_high=[c for c in df.columns
                                if c in ("Proj", "Carries", "Targets", "Rush yds",
                                         "Rec yds", "Rec", "Pass yds", "TD exp",
                                         "TD/touch", "Implied pts", "Matchup")],
                gradient=False)
            _fmt = {"TD/touch": "{:.1f}%", "Proj": "{:.1f}", "Carries": "{:.1f}", "Targets": "{:.1f}",
                    "Rush yds": "{:.1f}", "Rec yds": "{:.1f}", "Rec": "{:.1f}",
                    "Pass yds": "{:.1f}", "TD exp": "{:.2f}", "Matchup": "{:.2f}x",
                    "Implied pts": "{:g}", "GP": "{:.0f}"}
            if market == "Anytime TD":
                _fmt["Proj"] = "{:.0f}%"
            sty = sty.format({k: v for k, v in _fmt.items() if k in df.columns},
                             na_rep="—")
            st.dataframe(sty, hide_index=True, width="stretch")
            st.caption("Brighter = more. Sorted by the projection for the market "
                       "selected above. Research, not a pick.")

            # ---- CHECK A PROP AT YOUR PRICE ---------------------------
            # The projection is a mean; a bet is a line and a price. The
            # chance of clearing the line uses the game-to-game scatter
            # MEASURED for this market (engines/nfl_prop_odds).
            with card("nfl_prop_check"):
                st.markdown(f'<div class="pf-card-title" style="color:{_ACCENT};">'
                            f'Check a prop at your price</div>', unsafe_allow_html=True)
                _stk = _mv.staking_controls("nfl_props")
                _names = [f'{r["Player"]} ({r["Team"]})' for r in rows]
                _pick = st.selectbox("Player", range(len(rows)),
                                     format_func=lambda i: _names[i], key="nfl_pc_player")
                _r = rows[_pick]
                _spreads = league.get("prop_spreads") or {}
                if market == "Anytime TD":
                    _p_yes = (_r.get("Anytime %") or 0) / 100.0 if _r.get("Anytime %") is not None else None
                    _px = st.number_input("Price (yes)", value=150, step=5, key="nfl_pc_yes")
                    _sides = [("Scores (yes)", _p_yes, _px)]
                else:
                    c1, c2, c3 = st.columns(3)
                    _default = max(0.5, round(float(_r["Proj"]) - 0.5) + 0.5)
                    _line = c1.number_input("Line", value=_default, step=0.5, key="nfl_pc_line")
                    _po_px = c2.number_input("Over price", value=-110, step=5, key="nfl_pc_over")
                    _pu_px = c3.number_input("Under price", value=-110, step=5, key="nfl_pc_under")
                    _po = p_over(market, _r["Proj"], _line, _spreads)
                    _sides = [(f"Over {_line:g}", _po, _po_px),
                              (f"Under {_line:g}", None if _po is None else 1 - _po, _pu_px)]
                _out = []
                for _lab, _p, _price in _sides:
                    _a = _vl.assess(_p, _price, _stk[0] or None, _stk[1], _stk[2]) if _p is not None else None
                    _out.append({
                        "Bet": _lab,
                        "Model": "\u2014" if _p is None else f"{100 * _p:.1f}%",
                        "Fair": _mm.fmt_american(_mm.fair_american(_p)) if _p is not None else "\u2014",
                        "Price": _mm.fmt_american(int(_price)),
                        "Edge": f"{100 * _a['edge']:+.1f}" if _a else "\u2014",
                        "EV / $100": f"{_a['ev_per_100']:+.2f}" if _a else "\u2014",
                        "Stake": (f"${_a['stake']:.2f}" if _a and _a.get("stake") else "\u2014"),
                        "Value": "\u2705" if _a and _a["value"] else "",
                    })
                st.dataframe(_out, hide_index=True, width="stretch", key="nfl_pc_table")
                _sp = _spreads.get(market)
                if market != "Anytime TD":
                    st.caption(
                        (f"Projection {_r['Proj']:g}. Game-to-game scatter for {market.lower()} "
                         + (f"measured at {100 * _sp['cv']:.0f}% of the mean" if _sp and _sp["kind"] == "yards"
                            else f"measured as a negative binomial (size {_sp.get('size')})" if _sp
                            else "NOT measured yet \u2014 no chance shown")
                         + (f" over {_sp['games']} player-games." if _sp else ".")
                         + " These chances are not yet graded against outcomes, and the "
                           "yardage projections test within noise of a season average \u2014 "
                           "price them accordingly."))

        st.caption(
            f'League baselines measured from {league.get("team_games", 0)} team-games '
            f'this season: {league.get("points_pg")} points and {league.get("td_pg")} '
            f'offensive touchdowns a game, {league.get("ypc")} yards a carry, '
            f'{league.get("yards_per_target")} a target, '
            f'{(league.get("catch_rate") or 0) * 100:.0f}% catch rate. '
            f'Rebuilt every night from real box scores — nothing here is a '
            f'constant somebody typed in. Built {payload.get("generated_at_et")} ET.')

footer()
