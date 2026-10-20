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
from engines import nba_model as nm  # noqa: E402

EASTERN = ZoneInfo("America/New_York")
LEAGUE = "nba"
OUT = Path("build_data") / "data" / "nba"
PRIOR_PATH = ROOT / "data" / "nba" / "prior_season.json"
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
        proj = nm.project_now(p["games"], params, p.get("pos"))
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

    model = None
    try:
        if prior.get("players"):
            t0 = time.time()
            params = nm.fit(prior["players"])
            if params.get("hl"):
                model = {k: v for k, v in params.items() if k != "fit_rows"}
                print(f"  [verify] NBA model fit on 2025-26 ({time.time() - t0:.0f}s): half-life "
                      f"{params['hl']} games, shrink {params['k']} min, fit window "
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

    # THE GAME MODEL (10-20): the NFL module's normal margin / total on
    # team ratings — basketball scores are big and near-normal, the same
    # shape — fitted on 2025-26 while this season is young, then this
    # season's games move it; anchored to the market by its fitted weight.
    game_model = None
    try:
        game_model = nba_game_model(prior.get("finals"), cur_finals, slate)
    except Exception as exc:  # noqa: BLE001
        print(f"::warning::NBA game model failed: {type(exc).__name__}: {exc}")

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
    n_props = sum(len(g.get("away_props") or []) + len(g.get("home_props") or []) for g in slate)
    n_nmu = sum(len(g.get("away_next_man_up") or []) + len(g.get("home_next_man_up") or [])
                for g in slate)
    print(f"  [verify] NBA slate: {n_props} players projected, {held_total} held out (injured), "
          f"{n_nmu} Next Man Up boards")

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
    return block


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
