"""NHL — Player of the Day.

Built the way MLB's Player of the Day is built (one target, strict gates,
matchup kept in proportion, graded every night), on the NHL model's
tested 1+ point line. engines/edge_boards.nhl_player_of_the_day says why
each rule is there. Built nightly; this page fits nothing and calls
nothing. The pick is logged before puck drop and graded off the box
score (data/top_plays/nhl_potd.json), and the Results scorecard judges it.
"""
import pandas as pd
import streamlit as st

from styles.kc_theme import COLOR, card, footer, how_to_read, page_header, status_banner
from engines.slate_guard import load_slate, payload_field, staleness_note, today_for
from engines import defense_matchup as dm
from engines import edge_boards as eb
from engines import model_math as mm
from engines import model_view as mv
from engines import nhl_model as nm
from engines import top_plays_board as tpb
from engines import value as vl

page_header("NHL Player of the Day", "Tonight's best 1+ point play — and the record behind it",
            eyebrow="NHL", align="left")


@st.cache_data(ttl=900, show_spinner=False)
def _load(day):
    games, _slate_date, _cur = load_slate("nhl")
    return games, payload_field("nhl", "model")


_today = today_for("nhl")
games, model = _load(_today)
pick, cands, note = eb.nhl_player_of_the_day(games, model) if model else (None, [], None)

status_banner(
    "info",
    "One pick: the skater most likely to record a POINT tonight (goal or assist). "
    f"Eligible only with {eb.POTD_MIN_GP}+ games across this season and last, only if he "
    "played his team's last game, and only while the 1+ point line keeps beating the "
    "skater's own hit rate on games the model had not seen. The chance shown is what calls "
    "like it actually delivered. The matchup (his team's expected goals tonight, his ice "
    "time) is already inside that chance at the size it measured, so nothing is added on "
    "top. Judge it over weeks on the record below, not on one night.")

how_to_read([
    ("Point %", "His chance of 1+ point tonight, as delivered by calls like it on unseen "
                "games. Colour = chance band."),
    ("Worth it at", "The price that breaks even at that chance. Your book's 1+ point price "
                    "must be BETTER than this to be value; most nights a top pick is priced "
                    "near -200, so the edge is usually in shopping the price."),
    ("PP", "Power-play unit by minutes and PP minutes a game. "
           + nm.pp_note((model or {}).get("toi"))),
])

if not pick:
    _n = staleness_note("nhl", _today)
    st.info(_n or note or "Player of the Day fills in after the nightly builds tonight's "
                          "NHL model.")
else:
    _stk = mv.staking_controls("nhl_potd")
    with card("potd_pick"):
        st.markdown(
            f'<div class="pf-card-title" style="color:{COLOR["gold"]};">{pick["player"]} '
            f'— {pick["team"]} vs {pick["opp"]}</div>'
            f'<div class="pf-card-subtitle">{pick.get("time") or ""} · {pick["pos"] or ""} · '
            f'{pick["gp"]} games (this season + last)</div>', unsafe_allow_html=True)
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("1+ point", f"{100 * pick['chance']:.1f}%")
        c2.metric("Worth it at", pick["fair"])
        c3.metric("Exp points", pick.get("exp_pts"))
        _pp = pick.get("pp") or {}
        _m = _pp.get("l5") if _pp.get("l5") is not None else _pp.get("season")
        c4.metric("PP", "—" if _m is None else
                  (f"{_pp.get('unit')} · {_m:.1f}" if _pp.get("unit") not in (None, "-")
                   else f"{_m:.1f}"))
        bits = []
        if pick.get("card_pts"):
            bits.append(dm.notice(pick["card_pts"], "points", nm.DVP_GROUP_LABELS.get(
                pick["card_pts"].get("group"), "skaters"), pick["opp"]))
        if pick.get("why"):
            bits.append(f"<b>Why:</b> {pick['why']}")
        if bits:
            st.markdown('<div style="font-size:var(--lc-text-small); line-height:1.6;">'
                        + "<br>".join(bits) + "</div>", unsafe_allow_html=True)
        k1, _k2 = st.columns([1, 2])
        price = k1.number_input("Your book's 1+ point price",
                                value=int(mm.fair_american(pick["chance"]) or -150), step=5,
                                key="potd_px")
        a = vl.assess(pick["chance"], price, _stk[0] or None, _stk[1], _stk[2])
        if a:
            tier = mv.edge_tier(a["edge"], a["value"])
            lab, fg, _bg = mv.TIER_STYLE[tier]
            verdict = (f'<span style="color:{fg}; font-weight:800;">{lab}</span>'
                       if tier != "none" else
                       f'<span style="color:{COLOR["error"]}; font-weight:800;">NO VALUE</span>')
            mv.render_verdict_box(tier, (
                f"<b>{pick['player']}</b> 1+ point at <b>{mm.fmt_american(int(price))}</b> → "
                f"<b>{verdict}</b><br>chance <b>{100 * pick['chance']:.1f}%</b> · worth it at "
                f"<b>{pick['fair']}</b> or better · edge <b>{100 * a['edge']:+.1f} pts</b> · "
                f"EV {a['ev_per_100']:+.2f} per $100"
                + (f" · stake ${a['stake']:.2f}" if a.get("stake") else "")))

    with card("potd_next"):
        st.markdown(f'<div class="pf-card-title" style="color:{COLOR["gold"]};">'
                    f'Next in line</div>', unsafe_allow_html=True)
        df = pd.DataFrame([{
            "Player": c["player"], "Point %": f"{100 * c['chance']:.1f}%",
            "Worth it at": c["fair"], "Exp Pts": c.get("exp_pts"), "Team": c["team"],
            "Opp": c["opp"], "Time": c.get("time") or "—"} for c in cands])

        def _paint(frame):
            out = pd.DataFrame("", index=frame.index, columns=frame.columns)
            for i in frame.index:
                out.at[i, "Point %"] = mv.chance_css(cands[i]["chance"])
            return out
        st.dataframe(mv.painted(df, _paint), hide_index=True, width="stretch", key="potd_tab")

# THE RECORD
with card("potd_record"):
    st.markdown(f'<div class="pf-card-title" style="color:{COLOR["gold"]};">The record</div>',
                unsafe_allow_html=True)
    plays = tpb.load("nhl_potd").get("plays") or []
    sm = tpb.summary(plays)["all"]
    if not sm["n"]:
        st.caption("Graded from the first night this pick is logged. Every pick is recorded "
                   "before puck drop and graded off the box score.")
    else:
        st.markdown(f"**{sm['hits']} of {sm['n']}** picks recorded a point "
                    f"({100 * sm['hit_rate']:.1f}%) against **{100 * sm['promised']:.1f}%** "
                    f"promised. The Results scorecard says whether that gap is real.")
        recent = sorted(plays, key=lambda p: p.get("date") or "", reverse=True)[:15]
        st.dataframe(pd.DataFrame([{
            "Date": p.get("date"), "Player": p.get("player"),
            "Promised": f"{100 * p['p_cal']:.1f}%",
            "Result": p.get("result") or "pending",
            "Points": p.get("actual")} for p in recent]),
            hide_index=True, width="stretch", key="potd_rec")

footer()
