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

**11. A MODEL'S PROBABILITY IS NOT A BET'S PROBABILITY.** The market is
the prior; a model moves it only by the weight it earned on games it had
not seen (engines/market_blend). Pricing the model as the truth flagged
44 NFL bets in 16 games on 10-03.

**12. "BETTER ON AVERAGE, INSIDE THE NOISE" IS NOT PROOF.** A thin
verdict gets no weight and no stake.

**13. A DEFAULT IN AN INPUT IS A CLAIM.** A price box that starts at -110
printed "STRONG +23" on a line nobody posts. Start at the neutral value.

**14. LAST SEASON IS EVIDENCE AT A FITTED WEIGHT.** Never 0 by habit,
never 1 by hope: fit it on the players/teams in both seasons, and check a
shuffled last season earns nothing.

---

## PICK UP HERE — NBA finished for now: 1Q player points, Live tested, tests grow nightly, model vs book. 2026-10-21 (3)

**Suite 150, FAILING: none.** New tests/test_nba_quarters.py (4
controls, red by exit code: a game with no play-by-play read as 0; mu
ignoring his own first quarters; vs_book counting pushes; tested_nba
trusting every stat). test_nba_context wiring updated (season_data).
Dry run of the nightly offline; Props (1Q points), Bet Finder, Live (NBA,
halftime) and Tonight headless on its payload.

TESTS GROW NIGHTLY: nba_precompute builds season_data = last season's
players + this season's (merge_pool) and both seasons' finals. nc.fit(
season_data, model): fit window last season's, TEST window last season's
final 45 days + every game this season (n_this_season printed) — the
props verdicts, ladder and calibration curves now learn from this
season. First basket fit / book: prior + this season's play-by-play.

1Q PLAYER POINTS (engines/nba_quarters; stat "q1pts"; nm.PAGE_STATS):
mu = (1-W) x mu_pts x (C0 + C1 x min/36) + W x his last N first quarters.
MEASURED: share alone THIN (z 0.33); with W 0.4 of his last 20 BEATS his
own rate (z 2.47). C0 .22, C1 .05, size 2.84. Raw calls run overconfident
above 60% (0.74 called, 0.48 hit) — the delivered curve corrects it.
Joins model sizes / test ("@q1pts" curve); Props and Bet Finder offer it
only when fitted; trend games carry q1pts (his line).

LIVE, TESTED (nq.live_check -> model["live_check"]; lp.tested_nba):
points at the end of Q1 / Q2 / Q3 of every test game, the Live page's
chance of going over his line vs a naive read (his average x time left,
Poisson): 16,578 calls, BEATS z 6.4. Raw is badly overconfident at the
ends (97% called, 80% hit; 3% -> 13% — garbage-time rest and hot hands)
— the delivered curve is what the page prints. Points only (play-by-play
has points per quarter); rebounds / assists stay THIN; the page says so.

GAME MODEL VS BOOK (nba_precompute.vs_book -> game_model["vs_book"]):
this season's finished games with a recorded line, the model's P(over
the book's total) / P(home covers its spread; ESPN's spread is the
home side's) vs the book's 50/50, paired; pushes out. Tonight shows chips
from 30 games. Model weight stays 0 until it beats.

STILL TO WATCH (no build): offseason minutes (unmeasured), leaders'
overs, 2-leg points SGPs (z 1.95), first-team-to-score (thin).

FILES: app/engines/nba_quarters.py (new), app/engines/live_props.py,
app/engines/nba_context.py, app/engines/nba_model.py,
app/views/Bet_Finder.py, app/views/Live.py, app/views/NBA.py,
app/views/NBA_Props.py, nba_precompute.py, tests/test_nba_context.py,
tests/test_nba_quarters.py (new), HANDOFF.md, HANDOFF_ARCHIVE.md

---

## PICK UP HERE — NBA First Basket; first half / first quarter on the Simulator. 2026-10-21 (2)

**Suite 149, FAILING: none.** New tests/test_nba_first.py (3 controls,
red by exit code: pricing a game after adding it to the book; starters
ignoring the offseason gap; the first-team bet measured while its test
is thin). test_nba_sim +5 checks, control (half share of the predicted
total) red. Dry run of the nightly offline; First Basket and the
Simulator's half / quarter card headless on its payload.

THE BACKFILL RAN (nba-pbp-prior, 10-21): 1,235 of 1,235 games; quarter
lines, first field goal, first point, starters, quarter points in all;
tip in 1,233; 0 quarter lines off the final. First FG by a starter
100.0%; tip winner scored first 62.9%. Leaders: Queta / Murray / Edwards
15. data/nba/prior_pbp.json (1 MB) committed.

FIRST BASKET (engines/nba_first; views/NBA_First_Basket.py; NBA nav).
Walk-forward Book: tip records, who jumps for each team, last RECENT=5
starting fives, first FGs and starts per player. Five = most-started
in the last five games among tonight's available, filled by projected
minutes; across a 60-day gap the projected-minutes five (MEASURED: last
game's five picked April rest lineups — OKC without SGA / Holmgren;
recent-5 lifted the player test z 2.98 -> 3.88). Tip = jumper records
shrunk K_TIP to 50% (Bradley-Terry); team = tip x C + (1-tip)(1-C);
player = team x RHO x share (proj pts ^ G, blended LAMBDA with his own
first-basket rate shrunk K_HIST). Fitted on the fit window by log loss:
K_TIP 2 (grid edge), C 0.618, RHO 0.863, G 1.0, LAMBDA 0.5, K_HIST 60.
TEST (348 unseen games): player call 2.351 vs every-projected-starter-
equal 2.410 -> BEATS z 3.88; tip BEATS z 2.7; first team THIN z 0.9
(page caps it at THIN); scorer in our ten 91%. Calibration bins EDGES
-> delivered chance + support. Nightly: prices g["first_basket"] per
game; this season's play-by-play parsed from the summaries it already
fetches (cur_pbp) feeds the book.

HALVES / QUARTERS (nba_sim.quarter_links / periods / test_quarters):
measured on the fit window. WHO LEADS: the simulated game margin scaled
— P(leads at the half) = the game's own win chance. Two richer tries
LOST to that on unseen games (random per-team half share z -1.97;
fitted line + noise z -1.55). THE TOTAL: projected game total x the
share of the ACTUAL final scored in it (half 0.504, Q1 0.253) + measured
noise; fitting the share on the PREDICTED total (fit-window totals ran
4.6 high) sent halves 60% over on the test — fixed, now 51.6% / 53.1%
over at their middle lines (n 345). Simulator card: typical score, who
leads, total + range, over/under for a typed book total. Research, not
calls (the game model is untested against the book).

NEXT (Izzy's list): NHL periods / NFL quarters / MLB first five — each
its own backfill + test; then NHL / NFL simulators (links measured and
tested like NBA's).

FILES: app/engines/nba_first.py (new), app/views/NBA_First_Basket.py
(new), app/engines/nba_sim.py, app/views/NBA_Sim.py, app/app.py,
nba_precompute.py, tests/test_nba_first.py (new), tests/test_nba_sim.py,
HANDOFF.md, HANDOFF_ARCHIVE.md

---

## PICK UP HERE — Simulator box score; NBA play-by-play backfill (first basket + quarters, step 1). 2026-10-21

**Suite 148, FAILING: none.** New tests/test_nba_pbp.py (3 controls, red
by exit code: a free throw as the first field goal; the tip team read
from the jump ball; the backfill writing on a shape change). test_nba_sim
+2 checks (box score; int16 stats).

Izzy's list (10-21): (1) the Simulator should show player stats; (2)
per-quarter stats in every eligible league; (3) a simulator where there
isn't one; (4) a First Basket page. Plan agreed in chat: (1) now; (4) and
NBA quarters/halves need data we don't have — the tip, the first field
goal and quarter scores live in play-by-play, last season's file has
none — so step 1 is a one-time backfill; NHL periods / NFL quarters / MLB
first 5 and simulators for NHL / NFL come after, each measured.

(1) NBA_Sim "The box score": per team, every player's typical (median)
and 10th-90th range for Pts / Reb / Ast / 3PM / PRA, team's top three per
stat bold, the players' sum beside the team's simulated score. 10,000
games stays: medians and ranges are steady to well under a point there
(the parlay already runs 500,000). Stats now int16 (a 10,000-game slate
4 MB, not 17), sim cache 16 -> 8 entries.

(4/2 step 1) engines/nba_pbp.parse: quarter lines per team (header
linescores), the tip (jumpers + the team of the first play after the
jump ball that names one), first FIELD GOAL (books settle "first basket"
on a field goal; a free throw is not one) and first point, starters
(nba_box), per-player points per quarter (OT left out). check(): quarter
lines add up to the final. nba_pbp_prior.py + nba-pbp-prior.yml (manual,
once): every 2025-26 final's summary -> data/nba/prior_pbp.json; refuses
to write under 80% parsed. SHAPE NOT YET SEEN FROM ESPN — the fixture is
the documented shape; the [verify] lines on the first run are the check.

NEXT: read the backfill's log; then First Basket (P(team scores first) =
tip x measured conversion; P(player | team) = his share, fitted on the
fit window, graded on the test window) and NBA 1Q / 1H team lines.

FILES: app/engines/nba_pbp.py (new), nba_pbp_prior.py (new),
.github/workflows/nba-pbp-prior.yml (new), app/engines/nba_sim.py,
app/views/NBA_Sim.py, tests/test_nba_pbp.py (new), tests/test_nba_sim.py,
HANDOFF.md, HANDOFF_ARCHIVE.md

---

## PICK UP HERE — NBA Long Shots: the ladder (30+ pts, 10+ reb, 5+ threes) graded on unseen games. 2026-10-20 (8)

**Suite 147, FAILING: none.** test_nba +2 controls (long_shots listing a
stat whose ladder has not beaten; nv.chance ignoring the ladder), red by
exit code; test_long_shots nav count 3 -> 4. Dry run of the nightly +
Long Shots (NBA) headless on its payload.

Izzy: "why is there no long shots for NBA?" — it was never wired, and it
could not be honestly: the props test grades each player at HIS line
(chances near 50%), and Long Shots lists only chances inside a graded
curve's range with 30+ calls (+300..+2000 = 4.8-25%).

nm.test_ladder: every test-window player-game graded at every rung of
nm.LADDER (pts 10..50 by 5, reb 4..16 by 2, ast 2..14 by 2, 3PM 1..7,
PRA 20..60 by 5), vs his own last-20 hit rate at that rung, bins
LADDER_EDGES (2-pt bins below 10%). Run on the context-adjusted rows in
nc.fit (ctx["ladder"] -> model["ladder"]); nm.fit keeps a plain one.
REAL 2025-26: pts z 13.5, reb 12.0, ast 14.4, 3PM 11.7, PRA 10.6 — all
BEAT. Long-shot bins well calibrated for pts / 3PM (8-9%: 0.090 called,
0.092 hit); raw reb / ast / PRA run high there (reb 8-9%: 0.090 vs
0.069) — the delivered curve corrects it. Caveat: n includes the many
0-1% rungs; the 2-25% bins hold 1,000-3,500 calls each.

nv.long_shots(games, model): rungs of stats whose ladder BEAT, as
long_shots.rows_from_markets markets ("35+ points"), delivered + support
through the ladder curve, Out players skipped, signals "~33 min · vs
OKC: pts -3% · teammate out". Long Shots page: SOURCES["NBA"]; NBA nav.
nv.chance: a line outside his own line's tested range now reads the
ladder curve when it beat — alt lines on Props / Bet Finder are measured
instead of capped as out of range.

LIVE AT HALFTIME (Izzy's screenshot, BOS @ DET 58-45 at the half: "Overtime
(or a clock the feed did not send)"): live_props.clock_min read only
"M:SS"; ESPN's NBA clock under a minute is "45.3" and at a break "0.0",
so every NBA quarter's last minute and halftime were unpriced. Now
seconds-only and "M:SS.s" read; remaining(..., detail) treats a
clockless break ("Halftime", "End of 3rd", "intermission") as the
period's end. Live's warning was NHL-only text on every sport — now per
sport (NOT_IN). test_live_props +3 checks, control (colon-only parse) red.

FILES: app/engines/nba_model.py, app/engines/nba_context.py,
app/engines/live_props.py, app/views/Live.py, tests/test_live_props.py,
app/engines/nba_view.py, app/views/Long_Shots.py, app/app.py,
nba_precompute.py, tests/test_nba.py, tests/test_long_shots.py,
HANDOFF.md, HANDOFF_ARCHIVE.md

---

## PICK UP HERE — Same-game parlays graded by kind (2/3/4 legs, points/mixed); the test grows nightly. 2026-10-20 (7)

**Suite 147, FAILING: none.** test_nba_sim +3 controls, red by exit code
(a kind's verdict ignored; an under kept in range; the leg count ignored
with no combos test). Dry run of the nightly offline + the Simulator
page headless on its payload ("What has been graded" table rendered).

Izzy: "so none of them will give strong signals" -> build the way out.
nba_sim.test_combos: from every test game, the parlays people build —
2|pts (top-2 teammates; top scorer each side), 2|mixed (top scorer pts +
team's top rebounder reb), 3|pts (top-3 teammates), 3|mixed (pts + reb +
ast leaders), 4|pts (top-2 each side), 4|mixed (pts + reb leader each
side) — every leg an over at his own last-10 half-line, the delivered
chance per stat (that stat's curve), simulated at COMBO_SIMS = 20,000;
simulator (product x lift) vs multiplied, paired Brier per kind.
sgp_support(test, legs, combos): kind BEAT + all overs + 100+ graded ->
in range (STRONG allowed); beat with an under, or < 100 -> VALUE;
not beaten / never graded (5+ legs) -> THIN; sgp_guard() names which.

THE TEST GROWS: build(prior, model, pool, cur_finals) — the test window
is last season's final 45 days PLUS every game of this season (pool =
merge_pool, season_finals() converts this season's finals' shape). Links
stay fitted on last season. Checked with 6 re-dated days: +1,062
player-games, ~+58 per kind of pairs. Nightly sim step now ~47 s.

REAL 2025-26 (context model): no kind beats yet — 2|pts z 1.95 (the
closest), 3|pts 0.42, 4|pts 1.04, 2|mixed 0.35, 3|mixed -0.13, 4|mixed
0.78. The simulator moves the joint the right way in every pts kind
(3|pts: multiplied 11.6%, sim 12.8%, actual 13.3%), but the samples are
small. ALL kinds hit MORE than either predicts (4|mixed: 5.2% vs 8.2%) —
leaders' overs run 2-4 pts above their delivered chance on both windows.
A role shift (logit, per rank, fitted on the fit window) did NOT beat on
the test (pts z 0.1, reb -1.2, ast 1.9) — NOT shipped. Revisit with this
season's games.

FILES: app/engines/nba_sim.py, app/views/NBA_Sim.py, nba_precompute.py,
tests/test_nba_sim.py, HANDOFF.md, HANDOFF_ARCHIVE.md

---

## PICK UP HERE — NBA context: tonight's opponent + teammates out; a proper fit score; opening night. 2026-10-20 (6)

**Suite 147, FAILING: none.** New tests/test_nba_context.py (5 controls,
red by exit code; the 5th first stayed GREEN — it checked the row's
ctx/why, not its mu; the check now asserts mu = base x opp x bump).
test_nba +1 control (offseason cut). Dry run of nba_precompute.main
offline on the real 2025-26 file (ESPN patched: one game, HOU @ OKC,
Amen Thompson Out) — every verify line below came from it; Tonight /
Props / Simulator / Trends / Next Man Up / Bet Log render headless on
that payload.

THE FIT SCORE WAS BIASED (found while fitting the context): nm._sse was
(mu - y)^2 / mu — its denominator grows with mu, so it rewards projecting
HIGH (on Poisson(10) it is minimised at 10.49). It called a teammate-out
redistribution that made every Brier WORSE a 10% improvement. Now
nm.deviance (Poisson deviance — minimised at the mean). Base refit with
it: HL 2, K 600, HL_LONG 120, K_LONG 100; every stat's Brier lower than
the chi fit (3PM z 2.06 -> 4.66). FIT_HL gained 1.

engines/nba_context — per stat, fit window, deviance; OFF unless better:
  OPPONENT (defense + pace): walk-forward factor per opponent (by
    position for 3s), (sum w*actual + K*m) / (sum w*proj + K*m), days
    half-life: pts hl120 k40, reb hl30 k100, ast hl30 k100, tpm hl120
    k100 by position. A day's games never see their own day.
  TEAMMATE OUT: rotation players (15+ min) who miss a team game leave
    ALPHA of their production to those who play, in proportion; weight
    0.5^(games already missed / HL) — teammates' own recent games carry a
    long absence already. pts a.3 hl2, reb a.3 hl2, ast a.45 hl.5, tpm
    a.2 hl.5. Trades are not absences.
TEST (unseen 45 days), context vs no context on the same lines: Points
z 8.5, Reb 2.4, Ast 4.3, 3PM 3.9, PRA 8.4, P+R 8.0, P+A 9.0, R+A 4.7 —
all BEAT. Vs his own rate: Points z 8.1 (was 4.9) ... R+A 9.5. The
top-scorer gap from entry (4) CLOSED: test window top-2 projected 20.18
vs actual 20.09 (was 19.14). The model's sizes / test / curves are the
context's (model["base_test"] keeps the plain one; model["context"] has
opp / mean / out / vs_base). Pages' captions read nv.in_the_number.

TONIGHT: nc.book_now walks last season + this one; nc.outs_now counts
this team's games since an Out player's last (cur + prior finals);
nc.apply_tonight sets row mu, row["ctx"], appends the why ("vs DET: pts
+4% · with X out: pts +3%"). Late scratches after the nightly are NOT
in it.

OPENING NIGHT (NOT MEASURED — the file has no offseason): with HL 2, a
star was projected off his last two April games (SGA 30.1 min). Running
.offseason(): across a 60+ day gap the recent window restarts from his
long-run averages at CARRY weight; project_now(today=) applies it before
a projection made across the gap. SGA 30.1 -> 33.2 (last season 33.3).
Also changes 2025-26 players back from 60+ day injuries (test numbers
moved in the third decimal).

SIMULATOR on the context model: links e pts 1.005 reb -0.26 ast 1.06 3PM
1.10; test 1,065 pairs z 1.7-2.0 across the last two fits — ON THE LINE
between THIN and BEATS; the nightly's verdict sets the SGP cap.
Nightly cost: base fit ~70 s, context ~35 s, sim ~25 s.

SGP LEGS (Izzy: "why 4?" — it was my pick, not a measurement): the
Simulator's builder takes up to nba_sim.SGP_MAX_LEGS = 8. Measured at
500,000 games: the link's noise is +/- 0.002 at 2 legs, 0.009 at 6,
0.017 at 8, 0.035 at 10. But the test grades two-leg pairs only and the
link grows with every leg (8 overs: x1.7, 6 HOU overs on the dry run:
x2.1) — so sgp_support(test, n_legs) caps 3+ legs at THIN (untested),
SGP_GUARD["thin_legs"] says why. test_nba_sim +1 control (n_legs
ignored). The Bet Finder's parlay slip never had a cap.

FILES: app/engines/nba_model.py, app/engines/nba_context.py (new),
app/engines/nba_sim.py, app/engines/nba_view.py, app/views/NBA.py,
app/views/NBA_Props.py, nba_precompute.py, tests/test_nba.py,
tests/test_nba_context.py (new), HANDOFF.md, HANDOFF_ARCHIVE.md

---

## PICK UP HERE — Why 10,000 sims, and the parlay now runs 500,000. 2026-10-20 (5)

**Suite 146, FAILING: none.** test_nba_sim +2 controls, red by exit code
(joint_precise counting only the last chunk; simulating every player).

Izzy: "why 10,000? best simulator ever". MEASURED (one 4-leg SGP, 20
runs per size): the lift's run-to-run SD was 0.022 at 10k, 0.016 at
50k, 0.008 at 200k, 0.003 at 1M — at 10k the noise was as big as the
lift (+2%). The game numbers are fine at 10k (a 50% chance is +/- 0.5
pts); the parlay's link was not. Sim count is precision, not accuracy:
past the noise, more games add nothing — the model inside decides.

nba_sim.joint_precise: the parlay at SGP_SIMS = 500,000 games in
SGP_CHUNK = 100,000 chunks, simulating ONLY the leg players (a player's
draw needs the shared score and his own numbers, so the rest of the
roster changes nothing): 1.4 s, 62 MB peak here; cached per game + leg
set (_legs_run). Returns lift_se (from the all-hit count); the page says
"move together" / "pull apart" only when the lift is 2 SE from 1, else
"no real link". The game and player tables stay at 10,000.

NEXT, the real upgrades (each measured on the fit window, tested on the
unseen one, before shipping): tonight's opponent and pace in the props
(not in the number today); a teammate OUT moving minutes and usage
inside the sim (Next Man Up data already exists); then the top-scorer
gap (entry (4)).

FILES: app/engines/nba_sim.py, app/views/NBA_Sim.py, tests/test_nba_sim.py,
HANDOFF.md, HANDOFF_ARCHIVE.md

---

## PICK UP HERE — Points model fixed (stars no longer shrunk to average); the Simulator passes; the Bet Log. 2026-10-20 (4)

**Suite 146, FAILING: none.** New tests/test_bet_log.py (4 controls, red
by exit code: minus price read like a plus price, open bets counted as
losses, a missing close scored 0, the save without [skip render] — the
last one first stayed GREEN because the replace hit the docstring's copy
of the words; redone on the code line). test_nba +1 control (project
ignoring k_long). test_nba_sim +1 control (sgp_support letting a beating
test be in range). Headless: Simulator -> log SGP -> Bet Log -> grade,
in session mode and against a fake GitHub store; slip logs a parlay and
a single.

WHY THE SIM WAS THIN (measured on the FIT window, then confirmed): not
the link. Real teammate points correlation 0.02; real "both over" lift
1.025 (fit) / 1.039 (test), +/- 0.07; the sim said 1.06. The gap was the
LEGS: a team's top-2 projected scorers went over their line 49-50% of
the time against 45% delivered — one-level shrinkage pulled every
scorer's per-minute rate toward his position group's.

THE FIX (engines/nba_model): two levels — recent rate (HL) shrunk by K
min toward HIS OWN long-run rate (HL_LONG), which is shrunk by K_LONG
min toward the league. Grid FIT_HL (2,3,5,10) x FIT_K (100,300,600,1200)
x FIT_HL_LONG (30,60,120) x FIT_K_LONG (100,300,1000), fit window only;
~63 s in the nightly. Real 2025-26: HL 3, K 600, HL_LONG 120, K_LONG 300.
Test window (unseen): Points THIN z0.8 -> BEATS z4.45; 3PM THIN -> BEATS
z2.06; PRA / P+R / P+A THIN -> BEATS (z 5.5-6.1); Reb 7.67, Ast 6.74,
R+A 8.3. Minutes MAE 5.11 vs 5.87 (was 5.39). walk / Running / project_now
take the two levels; params carry hl_long / k_long (absent = one level,
so an old payload still projects).

STILL OPEN: top-2 scorers still under-projected on the test window
(18.6 vs 20.0) — partly a test artifact (top-2 among players who PLAYED:
when a star sits, the next man is "top-2" and his usage jumps). Measure
a usage-share adjustment on the fit window before touching it.

SIMULATOR on the new model: links e pts 0.987 reb -0.276 ast 1.115 3PM
1.082; test 1,065 pairs, 0.1955 vs 0.1963, z 2.93 -> BEATS. sgp_support:
beats -> measured but in_range False -> at most VALUE (only two-man
points pairs were graded; STRONG on an SGP would claim more than that).
nba_sim.SGP_GUARD holds the page's two cap sentences.

BET LOG (engines/bet_log, engines/bet_log_ui, views/Bet_Log.py; in every
nav after Bet Finder; on Home): bets {id, placed, sport, kind single /
parlay / sgp, desc, legs, chance, price, stake, tier, result, close}.
Summary: record / profit / ROI; expected wins vs won; MODEL VS BOOK —
the same bets scored on squared error, our chance vs the break-even of
the price paid (mm.paired_verdict, shown from 30 graded bets); CLOSING
LINE in points of chance when a close is typed (missing = left out).
Logged from the parlay slip (parlay / sgp when all legs share a game /
single) and the Simulator. STORAGE: Render's disk is wiped per deploy,
so the log is data/bets/<user>.json written through GitHub's contents
API — env BETLOG_TOKEN (fine-grained token, this repo, Contents
read/write), optional BETLOG_REPO (a private repo, if this one is
public). Commit message "[skip render] [skip ci]". Stale sha -> reload,
merge, retry once. No token -> session only + download / upload.

SIMULATOR PAGE, READABILITY (Izzy's iPad screenshot): the "Typical
score" metric truncated to "BOS 108 – D..." and the book's total printed
as "<b>47%</b>" (st.caption shows tags as text). Now two team boxes (big
score, win %, scoring range; the favourite outlined), a "Typical result /
Total" line, the margin table shaded by share; players read Line /
Typical / Most nights / Over / Under / Lean (a side at 55%+, else
toss-up), <1% / >99% at the ends. test_nba_sim: no HTML in a caption
(control red).

FILES: app/engines/nba_model.py, app/engines/nba_sim.py,
app/engines/bet_log.py (new), app/engines/bet_log_ui.py (new),
app/views/Bet_Log.py (new), app/views/NBA_Sim.py, app/views/Bet_Finder.py,
app/views/Home.py, app/app.py, nba_precompute.py, tests/test_nba.py,
tests/test_nba_sim.py, tests/test_bet_log.py (new), HANDOFF.md,
HANDOFF_ARCHIVE.md

---

## PICK UP HERE — NBA Game Simulator: 10,000 games, same-game parlays priced together. 2026-10-20 (3)

**Suite 145, FAILING: none.** New tests/test_nba_sim.py with four negative
controls, each red by exit code: plain-Poisson draws (marginals), score
link removed (teammate lift), blowout minutes share removed (starters
sit), sgp_support treating every test as beating (the THIN cap). The
page rendered headless on the synthetic slate; SGP added to the slip.

Izzy: "Can we add a simulator?" ENGINE engines/nba_sim: each run draws a
margin and total from the game model (its fitted SDs), then every
player's stats: mean = his projection x minutes share for the game
script (close / comfortable / blowout, |margin| 10 / 20) x (1 + e x
shock) — points ride his team's score, the rest ride pace. The NB draw
is sized so each player ON HIS OWN keeps the props model's distribution
(test: worst gap 0.4 pts). The minutes share is normalised to average 1
over the simulated games: unnormalised, last season's bench bias (1.02-
1.05) moved bench means +3% and the sim no longer priced legs like the
props board. joint(): share of games where every leg hit; lift = joint /
product.

MEASURED ON 2025-26 (fit window, then the 45-day test window): e pts
0.969, reb -0.286, ast 1.11, 3PM 1.037; minutes share starter 1.037 /
0.967 / 0.877, bench 1.049 / 1.019 / 1.017. TEST: 1,065 same-game pairs
of top scorers (teammates and opponents), each leg's DELIVERED chance
(the points calibration curve), joint = product x sim lift vs plain
product: Brier 0.1929 vs 0.1934, z 1.86 -> THIN. Teammates: product
20.4%, sim 21.5%, actual 25.8% — right direction, under-corrected.
Opponents: 20.0 / 20.6 / 27.6. (On RAW legs it beat at z 4.9 — but the
raw points model is overconfident at the ends, 0.84 predicted vs 0.57
actual, so that was the curve's win, not the sim's.)

PAGE app/views/NBA_Sim.py (NBA nav: "Simulator"): pick a game -> win %,
typical score, total's middle 80%, margin buckets, P(over the book's
total) with the not-tested-against-the-book note; every player's 10th /
50th / 90th percentile for a stat, Over % coloured; SGP builder, 2-4
legs, each leg = nv.chance (delivered), joint = product x lift, fair
price, your price -> bf.judge with nba_sim.sgp_support(test): UNTESTED
-> capped at THIN until the test BEATS. Out players are not simulated.
Cached 15 min per game; seed from crc32 of the game, so stable.

NEXT: the sim under-corrects teammates (21.5 vs 25.8). Candidates to
measure, not guess: a shared player-level "hot night" shock, usage
redistribution when a teammate goes cold. Never tune it on the test
window.

FILES: app/engines/nba_sim.py (new), app/views/NBA_Sim.py (new),
nba_precompute.py, app/app.py, tests/test_nba_sim.py (new), HANDOFF.md,
HANDOFF_ARCHIVE.md

---

## PICK UP HERE — NBA game model; colour on every measured NBA number. 2026-10-20 (2)

**Suite 144, FAILING: none.** test_nba gains a fourth negative control
(nba_game_model not attaching its projection) — red by exit code. Tonight
rendered headless with the game model on a simulated slate.

THE FIRST REAL NBA NIGHTLY (10-20): model fit in 6 s, HL 10 games, K 100
min. Test on the last 45 days of 2025-26 (6,754 player-games): Rebounds
BEATS (z 6.4), Assists BEATS (z 5.6), Reb+Ast BEATS (z 6.7); Points,
3PM, PRA, P+R, P+A THIN (z 0.8-1.6). Minutes MAE 5.39 vs season-average
5.89. 73 players projected, 5 held out, 1 Next Man Up board; role watch
40 (Julian Reese -24.9 min is real: 30.9 min over 13 late-2025 games).
Career feed: categories averages / totals / miscellaneous, labels
"2022-23" style — 73 fetched, 0 unreadable.

GAME MODEL (nba_precompute.nba_game_model): engines/nfl_game_model reused
as is — team ratings, normal margin / total with measured SDs, carryover
fitted. Offline on the real 2025-26 file: walk-forward 1,215 games, log
loss 0.600 vs coin 0.693 vs home-rate 0.689 (beats); margin MAE 11.54 vs
13.18 (beats); total MAE 15.34 vs 16.00 (beats). NO market history ->
model weight 0 on every game line (the market's own number prices game
bets on the Bet Finder, which now has NBA game lines). Payload
"game_model" (rates dropped); each slate game gets g["model"].

COLOUR (Izzy: "colour everything that requires measuring"): Tonight's
rotation cells coloured by the chance he clears HIS usual line
(mv.chance_css, legend under each game); verdict chips in TRUST_STYLE
colours, game-model chips added; win % chip coloured; a model-vs-book
total gap of 8+ reads "CHECK: the book likely knows why" (never a
"lean" — the model is not tested against the book); role watch Change
+/-4 coloured; Trends "Over %" coloured. Teams now stack (iPad width cut
the PRA column).

FILES: nba_precompute.py, app/views/NBA.py, app/views/NBA_Trends.py,
tests/test_nba.py, HANDOFF.md, HANDOFF_ARCHIVE.md

---

## PICK UP HERE — NBA goes live: model, Tonight, Props, Trends, Next Man Up. 2026-10-20

**Suite 144 (+ test_nba), FAILING: none.** Three negative controls red by
exit code (listed in the test). Every NBA page, plus the Bet Finder,
Live and Milestone Watch on NBA, rendered headless on a simulated slate
(fitted model, a star out, preseason games) with no exceptions.

WHY: opening night 10-20; the NBA page was a coming-soon stub. Izzy: make
it special, preseason for reference, player trend charts, "create a gem".

DATA: nba_prior_season.py + MANUAL workflow nba-prior-season.yml (RUN
ONCE) -> data/nba/prior_season.json (2025-26 regular season, ~1,230
box scores; tuples [date, team, opp, min, pts, reb, ast, tpm, stl, blk,
tov]). engines/nba_box parses ESPN's summary by LABELS (MIN PTS REB AST
3PT STL BLK TO); did-not-play / zero minutes are not games.

MODEL (engines/nba_model.py): recency-weighted minutes x per-minute rate
shrunk to the position group's league rate by K minutes; combos = sums;
NB spread per stat by method of moments; last season carries at CARRY
0.5 across the offseason gap. HL (5/10/20/40) and K (0/30/100/300)
FITTED on the 45 days before the test window. TEST: last 45 days of
2025-26, line = his last-10 average at the half point, vs his own last-20
hit rate over it, paired verdict + "@stat" calibration (the NFL shape,
so curve_for / support_for / the guard read it unchanged). Simulated
season: all 8 stats beat. NOT in the number (said on the pages):
opponent, pace, a teammate out, rest.

NIGHTLY (nba_precompute.py, step in nightly-data.yml, archive expects
data/nba/games.json): slate (14-day lookahead), this season's box
scores (regular -> pool; PRESEASON -> reference only, never a rate),
fit + verify lines, roster + league injury list (Out never projected),
per-team props rows (min, mu, season / last-season lines, why, a
30-game + preseason TREND list tagged LAST / PRE / REG), Next Man Up
boards for 20+ min players OUT, WHAT IF boards for each team's top six,
the preseason role watch, milestones (NBA in engines/milestones with a
sport-aware REACH; ESPN "made-att" threes parsed).

PAGES (NBA nav: Tonight, Props, Player Trends, Next Man Up, Bet Finder,
Live, Milestone Watch, Results): NBA.py (game cards, injury chips,
projected rotations, Next Man Up teaser, role watch, model verdict
chips); NBA_Props.py (stat board, editable line from his last-10 half
point, chance delivered, your price -> guard, card + parlay slip, trend
chart); NBA_Trends.py (one player, all stats, charts with PRE toggle);
NBA_Next_Man_Up.py (the gem: OUT tonight + What If). engines/nba_view
is the one chance function for all of them. Bet Finder SOURCES["NBA"];
Live NBA (4 x 12, NB rest-of-game updated on what he has; untested ->
THIN); live injury check covers nba props. Switcher caption: NBA live.

FIRST RUNS: 1) "NBA prior season" workflow -> [verify] ~1,230 box
scores, scoring leader. 2) nightly -> "[verify] NBA model fit", one line
per stat (beats / thin / fails), minutes MAE, injuries, Next Man Up
boards, role watch, the career feed probe.

FILES: app/engines/nba_box.py, nba_model.py, nba_view.py,
app/views/NBA_Props.py, NBA_Trends.py, NBA_Next_Man_Up.py,
nba_prior_season.py, nba_precompute.py,
.github/workflows/nba-prior-season.yml, tests/test_nba.py (NEW);
app/views/NBA.py (rewritten), app/app.py, app/views/Bet_Finder.py,
app/views/Live.py, app/views/Milestones.py, app/views/Results.py,
app/engines/live_props.py, live_injuries.py, milestones.py,
espn_feed.py, slate_guard.py, app/styles/kc_theme.py,
.github/workflows/nightly-data.yml, tests/test_live_props.py,
tests/test_bet_finder.py, tests/test_milestones.py,
tests/test_nfl_nhl_wiring.py, HANDOFF.md, HANDOFF_ARCHIVE.md

---

## PICK UP HERE — Parlay slip; the Live page's test on last season. 2026-10-18 (2)

**Suite 143 (+ test_parlay, test_live_check), FAILING: none.** Six
negative controls red by exit code (three per test). The slip rendered
headless on the Bet Finder (three legs, two same-game: THIN, linked).

WHY: Izzy bets parlays; every board judges singles, so he skipped legs
marked SKIP that may belong on a ticket (next to a strong leg, under a
boost) — and could not see a leg dragging a ticket down.

PARLAY (engines/parlay.py, NEW): joint = product of leg chances; payout =
the book's parlay price if typed, else the legs' product, boost on the
winnings; EV = joint * payout - 1; each leg's chance * decimal = carries
(> 1) / drags (< 1). Guard leg by leg: a CHECK leg -> CHECK; same-game
legs (game_id: the two abbreviations from any page's label) -> THIN
with the reason (the link is not priced); untested leg -> THIN; past
graded range -> VALUE. Ticket tiers by EV per $100: THIN < 10, VALUE
10-25, STRONG 25+ (display cuts). Stake = the single's Kelly rule on the
ticket. model_view.parlay_add_ui puts ANY typed leg (BET or SKIP) on
session_state["parlay"] from Bet Finder (props + game lines), Long
Shots and Live; the slip is judged at the bottom of the Bet Finder.
Izzy's 10-13 four-leg ticket: 1 in 356, +38,686 -> +9 per $100 (THIN),
Holmstrom carries +23%, Coyle / Hagens drag; a 25% boost -> STRONG.

LIVE TEST (nhl_live_check.py + MANUAL workflow nhl-live-check.yml, NEW):
last 90 days of 2025-26; pregame mu walk-forward (nhl_model.build on the
prior file alone, rates/probs/toi_scales — fitted 25,518 skater-games
from 2025-12-28 offline in 80 s); ESPN summaries' scoring plays by period
(plays[].scoringPlay or scoringPlays; scorer first when untyped;
shootout dropped); at the end of P1 / P2, live_props.nhl_chance vs a
naive read (his own season rate x time left), paired on squared error
per market (g1, g2, pt1, pt2, a1); calibration by checkpoint and by
score state. Refuses to write without scoring plays; prints the summary
probe. data/nhl/live_check.json -> live_props.tested(): a market that
BEAT gets its delivered chance + curve support (VALUE / STRONG possible
in range) for NHL Overs; everything else (Unders, shots, NFL) stays
UNTESTED. Game matched by the OPPONENT that night (traded players).

FILES: app/engines/parlay.py, nhl_live_check.py,
.github/workflows/nhl-live-check.yml, tests/test_parlay.py,
tests/test_live_check.py (NEW); app/engines/live_props.py,
app/engines/model_view.py, app/views/Bet_Finder.py,
app/views/Long_Shots.py, app/views/Live.py, HANDOFF.md,
HANDOFF_ARCHIVE.md (+ the 10-18 Live files, shipped together)

---

## PICK UP HERE — Live: player props over the rest of a game in progress. 2026-10-18

**Suite 141 (+ test_live_props), FAILING: none.** Three negative controls
red by exit code (listed in the test). Rendered headless on an NHL slate
with a faked live summary (2nd period, 10:00): Caufield 42% pregame ->
25.2% rest of game; a skater with a goal shows CASHED.

WHY: "I WANT TO LIVE BET MAKE IT POSSIBLE." Every board is pregame; a
mid-game price typed into the Bet Finder is judged against a full-game
chance and reads as a false VALUE.

ENGINE (engines/live_props.py, NEW, pure): remaining(sport, state,
period, clock) = fraction of regulation left (OT -> None, not priced).
rest_pmf: Poisson at m*f (goals, assists, points, TDs); NB counts with
the game rate's gamma UPDATED on what he already has (size r + have,
mean (r+have)/(r/m + 1 - f) * f — a hot start raises the rest); yards
normal, mean m*f, sd cv*m*sqrt(f). need = floor(line)+1 - have.
game_state / nhl_box / nfl_box read ESPN's live summary (header status,
boxscore groups via espn_feed.box_group_index).

PAGE (views/Live.py, NHL + NFL navs): games from load_slate_live /
load_week_live; ESPN summary re-read every 30 s (8 s timeout, both
hosts) + a Refresh button; stat / line / side; Has / Needs / Chance /
Worth it at / Your price; calls through bf.judge with
live_props.UNTESTED -> THIN at most (CHECK at a 10+ gap), Edge shown.

NOT IN THE NUMBER (on the page): score effects, an in-game injury, a
power play in progress. NEXT: test it — last season's NHL summaries
period by period (who had scored by the end of P1 / P2 vs the rest-of-
game chance) — and only then lift the THIN cap for what passes.

FILES: app/engines/live_props.py, app/views/Live.py,
tests/test_live_props.py (NEW); app/app.py, HANDOFF.md,
HANDOFF_ARCHIVE.md

---

## PICK UP HERE — MLB postseason: game logs, grading, trend windows. 2026-10-16

**Suite 140 (+ test_mlb_postseason_logs), FAILING: none.** Four negative
controls red by exit code (listed in the test).

WHY: Izzy, in the playoffs: "all of the data provided is for the last
game of regular season." The Stats API gameLog defaults to the REGULAR
season and every reader asked for it that way. Two consequences:
  1. Trend windows (2026 / L25 / L15 / L5, batters and pitchers) stopped
     at 09-27.
  2. GRADING: a postseason pick's date was never in the log, so
     calibration_pipeline closed it DID_NOT_PLAY at once — no postseason
     pick on Daily 13 / HR Edge / POTD / K Board ever counted.

FIX (engines/mlb_gamelog.py, NEW, pure): splits(get, url, group, season)
= regular log + postseason log (gameType "P", falling back to "F,D,L,W"),
every stats entry (trades), one row per gamePk, date order, "_post"
tag. A failed postseason read costs only postseason rows; a failed
regular read still raises (unknown != did-not-play). Used by
calibration_pipeline._mlb_line / _mlb_pitching_line (loaded by FILE
PATH — the pipeline has no app/ on sys.path), calibration._player_day_json
(its twin), batter_trends and pitcher_trends (opp label "(PS)").
reopen_postseason(record): ONE-TIME — MLB-board "dnp" picks dated >=
POSTSEASON_FROM (2026-09-28) are reopened once, stamped "ps_regraded",
so a genuine DNP is never reopened twice.

NOT CHANGED (rule 1): k_projection's own game-log reads (the K Board's
number) stay regular-season — adding October starts is a model change
and gets tested first. Statcast: pybaseball's query already asks for
PO; precompute now prints "[verify] Statcast postseason pitches in the
season pull: N" — if N is 0, the prop model's pitches stop at 09-27 too.

FIRST NIGHTLY: "Calibration: reopened N postseason pick(s)..." then the
board totals should rise; the Statcast line above.

FILES: app/engines/mlb_gamelog.py, tests/test_mlb_postseason_logs.py
(NEW); calibration_pipeline.py, app/engines/calibration.py,
app/engines/batter_trends.py, app/engines/pitcher_trends.py,
precompute.py, HANDOFF.md, HANDOFF_ARCHIVE.md

---
