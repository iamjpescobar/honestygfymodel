"""NBA Props (10-20) — every player on the slate for one stat: projected
minutes and mean, his usual line, the chance over it (delivered on last
season's unseen games), what it's worth, your book's price -> BET /
CHECK / SKIP through the site's one guard, and his trend chart.
Reads engines/nba_view; fits nothing.
"""
import pandas as pd
import streamlit as st

from styles.kc_theme import COLOR, card, footer, page_header
from engines import availability as av
from engines import bet_finder as bf
from engines import live_injuries as _li
from engines import model_math as mm
from engines import model_view as mv
from engines import nba_model as nm
from engines import nba_view as nv
from engines.live_sync import sync_latest_button

page_header("NBA Props", "Projections, his line, the chance — type your price",
            eyebrow="NBA", align="left")
sync_latest_button(key="sync_nba_props", include_data_package=True)
games, model, _pget = nv.load()
_li.render_note("nba")
if not games or not model:
    st.info("No NBA projections yet — they appear after the nightly build, once the "
            "NBA prior season workflow has run.")
    footer()
    st.stop()

_stk = mv.staking_controls("nba_props")
ss = st.session_state
ver = nv.verdicts(model)

c1, c2, c3 = st.columns(3)
labels = sorted({f"{g.get('away_abbr')} @ {g.get('home_abbr')}" for g in games})
gsel = c1.selectbox("Game", ["All games"] + labels, key="nbap_game")
_stats = [(s_, l_) for s_, l_ in nm.PAGE_STATS if s_ in nm.LABEL and (
    s_ != "q1pts" or ((model or {}).get("test") or {}).get("q1pts"))]
slab = c2.selectbox("Stat", [lab for _s, lab in _stats], key="nbap_stat")
stat = next(s for s, lab in _stats if lab == slab)
side = c3.segmented_control("Side", ["Over", "Under"], default="Over", key="nbap_side") or "Over"

rows = [r for r in nv.all_props(games) if gsel == "All games" or r["game"] == gsel]
rows = [r for r in rows if not av.is_out(r.get("status"))]
rows.sort(key=lambda r: -((r.get("mu") or {}).get(stat) or 0))
rows = rows[:60]

with card("nbap_board"):
    st.markdown(f'<div class="pf-card-title" style="color:{COLOR["gold"]};">{slab} — '
                f'{len(rows)} players · tested: {mv.trust_label(ver.get(stat))}</div>',
                unsafe_allow_html=True)
    base = pd.DataFrame([{
        "Player": r["name"] + (f" ⚠ {r['status']}" if av.maybe_label(r.get("status")) else "")
        + nv.tags(r),
        "Team": r["team"], "Matchup": nv.grade(r, stat, side), "Min": round(r["min"]),
        "Proj": round(r["mu"][stat], 1),
        "Line": nv.his_line(r, stat), "Your price": None} for r in rows])
    ed = st.data_editor(base, key=f"nbap_ed_{gsel}_{stat}", hide_index=True, width="stretch",
                        disabled=["Player", "Team", "Matchup", "Min", "Proj"],
                        column_config={
                            "Line": st.column_config.NumberColumn(
                                help="Starts at his last-10 average set at the half point (how "
                                     "books hang a line). Change it to your book's line.",
                                step=0.5, format="%.1f"),
                            "Your price": st.column_config.NumberColumn(
                                help="Your book's price for this side, e.g. -115.", step=5,
                                format="%d")})
    out, res = [], []
    for i, r in enumerate(rows):
        line = ed.at[i, "Line"]
        if line is None or pd.isna(line):
            continue
        ch, raw, sup = nv.chance(r, stat, float(line), model, side)
        if ch is None:
            continue
        out.append(dict(r, line=float(line), chance=ch, raw=raw, support=sup))
        j = bf.judge(ch, ed.at[i, "Your price"], _stk, None, sup)
        if j:
            res.append(dict(out[-1], price=bf.valid_price(ed.at[i, "Your price"]), **j))
    if out:
        show = pd.DataFrame([{
            "Player": x["name"], "Bet": f"{side} {x['line']:g}",
            "Chance": f"{100 * x['chance']:.0f}%", "Matchup": nv.grade(x, stat, side),
            "Worth it at": mm.fmt_american(mm.fair_american(x["chance"]))
            if 0 < x["chance"] < 1 else "—",
            "Proj": round(x["mu"][stat], 1), "Min": round(x["min"]), "Game": x["game"]}
            for x in out])

        def _paint(frame):
            o = pd.DataFrame("", index=frame.index, columns=frame.columns)
            for k in frame.index:
                o.at[k, "Chance"] = mv.chance_css(out[k]["chance"])
                o.at[k, "Matchup"] = mv.matchup_css(frame.at[k, "Matchup"])
            return o
        st.dataframe(mv.painted(show, _paint), hide_index=True, width="stretch",
                     key=f"nbap_ch_{gsel}_{stat}")
        mv.render_chance_legend()
    if res:
        res.sort(key=lambda x: (bf.CALL_ORDER[x["tier"]], -x["edge"]))
        n_bet = sum(1 for x in res if x["call"] == "BET")
        st.markdown(f"**{n_bet} BET{'s' if n_bet != 1 else ''}** out of {len(res)} priced")
        rdf = pd.DataFrame([{
            "Call": bf.TIER_LABEL[x["tier"]], "Player": x["name"],
            "Bet": f"{side} {x['line']:g} {slab}", "Your price": mm.fmt_american(x["price"]),
            "Chance": f"{100 * x['chance']:.1f}%", "Edge": f"{100 * x['edge']:+.1f} pts",
            "Stake": f"${x['stake']:.2f}" if x.get("stake") else "—"} for x in res])

        def _paint_r(frame):
            o = pd.DataFrame("", index=frame.index, columns=frame.columns)
            for k in frame.index:
                lab, fg, bg = mv.TIER_STYLE[res[k]["tier"]]
                o.at[k, "Call"] = (f"color: {COLOR['error']}; font-weight: 700;"
                                   if res[k]["tier"] == "none" else
                                   f"color: {fg}; font-weight: 800;"
                                   + (f" background-color: {bg};" if bg else ""))
            return o
        st.dataframe(mv.painted(rdf, _paint_r), hide_index=True, width="stretch",
                     key=f"nbap_res_{gsel}_{stat}")
        notes = [f"<b>{x['name']}</b> — {x['guard']}" for x in res if x.get("guard")]
        if notes:
            st.markdown(f'<div style="font-size:var(--lc-text-small); color:{COLOR["warn"]};">'
                        + "<br>".join(notes) + "</div>", unsafe_allow_html=True)
        if n_bet and st.button("Add these BETs to tonight's card", key=f"nbap_add_{stat}"):
            for x in res:
                if x["call"] == "BET":
                    ss.setdefault("bf_card", {})[bf.card_key("NBA", x["game"], x["name"], slab,
                                                             x["line"], side)] = dict(
                        x, sport="NBA", what=slab, line_label=f"{side[0]}{x['line']:g}")
            st.success("Added to tonight's card — it lives on the Bet Finder page.")
        mv.parlay_add_ui([{"player": x["name"], "game": x["game"],
                           "what": f"{slab} {side} {x['line']:g}", "chance": x["chance"],
                           "price": x["price"], "support": x.get("support"),
                           "tier": x["tier"]} for x in res], "NBA", f"nbap_{gsel}_{stat}")
    st.caption("Chance = what calls like it delivered on the last 45 days of 2025-26, games the "
               "model had not seen. " + nv.in_the_number(model) + " An early-season player is "
               "mostly last season's numbers until his own games pile up.")

# ---------------- his trend ----------------
with card("nbap_trend"):
    st.markdown(f'<div class="pf-card-title" style="color:{COLOR["gold"]};">His trend</div>',
                unsafe_allow_html=True)
    if rows:
        k1, k2, k3 = st.columns([2, 1, 1])
        pi = k1.selectbox("Player", range(len(rows)),
                          format_func=lambda i: f"{rows[i]['name']} ({rows[i]['team']})",
                          key=f"nbap_tp_{gsel}_{stat}")
        win = k2.selectbox("Window", ["L5", "L10", "L25", "Season"], index=1, key="nbap_win")
        pre = k3.toggle("Show preseason", value=False, key="nbap_pre")
        r = rows[pi]
        line = nv.his_line(r, stat) or 0.5
        try:
            line = float(ed.at[pi, "Line"])
        except Exception:  # noqa: BLE001 — the editor row can be blank
            pass
        nv.render_trend(r, stat, line, win, pre, key=f"nbap_tr_{pi}")
        st.caption(r.get("why") or "")

footer()
