"""NHL — Goal Edge.

Hockey's HR Edge: every skater on tonight's slate ranked by his chance
to score, with what drives it beside it — his expected shots, the goalie
he is likely shooting at, his recent ice time, his team's goal
environment tonight, and what this opponent allows to his position.

The chance is the NHL model's goal line (engines/nhl_model) run through
that line's own walk-forward record — what calls like it DELIVERED on
games the model had not seen (engines/edge_boards). Built nightly; this
page fits nothing and calls nothing.
"""
import pandas as pd
import streamlit as st

from styles.kc_theme import COLOR, card, footer, how_to_read, page_header
from engines.slate_guard import load_slate, payload_field, staleness_note, today_for
from engines import defense_matchup as dm
from engines import edge_boards as eb
from engines import model_math as mm
from engines import model_view as mv
from engines import nhl_model as nm
from engines import value as vl

page_header("Goal Edge", "Every skater's chance to score tonight — and why",
            eyebrow="NHL", align="left")


@st.cache_data(ttl=900, show_spinner=False)
def _load(day):
    games, slate_date, _cur = load_slate("nhl")
    return games, payload_field("nhl", "model")


_today = today_for("nhl")
games, model = _load(_today)
rows = eb.nhl_goal_rows(games, model) if model else []

how_to_read([
    ("Goal %", "His chance to score at least once tonight — what calls like this "
               "have actually delivered on games the model had not seen. Colour = the "
               "chance band."),
    ("Worth it at", "The price that breaks even at that chance. Your book's anytime-goal "
                    "price must be BETTER (bigger plus) than this to be value."),
    ("Exp G / Exp SOG", "Expected goals and shots tonight: his rate (this season + last) "
                        "x his recent ice time x his team's environment tonight."),
    ("TOI recent / norm", "Minutes over his last games vs. the minutes his rate is built on. "
                          "Up = more ice time = more chances (already in the number)."),
    ("Goal env", "How many goals the model expects his team to score tonight vs. its norm "
                 "(+8% = a good night to score)."),
    ("Goalie / SV%", "The goalie he is most likely shooting at (most recent starts — not "
                     "a confirmation) and that goalie's save rate. Lower = better for the "
                     "shooter. See Goalies to Target."),
    ("Def vs pos", "What tonight's opponent allows in GOALS to his position. Goal rankings "
                   "measured as mostly noise — a tiebreaker, not a reason."),
])

if not rows:
    _n = staleness_note("nhl", _today)
    st.info(_n or "Goal Edge fills in after the nightly builds tonight's NHL model.")
    footer()
    st.stop()

_stk = mv.staking_controls("nhl_goal_edge")
c1, c2 = st.columns([2, 1])
gsel = c1.selectbox("Game", ["All games"] + sorted({r["game"] for r in rows}),
                    key="ge_game")
fwd_only = c2.toggle("Forwards only", value=True, key="ge_fwd")
show = [r for r in rows if (gsel == "All games" or r["game"] == gsel)
        and (not fwd_only or nm.group(r["pos"]) == "F")]
top_n = st.slider("How many", 10, max(10, len(show)), min(30, max(10, len(show))),
                  step=5, key="ge_n") if len(show) > 10 else len(show)
show = show[:top_n]

with card("ge_board"):
    st.markdown(f'<div class="pf-card-title" style="color:{COLOR["gold"]};">'
                f'Most likely to score tonight</div>', unsafe_allow_html=True)


    def _pct(x):
        return "—" if x is None else f"{100 * x:.0f}%"


    def _env(x):
        return "—" if x is None else f"{100 * (x - 1):+.0f}%"


    df = pd.DataFrame([{
        "Player": r["player"], "Pos": r["pos"], "Goal %": _pct(r["chance"]),
        "Worth it at": r["fair"], "Def vs pos": dm.badge(r["card_g"]),
        "Exp G": r["exp_g"], "Exp SOG": r["exp_sog"], "Team": r["team"], "Opp": r["opp"],
        "Goalie": r["goalie"] or "—",
        "Goalie SV%": (f"{r['goalie_sv']:.3f}" if r["goalie_sv"] is not None else "—"),
        "Goal env": _env(r["goal_env"]),
        "TOI recent": r["ice_recent"], "TOI norm": r["ice_norm"],
        "Point %": _pct(r["pts_chance"]),
    } for r in show])

    def _paint(frame):
        out = pd.DataFrame("", index=frame.index, columns=frame.columns)
        for i in frame.index:
            out.at[i, "Goal %"] = mv.chance_css(show[i]["chance"])
            out.at[i, "Def vs pos"] = mv.matchup_css((show[i]["card_g"] or {}).get("tier"))
        return out

    st.dataframe(mv.painted(df, _paint), hide_index=True, width="stretch", key="ge_tab")
    mv.render_chance_legend()
    _t = ((model.get("props_validation") or {}).get("g1") or {})
    _v = ((_t.get("verdict") or {}).get("verdict"))
    st.caption(f"Goal O0.5 tested on last season's games the model had not seen: "
               f"{mv.trust_label(_v)}. Point % is the chance of 1+ point, from the same "
               f"model. NOT in the number: tonight's line combinations and power-play units, "
               f"late scratches, and which goalie actually starts.")

with card("ge_check"):
    st.markdown("**Check a goal at your book's price**")
    k1, k2 = st.columns([3, 1])
    names = [f"{r['player']} ({r['team']})" for r in show]
    i = k1.selectbox("Player", range(len(show)), format_func=lambda j: names[j], key="ge_pick")
    r = show[i]
    price = k2.number_input("Your price", value=int(mm.fair_american(r["chance"]) or 200),
                            step=5, key=f"ge_px_{i}")
    a = vl.assess(r["chance"], price, _stk[0] or None, _stk[1], _stk[2])
    if a:
        tier = mv.edge_tier(a["edge"], a["value"])
        lab, fg, _bg = mv.TIER_STYLE[tier]
        verdict = (f'<span style="color:{fg}; font-weight:800;">{lab}</span>' if tier != "none"
                   else f'<span style="color:{COLOR["error"]}; font-weight:800;">NO VALUE</span>')
        mv.render_verdict_box(tier, (
            f"<b>{r['player']}</b> anytime goal at <b>{mm.fmt_american(int(price))}</b> "
            f"→ <b>{verdict}</b><br>chance <b>{100 * r['chance']:.1f}%</b> · worth it "
            f"at <b>{r['fair']}</b> or better · edge <b>{100 * a['edge']:+.1f} pts</b> "
            f"· EV {a['ev_per_100']:+.2f} per $100"
            + (f" · stake ${a['stake']:.2f}" if a.get("stake") else "")))
    bits = []
    if r["card_g"]:
        bits.append(dm.notice(r["card_g"], "goals", nm.DVP_GROUP_LABELS.get(
            r["card_g"].get("group"), "skaters"), r["opp"]))
    if r["card_sog"]:
        bits.append(dm.notice(r["card_sog"], "shots on goal", nm.DVP_GROUP_LABELS.get(
            r["card_sog"].get("group"), "skaters"), r["opp"]))
    if r["why"]:
        bits.append(f"<b>Why:</b> {r['why']}")
    if bits:
        st.markdown('<div style="font-size:var(--lc-text-small); line-height:1.6;">'
                    + "<br>".join(bits) + "</div>", unsafe_allow_html=True)

footer()
