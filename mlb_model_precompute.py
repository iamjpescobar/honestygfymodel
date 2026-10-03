"""
MLB game model — fitted nightly from the season's real finals.

Writes data/mlb/model.json (committed by nightly-data.yml, like
lineup_lock.json), which the Game Card, the MLB Model page and the slate
builder all read. Nothing here runs on Render.

WHAT IT MEASURES
----------------
From statsapi's schedule (regular season, one call per month, hydrated
with linescore and probable pitchers):

  - every team's runs scored and allowed
  - the league run rate, home and road scoring multipliers
  - how often the home side wins a game that went to extra innings
  - shrink_k: how hard a team's own rate is pulled toward the league,
    FITTED by walk-forward log loss (engines/game_model.fit)
  - dispersion: negative-binomial size, measured on the residuals

And from each starting pitcher's statsapi game log:

  - how deep he goes (outs per start) and how many runs he allows per
    nine — each shrunk toward the league's starters by a gamma-Poisson
    prior FITTED by maximum likelihood across every starter
    (model_math.fit_gamma_prior). A 3-start call-up is mostly league
    average; a 30-start ace is mostly himself, by however much the
    season's own spread says.

THE STARTER LAYER HAS TO EARN ITS PLACE
---------------------------------------
The walk-forward is run twice — team rates only, and team rates with the
starter's share of the game replaced by his own record AS OF THE DAY
BEFORE. `use_starters` is true only if the second beats the first on log
loss. If it does not, the page shows the team-only number and says why.
A feature that does not beat the simpler model is not shown as if it
did (the NFL yardage lesson, 09-27).

One honest look-ahead: the two gamma priors are fitted on full-season
starter totals, so a walk-forward prediction in May borrows the
season's knowledge of how spread-out starters are (two numbers, not any
starter's own line). Stated in the validation block.

Run manually from Actions as part of the nightly; prints [verify] lines.
"""
import json
import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import requests

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "app"))
from engines import game_model as gm      # noqa: E402
from engines import model_math as mm      # noqa: E402
from engines.mlb_game_model import starter_layer  # noqa: E402

EASTERN = ZoneInfo("America/New_York")
OUT = ROOT / "data" / "mlb" / "model.json"
SCHEDULE = ("https://statsapi.mlb.com/api/v1/schedule?sportId=1&gameType=R"
            "&startDate={start}&endDate={end}&hydrate=linescore,probablePitcher")
GAMELOG = ("https://statsapi.mlb.com/api/v1/people/{pid}/stats"
           "?stats=gameLog&group=pitching&season={season}")


def _get(url, tries=3):
    for i in range(tries):
        try:
            r = requests.get(url, timeout=30, headers={"User-Agent": "loscappers/1.0"})
            if r.status_code == 200:
                return r.json()
        except Exception as exc:          # noqa: BLE001 — logged, retried
            print(f"  GET failed ({exc}); retry {i + 1}")
        time.sleep(1.5 * (i + 1))
    return None


def _ip_to_outs(ip):
    """'5.2' -> 17. statsapi prints thirds after the decimal point."""
    try:
        whole, _, frac = str(ip).partition(".")
        return int(whole) * 3 + (int(frac) if frac else 0)
    except (TypeError, ValueError):
        return None


def parse_schedule(payload):
    """Finals as game_model rows, plus starter ids and team names.

    Excludes anything not Final, ties (suspended-and-never-resumed games
    carry equal scores), and games with no score — MISSING IS NOT ZERO.
    """
    out = []
    for d in (payload or {}).get("dates") or []:
        for g in d.get("games") or []:
            st = g.get("status") or {}
            if st.get("abstractGameState") != "Final":
                continue
            if "postponed" in str(st.get("detailedState", "")).lower():
                continue
            t = g.get("teams") or {}
            h, a = t.get("home") or {}, t.get("away") or {}
            hs, as_ = h.get("score"), a.get("score")
            if hs is None or as_ is None or hs == as_:
                continue
            ls = g.get("linescore") or {}
            sched = ls.get("scheduledInnings") or 9
            inn = ls.get("currentInning")
            extra = (inn > sched) if isinstance(inn, int) else None
            out.append({
                "date": g.get("officialDate") or str(g.get("gameDate", ""))[:10],
                "game_pk": g.get("gamePk"),
                "home": (h.get("team") or {}).get("name"),
                "away": (a.get("team") or {}).get("name"),
                "hs": int(hs), "as": int(as_), "extra": extra,
                "home_sp": str((h.get("probablePitcher") or {}).get("id") or "") or None,
                "away_sp": str((a.get("probablePitcher") or {}).get("id") or "") or None,
                "home_sp_name": (h.get("probablePitcher") or {}).get("fullName"),
                "away_sp_name": (a.get("probablePitcher") or {}).get("fullName"),
            })
    return out


def parse_gamelog(payload):
    """[(date, runs, outs)] for STARTS only, date order."""
    starts = []
    for blk in (payload or {}).get("stats") or []:
        for sp in blk.get("splits") or []:
            s = sp.get("stat") or {}
            if not s.get("gamesStarted"):
                continue
            outs = s.get("outs")
            if outs is None:
                outs = _ip_to_outs(s.get("inningsPitched"))
            runs = s.get("runs")
            if outs is None or runs is None:
                continue
            starts.append((str(sp.get("date"))[:10], int(runs), int(outs)))
    starts.sort()
    return starts


def fit_starter_priors(logs):
    """Gamma-Poisson priors for runs per nine and outs per start, fitted
    across every starter's season. Returns {} if nothing to fit."""
    ra_obs = [(sum(r for _, r, _ in s), sum(o for *_, o in s) / 27.0)
              for s in logs.values() if s]
    out_obs = [(sum(o for *_, o in s), len(s)) for s in logs.values() if s]
    ra_mu, ra_s = mm.fit_gamma_prior([x for x in ra_obs if x[1] > 0])
    out_mu, out_s = mm.fit_gamma_prior(out_obs)
    if ra_mu is None or out_mu is None:
        return {}
    return {"ra9_mean": round(ra_mu, 4), "ra9_strength_games": round(ra_s, 3),
            "outs_mean": round(out_mu, 3), "outs_strength_starts": round(out_s, 3)}


def make_starter_fn(logs, priors):
    """starter_fn for game_model.walk_forward — his record BEFORE the
    game's date only."""
    def fn(final, side, league_rate):
        pid = final.get(f"{side}_sp")
        s = logs.get(pid) if pid else None
        if not s:
            return None
        before = [x for x in s if x[0] < final["date"]]
        rec = {"r": sum(r for _, r, _ in before), "outs": sum(o for *_, o in before),
               "gs": len(before)}
        return starter_layer(rec, priors, league_rate)
    return fn


def main(today=None, _get_json=_get):
    today = today or datetime.now(EASTERN).date()
    season = today.year
    # Regular season is March-September. Postseason games are NOT fitted
    # on — a playoff rotation and a 162-game sample are different
    # populations — but they ARE projected, from the regular season.
    start = date(season, 3, 1)
    end = min(today - timedelta(days=1), date(season, 10, 5))
    finals = []
    m = start
    while m <= end:
        nxt = (m.replace(day=28) + timedelta(days=4)).replace(day=1)
        stop = min(nxt - timedelta(days=1), end)
        payload = _get_json(SCHEDULE.format(start=m.isoformat(), end=stop.isoformat()))
        got = parse_schedule(payload)
        print(f"  schedule {m:%b}: {len(got)} finals")
        finals.extend(got)
        m = nxt
    if len(finals) < 100:
        print(f"MLB model: only {len(finals)} finals — refusing to fit on that.")
        return 1
    ex_known = sum(1 for f in finals if f["extra"] is not None)
    print(f"  [verify] {len(finals)} finals, {ex_known} with an inning count, "
          f"{sum(1 for f in finals if f['extra'])} extra-inning; "
          f"{sum(1 for f in finals if f['home_sp'] and f['away_sp'])} with both starters")

    # Starter game logs.
    pids = sorted({f[s] for f in finals for s in ("home_sp", "away_sp") if f[s]})
    names = {}
    for f in finals:
        for s in ("home", "away"):
            if f[f"{s}_sp"]:
                names[f[f"{s}_sp"]] = f[f"{s}_sp_name"]
    logs = {}
    for i, pid in enumerate(pids):
        logs[pid] = parse_gamelog(_get_json(GAMELOG.format(pid=pid, season=season)))
        if i % 50 == 0:
            print(f"  game logs {i}/{len(pids)}")
        time.sleep(0.05)
    with_logs = sum(1 for v in logs.values() if v)
    print(f"  [verify] {with_logs} of {len(pids)} starters returned a start log")
    priors = fit_starter_priors(logs)
    print(f"  [verify] starter priors: {priors}")

    model = gm.build(finals)
    if model is None:
        print("MLB model: fit failed.")
        return 1
    team_only = model["validation"]
    with_sp = None
    if priors:
        with_sp = gm.validate(finals, model["params"],
                              starter_fn=make_starter_fn(logs, priors))
    use_sp = bool(with_sp and with_sp.get("n") and team_only.get("n")
                  and with_sp["model"]["log_loss"] < team_only["model"]["log_loss"])
    model["validation"] = with_sp if use_sp else team_only
    model["validation_team_only"] = team_only
    model["validation_with_starters"] = with_sp
    model["use_starters"] = use_sp
    model["starter_priors"] = priors
    model["starters"] = {pid: {"name": names.get(pid), "gs": len(s),
                               "r": sum(r for _, r, _ in s),
                               "outs": sum(o for *_, o in s)}
                         for pid, s in logs.items() if s}
    model["sport"] = "mlb"
    model["season"] = season
    model["generated_at_et"] = datetime.now(EASTERN).strftime("%Y-%m-%d %H:%M")
    model["source"] = "statsapi.mlb.com schedule + pitcher game logs (regular season)"
    model["look_ahead_note"] = ("Starter priors (two numbers: the league's spread in "
                                "starter run prevention and depth) are fitted on full-"
                                "season totals; every team and starter rate in the "
                                "walk-forward uses only earlier games.")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(model, indent=1, sort_keys=True))
    v = model["validation"]
    print(f"MLB model: k={model['params']['shrink_k']} dispersion={model['params']['dispersion']} "
          f"home_mult={model['league']['home_mult']} extras home win={model['league']['tie_home_win']}")
    print(f"  walk-forward over {v['n']} games: log loss {v['model']['log_loss']} vs coin "
          f"{v['coin_flip']['log_loss']} vs home-rate {v['home_rate']['log_loss']} "
          f"| starters used: {use_sp}"
          + (f" (team-only {team_only['model']['log_loss']}, with starters "
             f"{with_sp['model']['log_loss']})" if with_sp else ""))
    print(f"  totals MAE {v['total_mae_model']} vs league-average {v['total_mae_league_avg']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
