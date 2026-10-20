"""Bet Log (10-20) — the bets you actually placed, at the price you got,
graded when they settle. The test no backtest can run: does the model
beat YOUR book on the bets YOU pick (engines/bet_log)."""
from datetime import datetime

import pandas as pd
import streamlit as st

from styles.kc_theme import COLOR, card, footer, page_header
from engines import bet_log as bl
from engines import bet_log_ui as blu
from engines import model_view as mv

page_header("Bet Log", "Every bet you placed — graded, and scored against your book",
            eyebrow="Your record", align="left")
s = blu.state()
bets = s["bets"]

if s["src"] == "github":
    st.caption("Saved to your log — it survives deploys and follows you to any device.")
else:
    st.warning(((s["err"] + " ") if s["err"] else "")
               + "Bets here last for this session only — the saved log isn't switched on for "
                 "this site yet. Download the log below before you leave, upload it next time.")
if s["err"] and s["src"] == "github":
    st.warning(s["err"])
if st.button("Reload", key="blog_reload"):
    blu.state(force=True)
    st.rerun()


def _amer(p):
    return "—" if p is None else (f"+{p}" if p > 0 else str(p))


def _pct(p):
    return "—" if p is None else f"{100 * p:.0f}%"


# ---------------- the scoreboard ----------------
sm = bl.summary(bets)
with card("blog_sum"):
    st.markdown(f'<div class="pf-card-title" style="color:{COLOR["gold"]};">How you\'re doing</div>',
                unsafe_allow_html=True)
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Record", f"{sm['won']}-{sm['lost']}" + (f"-{sm['push']}" if sm["push"] else ""))
    c2.metric("Profit", f"${sm['profit']:+,.2f}")
    c3.metric("ROI", "—" if sm["roi"] is None else f"{100 * sm['roi']:+.1f}%")
    c4.metric("Open", sm["open"])
    lines = []
    if sm["n_with_chance"]:
        lines.append(f"Our chances said <b>{sm['expected_wins']:.1f}</b> of these "
                     f"{sm['n_with_chance']} would hit; <b>{sm['wins_with_chance']}</b> did.")
    vb = sm["vs_book"]
    if vb and sm["vs_book_ready"]:
        lab, fg, _bg, _bd = mv.TRUST_STYLE.get(vb["verdict"], mv.TRUST_STYLE[None])
        lines.append(f'Model vs your book, same bets: <b style="color:{fg};">{lab}</b> '
                     f'(z {vb["z"]}) — "beats" means our chances called your bets better than '
                     f'the price you were paid did.')
    elif sm["n_with_chance"]:
        lines.append(f"Model vs your book: needs {bl.MIN_VERDICT_N} graded bets with our chance "
                     f"on them before it means anything (you have {sm['n_with_chance']}).")
    if sm["clv_n"]:
        good = sm["clv"] > 0
        lines.append(f'Closing line: you beat the close on <b>{sm["clv_beat"]} of '
                     f'{sm["clv_n"]}</b>, by <b style="color:'
                     f'{COLOR["stat_high"] if good else COLOR["error"]};">'
                     f'{100 * sm["clv"]:+.1f} pts</b> of chance on average — the earliest honest '
                     f'sign of an edge, long before profit settles down.')
    else:
        lines.append("Closing line: type the price at game time when you grade a bet — beating "
                     "it consistently is the earliest real sign of an edge.")
    st.markdown(f'<div style="font-size:var(--lc-text-body); line-height:1.7;">'
                + "<br>".join(lines) + "</div>", unsafe_allow_html=True)
    if sm["graded"]:
        rows = []
        for field, name in (("kind", "Type"), ("tier", "Call"), ("sport", "Sport")):
            for v, x in bl.by([b for b in bets if b.get("result")], field).items():
                rows.append({"Split": name, "Group": {"None": "—"}.get(v, v).upper()
                             if field == "tier" else v,
                             "Record": f"{x['won']}-{x['lost']}" + (f"-{x['push']}" if x["push"] else ""),
                             "Profit": x["profit"], "ROI": x["roi"],
                             "Expected / won": (f"{x['expected_wins']:.1f} / {x['wins_with_chance']}"
                                                if x["expected_wins"] is not None else "—")})
        df = pd.DataFrame(rows)

        def _paint(frame):
            o = pd.DataFrame("", index=frame.index, columns=frame.columns)
            for k in frame.index:
                p = frame.at[k, "Profit"]
                col = COLOR["stat_high"] if p > 0 else (COLOR["error"] if p < 0 else COLOR["text_muted"])
                o.at[k, "Profit"] = o.at[k, "ROI"] = f"color: {col}; font-weight: 700;"
            return o
        show = df.copy()
        show["Profit"] = [f"${p:+,.2f}" for p in df["Profit"]]
        show["ROI"] = ["—" if r is None or r != r else f"{100 * r:+.1f}%" for r in df["ROI"]]
        st.dataframe(mv.painted(show, lambda f: _paint(df)), hide_index=True, width="stretch",
                     key="blog_split")
    st.caption("Small samples swing hard: 30 bets says almost nothing about a +EV bettor, a few "
               "hundred start to. Judge the closing line and model-vs-book first, profit last.")

# ---------------- grade open bets ----------------
open_b = [b for b in bets if not b.get("result")]
with card("blog_open"):
    st.markdown(f'<div class="pf-card-title" style="color:{COLOR["gold"]};">Grade a bet '
                f'({len(open_b)} open)</div>', unsafe_allow_html=True)
    if not open_b:
        st.caption("Nothing open. Log bets from the parlay slip, the Simulator, or below.")
    else:
        lab = {b["id"]: f"{b['placed'][5:]} · {b['sport']} · {b['desc'][:70]} · {_amer(b['price'])}"
               for b in open_b}
        pick = st.selectbox("Bet", [b["id"] for b in open_b], format_func=lambda i: lab[i],
                            key="blog_pick")
        b = next(x for x in open_b if x["id"] == pick)
        st.caption(f"Our chance {_pct(b.get('chance'))} · break-even {_pct(bl.break_even(b['price']))}"
                   f" · stake ${b['stake']:.2f} · call {(b.get('tier') or '—').upper()}")
        close = st.number_input("Price at game time (optional)", value=None, step=5, format="%d",
                                key=f"blog_close_{pick}",
                                help="The same bet's price just before it started. Leave blank "
                                     "if you don't have it — it's left out, never counted as 0.")
        c1, c2, c3, c4 = st.columns(4)
        for col, res, name in ((c1, "won", "Won"), (c2, "lost", "Lost"), (c3, "push", "Push"),
                               (c4, "delete", "Delete")):
            if col.button(name, key=f"blog_{res}_{pick}"):
                if res == "delete":
                    blu.write(bl.remove(bets, pick), "delete")
                else:
                    blu.write(bl.upsert(bets, bl.settle(b, res, close)), f"grade {res}")
                st.rerun()

# ---------------- log a bet by hand ----------------
with card("blog_add"):
    st.markdown(f'<div class="pf-card-title" style="color:{COLOR["gold"]};">Log a bet by hand</div>',
                unsafe_allow_html=True)
    c1, c2 = st.columns(2)
    sport = c1.selectbox("Sport", ["NBA", "NFL", "NHL", "MLB", "WNBA", "Other"], key="blog_sport")
    kind = c2.selectbox("Type", list(bl.KINDS), key="blog_kind",
                        format_func=lambda k: {"sgp": "same-game parlay"}.get(k, k))
    desc = st.text_input("What you bet", key="blog_desc", placeholder="e.g. Brunson Over 27.5 pts")
    c1, c2, c3 = st.columns(3)
    ch = c1.number_input("Our chance % (from the site)", min_value=0.0, max_value=100.0,
                         value=None, step=1.0, key="blog_ch")
    price = c2.number_input("Price", value=None, step=5, format="%d", key="blog_price")
    stake = c3.number_input("Stake $", min_value=0.0, value=10.0, step=1.0, key="blog_stake")
    if st.button("Log it", key="blog_add_go"):
        nb = bl.new_bet(sport, kind, desc.strip() or "bet", None if ch is None else ch / 100.0,
                        price, stake)
        if nb is None or not desc.strip():
            st.warning("A description and a real price (like -110 or +150) are needed.")
        else:
            blu.add(nb)
            st.rerun()
    st.caption("Leave 'our chance' blank if the site had no number on it — that bet still counts "
               "for profit, but not for model-vs-book.")

# ---------------- every bet ----------------
with card("blog_all"):
    st.markdown(f'<div class="pf-card-title" style="color:{COLOR["gold"]};">Every bet</div>',
                unsafe_allow_html=True)
    if bets:
        df = pd.DataFrame([{
            "Placed": b["placed"], "Sport": b["sport"], "Bet": b["desc"],
            "Price": _amer(b["price"]), "Our chance": _pct(b.get("chance")),
            "Stake": f"${b['stake']:.2f}", "Result": (b.get("result") or "open").upper(),
            "P/L": "—" if bl.profit(b) is None else f"${bl.profit(b):+,.2f}",
            "Close": _amer(b.get("close"))} for b in bets])

        def _paint_all(frame):
            o = pd.DataFrame("", index=frame.index, columns=frame.columns)
            for k in frame.index:
                r = bets[k].get("result")
                if r == "won":
                    o.at[k, "Result"] = o.at[k, "P/L"] = f"color: {COLOR['stat_high']}; font-weight: 700;"
                elif r == "lost":
                    o.at[k, "Result"] = o.at[k, "P/L"] = f"color: {COLOR['error']}; font-weight: 700;"
                if bets[k].get("chance") is not None:
                    o.at[k, "Our chance"] = mv.chance_css(bets[k]["chance"])
                c = bl.clv(bets[k])
                if c is not None:
                    o.at[k, "Close"] = (f"color: {COLOR['stat_high'] if c > 0 else COLOR['error']};")
            return o
        st.dataframe(mv.painted(df, _paint_all), hide_index=True, width="stretch", key="blog_tab")
    st.download_button("Download the log", bl.dump(bets),
                       file_name=f"bet_log_{datetime.now():%Y%m%d}.json", mime="application/json",
                       key="blog_dl")
    up = st.file_uploader("Upload a log (merges with this one)", type=["json"], key="blog_up")
    if up is not None and st.button("Merge it in", key="blog_up_go"):
        merged = bets
        for b in bl.parse(up.getvalue().decode("utf-8", "replace")):
            if b["id"] not in {x["id"] for x in merged}:
                merged = bl.upsert(merged, b)
        blu.write(merged, "merge upload")
        st.rerun()

footer()
