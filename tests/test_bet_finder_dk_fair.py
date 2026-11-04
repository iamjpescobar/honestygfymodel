"""
Bet Finder: markets that have not beaten DraftKings are priced at
DraftKings' fair chance (11-03) — bet_finder.dk_fair / DK_FAIR_SUPPORT,
wired in views/Bet_Finder.py.

Izzy (11-03) picked it after the check: on the graded record, the plays
where the site's chance sat 3+ points off DraftKings' lost at the book's
prices on every main NHL market (about -6%, the vig) and every main NBA
one, while the Bet Finder still showed them as THIN bets with a stake.

Plain script — exits non-zero on failure. No network.

Negative controls, confirmed red by exit code when written (rule 4):
  - dk_fair from one price (the vig left in) -> "one side posted: no fair
    chance" fails
  - DK_FAIR_SUPPORT allowed the full range -> "never STRONG on DK's fair
    chance" fails
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))
from engines import bet_finder as bf  # noqa: E402

fails = []


def check(name, ok):
    print(("ok   " if ok else "FAIL ") + name)
    if not ok:
        fails.append(name)


f = bf.dk_fair(-110, -110)
check("both prices: the no-vig chance (-110 / -110 = 50%)", abs(f - 0.5) < 1e-9)
f2 = bf.dk_fair(+150, -180)
check("a favourite's other side: under 40% after the vig comes out",
      0.35 < f2 < 0.40)
check("one side posted: no fair chance", bf.dk_fair(+150, None) is None
      and bf.dk_fair(None, -110) is None)
sup = dict(bf.DK_FAIR_SUPPORT, n=1200)
j_dk = bf.judge(f2, 150, (1000, 0.25, 0.02), -180, sup)
check("DraftKings' own price at DK's fair chance: SKIP (the vig)",
      j_dk["call"] == "SKIP" and j_dk["stake"] == 0.0)
j_better = bf.judge(f2, 190, (1000, 0.25, 0.02), -180, sup)
check("a better price than DK's fair one: a BET", j_better["call"] == "BET"
      and j_better["edge"] > 0)
j_big = bf.judge(0.5, 130, (1000, 0.25, 0.02), None, sup)
check("never STRONG on DK's fair chance (the same edge reads STRONG on a graded curve)",
      j_big["call"] == "BET" and j_big["tier"] == "value"
      and bf.judge(0.5, 130, (1000, 0.25, 0.02), None, bf.MARKET_SUPPORT)["tier"] == "strong")
src = (ROOT / "app" / "views" / "Bet_Finder.py").read_text()
check("the Bet Finder prices unproven markets at DK's fair chance, ours beside it",
      'if _mk["status"] in ("no_edge", "behind")' in src
      and "_fair = bf.dk_fair(_bp.price_at(_bk(r), ln, side)," in src
      and 'row.update(ours=ch, chance=_fair' in src and '"Our model"' in src)
check("no DK pair at the line: still THIN at most",
      "_sup = dict(_sup or {}, untested=True)" in src)

print(f"\n{len(fails)} failed" if fails else "\nall passed")
sys.exit(1 if fails else 0)
