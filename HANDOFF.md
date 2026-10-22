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

## PICK UP HERE — NHL shots measured (context only, both thin); every workflow push retries; NFL spikes are incompletions. 2026-10-22 (10)

**Suite 159, FAILING: none.** New tests/test_push_retry.py (control red:
one workflow put back to a single pull + push); tests/test_period_backfills
.py +1 (control red: a spike read as a completion).

WHY THE RETRIES: 10-22 the nightly and "NFL prior quarters" both died at
their commit step — "[remote rejected] ... cannot lock ref" — main moved
under them (Izzy's push + another run in the same minute). The nightly
stopped at its FIRST commit step, so nothing after it published. All 16
pull + push pairs across 11 workflows are now a 5-try loop (pull
--rebase, push, sleep 15 / 30 / 45 / 60 s), then ::error:: and exit 1.

NHL PRIOR SHOTS (the (9) backfill, committed e83b99f): 1,312 games, 0
failed, skater-games matched to ESPN 100.0%, iSF == ESPN SOG 99.9% of
43,037. Spot on the ice for 73.3% of attempts = exactly the unblocked
ones (blocked attempts carry no spot — they count in iCF only anyway).
Per skater-game iCF 3.55, iFF 2.60, iSF 1.70, iSCF 1.21, iHDCF 0.72.
Goals per attempt: high-danger 0.130, other chances 0.092, the rest
0.034 (the slot box is generous; NOT re-tuned after seeing the test).

THE TEST (run locally on that file through fit_toi, the nightly's path —
the nightly prints the same): coverage 97.5% of fit rows.
  attempts -> SOG:  fitted strength 0.36; props window n 69,372, Brier
                    0.1173 vs 0.1172 -> THIN (z 0.2) -> context only
  chances -> goals: fitted strength 0.61; n 34,686, Brier 0.0694 vs
                    0.0695, log loss 0.2380 vs 0.2384 -> THIN (z 1.7)
                    -> context only
So neither beats the current number by enough: the shrunk SOG and goal
rates x ice time already carry what attempts and chances add. Att/G,
HD/G, xG/G stay on the NHL Model page as information with the note
saying so. Ice time itself re-confirmed: SOG z 7.9, points z 6.3. NEXT
for chances: they may still help where the current model is weakest —
2+ goals (Multi-Goal Watch) or a regression flag (goals far above xG) —
each needs its own test before it moves a number.

NFL QUARTERS RERUN (after (8)): pass_yds 78.8% (was 72.9), rush 90.1,
rec 94.2. 324 completions with no catcher found; the samples showed
SPIKES ("D.Prescott spiked the ball to stop the clock") read as
completions — the box counts a spike as an incomplete attempt. Fixed
(nfl_quarters: "spiked" -> not caught). A rerun of "NFL prior quarters"
picks it up; the nightly refits on the file itself.

FILES: .github/workflows/{market-history, nba-pbp-prior, nba-prior-season,
nfl-quarters-prior, nhl-live-check, nhl-periods-prior, nhl-prior-pp,
nhl-prior-season, nhl-shots-prior, nightly-data, slate-picks}.yml,
app/engines/nfl_quarters.py, tests/test_period_backfills.py,
tests/test_push_retry.py (NEW), HANDOFF.md, HANDOFF_ARCHIVE.md

---

## PICK UP HERE — NHL shot attempts (iCF / iFF) and scoring chances (iSCF / iHDCF) from the NHL feed: on the Model page, tested as factors on SOG and goals. 2026-10-22 (9)

**Suite 158, FAILING: none.** New tests/test_nhl_shots.py (5 controls,
red by exit code: blocked counted as unblocked, shootout read, the net
always at +89, last-name match without the first initial, shot_scales
applying a fit that was not adopted). NHL_Model headless on the archived
slate (columns "—" until the backfill). Izzy sent Natural Stat Trick's
definitions list: "implement the missing stats ... to take the positive
effect in the nhl page". TOI, G, iSF were already in; iCF, iFF, iSCF,
iHDCF were missing.

STEP 1 OF 2 — NEEDS THE BACKFILL: Izzy runs "NHL prior shots" once
(nhl-shots-prior.yml -> nhl_shots_prior.py -> data/nhl/prior_shots.json).
Until then the factors print "too few games carry shot attempts" and the
page says context only. Then the nightly fits and tests them by itself.

DATA (engines/nhl_shots): ESPN's plays don't reliably carry the spot, so
the NHL's own play-by-play (api-web.nhle.com/v1/gamecenter/{id}/play-by-
play — the same host the goalie probe already reaches): typeDescKey goal
/ shot-on-goal / missed-shot / blocked-shot, details.shootingPlayerId
(scoringPlayerId on goals), xCoord / yCoord, zoneCode; shootout dropped.
The attacked net from homeTeamDefendingSide (else the zone code). Chances
by SPOT only (NOT Natural Stat Trick's exact polygons, no rebounds /
rush): high danger = inner slot (goal line to 25 ft, |y| <= 9); chance =
that + home plate (to 35 ft, inside posts->dots, |y| <= 22). Blocked
attempts count in iCF only (their spot is the block's). Row per skater-
game [icf, iff, isf, g, iscf, ihdcf, g_sc, g_hd]. NHL ids -> ESPN ids by
name inside the game (full name; else last name + first initial, unique);
the ESPN game = most names in common (no abbreviation tables). Backfill
refuses under 85% of skater-games matched or 90% of iSF == ESPN SOG.
UNVERIFIED until the first run: the feed's field names above (from the
public API as known in 2025) — the log prints kinds seen and % with a
spot; if it refuses, read those lines.

MODEL (nhl_model "SHOT ATTEMPTS AND SCORING CHANCES", fitted inside
fit_toi on its train / test split, after ice time):
  sog: mu x (iFF/game x his on-net share shrunk 150 attempts to the
       league's  /  his SOG rate) ^ a
  g:   mu x (chance-implied goals/game — HD, other chances, the rest at
       the league's goals per attempt from each, measured before the test
       — / his goal rate) ^ b     (assists untouched; points via goals)
Ratios clipped [0.5, 2]; < 5 games of attempt data -> 1.0. Strength
fitted (golden search, log loss) on train, TESTED on the props window vs
strength 0; adopted only on "beats" (rule 1). shot_scales() applies the
adopted ones in validate_props (so the props verdicts test the page's
model), tonight's slate, and nhl_sim.test_rows (simulator / 1st-period
tests). Synthetic check: where chances decide goals it fits 1.0 and
beats z 3.7.

NIGHTLY: load_prior_shots (prior skaters' "shots"); current_shots: this
season's finals from the NHL feed every night (one schedule call a week
+ one play-by-play per game — ~1,300 calls by April; a cache file is the
fix if it gets slow) laid on the lines as line["shots"]; pool_skaters
merges both. VERIFY LINES: "NHL last-season shot attempts / chances: N
skaters", "NHL shots this season: ...matched ...% ; shots on goal equal
to ESPN's box ...%", "NHL shot attempts / chances: coverage, league",
"NHL attempts -> SOG: ... IN THE NUMBER / context only", "NHL chances ->
goals: ...".

PAGE (NHL_Model, skater props): Att/G (iCF), HD/G (iHDCF), xG/G (goals
his attempts are worth) + nm.shots_note(): what is in the number.

APPLIES TO (if adopted): every SOG prop (incl. 1st-period SOG, the
Simulator's shots), goal / point props, Player of the Day, Multi-Goal
Watch (they read the props' mu). NEXT: after the backfill + a nightly,
read the two verdict lines; if goals adopt, consider HD/G on the Goal
Edge board.

FILES: app/engines/nhl_shots.py (NEW), nhl_shots_prior.py (NEW),
.github/workflows/nhl-shots-prior.yml (NEW), tests/test_nhl_shots.py
(NEW), app/engines/nhl_model.py, app/engines/nhl_sim.py,
app/views/NHL_Model.py, nhl_precompute.py, HANDOFF.md, HANDOFF_ARCHIVE.md

---

## PICK UP HERE — NFL 1st quarter / 1st half: player props on the Simulator and Bet Finder, half / quarter leader; quarters parser fixed again. 2026-10-22 (8)

**Suite 157, FAILING: none.** New tests/test_nfl_quarter_props.py (5
controls, red by exit code: quarters that miss the box kept, fit on every
week, no projection band, offered() passing THIN, no tie band);
tests/test_period_backfills.py +2 checks (controls red: statYardage
instead of the text's gain, passer dropped when the catcher isn't
found). NFL_Sim and Bet Finder headless on the archived week + a real
build. Izzy: "Do nhl and nfl make sure player props are included". This
zip supersedes qfix.zip (same parser files) if that was not pushed.

PARSER (engines/nfl_quarters): the 10-22 rerun after (7) read receiving
yards 93.1%, rushing 89.3% but QB passing yards only 72.9%. From 2025's
box scores: QBs with the right attempts but short yards (completions
dropped when the catcher's name wasn't found; a penalty enforced after
the play riding statYardage — Dak wk1 +15). Now the gain is read from
the text ('for 12 yards', 'for no gain', '22 Yd pass from', '4 yard
rush'; statYardage only when the text has none) and the passer gets the
completion and yards with or without a named catcher. The backfill log
now prints completions with no catcher found and the first QBs whose
quarters still miss (event, id, box yds, quarters yds, att). NEXT: Izzy
reruns "NFL prior quarters"; the nightly refits on the new file itself.

MODEL (nfl_quarters.fit / pmf / test, run inside nfl_sim.build on its
own split: fit weeks < 10, test 10-18 of 2025): a player's 1Q / 1H stat =
his GAME projection (the Prop Lab's) x the measured distribution of
(1Q value / game projection) for players in his projection band (three
bands per stat — a small role blanks the 1st quarter far more often).
Only player-games whose quarters add up to his box (missing != zero).
Test: vs his own last-8 1Q / 1H hit rate at a line next to his own
1Q / 1H average. On the file before this fix (z): 1Q rec 6.2, rec yds
5.3, rush yds 2.8, carries 2.2, completions 2.5 (n 161, over-predicts —
the curve fixes delivery); 1H rec 7.3, rec yds 5.9, rush yds 3.1,
carries 2.8 — BEAT. QB yards / attempts 1Q and 1H, 1H completions:
thin or fail (n ~150 — the clean QB set is small until the rerun).
Team: points share 1Q 0.195, 1H 0.491; margin sd 6.2 / 10.4. Leading
after the 1Q fails vs the league rate (z -0.2), after the 1H thin
(1.7) — on the page labelled, never on the Bet Finder.

PAGES: NFL_Sim "1st quarter / 1st half" card (span toggle; points in the
span, who leads / tie; every player's line nearest a coin flip with the
test's delivered over / under, graded label). Bet Finder NFL: "Players —
1st quarter / 1st half", ONLY the span x stat keys that beat
(nfl_quarters.offered), per-player lines, the test's curves ("@q1_rec").
Not in SGP legs yet (the simulator draws whole games).

NIGHTLY: nfl_precompute loads data/nfl/prior_quarters.json -> nfl_sim
.build(..., quarters=) -> payload "sim" gains "quarters" {model, test,
team, team_test, cut_week, clean_rows}. VERIFY LINES: "NFL 1Q / 1H: N
player-game stats whose quarters add up ...", one per span x stat, and
"NFL q1_lead_home / h1_lead_home". SGP verdicts unchanged (UW, TW beat).

FILES: app/engines/nfl_quarters.py, app/engines/nfl_sim.py,
app/views/NFL_Sim.py, app/views/Bet_Finder.py, nfl_precompute.py,
nfl_quarters_prior.py, tests/test_nfl_quarter_props.py (NEW),
tests/test_period_backfills.py, HANDOFF.md, HANDOFF_ARCHIVE.md

---

## PICK UP HERE — NHL 1st period: player props (point / SOG / goal) and period lines on the Simulator and Bet Finder; NFL quarter names fixed. 2026-10-22 (7)

**Suite 156, FAILING: none.** tests/test_nhl_sim.py +9 checks (5 new
controls, each red by exit code: equal thirds, no per-skater night, a
p1_ leg reading the final, shares() fitted on the test window, offered()
passing a THIN market); tests/test_period_backfills.py +2 checks (4
controls red: no offense-team filter, no whole-first-name tie-break, the
receiver-first scoring text read passer-first, the try in parentheses
left in). NHL_Sim and Bet Finder headless on the archived slate + a
real build. Ships WITH the MLB simulator (6) — mlb_sim.zip was never
pushed; this zip carries it. Izzy: "Do nhl and nfl make sure player
props are included".

MEASURED (last season, prior_periods.json, test = final 60 days,
17,102 skater-games; shares fitted on the 828 games before): goals by
period 0.294 / 0.349 / 0.357, shots 0.325 / 0.353 / 0.322. A 1st-period
prop = his game mean x the 1st's share (points / goals Poisson, SOG the
boards' NB) vs his OWN last-20 1st-period rate: point z 11.3, 1+ SOG
z 13.0, 2+ SOG z 12.1, goal z 11.9 — all BEAT, calibrated (point
predicted 12.7% vs 12.2%). Blending his own 1st-period history in made
it worse at every weight -> not in the number. Team lines (1st-period
O1.5, home leads after 1) vs the league's own rate: FAIL (z -0.1, n 484)
— shown on the page labelled, never offered on the Bet Finder.

SIMULATOR (engines/nhl_sim.simulate): now period by period. Per game the
team's shot environment Z, per skater his night U (gamma, var = 1/size -
shot_var so his game shots keep the boards' NB spread exactly), per
period his shots Poisson(m x share x Z x U), goals Binomial from those
shots at conv x (goal share / shot share), assists inside the period.
New outputs per skater p1sog / p1g / p1pts, per team sim["per"] (n x 3
regulation goals). leg_hits: "_game" stats prefixed p1_ read the 1st
period (p1_total, p1_home_win, p1_away_win, p1_home_margin). Re-graded
SGP kinds on real data: unchanged (PP z 3.3, PPP 3.9, PW 3.0 beat; GW,
PPPP thin; GG, PPopp fail; SS lift 1.026 z -0.2 now "fails" vs +0.3
"thin" before — noise around zero, same lift).

PAGES: NHL_Sim "The 1st period" card (team 1st-period goals, O1.5, who
leads after one with the test's label; every skater's 1st-period point /
goal / 1+ / 2+ SOG through the test's curves); SGP legs gain 1st-period
points / SOG / goals and 1st-period total / leads after the 1st. Bet
Finder NHL: "Skaters — 1st period" — only markets that BEAT
(nhl_periods.offered).

NIGHTLY: nhl_precompute parses this season's periods from the finals it
already reads (cur_periods, own try per game), adds last season's
data/nhl/prior_periods.json; nhl_sim.build(..., periods=) fits shares
before the test window, grades; games.json "sim" gains "periods"
{shares, test, games}. VERIFY LINES: "NHL periods: N last-season + M
this-season games; shares ...", one "NHL 1st-period <market>" line each.

NFL QUARTERS (engines/nfl_quarters): names now found ONLY on the team
with the ball (drive.team.id) — 'C.Williams' the Bears' QB, not a
defender, and a tackler in parentheses is never the receiver; a shared
form on one team goes to the player whose whole first name it spells
(Ty.Johnson before Tyler); scoring plays written 'X 22 Yd pass from Y'
read receiver-first; the try in parentheses is cut before the play is
read (it used to drop the whole touchdown as a two-point play). NEXT:
Izzy reruns the "NFL prior quarters" workflow; expect pass_yds well
above 74.2% (rush 88.4 / rec 91.7 up too). Then the 1Q / 1H props.

FILES: app/engines/nhl_periods.py (period model, shares, test, offered),
app/engines/nhl_sim.py, app/views/NHL_Sim.py, app/views/Bet_Finder.py,
nhl_precompute.py, app/engines/nfl_quarters.py, tests/test_nhl_sim.py,
tests/test_period_backfills.py; plus everything in (6).

---

## PICK UP HERE — MLB Game Simulator: plate appearance by plate appearance, base-running measured; SGPs graded by kind. 2026-10-22 (6)

**Suite 156, FAILING: none.** New tests/test_mlb_sim.py (5 controls, red
by exit code) — a synthetic season played by known base-running rules,
in Statcast's PA shape. MLB_Sim page headless on it. Izzy: "for mlb i
only want the simulator with the player stats".

NEEDS ONE NIGHTLY: precompute.MODEL_COLS now carries inning,
outs_when_up, on_1b / on_2b / on_3b (season frame only, dropped before
the per-player files, like inning_topbot). Until a nightly has run with
them the page says the simulator appears after the next nightly.

ONE GAME (engines/mlb_sim.simulate, numpy, 10k in ~0.9 s): each PA = the
batter vs the other side's starter (mlb_props.combine on the props
model's shrunk rates) until the starter's DRAWN batters-faced (his
starter_bf_dist) runs out, then a league-average pen; outcome 1B..OUT;
then the base-out transition DRAWN from the season's real PAs in that
state (state_rows / measure_transitions: 24 states x 7 outcomes ->
(after bases, runs, outs added); sparse cells borrow the same bases +
outcome over all outs). Runners keep order (_move: lead runners score
first; on an out the batter is out first). Runs credited to whoever
scores, RBI = runs on his PA (the site's RBI). No bottom 9th when home
leads, walk-offs, extras with the runner on 2nd, to 15, then a coin.
Gives: batters h / tb / hr / rbi / r / hrr / k / bb / s / d; starters k
/ outs / h / bb / er (runs while he's in); runs by inning (F5).

THE TEST (mlb_prop_precompute.build_sim, in build_prop_model's own try):
the last 30 days, walked forward exactly like the props test (counts
before the date; lineups and starters from the PAs): HH, HHH, TT (2+ TB),
HW, RW (HR + win), KW (starter Ks at floor(his expected)+0.5 + win),
HHopp. Marginals: the props boards' delivered chances (validation /
pitcher_validation curves); the win leg the simulator's own. Also a
runs check: simulated runs a team vs actual on 40 games — the
[verify] line prints both; on the synthetic season 4.43 / 4.62 vs 4.46.

PAGE (views/MLB_Sim.py, MLB nav after Model): confirmed lineup else last
game's (both nine needed), the game (runs, win %, total vs the posted
line, run line, first five), box score (hit / 2+ TB / HR / RBI / run
chances, H+R+RBI, K; starters' K, innings, runs), every batter over /
under (board's delivered chance; runs and H+R+RBI the simulator's own,
untested), the SGP builder (batters, starters' K / outs / hits / runs,
win, total, run line, F5 total and line), Bet Log, slip.

NIGHTLY VERIFY LINES: "MLB simulator: base-out transitions from N plate
appearances; runs per team simulated X vs actual Y; SGPs graded on N
games", "MLB SGP <kind> ...". ~2 minutes.

FILES: app/engines/mlb_sim.py, app/views/MLB_Sim.py,
tests/test_mlb_sim.py (NEW); mlb_prop_precompute.py, precompute.py,
app/app.py, app/views/Home.py (an Explore card — test_home wants a route),
HANDOFF.md, HANDOFF_ARCHIVE.md

---

## PICK UP HERE — NHL periods / NFL quarters, step 1: the one-time play-by-play backfills. 2026-10-22 (5)

**Suite 155, FAILING: none.** New tests/test_period_backfills.py (4
controls, red by exit code). Izzy (10-22): NHL and NFL period / quarter
lines WITH player props; MLB: the simulator with player stats.

TWO MANUAL WORKFLOWS, RUN ONCE EACH, then send the logs:
- "NHL prior periods" (nhl-periods-prior.yml -> nhl_periods_prior.py ->
  data/nhl/prior_periods.json): every 2025-26 regular-season summary ->
  engines/nhl_periods.parse: goals per period per team, team shots by
  period, each skater's [goals, assists, SOG] in P1 / P2 / P3 (OT out),
  the first goal. Goalies are dropped from a goal's participants (ESPN
  lists them). Refuses to write under 80% period lines or under 90% of
  skaters whose periods add up to their box-score goals.
- "NFL prior quarters" (nfl-quarters-prior.yml -> nfl_quarters_prior.py
  -> data/nfl/prior_quarters.json): every 2025 game's drives ->
  engines/nfl_quarters.parse. ESPN's NFL plays name players ONLY in the
  text, so box-score athletes are turned into the text's forms
  ('Amon-Ra St. Brown' -> 'A.St. Brown', 'Ja.Chase', suffix dropped) and
  found: pass -> passer first name, receiver first name after " to ";
  rush -> first name; TD on the play; No Play / two-point / sacks
  skipped; Q1-Q4 + OT slot. Each player's quarters CHECKED against his
  box line from the same summary; refuses under 80% rushing / receiving
  yards adding up. Logs print the play types and texts no name was found
  in — if it refuses, those lines say why.

NEXT: with those files, the NHL period / NFL quarter lines and per-period
player props (fit + test on last season, like NBA's 1Q points), and this
season's periods parsed nightly from the summaries the nightlies already
fetch. MLB simulator meanwhile (no backfill needed).

FILES: app/engines/nhl_periods.py, app/engines/nfl_quarters.py,
nhl_periods_prior.py, nfl_quarters_prior.py,
.github/workflows/nhl-periods-prior.yml, nfl-quarters-prior.yml,
tests/test_period_backfills.py (NEW); HANDOFF.md, HANDOFF_ARCHIVE.md

---

## PICK UP HERE — NFL Game Simulator: score, game script, QB-receiver yards together, TDs from points; SGPs graded by kind. 2026-10-22 (4)

**Suite 154, FAILING: none.** New tests/test_nfl_sim.py (6 controls, red
by exit code, listed in the test). NFL Simulator page headless on the
week-7 payload with the real sim block. Ships WITH the NHL simulator
(this zip carries every NHL file too; nhl_sim.py no longer imports
model_view, which pulls in streamlit). NEXT: NHL periods, NFL quarters,
MLB first 5.

ONE GAME (engines/nfl_sim.simulate): margin / total normal from the game
model -> team points; per team x = points / projected - 1 and script m =
(margin - projected) / sd. Each line = projection x (1 + e_score x +
e_script m), e MEASURED per stat on 2025 weeks 2-9 (volume-weighted least
squares): pass yds +0.53 / -0.15, rec yds +0.44 / -0.11, rush yds +0.10 /
+0.10 (ahead -> run). Yards: one residual per line, correlated by type at
the MEASURED residual correlations after the score: QB-receiver +0.27,
receiver-receiver 0.00, QB-rush -0.14, receiver-rush -0.04, back-back
+0.08 (Cholesky; shrunk if not positive definite); spread = the board's
cv less what the shocks gave; floored at 0 like the board. Counts NB with
the shocks. TDs: Poisson(team points x TDs per point), each passing at
QB pass_td / team expected TDs, handed out by td_exp split receiving /
rushing by targets vs carries; QB pass TDs = the passing ones.

FIRST TRY DROPPED (measured): the QB's yards as the SUM of his receivers'
— QB + top receiver priced x1.42 where real games ran ~x1.03 (a
receiver's 0.29 residual correlation, not the arithmetic of the sum).

THE TEST (2025 weeks 10-18, 137 games, + this season — grows nightly):
BEATS: a back's rushing yards + his team wins (z 2.7), a TD + his team
wins (z 2.2). THIN: QB + two receivers (z 0.7). FAILS: QB + top receiver,
both QBs over, QB + receiver TD, two teammates to score (n 120-270 each;
small — this season adds ~14 games a week). TDs in the test: anchored to
the market's implied points when 2025 has a line (95 of 272), else the
game model's projected points.

PAGE (views/NFL_Sim.py, NFL nav after Model): the game (score, win %,
total and spread vs the book's), box score by QB / backs / receivers,
every player over / under (the Prop Lab's delivered chance), the SGP
builder (players, team to win, totals, spreads), Bet Log, parlay slip.

NIGHTLY VERIFY LINES: "NFL simulator links", "NFL same-game parlays
graded on N games", "NFL SGP <kind> ...". ~20 s.

FILES: app/engines/nfl_sim.py, app/views/NFL_Sim.py,
tests/test_nfl_sim.py (NEW); nfl_precompute.py, app/app.py,
app/engines/nhl_sim.py, app/views/NHL_Sim.py, HANDOFF.md,
HANDOFF_ARCHIVE.md (+ the NHL simulator files)

---

## PICK UP HERE — NHL Game Simulator: shots, goals from shots, assists, OT; same-game parlays graded by kind. 2026-10-22 (3)

**Suite 153, FAILING: none.** New tests/test_nhl_sim.py (6 controls, red
by exit code, listed in the test). Simulator page headless on the 10-22
NHL slate (archive payload + the real sim block). NEXT: the NFL
simulator (Izzy: "start with the simulators first"), then NHL periods /
NFL quarters / MLB first 5.

ONE GAME (engines/nhl_sim.simulate, numpy, 10k in 0.12 s): each team's
shot environment Z (lognormal, variance 0.011 and home/away corr -0.14,
MEASURED on last season's team shots past the Poisson part); each
skater's SOG negative binomial at the board's size around mu x Z; HIS
goals Binomial(his shots, his goals-per-shot x Z^(e-1)), e = 0.32
measured (goals rise with shots, not one-for-one), scaled so the team
averages the GAME MODEL's goals (18 dressed skaters' rates add to more);
"someone else" for the rest; assists 0/1/2 per goal at 6/18/76%
(measured from team-game goal and assist totals: mean AND variance per
goal), from teammates other than the scorer by assist rate; tie -> OT,
home wins at the model's measured 0.686; saves = other side's shots -
its regulation goals.

FIRST TRY DROPPED (measured): a fixed team total shared among shooters
made two teammates' goals pull apart (lift 0.96 where real ones go
together) — it failed its test. Goals from his own shots: lift 1.00.

THE TEST (last season's final 60 days, 484 games, + this season — grows
nightly): the delivered chances multiplied vs x the lift. BEATS: 2
teammates with a point (z 3.4, lift 1.11), 3 with a point (z 4.0), a
point + his team wins (z 3.0). THIN: goal + his team wins (z 1.8), 4
point legs, 2 teammates over their shots lines. FAILS (no real link):
2 teammates to score, a point-getter from each side. sgp_support: a
beaten kind with 100+ graded can reach STRONG; anything else (unders,
totals, saves, 2+ points) stays THIN, and the page says why.

PAGE (views/NHL_Sim.py, NHL nav after Model): the game (average goals,
win %, OT %, puck line, total vs the book's), the box score (SOG range,
goal / point / 2+ / assist chances, starter's saves), every skater over
or under (delivered like the boards), the SGP builder (skaters, team to
win at the model's market-anchored chance, totals and puck lines at the
simulator's own, goalie saves), Bet Log and parlay slip.

NIGHTLY VERIFY LINES: "NHL simulator links", "NHL same-game parlays
graded on N games", "NHL SGP <kind> ... -> beats / thin / fails".
Runtime ~100 s (the walk-forward skater rows).

FILES: app/engines/nhl_sim.py, app/views/NHL_Sim.py,
tests/test_nhl_sim.py (NEW); nhl_precompute.py, app/app.py, HANDOFF.md,
HANDOFF_ARCHIVE.md

---

## PICK UP HERE — NBA learns this season: minutes pull, team minutes add to 240, ROLE / NEW TEAM flags, roster margin, nightly re-tune; a refresh on every page. 2026-10-22 (2)

**Suite 152, FAILING: none.** New tests/test_nba_upgrades.py (7 controls,
red by exit code, listed in the test) and tests/test_refresh_buttons.py
(1 control, red). Dry run of the nightly; Tonight, Props, Simulator,
First Basket, Trends, Next Man Up and the Bet Finder headless, plus 8
non-NBA pages with the new button. Ships with the 10-22 newcomers batch
below (Izzy uploaded nba_newcomers.zip but never unpacked it).

WHY (Izzy): "none of the teams will operate like last season ... the
site needs to recognize stuff like that and adapt." Every piece below
was measured on 2025-26 before it moved a number:

1. OLD-TEAM GAMES — NOT DISCOUNTED. 129 team changes last season (107 at
   the deadline). Cutting the old team's games in the long-run tracker or
   the shrink made it worse; cutting the 2-game window was thin (fit
   window fails, test z 2.3, pooled z 0.2). The 2-game half-life already
   moves his minutes within ~3 games. NEW TEAM is a flag, not a number.
2. THE MINUTES PULL (nm.DOWN_PULL, fitted 0.3): a drop below his
   long-run minutes is pulled 30% back (a rise is not). Drops held only
   ~40% over the next 10 games, rises ~52% (nm.role_check). Paired vs no
   pull on the unseen window: beats z 4.25; on traded players alone, z
   2.5. Scored on the SAME player-games (the pull lifts rows over 10 min).
3. TEAM MINUTES ADD UP (nc, piece 3): rotation (projected 10+, who
   plays) scaled by (220 / their sum)^0.5. Their sum ran 237 +/- 30. vs
   without, unseen: beats z 6.8. All 8 props tests improved (points Brier
   0.2364 -> 0.2338, PRA 0.2351 -> 0.2310). Tonight: why line says
   "team minutes ... scaled -6%". Backtest "who plays" = who played.
4. ROSTER MARGIN (engines/nba_roster): sum of tonight's projections,
   minutes to 240. Fit-window margin MAE 11.84 -> 11.45 at w 0.3; the
   unseen window THIN (z 0.4) -> weight 0, shown on Tonight as
   information ("Tonight's rosters say ..."). Totals did not help. The
   test window includes this season, so it is re-judged nightly; at
   "beats" the margin blends in (ngm.project mu=) and the Simulator
   follows.
5. ROLE ↑ / ↓: this season's minutes vs his opening-night projection,
   3+ minutes and 2 SE (sd 6.5 min/game), 3+ games. Flag only.
6. NIGHTLY RE-TUNE: champion = data/nba/settings.json (committed by the
   nightly, in the "Commit NFL projection log" step); challenger = the
   same grid on the 45 game-days before the newest 14; replaces only on
   "beats" there. Starts once this season has 21 game-days and 1,500
   player-games in the newest 14. Log: "[verify] NBA settings ...
   held / REPLACED"; Tonight shows "settings in use since ...". On last
   season's March as a fake season it replaced (k 600 -> 300, z 2.1).
   Leak, said here: a replaced set is fitted on days the props test also
   grades.

REFRESH: "⟳ Sync latest" under the header on every nav page except Live
(own Refresh), Bet Log, Home and the admin pages.

NIGHTLY VERIFY LINES TO READ: "NBA minutes pull 0.3 ... beats", "NBA
settings ...", "NBA role changes on 2025-26", "NBA team minutes add up:
... in the number: yes", "NBA roster margin: ... in the margin: weight",
"NBA rosters: N games with a roster margin; M players flagged".

FILES: nba_precompute.py, .github/workflows/nightly-data.yml,
app/engines/nba_model.py, nba_context.py, nba_roster.py (NEW),
nba_view.py, nfl_game_model.py, bet_finder.py; app/views/NBA.py,
NBA_Props.py, Bet_Finder.py, Results.py + the 18 pages with the new
button; tests/test_nba_upgrades.py, tests/test_refresh_buttons.py (NEW),
tests/test_nba.py; HANDOFF.md, HANDOFF_ARCHIVE.md

---

## PICK UP HERE — NBA newcomers (rookies, back from a lost season) on the site; the 10-21 slate graded. 2026-10-22

**Suite 150, FAILING: none.** test_nba +3 checks, control (side_props
without newcomer_rows — the bug) red by exit code. Dry run of the
nightly; Tonight and Props headless.

THE BUG (Izzy, 10-22: "players that came back from injury or got drafted
weren't on the roster"): side_props walked only the POOL (last season's
regular-season players + this season's), so a rookie, or a man who
missed all of 2025-26, did not exist on the site until his first
regular-season game — role_watch hid them too (sorted by minutes change,
None last, cut at 40). newcomer_rows: tonight's roster players missing
from the pool (no roster: this preseason's team) — 2+ preseason games ->
projected from them (nm.project_now on the preseason box scores), row
"new": True, the why says so; fewer -> g["<side>_no_data"], listed by
name under the team on Tonight. A NEW row is UNTESTED everywhere:
nv.chance forces it, bet_finder.support_at honours "_untested", Long
Shots skips it, the Bet Finder name carries "· NEW". Once he plays a
regular-season game he joins the pool and the tested model.

THE 10-21 SLATE, GRADED BY HAND (the nightly archive is public:
github.com/.../releases/download/nightly-data/statcast_data.tar.gz has
data/nba/games.json): 8 finals — model winners 4 of 7 (one 50/50), the
book's 6 of 8; margin MAE model 14.9 vs book 13.6 (last season's model
11.5); total MAE model 10.9 vs book 9.5; 2 of 8 finals outside the
model's 80% range (expected ~1.6). The weak point: team ratings carry
last season at 0.956 and know no offseason moves. NEXT NBA BUILD: team
projections from the sum of tonight's player projections (roster-aware,
context-adjusted) — test on last season vs the team-rating model first.

THE REPO IS PUBLIC (checked 10-22): the Bet Log must write to a PRIVATE
repo (BETLOG_REPO), never this one. Izzy told.

FILES: nba_precompute.py, app/engines/nba_view.py, app/engines/bet_finder.py,
app/views/Bet_Finder.py, app/views/NBA.py, tests/test_nba.py, HANDOFF.md,
HANDOFF_ARCHIVE.md

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
