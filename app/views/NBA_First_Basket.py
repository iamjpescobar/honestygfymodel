"""NBA First Basket (10-21) — who scores each game's first field goal,
and which team does. The nightly prices it (engines/nba_first, fitted and
tested on last season's play-by-play); this page shows it, delivers each
call through what calls like it hit on unseen games, and judges your
book's price with the site's one guard. Fits nothing."""
import pandas as pd
import streamlit as st

from styles.kc_theme import COLOR, card, footer, page_header
from engines import bet_finder as bf
from engines import live_injuries as _li
from engines import model_math as mm
from engines import model_view as mv
from engines import nba_view as nv
from engines import top_plays_board as tpb

page_header("First Basket", "Who scores first — and which team", eyebrow="NBA", align="left")
games, model, pget = nv.load()
_li.render_note("nba")
fb = pget("first_basket") or {}
games = [g for g in games or [] if g.get("first_basket") and g.get("status") != "final"]
if not fb or not games:
    st.info("First-basket prices appear after the nightly build (it needs last season's "
            "play-by-play — the 'NBA prior play-by-play' workflow, run once).")
    footer()
    st.stop()

cal = fb.get("calibration") or []
pv = (fb.get("verdict") or {}).get("verdict")
tv = ((fb.get("team") or {}).get("verdict") or {}).get("verdict")
UNTESTED = {"measured": False, "in_range": False, "n": 0, "untested": True}
st.markdown(
    f'<div style="font-size:var(--lc-text-body); line-height:1.6; color:{COLOR["text"]};">'
    f'The first <b>field goal</b> of the game (most books settle first basket on a field goal, '
    f'not a free throw). Each team&rsquo;s chance comes from the <b>tip</b> &mdash; its jumper&rsquo;s '
    f'record &mdash; and how often the tip winner scores first; each player&rsquo;s from that, his '
    f'share of his team&rsquo;s scoring and his own first-basket record as a starter.<br>'
    f'<span style="color:{COLOR["text_muted"]};">Tested on {fb.get("n_test", 0)} games last season '
    f'the model had not seen: the player call {mv.trust_label(pv)} against pricing every '
    f'projected starter the same; the first-team call {mv.trust_label(tv)} against a coin'
    + (" &mdash; so a first-team bet here stays at THIN" if tv != "beats" else "")
    + f'. The scorer was one of the ten projected starters '
      f'{100 * (fb.get("scorer_in_five") or 0):.0f}% of the time; the rest is &ldquo;someone '
      f'else&rdquo;.</span></div>', unsafe_allow_html=True)

_stk = mv.staking_controls("first_basket")
labels = [f"{g.get('away_abbr')} @ {g.get('home_abbr')}  {g.get('time_et') or ''}".strip()
          for g in games]
gi = st.selectbox("Game", range(len(games)), format_func=lambda i: labels[i], key="fb_game")
g = games[gi]
F = g["first_basket"]
home, away = str(g["home_id"]), str(g["away_id"])
ab = {home: g.get("home_abbr"), away: g.get("away_abbr")}


def deliver(p):
    c = tpb.calibrate(p, cal) if cal else None
    return c if c is not None else p


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
                f'{100 * max(th, 1 - th):.0f}%</b></div>', unsafe_allow_html=True)
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

# ---------------- the players ----------------
with card("fb_players"):
    st.markdown(f'<div class="pf-card-title" style="color:{COLOR["gold"]};">Who scores the first '
                f'basket</div>', unsafe_allow_html=True)
    pl = []
    for x in F["players"]:
        ch = deliver(x["p"])
        sup = mv.curve_support(x["p"], cal) if pv == "beats" else UNTESTED
        pl.append(dict(x, chance=ch, sup=sup))
    pl.sort(key=lambda x: -x["chance"])
    tabs = st.tabs(["Both teams", ab[away], ab[home]])
    for tab, which in zip(tabs, (None, away, home)):
        with tab:
            show = [x for x in pl if which is None or x["team"] == which]
            base = pd.DataFrame([{
                "Player": f"{x['name']} ({ab[x['team']]})", "Chance": f"{100 * x['chance']:.1f}%",
                "Worth it at": mm.fmt_american(mm.fair_american(x["chance"])),
                "Your price": None,
                "His record": (f"{x['fb']} first baskets in {x['starts']} starts"
                               if x.get("starts") else "no starts on record")} for x in show])
            ek = f"fb_pl_{gi}_{which or 'all'}"
            edited = st.data_editor(base, hide_index=True, width="stretch", key=ek,
                                    disabled=["Player", "Chance", "Worth it at", "His record"],
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
    st.caption(f"Someone other than these ten: {100 * F.get('other', 0):.0f}%. Chance = what "
               f"calls like it hit on last season's unseen games. The five per team are last "
               f"game's starters who are playing, filled by projected minutes — a late lineup "
               f"change moves these, so check the starting five before you bet.")

footer()
