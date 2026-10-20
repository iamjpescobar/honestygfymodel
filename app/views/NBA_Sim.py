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
SGP_SUPPORT = ns.sgp_support(test)
st.markdown(
    f'<div style="font-size:var(--lc-text-body); line-height:1.6; color:{COLOR["text"]};">'
    f'Each run draws a final score from the game model, then every player&rsquo;s minutes and '
    f'stats <b>together</b>: a blowout sits the starters, a shootout lifts everyone. Each player '
    f'on his own still prices like the Props board &mdash; what the simulator adds is how the '
    f'legs of a <b>same-game parlay</b> move together.<br>'
    f'<span style="color:{COLOR["text_muted"]};">Tested on last season&rsquo;s same-game pairs '
    f'({test.get("n") or 0} of them): {mv.trust_label(tv)} vs simply multiplying the legs'
    + (" &mdash; same-game parlays priced here can reach VALUE (never STRONG: only two-man "
       "points pairs were graded)" if tv == "beats" else
       " &mdash; so a same-game parlay priced here stays at THIN until it beats")
    + '.</span></div>', unsafe_allow_html=True)

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


import json as _json  # noqa: E402
with st.spinner("Simulating 10,000 games…"):
    sim = _run(f"{g.get('event_id')}|{len(players)}", pj["mu_home"], pj["mu_away"], sd_m, sd_t,
               _json.dumps([{k: p[k] for k in ("pid", "side", "min", "mu")} for p in players]),
               _json.dumps(model.get("sizes") or {}), _json.dumps(links))
home, away = sim["home"], sim["away"]
ha, aa = g.get("home_abbr"), g.get("away_abbr")

# ---------------- the game ----------------
with card("nbs_game"):
    p_home = float((home > away).mean())
    margin = home - away
    total = home + away
    st.markdown(f'<div class="pf-card-title" style="color:{COLOR["gold"]};">{aa} @ {ha} — '
                f'{N_SIMS:,} games</div>', unsafe_allow_html=True)
    c1, c2, c3 = st.columns(3)
    c1.metric(f"{ha} wins", f"{100 * p_home:.0f}%")
    c2.metric("Typical score", f"{aa} {np.median(away):.0f} – {ha} {np.median(home):.0f}")
    c3.metric("Total (middle 80%)", f"{np.percentile(total, 10):.0f}–{np.percentile(total, 90):.0f}")
    o = g.get("odds") or {}
    bits = []
    if o.get("total") is not None:
        po = float((total > o["total"]).mean())
        bits.append(f"over the book's {o['total']:g}: <b>{100 * po:.0f}%</b>")
    lab = [f"{aa} by 20+", f"{aa} by 10-19", f"{aa} by 1-9", f"{ha} by 1-9",
           f"{ha} by 10-19", f"{ha} by 20+"]
    counts = np.histogram(margin, bins=[-1e9, -19.5, -9.5, 0, 9.5, 19.5, 1e9])[0]
    dist = pd.DataFrame({"Result": lab, "Share of games": [f"{100 * c / N_SIMS:.0f}%"
                                                            for c in counts]})
    st.dataframe(dist, hide_index=True, width="stretch", key="nbs_dist")
    st.caption(" · ".join(bits) + (" — " if bits else "")
               + "the game model has not been tested against the book; a big gap to its total "
                 "or spread means look closer (injuries, rest), not bet.")

# ---------------- every player ----------------
with card("nbs_players"):
    st.markdown(f'<div class="pf-card-title" style="color:{COLOR["gold"]};">Every player, '
                f'10,000 times</div>', unsafe_allow_html=True)
    stat_lab = st.selectbox("Stat", [lab for _s, lab in nm.STATS], key="nbs_stat")
    stat = next(s_ for s_, lab in nm.STATS if lab == stat_lab)
    rows, chances = [], []
    for p in sorted(players, key=lambda p: -(p["mu"].get(stat) or 0)):
        arr = sim["stats"][str(p["pid"])][stat]
        line = nv.his_line(p["row"], stat)
        ch = nv.chance(p["row"], stat, line, model)[0] if line is not None else None
        chances.append(ch)
        rows.append({"Player": f"{p['name']} ({p['team']})",
                     "Low (10%)": int(np.percentile(arr, 10)), "Typical": int(np.median(arr)),
                     "High (90%)": int(np.percentile(arr, 90)), "His line": line,
                     "Over %": "—" if ch is None else f"{100 * ch:.0f}%"})

    def _paint(frame):
        o_ = pd.DataFrame("", index=frame.index, columns=frame.columns)
        for k in frame.index:
            if chances[k] is not None:
                o_.at[k, "Over %"] = mv.chance_css(chances[k])
        return o_
    st.dataframe(mv.painted(pd.DataFrame(rows), _paint), hide_index=True, width="stretch",
                 key=f"nbs_pl_{stat}")
    mv.render_chance_legend()
    st.caption("Low / Typical / High = his 10th / 50th / 90th percentile over the 10,000 games. "
               "Over % = the same delivered chance the Props board prints.")

# ---------------- same-game parlay ----------------
with card("nbs_sgp"):
    st.markdown(f'<div class="pf-card-title" style="color:{COLOR["gold"]};">Same-game parlay</div>',
                unsafe_allow_html=True)
    names = [f"{p['name']} ({p['team']})" for p in players]
    nlegs = st.number_input("Legs", 2, 4, 2, key="nbs_n")
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
    j = ns.joint(sim, legs)
    prod = float(np.prod([c_ for _l, c_ in show])) if all(c_ is not None for _l, c_ in show) \
        else None
    if prod is not None and not j["lift"]:
        st.warning("In 10,000 games these legs never all hit together — the simulator can't "
                   "price this one. Check the lines.")
    if prod is not None and j["lift"]:
        jp = min(0.999, prod * j["lift"])
        st.markdown(
            f'<div style="font-size:var(--lc-text-body); line-height:1.8;">'
            + "<br>".join(f"{l_} — <b>{100 * c_:.0f}%</b>" for l_, c_ in show)
            + f'<br>Multiplied as strangers: <b>{100 * prod:.1f}%</b> · they move together '
              f'<b>x{j["lift"]:.2f}</b> in the simulator → '
              f'<span style="{mv.chance_css(jp)} padding:2px 8px; border-radius:6px;">'
              f'<b>{100 * jp:.1f}%</b></span> · worth it at '
              f'<b>{mm.fmt_american(mm.fair_american(jp))}</b></div>', unsafe_allow_html=True)
        k1, k2 = st.columns(2)
        price = k1.number_input("Your book's SGP price", value=None, step=5, format="%d",
                                key="nbs_price")
        res = bf.judge(jp, price, _stk, None, SGP_SUPPORT)
        if res and res.get("guard") and res["tier"] in ns.SGP_GUARD:
            res["guard"] = ns.SGP_GUARD[res["tier"]]
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
                           jp, bf.valid_price(price), SGP_SUPPORT, res["tier"])
                st.success("On the slip (Bet Finder page) as one leg, its legs' link priced in.")
        st.caption("Each leg is the Props board's delivered chance; only the link between them "
                   "comes from the simulator. A lift above 1 means the legs tend to hit together "
                   "(teammates in a shootout); below 1, they pull against each other (two players "
                   "fighting for the same shots, opposite sides of a blowout). Books price SGPs "
                   "with their own links — the edge, if any, is where theirs is off.")

footer()
