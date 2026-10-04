"""
Top Plays — log tonight's plays before the games and grade them after
(engines/top_plays_board has the rules; this is the I/O).

    python top_plays_log.py mlb          # slate-picks: grade, then log
    (NHL is logged and graded inside nhl_precompute — it already holds
     the slate and every final's box score)

MLB plays are built exactly as the MLB Model page builds them: each
lineup (confirmed, else last game's) against the opposing starter
through the prop model, plus each starter against the lineup he faces.
Graded from statsapi's boxscore: batting lines for batter plays, the
STARTER's pitching line for pitcher plays (didn't start -> void).

Prints [verify] lines. A failure costs the plays, never the slate.
"""
import sys
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "app"))

from engines import top_plays_board as tpb  # noqa: E402
from engines import mlb_props as mp         # noqa: E402

EASTERN = ZoneInfo("America/New_York")
BOX = "https://statsapi.mlb.com/api/v1/game/{pk}/boxscore"
FEED_STATUS = "https://statsapi.mlb.com/api/v1/schedule?sportId=1&gamePk={pk}"
# Module-level so a test can point it at a sandbox (rule: no test writes
# the real record).
PLAYS_ROOT = ROOT / "data" / "top_plays"


# ----------------------------------------------------------------------
# MLB: candidates
# ----------------------------------------------------------------------
def mlb_candidates(games, pm, batter_counts, pitcher_counts, lineup_for, date_str):
    """Every tested MLB prop for tonight. batter_counts(pid) / pitcher_counts(pid)
    -> outcome counts (this season) or None; lineup_for(game, side) -> [batter
    dicts with id/name/battingOrder]."""
    from engines.lineup_slot import _slot_from_batting_order
    out = []
    for g in games or []:
        pk, start = g.get("game_pk"), g.get("game_time")
        if not pk or not start:
            continue
        label = f"{g.get('away')} @ {g.get('home')}"
        for side, team, opp_pid in (("away", g.get("away"), g.get("home_pitcher_id")),
                                    ("home", g.get("home"), g.get("away_pitcher_id"))):
            batters = [b for b in (lineup_for(g, side) or []) if not b.get("is_pitcher")]
            p_counts = mp.player_counts(pm, opp_pid, pitcher_counts(opp_pid) if opp_pid else None,
                                        "pitcher") if opp_pid else None
            bf = mp.starter_bf_dist((pm.get("starter_bf") or {}).get(str(opp_pid)), pm,
                                    (pm.get("prior_bf") or {}).get(str(opp_pid))) if opp_pid else None
            seen, order = set(), [None] * 9
            for i, b in enumerate(batters):
                slot = _slot_from_batting_order(b.get("battingOrder")) or (i + 1)
                if slot in seen or not (1 <= slot <= 9):
                    continue
                seen.add(slot)
                c = mp.player_counts(pm, b.get("id"), batter_counts(b.get("id")), "batter")
                if not (c and c.get("PA")):
                    continue
                order[slot - 1] = c
                pj = mp.project_batter(slot, c, p_counts, pm, bf)
                if not pj:
                    continue
                for key, lab, stat, n in mp.MARKETS:
                    if key in pj["probs"]:
                        out.append({"sport": "mlb", "game_id": pk, "game": label, "start": start,
                                    "date": date_str, "player_id": b.get("id"),
                                    "player": b.get("name"), "team": team, "market": key,
                                    "label": lab, "stat": stat, "at_least": n,
                                    "p": pj["probs"][key]})
            # the starter facing this lineup
            if opp_pid and p_counts and p_counts.get("PA") and bf:
                pp = mp.project_pitcher(order, p_counts, pm, bf)
                if pp:
                    name = g.get("home_pitcher") if side == "away" else g.get("away_pitcher")
                    for key, lab, stat, n in mp.PITCHER_MARKETS:
                        out.append({"sport": "mlb", "game_id": pk, "game": label, "start": start,
                                    "date": date_str, "player_id": opp_pid, "player": name,
                                    "team": g.get("home") if side == "away" else g.get("away"),
                                    "market": key, "label": lab, "stat": "p_" + stat,
                                    "at_least": n, "p": pp["probs"][key]})
    return out


def mlb_validation(pm):
    v = dict((pm or {}).get("validation") or {})
    v.update((pm or {}).get("pitcher_validation") or {})
    return v


# ----------------------------------------------------------------------
# MLB: grading
# ----------------------------------------------------------------------
def parse_box(box, status_payload=None):
    """{"final", "players": {pid: {h,tb,hr,k,bb,s,d,rbi, p_k,p_h,p_bb,p_hr}}}.
    Walks include hit-by-pitch (the model's walk outcome does). A
    pitcher's line is kept only for the game's STARTER."""
    final = False
    for d in (status_payload or {}).get("dates") or []:
        for gg in d.get("games") or []:
            final = (gg.get("status") or {}).get("abstractGameState") == "Final"
    players = {}
    for side in ("home", "away"):
        for key, pl in (((box or {}).get("teams") or {}).get(side, {}).get("players") or {}).items():
            pid = str((pl.get("person") or {}).get("id") or key.lstrip("ID"))
            stt = pl.get("stats") or {}
            bat, pit = stt.get("batting") or {}, stt.get("pitching") or {}
            row = {}
            if bat.get("plateAppearances"):
                h, d, t, hr = (int(bat.get(k) or 0) for k in ("hits", "doubles", "triples", "homeRuns"))
                row.update({"h": h, "tb": h + d + 2 * t + 3 * hr, "hr": hr,
                            "k": int(bat.get("strikeOuts") or 0),
                            "bb": int(bat.get("baseOnBalls") or 0) + int(bat.get("hitByPitch") or 0),
                            "s": h - d - t - hr, "d": d, "rbi": int(bat.get("rbi") or 0)})
            if pit.get("gamesStarted"):
                row.update({"p_k": int(pit.get("strikeOuts") or 0), "p_h": int(pit.get("hits") or 0),
                            "p_bb": int(pit.get("baseOnBalls") or 0) + int(pit.get("hitBatsmen") or 0),
                            "p_hr": int(pit.get("homeRuns") or 0)})
            if row:
                players[pid] = row
    return {"final": final, "players": players}


def _get(url, tries=3):
    import requests
    for i in range(tries):
        try:
            r = requests.get(url, timeout=30, headers={"User-Agent": "loscappers/1.0"})
            if r.status_code == 200:
                return r.json()
        except Exception as exc:          # noqa: BLE001
            print(f"  GET failed ({exc}); retry {i + 1}")
        time.sleep(1.5 * (i + 1))
    return None


def mlb_lines_for(game_pk, _get_json=_get):
    st = _get_json(FEED_STATUS.format(pk=game_pk))
    if not st:
        return None
    return parse_box(_get_json(BOX.format(pk=game_pk)), st)


# ----------------------------------------------------------------------
# NHL (called from nhl_precompute)
# ----------------------------------------------------------------------
def nhl_candidates(slate, date_str):
    from engines import nhl_model as nm
    out = []
    for g in slate or []:
        if not g.get("start_et") or g.get("game_type") == "preseason":
            continue
        label = f"{g.get('away')} @ {g.get('home')}"
        for side in ("away", "home"):
            for r in g.get(f"{side}_props") or []:
                for key, lab, stat, n in nm.MARKETS:
                    p = (r.get("probs") or {}).get(key)
                    if p is None:
                        continue
                    out.append({"sport": "nhl", "game_id": g["event_id"], "game": label,
                                "start": g["start_et"], "date": date_str,
                                "player_id": r.get("pid"), "player": r.get("name"),
                                "team": g.get(side), "market": key, "label": lab,
                                "stat": stat, "at_least": n, "p": p})
    return out


def nhl_box_by_event(skaters):
    """{event_id: {"final": True, "players": {pid: {sog,g,a,pts}}}} from
    nhl_precompute's parsed finals (only finals are parsed there)."""
    out = {}
    for pid, rec in (skaters or {}).items():
        for eid, ln in (rec.get("games") or {}).items():
            box = out.setdefault(str(eid), {"final": True, "players": {}})
            g, a = ln.get("g"), ln.get("a")
            box["players"][str(pid)] = {"sog": ln.get("sog"), "g": g, "a": a,
                                        "pts": None if g is None or a is None else g + a}
    return out


# ----------------------------------------------------------------------
def main_mlb():
    from engines.slate_guard import load_slate
    from engines.roster import get_confirmed_lineup, get_last_starting_lineup
    from engines.statcast_engine import _get_batter_df, _get_pitcher_df

    g_n, v_n = tpb.grade("mlb", mlb_lines_for, root=PLAYS_ROOT)
    print(f"top plays mlb: graded {g_n}, voided {v_n}")
    pm = mp.load_prop_model()
    if not pm:
        print("top plays mlb: no prop model in this archive — nothing logged.")
        return 0
    games, slate_date, current = load_slate("mlb")
    if not games or not current:
        print("top plays mlb: no current slate.")
        return 0

    def counts(loader, pid):
        try:
            df, _e = loader(int(pid))
            return mp.outcome_counts(df)
        except Exception:
            return None

    def lineup_for(g, side):
        lu, ok = get_confirmed_lineup(g.get("game_pk"), side)
        if ok and lu:
            return lu
        last, _d, ok2 = get_last_starting_lineup(g.get(side))
        return last if ok2 else []

    cands = mlb_candidates(games, pm, lambda p: counts(_get_batter_df, p),
                           lambda p: counts(_get_pitcher_df, p), lineup_for,
                           slate_date or datetime.now(EASTERN).date().isoformat())
    plays = tpb.select(cands, mlb_validation(pm))
    n = tpb.log_plays("mlb", plays, root=PLAYS_ROOT)
    print(f"  [verify] top plays mlb: {len(cands)} candidate props, {len(plays)} selected, "
          f"{n} new logged")
    for p in plays[:5]:
        print(f"    {p['player']} {p['label']}: {100 * p['p_cal']:.1f}% (raw {100 * p['p']:.1f}%), "
              f"pay no worse than {p['fair']}")
    return 0


if __name__ == "__main__":
    which = (sys.argv[1:] or ["mlb"])[0]
    if which != "mlb":
        print("NHL top plays are logged by nhl_precompute.")
        sys.exit(0)
    try:
        sys.exit(main_mlb())
    except Exception as exc:  # noqa: BLE001
        print(f"::warning::top plays mlb failed: {type(exc).__name__}: {exc}")
        sys.exit(0)
