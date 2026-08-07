# Los Cappers — session handoff

Read RULES before proposing any change; every one was learned by
breaking something.

**Rewritten 2026-08-06. An earlier version of this file was itself
corrupt — a dead copy of item V dangled under the pitcher-H2H section,
describing as broken something the section twenty lines above described
as fixed. Verify before you build. START WITH "PICK UP HERE".**

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
ls tests/*.py | wc -l                                     # 73
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
grep -c '"mlb"' app/engines/slate_guard.py                # 0  = item C still blocked
ls data/                                                  # C unblocks when mlb/ appears
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
   starters"; `test_kbo_heat_risk` depends on it.
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

### O1. `fetch_homepage_conditions()` is orphaned — decide, don't delete.
It parses the site's own **`Chance of Heat Cancellation`** warning off
the homepage and nothing calls it. Weather moved to Open-Meteo, which
was right — but Open-Meteo can only give a temperature against
`HEAT_CANCEL_C`, and that threshold is UNVERIFIED (below). The site's
warning is the *league's actual judgement*, published in advance, and
it is the one thing our own forecast cannot reproduce. Either wire it
back in as a second, clearly-labelled signal or delete it and say why.
Right now it is neither.

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

### C. Best-games hero card — BLOCKED on recording an MLB slate.
Ranking **DECIDED**: biggest modeled edge → highest projected run total
→ weather/park swing. Closest-matchup rejected. Goes at the **top of
Home** (rule 10 — the hero must be forward-looking). Blocked on: no
`data/mlb/games.json`, `slate_guard._LEAGUES` has `wnba`/`kbo`/`npb`
and no `mlb`. Needs `calibration_picks.py` (already runs 1/5/7 PM ET
with network) extended to write an MLB slate in the shape `slate_guard`
reads. Home must degrade gracefully until CI populates it. **Biggest
remaining product item.**

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

### E3. KBO source migration — blocked on one probe.
mykbostats clause 6 forbids betting use, so the rest should move to
`eng.koreabaseball.com`. `DailySchedule.aspx` returns a whole month
(98KB, ~130 games, a POSTPONED column) in one GET. **Probables are the
blocker** — the Korean schedule serves 0 occurrences of 선발/투수/예고,
drawn client-side. One probe to find the XHR endpoint settles it. Until
then: keep mykbostats for probables only, or drop them.

### D. Daily cold start — his call needed.
Dome flags out of `intl_venues.py` into published data so the late
refresh stops triggering a Render deploy. Not started.

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

## The repo

`iamjpescobar/honestygfymodel` — Streamlit sports betting analytics app,
**Los Cappers**. Renders on Render. MLB, WNBA, KBO, NPB.

- Entrypoint is **`app/app.py`**, not `app.py`.
- Pages in **`app/views/`**, deliberately NOT `pages/` — Streamlit
  auto-registers `pages/` and would expose every page pre-auth.
- Engines in `app/engines/`. Theme in `app/styles/kc_theme.py`.
- Tests in `tests/` — **73 files, plain scripts, not pytest.**
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
