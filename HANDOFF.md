# Los Cappers — session handoff

Read RULES before proposing any change; every one was learned by
breaking something.

**Rewritten 2026-08-06. An earlier version of this file was itself
corrupt — a dead copy of item V dangled under the pitcher-H2H section,
describing as broken something the section twenty lines above described
as fixed. Verify before you build. START WITH "PICK UP HERE".**

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

## PICK UP HERE — the WNBA had no measured bar. 2026-08-12 (late)

**3 files (2 new). Suite 88, FAILING: none.** Two controls red.

### `wnba_props_probe.py` — one-shot

`hr_floors_probe` gave MLB batters a league context, so "Brl/PA 8.79"
reads as top decile instead of as a bare number. The WNBA board had no
equivalent, so a 71 consistency score could only be read against
tonight's other names and meant nothing on its own.

This prints median / 75th / 90th for CONSISTENCY (and its clear-rate and
floor-rate halves) and FORM, per stat, across every player clearing the
board's own floors.

**IT MEASURES 60% OF THE SCORE AND SAYS SO.** Consistency (35%) and form
(25%) are properties of the PLAYER, readable from the season log.
Matchup (25%) and pace (15%) are properties of TONIGHT and need a slate.
A probe that quietly reported a partial score as the whole thing is
exactly the kind of number this repo keeps having to unwind.

**Availability is deliberately NOT applied.** The board excludes players
who have not appeared recently and should. But this measures what the
LEAGUE looks like, not who is playable tonight, and dropping every
injured player would bias the distribution toward whoever is healthy
this week.

No formula is reimplemented — `_line_for`, `_clear_rate`, `_floor_rate`
and `_scale` are imported from the engine. Same reason `hr_floors_probe`
stopped carrying its own copy of the thresholds: a probe that computes
its own clear-rate measures a stat the board does not have.

Verified against a synthetic 120-player league before shipping (rule
22), not first-executed in production.

### `tests/test_probe_imports.py` — new

The probes import PRIVATE engine helpers by name. That is the right
design and its cost is that **a rename breaks a probe silently**:
nothing imports these files, no page renders them, and the break only
surfaces weeks later when someone runs one by hand.

This asserts the names still resolve, and that the props weights still
sum to 1.0 with the player-intrinsic share at 60% — because the probe
prints that fraction to the reader and would misstate it if the weights
moved. It does not run the probes; they need an archive not in the repo.

**A stale `app/engines/__pycache__` held a control edit alive through a
`cp` restore during this work** and produced a phantom failure in the
suite. `find app -name __pycache__ -exec rm -rf {} +` before believing a
surprising red.

### `READING_THE_BOARDS.md` — new this session

Full reading guide for every board: what each one answers, what the
columns mean, the measured MLB thresholds, and a workflow. Section 0 is
the one that matters — the league baselines (a hit is a 62% event, a
homer 12%), and what beating them actually looks like.

**Section 7 opens with the structural gap: there are no odds anywhere in
this app.** Every board rates the quality of a spot; none knows the
price being offered. "Good enough to bet" is unanswerable from this site
alone, and every threshold in that section is written as "strong
reading", never as "profitable".

Candidate for the Glossary expander later.

### NEXT
Unchanged: three or four weeks of graded bat-nights, then refit the axis
weights and re-set the floors against outcomes. Before touching FB95%
or HRWindow% in stat_scales, measure them.

---

## PICK UP HERE — an unreachable colour scale, and four fields the research log was dropping. 2026-08-12 (evening)

**4 files. Suite 87, FAILING: none.** Five controls confirmed red.

### THE BOARD WAS CALLING ITS BEST CLEARS% HITTER BAD AT IT

`stat_scales.SCALES["Clears%"]` was `(10.0, 20.0, 30.0, 40.0)`.

**Clears Anywhere is a rate in TENTHS of a percent.** The nightly
measures the league mean at 0.32%; across 373 hitters at 150+ PA the
median is 0.00, the 75th is 0.63, the 90th is 0.93. **Nobody in baseball
reaches the first cut point**, so every cell in that column rendered in
the bottom tier — a bat at 1.01, above the 90th percentile of the whole
league, in the same red as one at 0.13.

`_magnitude_column`'s own docstring says a colour reads as a verdict.
This one delivered the same verdict to everybody, which is worse than no
colour: the column looked graded and was not.

Now `(0.15, 0.40, 0.65, 0.95)` — median, ~65th, 75th, 90th, from the
measured distribution. The first cut sits just above zero on purpose:
over half of qualified hitters have never once put a ball on a
trajectory that leaves every park, so "has done it at all" genuinely is
what separates the bottom tier here.

**TWO NEIGHBOURS ARE SUSPECT AND WERE DELIBERATELY NOT TOUCHED.**
`FB95%` and `HRWindow%` are both `(15, 25, 35, 45)` — round numbers
spanning the same range, written in the same style, neither checked
against a real distribution. The HR-window league mean is 25.1%, so that
scale's median lands on its second cut and the top tier may be close to
unreachable; FB95% is unmeasured entirely. **Replacing one guess with
another is what produced the bug above**, so there is a one-line
measurement command in the comment beside them. Run it before changing
either.

The guard added to `test_number_formats.py` is "the top tier must be
reachable and the bottom cut must be beatable", checked against the
2026-08-12 league maxima for four stats — not a pin on the exact
numbers. Re-tuning a scale stays free; re-typing a tens-of-percent scale
onto a tenths-of-a-percent stat does not.

### THE RESEARCH LOG WAS DROPPING FOUR FIELDS

`data/hr_research/2026-08.ndjson` logged 103 rows on 2026-08-12 without
them. All four are things that came into existence AFTER the logger was
written, and `PROFILE_KEYS` / `EDGE_KEYS` were never revisited.

| field | what its absence costs |
|---|---|
| `game_pk` | **the worst one.** Every row read as its own game, so the log could never measure same-game correlation or evaluate the 2-per-game cap — the exact question the cap was built to answer |
| `edge_raw` | only the clamped integer was stored, so every bat that pinned at 100 is the same number and the board's real order is unrecoverable. The clamp erasing separation is what `edge_raw` was ADDED to fix; storing only `edge` put the bug back inside the measurement |
| `AvgEV` | the floor set names it, so the qualification tier was not reconstructable from a stored row — which is most of why the nine metrics are captured |
| `floors_met` | derivable in principle, but only against the thresholds IN FORCE THAT NIGHT, and those are measured nightly and move. Storing the count records what the board said, not what today's thresholds would say about a bat from three weeks ago |

**The 103 rows already on disk keep their gaps.** They are still valid
for score-vs-outcome; they cannot answer the cap or tier questions.
Nothing to backfill — the thresholds and the board state that produced
them are gone.

### ALSO IN FROM THE OTHER ACCOUNT (not my work, recorded here so the
### next session does not rediscover it)

`Styler.format()` REPLACES the display function for every column rather
than merging with the earlier `.format(precision=2, na_rep="—")` in
`_base_styler`. Any view adding its own format call silently stripped
precision and na_rep from every column it did not name — unlisted
numeric columns fell to pandas' default of SIX decimals, and missing
values printed the literal `nan` instead of the em dash.

**The `PA` column added in the previous batch shipped rendering as
`543.000000` on the live board.** Same root cause already recorded in
`Strikeout_Board.py` as `10.370000` — one defect, patched twice at the
symptom, never at the source. Fixed at the source now
(`styler.format.precision` set to 2 as a floor), plus explicit formats
across six views and `test_number_formats.py`.

### VERIFY

1. Suite: **87 files, FAILING: none.**
2. Open HR Edge. **Clears% should now show a range of colours** — the
   0.13s at the bottom, the 0.9+ at the top. If it is still uniformly
   red, Render has not redeployed.
3. After tonight's 5 PM and 7 PM pick runs, a fresh row should carry all
   four fields:
   `python -c "import json;r=[json.loads(l) for l in open('data/hr_research/2026-08.ndjson')][-1];print({k:r.get(k) for k in ('game_pk','edge_raw','AvgEV','floors_met')})"`
   Any `None` there means the board stopped supplying that key, not that
   the logger stopped asking.
4. `data/hr_research/2026-08.ndjson` should be well past 103 rows for
   2026-08-12 once lineups are posted. If it stalls near 100, something
   is gating the board harder than lineup availability.

### NEXT
Nothing structural. Three or four weeks of graded bat-nights, then refit
the axis weights and re-set the floors against outcomes instead of
choosing them. Before touching FB95% or HRWindow%, measure them.

---

## PICK UP HERE — floors as a tier, and the board's ordering fixed. 2026-08-12

**8 files (1 new engine, 1 new test). Suite 86, FAILING: none.**
Nine controls confirmed red.

### THE PROBE RESULT THAT DECIDED THIS

`hr_floors_probe.py` against 373 hitters at 150+ PA:

- **21 clear all nine floors. 33 more miss by exactly one.**
  About a third of qualifying hitters are in any night's confirmed
  lineups, so a hard AND gate leaves roughly SEVEN bats. **A top-15
  board cannot be built from that.** Tier, not filter.
- **Brl% did 89% of all the cutting** (373 -> 87). The remaining eight
  floors removed 66 between them. Nine conditions behaving like one,
  because they are all power proxies of each other.
- The only two still earning their place at the end were ISO (-8) and
  ClearsAnywhere (-7). ClearsAnywhere is the one floor in the set that
  is not a power proxy, and its median is 0.00 — over half of qualified
  hitters have never once put a ball on a trajectory that leaves every
  park.

**THREE OF THE NINE WERE NOT DOING WHAT THEY WERE MEANT TO.**

| floor | what happened |
|---|---|
| EV 91 | cleared **373 of 373** and removed nothing |
| HH% 40 | the league median to two decimals (39.95); removed **one** more bat after the barrel floors |
| PullAir% 10 | below the median too (11.89) |

The EV one is the instructive failure. It was meant as a floor on
AVERAGE exit velocity, where 91 sits above a league average near 89. The
only EV column was `EV90` — the 90th PERCENTILE of a hitter's batted
balls, median **104.2**. Right number, wrong stat, and it looked strict
the whole time. `AvgEV` now exists in the profile so 91 means what it
was meant to mean.

### `app/engines/hr_floors.py` — ONE definition, as percentiles

Imported by the board, the probe and the research log. Three copies of
nine numbers is nine chances to disagree, and this repo has already paid
for that with anchors typed separately into precompute and
statcast_engine.

**Stored as the PERCENTILE each floor was reaching for, resolved nightly
against the scale core** — the same pattern `hr_anchors` already uses. A
literal is a photograph of one season: set at the 75th in 2026 and left
alone it is the median by 2028, and nothing about a hardcoded 40
announces that the league moved. Brl/PA 8.0 was already the 90th and ISO
.200 the ~78th, so those barely move; HH%, FB%, PullAir% and the EV
floor snap up to the 75th, which is where "firm" was meant to be.

The literals in `FLOOR_SPECS` are a FALLBACK for an archive published
before this shipped — they are the values MEASURED on 2026-08-12, not
the values as originally typed.

`ClearsAnywhere` is deliberately NOT a percentile: its median is 0.00,
so a percentile floor would resolve to zero and pass everybody. "Has
done it at all" is the real threshold.

**Unmeasured fails its floor and is named in `missed`.** A bat with no
bat-tracking data has not cleared the Blast floor — and the DENOMINATOR
does not move, because a 9/9 that quietly became 8/8 would be one number
meaning two different things.

`_FLOOR_COLUMNS` in precompute is **deliberately partial**: HH%, FB%,
Blast%, ISO and AvgEV live in the per-player profile and have no column
in hr_metrics, so those keep the fallback until they do. A mapping that
guessed at a column name would publish a floor built from the wrong
stat — which is precisely what the EV90 mix-up already cost once.

### THE BOARD'S ORDERING WAS PARTLY THE SCHEDULE

`rows.sort(key=r["edge"])` — an INTEGER clamped to 0-100, ~270 bats
sharing 101 possible values, on a stable sort. **Ties resolved by the
order the build loop produced rows in: game order, away before home,
lineup order.** Rule 25 in a new place.

And **teammates tie far more often than strangers**, because they share
`ctx_adj` EXACTLY — same park, temperature, wind, opposing arsenal. Tied
teammates land adjacent. That is a real contributor to one lineup
appearing to take over the top of the board, and it is a separate cause
from the one the cap addresses.

The clamp compounds it: adjustments span **+/-67** (bvp 15, zone 15, pen
10, park 10, temp 4, pitch 8, slot 5), so a strong bat in a strong spot
pins at 100 beside one several points behind it — separation erased
exactly where the reader looks.

Now sorted on `edge_raw` (unrounded, unclamped, carried from
`edge_components` for SORTING ONLY — the displayed number stays the
bounded integer), with the tiebreak **said out loud**: HR Score, then HR
Threat. When the matchup layer cannot separate two bats, the better
hitter goes first. That is a choice and it belongs in the code as one.

### THE FIDELITY PROMISE, MADE TRUE

The docstring said a bat's edge here equals its edge on the Game Card.
Two differences had accumulated under it:

- **`batting_order` was never passed.** The slot term is worth up to
  five points, it was on the card and absent here, and THIS is the board
  that gets logged. Fixed — and only on a CONFIRMED lineup, because
  yesterday's order is a guess about tonight that would price a slot the
  hitter may not be in.
- **`batter_vs_pitch` is omitted**, deliberately, for cost. Now stated
  in the docstring instead of contradicted by it.

### `cap_per_game` — 2 per game

**Per GAME, not per team.** Park, temperature, wind and the opposing
arsenal apply to BOTH sides, so a team cap of two still lets one
hitter-park matinee put four bats in a top fifteen. The game is the unit
the correlation travels on.

- Order preserved. It filters an already-ranked list; it never re-ranks.
- **The overflow is returned, not discarded** — a capped-out bat has to
  stay reachable under the board with the rule named. Silently dropping
  a hitter from a list people bet off is worse than the stacking.
- A row with no game key is never capped away: unknown fails OPEN, so it
  can only ever show MORE bats. That is only safe if the key is really
  there, so a test asserts the board carries `game_pk` — from the
  outside, a cap doing nothing looks identical to a cap that works.
- **Applied to the logged top 5 as well.** The record's job is to
  measure what the site told you to play. It is a selection-rule change,
  not a metric change: what is graded (did the bat homer) and the
  baseline (share of league starters with a home run) are unchanged,
  exactly as when HRThreat and Clears% entered the scoring.
- **On a thin slate the list comes back SHORT.** Two confirmed games at
  5 PM means four picks, not five. The cap is absolute on purpose: a
  rule that stops applying when it is inconvenient cannot be read off
  the page.

### VERIFY

1. Suite: **86 files, FAILING: none.**
2. Next nightly log should carry a new line:
   `HR floors (measured): brl_pa 9.xx · brl_pct 10.xx · pull_air 15.xx`.
   Only three keys — the rest have no column in hr_metrics yet and keep
   their fallback, which is expected, not a failure.
3. Re-run `python hr_floors_probe.py`. It now reads the shared floors,
   so the numbers will differ from the 2026-08-12 run above — that IS
   the change. Expect FEWER qualifiers, since HH%/FB%/PullAir%/EV all
   rose to the 75th.
4. Open HR Edge. Top 15 should show at most two bats per GAME, an
   `N/9` floors column, and the capped-out bats below with the rule
   stated.

### NEXT
Nothing structural. The research log is the queue now — three or four
weeks of graded bat-nights, then refit the axis weights and re-set the
floors against outcomes instead of choosing them. `floors_met` is
derivable retroactively from what the log already captures.

---

## PICK UP HERE — the measuring instrument, not more structure. 2026-08-12

**3 files (2 new scripts + 1 new test). Suite 85, FAILING: none.**
Runs alongside the scoring batch below; neither depends on the other.

### WHY THIS AND NOT NINE NEW FLOORS

Nine hard qualification floors were proposed for the HR board (Brl% 11,
Brl/PA 8, HH% 40, FB% 26, EV 91, Blast% 18, PullAir% 10, ISO .200, plus
the clears-any-park contour). Every one of those nine already EXISTS and
is computed per batter — five of them feed HR Score as ranking inputs
and four are display-only. **None of them gates anything**, which is the
real hole: a bat at 3% Brl/PA is not excluded, he takes a low percentile
and can still ride park, weather and pen into the top 15.

The floors are a good idea. They were not buildable yet, for one reason:

**calibration.json records the top 5. The board rates ~270 bats a night
and discards 265.** After sixteen days that is ~80 graded HR picks, all
from the extreme top of the distribution, and it cannot answer the
question everything rests on — *does an 88 HR Edge homer more often than
a 71?* You cannot validate a ranking by only ever recording its first
five rows. Every weight in top_plays and every proposed floor is an
opinion until the middle of the distribution is on disk beside the top.

Three or four weeks of this gives ~8-10k graded bat-nights, and then
each of those arguments becomes a query.

### `hr_research_log.py`

    python hr_research_log.py log      # evening, beside calibration_picks
    python hr_research_log.py grade    # next morning, after the nightly

Writes `data/hr_research/YYYY-MM.ndjson`, one line per bat-night: the
edge components kept SEPARATE from hr_score (a miss from mis-rating the
hitter and a miss from mis-rating the park want opposite fixes), plus
all nine floor metrics, plus the result.

**It is NOT a second pick record.** It never touches calibration.json,
feeds no page, and must never be used to report a hit rate — it contains
every bat on the slate, most of which the site never recommended.

Grades off `app/data/statcast/batters/{id}.parquet`, the files the
nightly already writes. No network, no Stats API. Grading 270 bats a
night through `_mlb_line` would be 270 HTTP requests; this is a
dataframe lookup against the same source the metrics come from.

**THE GUARD THAT MATTERS.** "No rows for this batter on this date" is
ambiguous: he did not play, or the pull has not reached that date. Read
the second as the first and a whole night closes as DNP with a permanent
0 against each bat, and the file looks complete. A real slate always has
most of its bats appearing, so **under 50% appearing means the pull is
behind and the whole night is left ungraded.** This is the same mistake
that once closed 45 WNBA picks as DNP against games already played.

### `hr_floors_probe.py` — one-shot, run it before deciding anything

Reads every batter parquet, computes metrics by calling the engine's own
`_compute_batted_ball_metrics` (a probe that reimplements Brl% measures
a stat the site does not have), and prints four things:

1. **Where each proposed floor sits in the real league** — median, 75th,
   90th, and whether the floor is below the median. Two of the nine look
   like they may be: HH% 40 is near league average and PullAir% 10 is
   well under the measured anchor of 18. A floor below the median is a
   label, not a filter.
2. Each floor alone.
3. **The AND cascade**, so you can see which floor does the cutting.
   These nine are heavily correlated — a bat at 8% Brl/PA clears 91 EV,
   40% HH and .200 ISO by construction — so nine conditions may act like
   two, and the risk is thinking you built a wide net.
4. How many clear all nine, and **how many miss by exactly one**. That
   near-miss count decides hard gate vs a "floors met: 8/9" tier.

Rough guide in the output: about a third of qualifying hitters are in
any night's confirmed lineups, so under ~45 qualifiers means a hard gate
cannot fill a top-15 board.

### TWO TEST BUGS FOUND, both the same species as the last round

**1. A FUNCTION NAMED NARROWER THAN ITS SCOPE.** `_read(date_str)` read
like a day's rows and returned the whole month, so "tonight is ungraded"
picked up last night's graded rows and failed against working code.
Renamed `_read_month`. The write in `grade()` also keyed its destination
off `rows[0]["date"]` rather than the file it came from — same month by
construction, which is exactly the kind of assumption that puts a
month's rows in another month's file the first time it breaks.

**2. A CASE PASSING ON THE WRONG GUARD.** "Tonight is never graded"
passed because the coverage guard fired, not because of the date check —
the fixture had no batter rows for today. So the control that deleted
the date check stayed green. The fixture now covers today, which is the
realistic case anyway: **a 1 PM game lands in the pull hours before the
7 PM games finish**, and without the date check the grader would close
tonight's board at 4 PM.

Six controls confirmed red.

### NEXT — in this order, and the order is the point

1. Run `hr_floors_probe.py`. Nobody knows what the nine floors leave.
2. Wire the two logger calls into CI and let it run 3-4 weeks.
3. THEN decide floors, and refit the axis weights against real graded
   bat-nights instead of choosing them.

The HR Edge board batch (unclamped sort key, stated tiebreak,
`batting_order` on confirmed lineups, sample column, 2-per-game cap) is
still unstarted and is independent of all of the above.

---

## PICK UP HERE — HR scoring math and floors rebuilt. 2026-08-12

**5 files. Suite 84, FAILING: none** (the five streamlit-only ones in a
bare container, as always). **NOT YET RUN AGAINST A REAL NIGHTLY** —
every number below is verified against synthetic frames only. Rule 22:
read the next `nightly-data` log before trusting the table.

### THE DOUBLE COUNT, AND IT WAS THE SAME BUG TWICE

`hr_score` fed an "INTENT" axis from `hr_intent_pct`. HRIntent is the
mean of bat speed, HR window % and pull air % — and the last two WERE
the LAUNCH axis. So two columns entered the score through two doors, on
two different scales, while the docstring said the axes were
independent. Stated weights were power .45 / launch .30 / intent .15.
What the arithmetic actually produced:

    Brl/PA 37.5% | EV90 12.5% | HR window 22.2% | pull air 22.2%
    bat speed 5.6%

Launch plane carried 44% against power's 50%, and bat speed — the one
input measuring the SWING rather than the result of a swing — carried a
twentieth. That is the identical failure the docstring describes in the
version BEFORE it, where Barrel%, Hard-Hit% and EV were averaged as
three axes while measuring one thing. The fix for that bug contained it.

**Four axes now, and no column appears in two of them:**

| axis | weight | inputs |
|---|---|---|
| POWER | .40 | Brl/PA (.70), EV90 (.30) |
| CONVERGENCE | .30 | FB95 % (.60), Clears Anywhere % (.40) |
| LAUNCH | .22 | HR window % (.50), pull air % (.50) |
| PROCESS | .08 | bat speed, alone |

**FB95 was already computed, ranked, displayed — and scored nothing.**
Its own comment calls it the intersection that predicts home runs. It is
in the score now, as its own axis with Clears Anywhere: hard contact
ACTUALLY PUT IN THE AIR is not power and is not launch, and a bat can
sit top-decile in both and rarely combine them in one swing.

Correlation between axes remains — every batted-ball stat correlates
with every other. Nothing is literally entered twice, and the weights
say what the arithmetic does. **They are still calibration constants,
not fitted.** Refit them once calibration has graded history.

### COVERAGE FLOOR — one axis is not a score

Renormalising over live axes stops a MISSING axis reading as a zero. It
did nothing about a bat with only one axis PRESENT, which received a
full 0-100 indistinguishable from a bat measured on four. A score now
needs `_MIN_LIVE_WEIGHT` (0.60) of its own definition and must include
POWER.

**The Savant-only path is deliberately exempt.** When
`hr_metrics.parquet` is absent — fresh deploy, or an archive predating
it — the Savant percentile average is a complete score on its own, and
that fallback is the only reason the site did not go blank for the weeks
the metrics reader pointed at the wrong directory. The floor governs the
NEW path only: under-covered falls back to Savant, and returns None only
when neither source has the bat.

### THE GAP WAS A COUNT

`xhr_gap` was `xhr - hr` in whole home runs, percentile-ranked as if it
were a rate, then worth +/-8 on the score. **A count carries playing
time inside it.** A 550-PA bat can run six either way; a 60-PA bat
structurally cannot. Both tails of that percentile were regulars, and
part of what the correction rewarded was being in the lineup every
night. It was also the one figure in `build_hr_metrics` that skipped the
shrinkage every other rate gets.

Now `xhr_gap_rate`: per SCOREABLE batted ball, regressed with
`K_XHR_GAP = 150`. Per batted ball and not per PA on purpose — contact
rate is already inside Brl/PA in the power axis, and putting it in the
conversion correction too would be the same double-count one layer down.
`xhr_gap_rate_raw` ships alongside for display, and the raw count stays.

`hr_score` reads `xhr_gap_rate_pct`. **If that name ever reverts to
`xhr_gap_pct` the adjustment silently stops firing** — the new nightly
does not publish that column — and every score shifts with no error.
`test_hr_score` case 6 pins it.

### UNTRACKED CONTACT WAS BEING SCORED AS ZERO

The worst of the batch, because it looked like nothing. A batted ball
with no exit velocity or launch angle binned to NaN, missed the grid
merge, and took `fillna(0.0)` — **unmeasured contact scored as contact
that had no chance of leaving, while it stayed in the denominator.** Two
hitters who swung identically got different numbers because one played
in front of cameras that missed more balls. Missing-is-not-zero is
applied correctly three other places in that same function; the xHR path
was the one leak.

Three separate cases now, and they are NOT the same:

| what | treatment |
|---|---|
| no EV/LA at all | excluded from numerator and denominator |
| tracked, OUTSIDE the grid region (EV<80, LA outside 8-50) | a real 0.0 — the region was drawn where home runs happen |
| tracked, IN region, bucket dropped for thin sample | excluded, not zeroed — those buckets sit at the extremes where probability is HIGHEST, so zeroing them understated exactly the contact xHR exists to find |

`bbe_scored` is the denominator every xHR-derived rate divides by, and
`hr_tracked` is what the gap subtracts — an untracked home run used to
land in the subtrahend with nothing on the other side of it, pushing a
hitter's gap negative for doing the thing the metric rewards.
`HRM_MIN_TRACKED_BBE = 25`; below it xHR, the gap and Clears read N/A.

**The nightly now prints the scoreable share.** If that number is not in
the high nineties, read it before trusting anything above.

### THE PERCENTILE SCALE COMES FROM REGULARS

Inclusion is 50 PA / 30 BBE, deliberately low so a bench bat in
tonight's lineup still scores. But ranking everyone against everyone let
several hundred thin bats — all shrunk to the league mean BY
CONSTRUCTION — pile into the middle of every distribution and stretch
the tails. A regular's percentile depended on how many part-timers
happened to clear the floor that week.

`HRM_CORE_PA = 150` defines the scale; everyone else is PLACED on it by
searchsorted. Thin bats still rank, and still rank fairly. Under 30 core
bats it falls back to whole-pool ranking and says so in the log —
early April is a real state, not an error.

### ALSO

- `_regress` returns NaN on a zero league denominator instead of
  dividing by nothing and printing a numpy warning into the nightly log.
- Clears Anywhere divided by total BBE; it can only ever be counted on a
  ball that reached the grid, so it divides by `bbe_scored` now.
- HRThreat's comment said "60% outcome / 40% process". The genuinely
  process-only share is bat speed at 40/3 ~= 13%: HRIntent's other two
  inputs are outcomes. **Weights unchanged, label fixed** — the 60/40
  outcome lean is the decision; a right number under a wrong label is
  the one error nobody downstream can catch.
- `_league_hrfb()` was opening and re-parsing `baselines.json` once per
  hitter, inside the per-batter loop. `lru_cache`.
- `rank_batters` now carries `hr_pa` / `hr_bbe` so a board can show the
  denominator. Nothing renders them yet — that is the HR Edge batch.
- **`hr_intent_pct` and `hr_threat_pct` are now published and read by
  nothing.** `hr_threat_pct` already was. Left in rather than deleted: a
  key-literal grep cannot see a dynamic access, and this repo has had a
  sweep wrongly report rendered fields as unrendered for exactly that
  reason. Check the views for an f-string access before removing.

### TWO CONTROLS THAT DID NOT FIRE, both fixture bugs, both recorded

**1. A BOUND ASSERTED AGAINST ITS OWN CONSTANT.** `test_hr_score` case 5
read `2 * tp._XHR_MAX_ADJ + 1`. Widening the constant from 8 to 30
widened the bound with it, and the case stayed green through a control
that turned a bounded correction into the largest term in the score. A
test that derives its expectation from the thing under test measures
nothing. Literal now, plus a separate assertion pinning the constant.

**2. A FIXTURE WHOSE VALUES COULD NOT MOVE.** The scale case measured
`brl_per_pa_pct`, and every bat in that fixture barrels everything — so
all forty regulars tied on that column, and searchsorted gives ties the
same position whatever the scale is built from. It went green against a
control that ranked everyone together. Measured on `ev90_pct` now, where
the regulars actually spread and the part-timers sit in the MIDDLE of
that spread, which is where they do the most damage. Same round: the
untracked-contact fixture had no untracked HOME RUN, so `hr` and
`hr_tracked` were equal and the tracked-HR subtraction was untestable.

Same lesson as the KBO rounds and rules 25/26: **a test that cannot fail
is not evidence.** Twelve controls confirmed red across the two files.

### VERIFY, in order

1. `git pull`, run the suite. **84 files, FAILING: none.**
2. **Read the next `nightly-data` log.** The HR metrics line now ends
   with the core size and the scoreable share:
   `N in the 150+ PA scale core · X of Y batted balls scoreable (Z%)`.
   A low Z, or a core under 30, changes how everything above reads.
3. `python -c "import pandas as p;d=p.read_parquet('app/data/statcast/hr_metrics.parquet');print(d[['bbe','bbe_scored','xhr_gap','xhr_gap_rate']].describe())"`
   — `xhr_gap_rate` should be small and centred near zero, and
   `bbe_scored` should sit just under `bbe`.
4. **Open HR Edge and Player of the Day.** Scores will MOVE — the axes
   and the scale both changed. That is expected. What is not expected is
   blank scores: if a column is empty, the nightly has not republished
   yet and `hr_score` is on the Savant fallback.

### NEXT
The HR Edge board batch, unstarted: sort on the unclamped float with a
stated tiebreak (integer `edge` + a stable sort currently resolves ties
by slate iteration order, and teammates share `ctx_adj` exactly so they
tie more often than strangers), pass `batting_order` on confirmed
lineups, correct the fidelity docstring, show the sample column, then
the 2-per-game cap.

---

## PICK UP HERE — tier 2's cause found and fixed. 2026-08-11

**3 files. Suite 83, FAILING: none.**

### THE DIAGNOSTIC NAMED IT, AS DATA

    mlb slate: no projected total — not enough real run data for both teams yet
      schedule says home='Detroit Tigers' away='Cleveland Guardians'
      standings knows 30 clubs, e.g. ['Angels', 'Astros', 'Athletics']
      home matched: False | away matched: False

**The two MLB endpoints disagree about what a team is called.** Schedule
says "Detroit Tigers"; standings says "Tigers". Every lookup missed, all
fifteen games, and tier 2 wrote zero totals **with no error** — the
fetch succeeded, so nothing was wrong to report.

My hypothesis was right in shape and **wrong in detail**: I assumed
standings used the LONGER form. Printing both is what settled it.

### THE FIX — DERIVED, NOT HAND-WRITTEN

`canonical()` reduces either vocabulary to the abbreviation, and the
alias index is **built from `engines/team_abbreviations`** — the map the
app already uses and has verified. A second hand-written table of thirty
clubs would be a second thing to be wrong, and would drift on a rename.
Verified: **all 30 standings short names resolve, to 30 distinct clubs.**

**Ambiguous suffixes resolve to NOTHING.** "Sox" ends both Red Sox and
White Sox; a suffix matching more than one club maps to None. Guessing
would put the wrong offense on a card with nothing on screen to
contradict it.

`parse_standings` keys every record by BOTH name and abbreviation,
pointing at ONE dict. End to end, the exact failing matchup — Cleveland
Guardians @ Detroit Tigers — now projects **8.4**.

### TWO TEST BUGS FOUND WHILE FIXING IT, both the same shape

**1. A STUB THAT DID NOT MATCH THE INTERFACE.** `_Resp` exposed
`.json()` and I "fixed" it toward `.content` — but
`fetch_team_run_rates` uses `requests.GET` and `r.json()`. I had been
editing the test to match a DIFFERENT engine's shape. The original stub
patched `requests.get` correctly; my edit broke it, the call fell
through to a real request, and "22 of 30 is refused" passed on a
sandbox 403 instead of the guard.

**2. A FIXTURE THAT COULD NOT EXERCISE ITS OWN ASSERTION.** The
partial-league guard now counts distinct clubs rather than keys, because
dual keying makes `len(rates)` 60. The control for that did NOT fire —
the fixture used "Club 0".."Club 21", which `canonical()` does not
recognise, so they were keyed once and key-count equalled club-count.
Real names now, and the control fires.

Both are the same lesson as the KBO rounds: **a test that cannot fail is
not evidence.** Four controls now confirmed red — raw-name lookup,
ambiguous coin-flip, guard counting keys, unknown-name fallback.

### VERIFY
Re-run Slate Picks. Expect `15 with a projected total`. If it is still
0, the reason now prints with both canonical forms and whether they
matched — read that, do not infer.

Also confirmed live in the 11:40 run: **13 of 15 with a modeled edge**
at 7:40 AM ET, and **12 weather from NWS forecast**. Both earlier fixes
are working.

---

## PICK UP HERE — tier 2 wrote 0, and the reason was thrown away. 2026-08-11

**One file: `calibration_picks.py`.** Suite 83, FAILING: none.

### THE RUN — 2026-08-11 11:40 UTC, manual

    mlb slate: wrote 15 game(s) for 2026-08-11
      (13 with a modeled edge, 3 roofed, 12 weather from NWS forecast,
       0 with a projected total)

Everything else worked. **13 of 15 with a modeled edge at 7:40 AM ET** —
probables were already posted, better than expected. **12 weather from
NWS forecast** — that fix is live and doing its job.

**0 with a projected total, and NO error line above it.** So
`fetch_team_run_rates` SUCCEEDED — a failure would have logged
`no team run rates (...)`. The fetch worked and every projection failed.

### AND THE REASON WAS COMPUTED AND DISCARDED

`project_total` returns `(None, {"reason": ...})`. The code did:

    _t, _why = project_total(...)
    if _t is not None: ...

`_why` bound and never printed. **Rule 20, in the one place where the
reason IS the answer** — fifteen games, fifteen discarded explanations,
and a log line that says what happened but not why.

Now printed ONCE per run (fifteen identical lines would be noise), along
with the schedule's team names, the standings' team names, and whether
each matched.

### THE HYPOTHESIS, AND IT IS ONLY THAT

`run_rates` is keyed by the name **standings** uses. `home`/`away` come
from the **schedule**. If those vocabularies differ, every lookup misses.

Reproduced offline: matched names give a total of 8.7; a mismatch gives
exactly `(None, "not enough real run data for both teams yet")` — the
observed symptom.

**Do not fix this on that basis.** The next run prints the actual names
from both sources and says whether they matched. That is a fact; the
above is a guess that happens to fit. Nine rounds of KBO were spent on
guesses that fit.

### NEXT
Re-run Slate Picks manually. Read the three new lines under
`no projected total`. If the names differ, the fix is a mapping at the
lookup — and `engines/team_abbreviations` already exists for exactly
this kind of translation.

---

## PICK UP HERE — scope answered, window walk built. 2026-08-11

**3 files. Suite 83, FAILING: none.** `kbo_official.py` still NOT wired
into `kbo_precompute`.

### THE SCOPE ANSWER — run 85401634630

`GetKboGameDate` returns a **CURSOR, not a range**:

    BEFORE_G_DT 20260809 | NOW_G_DT 20260811 | AFTER_G_DT 20260812

previous / current / next game date. So a window is one call per date
either way. **The cursor is deliberately NOT used for the walk** —
following `AFTER_G_DT` costs an extra request per step to skip off-days
that `GetKboGameList` already reports as empty in a single call. Twice
the traffic to learn something the cheaper call tells us anyway.

It also carries the SAME trailing ASP.NET error page, which confirms
that quirk is site-wide rather than specific to one method. The engine's
tolerance is right for every endpoint here.

**Full migration is therefore cheap: ~14 POSTs for a fortnight**, one
per calendar date, against the league's own servers with a courtesy
pause. That is fewer requests than the current weekly walk of a fan site.

### `fetch_window(start, days)` — the one property that matters

**An off-day and a broken date are NOT the same thing.** Off-day = code
100, no rows, no error. A 503 = a recorded gap. Conflating them means a
nightly either publishes a fortnight with holes it does not know about,
or refuses to publish over a Monday with no baseball.

Errors are COLLECTED, never raised: one bad date must not cost the other
thirteen. Verified with a stubbed walk containing both an off-day and a
503 — the good dates still come back, and the gap is named.

### A TEST BUG WORTH RECORDING
The cursor-not-used assertion first checked the whole source and failed
on the **paragraph explaining why the cursor is unused** — rule 26
again, in a file written the same day I cited it. Now strips comment
lines and asserts the reasoning is still present. Control confirms it
fires when the cursor is genuinely used.

### THE MIGRATION MAP — what still needs deciding

`kbo_precompute` takes four things from mykbostats. The official source
covers three outright:

| what | mykbostats | GetKboGameList |
|---|---|---|
| schedule, venue, time | `parse_week` weekly walk | `G_DT` `G_TM` `S_NM` |
| probables | homepage scrape | `T_PIT_P_NM` / `B_PIT_P_NM` **+ player ids** |
| cancellation | `VOID_RISK_PAT` text | `CANCEL_SC_NM` official |
| **scoreline H2H** | `parse_week` scorelines | **UNVERIFIED** |

The first three are strict upgrades — official names, official status,
and player ids the scrape never had. **H2H is the open one.** The row
carries `B_SCORE_CN` and `GAME_RESULT_CK`, so past dates probably return
scores, but nobody has called this for a past date. **That is the last
thing to check before the swap** — one probe against a date last week.

Do not migrate until it is checked: dropping mykbostats while H2H
silently empties would take a rendered section off the KBO board.

---

## PICK UP HERE — KBO engine built. Scope probe pending. 2026-08-11

**3 files. Suite 83, FAILING: none.** `app/engines/kbo_official.py` is
NEW and NOT YET WIRED into anything.

### CONFIRMED ON A REAL SLATE — run 85398873888

    20260811HHOB0  한화 @ 두산   19:00  away 왕옌청   home 곽빈    정상경기
    20260811LTSK0  롯데 @ SSG   19:00  away 비슬리   home 아빌라   정상경기
    20260811SSHT0  삼성 @ KIA   19:00  away 페덱     home 올러    정상경기
    20260811KTNC0  KT  @ NC     19:00  away 로건     home 라일리   정상경기
    20260811LGWO0  LG  @ 키움    19:00  away 카라스코  home 안우진   정상경기
    5 of 5 game(s) have BOTH starters named.

One POST to `/ws/Main.asmx/GetKboGameList` gives game ids, teams, time,
stadium, BOTH starters with player ids, status and cancellation.

### THE ENGINE, AND THE TWO THINGS IT REFUSES TO DO

**`app/engines/kbo_official.py`** — parse + fetch, nothing else. It does
not project, grade or rank; it turns one response into records.

**1. THE TRAILING ERROR PAGE IS IGNORED, PERMANENTLY.** The server
returns a COMPLETE, SUCCESSFUL document — `{"game":[...], "code":"100",
"msg":"성공"}` — and then staples an ASP.NET runtime error page to the
same body. `json.loads` refuses the lot with "Extra data: char 8398".
It is present on EVERY successful call, so treating it as a failure
means never succeeding. `raw_decode` reads document one and stops.

**2. BOTH STARTERS OR NEITHER.** `starters_for` excludes a game unless
both sides are named. One name beside a blank reads as "the other team
hasn't announced" — a claim about the league, when the truth is we read
one side. `game_records` still returns every game, so a caller wanting
the schedule is not punished by the gate.

Cancellation compares against the ONE known-normal value (정상경기)
rather than listing reasons: the field is free text and a whitelist
would pass an unlisted reason through as fine.

`tests/test_kbo_official.py` (NEW, #83) — 30 assertions. Five negative
controls: json.loads instead of raw_decode, half-a-matchup, **T/B
swapped** (which would flip every starter on the board and look
normal), a reason whitelist, and a non-100 code treated as success.

**The code-check control initially did NOT fire** — the check lived in
`fetch_game_list`, which needs network, and nothing exercised it. Added
a stubbed-`requests` block; it now fails correctly. Worth noting because
a 200 with a failure code and a genuine off-day both arrive as "no
rows", and reading that wrong renders a broken call as "no KBO games
today" — a normal-looking page making a false statement about the
league.

### NOT WIRED YET, ON PURPOSE — the scope question

`GetKboGameList` takes ONE date. The pipeline currently walks WEEKS off
mykbostats. So the migration is either narrow (probables only, keep
mykbostats, stay bound by AUP clause 6 — pointless) or full (replace the
schedule walk too).

The cost of full depends on `GetKboGameDate`, the other web method round
5 found and nobody has called. **The probe now calls it.** A month of
dates in one response makes full cheap; one date makes it ~14 calls for
a fortnight — still fine against the league's own servers, but worth
knowing before committing.

**Run the probe, read the SCOPE PROBE block, then decide.** Building the
pipeline change on an assumption about that endpoint is exactly the
mistake the last nine rounds were made of.

---

## PICK UP HERE — KBO SOLVED. The answer was in the payload all along. 2026-08-11

**One file: `kbo_fragment_probe.py`.** Suite unchanged at 82.

### THE BYTE WINDOW EXPLAINED IT AND THEN ANSWERED THE WHOLE QUESTION

The trailing bytes at char 8398:

    ...  "code": "100",  "msg": "성공"  }
    >>> FAILS HERE >>>
    '<!DOCTYPE html>...<title>런타임 오류</title>...'

**The JSON is complete and successful** — `code 100`, `msg 성공`
("success") — and the server then appends an **ASP.NET runtime error
page** to the same response. That is the "Extra data" and the "Expecting
value". Rounds 7 and 8 theorised about BOMs and concatenated documents;
it was a stack trace bolted onto a valid payload, and no amount of
inference was going to produce that.

Keeping partial documents paid off immediately: **`parsed 5 game
row(s)`**, `using G_ID=20260811HHOB0`.

### AND THE STARTERS WERE IN THAT PAYLOAD THE ENTIRE TIME

The window printed the key list, and it contains:

    T_PIT_P_NM / T_PIT_P_ID    away starter, name and player id
    B_PIT_P_NM / B_PIT_P_ID    home starter, name and player id
    CANCEL_SC_NM               cancellation status, in words
    GAME_SC_NM  AWAY_NM  HOME_NM  S_NM  G_TM  LINEUP_CK

T = top of the inning = away, B = bottom = home. **One JSON call to
`/ws/Main.asmx/GetKboGameList` gives game ids, teams, start time,
stadium, BOTH STARTERS with player ids, cancellation status and a lineup
flag.**

`StartPitcher.aspx` — chased since round 1 — is the deep ANALYSIS page,
not the source of the names. It does work (**200, 7253b, 선발 x2, headed
선발투수 전력분석**), so the endpoint hunt was not wasted; it is just not
what probables need.

### THE LESSON, AND IT IS THE SAME ONE NINE TIMES OVER

Every round that printed raw material moved forward. Every round that
reasoned from an error message shipped a fix for a cause that did not
exist. The thing that finally cracked it was pointing the dump AT THE
FAILURE instead of at the start of the body — a two-line change I could
have made at round 6.

### WHAT SHIPS IN THIS FILE
The probe now prints, per game: id, teams, time, BOTH starters, status
and cancellation — then counts how many rows have BOTH names. That count
is the gate a real parser needs: **half a matchup reads as a whole one**,
so a board must fill both sides or show neither.

### NEXT — this is now a build, not a question
1. Run it once more and read the starters table. Confirm names are
   populated at a sane KST hour (this run was 19:xx, games already
   underway).
2. Write the parser into `kbo_precompute`: one POST to
   `GetKboGameList`, tolerate the trailing error page via `raw_decode`,
   read `T_PIT_P_NM`/`B_PIT_P_NM`, gate on both-or-neither.
3. **`CANCEL_SC_NM` is a bonus** — an official cancellation field, which
   is a better source than the homepage text `VOID_RISK_PAT` currently
   scrapes. Worth comparing before switching.
4. **Then drop mykbostats** (AUP clause 6 forbids using their content
   for betting). That was the point of all nine rounds.

---

## PICK UP HERE — KBO round 9. I kept dumping the wrong 1200 bytes. 2026-08-11

**One file: `kbo_fragment_probe.py`.** Suite unchanged at 82.

### THE ERROR MOVED, WHICH MEANS ROUND 8 ALSO FIXED THE WRONG THING

    round 7:  Extra data: line 336 column 2 (char 8397)   body 11460
    round 8:  Expecting value: line 336 column 2 (char 8399)  body 11462

Round 8 switched to `raw_decode` for concatenated documents. It DID
consume document one — the offset advanced past it — and then found
something at char 8399 that is not the start of any JSON value. So the
body is not simply two JSON objects, and round 8's fix, like round 7's,
addressed a cause inferred from an exception message rather than seen.

### THE ACTUAL MISTAKE, AND IT HAS BEEN RUNNING FOR THREE ROUNDS

| what the probe printed | covers |
|---|---|
| first 40 bytes on the wire | chars 0-40 |
| RAW JSON, first 1200 chars | chars 0-1200 |
| **the failure** | **char 8399 of 11462** |

**Every diagnostic in this probe looks at the START of the body. The
problem has never once been at the start.** I added "print the raw
material" three times and every time pointed it at the beginning, then
theorised about 8kb of bytes nobody had looked at.

Round 9 prints a **window around the reported offset** — 250 chars
before, 350 after, in repr, plus the last 200 chars of the body. Whatever
sits at 8399 will be readable instead of guessable.

It also keeps whatever documents DID parse rather than discarding them.
**The first document has parsed successfully in both round 7 and round
8** — the game rows were available both times and were thrown away over
what follows them.

### VERIFIED OFFLINE
Trailing HTML, a genuine second document, trailing junk, and a clean
body: the window reports the stop offset and shows the bytes for each,
and partial documents still yield their game rows.

### THE HONEST STATE
`GetKboGameList` returns **200 with ~11.5kb of real game data on every
run since round 6**, including `G_ID`, `SEASON_ID`, `AWAY_ID`, `HOME_ID`
and `GAME_SC`. The endpoint is not the problem and has not been for
three rounds. **The problem is entirely in how this probe reads it.**

If round 9's window does not make the cause obvious, that is the point to
stop probing and open the URL in a browser — five minutes with the raw
response beats a tenth round of inference.

---

## PICK UP HERE — KBO round 8. My round-7 fix was for the wrong cause. 2026-08-11

**One file: `kbo_fragment_probe.py`.** Suite unchanged at 82.

### THE DIAGNOSTIC WORKED, AND DISPROVED MY OWN FIX

Round 7 added "print the first 40 bytes and the full exception" because
round 6's `could not parse as JSON (JSONDecodeError)` said nothing about
the cause. It immediately earned its place:

    JSONDecodeError: Extra data: line 336 column 2 (char 8397)
    first 40 bytes on the wire: b'{\r\n  "game": [\r\n    {\r\n      "LE_ID": 1,'
    declared encoding: 'UTF-8'  content-type: 'text/plain; charset=UTF-8'

**NO BOM.** The body starts with a plain brace. Round 7 "fixed" a BOM
that was never there — I formed that hypothesis from an exception NAME,
confirmed it in isolation against a synthetic BOM, and shipped it. **A
plausible cause, reproduced in a test I wrote myself, is not the same as
the actual cause.** The `utf-8-sig` decode was harmless and beside the
point; the diagnostic line is what found the truth.

### THE REAL SHAPE: SEVERAL CONCATENATED JSON DOCUMENTS

`Extra data` at char 8397 of 11460 means the first document ENDS there
and another begins. The endpoint returns `{"game":[...]}` followed by at
least one more object. `json.loads` parses exactly one document and
refuses the rest — so it discarded a complete answer for the **second
round running**, both times reporting it as an endpoint failure.

`raw_decode` consumes one document at a time and reports where it
stopped. All documents are merged, so a single-document payload behaves
identically and this cannot regress if the endpoint ever changes.

Verified offline against five shapes: round 7's real two-document CRLF
body, three documents, a single document, a BOM as well, and a
ScriptService `d` wrapper. **All five parse; the game row comes out of
every one.**

### THE PATTERN, THREE TIMES OVER NOW

- rounds 2-4: searched HTML for an id that lives behind a web method
- round 6: got a perfect 200 and reported NO GAME ROWS
- round 7: fixed a BOM that did not exist

Every one is the same failure: **acting on a hypothesis about what is
there instead of printing what is there.** Every recovery came from a
line that dumped raw material. The probe is now mostly made of those
lines, which is why it keeps making progress.

### THIS IS STILL THE LAST HOP
`GetKboGameList` -> real `G_ID` -> `StartPitcher.aspx`. The first call is
confirmed working with real data in hand; only the second's response is
unseen.

- **A fragment with Korean names** -> round 9 is the parser, and
  mykbostats can go (AUP clause 6).
- **500 on StartPitcher** -> `srId` is the only value still guessed.
- **Parse still fails** -> the printed document list and key names are
  the answer. Do not theorise from the exception name; that is what
  produced rounds 7 and 8.

---

## PICK UP HERE — KBO round 7. The endpoint WORKS. My parser threw it away. 2026-08-11

**One file: `kbo_fragment_probe.py`.** Suite unchanged at 82.

### ROUND 6 SUCCEEDED AND THE PROBE REPORTED FAILURE

    CALLING .../ws/Main.asmx/GetKboGameList
      json body: {'leId': '1', 'srId': '0', 'date': '20260811'}
      -> 200 | 11461b
      ---- RAW JSON ----
      { "game": [ { "LE_ID": 1, "SR_ID": 0, "SEASON_ID": 2026,
                    "G_DT": "20260811", "G_ID": "20260811HHOB0",
                    "G_TM": "19:00", "S_NM": "잠실", "AWAY_ID": "HH", ...
      could not parse as JSON (JSONDecodeError)
    NO GAME ROWS.

**200. Eleven kilobytes of perfect JSON. Every field needed.** And the
probe said NO GAME ROWS — because `json.loads` raised *"Unexpected UTF-8
BOM"*. Three bytes. A working answer, discarded, and reported as a
failure of the endpoint.

That is the same shape as every other bug in this sequence, now on my
own side of the wire: **the output could not distinguish "the source
failed" from "I mishandled what the source gave me."** `could not parse
as JSON (JSONDecodeError)` names the exception and says nothing about
the cause, when the first forty bytes would have named it instantly.

Two fixes, both about that:
- `lr.content.decode("utf-8-sig")` — strips a BOM, no-op without one.
  Explicit UTF-8 matters twice over here: the payload carries Korean
  stadium names (잠실) and `requests` guesses ISO-8859-1 when the server
  omits a charset, which would mangle every one while still parsing.
- On any decode failure it now prints **the first 40 bytes as a repr**,
  the declared encoding and the Content-Type. An exception name is not a
  diagnosis.

### AND ROUND 2'S GUESS WAS RIGHT ALL ALONG

`G_ID: "20260811HHOB0"` — exactly the `20YYMMDD + 4 letters + digit`
shape round 2 assumed and got zero matches for. **The format was never
wrong. The place was.** It lives behind this web method and was never in
the page, so no amount of searching the HTML at any format could have
found it. Rounds 2, 3 and 4 were unwinnable, not badly aimed.

### KEYS, NOW KNOWN AND NO LONGER GUESSED

    LE_ID  SR_ID  SEASON_ID  G_DT  G_DT_TXT  G_ID  HEADER_NO
    G_TM   S_NM   AWAY_ID    HOME_ID   GAME_SC

Matched case-insensitively with the old guesses kept behind them: the
dump showed the FIRST row's keys, and a name seen once is not a name
confirmed on every row.

Verified offline end to end against the real payload shape, BOM
included: 2 rows parsed, the `GAME_SC == "1"` game selected over the
finished one, `G_ID`/`SEASON_ID`/`AWAY_ID`/`HOME_ID` all read, Korean
intact.

### THIS IS THE LAST HOP
The chain is now: `GetKboGameList` -> real `G_ID` -> `StartPitcher.aspx`.
Both calls confirmed reachable; only the second's response is unseen.

- **A fragment with Korean names** -> round 8 is the parser, and
  mykbostats can go (AUP clause 6).
- **A 500 on StartPitcher** -> `srId` is the only value still guessed.
- **Empty fragment** -> check `GAME_SC` values in the dump; every game
  may already be live or final at that hour.

---

## PICK UP HERE — KBO round 6. THE CALL IS FOUND. 2026-08-11

**One file: `kbo_fragment_probe.py`.** Suite unchanged at 82.

### ROUND 5 FOUND IT, in the path sweep

    $.ajax({ type: "post", url: "/ws/Main.asmx/GetKboGameList",
             dataType: "json",
             data: { leId: "1", srId: srId, date: $("#txtGameDate").val() } })

**`/ws/Main.asmx/GetKboGameList`** builds `.game-list-n`, and it returns
**JSON, not markup**. Invisible to rounds 1-4 because it is a `.asmx`
web method behind `$.ajax` rather than an `S2iAjaxHtml` block — only the
"every quoted path" sweep could see it.

### THE IRONY, RECORDED SO IT IS NOT REPEATED

**v1 of this probe guessed `.asmx` endpoint names, got 401/401/500, and
that was written down as "no endpoint found"** — which sent four rounds
down the HTML path looking for something that was never there.

**The `.asmx` route was right the whole time.** v1 guessed the wrong
method names, and a wrong guess and a dead route return the same thing.
`GetKboGameList` and `GetKboGameDate` were sitting in the page's own
script for all five runs, waiting to be read rather than guessed.

That is the same lesson as rounds 2, 3 and 4, one level up: **a probe
that guesses can only ever confirm or deny its own guess.** It cannot
tell you what is actually there.

### ALSO: .asmx WANTS JSON, NOT FORM FIELDS

A ScriptService method needs `Content-Type: application/json` and a JSON
body, and answers `{"d": ...}`. Posting form-encoded data yields a 500
that looks exactly like a dead endpoint — almost certainly what v1 hit,
on top of the wrong names.

### ROUND 6

1. POST JSON to `GetKboGameList` with `{leId:"1", srId:"0", date:YYYYMMDD}`.
   **`leId: "1"` is the page's own literal, not an assumption.** `srId`
   `"0"` is the ONE guess left and is labelled in the output.
2. Unwrap `{"d": ...}` defensively — d-as-list, d-as-object, d-as-JSON-
   string and bare-list all handled; **verified offline against all four.**
   The shape inside is NOT guessed at: it prints the raw JSON and the
   key names off the first row.
3. Pick a game with status `1` (the page's own preview branch), read the
   id by case-insensitive key match (`G_ID`/`gameId`/`gid`), and chain
   straight into `StartPitcher.aspx` with real values.

Team codes are read from whatever key the row carries; if none matches,
it sends EMPTY and says so rather than inventing a code.

### READ THE LOG LIKE THIS
- **A fragment with Korean names** -> round 7 is the parser. mykbostats
  can go (AUP clause 6).
- **SOAP fault on GetKboGameList** -> field names or content type. Read
  the fault string; it is descriptive.
- **Empty game list** -> check a date you KNOW has games before
  concluding.
- **`NO ID-LOOKING KEY`** -> the key list is printed. Name it explicitly
  next round; do not guess a third time.

---

## PICK UP HERE — KBO round 5. The page is a SHELL. 2026-08-11

**One file: `kbo_fragment_probe.py`.** Suite unchanged at 82.

### THE MEASUREMENT THAT SETTLES IT

    main page: 200 57178b

**Five runs, 11:21 / 11:35 / 19:07 / 19:20 / 19:26 KST — byte-identical
every time.** A live game centre whose size never moves by a single byte
across eight hours of a playing day is not rendering games. It is a
static frame that fetches everything after load.

That explains all four previous rounds at once:

| round | looked for | why it found nothing |
|---|---|---|
| 1 | 선발 in rendered content | it is in script only |
| 2 | ids matching `20260811LGOB0` | no ids in script — script's `gameId` starts `""` |
| 3 | ids under any pattern | same: they are markup attributes |
| 4 | `<li g_id=...>` in the HTML | **the `<li>`s do not exist until a fetch draws them** |

Round 4 was the right idea aimed at the right place — the place is just
empty on arrival. `$(".game-list-n > li[g_id=...]")` reads a list that
JavaScript builds.

### ROUND 5 STOPS NARROWING AND DUMPS EVERYTHING

Rounds 1-4 each guessed one layer deeper and each guess was wrong in the
same way: assuming the thing was somewhere and searching for its shape.
Round 5 asks the page to name its own calls.

- **`S2iAjax*`**, not just `S2iAjaxHtml` — a `Json` variant would have
  been invisible to every previous round.
- **Every ajax-shaped call**: `$.ajax`, `$.post`, `$.get`, `$.getJSON`,
  `.load`, `S2iAjax*`.
- **Every quoted path in the script.** This is the real safety net —
  it catches `.asmx` web methods and anything called through a wrapper
  the regexes do not know.

**What to look for: the call that builds `.game-list-n`.** It has to
come first. StartPitcher cannot be reached without a `g_id`, and the
`g_id` does not exist until that list is drawn.

Verified offline: the sweep finds `/Schedule/GameCenter/GameList.aspx`,
a `.load()` target, and `/ws/Schedule.asmx/GetGames` in one pass.

### THE HONEST STATE OF THIS THREAD

Five rounds, and the endpoint is confirmed but still uncalled. What has
been genuinely won:

- the game centre does NOT serve starters (reverses a finding that sat
  in this file for three sessions),
- the exact `param` contract, verbatim,
- the id source (`li.attr("g_id")`),
- and now that the page is a shell.

Every one of those came from a round that PRINTED THE SOURCE instead of
reporting a count. Every dead end came from a round that searched for a
shape it had assumed. That is the pattern worth keeping.

**If round 5 also comes back empty, stop probing and open the page in a
browser with devtools.** Five rounds is enough to say the static text is
not going to give it up; watching the network tab for thirty seconds
would. That is not defeat, it is the cheaper tool.

---

## PICK UP HERE — KBO round 4. The ids were never in the script. 2026-08-11

**One file: `kbo_fragment_probe.py`.** Suite unchanged at 82.

### ROUND 3 ANSWERED IT, by printing the source instead of a count

Run 85390946879. All three id patterns found zero — and then the
excerpts said why:

    var seasonId = li.attr("season");   var gameSc   = li.attr("game_sc");
    var gameId   = li.attr("g_id");     var awayTeam = li.attr("away_id");
    var homeTeam = li.attr("home_id");

and, at the top of the page:

    var gameId = "";

**The ids are HTML ATTRIBUTES on `<li>` elements in `.game-list-n`.**
The script's `gameId` starts EMPTY and is filled from the clicked list
item (or a `gameId` URL parameter). So no regex over script values could
ever have found one — there are none. They are not `data-` prefixed
either, which is why that sweep missed them too.

**Rounds 2 and 3 were both looking in the wrong PLACE, not for the wrong
shape.** Three patterns over the wrong corpus is still zero. What broke
the deadlock was round 3 printing the page's own source when it found
nothing, rather than reporting a count — the count is what made the
first two failures unreadable.

### ROUND 4 READS THE MARKUP

No attribute name is guessed. It captures the whole opening `<li>` tag
and prints it verbatim, so every attribute is visible — including
`le_id`/`sr_id`, which the page has still not shown a source for.

It picks a game with **`game_sc == "1"`**, which is not a guess either:
that is the page's own branch — `1` -> setPreview, `2`/`5` -> setLive,
`3` -> setReview. Only a preview game has starters to preview. If none
exists it says so and calls that a TIMING result, not a dead endpoint.

Every value now comes from the page: `gameId` <- `g_id`, `seasonId` <-
`season`, `awayTeam` <- `away_id`, `homeTeam` <- `home_id`, with the
field names from the `param` block round 2 printed. **The only
assumption left is `leId`/`srId`**, defaulted to "1"/"0" and explicitly
labelled in the output as the first suspects if the call fails.

Verified offline against markup matching round 3's description: two
`<li>`s, one final and one scheduled — it skips the final and picks the
scheduled one, and lists every attribute it saw.

### READ THE LOG LIKE THIS
- **A fragment with Korean names** -> round 5 writes the parser, keyed
  on markup somebody has seen. mykbostats can go (AUP clause 6).
- **`GAME LIST <li> TAGS: 0`** -> the list is filled by an earlier
  fetch. Print the `.game-list-n` block and read it, the same way round
  3 read the script. Do NOT guess an attribute name.
- **`NO game_sc==1`** -> every game today is live or final. Timing, not
  a dead endpoint. Re-run earlier in the KST day.
- **A 500 with real values** -> `leId`/`srId` are wrong; they are the
  last unknown.

### ALSO IN THIS RUN
Tier 2 reproduces (`30 entries | 30 w/stats | 30 w/runs`). NPB
reproduces (157 rows, 109 upcoming, zero risk vocabulary). Nightly ran
GREEN after the `calibration_picks.py` fix — archive published, 2548
entries, all four required files present.

---

## PICK UP HERE — KBO round 3. 2026-08-11

**One file: `kbo_fragment_probe.py`.** Suite unchanged at 82.

### ROUND 2 GOT THE CONTRACT, then stopped on a bad guess

The valuable half worked. Run 85388251099 printed the page's own call
block verbatim:

    S2iAjaxHtml({ url: "/Schedule/GameCenter/Preview/StartPitcher.aspx",
      param: { leId, srId, seasonId, awayTeam, homeTeam,
               awayPit, homePit, gameId }, async: false })

**EIGHT fields**, and round 2 was sending four — `awayTeam`, `homeTeam`,
`awayPit`, `homePit` were all missing. Printing the block BEFORE calling
is the only reason we know that instead of chasing a 500.

Then: `GAME IDS: 0 on the page`. The probe stopped rather than firing
blind, which was right — but the id format was **my second wrong guess
in this file**. `20260811LGOB0` matched nothing in 57KB, and a count of
zero cannot distinguish "no ids here" from "ids in a shape I did not
anticipate".

### ROUND 3 STOPS GUESSING

- **Three id patterns, not one**, and it reports which hit. The round-2
  guess is KEPT so its failure stays visible rather than being quietly
  replaced. The third keys on the NAME the page uses (`gameId: "..."`)
  rather than what the value looks like — that one cannot be wrong about
  format.
- **`data-*` attributes** dumped too, in case the ids live in markup.
- **When nothing matches, it PRINTS THE SOURCE** — every `gameId`
  mention in the script, verbatim, up to twelve. Round 2 printed a count
  and stopped; a count is what made "wrong guess" and "no ids" look
  identical.
- **All eight field names**, from the page's own `param` block.
  `awayPit`/`homePit` are sent EMPTY on purpose: setPreview checks
  `if (awayPit == undefined)` before firing, which reads as "this
  endpoint RESOLVES the starters" rather than "you pass them in". If
  that reading is wrong the response will say so.

Verified offline against five plausible id shapes — the round-2 format,
3-letter codes, no sequence digit, lowercase, and a wholly different
`KBO-2026-0811-07`. **All five are caught by at least one pattern.**
Round 2 would have found only the first.

### READ THE LOG LIKE THIS
- **A fragment with Korean names** -> round 4 writes the parser, keyed
  on markup somebody has now seen. mykbostats can go (AUP clause 6).
- **200, empty body** -> the params are right but something else is
  needed; the CALL BLOCKS section is still the reference.
- **`NO IDS MATCHED ANY PATTERN`** -> read the `gameId` excerpts it
  prints. Do NOT guess a third format.
- **`gameId does not appear at all`** -> it is supplied by a fetch that
  happens BEFORE this one. Find that call, not this value.

### ALSO CONFIRMED IN RUN 85388251099
Tier 2 reproduces: `standings 200 | 30 entries | 30 w/stats | 30 w/runs`.
NPB reproduces: 157 rows, 109 upcoming, zero risk vocabulary.

### WORKFLOWS — only THREE are scheduled
`nightly-data` (6 AM ET), `slate-picks` (1/5/7 PM ET), `intl-late-refresh`
(5:20 AM ET). The other **nine are manual-only probes** costing nothing
when idle, six of which have already answered their question. Worth
KEEPING: each records how a source was verified, and deleting them loses
the reasoning behind a parser's shape. If the Actions sidebar gets
noisy, move them to an archive folder rather than deleting.

---

## PICK UP HERE — NPB parity CLOSED, KBO round 2 ready. 2026-08-10

**Suite 82, FAILING: none.** Three files.

### NPB PARITY — CLOSED, and the answer is "there is nothing to show"

KBO's board carries `void_risk` — the league's own "Chance of Heat
Cancellation", published in advance on a game still ON. NPB's carried
nothing there, and **a missing badge is unreadable**: on one board it
meant "no risk", on the other "not measured", with nothing on screen
telling them apart.

Measured three times, most recently run 85313739682:

    157 dated rows | 109 upcoming | 0 cancel | zero risk vocabulary

across 中止 雨天 順延 延期 恐れ 見込み 予備日 微妙 流れ. npb.jp publishes
no advance warning of any kind.

**So the label says that**: `no rainout warning published`, on
`app/views/NPB.py`, gated to **scheduled AND open-air** games only —
under a roof the question is already answered by the roof badge, and two
hedges on one card read as more doubt than either deserves.

**WHAT IT DELIBERATELY DOES NOT SAY:** that NPB never calls a game off in
advance. The probe found ZERO cancelled games anywhere on the page, so
the forward-cancellation case had no opportunity to appear and remains
UNMEASURED. Claiming it would be the same overreach as the badge this
replaces. Re-run in the June rainy season to settle it.

### KBO ROUND 2 — `kbo_fragment_probe.py` (NEW) + its own workflow job

Round one established the game centre does NOT render starters
(`x8 raw, x0 rendered`) and handed over the endpoint its own script
calls. This one calls it.

**IT PARSES NOTHING, ON PURPOSE.** `S2iAjaxHtml` injects markup so the
response is an HTML fragment nobody has seen, and every wrong answer in
this whole sequence came from a probe that invented the structure it
parsed — v1 NPB split on a `<div class="date">` that does not exist, v1
KBO guessed three `.asmx` names (401/401/500), v2 KBO matched
`[가-힣]{2,4}` and returned ten Korean UI words as names. This prints the
raw fragment and lets a human decide what the container is. A parser
comes NEXT round, keyed on markup somebody has actually looked at.

**THE POST FIELD NAMES ARE ALSO UNKNOWN AND ARE NOT GUESSED.**
`setPreview` names nine values; the AJAX `data:` block is what maps them
onto fields. The probe prints that block VERBATIM *before* attempting any
call, because a 500 from wrong field names looks exactly like a 500 from
a dead endpoint — and last time that ambiguity was read as "no endpoint
found". The params it does send are labelled `FIRST GUESS`. It tries GET
and POST both, since a 405 from the wrong verb is also indistinguishable
from a dead route.

Verified offline: the game-id regex matches `20260811LGOB0` and the
call-block regex captures a realistic `S2iAjaxHtml({url:..., data:{...}})`
including its field names. **The live call is untested** — that is the
run.

Added as a SEPARATE workflow job (`kbo-fragment`), not bolted onto
`kbo-probables`: different questions, and one failing must not hide the
other's output.

### NEXT
1. **Actions → Open-question probes.** Read `kbo-fragment`'s RAW
   FRAGMENT section. If names are in there, round three writes the
   parser and mykbostats can go (AUP clause 6). If the body is empty,
   the CALL BLOCKS section holds the right field names.
2. **Tomorrow's 1 PM slate-picks** is the first with tier 2 —
   `grep -c proj_total data/mlb/games.json`, and the log ends
   `N with a projected total`.
3. `live_hits` is committed and unused. Viability check first: real
   denominators in the 40-70 range, or the floors refuse most states.

---

## PICK UP HERE — TIER 2 IS LIVE. 2026-08-10.

**Suite 82, FAILING: none.** The last dark piece of item C is wired.

### THE ANSWER, run 85313739682

```
standings regularSeason  200 | 30 entries | 30 w/stats | 30 w/runs
                             e.g. Rays: 519 runs in 117 G
TIER 2 BUILDABLE
```

**The `e.g.` line is what makes it a finding rather than a count.**
`teams/stats` printed `?: 591 runs in 119 G` — no team name, because
there wasn't one. That row is the LEAGUE AGGREGATE, and it looks like a
club until you notice the blank. It survived two rounds recorded as
"PARTIAL: 1 of 30". Standings gives a named club.

### WHAT SHIPPED

**`app/engines/mlb_run_rates.py` (NEW).** Turns one standings response
into `{"rs_pg", "ra_pg", "games"}` per club. Thin on purpose — three of
the four probe rounds went wrong in the PARSE, not the fetch, so
`parse_standings()` is pure and tested offline against a payload
matching the real shape.

**`calibration_picks._write_mlb_slate`** fetches once for all 30 clubs
BEFORE the per-game loop (inside it would be thirty requests a slate),
measures `league_rs_pg` from those same clubs, and writes `proj_total`.

**`run_total.project_total` is unchanged and is the SAME engine KBO and
NPB use.** `league_rs_pg` is a parameter it measures from whatever teams
it is handed, not a frozen constant, so MLB's run environment goes in
with no second copy of the maths. Verified end to end on a 30-club
payload: league 4.256 rs/pg, and totals of 10.1 (Rockies@Dodgers), 9.3
(WhiteSox@Yankees), 7.5 (Guardians@Mariners) — a sensible spread around
an MLB average.

**ERA IS NOT PASSED.** `run_total` shades a total by the starters' ERA
against the league's, and neither figure is on disk for MLB.
`starter_adjustment` returns 0.0 for a missing ERA, so this is the pure
team-rate projection — a real, smaller claim, and better than inventing
an ERA to make a bigger one. Adding starter ERA later would sharpen it.

### TWO WAYS A WRONG NUMBER REACHES THE FRONT PAGE, both refused

1. **A ZERO WHERE A MEASUREMENT IS MISSING.** A club with `runsScored`
   absent is unmeasured, not one that has scored no runs. A 0.00 rs_pg
   drags the league average down AND makes that club the worst offense
   in baseball — both invisible on a card. Such clubs are dropped.
2. **A PARTIAL LEAGUE.** 30 or nothing. With 22, eight games get no
   projected total, tier 2 fires on some and not others, and the ranking
   silently mixes two sorts — some games on three tiers, some on two,
   nothing on screen saying so. `fetch_team_run_rates` refuses and says
   why. The probe refused a partial for the same reason and was right to.

A standings outage returns a reason rather than raising: this runs
beside six pick builders and must cost tier 2, not the day's picks.

`tests/test_mlb_run_rates.py` (NEW, #82) — 20 assertions, 5 negative
controls (zero-for-missing, accept-a-partial, count-divisions,
outage-raises, fetch-inside-the-loop), all confirmed red.

### VERIFY, and this one is visible on the page
1. Next slate-picks run, the log line now ends `N with a projected
   total`. Expect it to equal the game count.
2. `grep -c proj_total data/mlb/games.json` — non-zero.
3. **Home's hero card.** With tier 1 tied (two games at edge_net 3 on
   08-10), tier 2 now breaks that tie, and `why_first` may say "Highest
   projected run total on the slate" where it used to fall to the
   alphabetical tiebreak.

### STILL OPEN
- **KBO fragment probe.** `/Schedule/GameCenter/Preview/StartPitcher.aspx`
  confirmed at 11:35 KST. `S2iAjaxHtml` injects markup, so these return
  **HTML FRAGMENTS, NOT JSON** — the next probe fetches with a live
  gameId and dumps ~2KB RAW, unparsed. Guessing structure is what made
  v1 and v2 wrong. This is the last thing before dropping mykbostats.
- **NPB label still not in the repo.** `grep -c "NO ADVANCE"
  app/views/NPB.py` returns 0. The verdict is earned and reproduces
  cleanly (157 rows, 109 upcoming, zero risk vocabulary).

---

## PICK UP HERE — 2026-08-10. KBO UNBLOCKED. MLB probe was under-reporting.

**Suite 81, FAILING: none.**

### KBO — THE ENDPOINT, AT LAST. Run 85311921317.

```
'선발' x8 raw, x0 in RENDERED content | 19 script blocks
THE PAGE'S OWN AJAX CALL (verbatim from its <script>):
  url: /Schedule/GameCenter/Preview/StartPitcher.aspx
  url: /Schedule/GameCenter/Preview/LineUp.aspx        (+6 more)
  setPreview(section, leId, srId, seasonId, gameId, awayTeam, homeTeam, awayPit, homePit)
```

**`/Schedule/GameCenter/Preview/StartPitcher.aspx`** — named
unambiguously, pulled verbatim from the page's own script, at **11:21
KST** so the "starters not posted yet" caveat does not apply.

**These return HTML FRAGMENTS, not JSON.** `S2iAjaxHtml` injects markup.
Whatever comes back is a page to parse, not a payload to read — which
shapes the next probe: fetch it with a real `gameId` and **dump the raw
fragment unparsed**. Do not guess its structure; guessing the structure
is what made v1 and v2 both wrong.

This is the last thing between here and dropping mykbostats (AUP clause
6 forbids using their content for betting).

### MLB — THE PROBE WAS WRONG, NOT THE API. Run 85312622391.

```
standings regularSeason  200 | 30 entries | 30 w/stats | 0 w/runs
```

Thirty entries. Thirty carrying `runsScored`. **Zero counted.** The
verdict then ranked shapes by `w/runs`, picked `teams/stats hitting` with
its ONE league-aggregate row, and reported *"tier 2 stays dark"* —
declaring tier 2 unbuildable off a payload holding all thirty clubs.

**Cause: two places extracted entries and only one learned the new
shape.** `_diagnose` was taught the standings nesting
(`records[].teamRecords[]`); `main()` kept its own copy keyed on the
top-level lists, which are empty for standings. Diagnostic saw thirty,
counter saw none, in the same row of the same line.

Third time this repo has been bitten by a computed thing and a rendered
thing disagreeing because they were derived separately — and the worst
version yet, because it produced a **confident negative about an endpoint
that works.** "Tier 2 is not buildable" is exactly the kind of finding
that gets written down and closes an avenue for months.

`_entries()` is now the single extractor and both callers go through it.
Verified offline: 30 entries / 30 w/stats / **30 w/runs**, verdict flips
to TIER 2 BUILDABLE.

**A third copy was still hiding in `_diagnose`'s fallback branch and the
new test found it, not me.** That is the assertion earning its place on
its first run.

`tests/test_mlb_rsra_probe.py` (NEW, #81) pins that exactly one place
extracts entries, that the diagnostic and counter agree, and that
`teams/stats` and hydrate still parse. Four negative controls, all red.

### NEXT
1. **Re-run the MLB probe.** Expect `30 entries | 30 w/stats | 30
   w/runs` and TIER 2 BUILDABLE. If so, write RS/RA into the slate and
   let `run_total` compute `proj_total` — the ranking is already wired
   and tested for it.
2. **Write the KBO fragment probe** — fetch StartPitcher.aspx with a live
   gameId, dump ~2KB raw.
3. **NPB reproduces cleanly** (157 rows, 109 upcoming, zero risk
   vocabulary; score-tag gap 153 vs 47-with-digits confirms the
   played-check fix holds). The label is still NOT in the repo —
   `grep -c "NO ADVANCE" app/views/NPB.py` returns 0.

---

## PICK UP HERE — MLB standings shape added to the probe. 2026-08-10

**One file. Suite 80, FAILING: none.** Not a finding — an instrument.
Run it and read the diagnostics.

### WHY

Every `teams/stats` shape returns ONE entry, and that entry is the
LEAGUE AGGREGATE (591 runs in 118 G), not a club. That is not "statsapi
lacks per-team runs" — it is that endpoint answering a league-level
question. The probe correctly refused to call it a finding.

Standings answers the right question: each `teamRecord` carries
`runsScored` and `runsAllowed` for THAT club, and `leagueId=103,104`
covers all 30 in one call. That is exactly what tier 2 of the best-games
ranking needs and has never had.

**STILL A HYPOTHESIS. Nobody has called this endpoint.**

### TWO WAYS IT WOULD HAVE SILENTLY MISREPORTED, both fixed first

Adding the url alone would not have worked, and both failures look like
"the endpoint is broken" rather than "the probe is wrong" — the exact
pattern that has now burned this repo three times.

1. **`_diagnose` counted the wrong level.** Standings nests one deeper:
   entries live under `records[].teamRecords[]`, not a top-level `teams`
   or `stats` list. Counting `records` alone reports **6** (the
   divisions) for a payload holding all 30 clubs — and 6-of-30 reads
   exactly like the partial failure this probe already refused once.
2. **`_walk_for_runs` looked only for `runs`.** Standings spells it
   `runsScored` / `runsAllowed`. The walker would have traversed a
   perfect payload, found nothing, and reported 0 with runs — the
   endpoint working and the probe calling it empty.

Verified offline against payloads matching each API's documented shape:
`teams/stats` -> 1 entry / (591, 118); a 3-club standings stub -> 3
entries across 2 division records; a full 6-division stub -> **30
entries, 30 with runs, verdict flips to TIER 2 BUILDABLE**.

### READ IT LIKE THIS

- `entries 30 | 30 w/runs` -> tier 2 is buildable. Next is writing RS/RA
  into the slate and letting `run_total` compute `proj_total`; the
  ranking is already wired and tested for it.
- `entries 30 | 0 w/runs` -> the query is wrong, not the API. Docs, not
  a new source.
- `entries 6` -> the nesting fix did not land.

### The KBO probe on the same run
Should now exit 0 and print `THE PAGE'S OWN AJAX CALL` with the url and
the `setPreview(... awayPit, homePit)` signature. **That url is the next
real step** — call it with a live gameId. If it prints `NONE FOUND`, the
script changed shape: dump it and read it. Do NOT guess a url; v1
guessed three `.asmx` names and got 401/401/500.

---

## PICK UP HERE — live hits props, engine only. 2026-08-10

**Suite 80 files, FAILING: none.** New engine + test. **NOTHING RENDERS
YET** — this is deliberately engine-first, headless and testable, before
a view touches it.

### WHAT IT ANSWERS

"He's 1-for-2 and I want 2+ hits — what are my chances?"
`conditional_rate(df, hits_so_far=1, pa_so_far=2, line=2)`

An EMPIRICAL CONDITIONAL FREQUENCY: his real games that reached the same
state, and how many finished at or above the line. Numerator and
denominator both real, both returned.

**NOT a model.** "He needs one more hit in two likely at-bats, his rate
is .270, assume a binomial" produces a confident number from an
assumption nobody can check. PAs are not independent draws — the pitcher
changes, the order turns over, a blowout empties the bench. All of that
is inside the real games; none of it is inside a binomial.

### PINCH HITS — HANDLED BY DOING NOTHING, AND THAT IS THE POINT

A game where he was lifted after 2 PAs with 1 hit FINISHED with 1 hit.
It lands in the denominator, not the numerator, and correctly counts as
a loss. No substitution detection needed.

**The failure mode is the opposite: someone "cleaning" the short games
out.** Measured at a 12% removal rate — keeping them **42.3%**, dropping
them **48.8%**. Six and a half points of pure optimism, biased exactly
the way that costs the bettor, and invisible on screen.

**DO NOT add a minimum-PA filter to `_game_states`.** A game that ended
early is a result, not a defect. `removal_rate()` reports removals
separately, which is the honest place for it.

### THE BULLPEN — BESIDE THE NUMBER, NEVER BLENDED IN

The base rate ALREADY covers bullpens structurally: in every historical
game where he was 1-for-2, his later ABs also came against relievers.
Late pen exposure is the normal shape of a game and is baked in.

What it cannot see is THIS pen. Adjusting for that needs a weight — how
many points is a B-grade pen worth? — which would be invented and then
hidden inside one number. Same argument as the best-games strict tiers.
The caller shows pen quality alongside, with its own label and window,
from the Bullpen Board data that already exists.

### WINDOWS — ONE, STATED, NOT MIXED

| quantity | window |
|---|---|
| conditional frequency | the batter pull's span (season; `DEFAULT_START_DATE`) |
| pen quality | Bullpen Board's own — shown beside, never folded in |
| batter recent form | **NOT USED, deliberately** |

Conditioning on state already cuts ~150 games to ~60. Adding "and he's
hot" takes it to ~15 — trading a real measurement for a noisier one to
chase a signal unverifiable at that size. If form is wanted later, show
BOTH numbers with BOTH denominators. Do not merge them.

### SAMPLE FLOORS, and the arithmetic behind them

`MIN_SHOW = 25` (no percentage below it), `MIN_TRUST = 50`. A .270 hitter
over 150 games reaches 0-for-2 ~80 times and 1-for-2 ~59 — comfortable.
But 2-for-2 happens ~11 times and 3-for-3 about 3. The count is ALWAYS
returned even when the rate is not: "6 of 11" is useful, "55%" off 11
games is not.

Interval is **Wilson, not the normal approximation** — the normal one
returns 33%-117% at 3-of-4, and a band claiming more than certainty is
worse than no band because it looks like arithmetic. Control 5 proves it.

### Six negative controls, all confirmed red
filter short games (the big one) · treat the state as "at least" · read
`line` as remaining · drop the floor · normal approximation · fold
removal into the rate.

### NEXT, and read this before building the view

1. **It is unproven and must say so on screen** until graded. This is the
   first number on the site a person acts on WITHIN SECONDS with money
   already down — every other board is published pregame and graded
   after. Log the state at query time `(batter, hits, PAs, line, ts)` into
   the calibration record from day one and show its hit rate against the
   league baseline like every other board.
2. `DEFAULT_START_DATE` caps this at ONE SEASON, ~150 games. Widening to
   two doubles every denominator but mixes a player who may have changed.
   A real trade — make it deliberately, do not inherit it.
3. WNBA points (the 11-at-halftime case) is **NOT buildable**:
   `parse_boxscore` stores final lines only, no period splits anywhere.
   ESPN exposes them; that is a new fetch, new storage, new nightly cost.
   Probe first.

---

## PICK UP HERE — 2026-08-10, KBO probe filter

**Suite 79 files, FAILING: none.** One file changed, one added.

### THE KBO PROBE COULD NOT HAVE ANSWERED ITS OWN QUESTION

v2 reported *"NAMES ARE ON THE PAGE: 10 candidates near starter markers,
server-rendered, no XHR. The KBO migration is unblocked."* It was not.
The ten were:

    기록이 됩니다 등록 라인업 선택 업데이트 전력 전력분석 전력비교 키플레이

"is recorded", "will be", "register", "lineup", "select", "update",
"power", "power analysis", "power comparison", "key play". UI vocabulary,
every one. **Two independent causes, both now fixed.**

**1. THE CORPUS.** The probe counted 선발 in RAW html, so eight
occurrences inside a `setPreview()` function and a **commented-out alert
string** were read as a server-rendered table. A commented-out alert is
not even executed. It now strips `<script>`/`<style>` and prints BOTH
counts, because the gap is the finding: raw high + rendered zero means
the page references starters and fetches them over AJAX — a completely
different next step from "parse the table".

**2. THE FILTER.** `[가-힣]{2,4}` plus a hand-written stoplist. A
stoplist cannot win: it needs the word foreseen, and rendered content has
its own nav labels and headers, so the same false positive would return
from a different corpus. Now structural — **exactly three syllables, and
the first is a common Korean surname.** Korean names are overwhelmingly
surname + two-syllable given name; surnames are a small closed set.

Syllable count must come first: 전 is a genuine surname, so 전력 and
전력분석 sail through a surname check alone.

**Precision over recall, deliberately.** Rare two- and four-syllable
names are dropped. For a probe that is the right trade — a missed name
understates, an invented one misdirects and cost a session here.

**MY FIRST VERSION LEAKED and I only caught it by testing against the
actual ten.** 기록이 passed: 기 IS a surname, and the word is a noun plus
a subject particle. The rare surname tail (기 반 왕 금 옥 육 맹 제 모 탁
국 어 은 편 용) is all genuine surnames AND common noun syllables — it
buys almost no recall and costs precision on every noun starting with
one. Dropped. Result: **0/10 UI words accepted, 11/11 real KBO pitcher
names caught.**

**It is still a heuristic.** 이용자 ("user") is three syllables starting
with the commonest surname in Korea; no syllable rule separates that from
a person. That is why the probe now prints the ACCEPTED names *and* the
REJECTS, and why the verdict says to check them against tonight's actual
probables. A count can be wrong in silence; a list cannot.

### `tests/test_kbo_name_filter.py` (NEW, #79)

Pins the exact ten verbatim, asserts real names still pass (a filter
rejecting everything would satisfy the first half alone), and asserts the
DATA FLOW rather than the presence of a line.

**That last part was a bug in my own test.** It first checked only that a
`re.sub(r"<script` call existed somewhere. Setting `rendered = html` on
the line above left that call in place doing nothing and the assertion
stayed green — the same failure as rule 26, where an assertion matched a
workflow's comment instead of its command. It now walks the AST: every
`rendered` assignment must be a Call, and nothing may slice raw `html`
afterwards. Six negative controls, all confirmed red.

### NOT DONE, and needs your other session

**The NPB label is NOT in this repo.** `grep -c "NO ADVANCE" app/views/NPB.py`
returns 0. A version of it existed in my workspace — well written, citing
run 85245341493 and correctly distinguishing "no forward WARNING"
(measured: 109 upcoming games, zero risk vocabulary) from "never cancels
in advance" (NOT measured: zero `<div class="cancel">` anywhere on the
page, so the case had no chance to appear). It was never committed. Find
it in that session or re-write it — do NOT let the two of you write it
twice.

### RUN 85252013581 — the KBO fix landed and REVERSED a recorded finding

```
STRUCTURE: 57178b | '선발' x8 raw, x0 in RENDERED content | 19 script blocks
ALL starter vocabulary is inside <script>
```

**The game centre does not serve starters server-side.** Retracted at
its source below (search RETRACTED). The other two probes reproduced
exactly: NPB `157 rows | 109 upcoming | 0 risk vocabulary`, MLB still
`1 club with runs, not 30` (the league aggregate, 591 runs in 118 G).

**And the run exposed a second bug, in the probe's own exit path.** It
printed *"NO STARTER VOCABULARY AT ALL ... re-run mid-afternoon KST"*
and `exit 1`. Both halves wrong: the vocabulary was there eight times,
and timing cannot move JavaScript into the DOM. Worse, exiting
suppressed the AJAX url — the one genuinely useful thing the run could
produce.

Fixed by splitting the two zeros, which are different questions:

| condition | meaning | action |
|---|---|---|
| `n_raw == 0` | genuinely absent | timing IS a real explanation — re-run |
| `n_raw > 0, rendered == 0` | referenced in script | NOT a failure. Print the endpoint, exit 0 |

The referenced-not-rendered branch now extracts `S2iAjaxHtml({url: ...})`
and the `setPreview(... awayPit, homePit)` signature **from the script
text** — `rendered` is empty by definition there, so extracting from it
would always find nothing and look like the endpoint had vanished. If no
url matches it says so rather than guessing; v1 guessed three `.asmx`
names and got 401/401/500.

Verified offline against markup matching the logged shape: the url
`/Schedule/GameCenter/StartPitcher.aspx` and the setPreview signature
both extract correctly. Three more negative controls on top of the six
already on the name filter.

### Still open
- **Tier 2 (`proj_total`)** — MLB probe correctly refused to half-fire:
  the one entry with runs is the LEAGUE AGGREGATE (591 runs in 118 G),
  not a club. Standings endpoint is the untested lead.
- **KBO AJAX** — `setPreview(... awayPit, homePit)` and
  `S2iAjaxHtml({url: "/Schedule/GameCenter..."})` are in the CONTEXT
  output. Extract the URL verbatim and call it with a real gameId. Do not
  guess `.asmx` names again — v1 did and got 401/401/500.

---

## PICK UP HERE — state as of 2026-08-10 (evening)

Perf audit + correctness sweep on the shipped item C. **Suite 77 files**
(one new). Everything below was MEASURED, not inferred.

### PERFORMANCE — no action needed, and here are the numbers

Benchmarked against real data with a cache shim standing in for
streamlit, so these reflect what the app does including cache hits:

| path | cold | warm |
|---|---|---|
| calibration record (162 KB) | 5.82 ms | **0.07 ms** |
| `summary()` | — | 0.09 ms |
| `load_slate("mlb")` | — | 0.08 ms |
| `rank_games()` over 10 real games | — | 0.03 ms |

One Home paint = **10 file reads, 0.6 ms**. `_load_cached(stamp)` is
earning its keep at 83x on the record.

- **`slate_guard` has no caching and reads two paths per call. Checked
  before flagging: 0.08 ms. Leave it.** A cache there would need the same
  mtime-stamp treatment or it would serve a stale slate.
- **Growth is the only thing to watch.** 158 KB over 15 days = 10.6
  KB/day, ~1.9 MB by season end. The cold merge is linear, so ~70 ms
  cold at 2 MB. Not urgent; know it before it surprises you.
- Cold start ~500 ms, essentially all pandas/requests/bs4 pulled through
  `statcast_engine`. Per PROCESS, not per request. Not worth restructuring.

### THREE REAL BUGS, all found by looking at the produced file

The 2026-08-10 slate looked complete — 10 games, both starters, 8 edges.
It was not. **Read the artifact your pipeline writes, not just its exit
code.**

**1. Weather was null on all ten games.** `weather_temp`, `weather_wind`,
`weather_condition` — zero of ten. `wind_adj` was 0 on every game (one
distinct value in the whole file). MLB does not post park weather until
close to first pitch, and slate-picks' FIRST and most important run is
1 PM ET, six hours early.

GameCard has done the right thing all along — its "in-house weather
desk" falls back to the National Weather Service and its own comment
says MLB posts late and it fills the gap "most of the day".
`_write_mlb_slate` never asked. **Two parts of one app disagreeing about
the weather for one game — rule 21, and the slate was the wrong side.**

Fixed: NWS fallback (roofed parks skipped, as Weather_Board does),
`weather_source` recorded so a forecast is never mistaken for an
observation, and the temperature now feeds `grade_matchup` so the
>=80F/<=65F O/U signals can fire on the 1 PM build at all.

**2. TWO WIND ENGINES, and the slate called the one that can't read
MLB's format.** `wind_engine.wind_hr_adj` handles compass
("12 mph SW", what NWS gives). `player_of_the_day._wind_hr_adj` handles
field-relative ("8 mph Out To CF", MLB's own). `_parse_wind` returns None
for field-relative ON PURPOSE — its docstring says so and names the other
function. So on the 5 and 7 PM runs, where MLB HAS posted a wind, the
slate wrote `wind_adj` 0 and `wind_note` None. Silently. Measured:

    "8 mph Out To CF"   -> (0, None)      "15 mph In From CF" -> (0, None)

Fixed with a router: field-relative first (it states which way the ball
carries), compass as fallback. Not merged into one function — they answer
with different confidence from different inputs. **`tests/test_mlb_slate_wind.py`
(NEW, #77)** asserts both engines are CALLED, not merely imported; two
negative controls confirm it catches the revert.

**3. `why_first` said "weather and park swing" having read no weather.**
Consequence of 1 and 2: the swing was real but came from the park factor
alone. A wrong number is catchable; **a right number under a wrong label
is not.** `_swing()` now returns which signals it measured and the label
names only those.

### Also fixed
- **`edge_signals` were published and read by nothing.** The file holds
  `"WHIP: edge Boston Red Sox (1.28 vs 1.55)"`; the card showed a bare
  letter. Rule 20, on the one page whose claim is "here is where the
  model has an opinion" — the reasoning IS the product. `edge_reasons()`
  now renders the lead game's signals.
- **NPB probe's played-check was wrong, and it is why v2's verdict was
  absurd.** Production requires DIGITS inside `<div class="score1">`;
  the probe tested for the tag's PRESENCE. Scheduled games carry an empty
  placeholder, so 154 of 157 future rows were discarded as played —
  that is the "3 upcoming" number. Now uses production's regex, and
  STRUCTURE prints both counts so the gap is visible. **Copying a
  selector is not copying a parser.**

### Two handoff items were stale
- `wnba-lineup-probe.yml` is ALREADY gone from the root.
- The admin-credential check cannot work as written: `auth_config.yaml`
  is gitignored and lives on Render's disk, so it never appears in a zip
  or a fresh clone. **It has to be checked on Render**, not from the repo.

### PITCHER SPLITS WINDOW — new, his request

The Game Card's STATS / STRIKES tables were **season only**, on a page
whose whole job is tonight's matchup. A starter's season line can be four
months old, and every other window control in the app — the grade window
ten lines above it, the lineup filter, Bullpen Board, Player of the Day
— already offered one.

Now: **Season / L10 / L5 / L3 / Last game**. Nothing estimated —
`get_pitcher_advanced_splits` slices raw Statcast rows through
`recency_windows` BEFORE any metric is computed, so IP, the games count
and every rate are honest for the window.

`l3` and `l1` are new keys in `recency_windows`, the ONE shared
definition — not a second map in the view.

**THE SAMPLE PROBLEM, and what was done about it.** `Last game` is about
25 batters faced. A .400 BA against on one night renders in the same
column, font and colour scale as a .240 over 700. statcast_engine already
carried a long comment about the empty-split case rendering "BA .000,
SLG .000, WHIP 0.00" — a line describing the most dominant pitcher who
ever lived — whose stated reason was that **"the table has no sample
column to contradict it."**

Three things fix that and are pinned by
`tests/test_pitcher_splits_window.py` (NEW, #78):

- **`G` (games) is now a column in BOTH tables**, second, right after
  Split — a denominator read after the number it qualifies has already
  done its damage. STRIKES had no IP either, so it previously had no
  sample at all.
- **`G` is never colour-ranked.** It is a sample size; shading it would
  claim more games is better or worse.
- **`THIN_WINDOWS` lives in `recency_windows`**, beside the slicing, so
  the warn-list cannot drift from the window list. A thin window prints
  a small-sample line above the table naming the actual game count, and
  calls out the platoon rows separately — a starter can face three
  lefties in a game, and "vs LHB" over three at-bats is an anecdote.

Also removed: `splits_vs_r` / `splits_vs_l`, the old season-only fetches.
The Matchup table was their only consumer and it now fetches per window,
so leaving them would have been two cached calls nothing read — rule 20,
in the same batch that fixed another instance of it.

**Six negative controls, all confirmed red:** drop G from STRIKES, offer
a window `apply_window` doesn't implement, wire the control to nothing,
remove the warning, colour-rank G, make `l1` slice to zero.

`_games` was also added to the `empty` return of
`get_pitcher_advanced_splits` — the populated path always had it, so a
caller reading the sample got a KeyError on exactly the case where the
sample matters most.

### Verify
1. `git pull`, run the suite. **78 files, FAILING: none.**
2. **After the next slate-picks run**, read the log line — it now ends
   `N weather from NWS forecast`. On the 1 PM run that number should be
   close to the open-air game count. If it is 0, the NWS fallback is not
   firing and tier 3 is back to park-only.
3. `grep -c nws_forecast data/mlb/games.json` — non-zero on a 1 PM build.
4. **The ranked card still has never been seen.** Three games, one line
   naming the tier the sort used, now with the lead game's actual
   signals beneath it.

---

## PICK UP HERE — state as of 2026-08-10 (afternoon)

**Everything below this block is still accurate. This is the delta.**

### The red test was the test's own bug, not a leaked fixture

`tests/test_slate_guard.py` was the only failing test. FIX-THIS-NEXT.md
ranked "a stale fixture on disk" first; **it was wrong, and the way it
was wrong is the interesting part.**

`staleness_note()` for MLB reads BOTH locations and keeps whichever
declares the later slate date — `app/data/mlb/games.json` (which the
test stubbed) and repo-root `data/mlb/games.json` (which it did not
touch at all). That second path was empty for months, so the omission
was invisible. The moment `calibration_picks` wrote a REAL dated slate
there, that file out-dated every fixture the test wrote, every MLB case
returned `ok=True`, and `staleness_note` returned `''` for all five.

**The test was defeated by the feature it was written to protect.** The
five assertions were fine; they were never reached. Fixed by backing up,
blanking and restoring the repo-root path too — the same
backup/blank/restore the other three leagues already had. Verified with
a real dated slate in place, and the real file is byte-identical
afterwards.

Generalises, and it is now rule 27: **a test that stubs a path must stub
every path the code under test reads.** `_read()` deliberately reads two
locations; a fixture covering one of them is a fixture covering none.

### Item C's before-1PM state is CONFIRMED LIVE

Screenshot at 11:02 ET: "Tonight's MLB slate builds around 1 PM ET, once
MLB posts probable starters." Framed section, hairline rule, no false
alarm. Verify-list step 2 is closed. **Step 3 — the ranked card itself —
is still unseen**, and needs a look after a same-day `slate-picks` run.

### Decisions taken, so nobody re-opens them

- **Dome flags stay in `intl_venues.py`. CLOSED, decided against.**
  Moving them to published data would break the "unknown ≠ open"
  guarantee that `roof()` exists to provide: a fetch failure or partial
  write would silently return `None` for every venue, where source code
  cannot fail to load. It also makes a fallback depend on the network
  that its caller already fell back FROM. And it buys nothing — 12 NPB
  venues and 11 KBO patterns that change about once a decade are a
  constant, not data. Same reasoning as `park_factors.py`. **Do not
  re-propose this as a cold-start fix.**
- **WNBA Volume now carries season AND L5, paired.** Not a swap. A bare
  "FTA L5" of 6 is unreadable — the reader cannot tell a player who
  always draws six from one whose attempts just doubled, and the
  doubling is the only reason to open the tab. The pair is the signal.
  L10 deliberately not added: six columns for two stats on a tab already
  carrying ten, read on an iPad, and L10 sits between two numbers the
  reader already has.
  **Stocks stays season-only on purpose** — the precompute windows the
  COMBINED `stocks` figure but not `stl`/`blk` separately, so there is no
  `l5_stl` to show, and deriving one from the combined number would put a
  label on a quantity that isn't what it says. Rule 21 cuts the other
  way here: the asymmetry is honest because the data is asymmetric.
- **mykbostats is going, not staying.** Clause 6 forbids betting use.
  This is no longer "unexamined" — it is decided. See E3 below; the only
  thing standing between here and dropping it is probables.

### Three probes delivered, NONE of them run yet

All three write nothing, commit nothing, and print a verdict line. **Run
them before building anything on top of what they ask about** — rule 22
exists because this repo has shipped correct, tested code with no
working source behind it.

**FIRST RUN 08-10, run 85209788549 — two probes were WRONG and were
rewritten. Read this before trusting any verdict from them.**

- **KBO: ~~a real finding~~ — WRONG, AND RETRACTED 2026-08-10. See the
  block at the top of this file.** This said
  `Schedule/GameCenter/Main.aspx` is "server-rendered and already
  contains 선발 투수" and that the client-side premise was false for that
  page. **It is not server-rendered.** Run 85252013581, with the probe
  finally separating script from content, measured
  `'선발' x8 raw, x0 in RENDERED content | 19 script blocks`. All eight
  live inside a `setPreview()` function and a **commented-out alert
  string** — the page TALKS ABOUT starters and fetches them over AJAX
  after load. A commented-out alert is not even executed.

  **Three runs recorded this as an unblock and it never was.** v1 read
  raw html, v2 read raw html and added a stoplist filter that passed ten
  Korean UI words as names. The original premise in this file — KBO
  probables are client-side — was RIGHT all along, for the game centre
  too. Do not re-derive the retraction; it cost three runs.

  The `.asmx` guesses returned 401/401/500 and must not be retried:
  guessing is what produced them. The real next step is the endpoint the
  page itself calls, which the probe now prints verbatim from its script
  rather than exiting before it gets there.
- **NPB: the probe was wrong, not the site.** v1 split on
  `<div class="date">`, which does not exist on that page, found zero
  dated blocks, and reported "no forward-looking warnings" — a verdict
  it had never measured. `npb_precompute.parse_games()` has parsed this
  exact page in production for months using `<tr id="dateMMDD">`. v2
  uses its selectors verbatim and prints a STRUCTURE line first; if that
  says zero rows, the NPB build is already broken and nothing after it
  is an answer.
- **MLB: verdict NOT earned, do not record it.** v1 tried one hydrate
  shape, got 0/30 and printed "NOT BUILDABLE HERE". **Zero out of thirty
  is the signature of a malformed query, not a missing field**, and v1
  could not tell those apart because it never checked whether any stats
  block came back. v2 tries four documented shapes and prints entries /
  w-stats / w-runs per shape. **Tier 2 is not closed.**

The generalisation, and it is the same one as rule 27: **a probe that
invents the structure it parses can manufacture either answer.** When
the pipeline already parses a page, the probe reads it the same way — a
second parser is a second thing to be wrong. Two of three v1 probes
guessed; both guessed wrong; one of them would have shipped a label
asserting something never checked.

| script | answers | if the answer is "no" |
|---|---|---|
| `npb_void_probe.py` | does npb.jp publish a forward-looking cancellation warning like KBO's? | ship a LABEL saying NPB publishes none, not an invented badge. That still closes the parity gap — rule 21 is about the reader being able to tell, not about both boards having the same badge |
| `mlb_rsra_probe.py` | can tier 2 (`proj_total`) be built from team RS/RA on statsapi, which we already depend on? | tier 2 stays dark. **Still do not substitute the O/U signal count** — it counts signals toward Over and is not a number of runs |
| `kbo_probables_probe.py` | is there a direct endpoint for KBO probables, which the rendered page draws client-side? | ship KBO without probables and label the board, rather than keeping a source clause 6 forbids |

`kbo_probables_probe` prints the `.asmx`/`.ashx` URLs the schedule page
itself references. **If the guessed endpoints 404, that list is the real
output** — it is ground truth and the guesses are not.

All three must run from **Actions**, not a Codespace: Korean and
Japanese sites geo-fence and rate-limit by region, and ESPN already
taught this repo that an IP-range result from a laptop predicts nothing.

`.github/workflows/open-question-probes.yml` runs all three on manual
dispatch — Actions tab, "Open-question probes", Run workflow. Three
SEPARATE jobs on purpose: they answer unrelated questions, and as
sequential steps a Japanese site being down would hide the MLB answer.
**Record what each verdict said in this file**, including a "cannot be
built" — that closes an item just as well as a yes, and an unrecorded
probe result means somebody runs it again in three weeks.

### Suite

**76 files** (was 75; `tests/test_wnba_context_windows.py` is new).
Same five streamlit-only failures in a bare container, green in the
Codespace.

`test_wnba_context_windows` asserts the PROPERTY, not the columns: for
every context column, the window named in the header and the window of
the key behind it must agree, and no recent-form column ships without
its season baseline. Rename or drop a column and it stays quiet; feed
"FTA L5" the season key and it goes red. **Three negative controls
confirmed red** — label/key mismatch, orphaned L5 with no baseline, and
a windowed key with the window stripped from its header.

---

## PICK UP HERE — state as of 2026-08-10

**Item C is LIVE and its CI half has really executed.** First real run of
`calibration_picks._write_mlb_slate()` produced:

```
2026-08-09 | 15 games | 14 with an edge
```

Tier 1 of the ranking is alive on a real slate — `grade_matchup`
resolved both starters' splits on 14 of 15 games. That was the single
biggest unknown in the whole item and it is closed. Suite in the
Codespace: **76 files, FAILING: none.** (My container shows 5 failing;
they are the streamlit-only ones documented below and are expected.)

**Still never seen: the ranked card itself.** Every load so far has hit
a degrade path, because the slate is only current on the ET day it was
built. First sighting will be after a `slate-picks` run, on that same
day.

### Two Home defects found by looking at the live page, both now fixed

Neither was in the item. Both showed up only once real screenshots
existed, which is the argument for looking at the page rather than the
suite.

**1. THE THIRTEEN-HOUR DEAD ZONE.** slate-picks runs at 1, 5 and 7 PM ET
because probables don't exist before midday. So from midnight to 1 PM —
over half of every day — there is legitimately no MLB slate for today,
and Home's top card was saying *"the slate-picks job hasn't published
since"*: the sentence for a broken workflow, fired daily at a workflow
that is fine, pointing whoever read it at something green.

Same mistake this repo already made once, with the WNBA warning that
said "the nightly fetch may be failing" through the All-Star break. The
rule left behind: **a confident wrong diagnosis is worse than no
message.**

`slate_guard._not_built_yet()` now separates *not due yet* from *broken*.
It is deliberately narrow and fires only when all three hold: the league
has a known build hour (`_FIRST_BUILD_HOUR`, **MLB alone** — the absence
of the other three is the mechanism, not an oversight); that hour hasn't
come round yet in the league's own timezone; and what's on disk is
either nothing or **exactly yesterday's** slate. That last clause is
what stops this becoming "mute the warning when it's inconvenient" — a
three-day-old slate is a real outage at any hour and keeps shouting.

`_FIRST_BUILD_HOUR["mlb"] = 13` duplicates slate-picks' first cron
(`0 17 * * *` UTC). The duplication is deliberate — reading a workflow
file at request time to render a sentence would be worse — and
`test_slate_guard` now **pins the constant to the cron** and fails if
either moves without the other. A known one-hour hole under EST is
written down in the constant's comment rather than left to be
discovered.

**2. THE EMPTY STATE WASN'T A CARD.** The no-slate branch was
`st.caption(note)` — loose grey text floating above the chip rail with
no frame, at the top of the landing page. Honest words in a presentation
that reads as "something failed to load", and it's the state a reader
sees for most of the day. It's a proper card now, matching "Today's
board isn't published yet" further down the same page. No "build it
live" button, unlike that card: rule 5, Home makes zero network calls.

### Five negative controls, all confirmed red

After two tests shipped last session that passed without proving
anything (rules 25 and 26), every case here was verified by breaking the
code on purpose:

| mutation | caught by |
|---|---|
| give the other leagues a build hour | kbo/npb/wnba each get MLB's message |
| drop the "exactly yesterday" guard | 3-day-old slate stops being a fault |
| drop the hour check | 15:00 gets the gentle message |
| revert the branch entirely | 06:00 gets the outage message |
| move the cron, not the constant | the cron/constant pin |

One note on method: the first mutation initially failed via a `KeyError`
crash in an unrelated earlier test rather than via its own assertion —
an artifact of an inconsistent mutation, not a weak test. Re-run in the
realistic shape (all four leagues given an hour) it fails on the three
intended assertions by name.

### Verify, in order

1. `git pull`, run the suite. **76 files, FAILING: none** in the
   Codespace.
2. Load Home **before 1 PM ET** → "Tonight's MLB slate builds around
   1 PM ET…", inside a card, not floating.
3. Load Home **after a slate-picks run, same ET day** → the ranked card.
   **Nobody has seen this yet.** Check three games, a one-line reason
   above them naming the tier the sort used, and the lead game genuinely
   holding the biggest `edge_net` in `data/mlb/games.json`.
4. KBO and NPB chips unchanged.

---

## PICK UP HERE — state as of 2026-08-09

**Everything below the NEXT "PICK UP HERE" is background from 08-07 and
is still accurate. This block is what changed today.**

### ITEM C IS BUILT. It has never executed. Read the next paragraph.

The best-games hero card is shipped, tested and wired end to end, and
**not one line of the CI half has run in production.** Rule 22 exists
because of exactly this: `parse_homepage_schedule()` was correct and
tested and had no caller, and KBO died every run while 66 tests stayed
green. `_write_mlb_slate()` is a new function whose first real execution
will be a scheduled job. Read the slate-picks log before believing it.

**The near-miss, recorded because it is the same bug twice.** The slate
was first written to repo-root `data/mlb/` while `slate_guard` read only
`app/data/`. That is a green run, a log line saying the file was
written, and a card that never sees it. Worse: `app/data/` is
GITIGNORED and only arrives via the nightly release archive, and
slate-picks publishes no archive — so writing there would have left the
file on the Actions runner to die with the job.

The repo had already solved this and I nearly missed it.
`engines/calibration._repo_path()` documents the identical split:
Render checks out the whole repository, so repo-root `data/` resolves in
production, and `app/` is the service root, not the checkout root.
`slate_guard._read` now reads BOTH locations and prefers whichever
declares the later slate date — not first-wins, because on the day both
exist first-wins would pin the app to whichever path was checked first
and the staleness would be invisible.

### The pieces

- **`app/engines/best_games.py` (NEW).** The ranking, and nothing else.
  No streamlit, no network, no file reads — which is the whole reason it
  is an engine and not code inside the view: it can be tested headlessly.
- **`slate_guard`** gains `mlb` (Eastern; an MLB schedule day IS an
  Eastern day) and the two-location read above.
- **`calibration_picks._write_mlb_slate()`** runs FIRST in `main()`,
  before the pick builders, in its own try. A slate failure must not cost
  the picks and a pick failure must not cost the slate. Every number it
  writes comes from an engine the site already uses — weather_engine for
  the schedule, matchup_grades for the edge, park_factors, wind_engine.
  There is no second copy of any ranking logic.
- **`Home._render_best_games()`** at the very top of `render()`.
- **`tests/test_best_games.py` (NEW, #76).**

### The ranking, as decided, and one thing it cannot do yet

Strict tiers: **biggest modeled edge → highest projected run total →
biggest weather/park swing.** Closest matchup rejected — a coin flip is
the ABSENCE of a modeled opinion. Tiers, not a weighted composite: the
weights would be invented, and the card can always say why a game is
first in one true clause.

**TIER 2 NEVER FIRES AND THAT IS NOT A BUG.** `engines/run_total` needs
each team's runs scored and allowed per game; nothing on disk carries
those for MLB. So `proj_total` is deliberately never written, ranking
falls through to tier 3, and the tier is wired and tested so it lights up
the day the field exists — same posture as `announced_starters()` for
WNBA. **Do not substitute the O/U signal count for it.** That counts
signals toward Over; it is not a number of runs, and ranking by it would
be a different quantity wearing the decided label. If you want tier 2
live, the work is a team RS/RA source for MLB, and it is a new scraper
with a new failure mode — probe it first.

**MISSING IS NOT ZERO**, per tier. A game with no posted starters has no
edge; that is not an edge of zero and must not outrank a game measured at
zero, nor be treated as the worst game on the slate. A game missing only
the total still competes normally on edge and on swing.

The weather/park swing weights in `best_games` are **calibration
constants, not measurements** — judgements about how much each signal
moves a game, in one file, like `styles/stat_scales.py`. The score is an
ORDERING quantity used to break a tie and is never displayed; the card
names the signals that fired, because those are real.

### Three degrade paths, all exercised by hand

| on disk | card shows |
|---|---|
| nothing, or a past date | slate_guard's own sentence, naming the date |
| slate, no starters posted | "N games — starters not posted yet" |
| slate with signals | the ranked card |

The middle one earns its branch: it is what every morning looks like, and
ranking an unscored slate produces ALPHABETICAL ORDER WEARING THE COSTUME
OF A RANKING. `has_any_signal()` is the guard.

### Rules held

Rule 5 (Home makes zero network calls) — the card reads CI's file;
`test_best_games` fails on `requests`/`urlopen`/`httpx`/
`get_todays_games_with_weather` appearing in Home.py. Rule 4 (Home cannot
write `lc_sport_seg`) — the jump uses `_goto_sport` when the switcher is
not on MLB. Rule 10 and the design rule — the hero is forward-looking and
last night's graded outcome stays below it; the test asserts the ORDER of
the `_render_*` calls by parsing `render()`, because a substring search
cannot see order.

### TWO TESTS THAT PASSED WITHOUT PROVING ANYTHING

Both caught by breaking the code on purpose. Both are the same lesson.

**1. The alphabetical tiebreak was rescuing broken tiers.**
`rank_games` ends with a team-name tiebreak so the card does not reshuffle
between refreshes. When a tier stops discriminating the sort falls
through to it — and three of the six ranking fixtures were named such
that alphabetical produced the RIGHT answer anyway. Re-introducing the
exact bug the module exists to prevent (missing edge sorting as zero)
left every assertion green.

Fixed by naming every expected winner `z-...` and every loser `a-...`, so
a broken tier now falls through to alphabetical and puts the LOSER first.
**Seven negative controls now run**: missing-as-zero, each tier deleted,
tiers 1 and 2 swapped, unverified park factor read, hero moved below Last
night, `has_any_signal` forced true. All seven go red.

**2. A workflow assertion matched the COMMENT, not the command.**
`test_calibration_picks` asserts slate-picks commits `data/mlb/games.json`.
Deleting the path from the git-add left the test green — because the long
explanatory comment above the step still named the file. This repo puts a
paragraph above every tricky step, so any assertion about what a workflow
DOES has to strip comment lines first. `_commands_only()` now does.

That test also had to change for a legitimate reason: it pinned the exact
string `git status --porcelain -- data/calibration.json`, and moving two
paths into a shell variable broke the spelling while keeping the
property. Rule 11. It now asserts git status / never git diff / both
paths present, and four controls confirm each clause bites.

### The rest of the batch (see the 08-07 block for context)

- **KBO was publishing a leaderboard to nobody.**
  `_render_batting_leaders()` was written in full and never called, while
  `kbo_precompute` wrote `batters.json` every run. Rule 20's third
  disguise: computed-never-rendered, written-never-called, and now
  **rendered-never-invoked**. `tests/test_no_dead_renderers.py` (NEW,
  #75) fails on any `_render_*` in a view without a call site in its own
  file. Exact rather than heuristic because nothing imports a view.
- **WNBA live tracking was a STARTING problem, not a fetching one.**
  `st.fragment` fixes `run_every` at creation and a fragment rerun does
  not re-run module scope, so the poll interval was decided from a
  snapshot taken before the fragment ever ran. Open the board at 6:55 for
  a 7:00 tip and it polled NEVER. The condition is now "is there a game
  tonight that has not finished". Also: `_render_slate` already returned
  the right answer and the caller threw it away while recomputing it.
- **WNBA context columns carry their window** — `FTA szn`, `TO szn`,
  `STL szn`, `BLK szn`. Zero columns added. `l5_fta`/`l10_fta`/`l5_to`/
  `l10_to` are published nightly and still read by nothing; switching to
  them is data-free and is HIS call, not a cleanup.
- `roster.py`'s `utcnow()` → ET, the only naive datetime in the repo.
- `sport_switcher()`'s docstring said "Only MLB is wired to real data",
  contradicting the caption twenty lines below it.
- `staleness_note` named the wrong job for MLB ("the nightly build"),
  which would have sent you to debug `nightly-data` while `slate-picks`
  was the one down.
- Four unused imports.

### A WRONG CALL IN THIS SESSION, recorded so it isn't repeated

A crude sweep for "fields a pipeline writes that no view reads" reported
KBO's **home/away splits and H2H run averages as unrendered.** Both are
rendered fine. The sweep collected dict-key literals and grepped `app/`,
so it could not follow keys consumed inside the same function
(`home_w`/`away_l` build `home_record`, which KBO.py draws) or keys
renamed at the publish boundary (`a_avg_runs` ships as `away_avg_runs`).
It also flagged `l15_pra`, which `player_of_the_day` builds with an
f-string. **A key-literal grep cannot see a rename or a dynamic access**,
and dynamic access is the normal idiom here for anything windowed.

What survived verification: `quality_starts`, `earned_runs`, `risp_avg`,
`high_total`, `low_total` are genuinely published and read by nothing.
Leaf stat fields, not features.

### Do these in order

1. Upload the batch, `git pull`, run the suite. Expect **`TESTS:76`**
   with the same five streamlit-only failures.
2. **Watch the next `slate-picks` run and read one line:**
   `mlb slate: wrote N game(s) for <date> (M with a modeled edge, ...)`.
   `M` will be 0 on an early run and that is expected — probables post
   one to three hours before first pitch. If the line is ABSENT, the
   slate step failed and the message above it says why.
3. **Then confirm the commit landed** — `data/mlb/games.json` must appear
   in the repo. If the log says it wrote the file and the repo has no such
   file, the commit step is the problem, not the writer. That distinction
   is the whole reason step 2 and step 3 are separate.
4. **Open Home after a slate-picks run.** Before probables: "N games —
   starters not posted yet". After: the ranked card.
5. **Open the WNBA board BEFORE a tipoff and leave it.** Scores should
   start moving within ~75s with no reload.
6. KBO board should show a **Batting Leaders** card.
7. Still watch the KBO coverage line on a day KBO actually plays (V2).

---

## PICK UP HERE — state as of 2026-08-07

**Everything below the next divider is background. This block is what
you do first.**

### V2 IS DONE. F2 is answered. Pitcher H2H is unblocked but useless yet.

Runs 84488187205 (late refresh) and 84488729291 (probe) closed three
items between them. No errors in either.

### The coverage counter earned itself on its first run
It printed:

```
KBO: slate 2026-08-07 coverage — venue 0/5, first pitch 0/5, a named starter 5/5
NPB: slate 2026-08-07 coverage — venue 6/6, first pitch 6/6, a named starter 6/6
```

Two things wrong in that line, and **only one of them was in the
scraper**:

- **`venue 0/5` was CORRECT.** Every KBO game on 2026-08-07 was called
  for extreme heat. The probe dumped the card:
  `Kia Tigers LG Twins Canceled Extreme Heat` — no `<time>` element at
  all. A called game has no clock, `_card_time_venue` correctly refused
  to read "Extreme Heat" as a venue, and NPB's 6/6 on the same run
  proves the pipeline path works. **The schedule-card fix is working;
  KBO has simply been heat-canceled two days running.**
- **`a named starter 5/5` was a LIE.** KBO writes
  `g.get("away_starter") or "TBD"`, so the field is never falsy. The
  KBO copy of the counter tested truthiness while the NPB copy tested
  against "TBD" — two copies of one idea, disagreeing inside a single
  run, on a slate the homepage had just reported `0 of 15` starters
  for.

Both are fixed in this batch: the counter now lives in
`app/engines/intl_slate.py`, both pipelines import it (rule 21), a
called-off slate explains its own zeros, and
`tests/test_slate_coverage.py` pins all of it.

### Pitcher game logs: the OPP column is there
Round 4 parsed `GameLogs.aspx` with `pd.read_html` — four tables, one
per month, 19 starts:

```
columns: ['APR','OPP','ERA','RES','PA','IP','H','HR','BB','HBP','K','R','ER','OAVG']
first row: [4.02, 'SAMSUNG', 0.0, nan, 25, '6', 2, 0, 5, 0, 4, 1, 0, 0.1]
```

Per-start, per-opponent, server-rendered, and readable with the same
`pd.read_html` the leaderboards already use. **Pitcher-vs-team H2H is
buildable for KBO.** Two landmines are recorded under the item below —
read them before writing the parser, one of them silently corrupts
dates.

### UI batch, 2026-08-07 — seven changes, all shipped together

1. **Game picker is a carousel.** Pagination removed entirely
   (`gc_page`, `PAGE_SIZE`, "Page 1 of 3"). The whole slate is now one
   horizontally scrollable, scroll-snapped row of real `st.button`s.
   Streamlit has no carousel and buttons cannot live in raw HTML, so
   the scrolling is CSS on a keyed container (`st-key-gc_gamestrip`) —
   the same mechanism every card already uses. Selection state and the
   `_pick_game` callback are untouched.
2. **Weak spots rebuilt.** It rendered in FOUR visual languages stacked
   (borderless table, two bordered box-grids, prose captions) with the
   colour key described in a sentence above all of it. Now one unit
   everywhere: a labelled row with a bar whose LENGTH is the xSLG and
   whose COLOUR is the verdict, one drawn legend at the top. Length
   first, colour as confirmation — a colour-only heatmap is unreadable
   to anyone colour-blind and slow for everyone else.
3. **Missing batter names — fixed.** The bullpen "vs this arsenal"
   table called `.set_index("Player")`, and `_base_styler` calls
   `.hide(axis="index")`, so the names were dropped before rendering.
   `HR_Edge_Board` lost its rank column to the identical mistake.
   `tests/test_gamecard_ui.py` now fails on ANY `.set_index()` in a
   view, because this is a class of bug and not two instances.
4. **Switch hitters labelled.** A switch hitter renders two or three
   rows. The combined row (no probable posted, `stand=None`, i.e. every
   PA from both sides) was labelled with a bare "S" while its siblings
   read "S (L)" / "S (R)" — same player, same batting order, different
   numbers, nothing to tell them apart. It now reads **"S (both)"**.
   It is deliberately NOT labelled with a side: that row is a blend,
   and naming a side would have been a confident wrong answer.
5. **L25 everywhere.** `apply_window` always supported `l25`; the Game
   Card's lineup Window was the only control missing it. Also filled
   the gaps in Bullpen Board (L10, L5) and batter trends (L10).
6. **Cards flattened.** `div[class*="st-key-card_"]` had a gradient and
   two shadows on every panel — the page read as a stack of grey slabs
   competing with dense tables for contrast. Now transparent, separated
   by space and a hairline. Third generation of this card: outline →
   surface+shadow → flat. Glossary keeps a red left rule so the
   reference block stays findable.
7. **League nav restyled, wiring untouched.** Still
   `st.segmented_control` with key `lc_sport_seg` — `app.py` and
   `Home.py` both depend on that machinery (rule 4) and none of it
   moved. Purely CSS: pill shape, 44px tap targets for iPad, and the
   active league filled rather than outlined so you can tell at a
   glance which board you are on.

**One test needed updating, not weakening.** `test_stale_state.py`
named two call sites by hand and one of them stopped existing in the
rewrite. It now finds every subscript using `gc_selected_game_idx` by
pattern and asserts each runs after the clamp, plus asserts `gc_page`
stays gone — a half-removed pager whose state survives unclamped is
precisely the stale-index crash that file exists for.

### Visual batch 2, 2026-08-07 — colour meaning, grid, picker, header

**Cell colour is now ABSOLUTE.** `app/styles/stat_scales.py` (new) holds
four cut points per stat in raw units; `_magnitude_column` uses them
when the column has a scale and only falls back to the old
column-relative normalisation when it does not. Before this, colour came
from each column's own min and max — the same .285 was gold in one table
and violet in another, and changing a filter recoloured every cell
without a value moving. **Direction is still the caller's**
(`favor_high` / `favor_low`), because 26% whiff is elite for a pitcher
and awful for a hitter; the number carries no verdict of its own, so the
scale must not invent one.

**Those cut points are calibration constants, not measurements.** They
are judgements about where a stat stops being average, anchored on
ordinary league ranges, and nothing recomputes them. Argue with them in
that one file — never special-case a scale at a call site, which is how
an app ends up with five definitions of "good".
`tests/test_stat_scales.py` pins the property that matters: the same
value renders identically regardless of what else is in the column.

**Tables got vertical rules.** The only structure was horizontal, so a
run of eight numbers read as a stripe and you had to track back to the
header to know which stat you were on. Hairlines at a twelfth the
strength of the row rules — you should feel the columns, not see them;
a full-strength grid becomes graph paper and fights the cell fills,
which are the signal. Numbers right-aligned so the ones column stacks.
No column gained or lost anything.

**Picker cards carry first pitch**, and the selected card lifts via
box-shadow rather than thickening its border — a 2px-on-select border
shifted every neighbour by a pixel as you moved along the strip, which
reads as jitter on a swipe.

**Headline and conditions.** Venue, first pitch and time are one meta
line with rules instead of a second gold headline. The weather band is a
fixed four-column grid with hairline dividers, ordered
condition/temp/wind/park — the three that change hourly first, the
constant anchoring the end.

### Two-layer bug: the switch-hitter label, 2026-08-07

The label fix shipped earlier was correct and **still showed a bare "S"
on screen.** `bats_chip()` in table_style.py rendered
`str(v).strip().upper()[:1]` — right for "L" and "R", silently
destructive for every qualified label. "S (both)", "S (L)" and "S (R)"
all came out as "S", so the lineup showed the same player twice at the
same batting order with different numbers and nothing telling the rows
apart. The view was fixed; the formatter threw the fix away one layer
later.

**Rule 20 again — follow the signal to the pixel.** A correct value that
a downstream formatter truncates is indistinguishable from never having
fixed it. `tests/test_gamecard_ui.py` now asserts the chip returns what
it was handed, for every label the view can produce.

The chip also no longer uppercases the whole string (that turned
"S (both)" into a shouted "S (BOTH)"), sizes to its content instead of a
fixed 17px box, and cannot wrap inside a narrow Bats column.

### Tables use the whole window

`.block-container` had Streamlit's default side gutters even under
`layout="wide"`. On a page whose main content is fourteen-column stat
tables, that gutter was the difference between reading five columns and
reading nine — every pixel of it came straight off the data. Now
`max-width: 100%` with minimal side padding, and `.lc-tbl-wrap` cells
carry tighter HORIZONTAL padding only. Vertical padding is untouched on
purpose: row height is what makes a dense table scannable, and squeezing
it turns the board into a spreadsheet.

### One control language, site-wide — 2026-08-07

The pill treatment was written scoped to the league nav. Every other
segmented control and pill group kept the older bordered-grey style, so
the SAME widget looked like two different things depending which page
you were on — Bats and Window on the Game Card, form window on WNBA,
prop tabs, every board's filters.

That is not a taste problem. A control's whole job is to answer "which
one is on", and when the answer is styled differently in two places the
reader re-learns it on every page.

The rule now lives **unscoped** in `kc_theme`. Three states, no
ambiguity: unselected is transparent with muted text and no border (a
row of options should not look like a row of buttons demanding to be
pressed), hover is the faintest wash, selected is filled accent with
dark text and is the only strong thing in the group. Plain `st.button`
matches — same pill radius, same quiet default, same filled accent at
`type="primary"`, which is what the game picker's cards use.

The nav keeps only what is genuinely nav-specific: centred, and 44px
instead of 40 because it is the first thing touched on every page.

**A real bug fell out of this.** The mobile block was setting
`stButtonGroup` to `min-height: 38px` — SHRINKING touch targets on the
one device where they matter most. Now 44px there too.
`tests/test_control_language.py` asserts no control anywhere is under
40px, that the selected state is defined unscoped, and that scoped
overrides set layout only and never a background colour — a per-board
colour override is exactly how the drift started.

**The test needed two goes.** Its first version read the MOBILE override
of `.stButton > button` because that rule appears earlier in the sheet,
and reported the base rule missing when it was fine. It now asks "does
ANY rule for this selector declare the property" rather than "does the
first one" — a test that parses CSS has to know the difference between
a rule and an override.

### Why KBO, NPB and Home missed the restyle — 2026-08-07

**Three selectors draw cards, and only one of them was flattened.**

- `div[class*="st-key-card_"]` — container cards, what the MLB views use.
  Flattened first.
- `.pf-card` — raw HTML from `card_open()`/`card_close()`. **This is what
  KBO and NPB render**, so both international boards kept the previous
  generation of the design while every other page moved on.
- A local override in `Home.py` for `st-key-card_home_`, which outlived
  the global rule it was overriding — the home page was the only page
  still drawing gradients and shadows.

Nothing in the code said the three had to agree, and they do: it is the
same object to a reader. `tests/test_control_language.py` now asserts
none of them paints a gradient or a shadow, wherever it is defined,
including the copy inside Home.py.

**What survived on Home, deliberately:** the coloured top rule and the
hover lift. Those carry information — which board is live, and that the
card is clickable. The fill and the shadow said nothing.

**Expanders joined the control language.** "Every pick from last night",
"Weak spots", the glossary — the one control that opens something, and
still a filled grey slab with a hard border while everything else had
gone quiet-until-active. Now a wide button: transparent, faint wash on
hover, hairlines above and below, 44px target, and the header takes the
accent when open. The open state keys off `details[open]` — the
browser's own flag — so it cannot drift with a Streamlit release the way
an internal class name would (rule 9).

### Do these in order

1. Upload this batch, `git pull`, run the suite. Expect
   **`TESTS:70 FAILING: none`**.
2. **Run `Late slate refresh` on a day KBO actually plays.** The line
   to read is the coverage line. On a played slate, `venue 5/5,
   first pitch 5/5` closes V2 for good. `a named starter 0/5` is
   EXPECTED and is not a defect — see F2.
3. Everything else is a build decision, not a verification. The
   biggest open product item is still **C** (best-games hero card),
   which is blocked on recording an MLB slate and has been the whole
   time.

### Decisions taken, do not re-litigate
- **The repo stays PUBLIC.** Going private would 404 the release-asset
  download in `app/fetch_data.py` — Render falls back to live Statcast
  pulls and says so in a warning that fails nothing, i.e. a silent data
  outage — and private repos stop getting free Actions minutes. If it
  ever goes private: create a fine-grained PAT, set `GITHUB_TOKEN` in
  Render, confirm the build log prints `[fetch_data] OK`, THEN flip.
- **He commits via GitHub's web editor**, which writes straight to
  `main`. The Codespace is therefore usually BEHIND, not ahead.
  `git pull` first; "nothing to commit, working tree clean" is the
  expected result there, not a failure.
- **A red workflow is not automatically a repo defect.** `The job was
  not acquired by Runner of type hosted` plus an internal-server-error
  correlation id is GitHub's. Check githubstatus.com before debugging,
  and do not re-run into an outage — queued runs all fire at once when
  capacity returns, which is exactly how two concurrent publishes
  happen.

---

## READ THIS BEFORE YOU ACT ON ANYTHING BELOW

A stale handoff that gets trusted is worse than no handoff: it sends a
session to redo something already done, or — as of this audit — to
believe a feature is live when it has never once executed. This file is
a summary. **The repo is the truth, and a green repo is not a green
pipeline (rule 14).**

```bash
cd /workspaces/honestygfymodel
git pull
git log --oneline -12
fails=""
for t in tests/*.py; do python "$t" >/dev/null 2>&1 || fails="$fails $(basename $t)"; done
echo "FAILING:${fails:- none}"
```

Then, for anything marked PENDING, **check it is still pending.**

```bash
ls tests/*.py | wc -l                                     # 76
python tests/test_no_dead_renderers.py | tail -1          # both leaderboards draw
python tests/test_best_games.py | tail -1                 # Home makes no network calls
grep -c _render_batting_leaders app/views/KBO.py          # 3 = def + 2 call sites
grep -c _could_go_live app/views/WNBA.py                  # 2 = live poll starts pre-tip
grep -c utcnow app/engines/roster.py                      # 0 = no naive datetimes left
grep -c \'"mlb"\' app/engines/slate_guard.py               # 2 = item C UNBLOCKED
grep -c _write_mlb_slate calibration_picks.py             # 2 = defined AND called
grep -c _render_best_games app/views/Home.py              # 2 = def + call
grep -c _not_built_yet app/engines/slate_guard.py         # 2 = def + call
grep -c 'st.caption(note)' app/views/Home.py              # 1 = the comment only
ls data/mlb/games.json                                    # appears after a slate-picks run
grep -c void_risk kbo_precompute.py                       # 3  = V3 in
grep -c void_reason app/views/KBO.py                      # 3  = board shows it
python tests/test_return_arity.py | tail -1               # FAILING: none
grep -c fetch_homepage_schedule kbo_precompute.py         # 2  = defined AND called
grep -cE '^\s+_hp, _hs =' kbo_precompute.py               # 0  = the crash is gone
                                                          #      (anchored: the docstring
                                                          #       quotes the broken line)
grep -c _card_time_venue kbo_precompute.py                # 2  = venue/time fix in
grep -c 'fetch failed twice' app/engines/intl_weather.py  # 1  = weather retry in
grep -rc publish-archive .github/workflows/nightly-data.yml  # 1  = item G closed
grep -c coverage_line kbo_precompute.py                    # 2  = shared counter in
grep -c coverage_line npb_precompute.py                    # 2  = and on both boards
wc -l wnba_precompute.py                                  # 1085 = comments restored
grep -c intl_weather npb_precompute.py                    # >0 = NPB weather WIRED
grep -c _weather_badges app/views/KBO.py                  # 2  = KBO shows weather
grep -c _weather_badges app/views/NPB.py                  # 2  = NPB shows weather
# (item C is now BUILT — see the 08-09 block. The two greps above
#  replace these; they said 0 when C was blocked.)
grep -c 'class="venue"' kbo_precompute.py                 # 2  = schedule-page regex
                                                          #      still dead; TODAY is
                                                          #      repaired from the homepage
ls .github/workflows/ | wc -l                             # 11
ls wnba-lineup-probe.yml                                  # should NOT exist — stray
```

**Update this file in the same commit that ships the work.**

---

## AUDIT, 2026-08-06 (second) — repo zip + the logs of failed run 84386218583

Checked on disk and against a real workflow log, not believed.

### THE HEADLINE: KBO has been failing every run, and nobody saw it.

The last session shipped the homepage venue/time repair, watched 66
tests go green, and pushed. **The repair has never executed.** Every
`intl-late-refresh` run since has died in `kbo_precompute.main()`:

```
ValueError: not enough values to unpack (expected 2, got 0)
  File "kbo_precompute.py", line 874, in main
    _hp, _hs = fetch_homepage_starters()
```

`fetch_homepage_starters()` returns ONE dict. The call site was
rewritten for a two-value contract the function was never given, and
`fetch_homepage_schedule()` — the other half — was never written at
all. `parse_homepage_schedule()` existed, was correct, was tested, and
had **no production caller**: rule 20 one layer deeper than last time.
Not "computed and never rendered" — written and never *called*.

The crash was the lucky outcome. Unpacking a dict yields its KEYS, so
on a slate where exactly two games had announced starters that line
would have **succeeded**, bound two game-id strings to `_hp` and `_hs`,
and every lookup after it would have found nothing while reporting
nothing wrong. The loud failure is why this was caught in one day
instead of the several weeks the last three silent scraper deaths took.

What that failure actually cost, from the run log:

- KBO step exits 1. NPB and WNBA ran fine and were published.
- The repack still ran, `data/kbo/` was "present", the archive was
  uploaded and Render was deployed — **with the nightly's stale KBO
  slate inside**. The site kept showing something, which is why this
  read as "not fixed yet" rather than "hard down".
- The failure was reported honestly at the end (`::error::KBO refresh
  failed - the archive kept the nightly's KBO slate`) and the job went
  red. That design is correct; keep it.

**Fixed in this batch** (see below). The lesson is now rule 22.

### Items the previous file listed as PENDING that are already DONE

- **0b — sweep for committed secrets. RUN, and it is clean.** Every
  match in `*.yaml`/`*.yml`/`*.toml` is a `${{ secrets.X }}` reference
  or the word "secret" in a log line. `app/auth_config.example.yaml`
  carries `key: REPLACE_ME__run_the_command_above` and a comment
  explaining why. Nothing live is committed. **Item closed.**
- **`likely_starters` double-docstring.** Already merged —
  `app/engines/wnba_props.py:603` has one docstring. **Item closed.**
- **NPB weather** is not just wired but working: run 84386218583 logged
  `weather: 5 venues, max 36°C, 1 at or above 35°C heat threshold` and
  `1 of 5 slate games at or above a 50% precipitation chance`. No
  `no coordinates for` line appeared anywhere in the run — that clears
  the watch-item under W on all three venue-lookup fixes.

### Real, and fixed in this batch

1. **The KBO crash.** `fetch_homepage_schedule()` now exists as a
   sibling of `fetch_homepage_starters()` — same cached document, so
   still one HTTP request — and `main()` calls the two separately. Kept
   separate rather than merged into a tuple return because membership
   of the starters map has to keep meaning "this game has announced
   starters"; `test_kbo_homepage_starters` depends on it. (This used to
   name `test_kbo_heat_risk`, which is DELETED — see O1-original.)
2. **`tests/test_return_arity.py` (NEW, test #67).** Static, no imports,
   no network. Parses each pipeline file, works out how many values each
   module-level function can return, and flags any call site in that file
   that unpacks a different number. It reports only definite
   contradictions and skips anything ambiguous — a test that cries wolf
   gets switched off. **Verified by re-introducing the exact broken line
   and watching it go red**, then removing it. It names no function, so a
   rename doesn't defeat it.
3. **A dead local in `main()`** — `_venues` was built from every
   upcoming game and never read, left behind by the move to Open-Meteo.
   Removed.
4. **This file.** The old item V's body survived as an unlabelled
   fragment under the pitcher-H2H section, still saying the board reads
   `TBD · TBD KST / TBD ET` on every game. Removed.
5. **A stale comment** in `tests/test_kbo_homepage_starters.py`
   describing `hp_time`/`hp_venue` keys that no longer exist anywhere in
   the codebase.

---

## OPEN — in priority order

### V2. KBO venue + time for future dates — CLOSED.
`parse_week` reads both off schedule-card text via `_card_time_venue`,
which reuses `HOME_TIME_VENUE` rather than adding a fifth regex to the
file that has lost four. `datetime=` is still alive so the markup key
wins where it exists; the text is a fallback only.

Confirmed working on 2026-08-07 by **NPB reporting 6/6 venue and 6/6
first pitch on the same run** KBO reported 0/5 — because every KBO game
that day was heat-canceled and a called card carries no `<time>`
element at all. See `tests/test_kbo_schedule_card.py`, which pins the
trap: `ds-game-card__sub is-prose` holds the VENUE on an upcoming card
and the words **"Extreme Heat"** on a canceled one, so requiring a
clock immediately before the venue is what separates them. Without
that, `venue_for_game()` would hunt for coordinates for a city called
Extreme Heat, miss, and fall back silently.

`week_of` is honoured for forward dates (asked 2026-08-20, served
2026-08-18..23). **One thing left:** watch the coverage line on a day
KBO actually plays. 5/5 there and this never needs looking at again.

### F2. KBO probables — the schedule page shows them ONLY AFTER the fact.
Round 2 counted `ds-game-team__starter` per card:

```
past/today: 10 cards, 7 carrying a starter span
upcoming:   20 cards, 0 carrying a starter span   (current week)
upcoming:   30 cards, 0 carrying a starter span   (two weeks out)
```

Fifty upcoming cards, zero starters — including games one day out, at
00:30 KST, well inside any announcement window. Combined with every
homepage measurement also reading 0, the hypothesis worth testing is no
longer "our regex broke" but **mykbostats v3 stopped publishing
probables in advance at all** and only fills the span once a lineup is
actual. `parse_homepage_starters()` is correct and costs nothing, so
leave it in; it lights up automatically if they come back.

**Do not widen either regex.** If probables matter, they need a source
that publishes them — which is item E3, and the reason to finish it.

### O1. CLOSED, and it uncovered a worse bug. See V3 below.

### V3. A CANCELLATION WAS ONLY READ FOR GAMES ALREADY PLAYED.
`parse_week`'s status block sat behind `if gdate < today_str:`, so a
game called off for TODAY or any future date still shipped as
`scheduled`. Measured on the live page 2026-08-07: mykbostats listed
**every KBO game through 08-09 as Canceled** in a heat wave, and the
board would have shown all fifteen as on. That is the void problem
itself — the board saying a game is playable when the source says it is
not — and it is the worst direction to be wrong in on a betting site.

NPB never had it: `<div class="cancel">` is checked with no date gate.
KBO was the odd one out, which is rule 21 in its quiet form.

Fixed. The cancellation check now runs on every date. `FINAL_PAT` stays
past-only on purpose (a future game has no score to parse), and a
postponed game can no longer also be graded final.

Two new fields ship on every KBO slate row, deliberately separate
because they answer different questions and a game never has both:

- **`void_reason`** — why a called game was called (`Extreme Heat`).
  Absent on a bare `Canceled`, which is a real difference in the source
  and not a gap to fill in.
- **`void_risk`** — the site's forward-looking warning on a game that
  is STILL ON. Three phrasings measured: `Chance of Heat Cancellation`,
  `Chance of Rainout`, `Forecast Uncertain`.

This is what O1 was asking for, taken off the homepage (today only) and
onto the schedule page (the whole week). Quoted verbatim, never mapped
onto our own scale — Open-Meteo gives a temperature against
`HEAT_CANCEL_C`, which is still unverified; this is the site DECIDING.
Both render on the KBO board ahead of the measured badge.

`tests/test_kbo_void_signals.py` pins the separation both ways: the
warning must never be read as a cancellation, and a decision must never
be read as a warning. Negative controls run — the test throws on the
pre-fix tree, and fails if the risk pattern is widened to overlap
`Cancel`.

**NPB parity is OWED here and is not done.** npb.jp has not been
checked for a forward-looking warning of its own. Until someone looks,
KBO shows a signal NPB does not, and a missing badge is unreadable —
it means "no risk" on one board and "not measured" on the other. Check
npb.jp's schedule markup before building anything else on this.

**`fetch_homepage_conditions()` — RESOLVED 2026-08-10, deleted.** See
O1-original below for the reasoning and for where its test's properties
went.

### O1-original — CLOSED 2026-08-10. Deleted, and here is the why.
Open across four sessions as "delete it and say why, or keep it as a
cross-check and wire it — do not leave it neither." Deleted.

The argument FOR wiring it was real and is worth recording, because it
is why this sat open so long: Open-Meteo only gives a temperature
against `HEAT_CANCEL_C`, and that threshold is still UNVERIFIED, whereas
the site's own warning is the *league's actual judgement*, published in
advance. That is a thing our forecast genuinely cannot reproduce.

It was answered by V3. `parse_week()` now reads `VOID_RISK_PAT` off the
SCHEDULE page — the same league judgement, quoted verbatim, for THE
WHOLE WEEK instead of today only. So the signal was never lost; it was
already being read better, from a page already fetched. Wiring the
orphan would have meant two answers to one question from two requests,
with no rule for which wins.

Deleted with it: `parse_homepage_conditions()`, `HEAT_RISK_PAT`,
`TEMP_PAT`, and `tests/test_kbo_heat_risk.py` (**76 -> 75 test files**;
it tested only those two functions, so keeping it meant keeping dead
code to keep a test green).

**Every property that test held was checked for a home before deleting,
not assumed.** All but one were already covered — warning-vs-decision by
`test_kbo_void_signals` (and against the LIVE reader, which is strictly
better), and the leak/absent/independence checks by
`test_kbo_homepage_starters`. The one exception, "the two readers are
separate functions", was MOVED into `test_kbo_homepage_starters` along
with a new check that the deleted readers stay deleted. Deleting a test
that guards a real property, because the code it happened to name went
away, is how a guarantee evaporates without anyone deciding to drop it.

### W2. Open-Meteo now retries once. Watch that it is enough.
Run 84398190888 fetched ten dates; nine succeeded and the ONE that
timed out was the first, which is today's — the slate actually on
screen. So a single 25-second blip cost the displayed board every
badge while nine days nobody looks at were forecast fine. The cost is
not spread evenly across dates, so "it usually works" was not good
enough for the first one.

`intl_weather.forecast()` now retries once after 2 seconds, then gives
up and prints `fetch failed twice`. **If that line ever appears, it is
a real outage, not a blip.** Not yet observed in production.

### C. Best-games hero card — BUILT 2026-08-09, NOT YET EXECUTED.
Everything this item asked for is on disk: `slate_guard` knows `mlb`,
`calibration_picks._write_mlb_slate()` writes the slate at 1/5/7 PM ET,
`engines/best_games.py` ranks it, Home leads with it and degrades three
ways. Details, the near-miss on WHERE the file goes, and the two tests
that passed without proving anything are all in the 08-09 block at the
top of this file.

**What is left is verification, not building.** The CI half has never
run. Read the `mlb slate: wrote N game(s)` line in the next slate-picks
log, then confirm `data/mlb/games.json` actually appears in the repo —
those are two separate failures and step 2 and step 3 of the top block
keep them apart on purpose.

**The one piece genuinely still missing is TIER 2.** `proj_total` is
never written because `engines/run_total` needs per-team runs scored and
allowed and nothing on disk carries them for MLB. The tier is wired and
tested and fires the day the field exists. Building it means a new MLB
team RS/RA source — a new scraper with a new failure mode, so probe it
before writing a parser. **Do not** substitute the O/U signal count:
that counts signals toward Over and is not a number of runs.

### PITCHER H2H — BUILDABLE FOR KBO. Blocked on knowing who starts.
Probe round 4 parsed
`eng.koreabaseball.com/Teams/PlayerInfoPitcher/GameLogs.aspx?pcode=55268`
with `pd.read_html`: **four tables, one per month, 19 starts.**

```
columns: ['APR','OPP','ERA','RES','PA','IP','H','HR','BB','HBP','K','R','ER','OAVG']
first row: [4.02, 'SAMSUNG', 0.0, nan, 25, '6', 2, 0, 5, 0, 4, 1, 0, 0.1]
```

Per-start, per-opponent, server-rendered, no JSON blobs, reachable from
the 20 player links on `PitchingLeaders.aspx` — a page the pipeline
already fetches. Read with the same `pd.read_html` the leaderboards use,
so this is an extension of existing code, not a new parser.

**TWO LANDMINES. Read before writing anything.**

1. **The date column is a FLOAT and it collides.** The header is the
   month (`APR`), the value is `4.02` = April 2. But `6.3` appears in
   the June table, and as a float that is indistinguishable from June 3
   (`6.03` → `6.03`) versus June 30 (`6.30` → `6.3`). **Pandas has
   already destroyed the distinction by the time you see it.** Take the
   month from the column header and the day from the RAW STRING, not
   the parsed float. A wrong date silently mis-orders a pitcher's
   season and mis-attributes starts.
2. **`IP` mixes types** — `'6'`, `4`, `'4 1/3'` in the same column.
   `_parse_ip()` already exists in `kbo_precompute`; use it rather than
   float().

Also: `RES` is `nan` for a no-decision, which is a real outcome and not
missing data.

**WHY IT IS STILL BLOCKED.** Pitcher-vs-team H2H answers "how has
tonight's starter done against tonight's opponent" — and **we do not
know who is starting.** F2 established that mykbostats no longer
publishes probables in advance, and 50 upcoming schedule cards carried
zero starter spans. Building this now yields a lookup with nothing to
key on. **Finish E3 first**, or accept that the feature only lights up
retroactively.

**NPB remains a dead end.** `/bis/eng/players/` is a 218-char stub with
no links; the Japanese leaderboard links only `/bis/players/`, which has
**0 tables**. Nothing we fetch reaches a per-start log. If this ships
for KBO only the boards will disagree — rule 21 — so say so on the page
rather than letting one board look richer for no stated reason.

Separately, both leagues' season lines come from leaderboards listing
QUALIFIED pitchers only — 20 for a 10-team league — so most starters
have no season line at all. Coverage gap in the source, not a parse
failure.

### E3. KBO source migration — probe DELIVERED, not yet run.
**Decided 08-10: mykbostats is going.** `kbo_probables_probe.py` is the
probe this section asked for. Run it from Actions and read the verdict
line; if no endpoint exists, ship KBO without probables and label the
board. See the top block.

### E3 (original note).
mykbostats clause 6 forbids betting use, so the rest should move to
`eng.koreabaseball.com`. `DailySchedule.aspx` returns a whole month
(98KB, ~130 games, a POSTPONED column) in one GET. **Probables are the
blocker** — the Korean schedule serves 0 occurrences of 선발/투수/예고,
drawn client-side. One probe to find the XHR endpoint settles it. Until
then: keep mykbostats for probables only, or drop them.

### D. Daily cold start — CLOSED 08-10, decided against.
Dome flags STAY in `intl_venues.py`. Reasoning in the top block: it
would break the "unknown is not open" guarantee, make a fallback depend
on the network its caller fell back from, and buy nothing on a table
that changes about once a decade. **Do not re-propose.** The cold-start
problem itself, if it still bites, needs a different fix.

### HEAT_CANCEL_C = 35.0 is still UNVERIFIED.
Matches the commonly cited figure and 폭염경보 criteria but was never
confirmed against a published KBO rule, which may key on apparent
temperature or a KMA warning. Every run logs max temps whether or not
the flag fires — a week of logs beside real cancellations calibrates
it. **Do not quietly tune the number without recording why.** See O1:
the site's own advance warning is a free check on this number.

### Smaller
- **`wnba-lineup-probe.yml` sits in the repo ROOT** as a byte-identical
  duplicate of `.github/workflows/wnba-lineup-probe.yml`. Inert —
  GitHub only reads the workflows directory — but it is exactly the
  artefact "Upload files flattens folders" leaves behind. One-line
  delete: `git rm wnba-lineup-probe.yml`.
- Unread terms for Baseball Savant and npb.jp (see SOURCES section in
  git history of this file).
- KBO probables cover **TODAY only** — the homepage has no future
  slate. Not a bug; V2 is the fix for the venue/time half.
- News section: pushed back on twice (rule 5 — Home can't fetch).
- Five tests import `streamlit` and so only pass where it is installed
  (`test_data_paths`, `test_home`, `test_pen_roster_drift`,
  `test_wnba_grading_honesty`, `test_wnba_injury_gate`). Green in the
  Codespace, red in a bare container. Not a defect — know it before
  reporting "5 failing".

### CLOSED — do not reopen
- **WNBA starters.** ESPN publishes no `today_starter`;
  `stats.wnba.com` hangs on datacenter ranges and Render is one. The
  inference says LIKELY. `announced_starters()` exists, so a real
  source would light it up automatically. Run 84386218583:
  `0 announced starters` on all three games, as expected. **Needs a new
  source, not another attempt.**
- **0b, committed secrets.** Swept 2026-08-06. Clean.
- **`likely_starters` double-docstring.** Already merged.

---

## RULES — how not to break things

1. **Verify what is ON DISK, never a script's own report.**
2. **Commit before running anything that reverts.**
3. **f-strings in the CSS blocks need `}}`.**
4. **Home cannot write `lc_sport_seg`** — use `_goto_sport()`.
5. **Home makes zero network calls, on purpose.**
6. **Never hand-write a dependency list in a workflow.**
7. **Home looks empty outside board hours (1, 5, 7 PM ET) — correct.**
8. **ESPN blocks by IP range, not User-Agent.**
9. **Don't fix layout by guessing at Streamlit's internal classes.**
10. **Above the "Today" tag, everything must be about today.**
11. **A test that greps source must assert the PROPERTY, not the
    spelling.**
12. **NEVER `git clean -xfd`.** `.gitignore` hides
    `app/auth_config.yaml` and `app/data/`, both unrecoverable.
13. **`|| echo "... continuing"` hides real defects** — something must
    run the code. Run `python -m pyflakes` on the pipeline files.
14. **A green repo is not a green pipeline.** Check Actions after any
    push touching a `*_precompute.py` or `tests/`.
15. **Long content is delivered as an uploaded FILE, never retyped
    into chat.** Retyping a base64 script caused the WNBA outage and
    destroyed 203 comment lines.
16. **Verify a replacement against the ORIGINAL, not a syntax
    checker.** Compare parsed ASTs with docstrings stripped.
17. **A substring is not an element.** `.count("player-link")` matched
    `data-ds-setting="player-links"` and inflated a whole table.
18. **Scrape the PRODUCT, not the STYLING.** Class names change on a
    rewrite; visible text and URLs do not. Three separate regexes in
    `kbo_precompute` died to one mykbostats rebuild.
19. **Never align ids on a partial list.** If the compare link's pid
    count is not exactly 2×games, drop them all.
20. **A computed field nobody renders is not a feature.** The weather
    pipeline was complete and correct for days while every board showed
    nothing, and the licence credit was printed for data that never
    appeared. When wiring a signal, follow it to the pixel.
21. **Parity between KBO and NPB is structural, not remembered.**
    Shared logic goes in an engine both views import; a test asserts
    neither hardcodes its own copy. A signal on one board and not the
    other is unreadable.
22. **NEW — unit tests on a parser cannot see a wiring error one frame
    up.** `parse_homepage_schedule()` was correct and tested and had no
    caller; `main()` unpacked two values from a one-value function and
    KBO failed every run while 66 tests stayed green. **When you add a
    function, the same change must add its caller and something that
    executes the caller.** `tests/test_return_arity.py` catches the
    specific shape; the habit it stands for is: after any change to a
    `*_precompute.py`, run the file or read the Actions log. Do not
    ship a function whose first real execution is in production.

23. **NEW — a probe that samples the wrong rows answers the wrong
    question.** Round 1 of `intl_v2_probe` fetched the CURRENT week,
    where every KBO game was already played or heat-canceled, and
    reported `'pm': 0`, `'°': 0`, `datetime=: 0`. That read as "the
    schedule page has no time or venue" and nearly closed item V2 as
    impossible. A finished card shows a score where an upcoming one
    shows a clock. Round 2 asked for a week two weeks out and got the
    opposite answer. **Before believing a zero, check that the sample
    could have produced a non-zero.**
24. **NEW — a red workflow is not always a repo defect.** `The job was
    not acquired by Runner of type hosted` and an internal-server-error
    correlation id are GitHub's, not yours. Check
    githubstatus.com before debugging, and do NOT re-run into an
    outage — queued runs all fire at once when capacity returns, which
    is exactly how two concurrent publishes happen.

---
25. **NEW — a ranking test can pass on its tiebreak.** `rank_games`
    ends with an alphabetical tiebreak so the card does not reshuffle
    between refreshes. Break a tier and the sort falls through to it —
    and three of six fixtures were named so that alphabetical produced
    the RIGHT answer anyway. Re-introducing the exact bug the module
    exists to prevent left every assertion green. **Name the expected
    winner so it loses the tiebreak**, then break the tier on purpose
    and watch the case go red. This generalises: whenever a sort has a
    fallback, a test of the primary key must be constructed so the
    fallback cannot supply the same answer.
27. **NEW — a test must stub every path the code under test reads.**
    `slate_guard._read()` deliberately reads TWO locations and keeps the
    later-dated one. `test_slate_guard` stubbed only `app/data/`, which
    was invisible for months because the repo-root path was empty. The
    day `calibration_picks` wrote a real dated slate there, that file
    out-dated every fixture, every MLB case returned ok, and five
    load-bearing assertions passed without ever being reached. **The
    test was defeated by the feature it was written to protect.** A
    fixture covering one of two read paths covers neither. Sibling of
    rule 25: both are a test going green for a reason that has nothing
    to do with the thing it asserts.

---
26. **NEW — an assertion about a workflow must read what it RUNS.**
    A test asserting slate-picks commits `data/mlb/games.json` stayed
    green after the path was deleted from the git-add, because the
    explanatory comment above the step still named the file. This repo
    puts a paragraph above every tricky step, so a substring search over
    a workflow matches prose far more often than code. Strip comment
    lines first. Sibling of rule 17: a substring is not an element, and
    a comment is not a command.

---

## The repo

`iamjpescobar/honestygfymodel` — Streamlit sports betting analytics app,
**Los Cappers**. Renders on Render. MLB, WNBA, KBO, NPB.

- Entrypoint is **`app/app.py`**, not `app.py`.
- Pages in **`app/views/`**, deliberately NOT `pages/` — Streamlit
  auto-registers `pages/` and would expose every page pre-auth.
- Engines in `app/engines/`. Theme in `app/styles/kc_theme.py`.
- Tests in `tests/` — **83 files, plain scripts, not pytest.**
- Data comes off disk; the nightly publishes a release asset.
- `requirements.txt` fully pinned, including transitives.

---

## How he works

- **iPad, GitHub Codespaces in Safari.** No local machine. Screenshots
  only — every command must print ONE short line. Never ask him to
  paste terminal output.
- Long heredocs have scrambled when pasted. **Keep pasted commands to
  one line.**
- **Uploading a file is the most reliable delivery** (rule 15).
- He can hand a new session the **repo zip plus this handoff** and have
  it audited from scratch — and, as of this audit, **the failed run's
  log zip too**. The log is what turned "the fix isn't showing up yet"
  into an exact line number. Keep doing both.
- GitHub web **"Upload files" flattens folders** — never use it here.
  The web **file editor** keeps the path and auto-generates the commit
  message. Editor yes, Upload files no.
- **Always say whether a file is a repo file or a script to run.**
- **Workflows run from the branch.** Commit and push BEFORE Run
  workflow.

---

## DESIGN RULE — do not violate

**Past results must never sit where they could read as a suggestion for
today's slate.** A large headline naming a player and an outcome reads
as a recommendation no matter what label sits above it, and on a
betting site that ambiguity costs someone money. Every graded figure
keeps its tense visible. This is why the top-of-page hero must be item
C, which is forward-looking, and not a recycled result.

---

## Working agreements

- He asked for the whole app reviewed, not just reported bugs.
- Comments explain **why**, including what broke before. It is the
  codebase's best feature; it has been destroyed once and rebuilt.
- Be explicit about verified vs assumed. Confident hypotheses that
  turned out wrong: the KBO failure was a missing dependency, not a
  source outage; the WNBA backfill's empty days were a payload-shape
  mismatch behind three 200s; a red test had no bug behind it; the WNBA
  outage was a transcription error; "2 real anchors per game" was an
  undercount of site chrome and the true figure was zero; and — this
  audit — "the venue fix is shipped, just waiting on a refresh" when it
  had never run.
- When you get something wrong, say so plainly and move on.
- Don't build something you can't verify.
