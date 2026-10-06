"""NFL — TD Edge.

Football's HR Edge: every skill player this week ranked by his chance to
score a touchdown, with what drives it — the points the market implies
for his team, his share of the team's touches, and what this defense
allows in touchdowns to his position.

The chance is the NFL projection's anytime-TD number run through the
nightly prop test's own calibration curve for touchdowns (nfl_prop_check)
— what calls like it DELIVERED on weeks the model had not seen. Built
nightly; this page fits nothing and calls nothing.
"""
import pandas as pd
import streamlit as st

from styles.kc_theme import COLOR, card, footer, how_to_read, page_header
from engines.nfl_week import load_week
from engines import defense_matchup as dm
from engines import edge_boards as eb
from engines import model_math as mm
from engines import model_view as mv
from engines import value as vl

page_header("TD Edge", "Every player's chance to score a touchdown this week — and why",
            eyebrow="NFL", align="left")


@st.cache_data(ttl=900, show_spinner=False)
def _load():
    wk, state = load_week()
    return wk or {}, state


wk, state = _load()
league = wk.get("league") or {}
rows = eb.nfl_td_rows(wk.get("games") or [], league, wk.get("dvp")) if wk else []

how_to_read([
    ("TD %", "His chance to score a rushing or receiving touchdown — what calls like "
             "this delivered on weeks the model had not seen (when the nightly's test has a "
             "record; otherwise the model's own number, and the caption says so)."),
    ("Worth it at", "The anytime-TD price that breaks even at that chance. Your book's price "
                    "must be better."),
    ("TD exp", "Expected touchdowns: the points the market implies for his team, turned "
               "into touchdowns, times his share of the team's scoring chances."),
    ("Touches/G", "Carries + targets a game — the volume a touchdown comes from."),
    ("Def vs pos", "What this defense allows in touchdowns to his position, this season + "
                   "last. SOFT = top quarter of the league."),
    ("Opp TD / RZ rank", "Where the defense ranks in TDs allowed per game and red-zone TD % "
                         "allowed. 1 = best defense, 32 = worst (the one to target)."),
])

if not rows:
    st.info("TD Edge fills in when this week's NFL file is current "
            f"(state: {state}).")
    footer()
    st.stop()

_stk = mv.staking_controls("nfl_td_edge")
c1, c2 = st.columns([2, 1])
teams = sorted({r["team"] for r in rows} | {r["opp"] for r in rows})
tsel = c1.selectbox("Team", ["All teams"] + teams, key="td_team")
pos = c2.multiselect("Positions", ["RB", "WR", "TE", "QB"], default=["RB", "WR", "TE"],
                     key="td_pos")
show = [r for r in rows if (tsel == "All teams" or tsel in (r["team"], r["opp"]))
        and (not pos or str(r["pos"]) in pos)]
top_n = st.slider("How many", 10, max(10, len(show)), min(40, max(10, len(show))), step=5,
                  key="td_n") if len(show) > 10 else len(show)
show = show[:top_n]


def _pct(x):
    return "—" if x is None else f"{100 * x:.0f}%"


def _rank(r, k):
    return "—" if r.get(k) is None else f"{r[k]}/{r.get('of') or 32}"


with card("td_board"):
    st.markdown(f'<div class="pf-card-title" style="color:{COLOR["gold"]};">'
                f'Most likely to score this week</div>', unsafe_allow_html=True)
    df = pd.DataFrame([{
        "Player": r["player"], "Pos": r["pos"], "TD %": _pct(r["chance"]),
        "Worth it at": r["fair"], "Def vs pos": dm.badge(r["card_td"]),
        "TD exp": r["td_exp"], "Touches/G": r["touches"],
        "Team": r["team"], "Opp": r["opp"], "Implied pts": r["implied"],
        "Opp TD rank": _rank(r, "opp_td_allowed_rank"), "Opp RZ rank": _rank(r, "opp_rz_rank"),
        "Status": r["status"],
    } for r in show])

    def _paint(frame):
        out = pd.DataFrame("", index=frame.index, columns=frame.columns)
        for i in frame.index:
            out.at[i, "TD %"] = mv.chance_css(show[i]["chance"])
            out.at[i, "Def vs pos"] = mv.matchup_css((show[i]["card_td"] or {}).get("tier"))
        return out

    st.dataframe(mv.painted(df, _paint), hide_index=True, width="stretch", key="td_tab")
    mv.render_chance_legend()
    v = (((league.get("prop_validation") or {}).get("td") or {}).get("verdict") or {}).get("verdict")
    basis = ("delivered chances (calibrated on weeks the model had not seen)"
             if any(r["basis"] == "delivered" for r in show) else
             "the model's own chances (no graded record yet)")
    st.caption(f"Anytime TD tested week by week against the player's own scoring rate: "
               f"{mv.trust_label(v)}. Shown: {basis}. Opp ranks: 1 = stingiest, last = "
               f"most generous. Out players are left off; check Status on game day.")

with card("td_check"):
    st.markdown("**Check a TD at your book's price**")
    k1, k2 = st.columns([3, 1])
    names = [f"{r['player']} ({r['team']})" for r in show]
    i = k1.selectbox("Player", range(len(show)), format_func=lambda j: names[j], key="td_pick")
    r = show[i]
    price = k2.number_input("Your price", value=int(mm.fair_american(r["chance"]) or 150),
                            step=5, key=f"td_px_{i}")
    a = vl.assess(r["chance"], price, _stk[0] or None, _stk[1], _stk[2])
    if a:
        tier = mv.edge_tier(a["edge"], a["value"])
        lab, fg, _bg = mv.TIER_STYLE[tier]
        verdict = (f'<span style="color:{fg}; font-weight:800;">{lab}</span>' if tier != "none"
                   else f'<span style="color:{COLOR["error"]}; font-weight:800;">NO VALUE</span>')
        mv.render_verdict_box(tier, (
            f"<b>{r['player']}</b> anytime TD at <b>{mm.fmt_american(int(price))}</b> → "
            f"<b>{verdict}</b><br>chance <b>{100 * r['chance']:.1f}%</b> · worth it at "
            f"<b>{r['fair']}</b> or better · edge <b>{100 * a['edge']:+.1f} pts</b> "
            f"· EV {a['ev_per_100']:+.2f} per $100"
            + (f" · stake ${a['stake']:.2f}" if a.get("stake") else "")))
    if r["card_td"]:
        grp = r["card_td"].get("group")
        st.markdown(f'<div style="font-size:var(--lc-text-small); line-height:1.6;">'
                    f'{dm.notice(r["card_td"], "touchdowns", eb.NFL_GROUP_LABELS.get(grp, grp), r["opp"])}'
                    f'</div>', unsafe_allow_html=True)

footer()
