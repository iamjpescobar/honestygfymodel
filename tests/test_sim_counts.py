"""
How many games each simulator page plays (10-23). Izzy: "We need to
change that 10000". The game view went 10,000 -> 50,000 (NHL, NBA,
NFL) and 25,000 (MLB: each game is played plate appearance by plate
appearance, ~4x slower); the simulator's own noise on a 50% chance goes
±0.5 -> ±0.22 points (MLB ±0.32), each page ~1-2 s. Parlays already ran
more (NBA 500k, NHL / NFL 200k, MLB 50k) and are unchanged. The page's
game cache holds 4 runs, not 8: a 50,000-game run is ~5x the memory.

Plain script — exits non-zero on failure. Reads the page sources only.

Negative control, confirmed red by exit code when written (rule 4):
  - one page's header put back to a literal "10,000 times"
    -> "every page says the number it plays" fails
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
failures = []


def check(name, ok):
    print(("ok   " if ok else "FAIL ") + name)
    if not ok:
        failures.append(name)


WANT = {"NHL": 50_000, "NBA": 50_000, "NFL": 50_000, "MLB": 25_000}
for lg, n in WANT.items():
    src = (ROOT / "app" / "views" / f"{lg}_Sim.py").read_text(encoding="utf-8")
    m = re.search(r"^N_SIMS = ([\d_]+)", src, re.M)
    got = int(m.group(1).replace("_", "")) if m else None
    check(f"{lg}: the game view plays {n:,} games", got == n)
    body = src.split('"""', 2)[-1]
    lits = [ln for ln in body.splitlines() if "10,000" in ln and not ln.lstrip().startswith("#")
            and "N_SIMS =" not in ln]
    check(f"{lg}: every page says the number it plays (no literal 10,000) {lits[:1]}",
          not lits and "{N_SIMS:,}" in src)
    caches = re.findall(r"max_entries=(\d+)\)\s*(?:#[^\n]*)?\ndef _run\(", src)
    check(f"{lg}: the game-run cache holds 4 runs (memory)", caches == ["4"])

if failures:
    print(f"\n{len(failures)} FAILED")
    sys.exit(1)
print("\nall simulator count checks passed")
