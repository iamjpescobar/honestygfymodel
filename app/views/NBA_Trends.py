"""NBA Player Trends (10-20) — one player, every stat: his projection
tonight, his usual line and the chance over it, and a game-by-game chart
per stat across last season, this season and (toggle) the preseason.
"""
import pandas as pd
import streamlit as st

from styles.kc_theme import COLOR, card, footer, page_header
from engines import live_injuries as _li
from engines import model_math as mm
from engines import model_view as mv
from engines import nba_model as nm
from engines import nba_view as nv
from engines.live_sync import sync_latest_button

page_header("NBA Trends", "One player, every stat, every game", eyebrow="NBA", align="left")
sync_latest_button(key="sync_nba_trends", include_data_package=True)
games, model, _pget = nv.load()
_li.render_note("nba")
rows = nv.all_props(games)
if not rows:
    st.info("No NBA players on the slate yet — they appear after the nightly build.")
    footer()
    st.stop()

rows.sort(key=lambda r: r["name"] or "")
c1, c2, c3 = st.columns([2, 1, 1])
pi = c1.selectbox("Player", range(len(rows)),
                  format_func=lambda i: f"{rows[i]['name']} ({rows[i]['team']} vs "
                                        f"{rows[i]['opp']})", key="nbat_p")
win = c2.selectbox("Window", ["L5", "L10", "L25", "Season"], index=1, key="nbat_w")
pre = c3.toggle("Show preseason", value=True, key="nbat_pre")
r = rows[pi]

with card("nbat_head"):
    st.markdown(f'<div class="pf-card-title" style="color:{COLOR["gold"]};">{r["name"]} · '
                f'{r["team"]} vs {r["opp"]} {r.get("time") or ""}</div>'
                f'<div style="color:{COLOR["text_muted"]};">~{r["min"]:.0f} minutes tonight'
                + (f' · <b style="color:{COLOR["warn"]};">{r["status"]}</b>'
                   if r.get("status") else "") + "</div>", unsafe_allow_html=True)
    tab = []
    for st_, lab in nm.STATS:
        line = nv.his_line(r, st_)
        ch = None
        if model and line is not None:
            ch, _raw, _sup = nv.chance(r, st_, line, model)
        tab.append({"Stat": lab, "Proj": round(r["mu"][st_], 1), "His line": line,
                    "Over %": "—" if ch is None else f"{100 * ch:.0f}%",
                    "Worth it at": (mm.fmt_american(mm.fair_american(ch))
                                    if ch and 0 < ch < 1 else "—"),
                    "This season": (r.get("season") or {}).get(st_) if st_ in
                    ("pts", "reb", "ast", "tpm") else None,
                    "Last season": (r.get("last_season") or {}).get(st_) if st_ in
                    ("pts", "reb", "ast", "tpm") else None})
    _ch = []
    for st_, _lab in nm.STATS:
        line = nv.his_line(r, st_)
        _ch.append(nv.chance(r, st_, line, model)[0] if (model and line is not None) else None)

    def _paint(frame):
        o = pd.DataFrame("", index=frame.index, columns=frame.columns)
        for k in frame.index:
            if _ch[k] is not None:
                o.at[k, "Over %"] = mv.chance_css(_ch[k])
        return o
    st.dataframe(mv.painted(pd.DataFrame(tab), _paint), hide_index=True, width="stretch",
                 key="nbat_tab")
    mv.render_chance_legend()
    st.caption((r.get("why") or "") + " · Price any line on NBA Props or the Bet Finder.")

for st_, lab in (("pts", "Points"), ("reb", "Rebounds"), ("ast", "Assists"),
                 ("tpm", "3-pointers made"), ("pra", "Pts + Reb + Ast")):
    with card(f"nbat_{st_}"):
        st.markdown(f"**{lab}** — line {nv.his_line(r, st_)}")
        nv.render_trend(r, st_, nv.his_line(r, st_) or 0.5, win, pre, key=f"nbat_tr_{st_}")

footer()
