"""What actually reached the page, counted once, for both leagues.

WHY THIS IS AN ENGINE AND NOT TWO COPIES

Rule 21. KBO and NPB are read together and get bet together, so a
diagnostic that means one thing on one board and something else on the
other is worse than none. That is not hypothetical here: the first
version of this counter lived in both pipelines separately, and the two
copies disagreed within one run. KBO tested `g.get("away_starter")` for
truthiness while NPB tested it against "TBD" — and because KBO writes
`g.get("away_starter") or "TBD"`, the string "TBD" is always truthy, so
KBO reported **a named starter 5/5 on a slate with no probables at
all** while NPB reported the same field honestly. A counter that lies
is worse than no counter, because it is trusted.

WHY IT EXISTS AT ALL

Every field these pipelines fill has, at some point, been complete and
correct one step short of the page. The weather ran for days while no
view rendered it. KBO's venue and first pitch read TBD for weeks after
a markup rewrite while all 66 tests stayed green. Both were invisible
because nothing counted the OUTPUT. Rule 20, made cheap: one line per
run, on the games the reader will actually see.

WHY IT REPORTS THE CALLED-OFF COUNT

A bare `venue 0/5` reads like a broken scraper. On 2026-08-07 it meant
every game on the slate was called for extreme heat, and a called game
carries no clock — so zero was the correct answer and the fix under
test was working. An unexplained zero costs a session chasing a
non-bug; the explanation costs a few characters.
"""

TBD = "TBD"


def _has(game, key):
    """A field counts only if it holds something the reader can use.

    TBD is this codebase's honest "not known" and is therefore MISSING
    here on purpose — this measures what reaches the page, not whether
    the code ran.
    """
    v = game.get(key)
    if v is None:
        return False
    return str(v).strip() not in ("", TBD)


def coverage_line(league, slate_date, games, time_key):
    """One log line describing the slate that actually ships.

    league: "KBO" / "NPB". time_key: "time_kst" / "time_jst" — the only
    thing that legitimately differs between the two.
    """
    if not games:
        return (f"{league}: empty slate — off-day or break. "
                f"That is the honest state.")

    n = len(games)
    venue = sum(1 for g in games if _has(g, "stadium"))
    first = sum(1 for g in games if _has(g, time_key))
    named = sum(1 for g in games
                if _has(g, "away_starter") or _has(g, "home_starter"))

    # "postponed" is what both pipelines set for a called-off game;
    # KBO's POSTPONED_PAT matches "Canceled" too.
    off = sum(1 for g in games
              if "postpon" in str(g.get("status", "")).lower()
              or "cancel" in str(g.get("status", "")).lower())

    line = (f"{league}: slate {slate_date} coverage — venue {venue}/{n}, "
            f"first pitch {first}/{n}, a named starter {named}/{n}")
    if off:
        line += (f" ({off} of {n} called off — a called game carries no "
                 f"clock, so zeros here are expected)")
    return line
