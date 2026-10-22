"""NBA — Tonight (10-20): every game on the slate with its injury report,
each team's projected rotation, Next Man Up when a big name sits, and
the preseason role watch. Reads the nightly's data/nba/games.json
through the live injury check (engines/nba_view). Fits nothing.
"""
import pandas as pd
import streamlit as st

from styles.kc_theme import COLOR, card, footer, page_header
from engines import availability as av
from engines import live_injuries as _li
from engines import model_view as mv
from engines import nba_model as nm
from engines import nba_view as nv
from engines.slate_guard import staleness_note
from engines.live_sync import sync_latest_button

page_header("NBA", "Tonight's slate — rotations, injuries, who steps up",
            eyebrow="NBA · 2026-27", align="left")
sync_latest_button(key="sync_nba", include_data_package=True)

games, model, pget = nv.load()
_note = staleness_note("nba")
if _note:
    st.caption(_note)
_li.render_note("nba")

if not games:
    st.info("No NBA slate on disk yet — it appears after the next nightly build.")
    footer()
    st.stop()

# ---------------- what the model has earned ----------------
ver = nv.verdicts(model)
if not model:
    st.warning("Projections need last season's box scores: run the **NBA prior season** "
               "workflow once (GitHub → Actions). Until then the slate, injuries and preseason "
               "are here, but no player numbers.")
else:
    def _chip(lab, verdict):
        name, fg, bg, bd = mv.TRUST_STYLE.get(verdict, mv.TRUST_STYLE[None])
        return (f'<span style="display:inline-block; margin:2px 6px 2px 0; padding:3px 9px; '
                f'border-radius:12px; border:1px solid {bd}; background:{bg}; '
                f'font-size:var(--lc-text-small);">{lab}: <b style="color:{fg};">{name}</b>'
                f'</span>')
    chips = "".join(_chip(lab, ver.get(st_)) for st_, lab in nm.STATS)
    _gv = ((pget("game_model") or {}).get("validation") or {})
    if _gv.get("n"):
        chips += "".join(_chip(lab, ((_gv.get(k) or {}).get("verdict")))
                         for k, lab in (("ml_verdict", "Winner"), ("spread_verdict", "Margin"),
                                        ("total_verdict", "Total")))
    _vb = (pget("game_model") or {}).get("vs_book") or {}
    for _k, _lab in (("total", "Totals vs book"), ("spread", "Spreads vs book")):
        _x = _vb.get(_k) or {}
        if _x.get("n"):
            chips += _chip(f"{_lab} ({_x['n']} games)", (_x.get("verdict") or {}).get("verdict")
                           if _x["n"] >= 30 else None)
    _cx = (model.get("context") or {}).get("vs_base") or {}
    if _cx:
        chips += "".join(_chip(f"{lab} + context", (_cx.get(st_) or {}).get("verdict"))
                         for st_, lab in nm.STATS[:4])
    st.markdown(f'<div style="font-size:var(--lc-text-small); color:{COLOR["text_muted"]};">'
                f'Tested on last season\'s games the model had not seen — player stats against each '
                f'player\'s own hit rate over his usual line; the game model against the home '
                f'team\'s record and the league\'s average margin and total'
                + ('; "+ context" = with tonight\'s opponent and teammates-out against '
                   'without them' if _cx else '') + f':</div>{chips}',
                unsafe_allow_html=True)
    _se = model.get("settings") or {}
    if _se.get("since"):
        _ck = _se.get("check") or {}
        _v = (_ck.get("verdict") or {})
        st.caption(
            f"Model settings in use since {_se['since']} ({_se.get('source')})"
            + (f" · changed {_se['changes']} time{'s' if _se['changes'] != 1 else ''} this "
               f"season" if _se.get("changes") else "")
            + " · re-checked every night against a challenger fitted on newer games: "
            + (_ck["note"] if _ck.get("note") else
               ("REPLACED tonight" if _ck.get("replace") else "held")
               + (f" (newest {_ck.get('n')} player-games, challenger z={_v.get('z')})"
                  if _v else " (the challenger came out the same)")) + ".")


def _pct(x):
    return "—" if x is None else f"{x:g}"


def _odds_line(g):
    o = g.get("odds") or {}
    bits = []
    if o.get("details"):
        bits.append(o["details"])
    if o.get("total") is not None:
        bits.append(f"O/U {o['total']:g}")
    return " · ".join(bits)


for gi, g in enumerate(games):
    with card(f"nba_game_{gi}"):
        logos = "".join(f'<img src="{g.get(s_ + "_logo")}" style="height:34px; '
                        f'vertical-align:middle; margin-right:6px;">'
                        for s_ in ("away", "home") if g.get(s_ + "_logo"))
        score = ""
        if g.get("status") in ("in progress", "final") and g.get("away_score") is not None:
            score = f' · <b>{g["away_score"]}–{g["home_score"]}</b> {g.get("detail") or ""}'
        st.markdown(
            f'<div style="display:flex; align-items:center; gap:8px; flex-wrap:wrap;">{logos}'
            f'<span class="pf-card-title" style="color:{COLOR["gold"]};">'
            f'{g.get("away_abbr")} @ {g.get("home_abbr")}</span>'
            f'<span style="color:{COLOR["text_muted"]};">{g.get("time_et") or ""}'
            f'{" · " + _odds_line(g) if _odds_line(g) else ""}{score}</span></div>',
            unsafe_allow_html=True)
        pj = g.get("model") or {}
        if pj.get("p_home") is not None:
            ph = pj["p_home"]
            fav, pf = ((g.get("home_abbr"), ph) if ph >= 0.5 else (g.get("away_abbr"), 1 - ph))
            tot = pj.get("total")
            mt = pj.get("market_total")
            lean = ""
            if tot is not None and mt is not None:
                gap = tot - mt
                lean = (f' · total <b>{tot:.1f}</b> vs book {mt:g} '
                        f'(<span style="color:{COLOR["warn"] if abs(gap) >= 8 else COLOR["text_muted"]};">'
                        f'model {gap:+.1f}{" — CHECK: the book likely knows why" if abs(gap) >= 8 else ""}'
                        f'</span>)')
            st.markdown(
                f'<div style="font-size:var(--lc-text-small); line-height:1.6;">Model: '
                f'{g.get("away_abbr")} <b>{pj["away_score"]:.0f}</b> – {g.get("home_abbr")} '
                f'<b>{pj["home_score"]:.0f}</b> · <span style="{mv.chance_css(pf)} padding:1px 6px; '
                f'border-radius:6px;">{fav} {100 * pf:.0f}%</span> · fair spread '
                f'{g.get("home_abbr")} {pj["fair_spread_home"]:+.1f}{lean}</div>',
                unsafe_allow_html=True)
            _ro = g.get("roster") or {}
            if _ro.get("margin") is not None:
                _rm = _ro["margin"]
                st.markdown(
                    f'<div style="font-size:var(--lc-text-small); color:{COLOR["text_muted"]};">'
                    f'Tonight\'s rosters say: {g.get("home_abbr") if _rm >= 0 else g.get("away_abbr")}'
                    f' by {abs(_rm):.1f} (each player\'s own projection, minutes summed to 240) — '
                    + ("in the model's margin at its tested weight"
                       if _ro.get("w") else "information only: it has not yet beaten the team "
                       "ratings on unseen games")
                    + "</div>", unsafe_allow_html=True)
        for side in ("away", "home"):
            st.markdown(f"**{g.get(side + '_abbr')}** "
                        f"<span style='color:{COLOR['text_muted']};'>"
                        f"{g.get(side + '_record') or ''}</span>", unsafe_allow_html=True)
            inj = g.get(side + "_injuries") or []
            if inj:
                st.markdown(" ".join(
                    f'<span style="display:inline-block; margin:1px 4px 1px 0; padding:1px 7px; '
                    f'border-radius:10px; font-size:var(--lc-text-small); '
                    f'background:{COLOR["error"] if av.is_out(x["status"]) else COLOR["warn_dim"]}; '
                    f'color:{COLOR["text"]};">{x["name"]} · {x["status"]}</span>'
                    for x in inj[:10]), unsafe_allow_html=True)
            rows = (g.get(side + "_props") or [])[:9]
            if rows:
                cells = ("pts", "reb", "ast", "tpm", "pra")
                heads = {"pts": "Pts", "reb": "Reb", "ast": "Ast", "tpm": "3PM", "pra": "PRA"}
                df = pd.DataFrame([{
                    "Player": r["name"] + (f" ⚠ {av.flag(r)}" if av.flag(r) else "")
                    + nv.tags(r),
                    "Min": round(r["min"]),
                    **{heads[c]: round(r["mu"][c], 1) for c in cells}} for r in rows])
                chances = []
                for r in rows:
                    ch = {}
                    for c in cells:
                        ln = nv.his_line(r, c)
                        ch[c] = nv.chance(r, c, ln, model)[0] if (model and ln) else None
                    chances.append(ch)

                def _paint(frame, chances=chances):
                    o = pd.DataFrame("", index=frame.index, columns=frame.columns)
                    for k in frame.index:
                        for c in cells:
                            if chances[k].get(c) is not None:
                                o.at[k, heads[c]] = mv.chance_css(chances[k][c])
                    return o
                st.dataframe(mv.painted(df, _paint), hide_index=True, width="stretch",
                             key=f"nba_rot_{gi}_{side}")
            if g.get(side + "_no_data"):
                st.caption("On the roster, no NBA games on file yet (not projected): "
                           + ", ".join(g[side + "_no_data"]))
            for b in (g.get(side + "_next_man_up") or [])[:2]:
                top = (b.get("rows") or [])[:3]
                if top:
                    st.markdown(
                        f'<div style="font-size:var(--lc-text-small); color:{COLOR["warn"]};">'
                        f'<b>{b["out_name"]} is out</b> ({b["out_min"]:.0f} min a game) — when he '
                        f'sat before: ' + ", ".join(
                            f'{x["name"]} {x["delta"]["pts"]:+.1f} pts / '
                            f'{x["delta"]["min"]:+.1f} min (n={x["n_without"]})'
                            for x in top if x["delta"].get("pts") is not None)
                        + " · <i>Next Man Up page has the full board</i></div>",
                        unsafe_allow_html=True)
        mv.render_chance_legend()
        if pj.get("p_home") is not None:
            st.caption("Game model: team ratings from last season and this one. It beats the home "
                       "team's record and the league average on unseen games, but it has not been "
                       "tested against the BOOK yet — so game bets on the Bet Finder are priced on "
                       "the book's own number, and a big model-vs-book gap means look closer, "
                       "not bet.")
        _tn = nv.tags_note([r for s_ in ("away", "home") for r in g.get(s_ + "_props") or []],
                           model)
        if _tn:
            st.caption(_tn)
        if any(r.get("new") for s_ in ("away", "home") for r in g.get(s_ + "_props") or []):
            st.caption("NEW = no NBA regular-season games on file (a rookie, or back from a season "
                       "out): projected from this preseason, never tested, so his calls stay "
                       "at THIN until his own games come in.")
        st.caption("Numbers = projected minutes and per-game means. Colour = the chance he "
                   "clears HIS usual line for that stat (his last-10 average set at the half "
                   "point) — green likely over, faint unlikely. " + nv.in_the_number(model)
                   + " Price any line on NBA Props or the Bet Finder.")

# ---------------- preseason role watch ----------------
watch = pget("role_watch") or []
with card("nba_role_watch"):
    st.markdown(f'<div class="pf-card-title" style="color:{COLOR["gold"]};">'
                f'Preseason role watch — minutes vs last season</div>', unsafe_allow_html=True)
    if not watch:
        st.caption("Shows up once preseason box scores are in.")
    else:
        df = pd.DataFrame([{
            "Player": w["name"], "Team": w.get("team_abbr") or "",
            "Pre GP": w["pre"]["gp"], "Pre min": w["pre"].get("min"),
            "Last season min": (w.get("last") or {}).get("min"),
            "Change": (f"{w['min_delta']:+.1f}" if w.get("min_delta") is not None else "new"),
            "Pre pts": w["pre"].get("pts"), "Pre reb": w["pre"].get("reb"),
            "Pre ast": w["pre"].get("ast")} for w in watch[:25]])
        def _paint_w(frame):
            o = pd.DataFrame("", index=frame.index, columns=frame.columns)
            for k in frame.index:
                d = watch[k].get("min_delta")
                if d is None:
                    continue
                if d >= 4:
                    o.at[k, "Change"] = f"color: {COLOR['stat_high']}; font-weight: 800;"
                elif d <= -4:
                    o.at[k, "Change"] = f"color: {COLOR['error']}; font-weight: 800;"
            return o
        st.dataframe(mv.painted(df, _paint_w), hide_index=True, width="stretch",
                     key="nba_watch")
        st.caption("REFERENCE ONLY — preseason rotations are not regular-season ones and never "
                   "touch a projection. A big minutes jump can hint at a new role; the model only "
                   "believes it once the regular-season games say so.")

footer()
