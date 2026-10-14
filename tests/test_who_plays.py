"""
Who is actually playing (10-14) — engines/availability, the NHL and NFL
nightlies' pool gates, and the boards that read them.

Plain script — exits non-zero on failure. Rows carry the shapes the
nightlies write: NFL players from nfl_precompute.player_summaries, NFL
roster entries from its _walk_roster, NHL prop rows from nhl_model,
ESPN's league injury list as its site API sends it — rule 5.

Negative controls, confirmed red by exit code when written (rule 4):
  - is_out matching only the word "out" (the old NFL check)
    -> "Injured Reserve is out" fails
  - side_players without the out filter before the role cap
    -> "a healthy 7th receiver takes the IR receiver's slot" fails
  - long_shots.nhl_players without the flag
    -> "a skater who missed his team's last game is flagged on Long Shots" fails
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))
sys.path.insert(0, str(ROOT))

from engines import availability as av  # noqa: E402
from engines import edge_boards as eb  # noqa: E402
from engines import long_shots as ls  # noqa: E402

failures = []


def check(name, cond):
    print(("PASS " if cond else "FAIL ") + name)
    if not cond:
        failures.append(name)


# --- 1. the one reading of a tag ------------------------------------------
for s in ("Out", "Injured Reserve", "IR", "Injured Reserve - Designated for Return",
          "Long-Term Injured Reserve", "LTIR", "Physically Unable to Perform", "PUP-R",
          "Suspension", "Suspended", "Reserve/Non-Football Injury", "Inactive"):
    check(f"{s} is out", av.is_out(s))
for s in ("Questionable", "Doubtful", "Day-To-Day", "Probable", "Active", "", None):
    check(f"{s!r} is not out", not av.is_out(s))
check("Injured Reserve is out", av.is_out("Injured Reserve"))
check("Doubtful / Day-to-day read as 'may not play'",
      av.maybe_label("Doubtful") == "Doubtful" and av.maybe_label("Day-To-Day") == "Day-to-day")
check("Out is never a 'maybe'", av.maybe_label("Out") is None)
row = {"status": "Day-To-Day", "last_game": "2026-10-10", "team_last_game": "2026-10-12"}
check("the flag names both reasons", av.flag(row) == "Day-to-day · missed last game")
check("a healthy player who played last time has no flag",
      av.flag({"last_game": "2026-10-12", "team_last_game": "2026-10-12"}) == "")
check("no dates is no flag (missing is not a miss)", av.flag({}) == "")

# --- 2. ESPN's league list ------------------------------------------------
feed = av.parse_injury_feed({"injuries": [
    {"displayName": "Boston Bruins", "injuries": [
        {"status": "Out", "athlete": {"displayName": "Charlie McAvoy",
                                      "links": [{"href": "https://www.espn.com/nhl/player/_/id/3900169/charlie-mcavoy"}]}},
        {"status": "Day-To-Day", "athlete": {"id": "4565", "displayName": "Pavel Zacha"}}]},
    {"displayName": "Broken", "injuries": [{"athlete": {"id": "1"}}, "junk"]}]})
check("the id comes from the athlete, else from his link",
      feed["by_id"] == {"3900169": "Out", "4565": "Day-To-Day"})
check("names are matched without accents or punctuation",
      av.status_for("x", "charlie mcavoy", None, feed) == "Out")
check("the roster's own tag wins over the list", av.status_for("4565", "Pavel Zacha",
                                                              "Questionable", feed) == "Questionable")
check("an unreadable payload is no tags, never a crash",
      av.parse_injury_feed(None) == {"by_id": {}, "by_name": {}}
      and av.parse_injury_feed({"injuries": "x"}) == {"by_id": {}, "by_name": {}})

# --- 3. NFL: out BEFORE the cap ------------------------------------------
import nfl_precompute as npc  # noqa: E402

players = {}
for i in range(7):                                     # 7 receivers, most volume first
    players[f"w{i}"] = {"pid": f"w{i}", "name": f"WR {i}", "team": "Home A",
                        "rece_tgt": 10 - i, "rece_rec": 6}
roster = {f"w{i}": {"name": f"WR {i}", "pos": "WR", "status": None} for i in range(7)}
roster["w0"]["status"] = "Injured Reserve"
got = [r["pid"] for r in npc.side_players("Home A", players, roster)]
check("the IR receiver is not on the card", "w0" not in got)
check("a healthy 7th receiver takes the IR receiver's slot", "w6" in got and len(got) == 6)
rep = [{"name": "WR 1", "status": "Out"}, {"name": "WR 2", "status": "Questionable"}]
got = {r["pid"]: r for r in npc.side_players("Home A", players, roster, rep)}
check("the game's injury report removes an Out player the roster did not tag", "w1" not in got)
check("...and a Questionable one stays, tagged", got["w2"]["status"] == "Questionable")
held = npc.held_out("Home A", players, roster, rep)
check("held out lists who would have played", held == ["WR 0 (Injured Reserve)", "WR 1 (Out)"])

# --- 4. NFL TD board drops every out tag ----------------------------------
src = (ROOT / "app" / "engines" / "edge_boards.py").read_text(encoding="utf-8")
check("the TD board reads the shared rule", "_av.is_out(r.get(\"Status\"))" in src)
mv_src = (ROOT / "app" / "engines" / "model_view.py").read_text(encoding="utf-8")
check("the NFL prop board reads the shared rule", "_av.is_out(r[\"Status\"])" in mv_src)

# --- 5. NHL: pool, rows, boards ---------------------------------------------
import nhl_precompute as nhp  # noqa: E402

sk = {"1": {"pid": "1", "name": "Hurt Guy", "team": "Boston Bruins", "gp": 5},
      "2": {"pid": "2", "name": "Fine Guy", "team": "Boston Bruins", "gp": 5},
      "3": {"pid": "3", "name": "Listed Guy", "team": "Boston Bruins", "gp": 5}}
slate = [{"away": "Boston Bruins", "home": "San Jose Sharks"}]
n = nhp.apply_availability(slate, sk, {"by_id": {}, "by_name": {av.name_key("Listed Guy"): "Out"}},
                           {"1": "Injured Reserve"})
check("roster and league-list tags both land on the skater",
      sk["1"]["status"] == "Injured Reserve" and sk["3"]["status"] == "Out"
      and "status" not in sk["2"])
check("the game lists who is held out", n == 2 and slate[0]["away_held_out"]
      == ["Hurt Guy (Injured Reserve)", "Listed Guy (Out)"])
nsrc = (ROOT / "nhl_precompute.py").read_text(encoding="utf-8")
check("the NHL pool drops them BEFORE the 18-skater cut",
      nsrc.index("not _av.is_out(p.get(\"status\"))") < nsrc.index("g[f\"{side}_skaters\"] = pool[:18]"))

p_dtd = {"name": "Maybe", "pid": "9", "pos": "C", "status": "Day-To-Day",
         "last_game": "2026-10-10", "team_last_game": "2026-10-12",
         "probs": {"g1": 0.2, "g2": 0.03, "pt1": 0.4}, "mu": {"g": 0.22}}
p_ok = {"name": "Sure", "pid": "8", "pos": "C", "last_game": "2026-10-12",
        "team_last_game": "2026-10-12", "probs": {"g1": 0.2, "g2": 0.03, "pt1": 0.4},
        "mu": {"g": 0.22}}
p_out = dict(p_ok, name="Gone", pid="7", status="Out")
g = {"away": "Boston Bruins", "home": "San Jose Sharks", "away_abbr": "BOS", "home_abbr": "SJ",
     "away_props": [p_dtd, p_ok, p_out], "home_props": [], "game_type": "regular"}
rows = {r["player"]: r for r in eb.nhl_goal_rows([g], {})}
check("Goal Edge carries the heads-up", rows["Maybe"]["flag"] == "Day-to-day · missed last game"
      and rows["Sure"]["flag"] == "")
lp = {r["_name"]: r for r in ls.nhl_players(g, {})}
check("a skater who missed his team's last game is flagged on Long Shots",
      "missed last game" in lp["Maybe (BOS)"]["_signals"])
check("an Out skater never reaches Long Shots", "Gone (BOS)" not in lp)
potd_src = (ROOT / "app" / "engines" / "edge_boards.py").read_text(encoding="utf-8")
check("Player of the Day skips any injury tag",
      "_av.is_out(p.get(\"status\")) or _av.maybe_label(p.get(\"status\"))" in potd_src)

if failures:
    print(f"\n{len(failures)} FAILED")
    sys.exit(1)
print("\nall who-plays checks passed")
