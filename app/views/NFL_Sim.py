"""NFL Game Simulator (10-22) — play this week's game 50,000 times.

Every simulated game draws a score from the game model, shapes every
player's line to it (a team that scores more throws for more; a team
that leads runs the clock), draws the yards of a quarterback and his
receivers together at their measured correlation, and hands the team's
touchdowns to its scorers — each link measured on 2025 (engines/nfl_sim).
The page shows the game's range of outcomes, every player's, and prices
a SAME-GAME PARLAY on how its legs move together. Fits nothing at page
time; simulates.
"""
import json as _json
import math

import numpy as np
import pandas as pd
import streamlit as st

from styles.kc_theme import COLOR, card, footer, page_header
from engines import availability as av
from engines import bet_finder as bf
from engines import live_injuries as _li
from engines import model_math as mm
from engines import model_view as mv
from engines import nfl_projection as nproj
from engines import nfl_prop_odds as npo
from engines import nfl_quarters as nq
from engines import nfl_sim as fs
from engines.live_sync import sync_latest_button

from engines import sim_settings as _ss  # noqa: E402
SIM = _ss.settings("nfl")   # 10-26: football's own settings (engines/sim_settings)
N_SIMS = SIM["games"]
page_header("NFL Simulator", f"Play this week's game {N_SIMS:,} times", eyebrow="NFL", align="left")
sync_latest_button(key="sync_nfl_sim", include_data_package=True)


@st.cache_data(ttl=900, show_spinner=False)
def _load(_day):
    payload, _state = _li.load_week_live()
    return payload or {}


from engines.nfl_week import EASTERN  # noqa: E402
from datetime import datetime  # noqa: E402
payload = _load(datetime.now(EASTERN).date().isoformat())
_li.render_note("nfl")
league = payload.get("league") or {}
sim_meta = payload.get("sim") or {}
games = [g for g in payload.get("games") or [] if (g.get("model") or {}).get("mu_home")
         and g.get("status") != "final" and (g.get("home_players") or g.get("away_players"))]
if not games or not league:
    st.info("The simulator needs this week's projections and the game model — both come from "
            "the nightly build.")
    footer()
    st.stop()

spreads = league.get("prop_spreads") or {}
cal = mv.nfl_calibration(league)
combos = sim_meta.get("combos") or {}
links = sim_meta.get("links") or fs.DEFAULT_LINKS
beat = [fs.KIND_LABEL[k] for k, x in combos.items()
        if (x.get("verdict") or {}).get("verdict") == "beats" and k in fs.KIND_LABEL]
st.markdown(
    f'<div style="font-size:var(--lc-text-body); line-height:1.6; color:{COLOR["text"]};">'
    f'Each run draws a final score, then every player&rsquo;s line <b>shaped by it</b>: a team '
    f'that scores more throws for more, a team that leads runs the ball, a quarterback&rsquo;s '
    f'yards and his receivers&rsquo; move together, and the touchdowns go to the team&rsquo;s '
    f'scorers. Each player on his own still prices like the Prop Lab &mdash; what the simulator '
    f'adds is how the legs of a <b>same-game parlay</b> move together.<br>'
    f'<span style="color:{COLOR["text_muted"]};">Graded on real games (2025&rsquo;s second half '
    f'plus this season so far): '
    + (("beats simply multiplying the legs for " + "; ".join(beat) + " — those can reach "
        "STRONG; every other kind stays at THIN") if beat else
       "no kind of parlay has beaten simply multiplying its legs yet, so every same-game "
       "parlay here stays at THIN")
    + '.</span></div>', unsafe_allow_html=True)

_stk = mv.staking_controls("nfl_sim")
ss = st.session_state
labels = [f"{g.get('away_abbr')} @ {g.get('home_abbr')}  "
          f"{g.get('kick_date_et') or ''} {g.get('kick_time_et') or ''}".strip() for g in games]
gi = st.selectbox("Game", range(len(games)), format_func=lambda i: labels[i], key="nfs_game")
g = games[gi]
pj = g["model"]
ha, aa = g.get("home_abbr"), g.get("away_abbr")
o = g.get("odds") or {}

# every player's projection, exactly as the Prop Lab builds it
nproj.attach_td_shares([g], league)
a_pts, h_pts, _n = nproj.implied_totals(o, aa, ha)
players, info = [], {}
for side, other in (("away", "home"), ("home", "away")):
    team, opp = g.get(f"{side}_profile"), g.get(f"{other}_profile")
    implied = a_pts if side == "away" else h_pts
    if implied is None:
        implied = pj["mu_away"] if side == "away" else pj["mu_home"]
    for p in g.get(f"{side}_players") or []:
        if av.is_out(p.get("status")) or not p.get("role"):
            continue
        proj = nproj.project_player(p, team, opp, league, implied)
        pr = {k: v for k, v in proj.items() if isinstance(v, (int, float))}
        players.append({"pid": str(p.get("pid")), "side": side, "role": p.get("role"),
                        "proj": pr, "name": p.get("name"), "team": g.get(f"{side}_abbr"),
                        "pos": p.get("pos") or p.get("role")})
        info[str(p.get("pid"))] = (side, p.get("role"))
if not players:
    st.info("No projected players for this game yet.")
    footer()
    st.stop()
_sds = sim_meta.get("sds") or [pj.get("sd_margin"), pj.get("sd_total")]
game_in = {"mu_home": pj["mu_home"], "mu_away": pj["mu_away"], "sd_margin": _sds[0],
           "sd_total": _sds[1]}


@st.cache_resource(ttl=900, show_spinner=False, max_entries=SIM["keep"])   # one shared copy
def _run(key, game_js, plist, sp_js, links_js):
    import zlib
    return _ss.run("nfl", fs.simulate, _json.loads(game_js), _json.loads(plist),
                   _json.loads(sp_js), _json.loads(links_js), seed=zlib.crc32(key.encode()))


@st.cache_data(ttl=900, show_spinner=False, max_entries=64)
def _legs_run(key, game_js, plist, sp_js, links_js, legs):
    import zlib
    return fs.joint_precise(_json.loads(game_js), _json.loads(plist), _json.loads(sp_js),
                            _json.loads(links_js), _json.loads(legs), n=SIM["sgp"],
                            chunk=SIM["sgp_chunk"], seed=zlib.crc32(key.encode()))


_plist = _json.dumps([{k: p[k] for k in ("pid", "side", "role", "proj")} for p in players])
_gjs, _spjs, _ljs = _json.dumps(game_in), _json.dumps(spreads), _json.dumps(links)
with st.spinner(f"Simulating {N_SIMS:,} games…"):
    sim = _run(f"{g.get('event_id')}|{len(players)}", _gjs, _plist, _spjs, _ljs)
home, away = sim["home"], sim["away"]


def _pc(p):
    return "<1%" if p < 0.005 else (">99%" if p > 0.995 else f"{100 * p:.0f}%")


def _rng(arr):
    return f"{np.percentile(arr, 10):.0f}–{np.percentile(arr, 90):.0f}"


def chance(p, stat, line, side="Over"):
    """The Prop Lab's delivered chance for one leg."""
    key = "td_exp" if stat == "td" else stat
    pm = npo.stat_pmf(fs.MARKET.get(stat), p["proj"].get(key), spreads)
    if not pm:
        return None
    raw = mm.over_prob_pmf(pm, line)
    ch, _b = mv.delivered_over(raw, stat, line, (), cal)
    return ch if side == "Over" else 1 - ch


def default_line(p, stat):
    if stat == "td":
        return 0.5
    v = p["proj"].get(stat) or 0
    return math.floor(v) + 0.5


def p_win(side):
    ph = pj.get("p_home_final", pj.get("p_home"))
    return ph if side == "home" else 1 - ph


# ---------------- the game ----------------
with card("nfs_game"):
    ph_sim = float((home > away).mean())
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
                f'scores {_rng(pts)} most weeks</div></div>')
    total, margin = home + away, home - away
    tl = f'Total: typically <b>{np.median(total):.0f}</b>, {_rng(total)} most weeks'
    if o.get("total") is not None:
        po = float((total > o["total"]).mean())
        tl += (f' · over the book\'s {o["total"]:g}: <b>{100 * po:.0f}%</b>, under '
               f'<b>{100 * (1 - po):.0f}%</b>')
    sl = ""
    if o.get("spread") is not None:
        cov = float((margin + o["spread"] > 0).mean())
        sl = (f'<br>{ha} {o["spread"]:+g} covers: <b>{100 * cov:.0f}%</b>, {aa} '
              f'{-o["spread"]:+g}: <b>{100 * (1 - cov):.0f}%</b>')
    st.markdown(
        f'<div style="display:flex; gap:12px; flex-wrap:wrap; margin:6px 0 10px;">'
        f'{_team(aa, away, 1 - ph_sim, g.get("away_logo"))}'
        f'{_team(ha, home, ph_sim, g.get("home_logo"))}</div>'
        f'<div style="font-size:var(--lc-text-body); line-height:1.8;">{tl}{sl}</div>',
        unsafe_allow_html=True)
    st.caption("Big number = the score in a typical game; 'most weeks' = 8 of every 10 "
               "simulated games. The game model's own weight against the book is on the "
               "Model page; a bet is priced on the Bet Finder, not here.")

# ---------------- the box score ----------------
BOX = {"QB": (("pass_yds", "Pass yds"), ("pass_td", "Pass TD"), ("rush_yds", "Rush yds")),
       "RB": (("rush_yds", "Rush yds"), ("rec_yds", "Rec yds"), ("td", "TD")),
       "REC": (("rec_yds", "Rec yds"), ("rec", "Catches"), ("td", "TD"))}
with card("nfs_box"):
    st.markdown(f'<div class="pf-card-title" style="color:{COLOR["gold"]};">The box score — '
                f'{N_SIMS:,} games</div>', unsafe_allow_html=True)
    for side, abbr in (("away", aa), ("home", ha)):
        mine = [p for p in players if p["side"] == side]
        if not mine:
            continue
        st.markdown(f"**{abbr}**")
        for role, lab in (("QB", "Quarterback"), ("RB", "Backs"), ("REC", "Receivers")):
            rr = [p for p in mine if p["role"] == role]
            if not rr:
                continue
            rows = []
            for p in rr:
                arr = sim["stats"].get(p["pid"]) or {}
                r = {lab: f"{p['name']} ({p['pos']})"}
                for st_, cl in BOX[role]:
                    a_ = arr.get(st_)
                    if a_ is None:
                        r[cl] = "—"
                    elif st_ in ("td", "pass_td"):
                        r[cl] = (f"{_pc(float((a_ > 0).mean()))} any" if st_ == "td"
                                 else f"{a_.mean():.1f}")
                    else:
                        r[cl] = f"{np.median(a_):.0f}  ({_rng(a_)})"
                rows.append(r)
            st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch",
                         key=f"nfs_box_{side}_{role}")
    st.caption("Each cell: his typical game, then the range 8 of 10 simulated games land in. TD "
               "= how often he scores at least one.")

# ---------------- the 1st quarter / 1st half ----------------
qmeta = sim_meta.get("quarters") or {}
if qmeta.get("model"):
    with card("nfs_q"):
        st.markdown(f'<div class="pf-card-title" style="color:{COLOR["gold"]};">1st quarter / '
                    f'1st half</div>', unsafe_allow_html=True)
        qtest, qcal = qmeta.get("test") or {}, {}
        for _k, _x in qtest.items():
            if _x.get("calibration"):
                qcal[f"@{_k}"] = _x["calibration"]
        c1, c2 = st.columns([1, 2])
        per_lab = c1.radio("Span", [lab for _p, lab, _i in nq.PERIODS], horizontal=True,
                           key="nfs_q_per")
        per = next(p_ for p_, lab, _i in nq.PERIODS if lab == per_lab)
        tl = nq.team_lines(float(pj["mu_home"]), float(pj["mu_away"]), qmeta.get("team"), per)
        tv = ((qmeta.get("team_test") or {}).get(f"{per}_lead_home") or {}).get("verdict") or {}
        if tl:
            st.markdown(
                f'<div style="font-size:var(--lc-text-body); line-height:1.8;">'
                f'Points in the {per_lab.lower()}: about <b>{tl["mu_total"]:.1f}</b> together '
                f'(the {per_lab.lower()} holds {100 * qmeta["team"][per]["share"]:.0f}% of a '
                f'game&rsquo;s points).<br>Leading after it: {ha} <b>{_pc(tl["lead_home"])}</b>, '
                f'tied <b>{_pc(tl["tie"])}</b>, {aa} <b>{_pc(tl["lead_away"])}</b> '
                f'<span style="color:{COLOR["text_muted"]};">'
                f'({mv.trust_label(tv.get("verdict"))})</span></div>', unsafe_allow_html=True)
        stl = c2.selectbox("Stat", [lab for _s, lab in nq.Q_STATS], index=5, key="nfs_q_stat")
        qs = next(s_ for s_, lab in nq.Q_STATS if lab == stl)
        k_ = nq.key(per, qs)
        rows_q, sides_q = [], []
        for p in sorted([p for p in players if (p["proj"].get(qs) or 0) > 0],
                        key=lambda p: -(p["proj"].get(qs) or 0)):
            pm = nq.pmf(qmeta["model"], per, qs, float(p["proj"][qs]))
            if not pm:
                continue
            ln = float(mv.balanced_line(pm))
            raw = mm.prob_at_least(pm, int(math.floor(ln)) + 1)
            ch, _b = mv.delivered_over(raw, k_, ln, (), qcal)
            sides_q.append((ch, 1 - ch))
            rows_q.append({"Player": f"{p['name']} ({p['team']})", "Line": f"{ln:g}",
                           "Average": f"{sum(i * x for i, x in enumerate(pm)):.1f}",
                           "Over": _pc(ch), "Under": _pc(1 - ch)})

        def _paint_q(frame):
            o_ = pd.DataFrame("", index=frame.index, columns=frame.columns)
            for k in frame.index:
                o_.at[k, "Over"] = mv.chance_css(sides_q[k][0])
                o_.at[k, "Under"] = mv.chance_css(sides_q[k][1])
            return o_
        if rows_q:
            st.dataframe(mv.painted(pd.DataFrame(rows_q), _paint_q), hide_index=True,
                         width="stretch", key=f"nfs_q_{k_}")
        xv = (qtest.get(k_) or {})
        st.caption(
            f"{nq.label(per, qs).capitalize()}: his game projection, spread the way the "
            f"{per_lab.lower()} really lands for players projected like him (2025, only games "
            f"whose quarters add up to the box score). Graded against his own last-8 "
            f"{per_lab.lower()} rate on 2025's second half: "
            f"{mv.trust_label((xv.get('verdict') or {}).get('verdict'))}"
            + (f" (n={xv.get('n')})" if xv.get("n") else "")
            + ". Only graded spans that beat it reach the Bet Finder. The line is the one "
              "nearest a coin flip for him — use your book's on the Bet Finder.")


# ---------------- every player ----------------
with card("nfs_players"):
    st.markdown(f'<div class="pf-card-title" style="color:{COLOR["gold"]};">Every player — '
                f'over or under?</div>', unsafe_allow_html=True)
    stat_lab = st.selectbox("Stat", [lab for _s, lab in fs.STATS], key="nfs_stat", index=7)
    stat = next(s_ for s_, lab in fs.STATS if lab == stat_lab)
    key = "td_exp" if stat == "td" else stat
    rows, sides = [], []
    for p in sorted([p for p in players if (p["proj"].get(key) or 0) > 0],
                    key=lambda p: -(p["proj"].get(key) or 0)):
        arr = (sim["stats"].get(p["pid"]) or {}).get(stat)
        if arr is None:
            continue
        line = default_line(p, stat)
        ch = chance(p, stat, line)
        un = None if ch is None else 1 - ch
        lean = ("—" if ch is None else f"OVER {_pc(ch)}" if ch >= 0.55 else
                f"UNDER {_pc(un)}" if un >= 0.55 else "toss-up")
        sides.append((ch, un))
        rows.append({"Player": f"{p['name']} ({p['team']})", "Line": f"{line:g}",
                     "Typical": f"{np.median(arr):.0f}", "Most weeks": _rng(arr),
                     "Over": "—" if ch is None else _pc(ch),
                     "Under": "—" if un is None else _pc(un), "Lean": lean})

    def _paint(frame):
        o_ = pd.DataFrame("", index=frame.index, columns=frame.columns)
        for k in frame.index:
            ch, un = sides[k]
            if ch is None:
                continue
            o_.at[k, "Over"] = mv.chance_css(ch)
            o_.at[k, "Under"] = mv.chance_css(un)
            if max(ch, un) >= 0.55:
                o_.at[k, "Lean"] = (f"color: {COLOR['stat_high'] if ch >= un else COLOR['warn']}; "
                                    f"font-weight: 800;")
        return o_
    if rows:
        st.dataframe(mv.painted(pd.DataFrame(rows), _paint), hide_index=True, width="stretch",
                     key=f"nfs_pl_{stat}")
    mv.render_chance_legend()
    st.caption("Line = the half-yard under his projection (TD: 0.5) — set your book's in the "
               "parlay builder. Over / Under = the Prop Lab's delivered chance (the model "
               "through what calls like it hit on unseen games).")

# ---------------- same-game parlay ----------------
with card("nfs_sgp"):
    st.markdown(f'<div class="pf-card-title" style="color:{COLOR["gold"]};">Same-game parlay'
                f'</div>',
                unsafe_allow_html=True)
    opts = ([("game", "home_win", f"{ha} to win"), ("game", "away_win", f"{aa} to win"),
             ("game", "total", "Total points"), ("game", "home_margin", f"{ha} spread"),
             ("game", "away_margin", f"{aa} spread")]
            + [("player", p["pid"], f"{p['name']} ({p['team']} {p['pos']})") for p in players])
    pmap = {p["pid"]: p for p in players}
    nlegs = st.number_input("Legs", 2, fs.SGP_MAX_LEGS, 2, key="nfs_n")
    legs, show = [], []
    for i in range(int(nlegs)):
        a, b, c, d = st.columns([3, 2, 1, 1])
        oi = a.selectbox(f"Leg {i + 1}", range(len(opts)), format_func=lambda k: opts[k][2],
                         key=f"nfs_o{i}", index=min(5 + i, len(opts) - 1))
        kind, key_, name = opts[oi]
        if kind == "player":
            p = pmap[key_]
            mine = [(s_, lab) for s_, lab in fs.STATS
                    if (p["proj"].get("td_exp" if s_ == "td" else s_) or 0) > 0]
            slab = b.selectbox("Stat", [lab for _s, lab in mine], key=f"nfs_s{i}_{key_}")
            st_ = next(s_ for s_, lab in mine if lab == slab)
            ln = c.number_input("Line", value=float(default_line(p, st_)), step=1.0,
                                key=f"nfs_l{i}_{key_}_{st_}")
            sd = d.selectbox("Side", ["Over", "Under"], key=f"nfs_d{i}")
            legs.append({"pid": key_, "stat": st_, "line": ln, "side": sd})
            show.append((f"{p['name']} {sd} {ln:g} {slab}", chance(p, st_, ln, sd)))
        elif key_ in ("home_win", "away_win"):
            b.markdown("Game")
            legs.append({"pid": "_game", "stat": key_, "line": 0.5, "side": "Over"})
            show.append((name, p_win(key_.split("_")[0])))
        else:
            b.markdown("Game")
            dflt = (float(o.get("total") or round(pj["mu_home"] + pj["mu_away"]) + 0.5)
                    if key_ == "total" else float(o.get("spread") or -2.5)
                    * (1 if key_ == "home_margin" else -1))
            ln = c.number_input("Line", value=dflt, step=0.5, key=f"nfs_l{i}_{key_}")
            sd = d.selectbox("Side", ["Over", "Under"], key=f"nfs_d{i}")
            # a spread of -3 covers when the margin is over 3
            leg = {"pid": "_game", "stat": key_, "line": (-ln if key_ != "total" else ln),
                   "side": sd}
            legs.append(leg)
            show.append((f"{name} {sd} {ln:g}", float(fs.leg_hits(sim, leg).mean())))
    with st.spinner(f"Playing this parlay {fs.SGP_SIMS:,} times…"):
        j = _legs_run(f"{g.get('event_id')}|{_json.dumps(legs, sort_keys=True)}", _gjs, _plist,
                      _spjs, _ljs, _json.dumps(legs))
    prod = (float(np.prod([c_ for _l, c_ in show])) if all(c_ is not None for _l, c_ in show)
            else None)
    if prod is not None and not j["lift"]:
        st.warning(f"In {fs.SGP_SIMS:,} games these legs never all hit together — the "
                   f"simulator can't price this one. Check the lines.")
    if prod is not None and j["lift"]:
        jp = min(0.999, prod * j["lift"])
        st.markdown(
            '<div style="font-size:var(--lc-text-body); line-height:1.8;">'
            + "<br>".join(f"{l_} — <b>{100 * c_:.0f}%</b>" for l_, c_ in show)
            + f'<br>Multiplied as strangers: <b>{100 * prod:.1f}%</b> · '
              + (f'they move together <b>x{j["lift"]:.2f}</b>' if j["lift"] - 2 * j["lift_se"] > 1
                 else f'they pull apart <b>x{j["lift"]:.2f}</b>' if j["lift"] + 2 * j["lift_se"] < 1
                 else f'no real link (<b>x{j["lift"]:.2f}</b>)')
            + f' <span style="color:{COLOR["text_muted"]};">(±{j["lift_se"]:.3f}, '
              f'{fs.SGP_SIMS:,} games)</span> → '
              f'<span style="{mv.chance_css(jp)} padding:2px 8px; border-radius:6px;">'
              f'<b>{100 * jp:.1f}%</b></span> · worth it at '
              f'<b>{mm.fmt_american(mm.fair_american(jp))}</b></div>', unsafe_allow_html=True)
        k1, k2 = st.columns(2)
        price = k1.number_input("Your book's SGP price", value=None, step=5, format="%d",
                                key="nfs_price")
        sup = fs.sgp_support(combos, legs, info)
        res = bf.judge(jp, price, _stk, None, sup)
        if res and res.get("guard"):
            res["guard"] = fs.sgp_guard(sup, res["tier"]) or res["guard"]
        if res:
            lab_, fg, _bg = mv.TIER_STYLE[res["tier"]]
            st.markdown(f'<span style="color:{fg if res["tier"] != "none" else COLOR["error"]}; '
                        f'font-weight:800;">{"SKIP" if res["tier"] == "none" else lab_}</span> '
                        f'· edge {100 * res["edge"]:+.1f} pts'
                        + (f' · stake ${res["stake"]:.2f}' if res.get("stake") else "")
                        + (f'<br><span style="color:{COLOR["warn"]};">{res["guard"]}</span>'
                           if res.get("guard") else ""), unsafe_allow_html=True)
            from engines import bet_log_ui as _blu
            _blu.log_button("NFL", "sgp", f"{labels[gi]}: " + " + ".join(l_ for l_, _c in show),
                            jp, price, res.get("stake"), res["tier"], [l_ for l_, _c in show],
                            "nfs_log")
            if k2.button("Add to parlay slip", key="nfs_add"):
                from engines import parlay as pl
                pl.add_leg(ss.setdefault("parlay", {}), "NFL", labels[gi],
                           "SGP: " + " + ".join(l_ for l_, _c in show), "same-game parlay",
                           jp, bf.valid_price(price), sup, res["tier"])
                st.success("On the slip (Bet Finder page) as one leg, its legs' link priced in.")
    if combos:
        mine_k = fs.combo_kind(legs, info)
        gr, vlist = [], []
        for kind in sorted(combos, key=lambda k_: (len(k_), k_)):
            x = combos[kind]
            gr.append({"Parlay": fs.KIND_LABEL.get(kind, kind) + ("  ← yours" if kind == mine_k
                                                                  else ""),
                       "Graded": x["n"], "Predicted": f"{100 * x['predicted_sim']:.1f}%",
                       "Multiplied": f"{100 * x['predicted_ind']:.1f}%",
                       "Hit": f"{100 * x['actual']:.1f}%",
                       "Verdict": mv.trust_label((x.get("verdict") or {}).get("verdict"))})
            vlist.append((x.get("verdict") or {}).get("verdict"))

        def _paint_g(frame):
            o_ = pd.DataFrame("", index=frame.index, columns=frame.columns)
            for k_ in frame.index:
                _n, fg_, bg_, _bd = mv.TRUST_STYLE.get(vlist[k_], mv.TRUST_STYLE[None])
                o_.at[k_, "Verdict"] = f"color: {fg_}; background-color: {bg_}; font-weight: 700;"
            return o_
        st.markdown('<div style="font-size:var(--lc-text-small); font-weight:700; '
                    'margin-top:8px;">What has been graded</div>', unsafe_allow_html=True)
        st.dataframe(mv.painted(pd.DataFrame(gr), _paint_g), hide_index=True, width="stretch",
                     key="nfs_graded")
        st.caption("Each row: same-game parlays of that kind built from real games (the top "
                   "quarterback, receivers, back and scorers, every leg an over at the player's "
                   "own average line). Predicted = the simulator's chance they all hit, "
                   "Multiplied = the legs as strangers, Hit = how often they really did. Any "
                   "other kind (an under, a total, catches) is priced the same way but stays at "
                   "THIN.")
    st.caption("Each leg is the Prop Lab's delivered chance (a team to win: the game model's, "
               "anchored to the market; a total or spread: the simulator's own); only the link "
               "between them comes from the simulator.")

footer()
