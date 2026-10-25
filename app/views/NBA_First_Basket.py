"""NBA First Basket (10-21, revamped 10-25) — who scores each game's first
field goal, and which team does.

THE 10-25 REVAMP, measured on last season's unseen games (engines/
nba_first.fit, "confirmed"): every first field goal last season (1,235 of
1,235) was scored by one of the ten STARTERS. The old page priced a
projected five and kept ~10% for "someone else" because the projected five
missed a starter one game in ten. Priced on the real five, the log loss
fell from 2.35 to 2.27 per game (paired z ~17) and the calls stay on the
diagonal. So the page now:
  1. reads ESPN's lineup for each game at page time (cached 5 minutes) —
     when it lists five starters, that team's five is CONFIRMED;
  2. lets you set the five yourself the moment lineups are announced;
  3. re-prices instantly (engines/nba_first.reprice — the same functions
     the test ran) and delivers each call through the curve measured for
     its kind (confirmed five or projected five);
  4. opens on tonight's board: the best first-basket chances across every
     game, each marked Confirmed or Projected.
The first-TEAM call stays at THIN: the tip is the only thing that moved
it (team scoring strength measured 10-25: no gain, z 0.07).
"""
import time as _time

import pandas as pd
import streamlit as st

from styles.kc_theme import COLOR, card, footer, page_header
from engines import bet_finder as bf
from engines import live_injuries as _li
from engines import model_math as mm
from engines import model_view as mv
from engines import nba_first as nf
from engines import nba_view as nv
from engines import top_plays_board as tpb
from engines.live_sync import sync_latest_button

page_header("First Basket", "Who scores first — and which team", eyebrow="NBA", align="left")
sync_latest_button(key="sync_nba_first_basket", include_data_package=True)
games, model, pget = nv.load()
_li.render_note("nba")
fb = pget("first_basket") or {}
games = [g for g in games or [] if g.get("first_basket") and g.get("status") != "final"]
if not fb or not games:
    st.info("First-basket prices appear after the nightly build (it needs last season's "
            "play-by-play — the 'NBA prior play-by-play' workflow, run once).")
    footer()
    st.stop()

prm = fb.get("params") or {}
cal_p = fb.get("calibration") or []
conf = fb.get("confirmed") or {}
cal_c = conf.get("calibration") or []
pv = (fb.get("verdict") or {}).get("verdict")
cv = (conf.get("verdict") or {}).get("verdict")
tv = ((fb.get("team") or {}).get("verdict") or {}).get("verdict")
UNTESTED = {"measured": False, "in_range": False, "n": 0, "untested": True}
CAN_CONFIRM = all(g["first_basket"].get("pool") for g in games) and bool(prm) and bool(cal_c)


@st.cache_data(ttl=300, show_spinner=False)
def _espn_five(event_id, _bucket):
    from engines import espn_feed as ef
    try:
        summ = ef.fetch_summary("nba", event_id)
        return {"fives": nf.pregame_starters(summ), "names": nf.pregame_names(summ)}
    except Exception:  # noqa: BLE001
        return {}


def _deliver(p, sure):
    c = tpb.calibrate(p, cal_c if sure else cal_p) if (cal_c if sure else cal_p) else None
    return c if c is not None else p


def _support(p, sure):
    if pv != "beats" or (sure and cv != "beats"):
        return UNTESTED
    return mv.curve_support(p, cal_c if sure else cal_p)


def _abbr(g):
    return {str(g["home_id"]): g.get("home_abbr"), str(g["away_id"]): g.get("away_abbr")}


saved = st.session_state.setdefault("fb_saved", {})   # event -> {"fives", "sure"}


def _priced(g):
    """(prices, espn teams) for one game: ESPN's five where it is out, the
    five you set where you set one, the projected five otherwise."""
    F = g["first_basket"]
    if not CAN_CONFIRM:
        return F, set()
    eid = str(g.get("event_id") or "")
    got = _espn_five(eid, int(_time.time() // 300)) if eid else {}
    espn, names = (got or {}).get("fives") or {}, (got or {}).get("names") or {}
    fives, sure = {}, set()
    for t, five in (espn or {}).items():
        fives[t] = five
        sure.add(t)
    mine = saved.get(eid) or {}
    for t, five in (mine.get("fives") or {}).items():
        if t not in espn and len(five) == 5:
            fives[t] = five
            if t in (mine.get("sure") or ()):
                sure.add(t)
    return nf.reprice(F, prm, fives, sure, names), set(espn or {})


# ---------------- what changed, in one paragraph ----------------
st.markdown(
    f'<div style="font-size:var(--lc-text-body); line-height:1.6; color:{COLOR["text"]};">'
    f'The first <b>field goal</b> of the game (how most books settle first basket). '
    f'<b>Last season every first basket was scored by one of the ten starters</b> &mdash; so the '
    f'number that matters most is <i>who starts</i>. When the lineups are out (about 30 minutes '
    f'before tip) the page prices the <b>real five</b>: from ESPN when it posts them, or set them '
    f'yourself below. On {conf.get("n", 0)} games it never saw, pricing the real five beat '
    f'pricing a projected five ({mv.trust_label(cv)}).<br>'
    f'<span style="color:{COLOR["text_muted"]};">The player call {mv.trust_label(pv)} against '
    f'every starter equal; the first-team call {mv.trust_label(tv)} against a coin'
    + (" &mdash; a first-team bet stays at THIN" if tv != "beats" else "")
    + '.</span></div>', unsafe_allow_html=True)
if not CAN_CONFIRM:
    st.caption("Lineup confirming arrives with the next nightly build — until then these are "
               "priced on the projected five.")

board_box = st.container()
_stk = mv.staking_controls("first_basket")

labels = [f"{g.get('away_abbr')} @ {g.get('home_abbr')}  {g.get('time_et') or ''}".strip()
          for g in games]
gi = st.selectbox("Game", range(len(games)), format_func=lambda i: labels[i], key="fb_game")
g = games[gi]
eid = str(g.get("event_id") or gi)
home, away = str(g["home_id"]), str(g["away_id"])
ab = _abbr(g)

# ---------------- the starting fives ----------------
if CAN_CONFIRM:
    F0, espn_t = _priced(g)
    pool = {str(r["pid"]): r for r in g["first_basket"]["pool"]}
    with card("fb_five"):
        st.markdown(f'<div class="pf-card-title" style="color:{COLOR["gold"]};">Starting fives'
                    f'</div>', unsafe_allow_html=True)
        cols = st.columns(2)
        mine = saved.setdefault(eid, {"fives": {}, "sure": []})
        for col, t in zip(cols, (away, home)):
            with col:
                opts = sorted((p for p, r in pool.items() if str(r["team"]) == t),
                              key=lambda p: -pool[p].get("min", 0))
                if t in espn_t:
                    st.markdown(f'**{ab[t]}** &nbsp;<span style="color:{COLOR["stat_high"]}; '
                                f'font-weight:800;">✓ CONFIRMED by ESPN</span>',
                                unsafe_allow_html=True)
                    _nm = {x["pid"]: x["name"] for x in F0["players"]}
                    st.markdown("<br>".join(_nm.get(p, p) for p in F0["five"][t]),
                                unsafe_allow_html=True)
                    continue
                k = f"fb5_{eid}_{t}"
                if k not in st.session_state:
                    st.session_state[k] = [p for p in F0["five"][t] if p in opts]
                pick = st.multiselect(f"{ab[t]} starters", opts, key=k, max_selections=5,
                                      format_func=lambda p: f"{pool[p]['name']} · "
                                                            f"~{pool[p].get('min', 0):.0f} min")
                ks = f"fbs_{eid}_{t}"
                if ks not in st.session_state:
                    st.session_state[ks] = t in (mine.get("sure") or [])
                ok = st.toggle("Lineup is out — these are the real five", key=ks,
                               disabled=len(pick) != 5)
                mine["fives"][t] = list(pick)
                mine["sure"] = sorted((set(mine["sure"]) - {t}) | ({t} if ok and len(pick) == 5
                                                                    else set()))
                if len(pick) != 5:
                    st.caption("Pick five to re-price.")
        st.caption("Projected = who started most of his team's last five games and is playing "
                   "tonight, filled by projected minutes. Flip the switch once the team "
                   "announces its starters: a confirmed five is priced on the curve measured "
                   "for confirmed fives (no 'someone else' share — last season it never "
                   "happened).")
F, _espn_t = _priced(g)
sure = set(F.get("sure") or [])

# ---------------- the tip and the first team ----------------
with card("fb_tip"):
    st.markdown(f'<div class="pf-card-title" style="color:{COLOR["gold"]};">The tip and the first '
                f'team</div>', unsafe_allow_html=True)
    jh, ja = F["jumpers"].get(home) or {}, F["jumpers"].get(away) or {}

    def jline(j, abbr):
        if not j.get("name"):
            return f"{abbr}: jumper unknown"
        rec = (f"won {j['wins']} of {j['jumps']} tips" if j.get("jumps") else "no tips on record")
        return f"{abbr}: <b>{j['name']}</b> ({rec})"
    th = F["tip_home"]
    st.markdown(f'<div style="font-size:var(--lc-text-body); line-height:1.8;">'
                f'{jline(ja, ab[away])} &nbsp;vs&nbsp; {jline(jh, ab[home])}<br>'
                f'Wins the tip: <b>{ab[home] if th >= 0.5 else ab[away]} '
                f'{100 * max(th, 1 - th):.0f}%</b> · the tip winner scored first '
                f'{100 * prm.get("c", 0.63):.0f}% of the time last season</div>',
                unsafe_allow_html=True)
    trow = [{"Team": ab[t], "Scores first": f"{100 * F['team'][t]:.0f}%",
             "Worth it at": mm.fmt_american(mm.fair_american(F["team"][t])), "Your price": None}
            for t in (away, home)]
    ed = st.data_editor(pd.DataFrame(trow), hide_index=True, width="stretch", key=f"fb_team_{gi}",
                        disabled=["Team", "Scores first", "Worth it at"],
                        column_config={"Your price": st.column_config.NumberColumn(
                            step=5, format="%d")})
    sup_t = ({"measured": True, "in_range": True, "n": fb.get("n_test", 0), "untested": False}
             if tv == "beats" else UNTESTED)
    for i, t in enumerate((away, home)):
        j = bf.judge(F["team"][t], ed.at[i, "Your price"], _stk, None, sup_t)
        if j:
            lab, fg, _bg = mv.TIER_STYLE[j["tier"]]
            st.markdown(f'{ab[t]} to score first: <b style="color:'
                        f'{fg if j["tier"] != "none" else COLOR["error"]};">'
                        f'{"SKIP" if j["tier"] == "none" else lab}</b> · edge '
                        f'{100 * j["edge"]:+.1f} pts' + (f' · {j["guard"]}' if j.get("guard")
                                                        else ""), unsafe_allow_html=True)


def _rows(F_, sure_):
    out = []
    for x in F_["players"]:
        s_ = str(x["team"]) in sure_
        out.append(dict(x, chance=_deliver(x["p"], s_), sup=_support(x["p"], s_), sure=s_))
    out.sort(key=lambda x: -x["chance"])
    return out


# ---------------- the players ----------------
with card("fb_players"):
    st.markdown(f'<div class="pf-card-title" style="color:{COLOR["gold"]};">Who scores the first '
                f'basket</div>', unsafe_allow_html=True)
    pl = _rows(F, sure)
    tabs = st.tabs(["Both teams", ab[away], ab[home]])
    for tab, which in zip(tabs, (None, away, home)):
        with tab:
            show = [x for x in pl if which is None or str(x["team"]) == which]
            base = pd.DataFrame([{
                "Player": f"{x['name']} ({ab[str(x['team'])]})",
                "Chance": f"{100 * x['chance']:.1f}%",
                "Worth it at": mm.fmt_american(mm.fair_american(x["chance"])),
                "Your price": None,
                "Lineup": "✓ Confirmed" if x["sure"] else "Projected",
                "His record": (f"{x['fb']} first baskets in {x['starts']} starts"
                               if x.get("starts") else "no starts on record")} for x in show])
            ek = f"fb_pl_{gi}_{which or 'all'}"
            edited = st.data_editor(base, hide_index=True, width="stretch", key=ek,
                                    disabled=["Player", "Chance", "Worth it at", "Lineup",
                                              "His record"],
                                    column_config={"Your price": st.column_config.NumberColumn(
                                        help="Your book's first-basket price, e.g. +600.",
                                        step=5, format="%d")})
            res = []
            for i, x in enumerate(show):
                j = bf.judge(x["chance"], edited.at[i, "Your price"], _stk, None, x["sup"])
                if j:
                    res.append(dict(x, **j, price=bf.valid_price(edited.at[i, "Your price"])))
            if res:
                df = pd.DataFrame([{
                    "Call": bf.TIER_LABEL[r["tier"]], "Player": r["name"],
                    "Your price": mm.fmt_american(r["price"]), "Chance": f"{100 * r['chance']:.1f}%",
                    "Edge": f"{100 * r['edge']:+.1f} pts",
                    "Stake": f"${r['stake']:.2f}" if r.get("stake") else "—"} for r in res])

                def _paint(frame, res=res):
                    o = pd.DataFrame("", index=frame.index, columns=frame.columns)
                    for k in frame.index:
                        t_ = res[k]["tier"]
                        _l, fg, bg = mv.TIER_STYLE[t_]
                        o.at[k, "Call"] = (f"color: {COLOR['error']}; font-weight: 700;"
                                           if t_ == "none" else f"color: {fg}; font-weight: 800;"
                                           + (f" background-color: {bg};" if bg else ""))
                    return o
                st.dataframe(mv.painted(df, _paint), hide_index=True, width="stretch",
                             key=f"{ek}_res")
                notes = [f"<b>{r['name']}</b> — {r['guard']}" for r in res if r.get("guard")]
                if notes:
                    st.markdown(f'<div style="font-size:var(--lc-text-small); color:'
                                f'{COLOR["warn"]};">' + "<br>".join(notes) + "</div>",
                                unsafe_allow_html=True)
    other = F.get("other", 0)
    st.caption(f"Someone other than these ten: {100 * other:.1f}%. Chance = what calls like it "
               f"hit on last season's unseen games — confirmed fives on their own curve. "
               f"Projected fives are wrong about one game in ten; check the lineup before you "
               f"bet, or confirm it above.")

# ---------------- tonight's board (top of the page) ----------------
with board_box:
    with card("fb_board"):
        st.markdown(f'<div class="pf-card-title" style="color:{COLOR["gold"]};">Tonight&rsquo;s '
                    f'board</div><div class="pf-card-subtitle">The best first-basket chances in '
                    f'every game</div>', unsafe_allow_html=True)
        allr = []
        for i, g_ in enumerate(games):
            F_, _e = _priced(g_)
            a_ = _abbr(g_)
            for x in _rows(F_, set(F_.get("sure") or []))[:3]:
                allr.append({"Player": x["name"], "Team": a_.get(str(x["team"])),
                             "Game": labels[i], "Chance": x["chance"],
                             "Worth it at": mm.fmt_american(mm.fair_american(x["chance"])),
                             "Lineup": "✓ Confirmed" if x["sure"] else "Projected"})
        allr.sort(key=lambda r: -r["Chance"])
        bd = pd.DataFrame(allr[:15])
        if not bd.empty:
            bd["Chance"] = bd["Chance"].map(lambda v: f"{100 * v:.1f}%")
            st.dataframe(bd, hide_index=True, width="stretch", key="fb_board_tab")
        st.caption("Top three per game. A first basket at 15% needs about +570 to be worth it — "
                   "compare with your book, then open the game below to judge your price.")

footer()
