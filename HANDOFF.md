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

## PICK UP HERE — the live injury check; a starting-goalie probe. 2026-10-14 (3)

**Suite 139 (+ test_live_injuries), FAILING: none.** Three negative
controls red by exit code (listed in the test). Goal Edge and Long Shots
rendered headless with a simulated same-day scratch: the player left
both boards and the warning line named him.

WHY: the nightly reads injury tags once in the morning; scratches at
morning skate, NFL inactives and late downgrades landed after it. Izzy
wanted the models to know what they did not.

LIVE CHECK (engines/live_injuries.py, NEW): every NHL / NFL view now
loads through load_slate_live("nhl") / load_week_live() (all views but
Results). ESPN's league injury list is re-read at most every 10 min
(2 min after a failure; 6 s timeout per host, no retries — a page never
hangs on ESPN). Out / IR / Suspended NOW leaves props, skaters, goalie
props and goalies (an Out goalie no longer anchors likely_starter) and
NFL players; a new Questionable / Day-to-day is tagged. A deep copy —
the cached nightly slate is never mutated. render_note prints one line
(warning colour when someone was removed) on Goal Edge, Long Shots,
Bet Finder, POTD, NHL Model, TD Edge, NFL Projections, Milestones.
Tags never change a chance (rule 1).

NOT YET KNOWN: whether ESPN's NFL list carries game-day inactives as
"Out" — first Sunday will show it (names should appear in the warning).

GOALIE PROBE (nhl_precompute.goalie_probe, print only): after writing
games.json, prints any goalie/starter/probable key paths in ESPN's game
summary and in the NHL API gamecenter landing for the first unstarted
game. Read the "[verify] NHL goalie probe" lines; if a confirmed starter
exists, the next batch swaps likely_starter for it — and tests it first.

FILES: app/engines/live_injuries.py, tests/test_live_injuries.py (NEW);
nhl_precompute.py; every NHL/NFL view in app/views (imports +
load calls; render_note on the eight above), HANDOFF.md,
HANDOFF_ARCHIVE.md

---

## PICK UP HERE — the 10-14 nightly read; NHL career totals counted this season twice. 2026-10-14 (2)

**Suite 138, FAILING: none.** One new negative control, red by exit code
(test_milestones: is_current_season without the two-digit label).

THE 10-14 NIGHTLY (first run of the injury + milestone batch):
- NFL injuries: 490 roster tags, 800 on ESPN's league list; 23 players
  held out of the prop pool across 14 games. NHL: 19 roster tags, 131
  league-list tags; 4 slate skaters held out. Both sources answer.
- NFL careers: 360 fetched, 0 unreadable; labels "2023".."2026" — read
  right (Rodgers' prior 66,274 pass yds). 71 within reach, 16 reached.
- NHL careers: 400 fetched (the cap), 0 unreadable — but ESPN labels NHL
  seasons "26-27", not "2026-27". is_current_season missed it, so this
  season's row was counted as a past one and then added AGAIN from our
  box scores (Ovechkin prior GP 1,579 = 1,572 + this season's 7).
  FIX: the two-digit label is this season; milestones.FORMAT["nhl"] = 2
  makes PriorCareer start the NHL file over (the NFL file is kept). The
  next two nightlies refetch ~677 skaters at 400 a night; until then
  the NHL watch only lists players already refetched.
- NHL category for a defenseman is "defense", stat "games" (not
  gamesPlayed) — both already matched.

FILES: app/engines/milestones.py, milestone_log.py,
tests/test_milestones.py, HANDOFF.md, HANDOFF_ARCHIVE.md

---

## PICK UP HERE — who is actually playing (NHL + NFL injuries); the Milestone Watch. 2026-10-14

**Suite 138 (+ test_who_plays, test_milestones), FAILING: none.** Six
negative controls red by exit code (three per test, listed in each).
Milestones, Goal Edge and Long Shots rendered headless on an augmented
NHL slate (milestones, a day-to-day skater, a held-out list).

WHY: Izzy asked whether every player and injury report comes in. They
did not. NFL boards dropped only status == "Out" (an IR receiver who had
played kept his TD-board and Long Shots row); the NHL had NO injury
source — only Player of the Day skipped a skater who missed his team's
last game. MLB was already right (active-26 roster + transactions).
Then: "inform me when a player is close to a 300th goal" -> the watch.

WHO IS PLAYING (engines/availability.py, NEW — one reading for all):
- is_out: Out, any Reserve list (IR, LTIR, PUP, NFI), Suspended,
  Inactive. maybe_label: Questionable / Doubtful / Day-to-day / Probable.
  flag(row): the maybe label + "missed last game".
- NHL nightly: the roster's injury tag (_walk_roster now reads it into
  ROSTER_STATUS), else ESPN's league list (espn_feed.fetch_injury_list,
  both hosts; athlete id from the athlete or his link, else by name).
  apply_availability tags every skater; Out players leave the pool
  BEFORE the 18-skater cut; g[side_held_out] lists them. Rows carry
  "status"; Goal Edge has a Heads up column + the held-out caption;
  Long Shots prefixes the warning; POTD skips any tag; Bet Finder drops
  Out and marks the rest.
- NFL nightly: side_players reads roster tag, else the game's injury
  report (summary), else the league list, and drops Out BEFORE the role
  cap (a healthy WR takes the slot); held_out() lists who would have
  played. TD board / prop board / Bet Finder use av.is_out.
- NOT FIXED, stated: NFL inactives post ~90 min before kickoff, after
  the nightly; a skater scratched today shows as healthy until he misses
  a game (then the flag catches it).

MILESTONE WATCH (engines/milestones.py, milestone_log.py, views/
Milestones.py — all NEW; nav for MLB/NHL/NFL, Home card, Results card):
- career now = career BEFORE this season (ESPN common/v3 athletes/{id}/
  stats, per-season rows, this season's row excluded, a traded season's
  combined row read once) + this season from our own box scores. Prior
  careers in data/{nhl,nfl}/career_prior.json, fetched once per player
  per season (cap 400/night), committed by nightly-data.yml.
- Feed-shape guard: 20+ new players with >35% "no earlier season" = the
  shape changed; that night's fetch is NOT saved (PriorCareer.suspect).
- REACH (most needed in one game): 2 G / 2 A / 3 PTS, 400 pass yds,
  175 rush/rec yds, 4 pass TD, 3 TD, 12 rec; MLB 2 HR / 3 H / 4 RBI.
- Chance = bf.chance_at on the row's own pmf at need - 0.5 (delivered).
  Games-played marks show "if he plays".
- MLB: careers read live (stats API people bulk call, hitting career);
  game_type now on weather_engine games; postseason games never count
  (the page says so — every MLB game is postseason right now).
- Marks reached in the last 3 (NHL) / 8 (NFL) days -> payload
  "milestones_happened" -> Milestones page + Results.

FIRST NIGHTLY — read these lines:
  [verify] NHL injuries: N roster tags, N league-list tags ...; N held out
  [verify] NFL injuries / NFL held out of the prop pool
  [verify] NHL|NFL milestones: careers on file / fetched / unreadable;
      the career feed probe line (categories, names, last season labels).
  If the probe's season labels are not "2025-26"-style (NHL) or "2025"
  (NFL), is_current_season needs the real label; if categories are
  empty for everyone, the guard will refuse to save — both are the
  expected failure shapes, not silent ones.

FILES: app/engines/availability.py, app/engines/milestones.py,
milestone_log.py, app/views/Milestones.py, tests/test_who_plays.py,
tests/test_milestones.py (NEW); nhl_precompute.py, nfl_precompute.py,
app/engines/espn_feed.py, app/engines/edge_boards.py,
app/engines/nhl_model.py, app/engines/model_view.py,
app/engines/long_shots.py, app/engines/weather_engine.py,
app/views/NHL_Goal_Edge.py, app/views/Long_Shots.py,
app/views/Bet_Finder.py, app/views/NFL_TD_Edge.py, app/views/Results.py,
app/views/Home.py, app/app.py, .github/workflows/nightly-data.yml,
HANDOFF.md, HANDOFF_ARCHIVE.md

---

## PICK UP HERE — Long Shots page; the 10-11 NFL nightly read. 2026-10-11 (3)

**Suite 136 (+ test_long_shots), FAILING: none.** Three negative controls red by
exit code (listed in the test). Long Shots rendered headless for NHL
(60 rows, signals filled), NFL (TD rows); MLB is network (lineups) and is
wrapped per game, so a feed failure costs that game only.

THE 10-11 NIGHTLY (two-season NFL batch, confirmed):
- NFL prior box scores 272/272 parsed, 605 players, 95 with a recorded
  line; data/nfl/prior_logs.json committed.
- Prop test rows: 21,599 from 2025 + 5,199 from 2026 (was ~2,000 total).
- Defense strength: rush fitted 0.25 -> thin (z 0.06, n 1,023); rec 0.5
  -> thin (z 0.58, n 5,716); pass fitted 0.0 (n 231 to fit) -> all
  CONTEXT ONLY. The defense does not add on top of the model in NFL
  either; the guard (CHECK) stays the protection.
- All 12 NFL prop stats BEAT the player's own rate on 618-4,961 graded
  player-games each (passing yards n 618, was 92).

LONG SHOTS (engines/long_shots.py, views/Long_Shots.py; MLB nav, NHL +
NFL subpages, Home card): every player whose DELIVERED chance is in
+300..+2000 (1/21..1/4), only on TESTED markets with the raw call inside
its curve's graded range and >= STRONG_MIN_N calls in the band.
NHL: every nhl_model market; MLB: every mlb_props market (lineup or last
lineup); NFL: anytime TD (td curve). "Why it's live" signals for NHL:
ice time up (>= 5%), PP1, team goal env >= +5%, opposing goalie below the
league save rate. Price-range filter opens on +600..+2000. Typed prices
go through bet_finder.judge with the row's support (the one guard); BETs
land on the Bet Finder's session card.

FILES: app/engines/long_shots.py, app/views/Long_Shots.py,
tests/test_long_shots.py (NEW), app/app.py, app/views/Home.py,
HANDOFF.md, HANDOFF_ARCHIVE.md

---

## PICK UP HERE — NFL props tested on last season + this one; defense strength fitted. 2026-10-11 (2)

**Suite 135 (+ test_nfl_two_seasons), FAILING: none.** Three negative controls red
by exit code (one first came back GREEN: the null world never fitted a
strength above 0, so "adopt without the test" could not show; the fixture
now has fit weeks that suggest a strength and test weeks that do not).
NFL pages + Bet Finder rendered headless. This zip ALSO carries the
10-11 guard batch (bet_guard), which had not been pushed yet.

WHY: Izzy — "make NFL behave like MLB and NHL". NHL/MLB props are tested
on a full past season; the NFL test ran on this season's weeks only (92
QB games for passing yards), and its defense multipliers were all-or-
nothing (all three failed).

DATA: nfl_precompute.load_or_fetch_prior_logs — every 2025 box score
through THIS season's parser (parse_summary_final), finals in this
season's shape (week via PRIOR_WEEK1_TUESDAY 2025-09-02, abbrs from the
summary, recorded line from pickcenter, team boxes), fetched ONCE by the
nightly (~272 summaries) and committed as data/nfl/prior_logs.json
(nightly-data.yml commit step). Refuses to save under 90% parsed.

TEST (nfl_prop_check.run, prior=): walk_forward on 2025 AND 2026, rows now
8 fields (+ {strength: p} on STRENGTH_GRID 0/.25/.5/.75/1 for the
family's stats). split_rows: fit on 2025's first half of weeks; test on
2025's second half + all of 2026 (never a week the fit saw). fit_strength
per family (rush / rec / pass): lowest log loss on the fit block, then
paired vs strength 0 on the test block; in the number only on "beats".
Then the props are graded (verdicts + calibration) on BOTH seasons with
the adopted strengths — the curves the delivered chances and the guard
read are now built on thousands of rows, not hundreds.

PROJECTION: nfl_projection.project_player applies ratio ** strength
(league["matchup_strength"]; absent = 1.0, old behaviour). Why lines say
"in the number at 50% strength" or "context only".

READ IN THE NEXT NIGHTLY: "[verify] NFL prior box scores", "NFL prop
test rows {prior_rows, current_rows}", "NFL defense strength (fam)".

FILES (this batch): nfl_precompute.py, nfl_prop_check.py,
app/engines/nfl_projection.py, app/engines/model_view.py,
.github/workflows/nightly-data.yml, tests/test_nfl_two_seasons.py (NEW),
HANDOFF.md, HANDOFF_ARCHIVE.md — plus the guard batch's files.

---

## PICK UP HERE — the guard on every bet call: no false STRONG. 2026-10-11

**Suite 134 (+ test_bet_guard), FAILING: none.** Three negative controls red by
exit code (listed in the test). Every changed page rendered headless; the
Bet Finder replays Brissett UNDER 266.5 (-113/-113) as CHECK with the reason.

WHY: 10-11, DET @ ARI. Model ~200 pass yds for Brissett, book 266.5. The
Finder would have called UNDER 266.5 STRONG (78% vs 53% break-even). Izzy
leans on STRONG; a false one is the most expensive bug on the site.

THE GUARD (model_view.guarded_tier; every PROP call — _any_line_tool for
all sports, render_prop_value_tool, Bet Finder, Top Plays, NHL Goal Edge,
NHL POTD, NFL TD Edge, NFL Projections; game lines are market-anchored):
1. BOOK DISAGREES -> CHECK when our chance - the book's >= GAP_CHECK 0.10.
   MEASURED: 3,050 NHL + NFL 2025-26 game lines with model walk-forward and
   market both recorded; gaps 0-10 pts no difference (z 0.29/-0.73/-1.08),
   10-15 pts market right (z -2.52, n 314), 15+ market right (z -2.23,
   n 104). Transfer to props is the cautious side; re-measure on props
   once prop prices are recorded. Book's chance = de-vigged with the other
   side's price (Bet Finder "Other side" column, checker's optional box),
   else the price's break-even.
2. No graded curve -> at most THIN.
3. STRONG needs the raw call inside its curve's graded range with >= 30
   calls in the nearest band (STRONG_MIN_N); else VALUE. No curve attached
   -> STRONG capped at VALUE.
curve_for() now holds the curve choice delivered_over uses (unchanged).
TIER_STYLE gains "check" (amber). Stakes are shown only on BET tiers.

ALSO MEASURED (no code change, 2025 data in the repo): game script —
QB attempts vs the team's spread, 153 QB games with lines: -0.05 att per
point (se 0.09), yards +0.15 (se 0.79): NOT measurable. Defense pass yds
allowed (walk-forward, 369 QB games) does not carry into QB yards the way
a multiplier assumes (slope -0.54, se 0.13 — confounded, not usable). So
neither was put in the projection; the guard is the protection. NEXT:
record prop prices (needs a durable store the app can write) so the
model-vs-book test can run on props and GAP_CHECK be re-fitted for them.

FILES: app/engines/model_view.py, app/engines/bet_finder.py,
app/views/{Bet_Finder,Top_Plays,NHL_Goal_Edge,NHL_Player_Of_The_Day,
NFL_TD_Edge,NFL_Projections}.py, tests/test_bet_guard.py (NEW),
tests/test_bet_finder.py, HANDOFF.md, HANDOFF_ARCHIVE.md

---

## PICK UP HERE — Bet Finder: type your book's prices, get BET or SKIP. 2026-10-09 (3)

**Suite 133 (+ test_bet_finder), FAILING: none.** Three negative controls red by
exit code (listed in the test). Bet Finder rendered headless on the NHL
archive: prices typed -> STRONG / VALUE / SKIP rows, stakes, the card;
NFL source renders; MLB source is network (lineups) and is wrapped so a
failed feed costs MLB, never the page.

FIRST, THE PP RESULT (10-09): prior_pp.json committed (47,229 of 47,229
skater-games). Run locally on it: PP-weighted ice time does NOT beat plain
ice time — sog thin z 1.16 (w 2.0), pts fails z -1.81 (w 1.5). Context
only; nothing changed. (The nightly that printed "0 skaters" had been
queued before the PP commit and checked out the older SHA.)

ALSO MEASURED 10-09 (no code): our g1 model vs "hot streak" hit rates on
2025-26 (16,955 games): beats last-5 (z 24.3), last-8 (z 18.2), last-20
(z 11.6). Players at 50%+ over their last 8 scored 29.4% next game; the
model said 30.3%.

WHY: Izzy, reading the boards: colour means LIKELY, and he could not tell
a good bet from a bad one. The rule is "book pays more than Worth it at";
this page applies it to a whole list at once.

ENGINE app/engines/bet_finder.py (pure, + model_view for delivered_over
/ edge_tier): chance_at (the DELIVERED chance, same as every board),
judge (BET iff edge > 0 on the printed grid, tiers THIN/VALUE/STRONG,
stake via value.assess), price_list, results, game_line_items (FINAL
chance at the posted line; no market -> left out), card_rows.

PAGE app/views/Bet_Finder.py: sport (defaults to the switcher's sport),
game, who (skaters/goalies, batters/starters, players), stat, line,
side; a 3-column data_editor (Player / Line / Your price — Line editable
for NFL, where lines differ by player); results table; game lines with
price inputs; "Tonight's card" in session state across sports, scaled
to the per-slate cap. In the MLB nav, NHL and NFL subpages, and a Home
explore card (test_home requires a route).

FILES: app/engines/bet_finder.py, app/views/Bet_Finder.py,
tests/test_bet_finder.py (NEW), app/app.py, app/views/Home.py,
HANDOFF.md, HANDOFF_ARCHIVE.md

---

## PICK UP HERE — PP-weighted ice time: fitted, tested against plain ice time. 2026-10-09 (2)

**Suite 132 (+ test_nhl_pp_factor), FAILING: none.** Three negative controls red by
exit code (listed in the test). NHL pages rendered headless on the 10-06
archive: no exceptions.

FIRST, THE PROBE ANSWERED (10-09 nightly): ESPN's NHL box DOES carry
powerPlayTimeOnIce — 2,340 of 2,340 skater lines. Also evenStrength- and
shortHandedTimeOnIce (not used yet). First NHL Player of the Day: Mark
Scheifele 68.7%.

LAST SEASON'S PP MINUTES: nhl_prior_season.py --pp-only re-reads the
2025-26 box scores and writes ONLY data/nhl/prior_pp.json ({pid: {date:
minutes}}) — prior_season.json and everything fitted on it untouched; its
game rows stay six fields (every reader unpacks six). Manual workflow
"NHL prior PP minutes" (nhl-prior-pp.yml), run ONCE. A full prior-season
rebuild now writes both files. nhl_precompute.load_prior_pp lays the file
over the prior skaters as "pp"; pool_skaters carries pp from both seasons.

THE FACTOR (nhl_model.fit_pp, called inside fit_toi per family): weighted
minutes = TOI + (w - 1) x PP minutes; w = 1 IS today's ice-time ratio, so
the PP version nests it. w from PP_WEIGHTS and its strength fitted on the
train window, tested on the props window AGAINST THE ADOPTED PLAIN FACTOR;
in the chance only on "beats" (toi[fam]["pp"]["adopted"]). Needs
PP_MIN_COVERAGE 50% of fit rows with PP minutes, else a note.
MEASURED BEFORE SHIPPING: on the real 2025-26 file with RANDOM PP minutes
attached, both families FAIL (sog z -2.16, pts z -0.78) and the plain
alphas are unchanged (0.478 / 0.774) — the test does not invent an edge.
On a simulated season where PP minutes drive scoring it is adopted
(z >= 2). Cost: fit_toi went to ~3.5 min at full size.

PAGES: nhl_model.pp_note(toi) — one sentence, IN the chance / tested and
not / untested — on Goal Edge, NHL Model, Player of the Day; why lines
say "PP minutes weighted into his ice time" only when used.

AFTER THE WORKFLOW RUNS: read "[verify] NHL PP-weighted minutes (sog|pts)"
in the next nightly. Adopted -> the props validation, Top Plays, Goal
Edge, POTD all move with it automatically.

FILES: nhl_prior_season.py, nhl_precompute.py, app/engines/nhl_model.py,
app/views/{NHL_Goal_Edge,NHL_Model,NHL_Player_Of_The_Day}.py,
.github/workflows/nhl-prior-pp.yml (NEW), .github/workflows/nhl-prior-season.yml,
tests/test_nhl_pp_factor.py (NEW), HANDOFF.md, HANDOFF_ARCHIVE.md

---

## PICK UP HERE — NHL: power-play minutes, 2+ goals, Player of the Day, the multi-goal check. 2026-10-09

**Suite 131 (+ test_nhl_pp_potd), FAILING: none.** Three negative controls red
by exit code (listed in the test). Goal Edge, NHL Player of the Day, NHL
Model, Top Plays and Results rendered headless against the 10-06 archive
both as-is (old games.json: no exceptions) and with the new fields added.

WHY: Izzy asked whether PP minutes are in the NHL model (they were not),
why nobody could see the night's multi-goal scorers coming, and for MLB's
Player of the Day structure in hockey.

POWER PLAY — CONTEXT ONLY. nhl_precompute.SKATER gains "pptoi" (ESPN's
PP TOI column under every spelling seen; ABSENT when the feed lacks it,
rule 6). The nightly prints the skater box columns it saw and how many
lines carried PP minutes: THAT IS THE PROBE — read it on the first run.
If ESPN has no PP column, the NHL's own API is the fallback (not built).
nhl_model.pp_units: PP1 = team's top 5 by last-5 PP minutes, PP2 next 5,
under 1.0 min none; {} when nobody has PP minutes (unknown, not zero).
Not in the number: prior_season.json has no PP minutes, so nothing to
test on yet. NEXT: once this season has ~60 days of PP lines, test a PP
factor walk-forward the way fit_toi was (adopt only on "beats").

2+ GOALS: ("g2", "Goal O1.5", "g", 2) added to MARKETS; Goals board
offers 1.5. Last season walk-forward: BEATS his own rate (z 4.86,
n 17,343). Calibration: calls of 10-19% (n 92) delivered 6.5% vs 11.5%
called — the delivered chance pulls the top of the list down to that.
Tried equal-count calibration bands for crowded markets (2+ goals has 98%
of calls under 10%); cross-fitted vs the 10-point bands: g2 thin (z 1.8),
pt2 thin, sog4 WORSE (z -2.4) -> not adopted, 10-point bands kept.

PLAYER OF THE DAY (edge_boards.nhl_player_of_the_day, views/
NHL_Player_Of_The_Day.py, NHL nav): 1+ point, gates = pt1 verdict beats,
20+ games both seasons, played his team's last game (nhl_model rows now
carry last_game / team_last_game). Ranked by DELIVERED chance; no matchup
nudges on top (already inside the chance — MLB nudges because its score
has none). Logged + graded nightly to data/top_plays/nhl_potd.json.

MULTI-GOAL WATCH + CHECK: top 10 by delivered 2+ goal chance logged to
nhl_multigoal.json (graded like Top Plays). nhl_multigoal_ranks.json keeps
each night's top-100 pre-game ranking; once every game of the night is
final, the two-goal scorers are recorded with their rank. Goal Edge shows
"X of Y were in our top 25; a random 25 would catch Z" — the yardstick.
Both new records are on the Results scorecard. nightly-data.yml commits
all three files.

FILES: nhl_precompute.py, app/engines/{nhl_model,edge_boards,scorecard}.py,
app/views/{NHL_Goal_Edge,NHL_Model,Results}.py, app/app.py,
app/views/NHL_Player_Of_The_Day.py + tests/test_nhl_pp_potd.py (NEW),
.github/workflows/nightly-data.yml, HANDOFF.md, HANDOFF_ARCHIVE.md

---

## PICK UP HERE — the Model Scorecard, and the NFL totals were already fixed. 2026-10-08

**Suite 130 (+ test_scorecard), FAILING: none.** Three negative controls red by
exit code (listed in tests/test_scorecard.py). Results page rendered
headless (streamlit AppTest) against the committed records: no exceptions.

WHY: Izzy asked that every model give its best possible performance. The
honest version of that is a record per model judged against the bar it
has to beat, checked every night, with a recent window that catches a
model that WAS good and stopped. That did not exist in one place.

THE NFL TOTALS 4-11 (looked into first, nothing changed): every graded
game bet so far (44 NFL, 23 NHL, 3 MLB) is formula "model-only", logged
10-03/10-04, i.e. BEFORE engines/market_blend went live. Rebuilt the blend
on 2025 (95 games with lines): total -> fails vs market (z -1.33),
moneyline thin, spread thin, w_used 0 everywhere. So today the final
chance IS the market's and no game bet clears the vig; the totals that
went 4-11 were the ones the 10-04 fix was built to stop. No over/under
lean either (8 over / 7 under). Rule 10: not retuned.

ENGINE: app/engines/scorecard.py (NEW, pure). Three kinds of record,
three targets (rule 9):
- pick boards (calibration.summary): vs the measured league rate.
- Top Plays (data/top_plays): vs the SUM of the delivered chances they
  printed (p_cal). Landing it = ON TARGET, which is the job.
- game bets (data/model_picks): market-anchored vs their logged chance;
  model-only = RETIRED, shown, never judged.
- boards graded vs their own printed number (K board, WNBA) = NO TARGET,
  never coloured. A 43% K board is not "bad": a Poisson count clears a
  non-integer mean less than half the time.
Verdict: MIN_N 30, |z| >= 2. SLIPPING also fires on the last 30 days
(>= 30 picks, z <= -2) — window anchored to the record's newest date.

PAGE: Results now opens with the scorecard (cards, not a table, so they
wrap on iPad; problems first). First real read: Daily 13, HR Edge, POTD
BEATING; NHL + MLB Top Plays ON TARGET; game bets NO PICKS YET.

NEXT (agreed order): NHL batch — PP-time probe (ESPN box score fields;
the free NHL API has PP TOI if ESPN does not), 2+ goals column + its
walk-forward verdict, NHL Player of the Day built like MLB's, and the
"where did tonight's multi-goal scorers rank" log. Then NFL Player of
the Week. The scorecard is how those get judged.

FILES: app/engines/scorecard.py, tests/test_scorecard.py (NEW),
app/views/Results.py, HANDOFF.md, HANDOFF_ARCHIVE.md

---

## PICK UP HERE — Goal Edge + Goalies to Target (NHL), TD Edge + Defenses to Target (NFL). 2026-10-06 (3)

**Suite 131 (+ test_edge_boards), FAILING: none.** Four negative controls
red by exit code (one first came back GREEN — the goalie fixture's game
goals agreed with the save-rate ranking, so it could not tell the two
apart; the fixture now makes them disagree). All four pages opened in a
real browser against the 10-06 nightly archive: no exceptions.

WHY: Izzy wanted hockey and football versions of HR Edge and Pitchers to
Target: one page that ranks the scoring chance, one that names who to
attack.

ENGINE: app/engines/edge_boards.py (NEW, pure). NOTHING NEW IS
ESTIMATED; it gathers what the nightly already fits and tests.
- nhl_goal_rows: every skater's Goal O0.5 from nhl_model through the g1
  calibration curve (the delivered chance, same as Top Plays), with exp
  G / SOG, ice time, goal environment, the goalie he SHOOTS AT and the
  DvP cards. No 0-100 composite: the ranked number has a graded record.
- likely_starter: most recent starts from the crease string; a TIE
  returns None (a split crease shows both names and their averaged save
  rate, never a guess).
- nhl_goalie_rows: ranked by HIS expected goals against = exp shots
  against x (1 - his shrunk save rate); the game model's team goals ride
  beside it as the cross-check. Saves are tested at TEAM level only, and
  the page says so.
- nfl_td_rows: projection_rows("Anytime TD") through the nightly NFL
  prop test's td calibration (nfl_prop_check), DvP td card, opponent TD
  and red-zone ranks.
- nfl_defense_rows: per position, the stat the defense allows MOST (of
  2-3), its rank and % vs league; sorted by SOFT count, then summed size.
  The page warns that max-of-three makes any defense look a bit softer.

PAGES (NEW): views/NHL_Goal_Edge.py, NHL_Goalies_To_Target.py,
NFL_TD_Edge.py, NFL_Defenses_To_Target.py: money columns first, chance
colours, price checker with the verdict box + matchup notices. Added to
SPORT_SUBPAGES in app.py (NHL: Goal Edge, Goalies to Target; NFL: TD
Edge, Defenses to Target).

FILES: app/engines/edge_boards.py, the four views, tests/test_edge_boards.py
(all NEW), app/app.py, HANDOFF.md, HANDOFF_ARCHIVE.md

---

## PICK UP HERE — money columns first on every model table (iPad width). 2026-10-06 (2)

**Suite 130 (+ test_money_columns_first), FAILING: none.** Three negative
controls red by exit code. NHL Model and Top Plays checked in a browser
at 1180px and 800px: every decision column visible without a swipe.

WHY: on the iPad the chance column and Defense vs pos sat off the right
edge, and the table would not scroll sideways for Izzy.

WHAT: model_view.lead_columns / prop_board_order (NEW) — one rule for
every model table: name, Pos, the line chances, Avg/Proj, Defense vs
pos, THEN GP / minutes / samples / team / status. Applied to
render_prop_board (MLB batters + starters, NHL skaters + goalies), the
NFL board (Low/Mid/High first), the game value table (Bet, Final, Price,
Fair, Edge, Tier, Stake, Trust, then Model/Market/Break-even/EV), Best
value tonight, Top Plays tonight (Player, Bet, Chance, Worth it at,
Matchup, Status, then Sport/Game) and Top Plays game bets. Reorder only:
nothing dropped, painters address columns by name, the value editor's
edits are keyed by row. Research boards untouched (own column groups).

NAMING NEAR-MISS: tests/test_column_order.py ALREADY EXISTS (Game Card
lineup order from the HR Score weights). The new test was first written
over it; restored from git — the new one is test_money_columns_first.py.

FILES: app/engines/model_view.py, app/views/Top_Plays.py,
tests/test_money_columns_first.py (NEW), HANDOFF.md

---

## PICK UP HERE — defense vs position on every sport, ice time in the NHL number, the NFL props graded, every chance DELIVERED, colour. 2026-10-06

**Suite 128 (+ test_defense_matchup), FAILING: none.** Nine negative
controls red by exit code (listed in the new test's docstring + the
calibration-ends control in test_top_plays). NHL Model, NFL Model, MLB
Model and Top Plays opened in a real browser from the 10-06 nightly
archive with the new NHL model block: no exceptions.

### WHY

Izzy: the boards "work" but give him the same obvious bet every night;
he wants to know WHY a play is suggested and whether the defense is
actually allowing it (this season AND last), a notice when a player
faces a soft/tough defense and the defense's rank vs his position, on
EVERY sport. No money for an odds feed — he checks his own book, so the
"your price" checker must be as accurate as it can be (no "STRONG" on a
-200 that is really a -350). And colour: plain black tables are hard to
read.

### MEASURED BEFORE BUILT (rule 1) — last season's NHL, walk-forward

| change | result on unseen games | in the number? |
|---|---|---|
| ice time (recent TOI / TOI the rate is built on)^alpha, shots | z 7.7, alpha 0.48, window 5 | YES |
| same, goals/assists/points | z 6.8, alpha 0.74, window 5 | YES |
| defense-vs-POSITION share on top of team shots/goals allowed | sog thin z 0.6, pts fails | NO — context |
| calibration past the curve's ends: carry the gap vs hold flat | better on 6/8 markets (z 2.1-8.4) | YES (all sports) |

The DvP result is the honest headline: a team's TOTAL shots allowed is
a stable trait (split-half 0.92) and the shots model already has it;
WHICH position gets them adds nothing measurable. It is still shown
(rank, tier, notice) because Izzy asked whether the defense allows it —
and the page says it is context.

### ENGINES

- **engines/defense_matchup.py (NEW, pure, all sports).** Rows (season,
  defense, game, group, stats) -> per defense x group x stat: this
  season / last / blended per game, ranks (1 = allows the MOST), quartile
  tier (soft/neutral/tough — a presentation cut, said so), split-half
  reliability ("is this matchup real?"), cards, one-sentence notices,
  badges ("SOFT · 3rd-most", "TOUGH · 2nd-fewest"). Season weight: the
  direct last->this fit is unidentified on two games a team (measured
  10-06: C 0.0, W 1.0 the same night), so a REFERENCE weight fitted on
  last season's first half -> second half is used until this season's
  likelihood prefers the direct fit by an LR test (1.92, scaled by the
  measured quasi-Poisson dispersion — yards are not counts). No
  games-played cutoff anywhere. MLB: mlb_starter_table / cards (the
  "defense" is the starter, per PA, at the props' fitted pitcher weight)
  and mlb_lineup_card (tonight's nine vs this season's team lineups).
- **nhl_model.** fit_toi (fit on the 60 days before the props window,
  tested on it; alpha 0 unless "beats"); validate_props now uses the
  adopted ice time so badges/calibration test the page's model;
  validate_dvp; DvP table; rows carry rate, ice, dvp cards, why.
  BUG FIXED: pool_skaters took EXHIBITION lines into every rate (the
  live dict holds preseason games parsed as a parser check) — now
  regular_ids only. ~2 min added to the nightly (fit_toi).
- **nfl_prop_check.py (NEW).** DvP from box scores with ROSTER
  positions (all 32 rosters read; box scores carry none; unknown -> ALL
  only). Last season's player-game lines parsed once ->
  data/nfl/prior_dvp.json (committed by the NFL step; written beside
  PRIOR_PLAYERS_PATH so tests stay sandboxed). THE NFL PROPS ARE NO
  LONGER UNTESTED: week-by-week walk-forward, line = floor(his average to
  date)+0.5, vs his own hit rate -> verdict + calibration per stat. Each
  defense multiplier family (rush/rec/pass) tested on vs off; only
  "beats" stays in (league["matchup_in_number"], read by
  nfl_projection.project_player; absent = all on, old files unchanged).
- **mlb_prop_precompute.** starter_allowed + team_batting in
  prop_model.json (batting team of the away side read from its batters'
  home games — never guessed). home_team rides into plate_appearances.
- **nfl_prop_odds** now owns STATS + stat_pmf (moved from model_view so
  the nightly prices exactly what the page prices); a zero/unmeasured
  yards cv returns no distribution instead of crashing.
- **top_plays_board.calibrate**: gap carried past the ends (the old flat
  top made Matthews 89% and Eichel 84.5% the same 84.4%).

### PAGES

- **Every prop board (model_view.render_prop_board, NFL board, Top
  Plays):** cells coloured by an ABSOLUTE chance band (80+ cyan, 65-79
  gold, 50-64 teal, 35-49 violet, under 35 faint — legend printed under
  each board, colour only), "Defense vs pos" column coloured by tier.
  Cells show the DELIVERED chance where a curve exists.
- **The checker** judges your price on the delivered chance
  (delivered_over: exact line's curve, else nearest tested line, else
  NFL "@stat" curve, else raw — and says which), answers in a coloured
  panel (STRONG / VALUE / THIN / NO VALUE), and under it prints the
  matchup notice and the WHY line for that player.
- NHL table adds TOI recent / TOI norm (window from the fit, rule 9).
- Top Plays logs `why`, `matchup`, `matchup_tier` with each play;
  Status green/red; the record's Delivered green at/above promised.

### FIRST RUNS — read these lines

    [verify] NHL ice time (sog): window 5 fitted alpha ~0.48 -> IN THE NUMBER (beats, z~7.7)
    [verify] NHL defense-vs-position (sog): thin ... -> context only
    [verify] NHL DvP table: 32 defenses; SOG to C league ~9.6 weight .. reliability ~0.63
    [verify] NFL prior defense lines: 272/272 box scores parsed      (first night only)
    [verify] NFL defense-vs-position: 32 defenses, N rostered positions, N 2025 lines
    [verify] NFL defense multiplier (rush|rec|pass): .. -> IN THE NUMBER | context only
    [verify] NFL prop rush_yds n=.. model .. vs his-own-rate .. -> beats|thin|fails
    [verify] matchup tables: N starters ranked; 30 team batting lines   (MLB)

### OPEN

- NFL walk-forward uses this season's weeks only (2025 has no per-week
  logs on disk); its sample grows weekly. Do not retune on a bad week
  (rule 10).
- MLB position split (platoon by batter hand) is still not in the
  number; the starter card is vs all batters.

### FILES, 2026-10-06

    app/engines/defense_matchup.py, nfl_prop_check.py, tests/test_defense_matchup.py   NEW
    app/engines/{nhl_model,model_view,nfl_projection,nfl_prop_odds,top_plays_board}.py
    app/views/{NHL_Model,NFL_Model,MLB_Model,GameCard,Top_Plays}.py
    nhl_precompute.py, nfl_precompute.py, mlb_prop_precompute.py, top_plays_log.py
    .github/workflows/nightly-data.yml (commit data/nfl/prior_dvp.json)
    tests/{test_top_plays,test_nfl_pipeline}.py

---

## PICK UP HERE — last season in every model, NFL props on the Model page, Top Plays with a record. 2026-10-04 (2)

**Suite 127, FAILING: none.** Twelve negative controls red by exit code;
the whole suite green on Python 3.11 too. NFL Model and Top Plays looked
at in a real browser from fixtures.

### WHY

Izzy: four weeks of NFL and one season of MLB is too little to judge a
player on — use last season; the NFL Model page had no player props; and
he wants a page he can hand his friends where everything shown is as
reliable as it can honestly be. Profit first, most likely outcomes up
front.

### LAST SEASON, AT A FITTED WEIGHT (model_math.fit_prior_weight)

    rate = (this season + w x last season + league x s) / (n + w x n_ly + s)

w is fitted by maximum likelihood of THIS season's totals predicted from
LAST season's alone, on everyone in both seasons. A last season shuffled
across players earns ~0 (asserted, live control in the test); a skill
that persists earns most of 1.

- **MLB game model**: 2025 finals via statsapi -> game_model.build's
  walk-forward-fitted team carryover (it existed; MLB never passed a
  prior). Starters: 2025 runs/outs at weights fitted on starters in both
  (mlb_model_precompute.fit_starter_prior_weight); a starter with only a
  2025 line now gets a layer. Validation, blend and page all use it.
- **MLB props**: 2025 per-player outcome counts from statsapi SEASON
  stats (one call each for hitting and pitching — not a second Statcast
  pull) + each 2025 starter's batters-faced. Weights per batter /
  pitcher / depth fitted in mlb_prop_precompute.fit_prior_weights; the
  walk-forward folds them in so the verdicts test the model the page uses.
  A line missing doubles/triples is left out, not split by a guess;
  traded players keep their largest line.
- **NFL player props**: every 2025 box score (272 summaries, the SAME
  parser) -> data/nfl/prior_players.json, raw totals per player
  (player_summaries now emits `tot`). Seven families with their own
  weights (shares, catch rate, ypc, ypt, TD per touch, QB rates, ypa —
  yardage via a quasi-Poisson likelihood). merge_prior recomputes every
  rate from weighted SUMS and flags a player who changed teams.
- **NHL** already did this (skaters pooled, team carryover) — unchanged.

Files written ONCE, the first night missing, committed by the nightly:
data/mlb/prior_season.json (Commit MLB game model), data/nfl/
prior_players.json (Commit NFL projection log). Under a near-complete
season they are refused, never saved partial.

### NFL PLAYER PROPS ON THE MODEL PAGE (model_view.render_nfl_props)

Under each game: pick a stat (passing yds/att/completions/TDs/INTs,
rushing yds, carries, receiving yds, receptions, targets, rush+rec,
TDs) -> every player's projection and a Low/Mid/High ladder of over
chances, then any line at your price. Yards are the measured-cv normal
discretised to whole yards (64.5 = P(65+), same as p_over). Out players
are left off; Questionable/Doubtful printed. UNTESTED badge — NFL prop
chances are not graded yet, so they never reach Top Plays.

### TOP PLAYS (views/Top_Plays.py, engines/top_plays_board.py, top_plays_log.py)

- **Props**: only lines whose market BEAT the player's own rate out of
  sample; probability CALIBRATED through that market's own walk-forward
  curve (PAV-monotone, linear between bins, flat past the ends) — the
  page shows what calls like it DELIVERED, not what the model claimed.
  One play per player; TB O0.5 never beside Hits O0.5. SHOW_N = 10 is a
  presentation choice. "Worth it at X or better" = fair price at the
  calibrated chance.
- **Logged before, graded after**: data/top_plays/mlb.json (slate-picks:
  grade then log, statsapi boxscore; batter lines from batting, starter
  plays from the STARTER's pitching line only, walks incl. HBP as the
  model counts them) and nhl.json (nhl_precompute, graded from the finals
  it already parsed). DNP -> void. The page leads with PROMISED vs
  DELIVERED overall and by band.
- **Game bets**: value at the posted price on the Final chance, ONLY in
  markets whose blend verdict is "beats" — empty until Market history has
  run and a market proves itself, and the page says why.

### ALSO

MLB walks markets relabelled "Walks+HBP" (rule 9: the model's walk
outcome includes HBP; books' walk props do not). edge_tier: +0.0 on the
printed grid is "none" — a price box at the fair price read THIN.

### FIRST RUNS

Nightly (writes both prior files) -> the next slate-picks run logs MLB
plays; the nightly logs NHL plays. Read:

    [verify] MLB 2025 prior season: ~2430 finals; N starters, N batters / N pitchers
    [verify] team carryover from 2025: ..   [verify] starter last-season weight: {..}
    [verify] last-season weights {'batter': .., 'pitcher': .., 'bf': ..}
    [verify] NFL prior players: 272/272 box scores ..; NFL last-season weights {..}
    [verify] top plays mlb: N candidate props, N selected, N new logged
    [verify] NHL top plays: graded N, voided N; N selected, N new logged

### FILES, 2026-10-04 (2)

    app/engines/top_plays_board.py, app/views/Top_Plays.py, top_plays_log.py   NEW
    tests/test_prior_season.py, tests/test_top_plays.py                         NEW
    app/engines/{model_math,mlb_game_model,mlb_props,model_view}.py
    app/views/{NFL_Model}.py, app/app.py (Top Plays in MLB/NFL/NHL navs)
    mlb_model_precompute.py, mlb_prop_precompute.py, nfl_precompute.py, nhl_precompute.py
    .github/workflows/{nightly-data,slate-picks}.yml
    tests/{test_game_model,test_mlb_props,test_nfl_pipeline,test_nhl_model,test_nhl_pipeline}.py
    HANDOFF.md, HANDOFF_ARCHIVE.md (09-27 projections entry rotated out)

---
