"""Live — player props during a game in progress (NHL, NFL).

Pick a game that has started; the page reads the live clock, score and
box score (ESPN), and prices every player's line over the REST of the
game from his pregame projection and what he already has
(engines/live_props). Type your book's live price; the call goes through
the site's one guard — untested, so at most THIN, with the edge shown.
Fits nothing.
"""
import json
from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd
import streamlit as st

from styles.kc_theme import COLOR, card, footer, page_header
from engines import bet_finder as bf
from engines import live_injuries as _li
from engines import live_props as lp
from engines import model_math as mm
from engines import model_view as mv

EASTERN = ZoneInfo("America/New_York")
page_header("Live", "Player props while the game is on", eyebrow="NHL · NFL · NBA", align="left")
st.markdown(
    f'<div style="font-size:var(--lc-text-body); line-height:1.6; color:{COLOR["text"]};">'
    f'Pick a game in progress. Every player&rsquo;s chance is for the <b>rest of the game</b>: '
    f'his pregame projection, cut to the time left, plus what he already has. Type your '
    f'book&rsquo;s <b>live</b> price; bet only when it pays more than <b>Worth it at</b>.<br>'
    f'<span style="color:{COLOR["warn"]};"><b>Not yet tested on past games</b> (until the '
    f'NHL live test has run, and then only for the markets that pass it) &mdash; so a call '
    f'here stays at THIN; the <b>Edge</b> column shows the gap in points. Not in the '
    f'number: the score (a trailing team shoots more, a blowout sits stars), a player hurt in '
    f'this game, a power play in progress. Overtime is not priced.</span></div>',
    unsafe_allow_html=True)

_stk = mv.staking_controls("live")
ss = st.session_state


@st.cache_data(ttl=30, show_spinner=False)
def _summary(sport, event_id):
    """The live game summary, read at most every 30 s; '' when it fails."""
    data = lp.fetch_summary(sport, event_id)
    if not data:
        return ""
    return json.dumps({"t": datetime.now(EASTERN).strftime("%-I:%M:%S %p"), "data": data})


_here = st.session_state.get("lc_sport_seg") or st.session_state.get("lc_sport")
_here = _here if _here in ("NHL", "NFL", "NBA") else "NHL"
sport = st.segmented_control("Sport", ["NHL", "NFL", "NBA"], default=_here,
                             key="live_sport") or _here
sp = sport.lower()

if sp == "nba":
    from engines import nba_view as _nv
    games, model, _pg = _nv.load()
    league = None
elif sp == "nhl":
    games, _d, _cur = _li.load_slate_live("nhl")
    from engines.slate_guard import payload_field
    model = payload_field("nhl", "model") or {}
    league = None
else:
    wk, _state = _li.load_week_live()
    games = (wk or {}).get("games") or []
    league = (wk or {}).get("league") or {}
    model = None

games = [g for g in games or [] if g.get("status") != "final" and g.get("event_id")
         and g.get("game_type") != "preseason"]
if not games:
    st.info(f"No {sport} games on the current slate.")
    footer()
    st.stop()

labels = [f"{g.get('away_abbr')} @ {g.get('home_abbr')}  "
          f"{g.get('time_et') or g.get('kickoff_label') or ''}".strip() for g in games]
gi = st.selectbox("Game", range(len(games)), format_func=lambda i: labels[i], key=f"live_g_{sp}")
g = games[gi]
if st.button("Refresh now", key="live_refresh"):
    _summary.clear()
raw = _summary(sp, str(g["event_id"]))
_got = json.loads(raw) if raw else {}
summ, read_at = _got.get("data") or {}, _got.get("t")
gs = lp.game_state(summ) if summ else {"state": "pre"}
f = lp.remaining(sp, gs.get("state"), gs.get("period"), gs.get("clock"))

with card("live_state"):
    if not summ:
        st.warning("Could not read the live game right now — try Refresh in a moment.")
    score = (f"{gs.get('away')} {int(gs['away_score']) if gs.get('away_score') is not None else '-'}"
             f" — {int(gs['home_score']) if gs.get('home_score') is not None else '-'} "
             f"{gs.get('home')}") if gs.get("away") else labels[gi]
    left = "—" if f is None else f"{100 * f:.0f}% of the game left"
    st.markdown(f'<div class="pf-card-title" style="color:{COLOR["gold"]};">{score}</div>'
                f'<div style="color:{COLOR["text_muted"]};">{gs.get("detail") or ""} · {left}'
                f'</div>', unsafe_allow_html=True)
    if gs.get("state") == "pre":
        st.caption("Not started — these are the pregame chances (the Bet Finder prices the same).")

if f is None:
    st.info("Overtime (or a clock the feed did not send) — live props are not priced here.")
    footer()
    st.stop()
if gs.get("state") == "post":
    st.info("This game is over.")
    footer()
    st.stop()

# ----------------------------------------------------------------------
# Players: projection + what they have
# ----------------------------------------------------------------------
rows = []
if sp == "nhl":
    STATS = {"Goals": "g", "Points": "pts", "Assists": "a", "Shots on goal": "sog"}
    box = lp.nhl_box(summ)
    size = (model.get("skater_priors") or {}).get("sog_dispersion")
    c1, c2, c3 = st.columns(3)
    slab = c1.selectbox("Stat", list(STATS), key="live_nhl_stat")
    stat = STATS[slab]
    line = c2.number_input("Line", min_value=0.5, max_value=10.5, step=1.0,
                           value=0.5 if stat != "sog" else 2.5, key=f"live_nhl_line_{stat}")
    side = c3.segmented_control("Side", ["Over", "Under"], default="Over", key="live_nhl_side") \
        or "Over"
    _check = lp.load_check()
    for s_ in ("away", "home"):
        abbr = g.get(f"{s_}_abbr")
        for p in g.get(f"{s_}_props") or []:
            have = (box.get(str(p.get("pid"))) or {}).get(stat, 0)
            ch, nd = lp.nhl_chance(p.get("mu"), stat, line, have, f, size)
            if ch is None:
                continue
            # the live test's verdict for this market (nhl_live_check.py)
            ch, sup = lp.tested(_check, stat, line, ch) if nd > 0 else (ch, lp.UNTESTED)
            rows.append({"player": f"{p.get('name')} ({abbr})", "have": have, "need": nd,
                         "over": ch, "support": sup})
elif sp == "nba":
    from engines import nba_model as _nm
    box = lp.nba_have(summ)
    sizes = (model or {}).get("sizes") or {}
    c1, c2, c3 = st.columns(3)
    slab = c1.selectbox("Stat", [lab for _s, lab in _nm.STATS], key="live_nba_stat")
    stat = next(s_ for s_, lab in _nm.STATS if lab == slab)
    line = c2.number_input("Line", min_value=0.5, max_value=89.5, step=1.0,
                           value=19.5 if stat in ("pts", "pra", "pr", "pa") else 4.5,
                           key=f"live_nba_line_{stat}")
    side = c3.segmented_control("Side", ["Over", "Under"], default="Over", key="live_nba_side") \
        or "Over"
    for s_ in ("away", "home"):
        abbr = g.get(f"{s_}_abbr")
        for p in g.get(f"{s_}_props") or []:
            have = (box.get(str(p.get("pid"))) or {}).get(stat, 0)
            ch, nd = lp.nba_chance((p.get("mu") or {}).get(stat), sizes.get(stat), line, have, f)
            if ch is None:
                continue
            rows.append({"player": f"{p.get('name')} ({abbr})", "have": have, "need": nd,
                         "over": ch})
else:
    NFL = [(s, lab, key, mk) for s, lab, key, mk, _r in mv.NFL_STATS]
    box = lp.nfl_box(summ)
    spreads = league.get("prop_spreads") or {}
    c1, c2, c3 = st.columns(3)
    slab = c1.selectbox("Stat", [lab for _s, lab, _k, _m in NFL], key="live_nfl_stat")
    stat, _lab, _key, market = next(x for x in NFL if x[1] == slab)
    big = stat in ("pass_yds", "rush_yds", "rec_yds", "scrim_yds")
    line = c2.number_input("Line", min_value=0.5, max_value=499.5, step=1.0 if not big else 5.0,
                           value=0.5 if not big else 49.5, key=f"live_nfl_line_{stat}")
    side = c3.segmented_control("Side", ["Over", "Under"], default="Over", key="live_nfl_side") \
        or "Over"
    for r in mv.nfl_game_prop_rows(g, league, wk.get("dvp")):
        mean = (r.get("_means") or {}).get(stat)
        if mean is None:
            continue
        have = (box.get(str(r.get("_pid"))) or {}).get(stat, 0)
        ch, nd = lp.nfl_chance(mean, market, spreads, line, have, f)
        if ch is None:
            continue
        rows.append({"player": r.get("_name"), "have": have, "need": nd, "over": ch})

if not rows:
    st.info("No player projections for this game.")
    footer()
    st.stop()
for r in rows:
    r["chance"] = r["over"] if side == "Over" else 1.0 - r["over"]
    r["done"] = r["need"] <= 0
rows.sort(key=lambda r: (r["done"], -r["chance"]))
rows = rows[:40]

with card("live_board"):
    st.markdown(f'<div class="pf-card-title" style="color:{COLOR["gold"]};">'
                f'{slab} {side} {line:g} — rest of the game</div>', unsafe_allow_html=True)
    base = pd.DataFrame([{
        "Player": r["player"], "Has": r["have"],
        "Needs": ("CASHED" if r["done"] and side == "Over" else
                  "LOST" if r["done"] else f"{r['need']} more"),
        "Chance": f"{100 * r['chance']:.1f}%",
        "Worth it at": (mm.fmt_american(mm.fair_american(r["chance"]))
                        if 0.01 < r["chance"] < 0.99 else "—"),
        "Your price": None} for r in rows])
    ed = st.data_editor(base, key=f"live_ed_{sp}_{stat}_{line}_{side}_{gi}", hide_index=True,
                        width="stretch",
                        disabled=["Player", "Has", "Needs", "Chance", "Worth it at"],
                        column_config={"Your price": st.column_config.NumberColumn(
                            help="Your book's LIVE price, e.g. +250.", step=5, format="%d")})
    res = []
    for i, r in enumerate(rows):
        if r["done"]:
            continue
        # Unders and NFL stay untested; an NHL Over on a market that BEAT
        # in the live test carries that test's support.
        _sup = r.get("support") if side == "Over" and r.get("support") else lp.UNTESTED
        j = bf.judge(r["chance"], ed.at[i, "Your price"], _stk, None, _sup)
        if j:
            res.append(dict(r, **j, price=bf.valid_price(ed.at[i, "Your price"])))
    if res:
        res.sort(key=lambda x: -x["edge"])
        st.dataframe(pd.DataFrame([{
            "Call": bf.TIER_LABEL[x["tier"]], "Player": x["player"],
            "Your price": mm.fmt_american(x["price"]), "Chance": f"{100 * x['chance']:.1f}%",
            "Edge": f"{100 * x['edge']:+.1f} pts",
            "Stake": f"${x['stake']:.2f}" if x.get("stake") else "—"} for x in res]),
            hide_index=True, width="stretch", key=f"live_res_{sp}")
        mv.parlay_add_ui([{"player": x["player"], "game": labels[gi],
                           "what": f"{slab} {side} {line:g} (live)", "chance": x["chance"],
                           "price": x["price"],
                           "support": (x.get("support") if side == "Over" and x.get("support")
                                       else lp.UNTESTED), "tier": x["tier"]}
                          for x in res], sp.upper(), f"live_{sp}_{stat}_{line}_{side}_{gi}")
        st.caption("Edge = our rest-of-game chance minus your price's break-even. Live markets "
                   "carry a bigger book margin and move fast; an edge of 10+ points usually "
                   "means the book knows something the box score does not (an injury, a "
                   "line change, a goalie pulled).")
    st.caption(f"Box score read {read_at or '—'} ET (re-read every 30 s). "
               "Tap Refresh now after a goal or a score.")

footer()
