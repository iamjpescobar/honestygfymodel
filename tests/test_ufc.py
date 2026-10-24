"""
UFC (10-24) — engines/ufc: the next card from ESPN's MMA scoreboard and
DraftKings' chances for every fight with the cut removed (win, method,
total rounds, goes the distance), the side check that never shows a
price under the wrong fighter, and the UFC page (nav, Home, the "not the
site's model" note).

Plain script — exits non-zero on failure. Shapes as ufc_probe.py printed
them on 10-24: competitions = fights, the core odds item with
awayAthleteOdds / homeAthleteOdds {favorite, moneyLine, open / close
{victoryMethod {koTkoDq, submission, points}}}, overUnder / overOdds /
underOdds, "details" naming the favourite; "Fight To Go The Distance"
props (rule 5). No network.

Negative controls, confirmed red by exit code when written (rule 4):
  - no_vig returning the raw break-even chances (cut left in)
    -> "the book's chances add to 100% (cut removed)" fails
  - pair() never swapping the sides
    -> "a price is never shown under the wrong fighter" fails
  - the distance prices read in the feed's order without the check
    -> "going the distance is matched to its own price" fails
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))
sys.path.insert(0, str(ROOT))
from engines import ufc  # noqa: E402

failures = []


def check(name, ok):
    print(("ok   " if ok else "FAIL ") + name)
    if not ok:
        failures.append(name)


def comp(cid, a, b, rec=("10-2-0", "8-3-0")):
    return {"id": cid, "type": {"abbreviation": "LW"}, "status": {"type": {"state": "pre"}},
            "competitors": [{"athlete": {"id": a, "displayName": a}, "records": [
                {"summary": rec[0]}]}, {"athlete": {"id": b, "displayName": b}, "records": [
                    {"summary": rec[1]}]}]}


SB = {"events": [{"id": "600", "name": "UFC 333", "date": "2026-10-24",
                  "competitions": [comp("11", "Daniel Santos", "Bolaji Oki"),
                                   comp("12", "Noah Gugnon", "Kody Steele")]}]}
C = ufc.card(SB)
check("the card: its fights, fighters and records in the scoreboard's order",
      C["event_id"] == "600" and [f["id"] for f in C["fights"]] == ["11", "12"]
      and C["fights"][0]["a"]["name"] == "Daniel Santos" and C["fights"][0]["a"]["record"] == "10-2-0")


def vm(ko, sub, dec):
    return {"close": {"victoryMethod": {"koTkoDq": {"american": ko}, "submission": sub,
                                        "points": {"american": dec}}}}


ITEM = {"details": "D. Santos -115", "overUnder": 2.5, "overOdds": 105, "underOdds": -135,
        "awayAthleteOdds": dict(vm("+120", "+500", "+400"), favorite=True, moneyLine=-115),
        "homeAthleteOdds": dict(vm("+150", "+600", "+450"), favorite=False, moneyLine=-105)}
O = ufc.fight_odds(C["fights"][0], ITEM, ["+165", "-220"])
check("the book's chances add to 100% (cut removed)",
      abs(O["win"]["a"] + O["win"]["b"] - 1) < 1e-9 and O["win"]["a"] > O["win"]["b"]
      and abs(sum(O["method"]["a"].values()) + sum(O["method"]["b"].values()) - 1) < 1e-9
      and abs(O["rounds"]["p_over"] + (1 - O["rounds"]["p_over"]) - 1) < 1e-9
      and O["rounds"]["p_over"] < 0.5)
flip = dict(C["fights"][0], a={"name": "Bolaji Oki"}, b={"name": "Daniel Santos"})
OF = ufc.fight_odds(flip, ITEM)
check("a price is never shown under the wrong fighter (details names the favourite)",
      OF["swapped"] and OF["ml"] == {"a": -105, "b": -115} and OF["win"]["b"] > OF["win"]["a"])
dec = O["method"]["a"]["points"] + O["method"]["b"]["points"]
O2 = ufc.fight_odds(C["fights"][0], ITEM, ["-220", "+165"])
check("going the distance is matched to its own price (agrees with the decision share)",
      abs(O["distance"]["p_yes"] - O2["distance"]["p_yes"]) < 1e-9
      and abs(O["distance"]["p_yes"] - dec) < abs((1 - O["distance"]["p_yes"]) - dec)
      and O2["distance"]["yes"] == 165)
urls = []


def get(url):
    urls.append(url)
    if "/scoreboard" in url:
        return SB
    if url.split("?")[0].endswith("/odds"):
        return {"items": [dict(ITEM, provider={"id": "100", "name": "DraftKings"})]}
    if "/propBets" in url:
        return {"items": [{"type": {"name": "Fight To Go The Distance"},
                           "odds": {"american": {"value": "+165"}}},
                          {"type": {"name": "Fight To Go The Distance"},
                           "odds": {"american": {"value": "-220"}}}]}
    return {}


B = ufc.build(get)
check("the page's build: every fight with its DraftKings chances",
      len(B["fights"]) == 2 and all(f["odds"]["win"] for f in B["fights"])
      and any("/events/600/competitions/12/odds/100/propBets" in u for u in urls))
pg = (ROOT / "app" / "views" / "UFC.py").read_text(encoding="utf-8")
app_ = (ROOT / "app" / "app.py").read_text(encoding="utf-8")
home = (ROOT / "app" / "views" / "Home.py").read_text(encoding="utf-8")
check("the UFC page is in every nav and on Home, and says these are the book's numbers",
      app_.count('("UFC", "views/UFC.py")') == 4 and '("UFC", "MLB",' in home
      and "The site&rsquo;s model is not here" in pg and "ufc.build(ef.get_json)" in pg)

if failures:
    print(f"\n{len(failures)} FAILED")
    sys.exit(1)
print("\nall UFC checks passed")
