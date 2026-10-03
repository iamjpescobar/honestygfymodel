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

**The suite is 122 files and stays green.** Five fail in a bare
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

## PICK UP HERE — value, stakes and a graded record for every model pick. 2026-10-03 (7)

**Suite 122, FAILING: none.** Three negative controls red by exit code.

Izzy wants to stake model picks. Nothing showed they beat the BOOK —
only that they beat a coin flip — so this batch makes every pick
checkable at the real price and grades every value pick in public.

### WHAT SHIPPED

`engines/value.py` — break-even, edge, EV per $100, fractional Kelly
with a per-bet cap. Bankroll / fraction / cap are the BETTOR's risk
settings (rule 1 is about numbers that describe the world), defaults
1/4 Kelly and 2%, shown wherever a stake prints.

Every model card (MLB Model, Game Card, NHL Model, NFL Model) has a
value table: model %, fair price, the posted price pre-filled where ESPN
has one, EDITABLE so the reader types his own book's price; edge, EV,
stake, ✅. MLB/NHL prop tables get a "check a prop at your price" tool;
NFL Projections gets one with real over/under chances
(`engines/nfl_prop_odds.py`: game-to-game scatter MEASURED per market —
NB size for counts, pooled cv for yards — not yet graded, page says so).

`engines/model_picks.py` + `model_picks_grade.py` — every side with
positive EV at the POSTED price is logged pre-game, first writer wins
per (game, market), to data/model_picks/{mlb,nhl,nfl}.json; graded
nightly from statsapi / ESPN finals by game id; void after 3 days not
final. Results → "Model picks": W-L-P, units, ROI, split by edge bucket
and market. **If bigger edges do not do better, the model's confidence
is not real — that table is the check.** MLB lines come from ESPN
(`espn_feed` gained "mlb", odds only) via calibration_picks at slate
time; odds_of now reads over/under and spread PRICES when published and
never fills in -110.

### RULES THIS BATCH ADDS

A side with no posted price is never logged (an assumed -110 reports a
profit nobody saw). A pick after first pitch is not a pick. Two
staking_controls() on one page is a duplicate-widget crash — the second
consumer uses current_staking().

### FOR THE FIRST LOGS

    mlb model: N/N games projected, N with an ESPN line, N new value pick(s)
    [verify] ... with a posted moneyline: N, total price: N
    [verify] NHL/NFL value picks logged this run: N
    model picks <sport>: graded N, voided N | record W-L-P ...

### FILES, 2026-10-03 (7)

    app/engines/{value,model_picks,nfl_prop_odds}.py, model_picks_grade.py   NEW
    tests/test_value_picks.py                                                NEW
    app/engines/{model_view,mlb_game_model,espn_feed}.py
    app/views/{MLB_Model,GameCard,NHL_Model,NFL_Model,NFL_Projections,Results}.py
    calibration_picks.py, nhl_precompute.py, nfl_precompute.py
    .github/workflows/{nightly-data,slate-picks}.yml
    tests/test_nhl_pipeline.py, tests/test_nfl_pipeline.py, tests/test_nhl_model.py

---

## PICK UP HERE — the first model nightly died on a file a TEST wrote. 2026-10-03 (6)

**Suite 121, FAILING: none.** One negative control red by exit code.

### WHAT THE FIRST REAL RUN SAID (before it died)

    MLB  2,430 finals, 2,428 with both starters, 376/376 start logs.
         walk-forward 2,415 games: log loss 0.6847 vs coin 0.6931 vs
         home-rate 0.6924. Starters USED (team-only 0.6876).
         Totals MAE 3.555 vs league-average 3.567 — barely better.
    NHL  fit on 2025-26: 1,292-game walk-forward 0.6874 vs 0.6931/0.6939.
         All SIX skater markets beat the skater's own rate (17,343 each).
         Goals came back Poisson (dispersion None), as hockey should.
    NFL  2025 fetched (272). Walk-forward 0.6441 vs 0.6931/0.6988;
         margin MAE 10.66 vs 11.44 home-edge; total MAE 10.96 vs 10.97 —
         the TOTAL is a tie with the league average. Say so; don't tune.

The MLB prop model did NOT run: it lives in precompute.py, which comes
after the step that failed. Its verdicts arrive with the next nightly.

### THE FAILURE

tests/test_calibration_picks sandboxed RECORD_PATH but not
MLB_SLATE_PATH. In CI the schedule fetch works, so each of its six
cp.main() calls rewrote the REAL data/mlb/games.json — silently, for
weeks. Harmless until "Commit MLB game model" (new today) did `git pull
--rebase --autostash` while upstream had a fresh games.json: the stash
pop conflicted, that step still pushed, and "Commit NFL projection log"
died on `U data/mlb/games.json` (exit 128) — after every model was built,
before the archive was published or Render redeployed.

Fixed twice: the test stubs the slate writer and sandboxes its path; and
nightly-data.yml now has "Restore any tracked files the tests touched"
between the tests and the first commit — a future leak is a ::warning::
with the file list, then restored. tests/test_ci_hygiene.py pins the
step's existence and position. (Offline, test_calibration_picks never
reached the network, so the leak was invisible locally — rule 5 again.)

### FILES, 2026-10-03 (6)

    tests/test_calibration_picks.py   slate writer stubbed + sandboxed
    .github/workflows/nightly-data.yml restore step after Run tests
    tests/test_ci_hygiene.py          NEW

---

## PICK UP HERE — a day with no WNBA games took the late refresh red. 2026-10-03 (5)

**Suite 120, FAILING: none.** Two negative controls red by exit code.

The 10-03 `intl-late-refresh` run failed at the WNBA step with "every
ESPN scoreboard source failed". It had not: site.api answered a REAL
scoreboard with events=[] — there were no games — while cdn.espn gave
nothing parseable and the header gave no scoreboard. require_events=True
counted the honest empty answer as a failure, and the step's red took
the whole job red although NPB and KBO had succeeded.

`espn_wnba.fetch_today()` runs the require_events=True pass first (so on
a game day a host answering [] cannot shadow one with the slate), and
only if nobody has games accepts an empty answer — and only from a host
that returned a real scoreboard. All hosts broken still raises, naming
each. wnba_precompute.main uses it; the downstream "zero box scores ->
refuse to publish" guard is untouched and still catches real outages.

Fixture lesson (rule 5): the source NAMED "site.api" is served from
site.web.api.espn.com, so a fake that routes by hostname hands every
source the wrong answer. Route by URL path. And a bare {"id"} event is
correctly dropped by _normalize_header_events — game-day fixtures need
a full competitions block.

### FILES, 2026-10-03 (5)

    app/engines/espn_wnba.py   fetch_today()
    wnba_precompute.py         tonight via fetch_today
    tests/test_wnba_off_day.py NEW — replays the logged responses

---

## PICK UP HERE — NFL game model: the site's own line beside the market's. 2026-10-03 (4)

**Suite 119, FAILING: none.** Three negative controls red by exit code.
**No extra workflow:** the first nightly after this lands fetches the
2025 season (~125 scoreboard calls) into data/nfl/prior_season.json and
the existing "Commit NFL projection log" step commits it; later nights
read it.

### WHY

nfl_projection anchors TDs to the MARKET's implied points — right for a
prop, but a board anchored to the line can never disagree with it.
`engines/nfl_game_model.py` is the independent opinion: points per side
from game_model's pairing on ESPN team ids, margin and total treated as
NORMAL with SDs measured as walk-forward residuals (the one assumption,
named on the page). Gives win %, fair spread, P(cover) on the posted
spread (read only through implied_totals' favourite check — a line that
contradicts itself gets no cover probability and says why), P(over),
and the no-vig moneyline gap.

Fitted on 2025 while 2026 has four weeks (same carryover machinery as
NHL); validation reports log loss vs coin and home-rate, margin MAE vs
"home team by the league's usual edge", total MAE vs league average.

### FOR THE FIRST LOG

    [verify] NFL 2025 prior season: 272 regular-season finals
    [verify] NFL model fit on prior season: k=.. carryover=.. sd_margin=~13-14
    [verify] week games with a projection: 16 of 16 (or 14 on a bye week)

Under 250 prior finals is REFUSED and not written (a partial season
written once would be read forever); the model then fits on 2026 alone
that night and the log says so.

### FILES, 2026-10-03 (4)

    app/engines/nfl_game_model.py, app/views/NFL_Model.py, nfl_prior_season.py  NEW
    tests/test_nfl_game_model.py                                                NEW
    nfl_precompute.py         ids on finals, PRIOR_PATH, model block + per-game model
    .github/workflows/nightly-data.yml   commit step also adds prior_season.json
    app/app.py                NFL -> Model subpage
    tests/test_nfl_pipeline.py (PRIOR_PATH sandboxed), tests/test_nfl_nhl_wiring.py

---

## PICK UP HERE — NHL game model + skater props, standing on last season. 2026-10-03 (3)

**Suite 118, FAILING: none.** Four negative controls red by exit code.
**Run the `NHL prior season` workflow ONCE** (manual; commits
data/nhl/prior_season.json, ~1,300 box scores), then the nightly. Until
the prior file exists the model fits on this season alone and says so.

### WHY LAST SEASON

The season opened 09-29. A few dozen finals cannot fit anything and a
three-game team rating is noise, so `engines/nhl_model.py` fits on
2025-26 and starts each team from its 2025-26 rating REGRESSED by a
measured carryover (split-half slope inside the prior season — the
weaker stand-in for a year-to-year fit, stated on the page). This
season's games then move each team through the fitted shrinkage. League
constants (home edge, OT home-win rate) come from the SAME season as
the fit — measured on this week's handful they were noise; asserted.

### THE TRAP THE FIXTURE CAUGHT

The site.web.api HEADER shape — the one production actually gets —
DROPS ESPN's season block (`_normalize_header_events` rebuilds events
without it). The collector required season.type == 2, so against the
real feed it would have kept **0 of 900** finals. It now falls back to
the 2025-26 regular-season date window when the type is absent; the
control proves the 0-of-900.

### WHAT IT IS

Goals: game_model on ESPN team ids, market moneylines and total parsed
by `espn_feed.odds_of` (both published shapes, EVEN = +100). Shots: the
same pairing fitted on squared error (`game_model.fit_volume`) — volume
is the output, not a winner. Skaters: SOG/G/A per game, gamma-Poisson
shrunk toward F or D, scaled by tonight's team shot and goal ratios;
SOG negative binomial with measured size. Props validated walk-forward
on the last 60 days of 2025-26 against each skater's own hit rate.

### ALSO

`tests/test_nfl_nhl_wiring` asserted the NHL nav EQUALS three pages and
went red when Model was added — rewritten as a floor plus an exists-on-
disk check (rule from 08-17: adding is not a regression; losing is).
`nhl_precompute.PRIOR_PATH` is module-level so test_nhl_pipeline runs
against no prior file and stays a parser test.

### FILES, 2026-10-03 (3)

    app/engines/nhl_model.py, app/views/NHL_Model.py, nhl_prior_season.py   NEW
    .github/workflows/nhl-prior-season.yml                                  NEW
    tests/test_nhl_model.py                                                 NEW
    nhl_precompute.py         ids on finals, model block in games.json
    app/engines/game_model.py score_only walk-forward, fit_volume, constants
    app/engines/espn_feed.py  moneylines in odds_of
    app/app.py                NHL -> Model subpage
    tests/test_nhl_pipeline.py, tests/test_nfl_nhl_wiring.py

---

## PICK UP HERE — MLB game model + props, every number fitted or measured. 2026-10-03 (2)

**Suite 117, FAILING: none.** Six negative controls red by exit code.
Built and tested against simulated seasons in statsapi's / Statcast's
real shapes — the audit box cannot reach either. **First real run is
the nightly: dispatch Nightly Statcast Data once, read the [verify]
lines, then open MLB -> Model.**

### WHAT IT IS

`engines/game_model.py` (shared with NHL): offense x opponent defense /
league x home multiplier per side -> negative-binomial runs -> win %,
fair line, total. `engines/model_math.py` holds the distributions, odds
and fitters, once, for every sport. MLB adds a STARTER LAYER
(`engines/mlb_game_model.py`): his share of the game (outs/start) and
his RA9, each shrunk by a gamma-Poisson prior fitted over every starter.

Nothing chosen by eye: shrink_k is fitted by walk-forward log loss,
dispersion by method of moments on the residuals, home/road and the
extra-inning home win rate are measured. **The starter layer is only
used if the walk-forward says it beats team-only** (`use_starters`).

Props (`engines/mlb_props.py`, builder `mlb_prop_precompute.py`, called
from precompute.main on the season frame it already holds): per-PA
outcomes by odds-ratio (batter x pitcher / league), beta-binomial priors
fitted per outcome, PA count from slot + the measured team-PA histogram,
starter exposure from his real batters-faced. Each market is scored
walk-forward over the last 30 days against the player's OWN hit rate;
markets that do not beat it are starred on the page.

### WHAT TO CHECK IN THE FIRST NIGHTLY LOG

    [verify] N finals ... with both starters      -> ~2,400, nearly all
    starters used: True/False (team-only X, with starters Y)
    [verify] Hits O0.5 ... BEATS / does not beat baseline   (x5 markets)

A market that does not beat baseline is a FINDING, not a bug — rule 10.

### THE BUG THE FIRST DRAFT HAD

`clean_finals` rebuilt each row from five fields and dropped the starter
ids, so "with starters" scored identical to team-only to four decimals.
Rows now carry every key; asserted, control red.

### KNOWN LIMITS, STATED ON THE PAGE

Props leave out park, weather, platoon and the specific bullpen. Starter
priors are fitted on full-season totals (two numbers of look-ahead).
`inning_topbot` rides in the season frame only (MODEL_COLS) and never
reaches a per-player parquet, so ENGINE_COLS == _KEEP_COLS still holds.
Not yet done: calibration_picks does not write the model into
games.json, so Home's best-games card does not use it.

### FILES, 2026-10-03 (2)

    app/engines/{model_math,game_model,mlb_game_model,mlb_props,model_view}.py  NEW
    app/views/MLB_Model.py              NEW page, listed after Game Card
    mlb_model_precompute.py, mlb_prop_precompute.py                  NEW
    app/views/GameCard.py               Game Model card + prop expander
    app/views/Home.py                   Explore card for Model (test_home)
    app/app.py, precompute.py, .github/workflows/nightly-data.yml
    tests/test_game_model.py, tests/test_mlb_props.py                NEW

---

## PICK UP HERE — audit before the model: clean, plus one time bomb defused. 2026-10-03

**Suite 115, FAILING: none.** One negative control red by exit code.
Audited on a bare container: all 114 prior scripts green, compiles under
a real 3.11, pyflakes zero undefined names, every view rendered in
AppTest with zero exceptions (offline — live feeds are blocked from the
audit box, so this proves no-crash paths, not live numbers).

### THE ONE REAL FINDING

Eight call sites still passed `use_container_width=`, which Streamlit
marks "will be removed after 2025-12-31". 1.59.2 still accepts it, so
nothing was broken — but app.py's nav uses it, so the first Streamlit
bump that drops it takes down EVERY page at once. All eight now use
`width="stretch"` / `width="content"` (Home keeps its compact switch).
`tests/test_no_deprecated_width.py` is tokenize-based, so the word in a
comment never counts, and self-checks its own detector first.

### HOUSEKEEPING

`dedupe-fix.zip` deleted from the repo root — byte-identical to the
09-27 (4) batch already on main. `*.zip` was listed twice in
.gitignore. README now names NFL/NHL and the real suite size.

### FILES, 2026-10-03

    app/app.py, app/views/{Home,HR_Edge_Board,GameCard}.py
    app/engines/{bvp,trend_chart,calibration_trend}.py
    tests/test_no_deprecated_width.py   NEW
    README.md, HANDOFF.md, .gitignore   dedupe-fix.zip DELETED

---

## PICK UP HERE — 49 entries for 16 games, and two dead pages. 2026-09-27 (4)

**Suite 114, FAILING: none.** Eight negative controls red by exit code.
Verified by rendering every page against the ACTUAL broken live file.

### THE FEED ANSWERS A DATE WITH A WEEK

`nfl_precompute` walks every day from the opener to the end of the
week. **ESPN's NFL scoreboard answers any date inside the current week
with the WHOLE week's fixtures**, so each of those days handed back the
same sixteen games and every one was appended again.

The 09-27 file held **49 entries for 16 real games**, each player three
or four times on every board, and both the Projections page and The
Week died outright on `StreamlitDuplicateElementKey`.

**The numbers were never wrong.** Each duplicate carried the same
correctly-normalised projection; `logs` was already keyed by event id so
league constants and team profiles were untouched (team_games 66 was
right all along). Only the ROWS multiplied.

`week_events` and `finals` are dicts keyed by event id now, not lists.
A later fetch of the same event overwrites the earlier one, which is
what we want: the last read carries the freshest status and score.

### AND NO VIEW SHOULD HAVE DIED OF IT

A duplicate Streamlit key raises, and that takes the WHOLE page down —
not one card. Three keys were data alone: the projection cards on the
player's NAME (not unique; the league has had two Michael Thomases), and
both game cards on the event id. All three now carry a positional slot,
so a future duplicate draws an odd card instead of a blank page.

Both hardenings are asserted in `test_nfl_nhl_wiring`, with controls.

### THE FIXTURE COULD NOT HAVE CAUGHT THIS

`test_nfl_pipeline`'s fixture gave each day its own games — the one
shape the live feed never has. There is now a second fetcher in that
file returning the same week-2 fixtures for all seven days of the week,
which is what ESPN actually does, and it asserts each game and each
player appears ONCE. Rule 5, again: a fixture that does not reproduce
production's shape is not a test of production.

### FILES, 2026-09-27 (4)

    nfl_precompute.py               week_events/finals keyed by event id
    app/views/NFL.py                game card takes a positional slot
    app/views/NHL.py                same
    app/views/NFL_Projections.py    projection cards keyed by position
    tests/test_nfl_pipeline.py      section 8 — the week-wide feed replayed
    tests/test_nfl_projection.py    section 9 — dedupe + key shape
    tests/test_nfl_nhl_wiring.py    no view keys a card on data alone

---

## PICK UP HERE — the anytime board was twice as confident as reality, and is rebuilt. 2026-09-27 (3)

**Suite 114, FAILING: none.** Seven negative controls red by exit code.
Validated against the REAL week-3 slate pulled from the nightly release,
not a fixture.

### WHAT THE PROBE FOUND

Walk-forward over weeks 1-3 (`nfl_projection_probe`, 09-27):

    projected 0- 9%  ->  actually scored 16.2%   (n=185)
    projected 50-59% ->  actually scored 33.3%   (n=9)
    projected 90-99% ->  actually scored 50.0%   (n=6)

Every band above 30% came in around half its claim, and there was no
middle at all: 185 of 243 player-games sat in 0-9% and the rest jumped
past 30%. Measured on the real slate, **65% of skill players had a flat
0%** against a **23.0% real base rate**, while a tight end with ONE score
in ONE game rendered at 88%.

Cause: splitting a team's expected touchdowns by the player's share of
its ACTUAL scores. On three games that is noise — zero for most, and
enormous for whoever happened to score.

### THE REBUILD

Share now comes from OPPORTUNITY (carries + targets, which repeats) x
his own conversion rate, shrunk toward the league by a beta-binomial
prior, then normalised so a team's players divide its expected TDs.

**The shrinkage is fitted, not chosen.** `td_opportunity_prior()` fits
the prior by maximum likelihood over every skill player in the league,
by golden-section search on log(strength). Method of moments was tried
first and rejected: it needs a minimum-touches cutoff to keep its
variance estimate sane, and that cutoff would be a number chosen by eye
(rule 1).

Result on the real slate:

    live before   mean 18.1%   zeros 65%   median  0.0%   max 90.8%
    rebuilt       mean 21.7%   zeros  0%   median 18.0%   max 76.0%
    reality       23.0%

**The fitted strength came out at 164 touches, and the likelihood is
nearly flat above it** (-590.4 at the fit vs -590.7 at 1000). That is a
real finding, not a fitting artefact: after three weeks the data cannot
yet tell one converter from another, so the honest model is "scores
follow the ball". As real differences emerge the fitted strength falls
on its own and good red-zone players come through. **Nothing to retune
by hand — do not add one.**

The board now leads with Henry, Walker, Gibbs, Taylor, which is how
anytime markets actually behave.

### THE YARDAGE MARKETS DO NOT BEAT A SEASON AVERAGE

Also from the probe, and left alone deliberately:

    rushing yards   projection 25.01  vs season average 25.09
    receiving yards            25.53                    25.90
    receptions                  1.86                     1.83  (loses)

Within noise on every market. The matchup multiplier is NOT earning its
complexity — but it was not removed, because three weeks is too thin to
kill a feature on (rule 10), and it is the mechanism that expresses the
matchup the page exists to show. **It is now stated on the page** that
these test within noise of a season average. Re-measure in a few weeks;
if it still does not separate, drop it.

### WHAT IS STILL OPEN

- Re-run the probe now the estimator has changed. The calibration curve
  is the check, and it has NOT yet been run against the rebuild.
- No grader still. The dated projection log accumulates; nothing scores
  it.
- The tests above this batch pass NO prior, so they exercise the
  fallback path. The new path has its own section; keep both.

### FILES, 2026-09-27 (3)

    nfl_precompute.py               td_opportunity_prior() + fitted into league
    app/engines/nfl_projection.py   attach_td_shares rebuilt; TD/touch, touches on the row
    app/views/NFL_Projections.py    TD/touch column, rewritten explanation, measured-honesty note
    tests/test_nfl_projection.py    section 8 — the new estimator, 7 controls

---

## PICK UP HERE — a test of mine took the whole nightly down. 2026-09-27 (2)

**Suite 114, FAILING: none.** Four negative controls red by exit code,
**two of which came back green first** (below).

### THE OUTAGE

The 09-27 nightly ran, built the projections, wrote
`data/nfl/projections/2026-09-27.json` and committed it — correctly.
The NEXT nightly then failed at the "Run tests" gate and refused to
fetch anything, for every league, MLB included.

The failing check was mine, from the batch hours earlier:

    check("running the pipeline left no fixture projections in the repo",
          not _repo_log.exists() or not any(_repo_log.glob("*.json")))

It asserts that directory is EMPTY. But the whole point of that
directory is to fill up: main() writes a file there every run and the
workflow commits it. So the first successful night guaranteed every
later night would fail. A self-blocking gate, shipped green, because
locally the directory was empty and stayed empty.

**The property I meant** is that running the pipeline UNDER TEST adds
nothing to the real record — not that the record is empty. Now
snapshotted before and compared after. Guard the thing you mean.

### AND THE FIRST FIX COULDN'T FAIL EITHER

Comparing the SET OF FILENAMES before and after passed both negative
controls on any day the log already held a file: a leak writes to
TODAY's filename, so the name set is unchanged while the real record has
been silently overwritten with fixture data. The comparison is now over
sha256 of the contents, and the controls are run in both repo states —
clean, and with a committed file present.

### WHAT THE NIGHTLY PROVED BEFORE IT BROKE

The league constants came out of 66 real team-games at
**td_per_point 0.1096, ypc 4.20, yards/target 7.61, catch rate 0.684** —
every one where real football sits. The measurement path is sound; only
the test was wrong.

### FILES, 2026-09-27 (2)

    tests/test_nfl_pipeline.py   emptiness check -> before/after content hash

---

## PICK UP HERE — projections for every NFL market, with no fitted weights in them. 2026-09-27

**Suite 114, FAILING: none.** 15 negative controls red by EXIT CODE —
**three came back green first** (section 5). Every page rendered in
AppTest against current-week data with zero exceptions; all files
compile under a real 3.11.

### 0. FIRST: THE 09-18 BATCH NEVER LANDED

The repo had three NFL tabs and no `live_days`, so that whole batch —
the week-wide live overlay, the final result line, the how-to-read
panels — was rebuilt here from scratch. **Check `git log` against the
handoff before assuming a batch shipped.** What reached production was
the 09-16 build, which is why Thursday's final still sat on the card as
"scheduled" days later.

### 1. WHAT THE PROJECTION IS

`app/engines/nfl_projection.py`. A projection is a volume times a rate:

    expected volume    = his share of his team's carries or targets
                         x his team's carries or targets a game
    matchup multiplier = what the defence allows per attempt
                         / the league average per attempt
    projected yards    = volume x his own rate x that multiplier

Touchdowns anchor to the MARKET rather than to our own guess at scoring:

    implied points = (total -/+ spread) / 2          EXACT arithmetic
    team TDs       = implied points x td_per_point   MEASURED nightly
    lambda         = team TDs x his share of them
    P(anytime)     = 1 - exp(-lambda)                THE ONE ASSUMPTION

Nine markets: anytime TD, rushing and receiving yards, receptions,
targets, carries, passing yards, attempts, scrimmage yards.

### 2. NO FREE PARAMETERS, DELIBERATELY

Rule 1 is the whole design constraint. There is no blend weight, no
shrinkage factor, no fitted coefficient anywhere in the engine. Every
constant it divides by — `td_per_point`, league ypc, yards per target,
catch rate — is recomputed by `league_constants()` from the season's
real finals on every nightly, shipped in games.json, and printed in the
run log and on the page. Every multiplier is a ratio of two measured
numbers.

That is a v1 restriction, NOT a claim of optimality, and the page says
so. Three questions stay open and `nfl_projection_probe.py` measures
them walk-forward (profiles from weeks before W, projections for W,
scored against W's real box scores):

  1. does the full-strength matchup multiplier help, or overshoot?
  2. does a share measured over a few games predict the next one?
  3. is the Poisson anytime step calibrated?

It prints mean absolute error against two baselines — his season
average and his last game — and says outright when the projection
**does not beat the season average**, because a model that cannot is
not earning its complexity. **Run it (`NFL projection probe`, manual)
before trusting any of this, and again every few weeks.**

### 3. THE SAMPLE TRAVELS WITH THE NUMBER

A TD share of 2-of-2 and one of 9-of-18 both read as "high" and are not
the same claim. There is no shrinkage applied to the first — that would
be a number chosen by eye — so the raw fraction is a COLUMN ("3 of 4")
and appears in the why-line. In the fixture a 1-of-1 player outranks a
3-of-4 player, which is the honest output and exactly why the counts
are on the row.

Every row also carries the arithmetic that produced it, as a sentence:
share → volume, own rate → adjusted rate, implied points → team TDs →
lambda. A projection nobody can take apart is indistinguishable from
one that was made up.

### 4. THE LINE IS CHECKED AGAINST ITSELF

ESPN states `spread` relative to the HOME team. That convention is the
one thing that could silently invert every projection on a card, so
`implied_totals` does not trust it: `details` names the favourite by
abbreviation, and when the name contradicts the sign it returns **no
implied totals at all** plus the reason, which the page prints. A
backwards implied total would not look wrong — it would look like a
confident projection of the wrong team.

### 5. THREE CONTROLS CAME BACK GREEN

- **"defensive rates read from own offence"** — the fixture hand-wrote
  `ypc_allowed` into the team profiles, so `team_research`'s defensive
  computation was never executed. Rule 2, exactly: a fixture cannot test
  a constant it replaces. Now run on real finals and asked directly.
- Then that new check ALSO could not fail: the fixture's MIA rushed 2
  for 10, so their own ypc and the 130/26 they allowed were both 5.00.
  Two different behaviours, one number. Changed to 2 for 4.
- **"live overlay today-only"** and **"Projections dropped from nav"** —
  no tests existed for either; both were lost with the 09-18 batch.

### 6. THE LOG, AND WHAT IS STILL MISSING

The nightly writes each slate's projections to
`data/nfl/projections/<date>.json` **in the repo**, committed by its own
workflow step — build_data/ is rebuilt every run, so a record written
there cannot accumulate. Only games that have NOT kicked off are logged:
a projection made after the whistle is not a projection.

**NOT BUILT: the grader.** Nothing yet scores those logged files
against box scores or puts NFL on the Results page. The log exists so
that when the grader is written there is a real record to grade rather
than a standing start. That is the next job, with the probe.

Also absent, and stated on the page: no sportsbook prop lines. The
public feed carries game odds only, so the board projects and the
reader compares against his own book. Do not invent lines to fill that
column.

### 7. THE SUITE WAS WRITING INTO THE REAL PROJECTION LOG

Caught only because an uncommitted-changes check flagged a `data/nfl/`
that had been deleted minutes earlier. `main()` writes the log to a REPO
path on purpose — that is the only way it accumulates — so every run of
`tests/test_nfl_pipeline.py`, which calls `main()` four times against
synthetic games, filed fixture projections under today's date. Nothing
in the file would have said so, and a grader reading it later would
have scored claims the site never made, for players who were never on
the slate.

The path is now the module constant `nfl_precompute.PROJECTION_LOG`,
the test redirects it to a temp dir, and a check asserts the repo log is
empty after the suite runs. Both controls red. **Any future test that
calls main() must redirect it too.**

### FILES, 2026-09-27

    app/engines/nfl_projection.py     NEW  the engine
    nfl_projection_probe.py           NEW  walk-forward measurement
    app/views/NFL_Projections.py      NEW  the board
    nfl_precompute.py                 team_game_usage, league_constants, per-attempt
                                      allowed rates, shares, TD counts, projection log
    app/engines/nfl_week.py           live_days()
    app/styles/kc_theme.py            how_to_read()
    app/views/NFL.py                  week-wide overlay, final result line, panel
    app/views/NFL_Mismatch.py         panel
    app/views/NFL_Props.py            panel
    app/views/NHL_Crease.py           panel
    app/views/NHL_Shots.py            panel
    app/app.py                        "Projections" in the NFL nav
    .github/workflows/nightly-data.yml      commit the projection log
    .github/workflows/nfl-projection-probe.yml  NEW  manual
    tests/test_nfl_projection.py      NEW
    tests/test_nfl_pipeline.py        live_days checks
    tests/test_nfl_nhl_wiring.py      Projections page, panels, log committed

Suite 113 -> 114.

---

## PICK UP HERE — NFL and NHL are live tabs, each built its own way. 2026-09-15

**Suite 113, FAILING: none.** 18 negative controls, all red by EXIT
CODE, and **one came back green on the first attempt** (section 5).
Every new page rendered with zero exceptions in Streamlit's AppTest
harness in all four data states: full, stale, preseason, nothing on disk.
All files compile under Python 3.11 (Render's version), checked with a
real 3.11 interpreter rather than the 3.12 container.

Repo audit first, before any change: 110/110 green, pyflakes zero
undefined names, the pipeline alive (MLB slate for 09-15 on disk, HR
research log grading into September).

### 1. WHY EACH LEAGUE LOOKS DIFFERENT

**NFL is a WEEK, not a night.** Football is researched days ahead and a
week runs Tuesday to Monday, so `data/nfl/games.json` is stamped
`week`, `week_start_et`, `week_end_et`. Three pages:

- **The Week** — every game grouped by TV window (TNF, Sunday
  Early/Late/Night, MNF), line, weather or roof, network, injuries, key
  players, and a ranked tale of the tape.
- **Mismatch Finder** — every offense-vs-defense pairing on the slate,
  sorted by `edge = defender rank - attacker rank`. Tiers are the gap as
  a share of the league (60/35/15%) and are labelled as DISTANCE, not
  probability. Nothing fitted.
- **Prop Lab** — QBs / backs / pass-catchers, season / L3 / last game,
  beside what the opposing defense allows in that phase.

**NHL is the crease and the shot clock.** Nightly Eastern slate.

- **Tonight's Ice** — goalie duel, top shooters, tale of the tape
  (W-L-OTL, points %, shot share, PP/PK), and a countdown banner.
- **Crease Report** — every goalie: starts, crease share of the last 10,
  pooled SV%/GAA, L5 SV% over STARTS, SA/60.
- **Shots Lab** — per-game SOG/P/G/A/TOI/HIT/BLK for season, L10, L5,
  plus hit-rate COUNTS (2+ SOG, 3+ SOG, 1+ PT).

Neither logs calibration picks, which is why Home still lists no board
for either (test_wnba_routing_and_home_scope still passes as written).

### 2. DATES — VERIFIED, NOT ASSUMED

NFL 2026 kicked off **Wed Sep 9**; week 1 is Tue Sep 8 – Mon Sep 14, so
`week_of` counts from `WEEK1_TUESDAY`. NHL preseason is **Sep 19–26**,
opening night **Tue Sep 29** (84 games). Both checked against the
leagues' own announcements on 09-15. Next season these constants move —
`nfl_week.SEASON_START/WEEK1_TUESDAY`, `nhl_rink.PRESEASON_START/
REGULAR_SEASON_START`.

### 3. WHY NFL IS NOT IN slate_guard

slate_guard compares ONE date. A week is a range, and stamping a fake
single date on it is a right number under a wrong label (rule 9). So
`nfl_week.load_week` applies the same contract to the range: a week that
ended before today returns `games=[]` and the state "stale". NHL IS in
slate_guard (`slate_date_et`, Eastern) and uses the existing
future-slate branch for its lookahead.

`slate_guard.payload_field(league, key)` is new: side tables beside the
games (the goalie sheet) are read through the guard's own file choice
instead of a second hand-rolled read.

### 4. PRESEASON IS PARSED AND COUNTED NOWHERE

Exhibition box scores are the wrong sample (split squads, prospects),
but they are REAL hockey box scores two weeks before opening night. So
`nhl_precompute` parses them, reports `exhibition_finals_parsed`, and
excludes them from every number. That makes Sep 19–26 a free parser
check. **Read the nightly log on Sep 20 for the `[verify]` line.**

An OT loss is an OTL only when the summary says so (`period > 3`, or
"OT"/"SO" in the detail). A loss whose length cannot be known is counted
as regulation AND flagged on the profile (`otl_unverified`) and on the
card — never silently guessed.

### 5. THE CONTROL THAT STAYED GREEN

"Credit every goalie in the game with a start" passed the first NHL
fixture, because every fixture game had exactly one goalie per team — so
correct and broken were indistinguishable (rule 4, again). Fixed by
adding a RELIEF appearance (Kochetkov pulled, Andersen finishes); now
the control is red and the test also proves a relief outing is a GP, not
a start, and that L5 SV% reads starts only.

### 6. WHAT IS NOT MEASURED — SAY IT OUT LOUD

**ESPN's NFL and NHL feeds have not been measured from Actions.** They
are the same hosts the WNBA probe measured with a different sport
segment, and `espn_feed` reuses espn_wnba's `get_json` and
`_normalize_header_events` rather than copying them. Box-score column
names are matched two ways (machine `keys`, then display `labels`), and
both fetchers refuse to publish when finals exist but nothing parsed.

**Run the `NFL + NHL feed probe` workflow once** (manual, touches
nothing). It prints each host's status and shape, every player group's
keys/labels, and what the real parsers read. If a column is missing,
add its name to the alias tuple at the top of the fetcher — do not
default it to zero.

Also not built: NFL playoffs (the page says so after week 18), NHL
playoffs, confirmed NHL starting goalies (crease share is labelled as
NOT a confirmation), and caching of past NHL summaries — by March the
NHL backfill is ~1,000 summary calls a night. Measure its runtime in
the nightly before optimising.

### FILES, 2026-09-15

    app/engines/espn_feed.py          NEW  league-parameterised ESPN access
    app/engines/nfl_week.py           NEW  week math, week guard, mismatches, prop rows
    app/engines/nhl_rink.py           NEW  phase/countdown, crease + shots rows, tape
    app/engines/slate_guard.py        nhl registered; payload_field()
    app/views/NFL.py                  REWRITTEN (was coming-soon)
    app/views/NFL_Mismatch.py         NEW
    app/views/NFL_Props.py            NEW
    app/views/NHL.py                  REWRITTEN (was coming-soon)
    app/views/NHL_Crease.py           NEW
    app/views/NHL_Shots.py            NEW
    app/app.py                        NFL + NHL subpage navs
    app/styles/kc_theme.py            caption: "...NFL · NHL live — NBA soon"
    nfl_precompute.py                 NEW  (repo root)
    nhl_precompute.py                 NEW  (repo root)
    nfl_nhl_probe.py                  NEW  (repo root)
    .github/workflows/nightly-data.yml   NFL + NHL steps, verifier entries
    .github/workflows/nfl-nhl-probe.yml  NEW  manual
    tests/test_nfl_pipeline.py        NEW
    tests/test_nhl_pipeline.py        NEW
    tests/test_nfl_nhl_wiring.py      NEW

Suite 110 -> 113.

---

## PICK UP HERE — the longest window on the card was under the stabilisation point. 2026-08-17 (3)

**Suite 108, FAILING: none.** Seven negative controls red by exit code.
One existing test went red on a CORRECT change and was rewritten — that
is section 3.

### 1. THE PROBLEM: 25 GAMES IS ~110 PA

The Game Card's longest batter window was Last 25 Games / Last 60 PA.
Against the published stabilisation points:

    HR rate       170 PA        <- the longest window was UNDER this
    ISO           160 AB        <- and this
    HR/FB          50 FB
    barrel/EV/LA   50 BBE       (~18 games — well covered already)

So every power read on the lineup table was taken on a sample too thin
for the stat being read. The contact-quality columns were fine; the
outcome-shaped ones were not, and they rendered in the same font.

Added, batter side: **Last 75 / Last 50 Games** and **Last 300 / 250 /
200 PA**. Ask in PA when the target is a PA count — games-to-PA moves
with playing time, so a platoon bat's 50 games is ~150 PA where a
regular's is ~215.

Pitcher splits went Season / L10 / L5 / L3 / Last game. Added **L25 /
L20 / L15** (~140 / 110 / 85 IP).

### 2. WHAT THE PITCHER WINDOWS ARE NOT FOR

Everything on the pitcher side that stabilises does so around **70
balls in play — five or six starts**. L15, L20 and L25 are all well
past it, so the longer two buy no extra stability, only more April.
**L15 is the one to use.**

And the number a long pitcher window LOOKS like it should give you is
the one it cannot: a pitcher's HR rate needs ~1,320 batters faced,
HR/FB ~400 fly balls. That is 200+ innings, more than a season. **No
window offerable in-season makes HR-allowed reliable.** Use these for
the batted-ball profile — FB%, hard contact allowed, what the arsenal
does — which is what zone_adj already leans on. The comment above
_sw_opts says this so the next reader does not have to rediscover it.

### 3. A TEST FROZE THE MENU INSTEAD OF THE PROPERTY

`test_pitcher_splits_window` asserted
`set(opts.values()) == {season, l10, l5, l3, l1}` — exact equality. It
went red the moment a window was ADDED, which is a correct change
failing a test that had pinned the wrong thing.

Rewritten as a floor: the short windows must SURVIVE (they are the "is
he right, right now" read the control exists for), the long ones must
be present, and everything offered must really slice. **Adding a window
is not a regression; losing one is.** Both directions have controls —
dropping L3 and dropping L15 each fail it now.

Its 12-game fixture also made a correct L25 look like a no-op, so the
frame builder is parameterised and section 2 measures against 60 games.
Same bug shape in the new test on its first run: the vacuity guard
counted deduped window KEYS (14 across three controls) rather than the
controls themselves. Guard the thing you mean.

### 4. THE LONG WINDOWS LIE QUIETLY, AND THE CONTROL SAYS SO

Every slice is a `tail()`. Ask for the last 250 PA from a rookie with
90 and you get 90, correctly computed, under a label reading 250.
Nothing errors, no rate is wrong — the sample is just a third of what
the label claims, next to a veteran's real 250.

This is the mirror of THIN_WINDOWS, so `LONG_WINDOWS` now exists beside
it in recency_windows with that written down, the lineup control
carries help text saying it, and a test asserts the help text still
says it. Also worth remembering: **the parquet only holds this season.**
In April every long window IS the season; by late August "Last 300 PA"
and "season" converge for an everyday bat. These windows earn most from
April to June.

### FILES TOUCHED, 2026-08-17 (3)

    app/engines/recency_windows.py       l20/l50/l75/l200/l250/l300 + LONG_WINDOWS
    app/views/GameCard.py                both window controls + help text
    tests/test_pitcher_splits_window.py  exact set -> floor; fixture parameterised
    tests/test_long_windows.py           NEW

Suite 107 -> 108.

### NOT MEASURED — SAY IT OUT LOUD

The stabilisation points above are PUBLISHED research, not measured on
this model. Carleton has since warned that a stat at its stabilisation
point is not thereby predictive of the NEXT sample of the same size.
Which window best predicts an actual HR **for this model** is an open
question the research log could answer — it already carries per-bat
components and graded outcomes. **No window here is a measured default,
and none is set as the default.** Season still is.

Still standing: **do not touch HR Edge.** Rule 10.

---

## PICK UP HERE — the morning lineup now says which parts it is unsure about. 2026-08-17 (2)

**Suite 107, FAILING: none.** Eight negative controls, red by EXIT
CODE — and **two of them came back green on the first attempt and had
to be fixed.** That is in section 4 and it is the most useful part of
this entry.

### 1. THE PROBLEM

Slate breakdowns get recorded in the MORNING. MLB posts a real lineup
1-3 hours before first pitch, so at 8am there is no lineup for any game
on the board — not here, not at Rotowire, nowhere. Every morning read
is a projection.

Measured on our own research log, 2026-08-12..16:

    ~80% of a team's bats repeat from one game to the next
    40% of bats started EVERY game their team played
    28% started two thirds or more
    24% sat between a third and two thirds   <- the coin flips
     9% rare

So last night's nine gets about seven right and two wrong, every night,
and the two are not random: catcher, platoon corner, DH rotation.

**The uncertainty is not evenly spread, and that is the whole opening.**

### 2. AND THE SLOT BARELY MATTERS — CHECK THE MODEL'S OWN NUMBERS

From the same log, mean absolute contribution per rated bat:

    slot_adj    0.59   (capped +/-1.2)   <- the smallest term in the model
    zone_adj    3.80   (range -9..+15)
    pen_adj     1.99
    ctx_adj     1.97

Batting 2nd instead of 5th moves a bat by at most 2.4 points. A bat who
does not play at all costs the whole pick. **Second-guessing the ORDER
in the morning is solving the wrong problem; presence is the problem.**

### 3. WHAT SHIPPED

`lineup_lock_precompute.py` (new, nightly) — per team, how often each
bat actually started over the last WINDOW_GAMES completed games, plus
the same split by the hand of the opposing STARTER. Every start counted
is a real posted lineup from MLB's boxscore endpoint. Writes
`data/mlb/lineup_lock.json`, committed by the nightly like
calibration.json. Self-verifies in the log: if every bat comes back at
100% or none do, that is a boxscore parse failure, not a league.

`app/engines/lineup_lock.py` (new) — READER ONLY. No requests, no
roster, no statcast import, and `tests/test_lineup_lock` asserts that
from the AST so a future edit cannot quietly add one. The Boards column
took the Game Card down on 08-16 by building during a render; this
cannot.

`app/views/GameCard.py` — one caption above the PROJECTED lineup:

    Projected lineup — 7 locks, 2 in question (Caratini, Crooks) ·
    start rates over the last 14 team games · provisional, not yet
    checked against outcomes.

Deliberately not a single confidence percentage. One number over nine
rows hides WHICH two are soft, and which two is the entire useful part
when you are talking through a slate on camera. Confirmed lineups skip
it entirely — once MLB posts the order there is nothing to project, and
a test asserts the call sits inside the unconfirmed branch.

`lineup_lock_probe.py` + `.github/workflows/lineup-lock-probe.yml`
(new, manual) — the measurement. **WINDOW_GAMES = 14 IS A GUESS AND IS
LABELLED AS ONE** (`window_is_measured: false`, and the caption says
"provisional" until it flips). The probe answers the forecast question
— given a bat started N of the last W, how often does he start the NEXT
one — across windows 7/14/21, with the hand split on and off, against
the naive baseline "he started last game". **If the rate does not beat
that baseline, drop the column and keep showing last game's nine.**
Same trap as the HR Edge 11.9% baseline: any plausible method clears a
bar nobody checked.

### 4. TWO CONTROLS CAME BACK GREEN, AND WHY

Both were caused by the perf fix in section 5, and both are standing
rules biting again.

**A duplicated guard is a half-tested guard.** After the rewrite, the
`not team` check existed in BOTH `start_rate` and `_lookup`. Breaking
`_lookup`'s copy left the suite green, because the test only ever
called `start_rate` — while `attach()`, the function the Game Card
actually uses, goes through `_lookup`. One guard now, in `_lookup`, and
the test exercises both entry points.

**A test that clears a cache by hand cannot test that the cache
notices.** The memo control stayed green because the fixture called
`clear_cache()` before every read — it told the memo to forget instead
of checking it noticed. The new check rewrites the file and re-reads
WITHOUT clearing. That is rule 4 in its exact documented form: a
control that did not modify anything is not a passing control, and a
fixture that cannot tell the two behaviours apart proves nothing.

### 5. THE FEATURE WAS 19 MS PER CARD BEFORE IT SHIPPED

First version wrapped the file read in `st.cache_data` and parsed the
JSON per call. On a real-sized file (30 teams, ~1,000 bats, 110 KB),
attaching one nine-man lineup cost **19.03 ms** — nine asks, nine full
league parses.

`st.cache_data` is the wrong tool one layer down: it SERIALISES what it
stores, so even a cached dict is re-unpickled per call and the 110 KB
is paid again. Replaced with a plain memo keyed on
(path, mtime_ns, size), plus resolving the team once for the lineup
instead of once per bat.

    attach + caption per card:  19.03 ms  ->  0.049 ms
    first read, cold:            2.17 ms

`roster.py` already keeps a response memo below `st.cache_data` for the
same reason. **Generalise: st.cache_data is for expensive results, not
for a file you are about to read nine times in a row.**

### FILES TOUCHED, 2026-08-17 (2)

    lineup_lock_precompute.py                 NEW  nightly builder
    lineup_lock_probe.py                      NEW  the measurement
    app/engines/lineup_lock.py                NEW  reader only
    app/views/GameCard.py                     projected-lineup caption
    .github/workflows/nightly-data.yml        build + commit steps
    .github/workflows/lineup-lock-probe.yml   NEW  manual
    tests/test_lineup_lock.py                 NEW

Suite 106 -> 107.

### NEXT — IN ORDER

1. **Run the probe.** Until it has, the caption says provisional and it
   should. Set WINDOW_GAMES from the widest spread that still beats the
   naive baseline, then flip `window_is_measured` to True.
2. **If the hand split does not beat the flat rate, take it out.** It
   is complexity that has to earn its place.
3. Still standing from 08-16: **do not touch HR Edge.** Rule 10.
   `benchmark_probe.py` in 2-3 weeks.

---
