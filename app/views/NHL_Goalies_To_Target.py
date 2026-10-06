"""NHL — Goalies to Target.

Hockey's Pitchers to Target: every goalie who could start tonight, the
one expected to give up the most goals first, with the shooters facing
him.

Expected goals against = the shots the model expects the opponent to put
on net x (1 - his save rate, last season + this, shrunk toward the
league by a fitted prior) — the same numbers the saves props use
(engines/nhl_model). The game model's projected goals for the team he
faces rides beside it as the cross-check. Built nightly; this page fits
nothing and calls nothing.
"""
import pandas as pd
import streamlit as st

from styles.kc_theme import COLOR, card, footer, how_to_read, page_header
from engines.slate_guard import load_slate, payload_field, staleness_note, today_for
from engines import edge_boards as eb
from engines import model_view as mv

page_header("Goalies to Target", "Who gives up the most tonight — and who is shooting at him",
            eyebrow="NHL", align="left")


@st.cache_data(ttl=900, show_spinner=False)
def _load(day):
    games, _sd, _cur = load_slate("nhl")
    return games, payload_field("nhl", "model")


_today = today_for("nhl")
games, model = _load(_today)
goal_rows = eb.nhl_goal_rows(games, model) if model else []
rows = eb.nhl_goalie_rows(games, model, goal_rows) if model else []

how_to_read([
    ("Exp GA", "Goals the model expects him to allow tonight: expected shots against x "
               "(1 - his save rate). Higher = a better goalie to target with goal, point "
               "and team-total overs."),
    ("SV% (model)", "His save rate, last season + this, pulled toward the league average "
                    "when his sample is small. vs lg = how many saves per 1,000 shots he is "
                    "above (+) or below (-) the league."),
    ("Shots against", "Shots on goal the model expects the opponent to take tonight."),
    ("Opp goals (game)", "The game model's projected goals for the team he faces — "
                         "the team-level cross-check."),
    ("Crease", "Starts in his team's last few games. LIKELY = most recent starts; SPLIT = "
               "tied, so either could start. Neither is a confirmation — check the "
               "morning skate."),
    ("Shooters facing him", "The three opposing skaters with the best chance to score "
                            "tonight (Goal Edge)."),
])

if not rows:
    _n = staleness_note("nhl", _today)
    st.info(_n or "Goalies to Target fills in after the nightly builds tonight's NHL model.")
    footer()
    st.stop()

likely_only = st.toggle("Likely or split starters only", value=True, key="gt_likely")
show = [r for r in rows if r["likely"] or r["split"]] if likely_only else rows

with card("gt_board"):
    st.markdown(f'<div class="pf-card-title" style="color:{COLOR["gold"]};">'
                f'Goalies to target tonight</div>', unsafe_allow_html=True)

    def _f(x, nd=2):
        return "—" if x is None else f"{x:.{nd}f}"

    df = pd.DataFrame([{
        "Goalie": r["goalie"], "Team": r["team"], "Exp GA": _f(r["exp_ga"]),
        "SV% (model)": _f(r["sv_model"], 3),
        "vs lg": ("—" if r["sv_vs_league"] is None else f"{r['sv_vs_league']:+.1f}"),
        "Shots against": _f(r["exp_sa"], 1), "Opp": r["opp"],
        "Shooters facing him": r["shooters"] or "—",
        "Crease": ("LIKELY · " if r["likely"] else ("SPLIT · " if r["split"] else ""))
                  + (r["crease"] or "—"),
        "Opp goals (game)": _f(r["opp_goals"]),
        "SV% season": _f(r["sv_season"], 3), "SV% L5": _f(r["sv_l5"], 3),
        "GAA": _f(r["gaa"]), "Game": r["game"],
    } for r in show])
    ga = [r["exp_ga"] for r in show if r["exp_ga"] is not None]
    lo, hi = (min(ga), max(ga)) if ga else (0, 1)

    def _paint(frame):
        out = pd.DataFrame("", index=frame.index, columns=frame.columns)
        for i in frame.index:
            x = show[i]["exp_ga"]
            if x is not None and hi > lo:
                t = (x - lo) / (hi - lo)
                # the most goals against = the brightest target
                if t >= 0.75:
                    out.at[i, "Exp GA"] = (f"background-color:{COLOR['accent']}; "
                                           f"color:{COLOR['bg']}; font-weight:700;")
                elif t >= 0.5:
                    out.at[i, "Exp GA"] = f"background-color:{COLOR['accent_dim']}; font-weight:600;"
            v = show[i]["sv_vs_league"]
            if v is not None:
                out.at[i, "vs lg"] = (f"color:{COLOR['accent']}; font-weight:700;" if v < 0
                                      else f"color:{COLOR['error']}; font-weight:700;")
        return out

    st.dataframe(mv.painted(df, _paint), hide_index=True, width="stretch", key="gt_tab")
    st.caption("Exp GA: brighter = more goals expected against him (a better target). vs lg: "
               "cyan = below the league's save rate (good to shoot at), red = above it. "
               "The saves model is tested at TEAM level on last season (team saves); his "
               "personal save rate is shrunk toward the league so a few hot or cold starts "
               "cannot carry it.")

footer()
