"""
How many games each simulator page plays (10-23). Izzy: "We need to
change that 10000". The game view went 10,000 -> 50,000 (NHL, NBA,
NFL) and 25,000 (MLB: each game is played plate appearance by plate
appearance, ~4x slower); the simulator's own noise on a 50% chance goes
±0.5 -> ±0.22 points (MLB ±0.32), each page ~1-2 s. Parlays already ran
more (NBA 500k, NHL / NFL 200k, MLB 50k) and are unchanged.
10-26: the numbers now live in engines/sim_settings, one entry per sport
(each page reads its own), and the run cache is st.cache_resource kept
at that sport's "keep" (tests/test_sim_settings.py has the memory).

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


sys.path.insert(0, str(ROOT / "app"))
from engines import sim_settings as ss  # noqa: E402

WANT = {"NHL": 50_000, "NBA": 50_000, "NFL": 50_000, "MLB": 25_000}
for lg, n in WANT.items():
    src = (ROOT / "app" / "views" / f"{lg}_Sim.py").read_text(encoding="utf-8")
    check(f"{lg}: the game view plays {n:,} games, from its OWN settings",
          ss.SIMS[lg.lower()]["games"] == n and f'SIM = _ss.settings("{lg.lower()}")' in src
          and 'N_SIMS = SIM["games"]' in src)
    body = src.split('"""', 2)[-1]
    lits = [ln for ln in body.splitlines() if "10,000" in ln and not ln.lstrip().startswith("#")
            and "N_SIMS =" not in ln]
    check(f"{lg}: every page says the number it plays (no literal 10,000) {lits[:1]}",
          not lits and "{N_SIMS:,}" in src)
    check(f"{lg}: the game run is cached once (cache_resource, its sport's keep), in pieces",
          re.search(r'@st.cache_resource\(ttl=900, show_spinner=False, max_entries=SIM\["keep"\]\)'
                    r'[^\n]*\ndef _run\(', src) is not None
          and f'_ss.run("{lg.lower()}", ' in src
          and 'n=SIM["sgp"]' in src and 'chunk=SIM["sgp_chunk"]' in src)

if failures:
    print(f"\n{len(failures)} FAILED")
    sys.exit(1)
print("\nall simulator count checks passed")
