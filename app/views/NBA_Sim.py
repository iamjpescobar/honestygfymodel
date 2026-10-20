"""NBA Game Simulator (10-20) — play tonight's game 10,000 times.

Every simulated game draws a score from the game model, shapes each
player's minutes and stats to it (blowouts sit starters, a high-scoring
game lifts everyone — each link measured on last season, engines/nba_sim)
and draws every player's line together. The page shows the game's range
of outcomes, every player's, and prices a SAME-GAME PARLAY on how its
legs actually move together. Fits nothing at page time; simulates.
"""
import numpy as np
import pandas as pd
import streamlit as st

from styles.kc_theme import COLOR, card, footer, page_header
from engines import availability as av
from engines import bet_finder as bf
from engines import live_injuries as _li
from engines import model_math as mm
from engines import model_view as mv
from engines import nba_model as nm
from engines import nba_sim as ns
from engines import nba_view as nv

N_SIMS = 10000
page_header("NBA Simulator", "Play tonight's game 10,000 times", eyebrow="NBA", align="left")
games, model, pget = nv.load()
_li.render_note("nba")
sim_meta = pget("sim") or {}
games = [g for g in games if (g.get("model") or {}).get("mu_home") and (g.get("home_props")
                                                                         or g.get("away_props"))]
if not games or not model:
    st.info("The simulator needs tonight's projections and the game model — both come from the "
            "nightly build.")
    footer()
    st.stop()

test = sim_meta.get("test") or {}
tv = (test.get("verdict") or {}).get("verdict")
combos = sim_meta.get("combos") or {}
st.markdown(
    f'<div style="font-size:var(--lc-text-body); line-height:1.6; color:{COLOR["text"]};">'
    f'Each run draws a final score from the game model, then every player&rsquo;s minutes and '
    f'stats <b>together</b>: a blowout sits the starters, a shootout lifts everyone. Each player '
    f'on his own still prices like the Props board &mdash; what the simulator adds is how the '
    f'legs of a <b>same-game parlay</b> move together.<br>'
    + (f'<span style="color:{COLOR["text_muted"]};">Every kind of same-game parlay is graded '
       f'on real games (last season&rsquo;s final 45 days plus this season so far) — see '
       f'&ldquo;What has been graded&rdquo; under the parlay builder. A kind that beats simply '
       f'multiplying its legs can reach STRONG; the rest stay at THIN.</span>'
       if combos else
       f'<span style="color:{COLOR["text_muted"]};">Tested on last season&rsquo;s same-game pairs '
       f'({test.get("n") or 0} of them): {mv.trust_label(tv)} vs simply multiplying the legs'
       + (" &mdash; same-game parlays priced here can reach VALUE" if tv == "beats" else
          " &mdash; so a same-game parlay priced here stays at THIN until it beats") + '.</span>')
    + '</div>', unsafe_allow_html=True)

_stk = mv.staking_controls("nba_sim")
ss = st.session_state
labels = [f"{g.get('away_abbr')} @ {g.get('home_abbr')}  {g.get('time_et') or ''}".strip()
          for g in games]
gi = st.selectbox("Game", range(len(games)), format_func=lambda i: labels[i], key="nbs_game")
g = games[gi]
pj = g["model"]
links = sim_meta.get("links") or ns.DEFAULT_LINKS
sd_m, sd_t = (sim_meta.get("sds") or [pj.get("sd_margin"), pj.get("sd_total")])
players = []
for side in ("away", "home"):
    for r in g.get(side + "_props") or []:
        if av.is_out(r.get("status")):
            continue
        players.append({"pid": r["pid"], "side": side, "min": r["min"], "mu": r["mu"],
                        "name": r["name"], "team": g.get(side + "_abbr"), "row": r})
if not players:
    st.info("No projected players for this game yet.")
    footer()
    st.stop()


@st.cache_data(ttl=900, show_spinner=False, max_entries=16)
def _run(key, mu_h, mu_a, sd_m, sd_t, plist, sizes, links):
    import json
    import zlib
    sim = ns.simulate(mu_h, mu_a, sd_m, sd_t, json.loads(plist), json.loads(sizes),
                      json.loads(links), n=N_SIMS, seed=zlib.crc32(key.encode()))
    return sim


@st.cache_data(ttl=900, show_spinner=False, max_entries=64)
def _legs_run(key, mu_h, mu_a, sd_m, sd_t, plist, sizes, links, legs):
    """The parlay at SGP_SIMS games — only its own players, so it stays
    light; cached per game and leg set."""
    import json
    import zlib
    return ns.joint_precise(mu_h, mu_a, sd_m, sd_t, json.loads(plist), json.loads(sizes),
                            json.loads(links), json.loads(legs), seed=zlib.crc32(key.encode()))


import json as _json  # noqa: E402
with st.spinner("Simulating 10,000 games…"):
    sim = _run(f"{g.get('event_id')}|{len(players)}", pj["mu_home"], pj["mu_away"], sd_m, sd_t,
               _json.dumps([{k: p[k] for k in ("pid", "side", "min", "mu")} for p in players]),
               _json.dumps(model.get("sizes") or {}), _json.dumps(links))
home, away = sim["home"], sim["away"]
ha, aa = g.get("home_abbr"), g.get("away_abbr")

# ---------------- the game ----------------
LEAN_AT = 0.55          # a side shows as a lean from 55%; 45-55% reads "toss-up"


def _pc(p):
    return "<1%" if p < 0.005 else (">99%" if p > 0.995 else f"{100 * p:.0f}%")


def _rng(arr):
    return f"{np.percentile(arr, 10):.0f}\u2013{np.percentile(arr, 90):.0f}"


with card("nbs_game"):
    p_home = float((home > away).mean())
    margin = home - away
    total = home + away
    st.markdown(f'<div class="pf-card-title" style="color:{COLOR["gold"]};">{aa} @ {ha} — '
                f'played {N_SIMS:,} times</div>', unsafe_allow_html=True)

    def _team(abbr, pts, win, logo):
        hot = win >= 0.5
        img = (f'<img src="{logo}" style="height:40px; vertical-align:middle; margin-right:8px;">'
               if logo else "")
        return (f'<div style="flex:1 1 220px; padding:14px 16px; border-radius:12px; '
                f'border:1px solid {COLOR["stat_high"] if hot else "rgba(152,163,173,0.25)"}; '
                f'background:{"rgba(59,184,255,0.08)" if hot else "transparent"};">'
                f'<div style="font-size:1.15em; font-weight:800;">{img}{abbr}</div>'
                f'<div style="font-size:3em; font-weight:800; line-height:1.1; '
                f'color:{COLOR["stat_high"] if hot else COLOR["text"]};">{np.median(pts):.0f}</div>'
                f'<div style="font-size:var(--lc-text-small); color:{COLOR["text_muted"]};">'
                f'wins <b style="color:{COLOR["text"]};">{100 * win:.0f}%</b> of games · '
                f'scores {_rng(pts)} most nights</div></div>')
    fav, fav_by = (ha, np.median(margin)) if np.median(margin) >= 0 else (aa, -np.median(margin))
    o = g.get("odds") or {}
    tot_line = (f'Total: typically <b>{np.median(total):.0f}</b>, {_rng(total)} most nights')
    if o.get("total") is not None:
        po = float((total > o["total"]).mean())
        tot_line += (f' · over the book\'s {o["total"]:g}: <b>{100 * po:.0f}%</b>, '
                     f'under: <b>{100 * (1 - po):.0f}%</b>')
    st.markdown(
        f'<div style="display:flex; gap:12px; flex-wrap:wrap; margin:6px 0 10px;">'
        f'{_team(aa, away, 1 - p_home, g.get("away_logo"))}'
        f'{_team(ha, home, p_home, g.get("home_logo"))}</div>'
        f'<div style="font-size:var(--lc-text-body); line-height:1.8;">'
        f'Typical result: <b>{fav} by {fav_by:.0f}</b>'
        + (f' (book: {o["details"]})' if o.get("details") else "")
        + f'<br>{tot_line}</div>', unsafe_allow_html=True)
    lab = [f"{aa} by 20+", f"{aa} by 10-19", f"{aa} by 1-9", f"{ha} by 1-9",
           f"{ha} by 10-19", f"{ha} by 20+"]
    counts = np.histogram(margin, bins=[-1e9, -19.5, -9.5, 0, 9.5, 19.5, 1e9])[0]
    shares = [c / N_SIMS for c in counts]
    dist = pd.DataFrame({"How it ends": lab,
                         "Share of games": [f"{100 * x:.0f}%" for x in shares]})

    def _paint_d(frame):
        o_ = pd.DataFrame("", index=frame.index, columns=frame.columns)
        top = max(shares)
        for k in frame.index:
            a_ = 0.10 + 0.45 * shares[k] / top
            o_.at[k, "Share of games"] = (f"background-color: rgba(59,184,255,{a_:.2f}); "
                                          f"font-weight: 700;")
        return o_
    st.dataframe(mv.painted(dist, _paint_d), hide_index=True, width="stretch", key="nbs_dist")
    st.caption("Big number = the score in a typical game; 'most nights' = 8 of every 10 "
               "simulated games land in that range. The game model has not been tested against "
               "the book — a big gap to the book's total or spread means look closer "
               "(injuries, rest), not bet.")

# ---------------- every player ----------------
with card("nbs_players"):
    st.markdown(f'<div class="pf-card-title" style="color:{COLOR["gold"]};">Every player — '
                f'over or under his line?</div>', unsafe_allow_html=True)
    stat_lab = st.selectbox("Stat", [lab for _s, lab in nm.STATS], key="nbs_stat")
    stat = next(s_ for s_, lab in nm.STATS if lab == stat_lab)
    rows, sides = [], []
    for p in sorted(players, key=lambda p: -(p["mu"].get(stat) or 0)):
        arr = sim["stats"][str(p["pid"])][stat]
        line = nv.his_line(p["row"], stat)
        ch = nv.chance(p["row"], stat, line, model)[0] if line is not None else None
        un = None if ch is None else 1.0 - ch
        if ch is None:
            lean = "—"
        elif ch >= LEAN_AT:
            lean = f"OVER {_pc(ch)}"
        elif un >= LEAN_AT:
            lean = f"UNDER {_pc(un)}"
        else:
            lean = "toss-up"
        sides.append((ch, un))
        rows.append({"Player": f"{p['name']} ({p['team']})",
                     "Line": "—" if line is None else f"{line:.1f}",
                     "Typical": f"{np.median(arr):.0f}", "Most nights": _rng(arr),
                     "Over": "—" if ch is None else _pc(ch),
                     "Under": "—" if un is None else _pc(un),
                     "Lean": lean})

    def _paint(frame):
        o_ = pd.DataFrame("", index=frame.index, columns=frame.columns)
        for k in frame.index:
            ch, un = sides[k]
            if ch is None:
                continue
            o_.at[k, "Over"] = mv.chance_css(ch)
            o_.at[k, "Under"] = mv.chance_css(un)
            best = max(ch, un)
            if best >= LEAN_AT:
                o_.at[k, "Lean"] = (f"color: {COLOR['stat_high'] if ch >= un else COLOR['warn']}; "
                                    f"font-weight: 800;")
            else:
                o_.at[k, "Lean"] = f"color: {COLOR['text_muted']};"
        return o_
    st.dataframe(mv.painted(pd.DataFrame(rows), _paint), hide_index=True, width="stretch",
                 key=f"nbs_pl_{stat}")
    mv.render_chance_legend()
    st.caption("Line = his usual number for this stat (his last-10 average, the way a book "
               "hangs one) — change it to your book's line in the parlay builder below. "
               "Typical = what he gets in a normal game; most nights = 8 of 10 games land in "
               "that range. Over / Under = his chance to clear / miss the line. Lean = the "
               "side at 55% or more; 45-55% is a toss-up. A lean is not a bet until your "
               "book's price is checked (Bet Finder / Props).")

# ---------------- same-game parlay ----------------
with card("nbs_sgp"):
    st.markdown(f'<div class="pf-card-title" style="color:{COLOR["gold"]};">Same-game parlay</div>',
                unsafe_allow_html=True)
    names = [f"{p['name']} ({p['team']})" for p in players]
    nlegs = st.number_input("Legs", 2, ns.SGP_MAX_LEGS, 2, key="nbs_n",
                            help="Up to 8. Two-leg pairs are what the simulator was tested on; "
                                 "3+ legs are priced the same way but capped at THIN.")
    legs, show = [], []
    for i in range(int(nlegs)):
        a, b, c, d = st.columns([3, 2, 1, 1])
        pi = a.selectbox(f"Leg {i + 1}", range(len(players)), format_func=lambda k: names[k],
                         key=f"nbs_p{i}", index=min(i, len(players) - 1))
        slab = b.selectbox("Stat", [lab for _s, lab in nm.STATS], key=f"nbs_s{i}")
        st_ = next(s_ for s_, lab in nm.STATS if lab == slab)
        p = players[pi]
        ln = c.number_input("Line", value=float(nv.his_line(p["row"], st_) or 0.5), step=0.5,
                            key=f"nbs_l{i}_{pi}_{st_}")
        sd = d.selectbox("Side", ["Over", "Under"], key=f"nbs_d{i}")
        ch, _raw, _sup = nv.chance(p["row"], st_, ln, model, sd)
        legs.append({"pid": p["pid"], "stat": st_, "line": ln, "side": sd})
        show.append((f"{p['name']} {sd} {ln:g} {slab}", ch))
    with st.spinner(f"Playing this parlay {ns.SGP_SIMS:,} times…"):
        j = _legs_run(f"{g.get('event_id')}|{_json.dumps(legs, sort_keys=True)}",
                      pj["mu_home"], pj["mu_away"], sd_m, sd_t,
                      _json.dumps([{k: p[k] for k in ("pid", "side", "min", "mu")}
                                   for p in players]),
                      _json.dumps(model.get("sizes") or {}), _json.dumps(links),
                      _json.dumps(legs))
    prod = float(np.prod([c_ for _l, c_ in show])) if all(c_ is not None for _l, c_ in show) \
        else None
    if prod is not None and not j["lift"]:
        st.warning(f"In {ns.SGP_SIMS:,} games these legs never all hit together — the simulator "
                   f"can't price this one. Check the lines.")
    if prod is not None and j["lift"]:
        jp = min(0.999, prod * j["lift"])
        st.markdown(
            f'<div style="font-size:var(--lc-text-body); line-height:1.8;">'
            + "<br>".join(f"{l_} — <b>{100 * c_:.0f}%</b>" for l_, c_ in show)
            + f'<br>Multiplied as strangers: <b>{100 * prod:.1f}%</b> · '
              + (f'they move together <b>x{j["lift"]:.2f}</b>' if j["lift"] - 2 * j["lift_se"] > 1
                 else f'they pull apart <b>x{j["lift"]:.2f}</b>' if j["lift"] + 2 * j["lift_se"] < 1
                 else f'no real link (<b>x{j["lift"]:.2f}</b>)')
            + f' <span style="color:{COLOR["text_muted"]};">(\u00b1{j["lift_se"]:.3f}, '
              f'{ns.SGP_SIMS:,} games)</span> → '
              f'<span style="{mv.chance_css(jp)} padding:2px 8px; border-radius:6px;">'
              f'<b>{100 * jp:.1f}%</b></span> · worth it at '
              f'<b>{mm.fmt_american(mm.fair_american(jp))}</b></div>', unsafe_allow_html=True)
        k1, k2 = st.columns(2)
        price = k1.number_input("Your book's SGP price", value=None, step=5, format="%d",
                                key="nbs_price")
        sup = ns.sgp_support(test, legs, sim_meta.get("combos"))
        res = bf.judge(jp, price, _stk, None, sup)
        if res and res.get("guard"):
            res["guard"] = ns.sgp_guard(sup, res["tier"]) or res["guard"]
        if res:
            lab_, fg, bg = mv.TIER_STYLE[res["tier"]]
            st.markdown(f'<span style="color:{fg if res["tier"] != "none" else COLOR["error"]}; '
                        f'font-weight:800;">{"SKIP" if res["tier"] == "none" else lab_}</span> '
                        f'· edge {100 * res["edge"]:+.1f} pts'
                        + (f' · stake ${res["stake"]:.2f}' if res.get("stake") else "")
                        + (f'<br><span style="color:{COLOR["warn"]};">{res["guard"]}</span>'
                           if res.get("guard") else ""), unsafe_allow_html=True)
            from engines import bet_log_ui as _blu
            _blu.log_button("NBA", "sgp", f"{labels[gi]}: " + " + ".join(l_ for l_, _c in show),
                            jp, price, res.get("stake"), res["tier"], [l_ for l_, _c in show],
                            "nbs_log")
            if k2.button("Add to parlay slip", key="nbs_add"):
                from engines import parlay as pl
                pl.add_leg(ss.setdefault("parlay", {}), "NBA", labels[gi],
                           "SGP: " + " + ".join(l_ for l_, _c in show), "same-game parlay",
                           jp, bf.valid_price(price), sup, res["tier"])
                st.success("On the slip (Bet Finder page) as one leg, its legs' link priced in.")
        if combos:
            mine = ns.combo_kind(legs)
            names_k = {"pts": "all points overs", "mixed": "mixed stats"}
            gr = []
            for kind in sorted(combos, key=lambda k_: (int(k_.split("|")[0]), k_)):
                x = combos[kind]
                nl, kk = kind.split("|")
                gr.append({"Parlay": f"{nl} legs, {names_k[kk]}" + ("  ← yours" if kind == mine
                                                                   else ""),
                           "Graded": x["n"], "Predicted": f"{100 * x['predicted_sim']:.1f}%",
                           "Multiplied": f"{100 * x['predicted_ind']:.1f}%",
                           "Hit": f"{100 * x['actual']:.1f}%",
                           "Verdict": mv.trust_label((x.get("verdict") or {}).get("verdict"))})
            vlist = [(combos[k_].get("verdict") or {}).get("verdict")
                     for k_ in sorted(combos, key=lambda k_: (int(k_.split("|")[0]), k_))]

            def _paint_g(frame):
                o_ = pd.DataFrame("", index=frame.index, columns=frame.columns)
                for k_ in frame.index:
                    _n, fg_, bg_, _bd = mv.TRUST_STYLE.get(vlist[k_], mv.TRUST_STYLE[None])
                    o_.at[k_, "Verdict"] = f"color: {fg_}; background-color: {bg_}; font-weight: 700;"
                return o_
            st.markdown(f'<div style="font-size:var(--lc-text-small); font-weight:700; '
                        f'margin-top:8px;">What has been graded</div>', unsafe_allow_html=True)
            st.dataframe(mv.painted(pd.DataFrame(gr), _paint_g), hide_index=True,
                         width="stretch", key="nbs_graded")
            st.caption("Each row: same-game parlays of that kind built from real games (the top "
                       "scorers, rebounders and passers, every leg an over at his own line). "
                       "Predicted = the simulator's chance they all hit, Multiplied = the legs as "
                       "strangers, Hit = how often they really did. The verdict is the simulator "
                       "against multiplying; it grows with every game this season.")
        st.caption("Each leg is the Props board's delivered chance; only the link between them "
                   "comes from the simulator. A lift above 1 means the legs tend to hit together "
                   "(teammates in a shootout); below 1, they pull against each other (two players "
                   "fighting for the same shots, opposite sides of a blowout). Books price SGPs "
                   "with their own links — the edge, if any, is where theirs is off.")

footer()
