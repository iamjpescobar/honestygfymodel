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
