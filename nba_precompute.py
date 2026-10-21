"""
NBA nightly (10-20) — tonight's slate, every player's projection, the
injury report, Next Man Up, the preseason role watch and the milestone
watch, written to build_data/data/nba/games.json.

  - Last season (data/nba/prior_season.json, the manual
    `nba-prior-season` workflow) is what the model is FITTED and TESTED
    on (engines/nba_model.fit) — every night, so the verdicts the pages
    print are tonight's.
  - This season's regular-season box scores join the pool as they come.
  - PRESEASON box scores are kept for REFERENCE only (trend charts,
    the role watch) and never touch a rate (rule 6: a preseason
    rotation is not a regular-season one).
  - Who is playing: the team roster's injury tag, else ESPN's league
    list (engines/availability); Out / suspended leave the pool before
    anything is projected.

Prints [verify] lines. A failure in any one board costs that board,
never the slate.
"""
import json
import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "app"))

from engines import availability as av  # noqa: E402
from engines import espn_feed as ef  # noqa: E402
from engines import nba_box as nb  # noqa: E402
from engines import nba_context as nc  # noqa: E402
from engines import nba_first as nf  # noqa: E402
from engines import nba_pbp as pbp  # noqa: E402
from engines import nba_quarters as nq  # noqa: E402
from engines import nba_model as nm  # noqa: E402

EASTERN = ZoneInfo("America/New_York")
LEAGUE = "nba"
OUT = Path("build_data") / "data" / "nba"
PRIOR_PATH = ROOT / "data" / "nba" / "prior_season.json"
PBP_PATH = ROOT / "data" / "nba" / "prior_pbp.json"
PRESEASON_START = date(2026, 10, 2)
REGULAR_SEASON_START = date(2026, 10, 20)
LOOKAHEAD_DAYS = 14
TREND_GAMES = 30          # games per player shipped for the trend charts
KEY_MINUTES = 20.0        # an OUT player this big gets a Next Man Up board


def phase(today):
    if today < PRESEASON_START:
        return "offseason"
    return "preseason" if today < REGULAR_SEASON_START else "regular"


def slate_game(event, on_date):
    comp, away, home = ef.event_sides(event)
    if comp is None:
        return None
    status, _done, detail = ef.status_of(event)
    stype = (event.get("season") or {}).get("type") if isinstance(event.get("season"), dict) \
        else None
    if stype in (1, 2, 3, 5):
        gtype = {1: "preseason", 2: "regular", 3: "playoffs", 5: "play-in"}[stype]
    else:
        gtype = "regular" if on_date >= REGULAR_SEASON_START else "preseason"
    start = ef.to_et(comp.get("date") or event.get("date"))
    g = {"event_id": str(event.get("id") or ""), "status": status, "detail": detail,
         "game_type": gtype, "venue": (comp.get("venue") or {}).get("fullName") or ""}
    for side, c in (("away", away), ("home", home)):
        t = c.get("team") or {}
        g[side] = t.get("displayName") or "TBD"
        g[f"{side}_abbr"] = t.get("abbreviation") or ""
        g[f"{side}_id"] = str(t.get("id") or "")
        g[f"{side}_logo"] = ef.team_logo(t)
        recs = c.get("records") or []
        if recs and isinstance(recs[0], dict):
            g[f"{side}_record"] = recs[0].get("summary")
        if status in ("in progress", "final"):
            v = ef.num(c.get("score"))
            if v is not None:
                g[f"{side}_score"] = int(v)
    if start:
        g["start_et"] = start.isoformat()
        g["time_et"] = start.strftime("%-I:%M %p")
    o = ef.odds_of(comp)
    if o:
        g["odds"] = o
    return g


# ----------------------------------------------------------------------
# Rosters and injury tags
# ----------------------------------------------------------------------
def fetch_roster(team_id):
    """{pid: {"pos", "status"}} from ESPN's team roster, or {}."""
    try:
        data = ef.get_json(f"{ef.base(LEAGUE)}/teams/{team_id}/roster")
    except Exception as exc:  # noqa: BLE001
        print(f"  roster {team_id} failed: {exc}")
        return {}
    out = {}

    def walk(o):
        if isinstance(o, dict):
            if o.get("id") and o.get("displayName") and isinstance(o.get("position"), dict):
                inj = o.get("injuries") or []
                st = None
                if inj and isinstance(inj[0], dict):
                    st = inj[0].get("status") or (inj[0].get("type") or {}).get("description")
                out[str(o["id"])] = {"pos": o["position"].get("abbreviation") or "",
                                     "status": st, "name": o.get("displayName")}
                return
            for v in o.values():
                walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)
    walk(data.get("athletes") or data)
    return out


# ----------------------------------------------------------------------
# Building blocks (pure, tested)
# ----------------------------------------------------------------------
def merge_pool(prior_players, cur_players):
    """Last season + this season's regular games, per player, date order."""
    pool = {}
    for pid, p in (prior_players or {}).items():
        pool[pid] = {"name": p.get("name"), "pos": p.get("pos"), "team": p.get("team"),
                     "games": [list(g) for g in p.get("games") or []]}
    for pid, p in (cur_players or {}).items():
        d = pool.setdefault(pid, {"name": p.get("name"), "pos": p.get("pos"), "games": []})
        d["games"] += [list(g) for g in p.get("games") or []]
        d["team"] = p.get("team") or d.get("team")
        d["name"] = p.get("name") or d.get("name")
        d["pos"] = p.get("pos") or d.get("pos")
    for d in pool.values():
        d["games"].sort(key=lambda g: g[0])
    return pool


def avg_line(games, cut_from=None):
    gs = [g for g in games or [] if g[3] and (cut_from is None or g[0] >= cut_from)]
    if not gs:
        return None
    out = {"gp": len(gs)}
    for st in ("min", "pts", "reb", "ast", "tpm"):
        v = [nm.val(g, st) for g in gs if nm.val(g, st) is not None]
        out[st] = round(sum(v) / len(v), 1) if v else None
    return out


def role_watch(pre_players, prior_players, min_games=2, top=20):
    """Preseason minutes vs last season's: the biggest movers (reference)."""
    rows = []
    for pid, p in (pre_players or {}).items():
        pre = avg_line(p.get("games"))
        last = avg_line((prior_players or {}).get(pid, {}).get("games"))
        if not pre or pre["gp"] < min_games or pre.get("min") is None:
            continue
        delta = None if not last or last.get("min") is None else round(pre["min"] - last["min"], 1)
        rows.append({"pid": pid, "name": p.get("name"), "team": p.get("team"),
                     "pre": pre, "last": last, "min_delta": delta})
    rows.sort(key=lambda r: -abs(r["min_delta"] or 0))
    return rows[:top] if top else rows


def trend_games(pool_games, pre_games, team_abbr, cur_from):
    """The last TREND_GAMES games (regular, both seasons) + every
    preseason game, each tagged REG / LAST / PRE with its opponent."""
    def row(g, tag):
        return {"date": g[0], "opp": team_abbr.get(str(g[2]), str(g[2])), "tag": tag,
                **{st: nm.val(g, st) for st in ("min", "pts", "reb", "ast", "tpm",
                                                "pra", "pr", "pa", "ra")}}
    reg = [row(g, "REG" if g[0] >= cur_from else "LAST") for g in (pool_games or [])[-TREND_GAMES:]]
    pre = [row(g, "PRE") for g in pre_games or []]
    return sorted(reg + pre, key=lambda r: r["date"])


def why_line(name, proj, last, cur):
    bits = [f"{name}: ~{proj['min']:.0f} min tonight"]
    if cur and cur.get("gp"):
        bits.append(f"{cur['pts']} pts / {cur['reb']} reb / {cur['ast']} ast in {cur['gp']} "
                    f"game{'s' if cur['gp'] != 1 else ''} this season")
    if last and last.get("gp"):
        bits.append(f"last season {last['pts']} / {last['reb']} / {last['ast']} over "
                    f"{last['gp']} games")
    return " · ".join(bits)


def side_props(team_id, pool, pre, params, roster, feed, team_abbr, cur_from):
    """(rows, held_out) for one team tonight."""
    rows, held = [], []
    for pid, p in pool.items():
        # The roster decides who is on this team tonight (an offseason
        # trade has no regular-season game yet); without a roster, his
        # latest team does — this season's, then the preseason's.
        if roster:
            if pid not in roster:
                continue
        else:
            now_team = (pre.get(pid) or {}).get("team") if not any(
                g[0] >= cur_from for g in p["games"]) else p.get("team")
            if str(now_team or p.get("team")) != str(team_id):
                continue
        st = av.status_for(pid, p.get("name"), (roster.get(pid) or {}).get("status"), feed)
        if av.is_out(st):
            held.append(f"{p.get('name')} ({st})")
            continue
        proj = nm.project_now(p["games"], params, p.get("pos"), today=cur_from)
        if not proj or proj["min"] < nm.MIN_PROJ_MIN:
            continue
        last = avg_line([g for g in p["games"] if g[0] < cur_from])
        cur = avg_line([g for g in p["games"] if g[0] >= cur_from])
        rows.append({"pid": pid, "name": p.get("name"), "pos": (roster.get(pid) or {}).get("pos")
                     or p.get("pos"), "status": st or "",
                     "min": round(proj["min"], 1),
                     "mu": {k: round(v, 3) for k, v in proj["mu"].items()},
                     "season": cur, "last_season": last,
                     "why": why_line(p.get("name"), proj, last, cur),
                     "trend": trend_games(p["games"], (pre.get(pid) or {}).get("games"),
                                          team_abbr, cur_from)})
    rows.sort(key=lambda r: -r["min"])
    return rows, sorted(held)


def first_basket_game(g, book, prm, pool):
    """One slate game's first-basket prices from its projected rows (Out
    players are already not in them)."""
    avail, pmin, ppts, preb, names = {}, {}, {}, {}, {}
    for side in ("home", "away"):
        t = str(g[f"{side}_id"])
        avail[t] = {str(r["pid"]) for r in g.get(f"{side}_props") or []}
        for r in g.get(f"{side}_props") or []:
            p = str(r["pid"])
            pmin[p], ppts[p], preb[p], names[p] = r["min"], r["mu"]["pts"], r["mu"]["reb"], \
                r["name"]
    home, away = str(g["home_id"]), str(g["away_id"])
    pg = nf.price_game(book, home, away, avail, pmin, ppts, preb, prm,
                       (g.get("start_et") or "")[:10] or None)

    def nm_(p):
        return names.get(p) or (pool.get(p) or {}).get("name") or p
    jump = {}
    for t, p in pg["jumpers"].items():
        w, n = (book.tip.get(p) or [0, 0]) if p else (0, 0)
        jump[t] = {"pid": p, "name": nm_(p) if p else None, "wins": w, "jumps": n,
                   "rate": round(nf.tip_rate(book, p, prm["k_tip"]), 3) if p else None}
    return {"tip_home": round(pg["tip"], 4), "team": {t: round(v, 4) for t, v in pg["team"].items()},
            "jumpers": jump,
            "players": sorted([{"pid": p, "name": nm_(p), "team": t, "p": round(v, 5),
                                "starts": book.starts.get(p, 0), "fb": book.fb.get(p, 0)}
                               for p, (t, v) in pg["players"].items()], key=lambda x: -x["p"]),
            "other": round(max(0.0, 1 - sum(v for _t, v in pg["players"].values())), 4)}


def next_man_up_boards(pool, team_id, held_pids, since):
    out = []
    for opid in held_pids:
        p = pool.get(opid) or {}
        mins = [nm.val(g, "min") for g in p.get("games") or []
                if str(g[1]) == str(team_id) and nm.val(g, "min")]
        if not mins or sum(mins) / len(mins) < KEY_MINUTES:
            continue
        rows = nm.next_man_up(pool, team_id, opid, since=since)[:8]
        if rows:
            out.append({"out_pid": opid, "out_name": p.get("name"),
                        "out_min": round(sum(mins) / len(mins), 1), "rows": rows})
    return out


# ----------------------------------------------------------------------
# Main
# ----------------------------------------------------------------------
def main(today=None):
    now = datetime.now(EASTERN)
    today = today or now.date()
    OUT.mkdir(parents=True, exist_ok=True)

    slate, slate_date = [], today
    for k in range(LOOKAHEAD_DAYS + 1):
        d = today + timedelta(days=k)
        try:
            sb, _src = ef.fetch_scoreboard(LEAGUE, d.strftime("%Y%m%d"))
        except Exception as exc:  # noqa: BLE001
            print(f"  scoreboard {d} failed: {exc}")
            if k == 0:
                raise
            continue
        games = [g for g in (slate_game(e, d) for e in sb.get("events") or []) if g]
        if games:
            slate, slate_date = games, d
            break
    print(f"NBA: slate {slate_date} — {len(slate)} games")

    # This season so far: regular games join the pool; preseason is reference.
    cur, pre, team_abbr, team_logo = {}, {}, {}, {}
    cur_finals = []
    cur_pbp = {}
    seen = parsed = 0
    d = PRESEASON_START
    while d <= today:
        try:
            sb, _src = ef.fetch_scoreboard(LEAGUE, d.strftime("%Y%m%d"))
        except Exception as exc:  # noqa: BLE001
            print(f"  scoreboard {d} failed: {exc}")
            d += timedelta(days=1)
            continue
        for ev in sb.get("events") or []:
            g = slate_game(ev, d)
            if not g or g["status"] != "final":
                continue
            seen += 1
            try:
                summ = ef.fetch_summary(LEAGUE, g["event_id"])
            except Exception as exc:  # noqa: BLE001
                print(f"  summary {g['event_id']} failed: {exc}")
                continue
            lines = nb.parse(summ)
            if not lines:
                continue
            parsed += 1
            if g["game_type"] == "regular":
                try:
                    cur_pbp[g["event_id"]] = dict(pbp.parse(summ), date=d.isoformat(),
                                                  home=g["home_id"], away=g["away_id"])
                except Exception as exc:  # noqa: BLE001 — one game's plays cost that game
                    print(f"  play-by-play {g['event_id']} failed: {exc}")
            if g["game_type"] == "regular" and g.get("home_score") is not None:
                cur_finals.append({"date": d.isoformat(), "home_id": g["home_id"],
                                   "away_id": g["away_id"], "home_score": g["home_score"],
                                   "away_score": g["away_score"],
                                   "home_abbr": g["home_abbr"], "away_abbr": g["away_abbr"],
                                   "odds": ef.recorded_line(g.get("odds"), summ) or None})
            store = cur if g["game_type"] == "regular" else pre
            for pid, ln in lines.items():
                p = store.setdefault(pid, {"name": ln["name"], "pos": ln["pos"], "games": []})
                p["team"] = ln["team_id"]
                p["games"].append(nb.as_tuple(d.isoformat(), ln))
            time.sleep(0.05)
        d += timedelta(days=1)
    for g in slate:
        for side in ("away", "home"):
            team_abbr[g[f"{side}_id"]] = g[f"{side}_abbr"]
            team_logo[g[f"{side}_id"]] = g.get(f"{side}_logo")
    print(f"NBA: {seen} finals since {PRESEASON_START}, {parsed} box scores parsed — "
          f"{sum(len(p['games']) for p in cur.values())} regular-season player-games, "
          f"{sum(len(p['games']) for p in pre.values())} preseason (reference only)")

    prior = json.loads(PRIOR_PATH.read_text()) if PRIOR_PATH.exists() else {}
    for tid, t in (prior.get("teams") or {}).items():
        team_abbr.setdefault(tid, t.get("abbr"))
        team_logo.setdefault(tid, t.get("logo"))
    if not prior:
        print("::warning::NBA: data/nba/prior_season.json missing - run the 'NBA prior "
              "season' workflow once. No projections until it exists.")

    # last season + this one, for every test that should grow nightly
    season_data = {"players": merge_pool(prior.get("players"), cur),
                   "finals": list(prior.get("finals") or [])
                   + [{"date": f["date"], "home": str(f.get("home_id")),
                       "away": str(f.get("away_id")), "hs": f.get("home_score"),
                       "as": f.get("away_score")} for f in cur_finals
                      if f.get("home_score") is not None]}
    model = None
    try:
        if prior.get("players"):
            t0 = time.time()
            params = nm.fit(prior["players"])
            if params.get("hl"):
                model = {k: v for k, v in params.items() if k != "fit_rows"}
                print(f"  [verify] NBA model fit on 2025-26 ({time.time() - t0:.0f}s): half-life "
                      f"{params['hl']} games, shrink {params['k']} min toward his own rate (half-life "
                      f"{params.get('hl_long')} games, itself shrunk {params.get('k_long')} min "
                      f"toward the league), fit window "
                      f"{params['fit_window']}, test {params['test_window']}")
                print(f"  [verify] NBA minutes: {params['minutes']}")
                for st, lab in nm.STATS:
                    x = params["test"].get(st) or {}
                    print(f"  [verify] NBA {lab:16s} n={x.get('n')} model {x.get('model_brier')} "
                          f"vs his-own-rate {x.get('baseline_brier')} -> "
                          f"{(x.get('verdict') or {}).get('verdict')} "
                          f"(z={(x.get('verdict') or {}).get('z')}) size {params['sizes'].get(st)}")
            else:
                print(f"::warning::NBA model not fitted: {params.get('note')}")
    except Exception as exc:  # noqa: BLE001
        print(f"::warning::NBA model failed: {type(exc).__name__}: {exc}")

    # TONIGHT'S CONTEXT (10-20, engines/nba_context): the opponent (defense
    # and pace) and teammates out, each fitted on 2025-26 and kept only
    # where it beat the plain projection; when it ships, the model's
    # sizes / test / curves are the context's, so every page prices it.
    try:
        if model:
            t0 = time.time()
            ctx = nc.fit(season_data, model)
            if ctx:
                model["base_test"] = model["test"]
                model["sizes"], model["test"] = ctx["sizes"], ctx["test"]
                model["ladder"] = ctx["ladder"]
                model["context"] = {k: ctx[k] for k in ("opp", "mean", "out", "vs_base")}
                print(f"  [verify] NBA props test: {ctx['n_test']} player-games ("
                      f"{ctx['n_this_season']} from this season)")
                print(f"  [verify] NBA context ({time.time() - t0:.0f}s): opponent {ctx['opp']}; "
                      f"teammate out {ctx['out']}")
                for st, lab in nm.STATS:
                    x, v = ctx["test"].get(st) or {}, ctx["vs_base"].get(st) or {}
                    print(f"  [verify] NBA {lab:16s} WITH CONTEXT model {x.get('model_brier')} vs "
                          f"his-own-rate {x.get('baseline_brier')} -> "
                          f"{(x.get('verdict') or {}).get('verdict')} "
                          f"(z={(x.get('verdict') or {}).get('z')}); vs no context -> "
                          f"{v.get('verdict')} (z={v.get('z')})")
        for st, x in ((model or {}).get("ladder") or {}).items():
            v = x.get("verdict") or {}
            print(f"  [verify] NBA ladder {st:4s} (every rung {nm.LADDER[st]}) n={x['n']} model "
                  f"{x['model_brier']} vs his-own-rate {x['baseline_brier']} -> "
                  f"{v.get('verdict')} (z={v.get('z')}); low bins "
                  + ", ".join(f"{b['band']} {b['actual']:.3f}/{b['predicted']:.3f} n{b['n']}"
                              for b in (x.get("calibration") or [])[:6]))
    except Exception as exc:  # noqa: BLE001
        print(f"::warning::NBA context failed (props stay without it): "
              f"{type(exc).__name__}: {exc}")

    # THE GAME MODEL (10-20): the NFL module's normal margin / total on
    # team ratings — basketball scores are big and near-normal, the same
    # shape — fitted on 2025-26 while this season is young, then this
    # season's games move it; anchored to the market by its fitted weight.
    game_model = None
    try:
        game_model = nba_game_model(prior.get("finals"), cur_finals, slate)
    except Exception as exc:  # noqa: BLE001
        print(f"::warning::NBA game model failed: {type(exc).__name__}: {exc}")

    # THE SIMULATOR'S LINKS AND ITS TEST (10-20, engines/nba_sim): how
    # minutes and stats move with the score, measured on last season;
    # whether same-game pairs priced with it beat plain multiplication.
    sim_block = None
    try:
        if model and prior.get("players"):
            from engines import nba_sim
            t0 = time.time()
            _pg = json.loads(PBP_PATH.read_text()).get("games") if PBP_PATH.exists() else {}
            sim_block = nba_sim.build(prior, model, merge_pool(prior.get("players"), cur),
                                      cur_finals, list((_pg or {}).values())
                                      + list(cur_pbp.values()))
            if sim_block:
                L, T = sim_block["links"], sim_block["test"]
                print(f"  [verify] NBA simulator links ({time.time() - t0:.0f}s): elasticities "
                      f"{L['e']}, minutes share starter {L['min_share']['starter']} bench "
                      f"{L['min_share']['bench']} (close / comfortable / blowout)")
                print(f"  [verify] NBA simulator test: n={T['n']} same-game pairs, sim "
                      f"{T['sim_brier']} vs multiplied {T['independent_brier']} -> "
                      f"{(T.get('verdict') or {}).get('verdict')} (z={(T.get('verdict') or {}).get('z')}); "
                      f"teammates {T['teammates']}; opponents {T['opponents']}")
                Q = sim_block.get("quarters") or {}
                if Q:
                    ql = (sim_block.get("links") or {}).get("quarters") or {}
                    print(f"  [verify] NBA halves / quarters (n={ql['n']}): first-half margin "
                          f"{ql['h1']['r_m']:.2f} x the game's, total {ql['h1']['r_t']:.3f} x "
                          f"(sd {ql['h1']['sd_t']:.1f}); first quarter {ql['q1']['r_m']:.2f} x, "
                          f"{ql['q1']['r_t']:.3f} x (sd {ql['q1']['sd_t']:.1f})")
                    for k in ("h1_win", "q1_win"):
                        x = Q[k]
                        print(f"  [verify] NBA {k}: n={x['n']} brier {x['brier']} -> vs coin "
                              f"{x['vs_coin']['verdict']} (z={x['vs_coin']['z']}), vs reusing "
                              f"the game's win chance {x['vs_game']['verdict']} "
                              f"(z={x['vs_game']['z']})")
                    for k in ("h1_over", "q1_over"):
                        x = Q[k]
                        print(f"  [verify] NBA {k} at its median: predicted {x['predicted']} "
                              f"vs hit {x['hit']} (n={x['n']})")
                print(f"  [verify] NBA same-game parlays graded: {sim_block['test_rows']} "
                      f"player-games ({sim_block['this_season_rows']} from this season)")
                for kind, x in (sim_block.get("combos") or {}).items():
                    v = x.get("verdict") or {}
                    print(f"  [verify] NBA SGP {kind:8s} n={x['n']} sim {x['sim_brier']} vs "
                          f"multiplied {x['independent_brier']} -> {v.get('verdict')} "
                          f"(z={v.get('z')}); predicted {x['predicted_sim']} (multiplied "
                          f"{x['predicted_ind']}) vs actual {x['actual']}")
    except Exception as exc:  # noqa: BLE001
        print(f"::warning::NBA simulator failed: {type(exc).__name__}: {exc}")

    # FIRST BASKET (10-21, engines/nba_first): fitted and tested on last
    # season's play-by-play (data/nba/prior_pbp.json, a one-time backfill)
    first_block, first_book = None, None
    try:
        prior_pbp = json.loads(PBP_PATH.read_text()).get("games") if PBP_PATH.exists() else None
        if model and prior_pbp:
            t0 = time.time()
            byg = {}
            ctx_rows = nc.context_rows(season_data, model)
            for pid, g_, pr, _h in ctx_rows:
                byg.setdefault((g_[0], str(g_[1])), []).append((str(pid), pr))
            # FIRST-QUARTER POINTS (engines/nba_quarters): fitted and tested
            # on the same rows; joins the props model as stat "q1pts"
            all_pbp = list(prior_pbp.values()) + list(cur_pbp.values())
            q1_block = nq.fit(ctx_rows, all_pbp, model["fit_window"], model["test_window"])
            # THE LIVE PAGE, TESTED: points at the end of each quarter
            lc = nq.live_check(ctx_rows, all_pbp, model.get("sizes"), model["test_window"][0])
            if lc:
                model["live_check"] = lc
                L_ = lc["pts"]
                print(f"  [verify] NBA live points test: n={L_['n']} quarter-end calls, model "
                      f"{L_['model_brier']} vs naive {L_['naive_brier']} -> "
                      f"{L_['verdict']['verdict']} (z={L_['verdict']['z']}); "
                      + ", ".join(f"{k} brier {v['brier']}"
                                  for k, v in L_["by_checkpoint"].items()))
            if q1_block:
                model["q1"] = q1_block["params"]
                model.setdefault("sizes", {})["q1pts"] = q1_block["size"]
                model.setdefault("test", {})["q1pts"] = q1_block["test"]
                Tq = q1_block["test"]
                print(f"  [verify] NBA 1st-quarter points: params {q1_block['params']}, size "
                      f"{q1_block['size']}; test n={Tq['n']} model {Tq['model_brier']} vs "
                      f"his-own-rate {Tq['baseline_brier']} -> {Tq['verdict']['verdict']} "
                      f"(z={Tq['verdict']['z']})")
            first_block = nf.fit(list(prior_pbp.values()) + list(cur_pbp.values()), byg,
                                 model["fit_window"], model["test_window"])
            first_book = nf.book_from(list(prior_pbp.values()) + list(cur_pbp.values()))
            F = first_block
            print(f"  [verify] NBA first basket ({time.time() - t0:.0f}s): params "
                  f"{F['params']}; test n={F['n_test']} games, log loss {F['test_loss']} vs "
                  f"every projected starter equal {F['naive_loss']} -> "
                  f"{F['verdict']['verdict']} (z={F['verdict']['z']}); first team "
                  f"{F['team']['verdict']['verdict']} (z={F['team']['verdict']['z']}); tip "
                  f"{F['tip']['verdict']['verdict']} (z={F['tip']['verdict']['z']}); scorer in "
                  f"our five {F['scorer_in_five']}; this season's play-by-play {len(cur_pbp)} "
                  f"games")
        elif not prior_pbp:
            print("::warning::NBA first basket: data/nba/prior_pbp.json missing - run the "
                  "'NBA prior play-by-play' workflow once.")
    except Exception as exc:  # noqa: BLE001
        print(f"::warning::NBA first basket failed: {type(exc).__name__}: {exc}")

    pool = merge_pool(prior.get("players"), cur)
    cur_from = REGULAR_SEASON_START.isoformat()
    feed = ef.fetch_injury_list(LEAGUE)
    rosters = {}
    for g in slate:
        for side in ("away", "home"):
            tid = g[f"{side}_id"]
            if tid and tid not in rosters:
                rosters[tid] = fetch_roster(tid)
    tags = sum(1 for r in rosters.values() for x in r.values() if x.get("status"))
    print(f"  [verify] NBA injuries: {tags} roster tags, {len(feed['by_id'])} league-list tags")

    book, team_dates = None, {}
    if model and model.get("context"):
        try:
            book = nc.book_now(pool, model, model["context"])
            team_dates = nc.schedules(list(prior.get("finals") or []) + cur_finals)
        except Exception as exc:  # noqa: BLE001
            print(f"::warning::NBA tonight's opponent book failed: {type(exc).__name__}: {exc}")
    n_ctx = 0
    held_total = 0
    for g in slate:
        if g.get("game_type") == "preseason":
            continue
        for side in ("away", "home"):
            tid = g[f"{side}_id"]
            roster = rosters.get(tid) or {}
            if model:
                rows, held = side_props(tid, pool, pre, model, roster, feed, team_abbr, cur_from)
                g[f"{side}_props"] = rows
            else:
                held = []
            g[f"{side}_held_out"] = held
            held_total += len(held)
            g[f"{side}_injuries"] = sorted(
                [{"name": x.get("name"), "status": x["status"]} for x in roster.values()
                 if x.get("status")], key=lambda x: (not av.is_out(x["status"]), x["name"] or ""))
            held_pids = [pid for pid, x in roster.items()
                         if av.is_out(av.status_for(pid, x.get("name"), x.get("status"), feed))]
            if model and model.get("context") and g.get(f"{side}_props"):
                try:
                    opp_side = "home" if side == "away" else "away"
                    outs = nc.outs_now(pool, tid, held_pids, team_dates.get(str(tid)), model,
                                       slate_date.isoformat())
                    names = [(pool.get(pid) or {}).get("name") or "" for pid in held_pids
                             if nc.outs_now(pool, tid, [pid], team_dates.get(str(tid)), model,
                                            slate_date.isoformat())]
                    nc.apply_tonight(g[f"{side}_props"], g[f"{opp_side}_id"],
                                     g[f"{opp_side}_abbr"], book, outs, names,
                                     model["context"], slate_date.isoformat())
                    n_ctx += len(g[f"{side}_props"])
                except Exception as exc:  # noqa: BLE001
                    print(f"::warning::NBA context for {g.get(side + '_abbr')} failed: "
                          f"{type(exc).__name__}: {exc}")
            try:
                g[f"{side}_next_man_up"] = next_man_up_boards(pool, tid, held_pids,
                                                              since="2025-10-01")
                # WHAT IF: the same board for each of his team's six
                # biggest-minute players who ARE playing, so a late
                # scratch can be read before the nightly knows about it.
                key = [r["pid"] for r in (g.get(f"{side}_props") or [])[:6]]
                g[f"{side}_what_if"] = next_man_up_boards(pool, tid, key, since="2025-10-01")
            except Exception as exc:  # noqa: BLE001
                print(f"::warning::NBA Next Man Up failed: {type(exc).__name__}: {exc}")
    # tonight's first-quarter points per player, and his first quarters on
    # the trend games (what "his line" reads)
    if model and model.get("q1"):
        try:
            _pg_all = (json.loads(PBP_PATH.read_text()).get("games") or {}) \
                if PBP_PATH.exists() else {}
            qm, cov = nq.q1_map(list(_pg_all.values()) + list(cur_pbp.values()))
            for g in slate:
                for side in ("away", "home"):
                    for r in g.get(f"{side}_props") or []:
                        games_ = (pool.get(str(r["pid"])) or {}).get("games") or []
                        hist = [nq.q1_of(r["pid"], x, qm, cov) for x in games_]
                        r["mu"]["q1pts"] = round(nq.mu(r, model["q1"], hist), 3)
                        team_on = {x[0]: str(x[1]) for x in games_}
                        for t_ in r.get("trend") or []:
                            tm = team_on.get(t_.get("date"))
                            if tm and (tm, t_["date"]) in cov and t_.get("min"):
                                t_["q1pts"] = qm.get((str(r["pid"]), t_["date"]), 0)
        except Exception as exc:  # noqa: BLE001
            print(f"::warning::NBA first-quarter points tonight failed: "
                  f"{type(exc).__name__}: {exc}")
    n_fb = 0
    if first_block and first_book:
        for g in slate:
            if g.get("game_type") == "preseason" or not (g.get("home_props") and
                                                         g.get("away_props")):
                continue
            try:
                g["first_basket"] = first_basket_game(g, first_book, first_block["params"], pool)
                n_fb += 1
            except Exception as exc:  # noqa: BLE001
                print(f"::warning::NBA first basket for {g.get('event_id')} failed: "
                      f"{type(exc).__name__}: {exc}")
        print(f"  [verify] NBA first basket priced for {n_fb} of {len(slate)} games")
    n_props = sum(len(g.get("away_props") or []) + len(g.get("home_props") or []) for g in slate)
    n_nmu = sum(len(g.get("away_next_man_up") or []) + len(g.get("home_next_man_up") or [])
                for g in slate)
    print(f"  [verify] NBA slate: {n_props} players projected, {held_total} held out (injured), "
          f"{n_nmu} Next Man Up boards; {n_ctx} with tonight's opponent / teammates-out "
          f"context applied")

    watch = role_watch(pre, prior.get("players"), top=40)
    for r in watch:
        r["team_abbr"] = team_abbr.get(str(r.get("team")), "")
    print(f"  [verify] NBA preseason role watch: {len(watch)} players"
          + (f"; biggest move {watch[0]['name']} {watch[0]['min_delta']:+} min"
             if watch and watch[0].get("min_delta") is not None else ""))

    happened = []
    try:
        happened = nba_milestones(slate, pool, cur, today)
    except Exception as exc:  # noqa: BLE001
        print(f"::warning::NBA milestones failed: {type(exc).__name__}: {exc}")

    (OUT / "games.json").write_text(json.dumps({
        "generated_at_et": now.strftime("%Y-%m-%d %H:%M"),
        "source": "ESPN public NBA API (scoreboard + game summaries + rosters)",
        "slate_date_et": slate_date.isoformat(),
        "phase": phase(today),
        "regular_season_start": cur_from,
        "games": slate,
        "model": model,
        "game_model": ({k: v for k, v in game_model.items() if k != "rates"}
                       if game_model else None),
        "sim": sim_block,
        "first_basket": ({k: v for k, v in first_block.items()} if first_block else None),
        "teams": {tid: {"abbr": a, "logo": team_logo.get(tid)} for tid, a in team_abbr.items()},
        "role_watch": watch,
        "milestones_happened": happened,
    }, ensure_ascii=False, separators=(",", ":")))
    print(f"NBA: wrote games.json ({slate_date}, {len(slate)} games)")


def prior_game_rows(prior_finals):
    """data/nba/prior_season.json finals -> the game model's finals shape."""
    return [{"date": f["date"], "home_id": f["home"], "away_id": f["away"],
             "home_score": f.get("hs"), "away_score": f.get("as")}
            for f in prior_finals or [] if f.get("home") and f.get("away")]


def nba_game_model(prior_finals, cur_finals, slate):
    from engines import nfl_game_model as ngm
    block = ngm.build(cur_finals, prior_game_rows(prior_finals))
    if not block:
        print("::warning::NBA game model not built (no finals)")
        return None
    pr, v = block["params"], block["validation"]
    print(f"  [verify] NBA game model fit on {pr['fit_on']} season: k={pr['shrink_k']} "
          f"carryover={pr.get('carryover')} sd_margin={pr['sd_margin']} sd_total={pr['sd_total']} "
          f"home_mult={block['league'].get('home_mult')}")
    if v.get("n"):
        print(f"  [verify] NBA walk-forward {v['n']} games: log loss {v['model']['log_loss']} vs "
              f"coin {v['coin_flip']['log_loss']} vs home-rate {v['home_rate']['log_loss']} "
              f"({(v.get('ml_verdict') or {}).get('verdict')}); margin MAE {v['margin_mae_model']} "
              f"vs home-edge {v['margin_mae_home_edge']} ({(v.get('spread_verdict') or {}).get('verdict')}); "
              f"total MAE {v['total_mae_model']} vs league avg {v['total_mae_league_avg']} "
              f"({(v.get('total_verdict') or {}).get('verdict')})")
    n = 0
    for g in slate:
        pj = ngm.project(block, g.get("home_id"), g.get("away_id"), g.get("odds"),
                         g.get("home_abbr", ""), g.get("away_abbr", ""))
        if pj:
            g["model"] = pj
            n += 1
    print(f"  [verify] NBA slate games with a projection: {n} of {len(slate)}")
    try:
        vb = vs_book(prior_finals, cur_finals, pr)
        block["vs_book"] = vb
        print("  [verify] NBA game model vs the book this season: " + "; ".join(
            f"{k} n={x['n']}" + (f" brier {x['brier']} -> {x['verdict']['verdict']} "
                                 f"(z={x['verdict']['z']})" if x.get("verdict") else "")
            for k, x in vb.items()))
    except Exception as exc:  # noqa: BLE001
        print(f"::warning::NBA game model vs book failed: {type(exc).__name__}: {exc}")
    return block


def vs_book(prior_finals, cur_finals, params):
    """THE GAME MODEL AGAINST THE BOOK (10-21): every finished game this
    season with a recorded line — the model's walk-forward chance of the
    OVER (normal on its projected total, sd_total) and of the HOME COVER
    (sd_margin) against the book's own 50/50 at that number, paired on
    squared error. Until this beats, game lines stay priced on the book's
    number (model weight 0). Pushes are left out."""
    from engines import game_model as gm
    from engines import model_math as mm
    from engines import nfl_game_model as ngm
    rows_f = prior_game_rows(prior_finals) + [
        {k: f.get(k) for k in ("date", "home_id", "away_id", "home_score", "away_score")}
        for f in cur_finals or []]
    fin = gm.clean_finals(ngm.rows(rows_f))
    preds = {(p["date"], str(p["home"])): p for p in ngm._wf(fin, params["shrink_k"])}
    tot, spr = [], []
    for f in cur_finals or []:
        o = f.get("odds") or {}
        p = preds.get((f["date"], str(f.get("home_id"))))
        hs, as_ = f.get("home_score"), f.get("away_score")
        if not p or hs is None or as_ is None:
            continue
        mt, mg = p["mu_h"] + p["mu_a"], p["mu_h"] - p["mu_a"]
        if o.get("total") is not None and hs + as_ != o["total"]:
            q = 1 - mm.normal_cdf(o["total"], mt, params["sd_total"])
            tot.append((q, 1 if hs + as_ > o["total"] else 0))
        if o.get("spread") is not None and hs - as_ + o["spread"] != 0:
            q = 1 - mm.normal_cdf(-o["spread"], mg, params["sd_margin"])
            spr.append((q, 1 if hs - as_ + o["spread"] > 0 else 0))
    out = {}
    for k, xs in (("total", tot), ("spread", spr)):
        out[k] = {"n": len(xs), "brier": mm.score_predictions(xs)["brier"],
                  "verdict": (mm.paired_verdict([(q - y) ** 2 for q, y in xs],
                                                [(0.5 - y) ** 2 for _q, y in xs])
                              if len(xs) >= 2 else None)}
    return out


def nba_milestones(slate, pool, cur, today):
    import milestone_log as mlog
    from engines import milestones as ms
    holders = [(r["pid"], r["name"], r) for g in slate for side in ("away", "home")
               for r in g.get(f"{side}_props") or []]
    season_of = {pid: ms.nba_season(p["games"]) for pid, p in (cur or {}).items()}
    for pid, _n, _r in holders:
        season_of.setdefault(pid, ms.nba_season([]))
    last = {}
    for pid, p in (cur or {}).items():
        gs = sorted(p["games"], key=lambda g: g[0])
        if gs:
            last[pid] = (gs[-1][0], ms.nba_season(gs[-1:]))
    since = (today - timedelta(days=mlog.HAPPENED_DAYS.get("nba", 3))).isoformat()
    also = [(pid, (cur.get(pid) or {}).get("name")) for pid, (d, _l) in last.items()
            if d and d >= since]
    res = mlog.run("nba", holders, season_of, last, today, also=also)
    print(mlog.verify_line("nba", res))
    return res["happened"]


if __name__ == "__main__":
    main()
