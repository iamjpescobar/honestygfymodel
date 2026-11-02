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

# 11-02 (Izzy): double-doubles / triple-doubles — what happened in his
# games (chips count games where it HAPPENED) and the simulator's chance
# tonight, untested so it reads THIN (engines/nba_doubles)
from engines import nba_doubles as _dd  # noqa: E402
from engines.trend_chart import render_trend_bars as _bars, window_hit_chips as _chips  # noqa: E402


@st.cache_data(ttl=900, show_spinner=False, max_entries=64)
def _dd_sim(key, mu_h, mu_a, sd_m, sd_t, player, sizes, links):
    import json
    import zlib
    from engines import nba_sim as _ns
    from engines import sim_settings as _ss
    sim = _ns.simulate(mu_h, mu_a, sd_m, sd_t, [json.loads(player)], json.loads(sizes),
                       json.loads(links), n=_ss.settings("nba")["games"],
                       seed=zlib.crc32(key.encode()))
    return _dd.sim_chance(next(iter(sim["stats"].values())))


_ddc = None
try:
    from engines import nba_sim as _ns
    import json as _js
    _g = next((g for g in games for sd in ("home", "away")
               if any(str(x.get("pid")) == str(r.get("pid")) for x in g.get(f"{sd}_props") or [])),
              None)
    _pj = (_g or {}).get("model") or {}
    _sm = _pget("sim") or {}
    if _g and _pj.get("mu_home") and model:
        _side = "home" if any(str(x.get("pid")) == str(r.get("pid"))
                              for x in _g.get("home_props") or []) else "away"
        _sds = _sm.get("sds") or [_pj.get("sd_margin"), _pj.get("sd_total")]
        if None not in _sds:
            _ddc = _dd_sim(f"{_g.get('event_id')}|{r.get('pid')}|{r['mu'].get('pts')}",
                           _pj["mu_home"], _pj["mu_away"], _sds[0], _sds[1],
                           _js.dumps({"pid": r["pid"], "side": _side, "min": r["min"],
                                      "mu": r["mu"]}),
                           _js.dumps(model.get("sizes") or {}),
                           _js.dumps(_sm.get("links") or _ns.DEFAULT_LINKS))
except Exception:  # noqa: BLE001 — the chance is extra; the history still shows
    _ddc = None

with card("nbat_dd"):
    st.markdown(f'<div class="pf-card-title" style="color:{COLOR["gold"]};">Double-double / '
                f'Triple-double</div>', unsafe_allow_html=True)
    _hist = _dd.history(r, pre)
    _reg = [n for _l, n, _w, t, _o in _hist if t != "PRE"]
    _h2h = [n for _l, n, _w, t, o in _hist if t != "PRE" and o == r.get("opp")]
    if _ddc:
        _c1, _c2 = st.columns(2)
        for _col, _k, _lab in ((_c1, "dd", "Double-double"), (_c2, "td", "Triple-double")):
            _p = _ddc[_k]
            _fair = (mm.fmt_american(mm.fair_american(_p)) if 0.01 <= _p <= 0.99 else "—")
            _col.markdown(
                f'<div style="font-size:var(--lc-text-tiny);color:{COLOR["text_muted"]};'
                f'text-transform:uppercase;letter-spacing:0.06em;">{_lab} tonight · THIN</div>'
                f'<div style="font-size:var(--lc-text-body-lg);font-weight:800;">'
                f'{"<1%" if _p < 0.005 else f"{100 * _p:.0f}%"}</div>'
                f'<div style="color:{COLOR["text_muted"]};">worth it at {_fair}</div>',
                unsafe_allow_html=True)
        st.caption("From the simulator (his projected points / rebounds / assists drawn "
                   "together through minutes, blowouts and pace). UNTESTED for one player's "
                   "doubles — read it beside his record below, never alone.")
    if not _reg:
        st.caption("No regular-season games for him yet.")
    else:
        for _lab, _line, _need in (("Double-double", _dd.DD_LINE, 2),
                                   ("Triple-double", _dd.TD_LINE, 3)):
            st.markdown(f"**{_lab}** — games he had it")
            _chips(_reg, _line, win, windows=("Season", "L20", "L10", "L5", "H2H"),
                   extra={"H2H": _h2h})
            _how = _dd.how_he_got_them(_hist, _need)
            if _how:
                st.caption("How: " + ", ".join(f"{k} {v}" for k, v in _how.items()))
        _shown = _hist
        if win == "H2H":
            _shown = [h for h in _hist if h[3] != "PRE" and h[4] == r.get("opp")]
        from engines.trend_chart import WINDOW_N as _WN
        _n = _WN.get(win)
        if _n and win != "H2H":
            _ri = [i for i, h in enumerate(_shown) if h[3] != "PRE"]
            _shown = _shown[_ri[-_n]:] if len(_ri) >= _n else _shown
        if _shown:
            _bars([h[0] for h in _shown], [h[1] for h in _shown],
                  "Stats at 10+", _dd.DD_LINE)
            st.caption("Each bar = how many of points / rebounds / assists reached 10 that game "
                       "(2 = double-double, 3 = triple-double); the dashed line is the "
                       "double-double mark. Steals / blocks are not counted.")

for st_, lab in (("pts", "Points"), ("reb", "Rebounds"), ("ast", "Assists"),
                 ("tpm", "3-pointers made"), ("pra", "Pts + Reb + Ast")):
    with card(f"nbat_{st_}"):
        st.markdown(f"**{lab}** — line {nv.his_line(r, st_)}")
        nv.render_trend(r, st_, nv.his_line(r, st_) or 0.5, win, pre, key=f"nbat_tr_{st_}",
                        minutes=show_min)

footer()
