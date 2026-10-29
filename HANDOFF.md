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

## PICK UP HERE — Live tested for every NBA stat (play-by-play rebounds / assists / threes), anchored calls that beat DraftKings get past THIN, NHL goal ratings' search un-pinned with a nightly form check. 2026-10-29 (2)

Izzy: "simulators as close as possible to the outcome ... some projections
seemed a bit low ... Bet Finder and Live — running fully or capped?"

**Measured:** NBA offered projection vs box since 10-27 (2 nights): pts
x1.025, reb x1.030, ast x1.035, 3PM x1.086 (DK lines sat on the actuals).
A POOLED level factor (all stats, walk-forward) did NOT help on 10-28
(z -0.20; 10-28 came in x1.02) — not proven, not forced; offered_level keeps
testing nightly. NHL runs slightly high (SOG x0.956). The simulators' player
means ARE the projections, so they follow these numbers.
Sim inputs (published 10-29): team ratings start from last season x
carryover and move with this season's games by shrink k — NBA carry 0.956
k 3.2, NFL 0.404 / 3.7, NHL shots 0.879 / 7.1, NHL goals 1.0 / 400 (ON the
old search edge).

**Changes:**
- game_model.K_MAX 400 -> 5000 (a fit pinned to its edge); form_check:
  fitted k vs k = 20 walk-forward on this season, shipped as model
  "form_check", printed `NHL goal ratings vs this-season form ...`.
- nba_pbp: "qstats" {pid: {reb|ast|tpm: [q1..q4, ot]}} — rebound plays
  (participant 0), assists (made FG, participant 1, text says assist), made
  threes (scoreValue 3); "qstats_ok" = stats whose per-player sums equal the
  box score for EVERY player (a misread format is left out, never guessed).
  nba_quarters.live_check now per stat (pts, reb, ast, tpm, combos from
  parts); Live lists the tested stats. LAST SEASON'S prior_pbp.json has no
  qstats until the "NBA prior play-by-play" workflow is re-run; this
  season's games get them nightly. Log: `NBA play-by-play stat counts that
  match the box score: reb in N ...`.
- Bet Finder: a no_edge / behind market's THIN cap is lifted for a call
  that is ANCHORED and whose market's anchored chances beat DK's own on the
  walk-forward (market_anchor.beats_book). None qualify yet.
- NHL Live has never been tested: the one-time "NHL live test" workflow
  (data/nhl/live_check.json) has not been run — run it.

Tests: test_nba_live_stats, test_form_check, test_market_anchor (+beats_book),
test_book_grade (cap wiring). Controls red: qstats_ok not checking the box;
assists to the shooter; live_check ignoring qstats_ok; K_MAX at 400;
form_check with one k; beats_book ignoring "used".

---

## PICK UP HERE — Matchup letters rebuilt on what predicts (NBA: beat-their-projection vs the defense; NHL: the matchup in the number), and chances anchored to DraftKings where it has proven to beat them. 2026-10-29

Izzy: "how do we improve the grading ... and matchup grades as well".

**Measured first (10-29, graded record after 10-28's nightly):**
- NBA main lines: our over chance averaged 0.397, overs hit 0.503, DK 0.495;
  calibration slope of our chance 0.31; where our projection disagreed with
  DK's line the box score followed at 0.08 per unit (3PM 0.91, ast 0.40,
  pts 0.10, reb 0.02, combos ~0). Widening the NB size did not fix it
  (Brier 0.2569 -> 0.2554 best). NHL slope 0.92, close to DK.
- Projection level after the team-minutes fix: 10-28 ours 12.41 vs actual
  12.64 (x1.02) — near level; OFFERED LEVEL not used (thin).

**1. NBA letters (nba_context.apply_tonight, matchup_grade.nba_grades).**
Walk-forward on last season (20,333 player-games, residual = actual /
projection - 1, by letter): ranking the projection's own opponent factor
(how players did vs their projections against this defense) across the 30
teams -> pts A +4.7 B +1.8 C -1.3 D -4.3 F -5.1%; reb A +4.8 .. F -8.9; ast
A +7.4 .. F -7.7; 3PM A +7.3 .. F -9.1. The 10-28 raw "allowed to his
position a game" letter: pts A +0.4 B +1.6 C -1.4 D -0.9 F -3.3 (weaker, out
of order). Position split on top of the factor: R2 0.44% -> 0.47% (nothing).
So the letter is the opponent factor again (as 10-26) but ranked over the
30 NBA teams (letter_teams: the DvP table's, else ESPN ids 1-30 — 10-26's
had 33 with exhibition clubs) and A+ .. F-. The G/F/C card stays on the row
("dvp", context); a stat the factor is not in takes the card's letter.
NOTE: the 10-28 switch to raw DvP was a step backwards — this undoes it.

**2. NHL letters (nhl_model.letter_cuts / matchup_letter / letter_cards).**
Walk-forward last season (36,887 skater-games from mid-Nov, vs his baseline
rate): the team matchup ratio already in the chance (shot ratio for SOG,
goal ratio for G / A / PTS) sorted best — SOG A +6.0 .. F -9.4, G A +7.5 ..
F -7.3, A A +8.7 .. F -8.5, PTS A +8.3 .. F -8.1; raw allowed to C/W/D (the
old letter) SOG A +5.0 .. F -9.3, G out of order (B -5.1); beat-baseline vs
the defense (team or C/W/D) no better. Letter = tonight's ratio against the
season's ratios in fifteen equal steps (model["letter_cuts"]); the C/W/D card
keeps its rank and "position_grade"; badge reads "B+ · x1.04".

**3. DraftKings anchor (engines/market_anchor; fit in book_props_grade ->
scorecard "anchor"; Bet Finder via bet_finder.anchor_chance).**
p = logistic(logit(book) + b (logit(ours) - logit(book))), b on 0..1 per
league / market ("stat" main, "stat*" alternates), walk-forward by date vs
the SERVED chance, used on "beats" with 150+ test lines; NBA learns from
10-27 on (SINCE). Applied only with BOTH of DK's prices in (de-vigged). The
record still stores the model's own chance (never learned from its output);
THIN caps (market_status) unchanged. 10-29 run: nothing used yet for NBA
since 10-27 (one night tested); all-history fit had pr / ra used, most
markets thin (z 1-1.9) — expect them to switch on over the coming week.
Nightly prints `[verify] DRAFTKINGS ANCHOR <lg>: ... -> USED / not used`.

Tests: test_nba_letters, test_nhl_letters, test_market_anchor (+ updated
test_matchup_grade). Controls (all red): card letter first again; exhibition
clubs kept; NHL cuts read upside down; position letter left in place; SOG on
the goal ratio; anchor b peeking at the scored night; gate without MIN_TEST;
anchoring with one price.

---

## PICK UP HERE — A-F letters adjusted for how much of a defense's standing is real (no A or F from a ranking that does not repeat), and split into A+ .. F- so a C still shows its lean. 2026-10-28 (2)

Izzy compared with HOF after the defense-vs-position letters went live
(14:04 nightly). PHI @ IND points: Siakam / Toppin (F) read "F" here,
"B-" on HOF. Cause: last season's fitted weight for forwards is 0.0026
(centres 0.007 — rosters change), so the blend WAS this season's 4 games
(PHI 25.8 pts/g to forwards, 29th; last season 18th), and a rank cut in
fifths spreads A-F however noisy the gaps are (points allowed to forwards:
split-half reliability 0.003 — none).

Now defense_matchup.reliability_grade (used by card(), so NBA, NHL, NFL):
  p1 = R / (n - (n-1) R)            R split-half, n games a team last season
  r  = m p1 / (1 + (m-1) p1)        m = n_cur + weight x n_prior
  z  = sqrt(r) (value - mean) / sd  across defenses on that basis
  cut at +-0.253 / +-0.842 (normal fifths) = the old rank cut when r = 1.
_summarise ships "spread" (mean, sd per basis) and "games_full"; the card
ships "grade_reliability" and "n_eff"; rank stays on the card. MLB starter
cards (no reliability) keep the rank letter.
Last season's NBA table: forwards' points / centres' points all C; guards'
assists (R 0.81) still spread A-F. Early in a season most C / F letters
read C and spread as this season's games build — by design.
Expect FEWER A/F than HOF; the by_grade check (Site vs DraftKings) is the
test of whether letters carry information.
tests/test_grade_reliability.py (controls: no sqrt(r); n_eff without last
season; card keeping the rank letter — all red).

PLUS / MINUS (same batch). Izzy: "don't ignore C grades — I don't use
anything else than our site ... make sure ours is super sharp". Every letter
is now one of fifteen (A+ A A- B+ ... F-): matchup_grade.label_from_q /
grade_pm (rank cards: MLB starter / lineup, rank fallback) and the
reliability z through the normal (q = 1 - Phi(z)). A C+ leans soft without
the evidence for a B; C- leans tough. matchup_grade.base() gives the A-F
letter for colours (model_view.matchup_css), the per-letter check
(by_grade) and the Under flip; flip() mirrors the sign too (A+ <-> F-,
C+ <-> C-). Graded rows saved before 10-28 carry plain letters — base()
reads both. Controls (red): flip keeping the sign; by_grade without base();
five steps instead of fifteen.

---

## PICK UP HERE — Matchup letters checked league by league: NBA letters now defense vs position (were a rank of near-ties over 33 teams); MLB batter letters by the hitter's hand where that tested better. 2026-10-28

Izzy: "are players getting their grades from what the team allows in
general or by the position ... I see players with the same exact grades".

**What each league's letter is (and the same position + same opponent =
the same letter everywhere: it grades the DEFENSE vs that kind of player):**
- NHL: by position already — centres / wingers / defencemen
  (nhl_model.dvp_group). LW and RW are one group (W). Correct; no change.
- NFL: by position already (QB / RB / WR / TE). No change.
- NBA: WAS WRONG. The letter ranked the projection's opponent factor —
  team-wide on pts / reb / ast (by position predicted WORSE: z -0.92 pts,
  -1.63 reb, -0.64 ast, -0.13 3s on last season's final 45 days), and
  within a percent or two of 1.0 for nearly every team, so a letter was a
  rank of near-ties (Dean Wade @ IND: x0.999 -> "B"; HOF showed "A") — and
  it ranked 33 "teams" (ESPN ids 111386 / 132374 / 132375, exhibition
  clubs). Now nba_context.dvp_table: what each defense ALLOWED to G / F / C
  a game, this season + last (defense_matchup, same engine as NHL / NFL),
  preseason left out, a defense needs 20+ games (drops exhibition clubs).
  The projection's factor is unchanged (tested); the nightly prints both
  `NBA opponent factor in the projection: ...` and `NBA matchup letters:
  defense vs position over 30 teams; ... reliability`.
  Last season: IND allowed forwards 41.16 pts/g vs 41.14 league (11th, B);
  split-half reliability of pts allowed: G 0.57, C 0.40, F 0.003 — a
  forward's points letter does not repeat (in any app). ESPN gives only
  G / F / C. tests/test_nba_dvp.py (controls: no 20-game filter;
  preseason kept; one group for all — all red).
- MLB: WAS WRONG for the ask — every hitter facing a starter got that
  starter's overall letter. Now defense_matchup.fit_platoon tests, per stat,
  the starter's rate against the hitter's side (same / opposite arm; switch
  hitters = opposite) vs his overall rate: season in thirds, select on the
  middle, test on the last, squared error per PA, adopted at z >= 2.
  On the 2026 season (tested 08-12..10-27): tb own split z 2.38, bb own
  z 2.90, hr league gap z 2.46, singles league gap z 2.71 -> adopted;
  hits (z 1.42), strikeouts (z 1.65), doubles (fails) -> overall.
  The letter ranks the starter among EVERY starter against hitters of that
  hand (a RHP vs lefties is compared with LHPs vs lefties — ranking by
  "same side" across both arms would mix lefty and righty hitters).
  On 2026 data ~2/3 of starters now give lefties and righties different
  letters on tb / hr / bb / singles. The card says "left-handed batters" /
  "right-handed batters" / "switch hitters" and basis "platoon".
  Batter hands ship in prop_model.json "batter_hand" (S = 10%+ from each
  side). Pitcher-prop letters (tonight's lineup) unchanged.
  The props' CHANCES do not use the hand split (only the letter); whether
  they should is a separate test (rule 1).
tests/test_mlb_platoon.py (controls: rank by side not hand; switch hitter
as same-side; gate ignoring the test — all red), test_matchup_grade.py.

---

## PICK UP HERE — Four follow-ups: the projection level learns from the graded DraftKings lines (gated); NHL saves checked; the MLB runs check made same-sample; NHL fitting 2.2x faster with identical output. 2026-10-27 (2)

Izzy, after the team-minutes fix: "Let's finish all of them".

**1. Offered projection level (engines/offered_level).** Graded rows carry
our offered projection and what the player did (since 10-26). Per base stat:
factor = 1 + (sum actual / sum ours - 1) x n/(n+150), clipped 0.85-1.20;
tested walk-forward by night (each night scaled by the factor from the
nights BEFORE it, squared error vs unscaled, paired verdict); USED only on
"beats" with 150+ test lines. NBA (pts reb ast tpm; combos re-summed) learns
only from 2026-10-27 on (`LEVEL_SINCE`): the team-minutes fix already moved
every NBA projection ~6%, and learning from the earlier nights would
correct it twice. NHL (sog, a; points follow) re-prices each skater's
stored chances and expected shots / points from the scaled means
(`nhl_refresh`, same distributions as nhl_model.probs). Nightly prints
`[verify] OFFERED LEVEL NBA/NHL ... -> USED / not used`. On the record as
of 10-27 nothing is used (one night graded; NBA none since the fix). Until it
switches on, NBA rebounds / assists still lean a little low vs DraftKings.
tests/test_offered_level.py.

**2. NHL saves:** graded record site Brier 0.2247 vs book 0.2441 (n=26). No
change.

**3. MLB "simulator 6% high" (4.43 vs 4.17) was the check, not the
simulator:** it set the first 40 games' simulation beside EVERY game's runs
(two samples) with no error bar; 40 games carry about +-0.35 runs.
`runs_check` now compares the same games and prints se, z, verdict ("in
line" under 2 se). On the test season: 4.5 vs 5.05 +- 0.31 -> in line. The
simulator is unchanged. Season over; read the line in spring before
touching run levels. tests/test_mlb_sim.py.

**4. NHL nightly speed:** ~8 of the NHL step's ~9 minutes were the fits
(ice time, PP weight, shot factors) calling nhl_model.probs millions of
times. model_math.nb_pmf now keeps the lgamma table per (size, length), and
probs(only=...) builds only the family a fit reads. Build on last season's
file: 228 s -> 103 s, output byte-identical (compared JSON).
tests/test_nhl_fit_speed.py checks equality float for float.

Negative controls (all red by exit code): factor reading the same night;
gate ignoring MIN_TEST; combos not re-summed; runs check reading every
game's actual; nb table keyed on size alone; only= building points from
goals alone.

---

## PICK UP HERE — Found why the offered NBA projections ran low: the team-minutes scale counted the whole roster tonight but only who played when it was tested. Fixed to the tested definition. 2026-10-27

**Suite 174, FAILING: none.** tests/test_nba_context.py +2 checks
(control red: rotation_total summing the whole roster).

READ 10-27 nightly (13:43 UTC):
  OFFERED PROJECTION vs BOX (10-26 games, first night with the projection
  captured), actual / ours: NBA pts x1.063 (DK line 14.54 vs ours 13.3),
  reb x1.172, ast x1.108, pr x1.116, pa x1.099, pra x1.093, ra x1.086
  (n 71-110); NHL a x1.234, pts x1.132 (n 65), sog x0.966, sv x1.023.
  MATCHUP GRADE nba (n ~140 a letter): over hit A 0.43, B 0.49, C 0.49,
  D 0.49, F 0.53 vs site ~0.38 each — no letter effect yet; nhl too small.
  Timing: 35.0 -> 30.5 min. NPB ~0 (fail-fast works). Summary cache:
  restored 19 MB, saved. NHL still 8.9 min: the season fetch is ~1 min
  now; the rest is FITTING (5 min in the game model + props validation
  after the environment line, 3 min in periods) — CPU, not network.
CAUSE (measured on the published 10-27 games.json): every NBA row's
ctx.vol was 0.83-0.97 (mean 0.887). nba_context.vol_factor scales by
(220 / team total)^0.5, the total TESTED as the projected minutes of the
players who PLAYED (2025-26: median 10 players, 235 min) but SERVED as
every roster player projected 10+ (10-27: 11-15 players, 234-321 min).
Doncic 27.3 projected vs 34.3 season. FIX: ctx.rot_n = rotation_size()
(median count projected 10+ who played, measured on the fit; 10), and
apply_tonight's total = rotation_total(rows, rot_n) = the rot_n biggest
projected minutes. On 10-27 that moves the scale from ~0.89 to ~0.94
(about +6% on every NBA projection, the size of the pts gap). Printed:
"[verify] NBA team minutes counted over the top N projected players".
NEXT: the OFFERED PROJECTION line over the next nights — NBA pts should
sit near x1.00; reb ran x1.17, more than this explains (look at the reb
rate / opponent factor next if it stays high). NHL assists / points
x1.13-1.23 on one night: watch before touching.

FILES: app/engines/nba_context.py, nba_precompute.py,
tests/test_nba_context.py, HANDOFF.md, HANDOFF_ARCHIVE.md

---

## PICK UP HERE — Speed and space audit: finished games fetched once, NPB fails fast, prop day files kept 14 days, First Basket / UFC stop waiting on the network one call at a time. 2026-10-26 (4)

**Suite 174, FAILING: none.** New tests/test_summary_cache.py (controls
red: a final served 2 h after it started; a game in progress kept; a
20-day file still waiting to be graded dropped). tests/test_ufc.py +1
(control red: one worker). tests/test_nba_first_confirmed.py +2 (control
red: lineup window always open).

MEASURED 10-26:
  Repo: 40 MB tracked, .git pack 10 MB. Biggest: hr_research ndjson
  (13 MB, ~6 MB a month while MLB plays), prior-season files (1-2 MB each,
  fixed), data/props day files 3.5 MB and ~1.5 MB more a day (each run
  rewrites today's). Two stale uploads tracked at the root:
  loscappers-full-batch.zip, loscappers-prop-colours.zip (*.zip is in
  .gitignore; they came in through "Add files via upload").
  Published archive: 45 MB gz / 104 MB (95 MB = 2,603 Statcast parquet
  files; payload JSONs 1-2 MB each). Left alone (MLB pages read it).
  Nightly 10 AM: 35 min. NHL 9.1 (every final of the season re-fetched
  every run), NPB 5.1 (npb.jp ConnectTimeout x ~14 at 25 s), tests 7.7,
  MLB statcast 4.3, NBA 3.1.
  Every page rendered on the real archive (AppTest, 41 views), no
  exception. Slow only where the page calls the network as you wait:
  First Basket 33.8 s (one ESPN summary per slate game, every game), UFC
  7.7 s (~26 calls one after another); NHL / NFL Tonight ~5 s (live
  injury feed; this sandbox has no network, so those are upper bounds).

CHANGES:
  espn_feed.fetch_summary: with ESPN_SUMMARY_CACHE set (nightly only), a
  FINAL fetched 36+ h after its start is kept gzipped and reused; anything
  else fetched live; only for the real fetcher (a test's fake never
  writes it). nightly-data.yml: env PYTHONUNBUFFERED=1 +
  ESPN_SUMMARY_CACHE, an actions/cache@v4 step (continue-on-error) for
  .cache/espn-summaries; .gitignore .cache/.
  npb_precompute._npb_get: connect timeout 8 s; the first connection
  failure marks npb.jp down for the run.
  book_props_snapshot.prune: day files dropped at 14 days when nothing
  in them waits to be graded, at 30 days regardless (graded rows stay in
  data/props/graded); prints "[verify] BOOK PROPS: N day files ... removed".
  First Basket: ESPN asked only for games within 2.5 h of tip
  (nba_first.lineup_window), all at once (8 threads, 6 s timeout, one try).
  ufc.build: fight odds fetched side by side (8 threads).
NEXT: read the first nightly after this: the NHL / NBA / NFL steps should
drop to minutes once the cache is warm (the first run after it still
fetches everything); NPB ~10 s. With PYTHONUNBUFFERED, the NHL step's
own slow parts become visible if it is still long.

FILES: app/engines/espn_feed.py, npb_precompute.py, book_props_snapshot.py,
.github/workflows/nightly-data.yml, .gitignore, app/engines/nba_first.py,
app/views/NBA_First_Basket.py, app/engines/ufc.py,
tests/test_summary_cache.py (NEW), tests/test_ufc.py,
tests/test_nba_first_confirmed.py, HANDOFF.md, HANDOFF_ARCHIVE.md;
removed: loscappers-full-batch.zip, loscappers-prop-colours.zip

---

## PICK UP HERE — Each simulator has its own settings (engines/sim_settings); runs are made in pieces and kept once, so the NHL simulator stops eating the server's memory. 2026-10-26 (3)

**Suite 173, FAILING: none.** New tests/test_sim_settings.py (controls
red: merge keeping the first piece; run ignoring the chunk; every piece
on the same seed); tests/test_sim_counts.py reads the per-sport settings.

Izzy: "NHL simulator be crashing on me ... maybe all of them need their
own settings, I think all of them are sharing settings and logic". They
were: every *_Sim page copied one block (st.cache_data, 4 runs kept, the
whole game in one numpy pass).

MEASURED 10-26 (the sims' own test games, one run): NHL 50,000 +147 MB
while running, 31 MB kept; MLB 50,000 +81 MB / 25 MB; NBA +14 / 4; NFL
+26 / 5. st.cache_data pickles: every click unpickled a fresh 31 MB copy,
and 4 runs were kept per page; the NHL parlay ran 50,000-game chunks
on top. That is the crash.

CHANGE: engines/sim_settings.SIMS, one entry per sport — games (as
before: NHL / NBA / NFL 50,000, MLB 25,000), chunk (NHL 10,000, NBA /
NFL 25,000, MLB 5,000), keep 2, sgp + sgp_chunk (NHL 200,000 / 10,000,
NBA 500,000 / 100,000, NFL 200,000 / 50,000, MLB 50,000 / 5,000).
sim_settings.run plays the run in pieces (seed + 7919 k each) and joins
them (merge: arrays along axis 0, dicts key by key). Each page: SIM =
_ss.settings("<sport>"), N_SIMS = SIM["games"], _run under
st.cache_resource(ttl=900, max_entries=SIM["keep"]) (one shared copy,
the pages never write into a sim), joint_precise(n=SIM["sgp"],
chunk=SIM["sgp_chunk"]). NHL 50,000: peak 141 MB -> 62 MB (tracemalloc);
means and a skater's point chance match one big run within noise; every
sim's joined output has the same keys, shapes and dtypes as one run.
NEXT if it still drops: lower NHL keep to 1 or its chunk to 5,000 —
both are one number in SIMS.

FILES: app/engines/sim_settings.py (NEW), app/views/NHL_Sim.py,
app/views/NBA_Sim.py, app/views/NFL_Sim.py, app/views/MLB_Sim.py,
tests/test_sim_settings.py (NEW), tests/test_sim_counts.py, HANDOFF.md,
HANDOFF_ARCHIVE.md

---

## PICK UP HERE — Markets clearly BEHIND DraftKings are capped at THIN now (not after 300 lines); every captured line keeps the projection we offered, so the next grade measures our projections against the box score. 2026-10-26 (2)

**Suite 172, FAILING: none.** tests/test_book_grade.py +5 checks
(controls red: "behind" on any fails without the z; ladder rungs counted
twice in the projection check); test_matchup_grade.py follows the new
graded-row shape.

READ 10-26 10 AM nightly:
  First 3 minutes on real projections: any point beats the league rate
  (z 6.18) and his own record (z 2.74); a made FG beats both too (z 5.33
  / 2.72). Not capped.
  First Basket confirmed five: beats (z 2.84).
  NBA projection bias (walk-forward test rows): last season x1.00 on
  every stat (control clean); THIS season actual / projected x0.87 pts,
  x0.93 reb, x0.86 ast (all rows), x0.88 pts (20+ min) — the walk-forward
  OVER-projects returning players this season (~43 games in).
  Site vs DraftKings, two NBA nights (10-24, 10-25): site mean over
  chance 0.38 both nights vs DK 0.49 / 0.50, overs hit 0.58 / 0.51.
  Implied from the captured chances at DK's main points line: our mean
  ~0.9-1.1 points under DK's line (13.95 vs 14.83; 13.5 vs 14.63), plus
  the negative-binomial skew (an even mean prices the over ~0.45). NBA
  pts / pr / pa / pra / tpm fail at z -2.2 to -3.1 on 130-180 lines.
  NHL: pts fails (z -2.96, n 304), g* fails (z -2.33), a / sog thin-ish;
  site 0.40 vs DK 0.42 vs hit 0.43-0.44.
  THE TWO NBA READS DISAGREE (walk-forward says too HIGH, tonight's
  offered chances sit LOW vs DK and the box): the offered pipeline
  (project_now, minutes, team-minutes 220 / beta 0.5, injuries) is not
  the walk-forward pipeline. Not guessed at: measured next.

CHANGES. book_grade.market_status: "behind" when n >= 100 and z <= -2
(BEHIND_MIN / BEHIND_Z) — the Bet Finder caps it at THIN and labels it
"BEHIND DraftKings so far"; Site vs DraftKings shows BEHIND DRAFTKINGS.
Only ever a cap ("beats" still needs 300). capture saves our offered
projection (the pmf mean) as element 7; grade_event appends [letter,
our projection, what he did]; projection_bias -> nightly "[verify]
OFFERED PROJECTION vs BOX <lg>: <stat> ours vs actual (x ratio, DK line,
n)" and scorecard "bias". NEXT: two nights of that line; if NBA ours /
actual sits clearly under 1 while DK's line ~ actual, fix the offered
pipeline at the source (minutes first), test, adopt only if it beats.

FILES: app/engines/book_grade.py, book_props_grade.py,
app/views/Bet_Finder.py, app/views/Site_vs_Book.py,
tests/test_book_grade.py, tests/test_matchup_grade.py, HANDOFF.md,
HANDOFF_ARCHIVE.md

---

## PICK UP HERE — Matchup grade A-F on every prop (Bet Finder, NBA Props / Trends, every "Defense vs pos" board), and a check of whether the letter knows more than the chance. 2026-10-26

**Suite 172, FAILING: none.** New tests/test_matchup_grade.py (controls
red: the letter upside down; grade_event dropping the letter; the NBA
opponent ranked against itself only). Ships in the same zip as the
first-3-minutes batch (not pushed before this one was built).

Izzy: "DeBrincat anytime goal prop would be graded a B ... I want that to
be a factor on the whole site and anything prop related".

THE LETTER (engines/matchup_grade): tonight's opponent RANKED on what it
gives up on this stat to his kind of player, cut in fifths (32 teams:
7 A / 6 B / 6 C / 6 D / 7 F; 30: 6 each). Nothing new measured — each
sport's own matchup number: NHL / NFL defense vs position cards, MLB
starter (batters) and lineup (pitchers) cards — all now carry "grade" —
and the NBA opponent factor the props model already uses, ranked over
every team for his position group (nba_context.apply_tonight sets
row["grade"] and ctx.grade; combos rank the league-mean-weighted factor).
The letter is about the OVER; the Bet Finder and NBA Props flip it for
an Under (an F defense is an A spot for the under).

IN THE CHANCE? NOT ADDED AGAIN. NBA / NFL / MLB matchups are already in
the projection; the NHL position split is context (validate_dvp did not
beat). Stacking the letter on top would count the matchup twice. Instead
every captured line now carries its letter (book_grade.capture 6th
element; graded rows get it as element 10; old 5-element captures still
grade), and the nightly prints "[verify] MATCHUP GRADE <lg>: A n= site
book hit ..." with scorecard.json "grades"; Site vs DraftKings shows
"Matchup grade check" (per letter: our chance, DK's, went over, over vs
us). NEXT: once each letter has ~300 lines, if A rows go over clearly
more than the site said and F rows less, fit a letter adjustment and
test it walk-forward (adopt only if it beats); if flat, the matchup is
priced in and the letter stays a read.

WHERE IT SHOWS: dm.badge -> "A · 3rd-most" (every Defense vs pos column:
NHL / NFL / MLB boards, NHL Goal Edge, NFL TD Edge), colours by letter
(model_view.GRADE_STYLE); dm.notice -> "Matchup grade A — ..."; Bet
Finder: a Matchup column in the editor and the judged table, with a
caption saying per sport whether the matchup is in the chance; NBA Props
(editor + chances), NBA Trends (per stat).

FILES: app/engines/matchup_grade.py (NEW), app/engines/defense_matchup.py,
app/engines/model_view.py, app/engines/nba_context.py,
app/engines/nba_view.py, app/engines/book_grade.py, book_props_grade.py,
app/views/Bet_Finder.py, app/views/NBA_Props.py, app/views/NBA_Trends.py,
app/views/Site_vs_Book.py, app/views/NHL_Goal_Edge.py,
app/views/NFL_TD_Edge.py, tests/test_matchup_grade.py (NEW), HANDOFF.md,
HANDOFF_ARCHIVE.md

---

## PICK UP HERE — NBA "scores in the first 3 minutes": fitted, tested, priced on the First Basket page; confirmed-five First Basket now BEATS. 2026-10-25 (5)

**Suite 171, FAILING: none.** New tests/test_nba_early.py (controls red:
_walk adding the game before pricing; an unprojected starter at 0.1
points; "beats" on the league rate alone). test_nba_first_confirmed.py:
the page render now includes the first-3-minutes card (control red: the
card's data withheld).

READ 10-25 3 PM nightly (included first_basket_fix): CONFIRMED five
log loss 2.2915 vs projected 2.3411 -> BEATS (z 2.92), real starters
with no projection 1.7%. Confirmed First Basket calls are no longer
capped. The projection-bias line (pushed 5 PM) is not in that run.
"NBA prior play-by-play" re-run: 1,235 / 1,235 games with first-3-minute
scoring and each team's first FG; a starter scored in the first 3
minutes 46.6% of the time.

FIRST 3 MINUTES — engines/nba_early. MEASURED offline on that file
(proxy projections, test from 2026-01-20, 5,920 starter-games): any
point: Brier 0.2419 vs league rate 0.2487 (z 7.7) vs his own shrunk
record 0.2435 (z 2.7) -> beats both, calibrated 30-65%. A made FG: beats
the league rate, thin vs his own record. Team / opponent early pace:
fitted weight 0 -> not in the number. The number: share of his five's
projected points -> 1 - exp(-C (5 share)^G), blended LAM with his own
record shrunk K starts to the league rate. Nightly: ne.fit on the same
rows / windows as First Basket, "[verify] NBA first 3 minutes (pts|fg)",
payload "first3", per game first_basket.early = game_block (starts, pts
hits, fg hits per pool player). Page: card under the players, market
"Any point" / "A made field goal", the five in use (ESPN / yours /
projected), delivered through the curve, judged by bf.judge; THIN cap
unless its verdict beats both baselines. DraftKings' feed has no such
market — price typed.

FILES: app/engines/nba_early.py (NEW), nba_precompute.py,
app/views/NBA_First_Basket.py, tests/test_nba_early.py (NEW),
tests/test_nba_first_confirmed.py, HANDOFF.md, HANDOFF_ARCHIVE.md

---

## PICK UP HERE — First Site-vs-DraftKings read: the NBA model's over chances run ~11 points under the book's; a nightly bias line now measures whether the model under-projects this season. 2026-10-25 (4)

**Suite 170, FAILING: none.** tests/test_nba_context.py +2 checks
(control red: the ratio inverted); tests/test_nba_pbp.py +6 (control red:
9:00 exactly left out).

READ (scorecard 10-25 4 PM; graded nights: NBA 10-24 only, 7 games, 637
main lines). Brier site vs book: every NBA market worse (0.27-0.30 vs
0.24-0.25; pa / pr / pra fail at z -2.5 to -2.9); flagged plays -6% to
-30% ROI. Direction, measured from data/props/graded/nba.json: site mean
P(over) 0.38, book 0.49, actual 0.58. The site leaned UNDER by 5+ points
on 448 of 637 lines and those went over 58%. Not the calibration curve
(raw 0.36, delivered 0.34 on all captured rows incl. ladders), not the
league environment (115.08 vs 115.36). So the projections themselves sat
below DraftKings' lines. One night of correlated games — not a verdict
yet — but too one-sided to wait on blind.
NHL: site ~= book on every market (Brier within 0.01), still grading.

NEW DIAGNOSTIC: nba_context.fit returns "bias" — mean projected vs
actual per stat on unseen player-games, this season vs last season's
test window, all and 20+ projected minutes; nightly prints "[verify] NBA
projection bias ...". NEXT: if this season's ratio sits clearly above 1
(e.g. 1.05+) while last season's is ~1.00, the fix is a this-season
level correction fitted walk-forward and tested (adopt only if it
beats); if both ~1.00, look at minutes (team minutes target 220,
beta 0.5) and at capture time (12:39Z, before lineup news).

FIRST 3 MINUTES (Izzy: "I need players to score in the first 3 minutes
... a market I like to bet on"). Step 1, the data: nba_pbp.parse now
records "early" {pid: [points, made FGs]} for period 1 with 9:00 or
more left (exactly 9:00 counts), "early_team" {team: points}, and
"team_first_fg" {team: first FG record} (team first basket market).
This season's games get it from the nightly's play-by-play; last
season's needs ONE re-run of "NBA prior play-by-play" (nba-pbp-prior.yml,
30-60 min), which now prints "[verify] first 3 minutes: ... a starter
scored in the first 3 minutes X%". DraftKings' feed has no such market
(10-24 type list) — price typed in. NEXT: the model, fitted and tested
on that data (his early points rate per start, shrunk toward his share
of team scoring x the team's early points), then a section on First
Basket.

FILES: app/engines/nba_context.py, nba_precompute.py,
tests/test_nba_context.py, app/engines/nba_pbp.py, nba_pbp_prior.py,
.github/workflows/nba-pbp-prior.yml, tests/test_nba_pbp.py, HANDOFF.md,
HANDOFF_ARCHIVE.md

---

## PICK UP HERE — First Basket: a real starter with no projection is priced, not zeroed (the 10-25 nightly's confirmed test was thin because of it). 2026-10-25 (3)

**Suite 170, FAILING: none.** tests/test_nba_first_confirmed.py +4 checks
(control red: shares pricing an unprojected starter at 0.1 points).

READ 10-25 11 AM nightly: the confirmed-five test came out THIN (2.321
vs 2.341, z 0.63, n 384) where the offline measurement said z ~17.
Cause, reproduced offline: a real starter missing from the props rows
(call-up, no context rows) got share from 0.1 projected points, so when
he scored first the price was ~0 and the log loss exploded. Dropping 8%
of rows offline: fails z -1.71 before, beats z 5.43 after. Fix: he gets
the lowest projection among his four teammates (shares). ESPN-posted
starters outside the pool now come in by name (pregame_names; reprice
names=) instead of knocking the team back to "projected". The fit
reports confirmed.unprojected (share of real starters with no
projection); the verify line prints it. Until the confirmed test beats,
confirmed calls are capped at THIN on the page (as designed).

ENVIRONMENT, first real read (11 AM): NBA 36 games, last-season gate
thin (z 1.8) -> kept 115.36; NHL 179 games kept 3.15; NFL 93 games kept
22.95; MLB kept. No sport switched — none showed a drift worth following.

FILES: app/engines/nba_first.py, app/views/NBA_First_Basket.py,
nba_precompute.py, tests/test_nba_first_confirmed.py, HANDOFF.md,
HANDOFF_ARCHIVE.md

---

## PICK UP HERE — First Basket rebuilt on the CONFIRMED starting five; NBA Trends picks a team first; every game model follows today's scoring when it is measured to help. 2026-10-25 (2)

**Suite 170, FAILING: none.** New: tests/test_nba_first_confirmed.py,
tests/test_nba_trends_picker.py, tests/test_environment.py;
test_nba_first.py and test_bet_finder_why.py updated. Controls red
(exit 1): reprice ignoring `sure`; rho_confirmed counted over the test
window; four starters taken as a lineup; team_players keeping Out rows;
slate_teams listing a team twice; environment applied on the prior test
alone; _ewma_errors scoring a game after adding it; build() ignoring an
applied environment; the NFL no-price note removed.

FIRST BASKET (Izzy: "not set up the right way ... Surprise me").
MEASURED on last season's play-by-play (offline proxy reproduced the
nightly's 2.35 vs 2.40): every first field goal, 1,235 of 1,235, came
from one of the ten STARTERS, but the projected five missed a starter
in ~9% of games, so the model kept ~10% for "someone else". Priced on
the REAL five: 2.27 vs 2.35 log loss per game (paired z 16.9, 592
games), calibrated 4%-19%. Team scoring strength for the first-team call:
nothing (z 0.07) — not built; first team stays THIN.
  engine: price_game(five=, sure=), _walk(confirmed=), fit() returns
  "confirmed" {n, loss, rho, verdict, calibration} and
  params.rho_confirmed (fit side only); pool_row, reprice (the page's
  re-price, identical to the nightly's price when nothing is confirmed),
  pregame_starters (ESPN box / rosters, exactly five).
  nightly: first_basket_game ships "pool", "five", "home", "away"; the
  verify line adds "CONFIRMED five ... vs projected five".
  page: tonight's board on top (best 3 per game, Confirmed / Projected);
  per game, ESPN's posted five auto-confirms (cached 5 min), otherwise
  pick the five and flip "Lineup is out"; confirmed calls go through
  the confirmed curve. Until the next nightly ships "pool" the page says
  lineup confirming is coming and shows the projected prices.
UNKNOWN: whether ESPN's summary marks starters BEFORE tip (pregame shape
never probed). If it never does, the manual switch is the path.

NBA TRENDS: Team first (tonight's teams, game-time order), then
"Player (available tonight)" — ruled-out players dropped and named
under the picker, most projected minutes first, doubt tags shown.

ADAPTIVE ("today's game style", all four sports). Player form is
already recency-weighted where it was measured to help (NBA half-lives,
NHL TOI windows). The gap: every game model's league scoring rate was
LAST season's average until 150 games this season. MEASURED on last
season's finals: the NBA drifted ~10 points in-season (Oct 235, Feb 225,
Apr 236) and a recency-weighted rate beat flat (hl 100, z 2.04); NHL,
MLB, NFL no (z <= 0.9). game_model.environment tests it per sport every
night, twice (half-life vs flat on last season; then on this season's
games, each priced before it, vs the rate in use) and uses it only when
both beat; game_model.build and nfl_game_model.build apply it
(league "from" ends "+environment"). The sims ride the game models.
NEXT: read "[verify] <SPORT> scoring environment" in the nightly.

Bet Finder NFL rows now say DraftKings' free feed posts the line but no
price (probe 10-25: 0 of 744 / 664 items priced in every variant).

FILES: app/engines/nba_first.py, app/views/NBA_First_Basket.py,
nba_precompute.py, app/engines/nba_view.py, app/views/NBA_Trends.py,
app/engines/game_model.py, app/engines/nfl_game_model.py,
app/engines/nhl_model.py, nfl_precompute.py, mlb_model_precompute.py,
app/views/Bet_Finder.py, tests (above), HANDOFF.md, HANDOFF_ARCHIVE.md

---
