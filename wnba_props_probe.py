"""ONE-SHOT PROBE — what does a good WNBA props score actually look like?

    python wnba_props_probe.py

THE GAP THIS FILLS
------------------
hr_floors_probe measured the MLB batter distributions, so "Brl/PA 8.79"
can be read as "top decile of the league" instead of as a bare number.
The WNBA board had no equivalent, so its scores could only be read
RELATIVELY — tonight's names against each other — and a 71 consistency
score meant nothing on its own.

This produces the same table for the props board's two player-intrinsic
components. After it runs, a score on that page has a league context.

WHAT IT CAN AND CANNOT MEASURE
------------------------------
Four components make up a props score. Two are properties of the PLAYER
and are measurable from the season log alone:

    CONSISTENCY  35%   clear-rate and floor-rate against her own line
    FORM         25%   recent production vs her own season baseline

Two are properties of TONIGHT and cannot be measured without a slate:

    MATCHUP      25%   depends on who she plays
    PACE         15%   depends on the game's total

So this reports on 60% of the score. That is stated rather than papered
over — a probe that quietly reported a partial score as the whole thing
would be exactly the kind of number this repo keeps having to unwind.

NO FORMULA IS REIMPLEMENTED. `_line_for`, `_clear_rate`, `_floor_rate`
and `_scale` are imported from the engine. A probe that computed its own
clear-rate would be measuring a stat the board does not have — the same
reason hr_floors_probe stopped carrying its own copy of the floors.

AVAILABILITY IS DELIBERATELY NOT APPLIED. The board excludes players who
have not appeared recently, and rightly so. But this is measuring what
the LEAGUE looks like, not who is playable tonight, and dropping every
injured player would bias the distribution toward whoever happens to be
healthy this week.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "app"))

import pandas as pd  # noqa: E402


def main() -> int:
    import types
    # The engine imports streamlit for its cache decorators. Shim it so
    # the probe runs headless; nothing here touches the cache.
    if "streamlit" not in sys.modules:
        st = types.ModuleType("streamlit")
        st.cache_data = lambda **kw: (lambda f: f)
        sys.modules["streamlit"] = st

    from engines.wnba_props import (
        STATS, MIN_GP, MIN_MPG, MIN_LOG,
        _line_for, _clear_rate, _floor_rate, _scale,
        W_CONSISTENCY, W_FORM, W_MATCHUP, W_PACE,
    )

    players_path = ROOT / "app" / "data" / "wnba" / "players.json"
    if not players_path.exists():
        print(f"No player file at {players_path}.")
        print("Run `python app/fetch_data.py` first — this probe reads what "
              "the nightly writes and fetches nothing itself.")
        return 1

    import json
    payload = json.loads(players_path.read_text())
    players = payload.get("players") if isinstance(payload, dict) else payload
    if not players:
        print("Player file present but empty.")
        return 1
    print(f"Reading {len(players):,} players from {players_path.name}\n")

    for label, cfg in STATS.items():
        key = cfg["key"]
        rows, skipped = [], 0
        for p in players:
            if (p.get("gp") or 0) < MIN_GP:
                skipped += 1
                continue
            mpg = p.get("min") or 0
            if mpg and mpg < MIN_MPG:
                skipped += 1
                continue

            log = p.get("log") or []
            vals = [gl.get(key) for gl in log if gl.get(key) is not None]
            if key == "pra" and not vals:
                vals = [((gl.get("pts") or 0) + (gl.get("reb") or 0)
                         + (gl.get("ast") or 0)) for gl in log]
            if len(vals) < MIN_LOG:
                skipped += 1
                continue

            l15, l10 = vals[-15:], vals[-10:]
            line = _line_for(l15)
            if line is None:
                skipped += 1
                continue

            # THE ENGINE'S OWN ARITHMETIC, step for step.
            r15, r10 = _clear_rate(l15, line), _clear_rate(l10, line)
            f15 = _floor_rate(l15, line)
            consistency = None
            if r15 is not None and r10 is not None:
                clear_part = _scale(r15 * 0.6 + r10 * 0.4, 30.0, 85.0)
                floor_part = _scale(f15, 40.0, 95.0) if f15 is not None else None
                consistency = (clear_part if floor_part is None
                               else clear_part * 0.5 + floor_part * 0.5)

            season_v = p.get(cfg["season"])
            recent_v = p.get(cfg["l10"])
            form = None
            if season_v and recent_v:
                form = _scale((recent_v - season_v) / season_v * 100.0,
                              -25.0, 25.0)

            rows.append({"line": line, "clear15": r15, "floor15": f15,
                         "consistency": consistency, "form": form})

        if not rows:
            print(f"{label}: no player cleared the floors "
                  f"({MIN_GP} GP / {MIN_MPG:.0f} MPG / {MIN_LOG} log)\n")
            continue

        d = pd.DataFrame(rows)
        print("=" * 72)
        print(f"{label.upper()} — {len(d)} qualified players "
              f"({skipped} below the floors)")
        print("=" * 72)
        print(f"{'component':<16}{'median':>9}{'75th':>9}{'90th':>9}"
              f"{'max':>9}")
        for col, name in (("consistency", "CONSISTENCY"),
                          ("clear15", "  clear rate L15"),
                          ("floor15", "  floor rate L15"),
                          ("form", "FORM"),
                          ("line", "typical line")):
            s = pd.to_numeric(d[col], errors="coerce").dropna()
            if s.empty:
                print(f"{name:<16}{'—':>9}{'—':>9}{'—':>9}{'—':>9}")
                continue
            print(f"{name:<16}{s.median():>9.1f}{s.quantile(.75):>9.1f}"
                  f"{s.quantile(.90):>9.1f}{s.max():>9.1f}")
        print()

    _measured = W_CONSISTENCY + W_FORM
    print("=" * 72)
    print("HOW TO READ IT")
    print("=" * 72)
    print(f"""
The two components above are {_measured * 100:.0f}% of a props score.
MATCHUP ({W_MATCHUP * 100:.0f}%) and PACE ({W_PACE * 100:.0f}%) are
properties of tonight's game, not of the player, and cannot be measured
without a slate — so the FINAL score on the board will sit higher or
lower than these numbers depending on the matchup, and its distribution
is not this one.

CONSISTENCY is the column to internalise. It is the largest single
weight and the one a book prices worst: a line hung at a player's own
average is cleared about half the time by anybody, so clear-rate alone
separates nobody. The FLOOR RATE — how often she stayed within 20% of
the line even when she missed — is what tells a metronome apart from a
boom-or-bust scorer with the same average.

Read a player's consistency against the 75th and 90th above. A score at
the median is not a signal; it is what a randomly chosen rotation player
looks like.

FORM sits near 50 for most players by construction — it measures recent
production against her OWN season baseline, so half the league is above
and half below at any moment. A form score far from 50 is a real
departure, in either direction. Remember the board weights form at only
{W_FORM * 100:.0f}%, and deliberately: form is what the book has already
moved the line for.
""")
    return 0


if __name__ == "__main__":
    sys.exit(main())
