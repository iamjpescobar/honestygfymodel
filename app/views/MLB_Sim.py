"""MLB Game Simulator (10-22) — play today's game 25,000 times, plate
appearance by plate appearance.

Every PA is the batter against the starter (the props model's own
per-PA numbers) until the starter has faced his drawn number of batters,
then the bullpen; what each play does to the runners, the outs and the
score is drawn from the season's real plate appearances in that base-out
state (engines/mlb_sim). The page shows the game's range of outcomes,
the first five innings, every batter's and both starters' lines, and
prices a SAME-GAME PARLAY on how its legs move together. Fits nothing at
page time; simulates.
"""
import json as _json
import math
from datetime import datetime
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import streamlit as st

from styles.kc_theme import COLOR, card, footer, page_header
from engines import bet_finder as bf
from engines import mlb_game_model as mgm
from engines import mlb_props as mp
from engines import mlb_sim as ms
from engines import model_math as mm
from engines import model_view as mv
from engines.lineup_slot import _slot_from_batting_order
from engines.roster import get_confirmed_lineup, get_last_starting_lineup
from engines.team_abbreviations import team_abbr
from engines.weather_engine import get_todays_games_with_weather
from engines.live_sync import sync_latest_button

EASTERN = ZoneInfo("America/New_York")
N_SIMS = 25_000   # 10-23: 10,000 -> 25,000 (simulator noise on a 50% chance ±0.5 -> ±0.32 pts); ~1-2 s
page_header("MLB Simulator", f"Play today's game {N_SIMS:,} times, pitch to pitch outcomes",
            eyebrow="MLB", align="left")
sync_latest_button(key="sync_mlb_sim", include_data_package=True)

pm = mp.load_prop_model() or {}
simblk = pm.get("sim") or {}
if not pm or not simblk.get("transitions"):
    st.info("The simulator needs the nightly's prop model with its base-running table "
            + (f"({simblk['note']})" if simblk.get("note") else "")
            + " — it appears after the next nightly data run.")
    footer()
    st.stop()


@st.cache_resource(show_spinner=False)
def _tab(stamp):
    return ms.tables(simblk["transitions"])


tab = _tab(f"{pm.get('through')}|{(simblk.get('transitions') or {}).get('n')}")
combos = simblk.get("combos") or {}
beat = [ms.KIND_LABEL[k] for k, x in combos.items()
        if (x.get("verdict") or {}).get("verdict") == "beats" and k in ms.KIND_LABEL]
rc = simblk.get("runs_check") or {}
st.markdown(
    f'<div style="font-size:var(--lc-text-body); line-height:1.6; color:{COLOR["text"]};">'
    f'Each run plays the game <b>plate appearance by plate appearance</b>: every batter against '
    f'the starter (the props model&rsquo;s own numbers) until the starter is pulled, then the '
    f'bullpen; what each hit, walk or out does to the runners and the score is drawn from this '
    f'season&rsquo;s real plays in the same spot. Each batter on his own still prices like the '
    f'prop board &mdash; what the simulator adds is how the legs of a <b>same-game parlay</b> '
    f'move together.<br><span style="color:{COLOR["text_muted"]};">'
    + (f'Check: simulated games average {rc.get("sim")} runs a team against {rc.get("actual")} '
       f'in the real ones. ' if rc.get("sim") else "")
    + 'Graded on the last 30 days of games: '
    + (("beats simply multiplying the legs for " + "; ".join(beat) + " — those can reach "
        "STRONG; every other kind stays at THIN") if beat else
       "no kind of parlay has beaten simply multiplying its legs yet, so every same-game "
       "parlay here stays at THIN")
    + '.</span></div>', unsafe_allow_html=True)

_stk = mv.staking_controls("mlb_sim")
ss = st.session_state
_today = datetime.now(EASTERN).strftime("%Y-%m-%d")
games, err = get_todays_games_with_weather(_today)
if err:
    st.warning(f"Schedule unavailable right now ({err}).")
games = [g for g in games or [] if g.get("home") and g.get("away")]
if not games:
    st.info("No MLB games today.")
    footer()
    st.stop()
labels = [f"{team_abbr(g.get('away'))} @ {team_abbr(g.get('home'))}  "
          f"{g.get('away_pitcher') or 'TBD'} vs {g.get('home_pitcher') or 'TBD'}" for g in games]
gi = st.selectbox("Game", range(len(games)), format_func=lambda i: labels[i], key="mls_game")
g = games[gi]
ha, aa = team_abbr(g.get("home")), team_abbr(g.get("away"))
league = pm.get("league_rates") or {}


def _lineup(side, team):
    lineup, confirmed = get_confirmed_lineup(g.get("game_pk"), side)
    batters = [p for p in (lineup or []) if not p.get("is_pitcher")]
    src = "confirmed lineup"
    if not confirmed or not batters:
        last, last_date, ok = get_last_starting_lineup(team)
        batters = [p for p in (last or []) if not p.get("is_pitcher")] if ok else []
        src = f"projected — last game's lineup ({last_date})" if ok else "no lineup"
    seen, order = set(), []
    for i, b in enumerate(batters):
        slot = _slot_from_batting_order(b.get("battingOrder")) or (i + 1)
        if slot in seen or not (1 <= slot <= 9):
            continue
        seen.add(slot)
        order.append((slot, b))
    order.sort(key=lambda x: x[0])
    return order, src


@st.cache_data(ttl=900, show_spinner=False)
def _counts(kind, pid):
    from engines.statcast_engine import _get_batter_df, _get_pitcher_df
    try:
        df, _e = (_get_batter_df if kind == "batter" else _get_pitcher_df)(int(pid))
        c = mp.outcome_counts(df)
    except Exception:  # noqa: BLE001 — no record is no record
        c = None
    return mp.player_counts(pm, pid, c, kind)


def _bf(pid):
    return mp.starter_bf_dist((pm.get("starter_bf") or {}).get(str(pid)), pm,
                              (pm.get("prior_bf") or {}).get(str(pid))) if pid else None


sides, info, players, problems = {}, {}, [], []
sp_id = {"home": g.get("home_pitcher_id"), "away": g.get("away_pitcher_id")}
sp_name = {"home": g.get("home_pitcher") or "TBD", "away": g.get("away_pitcher") or "TBD"}
for side, team in (("away", g.get("away")), ("home", g.get("home"))):
    order, src = _lineup(side, team)
    opp = "home" if side == "away" else "away"
    pc = _counts("pitcher", sp_id[opp]) if sp_id[opp] else None
    p_rates = mp.shrunk_rates(pc, pm.get("pitcher_priors")) if pc and pc.get("PA") else None
    bf_opp = _bf(sp_id[opp])
    if len(order) < 9:
        problems.append(f"{team_abbr(team)}: {src} has {len(order)} of 9 bats")
        continue
    vs_sp, vs_pen, pids = [], [], []
    for slot, b in order:
        bc = _counts("batter", b.get("id"))
        br = mp.shrunk_rates(bc, pm.get("batter_priors"))
        vs_sp.append(mp.combine(br, p_rates, league))
        vs_pen.append(br)
        pid = str(b.get("id"))
        pids.append(pid)
        proj = mp.project_batter(slot, bc, pc, pm, bf_opp) if bc.get("PA") else None
        players.append({"pid": pid, "name": b.get("name"), "side": side, "slot": slot,
                        "team": team_abbr(team), "pmfs": (proj or {}).get("pmfs") or {},
                        "pa": bc.get("PA", 0), "counts": bc})
        info[pid] = side
    sides[side] = {"pids": pids, "vs_sp": vs_sp, "vs_pen": vs_pen, "bf": _bf(sp_id[side]) or {},
                   "sp": str(sp_id[side] or ""), "src": src}
if problems or len(sides) < 2:
    st.info("The simulator needs both nine-man lineups: " + "; ".join(problems))
    footer()
    st.stop()

# the starters' own boards (props model): his pmfs against the lineup he faces
sp_pmfs = {}
for side in ("home", "away"):
    opp = "home" if side == "away" else "away"
    pc = _counts("pitcher", sp_id[side]) if sp_id[side] else None
    order = [p["counts"] for p in players if p["side"] == opp]
    pp = mp.project_pitcher(order, pc, pm, sides[side]["bf"]) \
        if (pc and pc.get("PA") and sides[side]["bf"]) else None
    sp_pmfs[side] = pp


@st.cache_data(ttl=900, show_spinner=False, max_entries=4)   # a run is ~5x the 10k one's memory
def _run(key, game_js):
    import zlib
    return ms.simulate(_json.loads(game_js), _tab(f"{pm.get('through')}|"
                                                  f"{(simblk.get('transitions') or {}).get('n')}"),
                       n=N_SIMS, seed=zlib.crc32(key.encode()))


@st.cache_data(ttl=900, show_spinner=False, max_entries=64)
def _legs_run(key, game_js, legs):
    import zlib
    return ms.joint_precise(_json.loads(game_js),
                            _tab(f"{pm.get('through')}|{(simblk.get('transitions') or {}).get('n')}"),
                            _json.loads(legs), seed=zlib.crc32(key.encode()))


_gjs = _json.dumps({s: {k: v for k, v in sides[s].items() if k != "src"} for s in sides})
with st.spinner(f"Simulating {N_SIMS:,} games…"):
    sim = _run(f"{g.get('game_pk')}|{_gjs[:200]}|{len(_gjs)}", _gjs)
home, away = sim["home"], sim["away"]


def _pc(p):
    return "<1%" if p < 0.005 else (">99%" if p > 0.995 else f"{100 * p:.0f}%")


def _rng(arr):
    return f"{np.percentile(arr, 10):.0f}–{np.percentile(arr, 90):.0f}"


cal_b, cal_p = mv.mlb_calibration(), mv.mlb_calibration(pitcher=True)
odds = mgm.posted_lines().get(g.get("game_pk")) or {}
proj = mgm.project_game(g.get("home"), g.get("away"), sp_id["home"], sp_id["away"], market=odds)


def bat_chance(p, stat, line, side="Over"):
    """The prop board's delivered chance where the props model prices the
    stat; runs and H+R+RBI (not on the board) from the simulator."""
    pmf = (p.get("pmfs") or {}).get(stat)
    if pmf:
        raw = mm.prob_at_least(pmf, int(math.floor(line)) + 1)
        ch, _b = mv.delivered_over(raw, stat, line, mp.MARKETS, cal_b)
    else:
        ch = float((sim["stats"][p["pid"]][stat] > line).mean())
    return ch if side == "Over" else 1 - ch


def sp_chance(side, stat, line, sd="Over"):
    pp = sp_pmfs.get(side) or {}
    pmf = (pp.get("pmfs") or {}).get(stat)
    if pmf and stat in ("k", "h"):
        raw = mm.prob_at_least(pmf, int(math.floor(line)) + 1)
        ch, _b = mv.delivered_over(raw, stat, line, mp.PITCHER_MARKETS, cal_p)
    else:
        ch = float((sim["sp"][side][stat] > line).mean())
    return ch if sd == "Over" else 1 - ch


def p_win(side):
    if proj and proj.get("p_home") is not None:
        ph = proj.get("p_home_final", proj.get("p_home"))
        return ph if side == "home" else 1 - ph
    ph = float((home > away).mean())
    return ph if side == "home" else 1 - ph


# ---------------- the game ----------------
with card("mls_game"):
    ph_sim = float((home > away).mean())
    st.markdown(f'<div class="pf-card-title" style="color:{COLOR["gold"]};">{aa} @ {ha} — '
                f'played {N_SIMS:,} times</div><div class="pf-card-subtitle">'
                f'{sp_name["away"]} vs {sp_name["home"]} · {sides["away"]["src"]} / '
                f'{sides["home"]["src"]}</div>', unsafe_allow_html=True)

    def _team(abbr, runs, win):
        hot = win >= 0.5
        return (f'<div style="flex:1 1 220px; padding:14px 16px; border-radius:12px; '
                f'border:1px solid {COLOR["stat_high"] if hot else "rgba(152,163,173,0.25)"}; '
                f'background:{"rgba(59,184,255,0.08)" if hot else "transparent"};">'
                f'<div style="font-size:1.15em; font-weight:800;">{abbr}</div>'
                f'<div style="font-size:3em; font-weight:800; line-height:1.1; '
                f'color:{COLOR["stat_high"] if hot else COLOR["text"]};">{runs.mean():.1f}</div>'
                f'<div style="font-size:var(--lc-text-small); color:{COLOR["text_muted"]};">'
                f'runs on average · wins <b style="color:{COLOR["text"]};">{100 * win:.0f}%</b>'
                f'</div></div>')
    tot = home + away
    f5h, f5a = sim["inn"]["home"][:, :5].sum(axis=1), sim["inn"]["away"][:, :5].sum(axis=1)
    tl = f"Total runs: typically <b>{np.median(tot):.0f}</b>, {_rng(tot)} most games"
    if odds.get("total") is not None:
        po = float((tot > odds["total"]).mean())
        tl += (f" · over the book's {odds['total']:g}: <b>{100 * po:.0f}%</b>, under "
               f"<b>{100 * (1 - po):.0f}%</b>")
    st.markdown(
        f'<div style="display:flex; gap:12px; flex-wrap:wrap; margin:6px 0 10px;">'
        f'{_team(aa, away, 1 - ph_sim)}{_team(ha, home, ph_sim)}</div>'
        f'<div style="font-size:var(--lc-text-body); line-height:1.8;">{tl}<br>'
        f'Wins by 2+ (the run line): {ha} <b>{100 * float((home - away >= 2).mean()):.0f}%</b>, '
        f'{aa} <b>{100 * float((away - home >= 2).mean()):.0f}%</b><br>'
        f'First five innings: {aa} {f5a.mean():.1f} – {ha} {f5h.mean():.1f} · {ha} leads '
        f'<b>{100 * float((f5h > f5a).mean()):.0f}%</b>, tied <b>'
        f'{100 * float((f5h == f5a).mean()):.0f}%</b>, {aa} leads <b>'
        f'{100 * float((f5a > f5h).mean()):.0f}%</b> · total {np.median(f5h + f5a):.0f} '
        f'({_rng(f5h + f5a)})</div>', unsafe_allow_html=True)
    st.caption("Win chances here are the simulator's; a moneyline bet is priced on the Bet "
               "Finder / Model page with the game model's tested weight against the book. "
               "Extra innings start with a runner on second, as in the real game.")

# ---------------- the box score ----------------
with card("mls_box"):
    st.markdown(f'<div class="pf-card-title" style="color:{COLOR["gold"]};">The box score — '
                f'{N_SIMS:,} games</div>', unsafe_allow_html=True)
    for side, abbr in (("away", aa), ("home", ha)):
        rows = []
        for p in [x for x in players if x["side"] == side]:
            a_ = sim["stats"][p["pid"]]
            rows.append({"#": p["slot"], "Batter": p["name"],
                         "Hit": _pc(float((a_["h"] > 0).mean())),
                         "2+ TB": _pc(float((a_["tb"] > 1).mean())),
                         "HR": _pc(float((a_["hr"] > 0).mean())),
                         "RBI": _pc(float((a_["rbi"] > 0).mean())),
                         "Run": _pc(float((a_["r"] > 0).mean())),
                         "H+R+RBI": f"{a_['hrr'].mean():.1f}",
                         "K": f"{a_['k'].mean():.1f}"})
        st.markdown(f"**{abbr}**")
        st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch", key=f"mls_b_{side}")
        s_ = sim["sp"][side]
        st.caption(f"{sp_name[side]}: {s_['k'].mean():.1f} K ({_rng(s_['k'])}), "
                   f"{s_['outs'].mean() / 3:.1f} innings, {s_['h'].mean():.1f} hits, "
                   f"{s_['er'].mean():.1f} runs while he's in.")
    st.caption("Hit / 2+ TB / HR / RBI / Run = how often he gets one across the simulated games; "
               "H+R+RBI and K = his average. A starter's runs here are the runs scored while he "
               "pitched (a runner he leaves on who scores later is not his here).")

# ---------------- every batter ----------------
STATS = (("h", "Hits", 0.5), ("tb", "Total bases", 1.5), ("hr", "Home runs", 0.5),
         ("rbi", "RBI", 0.5), ("r", "Runs", 0.5), ("hrr", "Hits + Runs + RBI", 1.5),
         ("k", "Strikeouts", 0.5), ("bb", "Walks", 0.5))
with card("mls_players"):
    st.markdown(f'<div class="pf-card-title" style="color:{COLOR["gold"]};">Every batter — '
                f'over or under?</div>', unsafe_allow_html=True)
    c1, c2 = st.columns([2, 1])
    slab = c1.selectbox("Stat", [lab for _s, lab, _l in STATS], key="mls_stat")
    stat, _lab, dl = next(x for x in STATS if x[1] == slab)
    line = c2.number_input("Line", value=dl, step=1.0, key=f"mls_line_{stat}")
    line = math.floor(line) + 0.5
    rows, sides_ = [], []
    for p in sorted(players, key=lambda p: -float((sim["stats"][p["pid"]][stat] > line).mean())):
        ch = bat_chance(p, stat, line)
        sides_.append(ch)
        rows.append({"Batter": f"{p['name']} ({p['team']}, #{p['slot']})", "Line": f"{line:g}",
                     "Over": _pc(ch), "Under": _pc(1 - ch),
                     "Lean": (f"OVER {_pc(ch)}" if ch >= 0.55 else f"UNDER {_pc(1 - ch)}"
                              if ch <= 0.45 else "toss-up")})

    def _paint(frame):
        o_ = pd.DataFrame("", index=frame.index, columns=frame.columns)
        for k in frame.index:
            o_.at[k, "Over"] = mv.chance_css(sides_[k])
            o_.at[k, "Under"] = mv.chance_css(1 - sides_[k])
        return o_
    st.dataframe(mv.painted(pd.DataFrame(rows), _paint), hide_index=True, width="stretch",
                 key=f"mls_pl_{stat}")
    mv.render_chance_legend()
    st.caption("Hits, total bases, HR, RBI, strikeouts and walks: the prop board's delivered "
               "chance. Runs and H+R+RBI are not on the board — those are the simulator's own "
               "chance, untested, so a bet on them stays at THIN. " + mp.RBI_NOTE)

# ---------------- same-game parlay ----------------
with card("mls_sgp"):
    st.markdown(f'<div class="pf-card-title" style="color:{COLOR["gold"]};">Same-game parlay'
                f'</div>', unsafe_allow_html=True)
    opts = ([("game", "home_win", f"{ha} to win"), ("game", "away_win", f"{aa} to win"),
             ("game", "total", "Total runs"), ("game", "home_margin", f"{ha} run line"),
             ("game", "away_margin", f"{aa} run line"), ("game", "f5_total", "First 5: total"),
             ("game", "f5_home_margin", f"First 5: {ha} line"),
             ("sp", "away", f"{sp_name['away']} ({aa} starter)"),
             ("sp", "home", f"{sp_name['home']} ({ha} starter)")]
            + [("bat", p["pid"], f"{p['name']} ({p['team']})") for p in players])
    pmap = {p["pid"]: p for p in players}
    n_fixed = len(opts) - len(players)
    nlegs = st.number_input("Legs", 2, ms.SGP_MAX_LEGS, 2, key="mls_n")
    legs, show = [], []
    SPS = (("k", "Strikeouts"), ("outs", "Outs recorded"), ("h", "Hits allowed"),
           ("er", "Runs allowed"))
    for i in range(int(nlegs)):
        a, b, c, d = st.columns([3, 2, 1, 1])
        oi = a.selectbox(f"Leg {i + 1}", range(len(opts)), format_func=lambda k: opts[k][2],
                         key=f"mls_o{i}", index=min(n_fixed + i, len(opts) - 1))
        kind, key_, name = opts[oi]
        if kind == "bat":
            p = pmap[key_]
            sl = b.selectbox("Stat", [lab for _s, lab, _l in STATS], key=f"mls_s{i}_{key_}")
            st_, _l, dl = next(x for x in STATS if x[1] == sl)
            ln = c.number_input("Line", value=dl, step=1.0, key=f"mls_l{i}_{key_}_{st_}")
            ln = math.floor(ln) + 0.5
            sd = d.selectbox("Side", ["Over", "Under"], key=f"mls_d{i}")
            legs.append({"pid": key_, "stat": st_, "line": ln, "side": sd})
            show.append((f"{p['name']} {sd} {ln:g} {sl}", bat_chance(p, st_, ln, sd)))
        elif kind == "sp":
            sl = b.selectbox("Stat", [lab for _s, lab in SPS], key=f"mls_ss{i}_{key_}")
            st_ = next(s_ for s_, lab in SPS if lab == sl)
            ex = float(sim["sp"][key_][st_].mean())
            ln = c.number_input("Line", value=math.floor(ex) + 0.5, step=1.0,
                                key=f"mls_l{i}_sp{key_}_{st_}")
            ln = math.floor(ln) + 0.5
            sd = d.selectbox("Side", ["Over", "Under"], key=f"mls_d{i}")
            legs.append({"pid": f"_sp_{key_}", "stat": st_, "line": ln, "side": sd})
            show.append((f"{sp_name[key_]} {sd} {ln:g} {sl.lower()}", sp_chance(key_, st_, ln, sd)))
        elif key_ in ("home_win", "away_win"):
            b.markdown("Game")
            legs.append({"pid": "_game", "stat": key_, "line": 0.5, "side": "Over"})
            show.append((name, p_win(key_.split("_")[0])))
        else:
            b.markdown("Game")
            dflt = (float(odds.get("total") or 8.5) if key_ == "total" else
                    4.5 if key_ == "f5_total" else -1.5 if key_ != "f5_home_margin" else -0.5)
            ln = c.number_input("Line", value=dflt, step=0.5, key=f"mls_l{i}_{key_}")
            sd = d.selectbox("Side", ["Over", "Under"], key=f"mls_d{i}")
            leg = {"pid": "_game", "stat": key_,
                   "line": ln if key_.endswith("total") else -ln, "side": sd}
            legs.append(leg)
            show.append((f"{name} {sd} {ln:g}", float(ms.leg_hits(sim, leg).mean())))
    with st.spinner(f"Playing this parlay {ms.SGP_SIMS:,} times…"):
        j = _legs_run(f"{g.get('game_pk')}|{_json.dumps(legs, sort_keys=True)}|{len(_gjs)}",
                      _gjs, _json.dumps(legs))
    prod = float(np.prod([c_ for _l, c_ in show]))
    if not j["lift"]:
        st.warning(f"In {ms.SGP_SIMS:,} games these legs never all hit together — the "
                   f"simulator can't price this one. Check the lines.")
    else:
        jp = min(0.999, prod * j["lift"])
        st.markdown(
            '<div style="font-size:var(--lc-text-body); line-height:1.8;">'
            + "<br>".join(f"{l_} — <b>{100 * c_:.0f}%</b>" for l_, c_ in show)
            + f'<br>Multiplied as strangers: <b>{100 * prod:.1f}%</b> · '
              + (f'they move together <b>x{j["lift"]:.2f}</b>' if j["lift"] - 2 * j["lift_se"] > 1
                 else f'they pull apart <b>x{j["lift"]:.2f}</b>' if j["lift"] + 2 * j["lift_se"] < 1
                 else f'no real link (<b>x{j["lift"]:.2f}</b>)')
            + f' <span style="color:{COLOR["text_muted"]};">(±{j["lift_se"]:.3f}, '
              f'{ms.SGP_SIMS:,} games)</span> → '
              f'<span style="{mv.chance_css(jp)} padding:2px 8px; border-radius:6px;">'
              f'<b>{100 * jp:.1f}%</b></span> · worth it at '
              f'<b>{mm.fmt_american(mm.fair_american(jp))}</b></div>', unsafe_allow_html=True)
        k1, k2 = st.columns(2)
        price = k1.number_input("Your book's SGP price", value=None, step=5, format="%d",
                                key="mls_price")
        sup = ms.sgp_support(combos, legs, info)
        res = bf.judge(jp, price, _stk, None, sup)
        if res and res.get("guard"):
            res["guard"] = ms.sgp_guard(sup, res["tier"]) or res["guard"]
        if res:
            lab_, fg, _bg = mv.TIER_STYLE[res["tier"]]
            st.markdown(f'<span style="color:{fg if res["tier"] != "none" else COLOR["error"]}; '
                        f'font-weight:800;">{"SKIP" if res["tier"] == "none" else lab_}</span> '
                        f'· edge {100 * res["edge"]:+.1f} pts'
                        + (f' · stake ${res["stake"]:.2f}' if res.get("stake") else "")
                        + (f'<br><span style="color:{COLOR["warn"]};">{res["guard"]}</span>'
                           if res.get("guard") else ""), unsafe_allow_html=True)
            from engines import bet_log_ui as _blu
            _blu.log_button("MLB", "sgp", f"{labels[gi]}: " + " + ".join(l_ for l_, _c in show),
                            jp, price, res.get("stake"), res["tier"], [l_ for l_, _c in show],
                            "mls_log")
            if k2.button("Add to parlay slip", key="mls_add"):
                from engines import parlay as pl
                pl.add_leg(ss.setdefault("parlay", {}), "MLB", labels[gi],
                           "SGP: " + " + ".join(l_ for l_, _c in show), "same-game parlay",
                           jp, bf.valid_price(price), sup, res["tier"])
                st.success("On the slip (Bet Finder page) as one leg, its legs' link priced in.")
    if combos:
        mine = ms.combo_kind(legs, info)
        gr, vlist = [], []
        for kind in sorted(combos, key=lambda k_: (len(k_), k_)):
            x = combos[kind]
            gr.append({"Parlay": ms.KIND_LABEL.get(kind, kind) + ("  ← yours" if kind == mine
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
                     key="mls_graded")
        st.caption("Each row: same-game parlays of that kind built from the last 30 days of real "
                   "games (each team's likeliest hitters and power bat, its starter's strikeouts "
                   "at his own line, every leg an over). Predicted = the simulator's chance they "
                   "all hit, Multiplied = the legs as strangers, Hit = how often they really did.")
    st.caption("Each leg is the board's delivered chance where the props model prices it (a "
               "team to win: the game model's, anchored to the market; totals, run lines, first "
               "five, runs, H+R+RBI, a starter's outs and runs: the simulator's own); only the "
               "link between the legs comes from the simulator.")

footer()
