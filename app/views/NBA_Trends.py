"""NBA Player Trends (10-20) — one player, every stat: his projection
tonight, his usual line and the chance over it, and a game-by-game chart
per stat across last season, this season and (toggle) the preseason.
11-02: L20 / H2H windows, a minutes line, the shot profile vs tonight's
defense and the two teams' ranks (engines/nba_research).
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

# 10-25 (Izzy): pick the TEAM first, then one of its players who can play
# tonight — ruled-out players are left out of the list and named under it.
teams = nv.slate_teams(rows)
c0, c1 = st.columns([1, 2])
ti = c0.selectbox("Team", range(len(teams)), format_func=lambda i: teams[i][1], key="nbat_t")
avail, ruled_out = nv.team_players(rows, teams[ti][0])
if not avail:
    st.info(f"No {teams[ti][0]} player is cleared to play tonight on the injury report.")
    footer()
    st.stop()
pi = c1.selectbox("Player (available tonight)", range(len(avail)),
                  format_func=lambda i: nv.player_label(avail[i]), key=f"nbat_p_{teams[ti][0]}")
if ruled_out:
    st.caption(f"Ruled out tonight, not listed: {', '.join(ruled_out)}.")
c2, c3, c4 = st.columns([1, 1, 1])
win = c2.selectbox("Window", ["L5", "L10", "L20", "Season", "H2H"], index=1, key="nbat_w")
pre = c3.toggle("Show preseason", value=True, key="nbat_pre")
show_min = c4.toggle("Minutes line", value=False, key="nbat_min")
r = avail[pi]

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
        tab.append({"Stat": lab, "Def vs pos": nv.grade(r, st_), "Overall D": nv.overall(r, st_), "Proj": round(r["mu"][st_], 1),
                    "His line": line,
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
            o.at[k, "Def vs pos"] = mv.matchup_css(frame.at[k, "Def vs pos"])
        return o
    st.dataframe(mv.painted(pd.DataFrame(tab), _paint), hide_index=True, width="stretch",
                 key="nbat_tab")
    mv.render_chance_legend()
    st.caption((r.get("why") or "") + " · Price any line on NBA Props or the Bet Finder.")

# 11-02 (Izzy): the shot profile and the team ranks (engines/nba_research,
# built in the nightly from the play-by-play). Display only.
from engines import nba_research as _nr  # noqa: E402
from engines import nba_research_view as _rv  # noqa: E402

_res = _pget("research") or {}
_seasons = [(k, _res.get(f"{k}_label") or k) for k in ("cur", "last") if _res.get(k)]
if _seasons:
    _si = st.radio("Research season", range(len(_seasons)), horizontal=True,
                   format_func=lambda i: _seasons[i][1], key="nbat_rs")
    _blk = _res[_seasons[_si][0]]
    _opp_id, _team_id = r.get("opp_id"), r.get("team_id")
    _dtab = (_blk.get("defense") or {})
    _prof = _nr.profile((_blk.get("players") or {}).get(str(r.get("pid"))))
    with card("nbat_shots"):
        st.markdown(f'<div class="pf-card-title" style="color:{COLOR["gold"]};">Shot profile · '
                    f'{r["name"]} vs {r["opp"]}</div>', unsafe_allow_html=True)
        _pz = (_blk.get("players") or {}).get(str(r.get("pid"))) or {}
        if not _prof or not any(z["att"] for z in _prof):
            st.caption("No checked shots for him this season yet (his play-by-play has to add "
                       "up to his box score before a game counts).")
        else:
            _cells = _rv.zone_cells(_prof, (_dtab.get("teams") or {}).get(_opp_id))
            st.markdown(_rv.court_img(_cells), unsafe_allow_html=True)
            st.caption(f"Tint = how much of his shooting comes from the zone (blue least, orange "
                       f"most); the white box is his share; #rank = {r['opp']}'s defense there by "
                       f"opponents' FG% (1st = toughest, red; 30th = softest, green). "
                       f"{_pz.get('games', 0)} of his games, "
                       f"{(_dtab.get('games') or {}).get(_opp_id, 0)} of {r['opp']}'s.")
            st.dataframe(pd.DataFrame(_rv.zone_rows(_prof, (_dtab.get("teams") or {}).get(_opp_id),
                                                    _dtab.get("league"), r["opp"])),
                         hide_index=True, width="stretch", key="nbat_zones")
        _src = _blk.get("src") or {}
        if _src.get("text"):
            st.caption(f"{_src.get('text')} games read from the distance written in the play "
                       f"(no shot coordinates): their threes are \"side unknown\".")
    with card("nbat_ranks"):
        st.markdown(f'<div class="pf-card-title" style="color:{COLOR["gold"]};">vs Opponent · '
                    f'team ranks</div>', unsafe_allow_html=True)
        _flip = st.radio("View", [0, 1], horizontal=True, key="nbat_flip",
                         format_func=lambda i: (f"{r['team']} offense vs {r['opp']} defense",
                                                f"{r['team']} defense vs {r['opp']} offense")[i])
        _rr = _rv.rank_rows(_blk.get("ranks"), _team_id, _opp_id, r["team"], r["opp"], bool(_flip))
        if not any(x["left_rank"] or x["right_rank"] for x in _rr):
            st.caption("No team ranks for these two teams yet.")
        else:
            _l = f"{r['team']} {'D' if _flip else 'O'}"
            _rt = f"{r['opp']} {'O' if _flip else 'D'}"
            st.dataframe(pd.DataFrame([{
                "": x["metric"],
                _l: "—" if x["left"] is None else f"{x['left']} ({_rv.ordinal(x['left_rank'])})",
                _rt: "—" if x["right"] is None else f"{x['right']} ({_rv.ordinal(x['right_rank'])})",
                "What": x["desc"]} for x in _rr]), hide_index=True, width="stretch",
                key="nbat_rk")
            st.caption("Offense: 1st = most. Defense: 1st = toughest (least allowed). Pace: 1st = "
                       "fastest. Research context — not in the projection or the letter.")
else:
    st.caption("Shot profile and team ranks appear after the next nightly build.")

for st_, lab in (("pts", "Points"), ("reb", "Rebounds"), ("ast", "Assists"),
                 ("tpm", "3-pointers made"), ("pra", "Pts + Reb + Ast")):
    with card(f"nbat_{st_}"):
        st.markdown(f"**{lab}** — line {nv.his_line(r, st_)}")
        nv.render_trend(r, st_, nv.his_line(r, st_) or 0.5, win, pre, key=f"nbat_tr_{st_}",
                        minutes=show_min)

footer()
