"""NHL Game Simulator (10-22) — play tonight's game 50,000 times.

Every simulated game draws each team's shot environment, every skater's
shots, his goals from his own shots, assists from the teammates on the
ice for them, overtime when it is tied — each link measured on last
season (engines/nhl_sim). The page shows the game's range of outcomes,
every skater's and goalie's, and prices a SAME-GAME PARLAY on how its
legs actually move together. Fits nothing at page time; simulates.
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
from engines import nhl_model as hm
from engines import nhl_periods as npd
from engines import nhl_sim as hs
from engines.slate_guard import payload_field, today_for
from engines.live_sync import sync_latest_button

from engines import sim_settings as _ss  # noqa: E402
SIM = _ss.settings("nhl")   # 10-26: hockey's own settings (engines/sim_settings)
N_SIMS = SIM["games"]
page_header("NHL Simulator", f"Play tonight's game {N_SIMS:,} times", eyebrow="NHL", align="left")
sync_latest_button(key="sync_nhl_sim", include_data_package=True)


@st.cache_data(ttl=900, show_spinner=False)
def _load(day):
    games, _sd, _cur = _li.load_slate_live("nhl")
    return games, payload_field("nhl", "model"), payload_field("nhl", "sim")


games, model, sim_meta = _load(today_for("nhl"))
_li.render_note("nhl")
model, sim_meta = model or {}, sim_meta or {}
games = [g for g in games or [] if (g.get("model") or {}).get("mu_home")
         and (g.get("home_props") or g.get("away_props")) and g.get("status") != "final"
         and g.get("game_type") != "preseason"]
if not games or not model:
    st.info("The simulator needs tonight's projections and the game model — both come from the "
            "nightly build.")
    footer()
    st.stop()

combos = sim_meta.get("combos") or {}
links = sim_meta.get("links") or hs.DEFAULT_LINKS
sog_disp = (model.get("skater_priors") or {}).get("sog_dispersion")
shot_disp = (model.get("shots") or {}).get("dispersion")
cal = mv.calibration_map(model.get("props_validation") or {}, hm.MARKETS)
cal_sv = mv.calibration_map(model.get("saves_validation") or {}, hm.SAVE_MARKETS)
per_meta = sim_meta.get("periods") or {}
per_test = per_meta.get("test") or {}
per_sh = (per_meta.get("shares") or links.get("shares") or npd.DEFAULT_SHARES)
cal_p1 = mv.calibration_map(per_test, npd.P1_MARKETS)
P1_LAB = {"p1pts": "1st-period points", "p1sog": "1st-period SOG", "p1g": "1st-period goals"}
beat = [hs.KIND_LABEL[k] for k, x in combos.items()
        if (x.get("verdict") or {}).get("verdict") == "beats" and k in hs.KIND_LABEL]
st.markdown(
    f'<div style="font-size:var(--lc-text-body); line-height:1.6; color:{COLOR["text"]};">'
    f'Each run draws how many shots each team gets, every skater&rsquo;s shots, his goals '
    f'<b>from his own shots</b>, the assists on them and overtime when it&rsquo;s tied. Each skater '
    f'on his own still prices like the props boards &mdash; what the simulator adds is how the '
    f'legs of a <b>same-game parlay</b> move together.<br>'
    f'<span style="color:{COLOR["text_muted"]};">Graded on real games (last season&rsquo;s final '
    f'60 days plus this season so far): '
    + (("beats simply multiplying the legs for " + "; ".join(beat) + " — those can reach "
        "STRONG; every other kind stays at THIN") if beat else
       "no kind of parlay has beaten simply multiplying its legs yet, so every same-game "
       "parlay here stays at THIN")
    + '.</span></div>', unsafe_allow_html=True)

_stk = mv.staking_controls("nhl_sim")
ss = st.session_state
labels = [f"{g.get('away_abbr')} @ {g.get('home_abbr')}  {g.get('time_et') or ''}".strip()
          for g in games]
gi = st.selectbox("Game", range(len(games)), format_func=lambda i: labels[i], key="nhs_game")
g = games[gi]
pj = g["model"]
ha, aa = g.get("home_abbr"), g.get("away_abbr")
players, side_of = [], {}
for side in ("away", "home"):
    for r in g.get(side + "_props") or []:
        if av.is_out(r.get("status")):
            continue
        players.append({"pid": str(r["pid"]), "side": side, "mu": r["mu"], "name": r["name"],
                        "team": g.get(side + "_abbr"), "row": r})
        side_of[str(r["pid"])] = side
goalie = {s: (g.get(s + "_goalie_props") or [None])[0] for s in ("home", "away")}


def _shots(side):
    """The team's expected shots: what the OTHER side's goalie is projected
    to face (the shots model), else its skaters' projected shots."""
    other = goalie["away" if side == "home" else "home"]
    if other and other.get("exp_sa"):
        return float(other["exp_sa"])
    return sum(float(p["mu"].get("sog") or 0) for p in players if p["side"] == side)


game_in = {"mu_home": pj["mu_home"], "mu_away": pj["mu_away"],
           "shots_home": _shots("home"), "shots_away": _shots("away")}
if not players:
    st.info("No projected skaters for this game yet.")
    footer()
    st.stop()


@st.cache_resource(ttl=900, show_spinner=False, max_entries=SIM["keep"])   # one shared copy
def _run(key, game_js, plist, links_js, sog_size):
    import zlib
    return _ss.run("nhl", hs.simulate, _json.loads(game_js), _json.loads(plist),
                   _json.loads(links_js), sog_size, seed=zlib.crc32(key.encode()))


@st.cache_data(ttl=900, show_spinner=False, max_entries=64)
def _legs_run(key, game_js, plist, links_js, sog_size, legs):
    import zlib
    return hs.joint_precise(_json.loads(game_js), _json.loads(plist), _json.loads(links_js),
                            sog_size, _json.loads(legs), n=SIM["sgp"], chunk=SIM["sgp_chunk"],
                            seed=zlib.crc32(key.encode()))


_plist = _json.dumps([{k: p[k] for k in ("pid", "side", "mu")} for p in players])
_gjs = _json.dumps(game_in)
_ljs = _json.dumps(links, default=float)
with st.spinner(f"Simulating {N_SIMS:,} games…"):
    sim = _run(f"{g.get('event_id')}|{len(players)}", _gjs, _plist, _ljs, sog_disp)
home, away = sim["home"], sim["away"]


def _pc(p):
    return "<1%" if p < 0.005 else (">99%" if p > 0.995 else f"{100 * p:.0f}%")


def _rng(arr):
    return f"{np.percentile(arr, 10):.0f}–{np.percentile(arr, 90):.0f}"


def p_win(side):
    """The win chance the site prices bets with (the game model, anchored
    to the market by its fitted weight)."""
    ph = pj.get("p_home_final", pj.get("p_home"))
    return ph if side == "home" else 1 - ph


# ---------------- the game ----------------
with card("nhs_game"):
    ph_sim = float((home > away).mean())
    st.markdown(f'<div class="pf-card-title" style="color:{COLOR["gold"]};">{aa} @ {ha} — '
                f'played {N_SIMS:,} times</div>', unsafe_allow_html=True)

    def _team(abbr, gl, win, logo):
        hot = win >= 0.5
        img = (f'<img src="{logo}" style="height:40px; vertical-align:middle; margin-right:8px;">'
               if logo else "")
        return (f'<div style="flex:1 1 220px; padding:14px 16px; border-radius:12px; '
                f'border:1px solid {COLOR["stat_high"] if hot else "rgba(152,163,173,0.25)"}; '
                f'background:{"rgba(59,184,255,0.08)" if hot else "transparent"};">'
                f'<div style="font-size:1.15em; font-weight:800;">{img}{abbr}</div>'
                f'<div style="font-size:3em; font-weight:800; line-height:1.1; '
                f'color:{COLOR["stat_high"] if hot else COLOR["text"]};">{np.mean(gl):.1f}</div>'
                f'<div style="font-size:var(--lc-text-small); color:{COLOR["text_muted"]};">'
                f'goals on average · wins <b style="color:{COLOR["text"]};">{100 * win:.0f}%</b>'
                f' of games</div></div>')
    o = g.get("odds") or {}
    total = home + away
    margin = home - away
    tot_line = f'Total goals: typically <b>{np.median(total):.0f}</b>, {_rng(total)} most nights'
    if o.get("total") is not None:
        po = float((total > o["total"]).mean())
        tot_line += (f' · over the book\'s {o["total"]:g}: <b>{100 * po:.0f}%</b>, '
                     f'under <b>{100 * (1 - po):.0f}%</b>')
    pl_h = float((margin >= 2).mean())
    pl_a = float((margin <= -2).mean())
    st.markdown(
        f'<div style="display:flex; gap:12px; flex-wrap:wrap; margin:6px 0 10px;">'
        f'{_team(aa, away, 1 - ph_sim, g.get("away_logo"))}'
        f'{_team(ha, home, ph_sim, g.get("home_logo"))}</div>'
        f'<div style="font-size:var(--lc-text-body); line-height:1.8;">{tot_line}<br>'
        f'Goes to overtime: <b>{100 * float(sim["ot"].mean()):.0f}%</b> · wins by 2+ (the puck '
        f'line): {ha} <b>{100 * pl_h:.0f}%</b>, {aa} <b>{100 * pl_a:.0f}%</b>'
        + (f' · book: {o["details"]}' if o.get("details") else "") + '</div>',
        unsafe_allow_html=True)
    lab = [f"{aa} by 3+", f"{aa} by 2", f"{aa} by 1", f"{ha} by 1", f"{ha} by 2", f"{ha} by 3+"]
    counts = [int((margin <= -3).sum()), int((margin == -2).sum()), int((margin == -1).sum()),
              int((margin == 1).sum()), int((margin == 2).sum()), int((margin >= 3).sum())]
    shares = [c / N_SIMS for c in counts]
    dist = pd.DataFrame({"How it ends": lab,
                         "Share of games": [f"{100 * x:.0f}%" for x in shares]})

    def _paint_d(frame):
        o_ = pd.DataFrame("", index=frame.index, columns=frame.columns)
        top = max(shares) or 1
        for k in frame.index:
            a_ = 0.10 + 0.45 * shares[k] / top
            o_.at[k, "Share of games"] = (f"background-color: rgba(59,184,255,{a_:.2f}); "
                                          f"font-weight: 700;")
        return o_
    st.dataframe(mv.painted(dist, _paint_d), hide_index=True, width="stretch", key="nhs_dist")
    st.caption("Big number = the team's average goals across the simulated games (overtime "
               "goal included); 'most nights' = 8 of 10 games land in that range. 'By 1' "
               "includes overtime and shootout wins. Win chances here are the simulator's; "
               "a bet on the moneyline is priced on the Bet Finder with the game model's "
               "tested weight against the book.")

# ---------------- the box score ----------------
with card("nhs_box"):
    st.markdown(f'<div class="pf-card-title" style="color:{COLOR["gold"]};">The box score — '
                f'{N_SIMS:,} games</div>', unsafe_allow_html=True)
    for side, abbr in (("away", aa), ("home", ha)):
        mine = sorted([p for p in players if p["side"] == side],
                      key=lambda p: -((p["mu"].get("g") or 0) + (p["mu"].get("a") or 0)))
        if not mine:
            continue
        brow = []
        for p in mine:
            a_ = sim["stats"][p["pid"]]
            brow.append({"Player": f"{p['name']} ({p['row'].get('pos') or ''})",
                         "SOG": f"{a_['sog'].mean():.1f}  ({_rng(a_['sog'])})",
                         "Goal": _pc(float((a_['g'] > 0).mean())),
                         "Point": _pc(float((a_['pts'] > 0).mean())),
                         "2+ pts": _pc(float((a_['pts'] > 1).mean())),
                         "Assist": _pc(float((a_['a'] > 0).mean()))})
        st.markdown(f"**{abbr}** — {np.mean(sim['shots'][side]):.0f} shots, "
                    f"{np.mean(home if side == 'home' else away):.1f} goals on average")
        st.dataframe(pd.DataFrame(brow), hide_index=True, width="stretch",
                     key=f"nhs_box_{side}")
        gk = goalie[side]
        if gk:
            sv = sim["saves"][side]
            st.caption(f"{gk.get('name')} (projected starter): {np.mean(sv):.1f} saves on average, "
                       f"{_rng(sv)} most nights.")
    st.caption("SOG = his average shots, then the range 8 of 10 games land in. Goal / Point / "
               "2+ pts / Assist = how often he gets one across the simulated games. The goalie "
               "line assumes the team's most-used goalie starts — check the confirmed starter.")


# ---------------- leg chances (as the boards deliver them) ----------------
def skater_chance(row, stat, line, side="Over"):
    """(delivered chance, raw, support) for one skater leg — the props
    model's pmf through the props test's curve, like the Bet Finder."""
    p1 = stat.startswith("p1")
    pm = (npd.p1_pmfs(row.get("mu"), per_sh, sog_disp) if p1
          else hm.skater_pmfs(row.get("mu"), sog_disp)).get(stat)
    if not pm:
        return None, None, None
    mk, cm = (npd.P1_MARKETS, cal_p1) if p1 else (hm.MARKETS, cal)
    raw = mm.prob_at_least(pm, int(math.floor(line)) + 1)
    ch, _basis = mv.delivered_over(raw, stat, line, mk, cm)
    sup = mv.support_for(raw, stat, line, mk, cm)
    return (ch if side == "Over" else 1 - ch), raw, sup


def saves_chance(gk, line, side="Over"):
    pm = hm.saves_pmf(gk.get("exp_sa"), shot_disp, gk.get("sv_pct"))
    if not pm:
        return None
    raw = mm.prob_at_least(pm, int(math.floor(line)) + 1)
    ch, _b = mv.delivered_over(raw, "sv", line, hm.SAVE_MARKETS, cal_sv)
    return ch if side == "Over" else 1 - ch


def default_line(row, stat):
    if stat == "p1sog":
        return max(0.5, math.floor(float(row["mu"].get("sog") or 0) * per_sh["sog"][0]) + 0.5)
    if stat == "sog":
        return max(0.5, math.floor(float(row["mu"].get("sog") or 0)) + 0.5)
    return 0.5


# ---------------- the 1st period ----------------
with card("nhs_p1"):
    st.markdown(f'<div class="pf-card-title" style="color:{COLOR["gold"]};">The 1st period'
                f'</div>', unsafe_allow_html=True)
    ph1, pa1 = sim["per"]["home"][:, 0], sim["per"]["away"][:, 0]
    t1 = npd.team_p1(float(pj["mu_home"]), float(pj["mu_away"]), per_sh)

    def _verd(k):
        return mv.trust_label(((per_test.get(k) or {}).get("verdict") or {}).get("verdict"))
    st.markdown(
        f'<div style="font-size:var(--lc-text-body); line-height:1.8;">'
        f'Goals in the 1st: {aa} <b>{pa1.mean():.2f}</b>, {ha} <b>{ph1.mean():.2f}</b> on average '
        f'(the 1st holds {100 * per_sh["goals"][0]:.0f}% of a game&rsquo;s goals, '
        f'{100 * per_sh["sog"][0]:.0f}% of its shots).<br>'
        f'Over 1.5 goals in the 1st: <b>{_pc(t1["p1tot15"])}</b> '
        f'<span style="color:{COLOR["text_muted"]};">({_verd("p1tot15")})</span><br>'
        f'After one: {ha} leads <b>{_pc(t1["p1lead_home"])}</b> '
        f'<span style="color:{COLOR["text_muted"]};">({_verd("p1lead_home")})</span>, tied '
        f'<b>{_pc(t1["p1tie"])}</b>, {aa} leads <b>{_pc(t1["p1lead_away"])}</b></div>',
        unsafe_allow_html=True)
    prow, pchs = [], []
    for p in sorted(players, key=lambda p: -float(p["mu"].get("sog") or 0)):
        c = {k: skater_chance(p["row"], st_, n - 0.5)[0] for k, _l, st_, n in npd.P1_MARKETS}
        pchs.append(c)
        prow.append({"Player": f"{p['name']} ({p['team']})",
                     "Point": _pc(c["p1pt"]) if c["p1pt"] is not None else "—",
                     "Goal": _pc(c["p1g"]) if c["p1g"] is not None else "—",
                     "1+ SOG": _pc(c["p1sog1"]) if c["p1sog1"] is not None else "—",
                     "2+ SOG": _pc(c["p1sog2"]) if c["p1sog2"] is not None else "—"})
    _cols = {"Point": "p1pt", "Goal": "p1g", "1+ SOG": "p1sog1", "2+ SOG": "p1sog2"}

    def _paint_p1(frame):
        o_ = pd.DataFrame("", index=frame.index, columns=frame.columns)
        for k_ in frame.index:
            for col, mk_ in _cols.items():
                if pchs[k_][mk_] is not None:
                    o_.at[k_, col] = mv.chance_css(pchs[k_][mk_])
        return o_
    st.dataframe(mv.painted(pd.DataFrame(prow), _paint_p1), hide_index=True, width="stretch",
                 key="nhs_p1_tab")
    st.caption("Each skater's 1st period: his game projection at the share of goals and shots "
               "the 1st period MEASURED last season, through what those calls delivered on "
               "unseen games. Graded against his own last-20 1st-period rate: "
               + "; ".join(f"{lab} — {_verd(k)}" for k, lab, *_ in npd.P1_MARKETS)
               + ". Team lines are the game model's goals at the 1st-period share.")


# ---------------- every skater ----------------
with card("nhs_players"):
    st.markdown(f'<div class="pf-card-title" style="color:{COLOR["gold"]};">Every skater — '
                f'over or under?</div>', unsafe_allow_html=True)
    c1, c2 = st.columns([2, 1])
    stat_lab = c1.selectbox("Stat", [lab for _s, lab in hs.STATS], key="nhs_stat")
    stat = next(s_ for s_, lab in hs.STATS if lab == stat_lab)
    fixed = c2.number_input("Line (blank = his usual)", value=None, step=1.0, min_value=0.5,
                            key=f"nhs_line_{stat}")
    rows, sides = [], []
    for p in sorted(players, key=lambda p: -float(p["mu"].get(stat if stat != "pts" else "a")
                                                  or 0) - (float(p["mu"].get("g") or 0)
                                                           if stat == "pts" else 0)):
        line = fixed if fixed else default_line(p["row"], stat)
        line = math.floor(line) + 0.5
        ch = skater_chance(p["row"], stat, line)[0]
        arr = sim["stats"][p["pid"]][stat]
        un = None if ch is None else 1 - ch
        lean = ("—" if ch is None else f"OVER {_pc(ch)}" if ch >= 0.55 else
                f"UNDER {_pc(un)}" if un >= 0.55 else "toss-up")
        sides.append((ch, un))
        rows.append({"Player": f"{p['name']} ({p['team']})", "Line": f"{line:g}",
                     "Average": f"{arr.mean():.2f}", "Over": "—" if ch is None else _pc(ch),
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
    st.dataframe(mv.painted(pd.DataFrame(rows), _paint), hide_index=True, width="stretch",
                 key=f"nhs_pl_{stat}")
    mv.render_chance_legend()
    st.caption("Over / Under = his chance as the props boards deliver it (the model's number "
               "through what calls like it hit on last season's unseen games). Shots default to "
               "the half-line under his projection; goals, assists and points to 0.5. A lean is "
               "not a bet until your book's price is checked (Bet Finder).")

# ---------------- same-game parlay ----------------
SGP_STATS = tuple(hs.STATS) + tuple((s_, lab) for s_, lab, _l in npd.P1_STATS)
with card("nhs_sgp"):
    st.markdown(f'<div class="pf-card-title" style="color:{COLOR["gold"]};">Same-game parlay'
                f'</div>',
                unsafe_allow_html=True)
    opts = ([("game", "home_win", f"{ha} to win"), ("game", "away_win", f"{aa} to win"),
             ("game", "total", "Total goals"), ("game", "home_margin", f"{ha} puck line"),
             ("game", "away_margin", f"{aa} puck line"),
             ("game", "p1_total", "1st-period total goals"),
             ("game", "p1_home_win", f"{ha} leads after the 1st"),
             ("game", "p1_away_win", f"{aa} leads after the 1st")]
            + [("goalie", s_, f"{goalie[s_]['name']} saves ({ha if s_ == 'home' else aa})")
               for s_ in ("away", "home") if goalie[s_]]
            + [("skater", p["pid"], f"{p['name']} ({p['team']})") for p in players])
    nlegs = st.number_input("Legs", 2, hs.SGP_MAX_LEGS, 2, key="nhs_n")
    legs, show = [], []
    pmap = {p["pid"]: p for p in players}
    for i in range(int(nlegs)):
        a, b, c, d = st.columns([3, 2, 1, 1])
        oi = a.selectbox(f"Leg {i + 1}", range(len(opts)), format_func=lambda k: opts[k][2],
                         key=f"nhs_o{i}", index=min(len(opts) - len(players) + i,
                                                     len(opts) - 1))
        kind, key, name = opts[oi]
        if kind == "skater":
            slab = b.selectbox("Stat", [lab for _s, lab in SGP_STATS], key=f"nhs_s{i}",
                               index=3)
            st_ = next(s_ for s_, lab in SGP_STATS if lab == slab)
            p = pmap[key]
            ln = c.number_input("Line", value=float(default_line(p["row"], st_)), step=1.0,
                                key=f"nhs_l{i}_{key}_{st_}")
            ln = math.floor(ln) + 0.5
            sd = d.selectbox("Side", ["Over", "Under"], key=f"nhs_d{i}")
            ch = skater_chance(p["row"], st_, ln, sd)[0]
            legs.append({"pid": key, "stat": st_, "line": ln, "side": sd})
            show.append((f"{p['name']} {sd} {ln:g} {slab}", ch))
        elif kind == "goalie":
            b.markdown("Saves")
            gk = goalie[key]
            ln = c.number_input("Line", value=float(math.floor(gk.get("exp_saves") or 25) + 0.5),
                                step=1.0, key=f"nhs_l{i}_g{key}")
            ln = math.floor(ln) + 0.5
            sd = d.selectbox("Side", ["Over", "Under"], key=f"nhs_d{i}")
            legs.append({"pid": f"_goalie_{key}", "stat": "sv", "line": ln, "side": sd})
            show.append((f"{gk['name']} {sd} {ln:g} saves", saves_chance(gk, ln, sd)))
        else:
            b.markdown("Game")
            if key in ("home_win", "away_win"):
                legs.append({"pid": "_game", "stat": key, "line": 0.5, "side": "Over"})
                show.append((name, p_win(key.split("_")[0])))
            elif key in ("p1_home_win", "p1_away_win"):
                # leads after one: regulation 1st-period goals, ties lose
                leg = {"pid": "_game", "stat": key.replace("_win", "_margin"), "line": 0.5,
                       "side": "Over"}
                legs.append(leg)
                show.append((name, t1["p1lead_" + key.split("_")[1]]))
            elif key == "p1_total":
                ln = c.number_input("Line", value=1.5, step=1.0, key=f"nhs_l{i}_{key}")
                sd = d.selectbox("Side", ["Over", "Under"], key=f"nhs_d{i}")
                leg = {"pid": "_game", "stat": "p1_total", "line": ln, "side": sd}
                legs.append(leg)
                pt = (t1["p1tot15"] if ln == 1.5 else float(hs.leg_hits(sim, dict(
                    leg, side="Over")).mean()))
                show.append((f"{name} {sd} {ln:g}", pt if sd == "Over" else 1 - pt))
            else:
                dflt = (float(o.get("total") or 5.5) if key == "total" else -1.5)
                ln = c.number_input("Line", value=dflt, step=1.0, key=f"nhs_l{i}_{key}")
                sd = d.selectbox("Side", ["Over", "Under"], key=f"nhs_d{i}")
                # the puck line: -1.5 means win by 2+ (margin over 1.5)
                leg = {"pid": "_game", "stat": key, "line": (-ln if key != "total" else ln),
                       "side": sd}
                legs.append(leg)
                show.append((f"{name} {sd} {ln:g}", float(hs.leg_hits(sim, leg).mean())))
    with st.spinner(f"Playing this parlay {hs.SGP_SIMS:,} times…"):
        j = _legs_run(f"{g.get('event_id')}|{_json.dumps(legs, sort_keys=True)}", _gjs, _plist,
                      _ljs, sog_disp, _json.dumps(legs))
    prod = (float(np.prod([c_ for _l, c_ in show])) if all(c_ is not None for _l, c_ in show)
            else None)
    if prod is not None and not j["lift"]:
        st.warning(f"In {hs.SGP_SIMS:,} games these legs never all hit together — the "
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
              f'{hs.SGP_SIMS:,} games)</span> → '
              f'<span style="{mv.chance_css(jp)} padding:2px 8px; border-radius:6px;">'
              f'<b>{100 * jp:.1f}%</b></span> · worth it at '
              f'<b>{mm.fmt_american(mm.fair_american(jp))}</b></div>', unsafe_allow_html=True)
        k1, k2 = st.columns(2)
        price = k1.number_input("Your book's SGP price", value=None, step=5, format="%d",
                                key="nhs_price")
        sup = hs.sgp_support(combos, legs, side_of)
        res = bf.judge(jp, price, _stk, None, sup)
        if res and res.get("guard"):
            res["guard"] = hs.sgp_guard(sup, res["tier"]) or res["guard"]
        if res:
            lab_, fg, _bg = mv.TIER_STYLE[res["tier"]]
            st.markdown(f'<span style="color:{fg if res["tier"] != "none" else COLOR["error"]}; '
                        f'font-weight:800;">{"SKIP" if res["tier"] == "none" else lab_}</span> '
                        f'· edge {100 * res["edge"]:+.1f} pts'
                        + (f' · stake ${res["stake"]:.2f}' if res.get("stake") else "")
                        + (f'<br><span style="color:{COLOR["warn"]};">{res["guard"]}</span>'
                           if res.get("guard") else ""), unsafe_allow_html=True)
            from engines import bet_log_ui as _blu
            _blu.log_button("NHL", "sgp", f"{labels[gi]}: " + " + ".join(l_ for l_, _c in show),
                            jp, price, res.get("stake"), res["tier"], [l_ for l_, _c in show],
                            "nhs_log")
            if k2.button("Add to parlay slip", key="nhs_add"):
                from engines import parlay as pl
                pl.add_leg(ss.setdefault("parlay", {}), "NHL", labels[gi],
                           "SGP: " + " + ".join(l_ for l_, _c in show), "same-game parlay",
                           jp, bf.valid_price(price), sup, res["tier"])
                st.success("On the slip (Bet Finder page) as one leg, its legs' link priced in.")
    if combos:
        mine = hs.combo_kind(legs, side_of)
        gr, vlist = [], []
        for kind in sorted(combos, key=lambda k_: (len(k_.replace("opp", "")), k_)):
            x = combos[kind]
            gr.append({"Parlay": hs.KIND_LABEL.get(kind, kind) + ("  ← yours" if kind == mine
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
                     key="nhs_graded")
        st.caption("Each row: same-game parlays of that kind built from real games (the top "
                   "point-getters, scorers and shooters, every leg an over — points and goals at "
                   "0.5, shots at his own last-10 line). Predicted = the simulator's chance they "
                   "all hit, Multiplied = the legs as strangers, Hit = how often they really did. "
                   "A parlay of any other kind (an under, a total, saves) is priced the same way "
                   "but stays at THIN.")
    st.caption("Each leg is the boards' delivered chance (a team to win: the game model's, "
               "anchored to the market; a total or puck line: the simulator's own); only the "
               "link between them comes from the simulator. Linemates move together — one's "
               "goal is often the other's assist.")

footer()
