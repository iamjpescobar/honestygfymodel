"""
NBA upgrades (10-22) — the minutes pull, the team's minutes adding up,
role changes, new team, the roster-aware margin and the nightly re-tune
(engines/nba_model, nba_context, nba_roster; nba_precompute; the pages).

Plain script — exits non-zero on failure. Synthetic worlds in the
model's tuple shape [date, team, opp, min, pts, reb, ast, tpm, stl, blk,
tov] (rule 5). No network. Never writes a tracked file (the settings
file is pointed at a temp dir).

Negative controls, confirmed red by exit code when written (rule 4):
  - Running.project pulling a RISE toward his usual minutes too
    -> "a rise is not pulled" fails
  - grid scoring the pull on whatever rows it produces (not the same rows)
    -> "the pull is scored on the same player-games" fails
  - apply_tonight skipping the team-minutes scale
    -> "tonight's rows are scaled when the rotation over-fills" fails
  - roster_points not summing the minutes to 240
    -> "the roster total is a 240-minute team" fails
  - role_dir ignoring the noise test (any 3+ minute swing)
    -> "a swing inside the noise is not a role change" fails
  - retune replacing on any challenger (ignoring its verdict)
    -> "a challenger that does not beat is not taken" fails
  - settings_step starting from last season's fit instead of the saved file
    -> "tomorrow's champion is tonight's (the saved file)" fails
"""
import json
import math
import random
import sys
import tempfile
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))
sys.path.insert(0, str(ROOT))
from engines import nba_context as nc  # noqa: E402
from engines import nba_model as nm  # noqa: E402
from engines import nba_roster as nr  # noqa: E402
from engines import nba_view as nv  # noqa: E402

failures = []


def check(name, ok):
    print(("ok   " if ok else "FAIL ") + name)
    if not ok:
        failures.append(name)


def pois(g, mu):
    L, c, p = math.exp(-mu), 0, 1.0
    while True:
        p *= g.random()
        if p < L:
            return c
        c += 1


def gm_(d, team, mn, pts=10, reb=4, ast=3, tpm=1):
    return [d, team, "X", mn, pts, reb, ast, tpm, 0, 0, 0]


# --- 1. the minutes pull ---------------------------------------------------------
lg = {"pts": 0.45, "reb": 0.15, "ast": 0.1, "tpm": 0.03}
days = [(date(2026, 1, 1) + timedelta(days=k)).isoformat() for k in range(40)]
steady = [gm_(d, "T", 30) for d in days[:30]]
r = nm.Running(2, 120)
for g in steady + [gm_(days[30], "T", 14), gm_(days[31], "T", 14)]:
    r.add(g)
p0 = r.project(600, lg, 100, 0.0)
p3 = r.project(600, lg, 100, 0.3)
long_min = r.long.m / r.long.w
check("a drop is pulled 30% of the way back toward his usual minutes",
      abs(p3["min"] - (p0["min"] + 0.3 * (long_min - p0["min"]))) < 1e-9
      and p3["mu"]["pts"] > p0["mu"]["pts"])
r2 = nm.Running(2, 120)
for g in steady + [gm_(days[30], "T", 40), gm_(days[31], "T", 40)]:
    r2.add(g)
check("a rise is not pulled", abs(r2.project(600, lg, 100, 0.3)["min"]
                                  - r2.project(600, lg, 100, 0.0)["min"]) < 1e-12)
check("project_now reads the fitted pull",
      nm.project_now(steady + [gm_(days[30], "T", 14)],
                     {"hl": 2, "k": 600, "hl_long": 120, "k_long": 100, "down_pull": 0.3,
                      "league": {"F": lg}}, "F")["min"]
      > nm.project_now(steady + [gm_(days[30], "T", 14)],
                       {"hl": 2, "k": 600, "hl_long": 120, "k_long": 100,
                        "league": {"F": lg}}, "F")["min"])


# --- the world: rotations that must add to 240, one-night dips, rest nights,
#     and players who change teams mid-season ---------------------------------------
def world(seed=3, teams=6, per=9, ndays=150, movers=4):
    g = random.Random(seed)
    ps = {}
    for t in range(teams):
        for j in range(per):
            ps[f"{t}-{j}"] = {"name": f"P{t}-{j}", "pos": "GFC"[j % 3], "team": f"T{t}",
                              "base": 36 - 2.6 * j, "rate": g.uniform(.35, .75), "games": []}
    move_day = ndays // 2
    moving = [f"{t}-{1}" for t in range(movers)]       # a starter moves to the next team
    finals = []
    start = date(2025, 10, 21)
    for k in range(ndays):
        d = (start + timedelta(days=k)).isoformat()
        if k == move_day:
            for x in moving:
                t = int(ps[x]["team"][1:])
                ps[x]["team"] = f"T{(t + 1) % teams}"
        order = list(range(teams))
        g.shuffle(order)
        for a, h in zip(order[::2], order[1::2]):
            sc = {}
            for me in (a, h):
                roster = [x for x, p in ps.items() if p["team"] == f"T{me}"]
                play = [x for x in roster if g.random() > 0.12]          # rest / injury nights
                base = {x: ps[x]["base"] for x in play}
                for x in play:
                    if g.random() < 0.15:
                        base[x] *= 0.45                                 # foul trouble: one night
                f = 240.0 / sum(base.values())
                tot = 0
                for x in play:
                    m = max(4.0, g.gauss(base[x] * f, 2.0))
                    pts = pois(g, m * ps[x]["rate"])
                    tot += pts
                    ps[x]["games"].append([d, f"T{me}", f"T{a if me == h else h}", round(m, 1),
                                           pts, pois(g, m * .16), pois(g, m * .1),
                                           pois(g, m * .04), 0, 0, 0])
                sc[me] = tot
            finals.append({"date": d, "home": f"T{h}", "away": f"T{a}", "hs": sc[h], "as": sc[a]})
    players = {x: {k: v for k, v in p.items() if k in ("name", "pos", "team", "games")}
               for x, p in ps.items()}
    return {"players": players, "finals": finals}, moving


W, MOVERS = world()
# the four shrink settings held at last season's fit (the grid itself is
# test_nba's); the pull is what this fit decides
nm.FIT_HL, nm.FIT_K, nm.FIT_HL_LONG, nm.FIT_K_LONG = (2,), (600,), (120,), (100,)
params = nm.fit(W["players"])
print(f"     synthetic fit: hl {params['hl']} k {params['k']} pull {params['down_pull']} "
      f"pull test {params['pull_test']}")
check("where one-night drops are noise, the fit pulls them back and it beats no pull unseen",
      params["down_pull"] > 0 and (params["pull_test"] or {}).get("verdict") == "beats")
src = (ROOT / "app" / "engines" / "nba_model.py").read_text(encoding="utf-8")
check("the pull is scored on the same player-games as no pull",
      "e = _sse([r for r in rows if (r[0], r[1][0]) in keys])" in src)

# --- 2. the team's minutes add up -------------------------------------------------------
check("the scale: (T / sum) ^ beta, clipped",
      abs(nc.vol_factor(250, {"t": 220, "beta": 0.5}) - (220 / 250) ** 0.5) < 1e-12
      and nc.vol_factor(1000, {"t": 220, "beta": 1}) == nc.VOL_CLIP[0]
      and nc.vol_factor(250, None) == 1.0 and nc.vol_factor(None, {"t": 220, "beta": .5}) == 1.0)
mdl = {k: v for k, v in params.items() if k != "fit_rows"}
vols = nc.rotation_minutes(W["players"], mdl)
first_day = min(g[0] for p in W["players"].values() for g in p["games"])
check("the rotation sum is walk-forward (nobody is projected on his first game)",
      not any(k[1] == first_day for k in vols))
ctx = nc.fit(W, mdl)
print(f"     synthetic context: vol {ctx['vol']} tried {ctx['vol_tried']} test {ctx['vol_test']}")
check("where a team's minutes must add to 240, the scale ships and beats unseen",
      ctx["vol"] is not None and (ctx["vol_test"] or {}).get("verdict") == "beats")
rows_t = [{"pid": str(i), "pos": "G", "min": 32.0, "why": "",
           "mu": {"pts": 15.0, "reb": 5.0, "ast": 4.0, "tpm": 1.5, "pra": 24.0, "pr": 20.0,
                  "pa": 19.0, "ra": 9.0}} for i in range(9)]           # 288 projected minutes
nc.apply_tonight(rows_t, "O", "OPP", None, [], [], {"vol": {"t": 220.0, "beta": 0.5}},
                 "2026-11-01")
f_ = (220 / 288) ** 0.5
check("tonight's rows are scaled when the rotation over-fills (and say why)",
      abs(rows_t[0]["mu"]["pts"] - round(15 * f_, 3)) < 1e-3 and rows_t[0]["ctx"]["vol"] < 1
      and "team minutes" in rows_t[0]["why"]
      and abs(rows_t[0]["mu"]["pra"] - (rows_t[0]["mu"]["pts"] + rows_t[0]["mu"]["reb"]
                                         + rows_t[0]["mu"]["ast"])) < 0.01)

# --- 3. role changes ---------------------------------------------------------------------
check("a 3-game run 10 minutes over his projection is ROLE up; 10 under is ROLE down",
      nm.role_dir(38, 28, 3, 6.5) == "up" and nm.role_dir(18, 28, 3, 6.5) == "down")
check("a swing inside the noise is not a role change (4 min over 3 games)",
      nm.role_dir(32, 28, 3, 6.5) is None)
check("too few games: no flag", nm.role_dir(40, 28, 2, 6.5) is None)
season = [gm_(d, "T", 20) for d in days[:30]]
cur = [gm_(f"2026-10-2{k}", "T", 34) for k in range(1, 5)]
pr_ = {"hl": 2, "k": 600, "hl_long": 120, "k_long": 100, "league": {"F": lg}}
rn = nm.role_now(season + cur, pr_, "F", "2026-10-20", 6.5)
check("tonight's flag reads this season against his opening-night projection",
      rn and rn["dir"] == "up" and rn["n"] == 4 and abs(rn["was"] - 20) < 0.5)
rc = nm.role_check(W["players"], mdl, nm.minutes_sd(nm.walk(
    W["players"], mdl["hl"], mdl["k"], mdl["league"], "0000", "9999", mdl["hl_long"],
    mdl["k_long"], mdl["down_pull"])))
print(f"     synthetic role check: {rc}")
check("the role check measures how much of a flagged change held",
      rc and rc.get("sd_min") and any((rc.get(k) or {}).get("n") for k in ("up", "down")))

# --- 4. new team ----------------------------------------------------------------------------
import nba_precompute as npc  # noqa: E402
ab = {"1": "OLD", "2": "NEW"}
old = [gm_(d, "1", 30) for d in days[:20]]
check("three games with tonight's team after 20 with another: NEW TEAM (from OLD)",
      npc.new_team(old + [gm_(d, "2", 30) for d in days[20:23]], "2", ab) == "OLD")
check("traded but no game yet for the new team: NEW TEAM", npc.new_team(old, "2", ab) == "OLD")
check("15+ games with tonight's team, or only ever his team: no flag",
      npc.new_team(old + [gm_(d, "2", 30) for d in days[20:36]], "2", ab) is None
      and npc.new_team(old, "1", ab) is None)
check("the page tags read the flags",
      nv.tags({"new_team": "OLD", "role": {"dir": "down"}}) == " · NEW TEAM · ROLE ↓"
      and nv.tags({"new": True}) == " · NEW" and nv.tags({}) == "")

# --- 5. the roster-aware margin ------------------------------------------------------------
check("the roster total is a 240-minute team",
      abs(nr.roster_points([(30, 15), (30, 15), (60, 30)]) - 120.0) < 1e-9
      and abs(nr.roster_points([(230, 115), (None, None)]) - (115 + nr.LOW_PTS) * 240
              / (230 + nr.LOW_MIN)) < 1e-9 and nr.roster_points([]) is None)
check("the blend moves the margin a share w toward the rosters'",
      nr.blend_margin(4.0, 10.0, 0.25) == 5.5 and nr.blend_margin(4.0, 10.0, 0.0) == 4.0
      and nr.blend_margin(4.0, None, 0.5) == 4.0)
gmp = {"shrink_k": 3.0, "sd_margin": 14.0, "sd_total": 19.0}
dates_w = sorted({f["date"] for f in W["finals"]})
rb = nr.fit(W["players"], W["finals"], mdl, gmp, [dates_w[-90], dates_w[-45]],
            [dates_w[-45], dates_w[-1]])
print(f"     synthetic roster margin: {rb}")
check("the roster fit reports its weight, both MAEs and a verdict on unseen games",
      rb and "w" in rb and rb["mae"]["ratings"] > 0 and (rb.get("test") or {"verdict": 1})
      .get("verdict") is not None and (rb["w"] == 0 or rb["test"]["verdict"] == "beats"))
from engines import nfl_game_model as ngm  # noqa: E402
blk = {"rates": {"A": {"off": 1.0, "def": 1.0}, "B": {"off": 1.0, "def": 1.0}},
       "league": {"league_rate": 110.0, "home_mult": 1.0},
       "params": {"sd_margin": 14.0, "sd_total": 19.0}}
try:
    pj = ngm.project(blk, "A", "B", {}, "A", "B", mu=(115.0, 105.0))
    check("the game model takes the blended scores (margin, total, win chance follow)",
          pj["margin"] == 10.0 and pj["total"] == 220.0 and pj["p_home"] > 0.7)
except Exception as exc:  # noqa: BLE001
    check(f"the game model takes the blended scores ({type(exc).__name__}: {exc})", False)

# --- 6. the nightly re-tune --------------------------------------------------------------
short = nm.retune(W["players"], nm.settings_of(mdl), "2026-04-01")
check("no season to re-tune on yet: a note, nothing replaced",
      "note" in short and not short.get("replace"))
cur_from = dates_w[-35]
nm.RETUNE_MIN_ROWS = 300                 # a small world; the rule is the same
nm.FIT_HL, nm.FIT_K = (2, 10), (100, 600)
bad = dict(nm.settings_of(mdl), hl=10, k=100, down_pull=0.0)
rt = nm.retune(W["players"], bad, cur_from)
print(f"     synthetic re-tune vs a poor champion: {rt}")
check("a challenger that beats the champion on the newest unseen games replaces it",
      rt.get("replace") and rt["verdict"]["verdict"] == "beats"
      and rt["window"][0] > rt["fit_window"][0] and rt["fit_window"][1] == rt["window"][0])
_real = nm.paired_dev
nm.paired_dev = lambda *a, **k: {"n": 99, "z": 0.4, "verdict": "thin"}
try:
    rt2 = nm.retune(W["players"], bad, cur_from)
finally:
    nm.paired_dev = _real
check("a challenger that does not beat is not taken", rt2.get("replace") is False)

tmp = Path(tempfile.mkdtemp())
npc.SETTINGS_PATH = tmp / "settings.json"
_rt = nm.retune
base_model = dict(mdl)
nm.retune = lambda *a, **k: {"note": "too early"}
try:
    m1, _r = npc.settings_step(dict(base_model), W["players"], "2026-10-20", "2026-10-22")
    saved1 = json.loads(npc.SETTINGS_PATH.read_text())
    check("first night: the file is written with last season's settings, in use since today",
          saved1["settings"] == nm.settings_of(base_model) and saved1["since"] == "2026-10-22"
          and m1["settings"]["since"] == "2026-10-22" and m1["settings"]["check"]["note"])
    saved1["settings"] = dict(saved1["settings"], k=300)
    npc.SETTINGS_PATH.write_text(json.dumps(saved1))
    m2, _r = npc.settings_step(dict(base_model), W["players"], "2026-10-20", "2026-10-23")
    check("tomorrow's champion is tonight's (the saved file)",
          m2["k"] == 300 and m2["settings"]["since"] == "2026-10-22")
    chal = dict(nm.settings_of(base_model), hl=3)
    nm.retune = lambda *a, **k: {"replace": True, "challenger": chal, "n": 2000,
                                 "verdict": {"verdict": "beats", "z": 2.5},
                                 "window": ["2026-11-20", "2026-12-03"],
                                 "fit_window": ["2026-10-01", "2026-11-20"]}
    m3, _r = npc.settings_step(dict(base_model), W["players"], "2026-10-20", "2026-12-04")
    saved3 = json.loads(npc.SETTINGS_PATH.read_text())
    check("a winning challenger is saved, dated, logged and used tonight",
          m3["hl"] == 3 and saved3["since"] == "2026-12-04" and len(saved3["history"]) == 1
          and saved3["history"][0]["from"]["k"] == 300 and m3["settings"]["changes"] == 1
          and "re-tuned" in saved3["source"])
finally:
    nm.retune = _rt

# --- 7. wiring ---------------------------------------------------------------------------
pc = (ROOT / "nba_precompute.py").read_text(encoding="utf-8")
check("the nightly re-tunes, measures roles, ships the team-minutes piece and the rosters",
      "settings_step(model, season_data[\"players\"]" in pc and "nm.role_check(" in pc
      and '"vol",' in pc and "nr.fit(season_data[\"players\"]" in pc
      and "nr.roster_points(" in pc and "mu=((tot + mg) / 2, (tot - mg) / 2)" in pc
      and '"role": nm.role_now(' in pc and '"new_team": new_team(' in pc)
wf = (ROOT / ".github" / "workflows" / "nightly-data.yml").read_text(encoding="utf-8")
check("the nightly commits the settings file", wf.count("data/nba/settings.json") >= 2)
nba = (ROOT / "app" / "views" / "NBA.py").read_text(encoding="utf-8")
check("Tonight shows the settings in use, the roster margin and the flags",
      'model.get("settings")' in nba and "Tonight\\'s rosters say" in nba and "nv.tags(r)" in nba
      and "nv.tags_note(" in nba)
check("Props and the Bet Finder tag the players",
      "nv.tags(r)" in (ROOT / "app" / "views" / "NBA_Props.py").read_text(encoding="utf-8")
      and "nv.tags(r)" in (ROOT / "app" / "views" / "Bet_Finder.py").read_text(encoding="utf-8"))
check("every page's 'in the number' says when the team-minutes piece is on",
      "240 minutes" in nv.in_the_number({"context": {"opp": {"pts": {"hl": 30}}, "vol": {"t": 220}}}))

if failures:
    print(f"\n{len(failures)} FAILED")
    sys.exit(1)
print("\nall NBA upgrade checks passed")
