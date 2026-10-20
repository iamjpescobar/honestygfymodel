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

page_header("NBA", "Tonight's slate — rotations, injuries, who steps up",
            eyebrow="NBA · 2026-27", align="left")

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
    chips = "".join(
        f'<span style="display:inline-block; margin:2px 6px 2px 0; padding:3px 9px; '
        f'border-radius:12px; border:1px solid {COLOR["border"]}; '
        f'font-size:var(--lc-text-small);">{lab}: <b>{mv.trust_label(ver.get(st_))}</b></span>'
        for st_, lab in nm.STATS)
    st.markdown(f'<div style="font-size:var(--lc-text-small); color:{COLOR["text_muted"]};">'
                f'Tested on the last {nm.TEST_DAYS} days of 2025-26, against each player\'s own '
                f'hit rate over his usual line:</div>{chips}', unsafe_allow_html=True)


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
        cols = st.columns(2)
        for ci, side in enumerate(("away", "home")):
            with cols[ci]:
                st.markdown(f"**{g.get(side + '_abbr')}** "
                            f"<span style='color:{COLOR['text_muted']};'>"
                            f"{g.get(side + '_record') or ''}</span>", unsafe_allow_html=True)
                inj = g.get(side + "_injuries") or []
                if inj:
                    st.markdown(" ".join(
                        f'<span style="display:inline-block; margin:1px 4px 1px 0; padding:1px 7px; '
                        f'border-radius:10px; font-size:var(--lc-text-small); '
                        f'background:{COLOR["error"] if av.is_out(x["status"]) else COLOR["surface_raised"]}; '
                        f'color:{COLOR["text"]};">{x["name"]} · {x["status"]}</span>'
                        for x in inj[:10]), unsafe_allow_html=True)
                rows = (g.get(side + "_props") or [])[:9]
                if rows:
                    df = pd.DataFrame([{
                        "Player": r["name"] + (f" ⚠ {av.flag(r)}" if av.flag(r) else ""),
                        "Min": round(r["min"]), "Pts": round(r["mu"]["pts"], 1),
                        "Reb": round(r["mu"]["reb"], 1), "Ast": round(r["mu"]["ast"], 1),
                        "3PM": round(r["mu"]["tpm"], 1), "PRA": round(r["mu"]["pra"], 1)}
                        for r in rows])
                    st.dataframe(df, hide_index=True, width="stretch", key=f"nba_rot_{gi}_{side}")
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
        st.caption("Projected minutes and per-game means. NOT in the number: tonight's "
                   "opponent and pace, a teammate out, rest. Price any of them on the Bet Finder.")

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
        st.dataframe(df, hide_index=True, width="stretch", key="nba_watch")
        st.caption("REFERENCE ONLY — preseason rotations are not regular-season ones and never "
                   "touch a projection. A big minutes jump can hint at a new role; the model only "
                   "believes it once the regular-season games say so.")

footer()
