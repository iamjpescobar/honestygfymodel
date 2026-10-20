"""
Bet log (10-20) — engines/bet_log, its GitHub store (a fake transport,
no network), and the wiring: the parlay slip and the Simulator log bets,
the Bet Log page is in every nav with a Bet Finder.

Plain script — exits non-zero on failure.

Negative controls, confirmed red by exit code when written (rule 4):
  - decimal() reading a minus price as p/100 like a plus price
    -> "a -110 winner pays 9.09 on 10" fails
  - summary counting open bets as losses
    -> "an open bet counts nowhere" fails
  - clv() scoring a missing close as 0
    -> "a bet with no close is left out of the closing line" fails
  - GitHubStore.save without [skip render]
    -> "a logged bet never redeploys the site" fails
"""
import base64

import random
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))
sys.path.insert(0, str(ROOT))
from engines import bet_log as bl  # noqa: E402

failures = []


def check(name, ok):
    print(("ok   " if ok else "FAIL ") + name)
    if not ok:
        failures.append(name)


T = datetime(2026, 10, 20, 19, 0)
w150 = bl.settle(bl.new_bet("NBA", "single", "A over", 0.45, 150, 10, "value", now=T), "won", now=T)
w110 = bl.settle(bl.new_bet("NBA", "single", "B over", 0.55, -110, 10, now=T), "won", now=T)
l1 = bl.settle(bl.new_bet("NHL", "parlay", "C + D", 0.30, 250, 10, now=T), "lost", now=T)
p1 = bl.settle(bl.new_bet("NFL", "single", "E", 0.5, -110, 10, now=T), "push", now=T)
op = bl.new_bet("NBA", "sgp", "F + G", 0.33, 220, 10, now=T)
check("a +150 winner pays 15 on 10", abs(bl.profit(w150) - 15.0) < 1e-9)
check("a -110 winner pays 9.09 on 10", abs(bl.profit(w110) - 100 / 11) < 1e-9)
check("a loser loses the stake, a push is 0, an open bet has no profit yet",
      bl.profit(l1) == -10 and bl.profit(p1) == 0 and bl.profit(op) is None)
check("a fake price is not a bet", bl.new_bet("NBA", "single", "x", 0.5, 50, 10) is None)

sm = bl.summary([w150, w110, l1, p1, op])
check("record and money", (sm["won"], sm["lost"], sm["push"]) == (2, 1, 1)
      and abs(sm["profit"] - round(15 + 100 / 11 - 10, 2)) < 1e-9 and sm["staked"] == 40)
check("an open bet counts nowhere (not a loss, not staked)",
      sm["open"] == 1 and sm["graded"] == 4 and sm["lost"] == 1 and sm["staked"] == 40)
check("expected wins = our chances on the decided bets (push left out)",
      abs(sm["expected_wins"] - (0.45 + 0.55 + 0.30)) < 1e-9 and sm["n_with_chance"] == 3)

# closing line: you took +150, it closed +120 -> you beat it
c1 = bl.settle(w150, "won", close=120)
check("beating the close is positive points of chance",
      abs(bl.clv(c1) - (1 / 2.2 - 1 / 2.5)) < 1e-12 and bl.clv(c1) > 0)
sm2 = bl.summary([c1, w110, l1])
check("a bet with no close is left out of the closing line, not scored 0",
      sm2["clv_n"] == 1 and abs(sm2["clv"] - round(bl.clv(c1), 4)) < 1e-12)

# model vs book on the same bets
rng = random.Random(4)
sharp, blind = [], []
for i in range(600):
    q = rng.uniform(0.15, 0.85)
    price = -110
    y = rng.random() < q
    for lst, ch in ((sharp, q), (blind, bl.break_even(price))):
        b = bl.new_bet("NBA", "single", f"b{i}", ch, price, 10, now=T)
        lst.append(bl.settle(b, "won" if y else "lost", now=T))
vs = bl.summary(sharp)["vs_book"]
vb = bl.summary(blind)["vs_book"]
print(f"     sharp model vs a -110 book: {vs['verdict']} z={vs['z']}; the book's own number: "
      f"{vb['verdict']}")
check("a model that knows the real chance beats a flat -110 book; the book's own number doesn't",
      vs["verdict"] == "beats" and vb["verdict"] != "beats")
check("model-vs-book waits for 30 graded bets", not bl.summary(sharp[:29])["vs_book_ready"]
      and bl.summary(sharp[:30])["vs_book_ready"])
check("splits by type", set(bl.by([w150, l1], "kind")) == {"single", "parlay"})

# upsert / remove / parse
lst = bl.upsert([], w150)
lst = bl.upsert(lst, bl.settle(w150, None))
check("upsert replaces by id", len(lst) == 1 and lst[0]["result"] is None)
check("remove by id", bl.remove(lst, w150["id"]) == [])
check("an uploaded file round-trips; junk is ignored",
      [b["id"] for b in bl.parse(bl.dump([w150, l1]))] == [w150["id"], l1["id"]]
      and bl.parse("not json") == [] and bl.parse('[{"x": 1}]') == [])
check("the user's file name is safe", bl.user_slug("../Izzy P!") == "izzy-p"
      and bl.user_slug(None) == "guest")


# the GitHub store over a fake transport
class Resp:
    def __init__(self, code, js=None):
        self.status_code, self._js = code, js or {}

    def json(self):
        return self._js

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(self.status_code)


class Fake:
    def __init__(self):
        self.file, self.sha, self.puts = None, None, []

    def get(self, url, headers=None, timeout=None):
        if self.file is None:
            return Resp(404)
        return Resp(200, {"content": base64.b64encode(self.file.encode()).decode(),
                          "sha": self.sha})

    def put(self, url, headers=None, json=None, timeout=None):
        self.puts.append((url, json))
        if self.sha and json.get("sha") != self.sha:
            return Resp(409)
        self.file = base64.b64decode(json["content"]).decode()
        self.sha = f"s{len(self.puts)}"
        return Resp(201, {"content": {"sha": self.sha}})


fk = Fake()
store = bl.GitHubStore("tok", "me/repo", "data/bets/izzy.json", _http=fk)
b0, s0 = store.load()
check("no file yet: an empty log", b0 == [] and s0 is None)
s1 = store.save([w150], s0, "add")
b1, s1b = store.load()
check("saved and read back", [b["id"] for b in b1] == [w150["id"]] and s1 == s1b)
url, body = fk.puts[-1]
check("a logged bet never redeploys the site or runs the nightly",
      "[skip render]" in body["message"] and "[skip ci]" in body["message"])
check("it writes the user's own file", url.endswith("/repos/me/repo/contents/data/bets/izzy.json"))
try:
    store.save([w150, l1], "stale", "add")
    stale_raised = False
except RuntimeError:
    stale_raised = True
check("a stale write is refused, not silently overwritten", stale_raised)
check("no token on the server: no store (the page says session only)",
      bl.store_for("izzy", env={}) is None
      and bl.store_for("izzy", env={"BETLOG_TOKEN": "t"}).path == "data/bets/izzy.json"
      and bl.store_for("izzy", env={"BETLOG_TOKEN": "t", "BETLOG_REPO": "me/private"}).repo
      == "me/private")

# wiring
app = (ROOT / "app" / "app.py").read_text(encoding="utf-8")
check("the Bet Log sits after every Bet Finder in the navs",
      app.count('("Bet Finder", "views/Bet_Finder.py"),\n        ("Bet Log", "views/Bet_Log.py")')
      == app.count('("Bet Finder", "views/Bet_Finder.py")') >= 4)
bf = (ROOT / "app" / "views" / "Bet_Finder.py").read_text(encoding="utf-8")
check("the parlay slip logs a parlay and a single",
      '"pl_parlay"' in bf and '"pl_single"' in bf and "_blu.log_button(" in bf)
sim = (ROOT / "app" / "views" / "NBA_Sim.py").read_text(encoding="utf-8")
check("the Simulator logs an SGP at the price you typed",
      '_blu.log_button("NBA", "sgp"' in sim and '"nbs_log"' in sim)
page = (ROOT / "app" / "views" / "Bet_Log.py").read_text(encoding="utf-8")
check("the page holds no GitHub URL or token (the engine does)",
      "api.github.com" not in page and "BETLOG_TOKEN" not in page)


if failures:
    print(f"\n{len(failures)} FAILED")
    sys.exit(1)
print("\nall bet log checks passed")
