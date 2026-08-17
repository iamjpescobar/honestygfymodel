# Los Cappers — session handoff

**START WITH "PICK UP HERE" BELOW.** Standing rules first — every one was
learned by breaking something.

---

## HOW THIS FILE IS KEPT

**The most recent 12 entries live here. Everything older moves to
`HANDOFF_ARCHIVE.md`.**

It reached 4,317 lines and 40 entries before this rotation, and 64% of
that was superseded: entries describing defects that had since been
re-fixed, thresholds that had since been re-measured, and designs that
had since been replaced. A handoff that long stops being read, and an
unread handoff is worse than a short one — it looks like the context is
there.

Git has the full history. This file's job is **what is true now** plus
**the lessons that outlive their own entry**, which is what the rules
below are.

`tests/test_handoff_size.py` fails when this file passes its cap. When
it does, move the oldest entries to the archive — do not trim the rules.

---

## HOW WE WORK

Not preferences — these shape what a useful answer looks like here.

**The owner is on an iPad, in Codespaces.** Deliver COMPLETE FILES to
upload through GitHub's web editor, never terminal edit instructions,
never patches. One tap beats three commands. Say which folder each file
goes in — `GameCard.py` and `hr_edge_board.py` differ from
`HR_Edge_Board.py` and `hr_edge_board.py` only by case and folder, and
that has already cost a cycle.

**Every change ships with a test AND a negative control that is
confirmed red.** Break the thing on purpose, watch the test fail, put it
back. A control that stays green proves nothing, and several have —
because the fixture could not tell the two behaviours apart, or because
the edit never applied at all.

**The suite is 105 files and stays green.** Five fail in a bare
container for want of streamlit and pass in Codespaces:
test_data_paths, test_home, test_pen_roster_drift,
test_wnba_grading_honesty, test_wnba_injury_gate. Run it with:

    find . -name __pycache__ -type d -prune -exec rm -rf {} + 2>/dev/null
    for f in tests/*.py; do python "$f" >/dev/null 2>&1 || echo "FAIL $f"; done

Silence is a pass.

**`git stash` before every `git pull`,** and `git checkout --
data/mlb/games.json` after. CI rewrites that file constantly; never
commit it.

**Every batch ships a HANDOFF.md entry in the same commit.**

## WHAT THE SITE IS FOR RIGHT NOW

Not published. The owner uses it himself and records slate-breakdown
videos from it (YouTube: Slate Signals), which changes what "good"
means in two concrete ways:

- **Speed is a feature.** A page that degrades as you open more games is
  fine while browsing and painful on camera. That is why the cache
  sizing entry below exists.
- **Mornings matter.** Recording happens before first pitch, so anything
  that only works once MLB posts official data is broken for the actual
  use. That is why the wind forecast entry below exists.

## STANDING RULES

These are not history. They cost real time to learn and every one of
them has bitten more than once.

**1. MEASURE BEFORE YOU SET ANY NUMBER.** Everything on this site chosen
by eye turned out wrong, and every one was caught by writing a probe
first:

| chosen by eye | what measurement found |
|---|---|
| `Clears%` scale (10,20,30,40) | league max ~1.1 — every cell rendered bottom-tier |
| `FB95%` scale (15,25,35,45) | top two tiers unreachable; 3/4 of the league in the bottom |
| `HRWindow%` scale (15,25,35,45) | league max 41.9 never reaches the 4th cut |
| "91 EV minimum" floor | applied to EV90 (median 104.2) it cleared 373 of 373 |
| WNBA form band +/-25% | 3PM 90th percentile was exactly 100 — a quarter pinned |
| MLB form on 5 inputs | 25% of hitters at exactly -100% on Brl/PA — a wall, not a measurement |
| `XSLG_HOT` 0.550 | flagged 40.2% of buckets as "real damage" |

The probes are in the repo: `hr_floors_probe`, `wnba_props_probe`,
`mlb_form_probe`, `mlb_platoon_probe`, `mlb_weakspot_probe`. Re-run every
few weeks; distributions drift.

**2. A FIXTURE CANNOT TEST A CONSTANT IT REPLACES.** Nine tests
monkeypatched `BATTER_DIRS`, so a wrong hardcoded path was invisible to
all of them. Cross-module agreement needs a test that compares the two
modules' own literals.

**3. A TEST THAT DERIVES ITS EXPECTATION FROM THE CODE UNDER TEST
MEASURES NOTHING.** A bound asserted against its own constant stayed
green through a control that tripled it.

**4. CONFIRM EVERY NEGATIVE CONTROL GOES RED.** Several have passed
against deliberately broken code — because the fixture could not tell
the two behaviours apart (every game had the same PA count), or because
the edit never applied (a shell heredoc turned `\n` into a literal
backslash-n and "no match" scrolled past above a green line). **A
control that did not modify anything is not a passing control.**

**5. A FIXTURE THAT DOES NOT REPRODUCE PRODUCTION'S SHAPE IS NOT A TEST
OF PRODUCTION.** A probe passed its pre-ship run against a list and died
in the field against a dict.

**6. MISSING IS NOT ZERO.** A rest day is not an 0-for. An unmeasured
distance is not 0 feet. An ungradeable night is not a night of misses.
This rule has been relearned in the xHR path, the game logs, the
distance columns and the research grader.

**7. NEVER RUN `git clean` IN THIS REPO.** `-X` removes ignored files,
and `-e` makes a path MORE ignored, not less — it deleted `app/data/`
and `auth_config.yaml` while claiming to protect them. The
`find … __pycache__ … -exec rm -rf` line does the whole job and cannot
touch anything else.

**8. CLEAR `__pycache__` BEFORE BELIEVING A SURPRISING TEST FAILURE.**
Stale bytecode has produced a phantom red more than once.

**9. A RIGHT NUMBER UNDER A WRONG LABEL IS THE ONE ERROR NOBODY
DOWNSTREAM CAN CATCH.** The board capped per TEAM while its caption said
"per game, not per team". Labels get generated from the constant now.

**10. DO NOT TUNE AFTER A BAD NIGHT.** At a 12% base rate a bad week and
a broken model are indistinguishable, and every change resets the
measurement clock.

---

## PICK UP HERE — arsenal freshness, cross-board tokens, morning wind. 2026-08-16

**Suite 105, FAILING: none.** Everything below shipped with negative
controls confirmed red.

### 1. THE ARSENAL WAS STALE, AND IN THREE PLACES AT ONCE

`get_weak_spots` read usage and damage off the SAME window, which forces
a bad trade either way:

  season only -> damage well-sampled, USAGE STALE. A pitcher who
                 scrapped his curve in June still showed 16% curveballs.
  recent only -> usage current, DAMAGE COLLAPSES. The floor is 150
                 pitches / 35 batted balls per pitch type and thirty
                 days does not clear it for anything but a fastball.

**Fixed by giving them different windows: rank by 30-day usage, rate on
season damage.** Usage is a proportion and settles in ~450 pitches;
damage is a rate over batted balls and needs the year. Both are
published per pitch (`usage`, `usage_recent`, `usage_drift`) because THE
GAP IS THE SIGNAL — 7% on the season and 18% over the last month is a
pitcher who changed something, shown as `+11 pts` on the chart.

**Top 3 are marked, never truncated.** A fourth pitch thrown 9% still
leaves the yard, and a pitch a pitcher has just ADDED appears at the
bottom of that list before it appears anywhere else on the site.

**THE PART I GOT WRONG FIRST.** I fixed the weak-spot quadrant and
called it done. There are THREE arsenal displays on the Game Card — the
quadrant, "Both Starters — Arsenal Comparison", and the usage pills —
and the other two still read season usage, so one card could say 13%
sweeper in one panel and 17% in another. Now `Pitch Arsenal` in
statcast_engine is the single 30-day source all three read, with
`Pitch Arsenal Season` kept alongside for the drift number.
`ARSENAL_USAGE_DAYS` and `USAGE_DAYS` are both 30 and a test fails if
they drift apart.

Guarded by `tests/test_arsenal_freshness`.

Layout fixes in the same batch: labels no longer collide (they flip
below the bubble when the slot above is taken), the caption wraps to two
lines instead of running off the viewBox, and edge labels anchor inward.

### 2. CROSS-BOARD TOKENS — and the outage they caused

New `Boards` column on the lineup table: `HR13 · H4` means 13th on HR
Edge, 4th on Daily 13. Blank when a bat is on no board, which is most of
them — blank rather than a dash, because a column of dashes reads as
missing data instead of a clean no.

**THIS TOOK THE GAME CARD DOWN ON ITS FIRST DEPLOY.** The first version
called `get_hr_edge_board()` and `get_daily_13()` directly, on my claim
that both were "already built and cached for the slate". That is only
true if the reader visited those pages first. Landing on a Game Card
cold, it rebuilt the entire HR Edge board — ~270 rated bats — and
scanned the league for Daily 13 before a single row could draw. Both
boards cache with `show_spinner=False`, so the page just sat blank: no
error, no spinner, nothing.

**`board_ranks(allow_build=False)` is now the default** and reads today's
published picks out of `calibration.json` — one file read, ~27ms, and
the SAME list the site published so a token can never disagree with the
board it names. Live building is behind `allow_build=True`.

Cost of the cheap path: ranks 1-5 per board rather than up to 25. If
deeper ranks are wanted, the honest fix is having the nightly write a
fuller index — NOT rebuilding during a render.

Guarded by `tests/test_board_ranks` — it asserts the default cannot
build, that every build sits behind the guard, and that "today" resolves
in Eastern (without that, after 8pm ET it reads tomorrow's empty entry
and every token silently vanishes).

**Generalise this:** a convenience column must never be able to build
anything. Anything decorating a page has to read, not compute.

### 3. WIND ARROWS NOW WORK IN THE MORNING

MLB does not publish `gameData.weather` until close to first pitch, so a
card opened at 8am had only an NWS compass forecast. Two failures:

- **The grade ignored it.** `_hr_weather` was handed `g["weather_wind"]`
  — MLB only — while `_wind_raw` (computed four lines above WITH the
  forecast fallback) went unused. Temperature fell back correctly, wind
  did not, so a morning card showed a real temperature beside "wind
  pending official".
- **The arrow pointed at real-world north.** A compass forecast drew a
  rose at its true bearing: correct, and useless for knowing whether a
  ball carries.

Both were already solvable. `wind_engine` carries the home-plate-to-
centre-field bearing for 29 parks and **was already resolving these same
forecasts to score them elsewhere on the site** — the Weather Board
called a wind "pending" while HR Edge had scored it. New
`wind_engine.field_angle()` returns the resolved field direction so the
arrow points the way the grade is reasoning.

    SW 12 mph -> Wrigley    0 deg   straight out
    SW 12 mph -> Comerica -112 deg  crosswind
    NE 12 mph -> Wrigley  +180 deg  straight in

Guarded by `tests/test_wind_forecast_arrow`.

**AND THE SAME MISS HAPPENED AGAIN, ONE FILE OVER.** The Weather Board
was fixed and the Game Card was not — its conditions strip has its own
`wind_arrow` call and was not passing the park, so the identical
forecast resolved on one page and drew a neutral swirl on the other.
That is the SECOND time in two days a fix reached one consumer and
silently missed another (the arsenal window was fixed in one of three
panels the same way).

So the guard is not "check the two places I know about":
`tests/test_wind_forecast_arrow` now walks every `.py` under `app/` and
fails on any `wind_arrow()` call without `home_team`. A call without it
cannot work in the morning, which is when the wind read matters most.

**When a fix has multiple call sites, grep for all of them before
declaring it done, and write the test against the glob rather than the
known callers.**

Resolved forecasts still render DASHED — the direction is right now, the
fact that it is a forecast has not changed. An official field-relative
string still wins when it arrives: measured beats modelled, and a test
pins that order.

### 4. CACHE SIZING — a caller count doubled and nobody resized

`get_batter_iso_vs_hand` sat at `max_entries=64`, correct when
pen_context was its only caller. The platoon term (2026-08-13) calls it
TWICE per batter, once per hand, so a full slate is ~600 lookups against
64 slots. Near-total thrash, and **every miss reads that batter's whole
parquet from disk.** Raised to 1024, same for
`get_batter_profile_windowed` (season + l15 per batter is ~600 entries
against a 384 cap).

A cache smaller than the working set does not fail — it evicts silently
and the page gets slower the longer you use it. `tests/test_cache_sizing`
now checks each per-batter cache against one slate.

**RULE: when a function gains a caller, re-size its cache.**

### 5. MEASURED, THEN NOT BUILT

Asked for a tiered cap — 2nd/3rd bat on a team must be within X of the
team leader. Measured it first:

    gap <=  5 behind leader:  9.4%   |  gap >  5:  7.8%
    gap <= 20:                7.5%   |  gap > 20: 12.5%

**No signal, and the direction flips with the threshold.** Building it
would have meant picking a number that looked principled and was not.
Not built. (8 homers across 96 teammate bats — nowhere near enough
either way.)

### 6. BENCHMARK — the Results page baseline is too easy

`benchmark_probe.py` (new, reads the research log, no nightly step).

HR Edge is 19/89 = 21.3% against the published 11.9% baseline, p=0.003.
**But 11.9% is every league starter including slap hitters**, and the
board picks sluggers — any power-sorted list clears that bar with no
model in it. The probe runs the honest comparison: model top five vs
naive top fives (ISO, HR/FB, SLG, Brl/PA, HH%) from the same pool on the
same nights.

Currently 2/10 vs 2/10. That is ten picks and means nothing. **Re-run in
2-3 weeks** — at five a night a month is ~150 an arm.

### FILES TOUCHED, 2026-08-15 to 08-16

    app/engines/statcast_engine.py   arsenal source + cache sizing
    app/engines/pitcher_weakspots.py usage window split
    app/engines/weakspot_view.py     labels, caption, recent-usage plot
    app/engines/board_ranks.py       NEW - cross-board tokens
    app/engines/wind_engine.py       NEW field_angle()
    app/engines/weather_icons.py     forecast arrows
    app/views/GameCard.py            Boards column
    app/views/Weather_Board.py       forecast wind to grade AND arrow
    benchmark_probe.py               NEW - model vs naive lists
    tests/test_cache_sizing.py             NEW
    tests/test_arsenal_freshness.py        NEW
    tests/test_board_ranks.py              NEW
    tests/test_wind_forecast_arrow.py      NEW

Suite went 102 -> 105.

**NOT in the repo:** `SITE_CAPABILITIES.md` was written this session as a
briefing doc for a separate assistant working on the YouTube side. It
describes what the site offers and its honest limits, with no strategy in
it. Commit it if that hand-off is worth keeping; it goes stale the moment
the model changes materially.

### WHERE THE RECORD STANDS

    HR Edge   19/89  = 21.3%  vs 11.9% published baseline  (p=0.003)
    Daily 13  133/200 = 66.5% vs 62% baseline

Both are ahead. Neither is settled — and see section 6 above for why the
HR Edge baseline is the easy opponent.

### NEXT — AND THE ANSWER IS MOSTLY "NOT YET"

**Nothing is queued, and that is deliberate.** The research log records
~270 rated bats a night with season AND l15/l5 windows plus the graded
outcome. It needs another 2-3 weeks before anything is tuned. Until
then:

- `benchmark_probe.py` is the thing to run — model vs naive lists.
- Do NOT refit weights, move floors, or change the cap. At a 12% base
  rate a bad week and a broken model look identical, and every change
  resets the clock. This is standing rule 10 and it is the one most
  likely to get ignored.

**Open items, none urgent:**

- **Bullpen weak spots.** `get_weak_spots(pitcher_id)` already works on
  relievers — nothing in it is starter-specific, and the sample floors
  drop the TTO/slot sections on their own because a reliever never
  clears 60 BBE facing the order once. Needs a view that aggregates the
  pen as ONE arm, weighted by innings and split by hand.
- **Custom floor sets.** `hr_floors` already computes 9 floors and
  `evaluate()` takes any subset, so a "highlight bats meeting MY floors"
  feature is small. The trap: a self-chosen floor set is unfalsifiable —
  you pick floors that light up bats you already like. The honest
  version logs each saved set alongside the boards so it gets a hit rate
  against the baseline and can be WRONG.
- **Research page part 2.** Part 1 shipped (`build_player_game_logs`
  writes one row per player per game so a threshold moves live instead
  of being baked in). Part 2 is the view. Open decision: where saved
  filter presets live — `streamlit_authenticator` gives a username to
  key on, so it is a storage question, not a feasibility one.

---

## PICK UP HERE — column order derived from the model's weights. 2026-08-14 (3)

**2 files (1 new test). Suite 100, FAILING: none.** Four controls red.

### THE ORDER WAS AN ACCIDENT

Lineup columns rendered in whatever order `_stat_row` happened to
insert. The six volume and distance columns went in right after Form and
pushed **Brl/PA — 28% of HR Score on its own — out past ten others**, so
a reader scanning left to right met batted-ball distance before the
thing the score is mostly made of.

### THE ANSWER IS NOT TASTE

`engines/top_plays` multiplies out to a real ranking:

    Brl/PA     28%   POWER    .40 x .70
    FB95%      18%   CONVERGE .30 x .60
    EV90       12%   POWER    .40 x .30
    Clears%    12%   CONVERGE .30 x .40
    HRWindow%  11%   LAUNCH   .22 x .50
    PullAir%   11%   LAUNCH   .22 x .50

`_COL_ORDER` in GameCard puts the model's verdicts first, then the
scored inputs HEAVIEST FIRST, then outcomes, then contact quality, then
volume/distance, then the raw form deltas. Left to right is the score's
own reasoning in its own order.

**AND IT MOVES WITH THE WEIGHTS.** When the research log has enough
graded outcomes to refit them, this order follows — which is the entire
reason it is derived rather than typed. `tests/test_column_order` reads
`_W_POWER` etc. out of top_plays and asserts the on-screen order matches
what they multiply out to, so a refit that forgets the table fails a
test instead of shipping a stale layout.

Two smaller rules pinned there:

- **HR and NearHR stay adjacent.** The PAIR is the read — 3 homers
  against 12 near misses is a different hitter from 12 against 3, and
  splitting them destroys the comparison NearHR exists for.
- **A column absent from `_COL_ORDER` still renders**, at the end.
  Dropping one silently is how a stat vanishes and nobody notices for a
  month.

### CONTROL LESSON, AGAIN

C1 (reverse the scored inputs) reported GREEN on its first run because
the shell heredoc turned `\n` into a literal backslash-n and the edit
never applied — "no match" scrolled past above a green line. **A control
that did not modify anything is not a passing control.** Re-fired with a
real newline: red.

### NEXT
Nothing. The research log needs weeks. Re-run mlb_form_probe /
mlb_platoon_probe / mlb_weakspot_probe every few weeks.

---

## PICK UP HERE — six new columns, weak-spot gem wired. 2026-08-14 (2)

**7 files (1 new test). Suite 99, FAILING: none.** Four controls red.

### THE WEAK-SPOT PANEL WAS HALF-FINISHED

`slot_rows` shipped in engines/weakspot_view and **was never called**.
The "Weak spot vs this lineup" section in GameCard still built its own
list in batting order 1-9 — the roster-printout problem the function was
written to fix.

Now wired. Slots are SORTED BY LEAK, so the top rows ARE the answer
instead of nine numbers to scan, and slots below the sample floor drop
out entirely rather than rendering an empty track. The caption says the
ordering out loud and states the caveat that makes the join necessary: a
slot line partly reflects WHICH hitters have batted there, which is
exactly why it is shown against tonight's order rather than alone.

Import moved to module scope — it is used ~1,700 lines from the function
that had the local import.

### SIX NEW COLUMNS ON THE LINEUP TABLE

| column | what it answers | needs a re-pull |
|---|---|---|
| **HR** | season home runs | no |
| **NearHR** | hit hard enough AND at an angle to leave, and did not | no |
| **L5 PA/G** | how many swings he actually gets | no |
| **AvgDist / 300+ / 350+** | how FAR his contact travels | **yes** |

**NEAR HR reuses `in_window`** — the same launch window the LAUNCH axis
uses — rather than inventing a second threshold, so a near miss and a
home-run trajectory are the same shape by construction. Read against HR
as a PAIR: 1 home run against 60 near misses is a hitter the ball is not
falling for; 26 against 0 is one who has cashed everything.

**L5 PA/G is the volume column.** Every other number on that table is a
RATE, and a bat hitting ninth simply gets fewer chances than one hitting
second. Built from the per-game lines `build_player_game_logs` already
writes — factored into `_player_game_logs()` so build_hr_metrics does
not depend on another function's side effect or on ordering in main().

**`hit_distance_sc` added to ENGINE_COLS and _KEEP_COLS.** Only
populates going forward, so historical rows are NaN — and they must STAY
NaN. A 0 in a count column is indistinguishable from a hitter who
genuinely never cleared 300 feet. Control C3 makes it 0 and goes red.

### ON FORM — WHY YOURS REACHES 98 AND A COMPETITOR'S TOPS OUT NEAR 69

Not a bug, a different measurement. **A percentile is uniform by
construction**: rank 502 hitters and somebody is at 98 and somebody is
at 4, every night. Their column clusters 41-69, which is the shape of a
RATE, not a rank.

The trade, stated plainly:
- **ours always discriminates** — guaranteed spread, no night where
  everyone looks alike
- **theirs is comparable across nights** — 62% means the same in April

**The weakness in ours worth knowing:** on a night when nobody is
moving, the 98th-percentile bat may be barely above his own baseline and
still read 98%. The percentile ranks; it cannot size. That is what dEV
and dHH% are for, and why keeping them was right. Read together: 96%
with dEV +1.7 is a real move, 96% with +0.2 is a technicality.

### FIXTURE LESSONS (both cost a cycle here)

- `_mask()` rejects a scalar from a missing column, so a fixture must
  carry EVERY column the builder reads, not just the ones under test.
- **A control that cannot distinguish the two behaviours stays green.**
  C4 (L5 PA/G over all games instead of the last five) passed twice
  because every fixture game had the same PA count — last-five and
  all-games gave the identical mean. Only games of DIFFERENT sizes
  (8 PA x7 then 4 PA x5) made it fire.

### NEXT
Nothing structural. The research log needs weeks. Re-run
mlb_form_probe / mlb_platoon_probe / mlb_weakspot_probe every few weeks;
distributions drift.

---

## PICK UP HERE — weak spots redrawn, thresholds measured. 2026-08-14

**5 files (2 new). Suite 96, FAILING: none.** Six controls red.

### THE THRESHOLDS WERE FLAGGING 40% OF EVERYTHING

`mlb_weakspot_probe.py`, 5,032 buckets across 451 pitchers — every
bucket the panel actually draws:

    10th   25th   median   75th   90th
   0.394  0.453   0.523   0.598  0.675

At `XSLG_HOT = 0.550` the panel flagged **40.2%** of buckets as "hitters
do real damage here". A phrase that marks the dangerous QUARTER cannot
apply to two buckets in five: a panel where nearly half the bars are red
says nothing about WHERE a pitcher gets hurt, which is its only job.

xSLG measured ON CONTACT excludes strikeouts, so it sits far above the
per-PA figure people quote. 0.550 sat near the MIDDLE of this
distribution, not near its top.

Now the measured 75th and 25th: `XSLG_HOT = 0.598`, `XSLG_COLD = 0.453`.

**Fifth scale on this site set by eye.** Clears%, FB95%, HRWindow% and an
EV floor were the others — all measured, all wrong, three unreachable at
one end. Re-run the probe every few weeks.

### THE BARS ARE GONE — `app/engines/weakspot_view.py`

Nineteen horizontal bars, no shape. Three of the groups were the wrong
form for their data:

- **A pitch type carries TWO numbers** — usage and damage. A bar draws
  one, so usage was demoted to a subtitle where it stopped being
  comparable across pitches.
- **Up/middle/down is a strike zone** that was being drawn sideways.
- **Times through the order is a three-point trend** drawn as three
  unconnected bars, which hides the only thing it says.

Replaced by:

| panel | why |
|---|---|
| `arsenal_svg` | usage on x, damage on y, bubble area = batted balls. Position answers the question — top right is "thrown often, gets hit", the only quadrant worth acting on |
| `zone_svg` | up / middle / down stacked as an actual zone, shaded by damage |
| `tto_svg` | three passes as a connected line; the SHAPE is the finding |

Pitches under the sample floor are **named** underneath rather than
dropped — "he throws a sweeper 9% of the time and we cannot rate it" is
worth knowing, and omitting it makes the arsenal look smaller than it is.

These are SVG STRINGS, not Streamlit widgets: one markdown call instead
of ~19 nested column layouts, and the whole thing is unit-testable
without a Streamlit runtime. The old version could not be.

### THE SLOT PANEL BECAME THE GEM

The flat 1-9 slot list is gone from the weak-spots card entirely. Nine
slots in batting order is a roster printout, and the panel's own caveat
admits a slot line partly reflects WHICH hitters batted there rather
than the pitcher — close to unactionable alone.

`slot_rows()` **sorts by leak** and joins to tonight's lineup. That
ordering is the change: sorted by damage, the top rows ARE the answer
instead of something to scan for. And the join answers the caveat — the
claim is no longer "he is bad at slot 4", it is "the soft spots in this
order line up with these bats tonight", which is true whatever causes
the softness. Unmeasured slots drop out rather than rendering empty.

The "vs this lineup" section in GameCard (~line 2020) already did the
join; it now has the sorted, hitter-joined rows to draw.

### AN EXISTING TEST HAD TO CHANGE, AND WHY THAT WAS RIGHT

`test_gamecard_ui` asserted "every group uses the same row unit"
(`_ws_group(` >= 5). Correct for a bar stack: one shape, repeated, no
hand-rolled variants. Wrong now that three groups are deliberately
spatial.

The rule it was really protecting — **don't hand-roll a new visual
language inline in the view** — still holds and is what it asserts now:
the panels come from one engine module, the view contains no `<svg>` of
its own, and whatever stays a bar still goes through the one bar
renderer. Changed rather than deleted.

### ALSO

- WNBA combo tabs (Pts+Reb / Pts+Ast / Reb+Ast) lost their colour
  because `f"wnba_{label}_{side}"` put a **`+`** into the CSS selector,
  which is not a legal identifier — the browser discarded the whole rule
  block. Sanitised in `render_html_table`; two cases pin it.
- `AvgEV` and `Form` are on the HR Edge board with measured scales.
  Form reads AvgEV and HH% only, per-input bands 7.3% and 48%.
- Cap is `GAME_CAP = 3`, `CAP_UNIT = "team"` — looser than 2-per-game by
  design; both constants in one place to revert.

### NEXT
Nothing structural. The research log needs weeks. `mlb_form_probe` and
`mlb_platoon_probe` are in the repo; re-run every few weeks.

---

## PICK UP HERE — slam_engine.py was overwritten with statcast_engine.py. Restored from git. 2026-08-13 (3)

**3 files (1 new test). Suite 94, FAILING: none.** Control confirmed red
against the break.

### THE SYMPTOM

    ImportError: cannot import name 'slam_from_profile'
                 from 'engines.slam_engine'
    app/views/GameCard.py, line 38

Whole page down in production, found by a user.

### THE CAUSE — not a rename, a clobber

    commit dd9f481  Thu Aug 13 17:17:52 2026
    Update fmt.Println message from 'Hello' to 'Goodbye'
    app/engines/slam_engine.py | 1730 +++++++++++++++++++++++++++++---
    1 file changed, 1618 insertions(+), 112 deletions(-)

A 112-line engine replaced by 1,730 lines, under a commit message from
some other language's tutorial. `diff` against `statcast_engine.py`
returns ONE hunk: the seventeen-line, three-column addition dated today
(`swing_length`, `bat_score`, `post_bat_score`). Those columns belonged
in `statcast_engine._KEEP_COLS`. What was actually written was
statcast_engine's entire contents, plus the columns, into slam_engine.py.

`slam_from_profile` was not renamed and did not move. It, and
`_league_hrfb`, were deleted. Nothing in the repo documents SLAM's
formula either — `grep -i slam` across HANDOFF.md, README.md and
READING_THE_BOARDS.md returns zero lines — so there was no path to
rebuilding it from the working tree. **Only git had it.**

Two already-red tests were downstream of this one commit:
`test_league_anchors` (`slam_engine no longer reads the measured
anchor` — `_league_hrfb` gone with the file) and `test_columns` (`build
writes columns the engine discards` — the addition landed in the wrong
file, so the nightly wrote three columns statcast_engine threw away).

### THE FIX

    git show --stat dd9f481                       # confirm the clobber
    git show 95614a4:app/engines/slam_engine.py \
      | grep -n "def slam_from_profile\|def _league_hrfb"
    git checkout 95614a4 -- app/engines/slam_engine.py

`95614a4` ("Refactor slam_engine.py by removing
compute_slam_all_windows") is the last commit that touched the file
before dd9f481. Both functions verified present — `_league_hrfb` at 45,
`slam_from_profile` at 59 — BEFORE the checkout, not after.
`test_league_anchors` green immediately: both engines read the same
anchor, a measured value is used when present, neither scores against
the raw literal.

**No tourniquet shipped.** A guarded import with a stub returning `{}`
was written and held while history was checked; the restore made it
unnecessary and it was thrown away rather than committed. A permanent
stub is an empty panel that looks like measured data.

### WHAT SHIPPED BESIDE THE RESTORE

**1. `app/engines/statcast_engine.py`** — the three columns, verbatim
with their comment, in the file they were meant for. `test_columns`
green. Matters tonight: they only populate going forward.

**2. `app/views/GameCard.py`** — one line.
`tier = matchup_tier(slam) if slam is not None else None`. It previously
fed `0.0` into `matchup_tier`, which returns **"Weak"** — a fabricated
read on a bat that was never measured, sitting in the same column as
tiers that were. Two lines above, SLAM itself already renders as an em
dash in exactly that case. Matchup is derived from SLAM; a missing SLAM
now blanks both. Unrelated to the outage, found while reading the path.

**3. `tests/test_view_engine_imports.py` — NEW. The control.**
Checks via `ast` that every name in every `from engines.X import ...`
across `app/views/` exists in that engine — 183 imports today. Reads
both sides as source, so no streamlit and no data archive; runs bare.

Two neighbours existed and neither covers this case.
`test_view_imports.py` checks that every name a view CALLS is bound
somewhere in that view — it passes on this break, because the import
line was present and correctly spelled; the name it asked for is what
stopped existing. `test_probe_imports.py` guards the probes' reach into
engine internals, the cheaper direction: a broken probe is noticed by
whoever runs it, a broken view is a dead page in production.

Negative control confirmed against the clobbered tree:

    BROKEN: GameCard.py imports slam_from_profile from
            engines.slam_engine — that name does not exist

`KNOWN_TOURNIQUETS` is deliberately empty. Any `except ImportError`
fallback added to a view must be listed there, and the test fails both
ways — unlisted fallback appears, or a listed one starts resolving again
and the dead stub is still sitting in front of it.

### THE RULE THIS ADDS

**A whole-file write is a deletion of everything in that file.**
The three-column edit was correct, small, and reviewed. It went to the
wrong path and cost the SLAM engine, because writing a file replaces it
— an edit that only ADDS lines cannot do this. Prefer targeted edits;
when a full-file write is unavoidable, diff against what is on disk
first. `diff` would have shown 1,618 unexplained insertions in a
seventeen-line change, and so would `git show --stat` before the push.

**Corollary, from a near-miss the same night:** the new test was first
written as `tests/test_view_imports.py`, which already existed and does
something different. Check the directory before naming a file. Same
failure, one directory over.

---

## PICK UP HERE — Daily 13 was picking bench bats, and the grader was mislabelling starters. 2026-08-13 (2)

**4 files (1 new test). Suite 92, FAILING: none.** Four controls red.

### THE NUMBER THAT STARTED IT

    daily13   221 picks | hit 133  miss 67  dnp 16 (7.2%)
    hr_edge    79 picks | hit  18  miss 61  dnp  0 (0.0%)
    potd       17 picks | hit   8  miss  9  dnp  0 (0.0%)

One Daily 13 slot in fourteen went to someone who never appeared, while
two other boards had ZERO across 96 picks. That gap is the whole story
and it had two separate causes.

### CAUSE 1 — the fallback pool was a 26-man ROSTER

`get_confirmed_lineup` failing dropped Daily 13 to
`get_live_team_roster`, which contains every bench bat and backup
catcher. The recency cutoff is a weak filter: a backup who started twice
last week clears it.

HR Edge and Player of the Day fall back to the last STARTING LINEUP —
nine men who start. That is the entire difference in the table above.

Daily 13 now does the same, with the roster kept as a last resort for a
team with no posted lineup to fall back on at all.

### CAUSE 2 — a starter was being recorded as a DNP

**James McCann appeared ungraded on two Daily 13 days while playing —
and homering — for Arizona.** So the 7.2% is not purely bench bats;
some of it is real starters the grader could not find.

`_mlb_line` read **`stats[0]`** and ignored every other entry. A player
who changes teams mid-season can come back as more than one, so every
game after the move was invisible. Now every entry's splits are read.

And there was no way to say *"the API answered, he wasn't there."* A
timeout, a rate limit and a genuine bench night all returned None, were
held open three days, then closed `dnp` — identical permanent records
for completely different events.

Three returns now:

| return | meaning | grade() does |
|---|---|---|
| dict | he played | grade it |
| `DID_NOT_PLAY` | API answered, not in his log | close `dnp` at once |
| `None` | request failed | hold, retry |

A pick still closed after FINALIZE_AFTER_DAYS with no answer gets
`dnp_reason` and prints a warning naming the player. **A collection
failure must be visible, not filed under the same word as a bench
night.**

### WHAT WAS NOT A BUG

The three "ungraded" picks from 2026-08-12 are one day old and inside
the three-day window by design. Closing early is what poisoned whole
days before. They resolve on their own.

### WORTH SEEING

**Daily 13 is 133 of 200 resolved — 66.5% against a 62% baseline, over
200 picks.** That is the strongest evidence on the site, and it is
currently buried under a board that reads "8/13" on a day where three
picks had not resolved.

### NEXT
Research page part 2. Then the calibration bands — score to observed
rate from the research log, which is what turns a score into something
a subscriber can act on. Do not tune weights before that exists.

---

## PICK UP HERE — the record was grading the 1 PM board. 2026-08-13

**5 files (1 new test). Suite 91, FAILING: none.** Four controls red.

### THE RECORD AND THE BOARD WERE DIFFERENT LISTS

hr_edge graded FOUR picks on 2026-08-12 — Alonso, Schwarber, Harper,
Encarnacion-Strand, all miss. The user reported seeing Ohtani, Carroll
and Riley in the top 5. Both were right.

Reconstructed from the 270-row research log, the board's real ranking:

     1. Cal Raleigh     edge 100  raw 106.8
     2. Shohei Ohtani   edge 100  raw  99.7
     3. Pete Alonso     edge  99  raw  None
     4. Kyle Schwarber  edge  99  raw  None
     5. Austin Riley    edge  99  raw  98.7

**Four picks on a fifteen-game slate is two confirmed lineups at 1 PM
against a 2-per-game cap.** The record froze there and never looked
again.

### CAUSE 1 — stat=None IS A MARKET

    logged_markets = {p.get("stat") for p in existing["picks"]}
    fresh = [r for r in rows if r.get("stat") not in logged_markets]

hr_edge, daily13 and potd carry `stat=None` on every pick. After the
1 PM run `logged_markets == {None}`; at 5 and 7 PM every row was also
None, so `fresh` was empty. **Every single-market board froze at the
first run that produced anything.** The per-market rule was written for
the WNBA boards, which have five real markets, and silently froze the
MLB ones. The log said "every market already logged" — true, and
completely misleading.

Fixed: a board whose markets are all None REPLACES its picks each run.

**BUT REPLACEMENT ALONE WAS WRONG, and an existing test caught it.**
`test_calibration_picks.py` re-runs with a thinner board and asserts the
fuller one survives — retry safety is what three daily runs are FOR, and
plain replacement traded it away: a 7 PM hiccup returning two games would
overwrite a good fifteen-game record. Guard is
`len(rows) >= len(existing["picks"])`. `>=` not `>`, because an
equal-sized evening board rests on more confirmed lineups and should win
a tie.

### CAUSE 2 — the board threw away every unconfirmed game

`get_hr_edge_board(confirmed_only=True)` was the default, so before a
lineup posted the game was simply absent. The list therefore APPEARED
through the afternoon rather than refining, and reordered wholesale under
anyone reading it.

`_lineup_for` already falls back to the team's last posted lineup,
already drops anyone since placed on the IL, and already reports
`confirmed=False` upward so the weaker claim stays visible. **That good
information was being discarded to avoid labelling it.**

Now: `confirmed_only=False` by default on both `get_hr_edge_board` and
`top_hr_edge`. Every game is rated from the morning. A **Lineup** column
reads CONFIRMED or *projected* per row, and the caption reads
"N of M lineups confirmed" with the fallback explained.

`get_confirmed_lineup` already has ttl=300, so a lineup posted at 5:32 is
on the board by 5:37. "Soonest possible" needed no work.

### WHAT THIS DOES AND DOES NOT SOLVE

Solved: the board no longer materialises out of nowhere, the record no
longer grades lunchtime, and a projected row is visibly a weaker claim.

**NOT solved: a projected row can still change.** A bat rated off
yesterday's card may not be in tonight's lineup at all. The badge makes
that visible; nothing makes it stop. The user considered per-window locks
(11 AM / 5:30 PM / 8 PM for the late West Coast games, and the same shape
for WNBA) and chose this instead — one always-complete list that refines,
rather than three locked ones. Revisit if projected rows prove unstable.

### NEXT
Research page part 2 (the view; presets storage still undecided). The
per-game log table builds on the next nightly. The research grader's
data-root fix is in — expect `graded 270 bat(s) for 2026-08-12`.

---

## PICK UP HERE — the research grader was reading the wrong data root. 2026-08-13

**3 files. Suite 90, FAILING: none.** Control red.

### 270 ROWS SAT UNGRADED FOR A DAY

The nightly ran and graded calibration for 2026-08-12 normally. The
research log did not grade a single row.

**precompute writes to `build_data/data/statcast/batters/`. The grader
read `app/data/statcast/batters/`.**

    OUT_ROOT = Path("build_data")                        precompute.py:62
    BATTER_DIR = ROOT / "app" / "data" / ...       hr_research_log.py:63

`app/data/` only exists once `fetch_data.py` unpacks the published
release asset — which happens on Render and in a Codespace and **never on
the CI runner**. So the grader found zero files, every lookup returned
"cannot tell", and the coverage guard refused to close the night.

**The guard worked exactly as designed.** It stopped 270 rows being
written as DNP against games that had been played. What it could not do
was say why: inside `_homered`, "no rows for this batter" and "no file
for this batter" are the same return value, and they mean opposite
things — a pull that has not caught up versus a path that is wrong.

### FIXED

- `BATTER_DIRS` is now a tuple, build_data first (freshest at grading
  time), app/data second (Codespace and Render).
- The refusal message now reports **how many bats had NO FILE AT ALL**
  and **which roots exist**, so the two causes are distinguishable from
  the log.

### THE TEST THAT WOULD HAVE CAUGHT IT — and why the other nine could not

Every existing case monkeypatches `BATTER_DIRS` to a temp directory. **A
fixture cannot test a constant it replaces.** Flipping the module back to
the broken single path left all nine green.

Case 10 compares the two modules' own literals: it reads `OUT_ROOT` and
`DATA_DIR` out of precompute's SOURCE and asserts one of the grader's
roots resolves to `<that>/batters`. Reads the source rather than
importing precompute, because precompute pulls in engines.hr_floors and
needs app/ on sys.path plus a streamlit shim — dragging an import graph
in to compare two string literals is how a test starts failing for
reasons unrelated to what it checks.

**Generalise this.** Any two modules agreeing on a filesystem path by
convention have this exposure, and no amount of behavioural testing finds
it. The metrics reader pointing at the wrong directory for weeks was the
same defect class.

### WHAT TO EXPECT ON THE NEXT NIGHTLY

`hr_research: graded 270 bat(s) for 2026-08-12` — the backlog clears in
one run, because grade() walks every ungraded date, not just yesterday.

### YESTERDAY'S RECORD, for the avoidance of doubt

hr_edge 2026-08-12: **0 for 4**, all four graded `miss` (Alonso,
Schwarber, Harper, Encarnacion-Strand). Four picks, not five — the
2-per-game cap on a thin slate, as designed.

Last four nights: 1/5, 1/5, 2/5, 0/4 = **4 of 19, ~21% against a 12%
baseline.** Ahead of the league rate, and nineteen picks.

---

## PICK UP HERE — every HTML table on the site shared one CSS selector. 2026-08-12 (late)

**3 files (1 new test). Suite 90, FAILING: none.** Three controls red.

### IT WAS NEVER THE COLOURS

Reported as "the WNBA FG%/3P% columns grade backwards": 56.7 FG% rendered
poor, 30.0 rendered elite, in a table captioned "higher is better".

**They were not inverted.** An inversion is still ordered, and this was
not — 0.0 rendered good on one team while 33.1 rendered elite on another.
No value-based theory fits, and three were killed by measurement before
the real one turned up:

1. Fractions vs percentages — dead. `fg_pct` runs 0.0-100.0 consistently.
2. Values arriving as strings — real (every stat column is `object`
   dtype by design, so numbers sit flush under left-aligned headers) but
   NOT the cause: `to_numeric` parses them, and the debug panel showed
   `FG%: min=30.0 max=56.7 nulls=0/14`.
3. The grader itself — dead, and decisively. Fed the exact 14-row Sky
   frame, the Styler returns ELITE for 56.7 and POOR for 30.0. Correct
   at both ends.

### THE ACTUAL CAUSE

pandas builds Styler selectors from `table_uuid`:

    #T_{uuid}_row0_col10 { background-image: ... }

`render_html_table` used `f"lc{key}"`, and **key defaults to `""`**. Of
24 call sites only 9 pass a key at all. Every keyless table emitted CSS
under `#T_lc_row*_col*` — identical selectors, equal specificity, so in
one DOM **the last table rendered wins for all of them.**

The WNBA team table is the worst case: it renders inside two nested
loops (once per prop tab, once per side) under a single hardcoded
`key="wnba_636"`, so a three-game slate painted dozens of grids all
claiming the same selectors. Every team's table wore the colours
computed for whichever rendered last. **GameCard has nine keyless tables
on one page** with the same collision.

That explains what nothing else could: FG% and 3P% matching each OTHER
within a row (both taking col10/col11 from a different table where those
landed in one tier), and MIN looking right most of the time (after the
same sort, minutes correlate by row position across teams, so the wrong
colours land plausibly).

**Every colour in every one of these tables has been wrong** — just
invisible in columns where teams happen to look alike.

### THE FIX

`uid = f"lc{key}_{next(_TABLE_SEQ)}"` — a module-level `itertools.count`.

**`key` is now a readable LABEL, not the uniqueness mechanism.** A
counter guarantees distinct selectors even when two callers pass the same
key or none. Uniqueness must not depend on every future caller
remembering to invent a name; this bug is the proof nobody sustains that.
The key survives in the uuid so devtools shows
`lcwnba_Points_away_7` rather than `lc_7`, and the WNBA call site now
passes `f"wnba_{label}_{side}"`.

No other call site needs touching — the counter covers them all.

### THE DIAGNOSTIC THAT FOUND IT

A temporary expander rendered ON THE PAGE (not to logs) printing
`df.columns`, dtype, nulls, min/max and samples. Removed in this commit.
Worth repeating as a technique: reading Render logs from a tablet is
worse than looking at the table already open, and it took one tap to
produce the `FG%: min=30.0 max=56.7` line that killed hypothesis 2.

### NEXT
Unchanged. Research page part 2 (the view, plus deciding where saved
filter presets live), then WNBA. The per-game log table builds on the
next nightly. Tomorrow's checkpoint is still
`hr_research: graded N bat(s) for 2026-08-12`.

---

## PICK UP HERE — dead code cleared, and what is deliberately NOT fixed. 2026-08-12 (close)

**5 files. Suite 88, FAILING: none.**

### DELETED, promised at the start of the day and not delivered until now

- `calibration.implied_pct()` — zero references anywhere including
  tests. It converted American odds to an implied percentage; nothing in
  this app has ever had a price to convert.
- `slate_guard.today_et()` — zero references, superseded by
  `today_for(league)`.

**Deleting `today_et` ORPHANED `EASTERN`,** which was its only consumer
and then sat defined-and-unused with a comment still pointing at it.
That is the shape this kind of cleanup usually takes: removing a
function leaves its constants behind, and the second pass is the one
people skip. `EASTERN` is gone too, and the comment that referenced it
now says which module actually holds one — slate_guard holds no timezone
of its own, every zone comes from the league table, so a league's
timezone is stated in exactly one place instead of two that can
disagree.

Also trimmed: `import json` in kbo_probables_probe, `timedelta` in
kbo_fragment_probe. The remaining `from __future__ import annotations`
hits in the scan are false positives.

### NOT FIXED, ON PURPOSE — read before "finishing" these

**1. The WNBA form band.** It saturates: 75th percentile of 3PM form is
94.9, the 90th is exactly 100. The defect is real and measured. The FIX
is not, because it requires choosing a new band, and the raw deviation
distribution needed to choose one honestly has not been printed yet —
`wnba_props_probe.py` now reports it (with the 10th percentile, so both
edges of a band are visible) but has not been re-run since.

Picking a nicer-looking number here is precisely what produced three
broken colour scales earlier today. **Run the probe, read the raw dev %
rows, then set the band per stat** — and consider whether a stat whose
typical line is 1.0 should use a percentage band at all.

**2. Consistency cannot reach 100 and form can.** Consistency tops out
near 70 league-wide. So the effective weight of form at the top of the
range exceeds its nominal 25%. Fixing this means rescaling a component,
which changes every WNBA score, and it should be done together with (1)
rather than twice.

**3. `hr_intent_pct` and `hr_threat_pct` are published and read by
nothing.** Verified this time: no dynamic `_pct` access exists in any
view. They are still LEFT IN — deleting parquet columns has downstream
reach this repo cannot see from a grep, and they cost almost nothing.
Decide deliberately, not as cleanup.

**4. The 103 `hr_research` rows logged before the afternoon fix** lack
`game_pk`, `edge_raw`, `AvgEV` and `floors_met`. Nothing to backfill:
the board state and the thresholds that produced them are gone. They
remain valid for score-versus-outcome.

### THE STATE TO COME BACK TO

Nothing is queued. `hr_research_log` runs at 1, 5 and 7 PM and grades
each morning after the nightly. The next real step is **three to four
weeks of graded bat-nights**, then refit the HR axis weights and re-set
the nine floors against outcomes instead of choosing them.

Everything decided today was decided by measurement, and the two things
above are unfinished for exactly that reason — there is no measurement
for them yet.

---

## PICK UP HERE — WNBA measured, and the props form component saturates. 2026-08-12 (final)

**3 files. Suite 88, FAILING: none.**

### THE WNBA BAR, MEASURED (123 qualified players of 308)

| stat | CONSISTENCY median | 75th | 90th | **league max** |
|---|---|---|---|---|
| Points | 33.3 | 41.8 | 50.3 | 63.6 |
| Rebounds | 28.5 | 38.2 | 50.3 | 70.9 |
| Assists | 27.3 | 36.4 | 48.8 | 62.4 |
| PRA | 40.6 | 50.3 | 57.3 | 69.7 |
| 3PM | 18.2 | 29.6 | 43.8 | 68.5 |

Written into READING_THE_BOARDS. **A consistency score of 50 is a strong
reading, not a mediocre one** — nobody in the league exceeds ~71 and the
medians sit in the twenties and thirties. The bar differs per stat: 45
is top-decile on 3PM and ordinary on PRA.

### TWO PROBLEMS THE FIRST RUN EXPOSED. NEITHER IS FIXED, ON PURPOSE.

**1. FORM SATURATES ON LOW-COUNT STATS.** `form` scales
`(l10 - season) / season * 100` across a +/-25% band. For 3PM, where a
typical line is 1.0, going 1.0 -> 1.4 is +40% and clamps to 100.
Measured: the 75th percentile of 3PM form is **94.9** and the 90th is
**exactly 100**. A quarter of the league pinned at the ceiling of a
component means that component has stopped separating anyone.

This is the Clears% defect in a new place: a fixed band chosen by
eye, applied to a quantity whose real spread nobody measured.

**2. CONSISTENCY CANNOT REACH 100 AND FORM CAN.** Consistency tops out
near 70 league-wide; form regularly hits 100. So although the board
weights consistency 35% and form 25%, **at the top of the range form has
more room to move a score than consistency does.** Nominal weights and
effective weights are not the same thing, and the docstring describes
the nominal ones.

**Why nothing was changed:** picking a nicer-looking band is exactly
what produced three broken colour scales earlier today. The probe now
also reports the RAW deviation percentages (and the 10th percentile, so
both edges of a band are visible — a median/75th/90th table only shows
one). Set the band from that distribution, per stat, and consider
whether a stat with a typical line of 1.0 should use a percentage band
at all.

**The prediction I got wrong, recorded because it is the useful part:**
I told the user form would sit near 50 by construction, since it
measures a player against her own baseline. Measured medians run 50 to
58 with a saturating upper tail. The reasoning was sound and the number
was not — which is the argument for the probe existing.

### STATE OF PLAY

Nothing structural is queued. `hr_research_log` runs nightly; the honest
next step is three to four weeks of graded bat-nights, then refit the HR
axis weights and re-set the floors against outcomes rather than
choosing them. The WNBA form band wants the same treatment: measure,
then set.

READING_THE_BOARDS.md is complete — every "measure this yourself" in it
is now a real number.

---

## PICK UP HERE — probe crash fixed, Daily 13 docstring. 2026-08-12 (last)

**3 files. Suite 88, FAILING: none.** Control confirmed red.

### THE PROBE CRASHED ON ITS FIRST REAL RUN

```
if (p.get("gp") or 0) < MIN_GP:
AttributeError: 'str' object has no attribute 'get'
```

**`players.json` is keyed BY PLAYER ID, not a list.** Iterating it yields
the id strings. `league_percentiles()` in `engines/wnba_props.py` does
exactly this unwrap — `if isinstance(players, dict): players =
list(players.values())` — three lines from where it reads the same file,
and the probe was written without copying it.

The lesson is not "remember the unwrap." It is that **the shape of a
payload belongs in one place**, and a probe reading a file the engine
already reads should look at how the engine reads it. Rule 21 in a form
it had not taken here before: not duplicated LOGIC, duplicated
ASSUMPTIONS about a file.

Fixed, then verified against a synthetic 308-player fixture built with
the dict-keyed shape that crashed it — the previous fixture used a list,
which is why the probe passed its pre-ship run and failed in the field.
**A fixture that does not reproduce production's shape is not a test of
production.**

`test_probe_imports.py` now asserts BOTH readers unwrap it: if the
engine ever stops, the probe's copy is the only one left and it rots
silently.

### Daily 13 docstring

Said the floor was 60% of games with a hit; `MIN_HIT_RATE` is 50.0. The
page body renders the real constant, so nothing on screen contradicted
the wrong text — the worst version, because the next reader goes looking
for a floor that does not exist.

**Now it names the constants and states no number.** A threshold copied
into prose has no way to stay true. (The first pass at this fix restated
"currently 50%" one line after saying the number was not repeated —
caught by the check, not by reading it back.)

### STILL OUTSTANDING
`wnba_props_probe.py` has still not produced real output. Run it after
this lands; the WNBA section of READING_THE_BOARDS is the last place in
the guide that tells the reader to measure something themselves.

---

## PICK UP HERE — the other two colour scales were broken too. 2026-08-12 (night)

**4 files. Suite 88, FAILING: none.** Control confirmed red.

### MEASURED, AND BOTH WERE WRONG

`FB95%` and `HRWindow%` were flagged as suspect in the previous entry
and deliberately left alone until measured. Measured now, 373 hitters at
150+ PA:

| stat | median | 65th | 75th | 90th | **MAX** | old scale |
|---|---|---|---|---|---|---|
| FB95 % | 11.49 | 13.45 | 15.07 | 18.66 | **30.89** | (15, 25, 35, 45) |
| HRWindow % | 25.10 | 26.62 | 27.74 | 30.14 | **41.94** | (15, 25, 35, 45) |

**FB95% was the worse of the two.** The top two tiers were unreachable —
nobody in the league hit 35 — and the 90th percentile did not clear the
SECOND cut. Three quarters of hitters sat in the bottom tier.

**HRWindow% was broken only at the top**, which is why it survived
longer: the league maximum fell short of the fourth cut, so the elite
tier could never be earned, and the 90th percentile did not reach the
third. The bottom half of that scale worked fine. **A scale can be half
right and still tell the reader nothing where it matters.**

Both are now median / 65th / 75th / 90th, the same shape as the Clears%
fix. HRWindow%'s cut points are deliberately close together (std 4.19) —
small differences flip tiers because that is what the league actually
looks like. A wider, prettier scale would just be the old bug again.

**THREE SCALES, ONE DEFECT, and the pattern is worth naming.** All three
were round numbers spanning 15-45 (or 10-40) for a per-batted-ball rate.
None was caught by looking at the site — a uniformly-coloured column
looks graded. All three were caught by measuring. **Assume any scale not
in `_LEAGUE_MAX` in test_number_formats.py is unverified.**

The guard now covers six stats and asserts both directions: the bottom
cut must be beatable and the top cut must be reachable.

### STILL OUTSTANDING
`wnba_props_probe.py` has not been run — the WNBA section of
READING_THE_BOARDS still tells the reader to measure it themselves.
That is the last "measure this" left in the guide.

Also unresolved: `app/views/Daily_13.py`'s module docstring says the
floor is 60% of games with a hit. `daily_13.MIN_HIT_RATE` is 50.0. The
page body renders the real constant, so only the docstring lies — but it
will send someone hunting for a floor that does not exist.

---
