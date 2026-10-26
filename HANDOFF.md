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

## PICK UP HERE — NFL props carry NO prices in the saved record; the probe now looks for where they are. 2026-10-25

**Suite 167, FAILING: none.** tests/test_prop_lines_probe.py +1 check
(control red: the probe no longer counting priced items).

MEASURED 10-25 5 AM (data/props/nfl/2026-10-25.json, 12 games, "ours"
captured on all 12): 0 of 16,883 NFL items carry a price — totals,
"N+" ladders, anytime TD, 1Q / 1H, all lines only. (NHL / NBA / MLB
items carry odds.american.) So the NFL Bet Finder opens on DraftKings'
LINE with the price to type, and NFL cannot be graded against the book
until prices are found. The ladder never sits at the total's own line
(0 of 400 NFL players), so it cannot stand in for the main price.

prop_lines_probe.py now prints, per provider, how many items carry an
odds block, ONE FULL ITEM of each of the first 6 types, and four query
variants (none, region=us, region=nj, page 2) with their priced counts.
NEXT: run "Prop lines probe"; if a variant or another field carries NFL
prices, parse it in book_props.parse; if none, say so on the NFL rows.

FILES: prop_lines_probe.py, tests/test_prop_lines_probe.py, HANDOFF.md,
HANDOFF_ARCHIVE.md

---

## PICK UP HERE — Bet Finder says WHY under every row; NHL goals open on ANYTIME goalscorer (was 2+ goals). 2026-10-24 (5)

**Suite 167, FAILING: none.** New tests/test_bet_finder_why.py (2
controls red: the stat's matchup note dropped; the NHL why no longer
marking the position split as context); tests/test_book_props.py +1
(control red: board() dropping a yes market with no target).

WHY (Izzy 4:33 PM: "the bet finder doesn't attack defense or nothing"):
it did — the Bet Finder prices the model's whole projection — but never
said so. _why_lines(): under the table, "Why these numbers (n players)"
(open when prices are typed), each player: line, call, our chance, the
board's own "why" (NHL: rate, ice time, the opponent's team-level shot /
goal environment, DvP; NBA: minutes, season / last season, team minutes,
opponent; NFL / MLB: theirs) + this stat's matchup note. The 1st-period
and 1Q / 1H rows carry the why too. nhl_model.why_line now marks the
team-level matchup "(in the number)" and defence-vs-position "context,
not in the number — the position split did not beat the team-level
matchup on unseen games" (its docstring always claimed this marking).

ANYTIME GOAL (Izzy 4:42 PM, screenshot: Goals rows opened at 1.5 at
+1100 / +2000 — "i am researching for anytime goal scorer"): MEASURED in
the 10-24 record — all 431 NHL "Anytime Goalscorer" items (and 2+ / 3+,
and NFL anytime TD) carry NO target, so board() dropped them and lookup
fell back to the ladder ("Goals Milestones" starts at 2+). Now a yes
market with no target sits at its own line (YES_LINE: anytime 0.5, 2+
1.5, 3+ 2.5) and, with no total, IS the main line. Real board: 399 NHL
players open on anytime at 0.5. NFL anytime TD items carry no price in
this feed — none shown (honest blank). The grader captures anytime goal
from tonight (one-sided -> graded as "g*").

FILES: app/engines/book_props.py, app/engines/nhl_model.py,
app/views/Bet_Finder.py, tests/test_bet_finder_why.py (NEW),
tests/test_book_props.py, HANDOFF.md, HANDOFF_ARCHIVE.md

---

## PICK UP HERE — UFC is its own sport in the switcher; a sport's page nav is one wrapped bar of pills. 2026-10-24 (4)

**Suite 166, FAILING: none.** New tests/test_sport_nav.py (2 controls
red: the nav back to a column per page; the wrap rule on the outer
group). tests/test_ufc.py's wiring check now wants UFC in the switcher
and SPORT_PAGES, not in the four navs.

Izzy 12:46 PM: "UFC is not showing on its own instead it's implemented
as an option on all of the league pages", and a screenshot of NHL's page
nav: 16 st.columns, each label wrapped a letter per line into tall
slivers — "this format here bother me make it beautiful".

UFC: removed from the four navs; SPORT_PAGES["UFC"] = views/UFC.py (a
one-page sport loads straight through); kc_theme.sport_switcher lists
"UFC" and its caption says so; Home's Explore card is ("UFC", "UFC",
...) so it shows as a jump to the UFC sport.

PAGE NAV (app.py, sports with SPORT_SUBPAGES): st.pills(selection_mode
"single", default = the active page, key lc_sub_<sport>_pills_<active>
so a jump from Home that writes lc_sub_<sport> shows selected); a pick
writes lc_sub_<sport> and reruns. Theme: MEASURED in headless Chromium —
the pills sit in an INNER flex row Streamlit makes a one-line scroller
(display flex, nowrap, overflow-x auto; the page scrolled to the
selected pill and hid the first ones). The theme wraps THAT row
(div[class*="st-key-lc_sub_"] [data-testid="stButtonGroup"] div:has(>
button)): centred, wrapped, one soft rounded panel, labels nowrap, 40px
targets (test_control_language's floor). Screens checked at 1180 and
820 px: 2 and 3 tidy rows.

FILES: app/app.py, app/styles/kc_theme.py, app/views/Home.py,
tests/test_ufc.py, tests/test_sport_nav.py (NEW), HANDOFF.md,
HANDOFF_ARCHIVE.md

---

## PICK UP HERE — UFC page: the next card with DraftKings' chances (cut removed) for every fight — the BOOK's numbers, the site's model not yet built. 2026-10-24 (3)

**Suite 165, FAILING: none.** New tests/test_ufc.py (3 controls red:
no_vig leaving the cut in; pair() never swapping sides; the distance
prices read in feed order without the check). UFC page headless on a
fake feed in the probe's shapes.

Izzy 10-24: "make ufc work if possible" (not live betting). THE UFC
PROBE (10-24, UFC 333 Volkanovski vs Evloev, 14 fights): ESPN MMA
scoreboard via site.web.api; core odds per fight: DraftKings (100) +
"DraftKings - Live Odds" (200); each fighter's moneyLine, overUnder 2.5
with overOdds / underOdds, the round spread, victoryMethod (koTkoDq /
submission / points) under open / close per fighter; propBets ONLY
"Fight To Go The Distance" (two prices, no side field). ufcstats.com:
HTTP 200 but a 2,994-byte stub, 0 event links — blocked from Actions.
Core season event list returned count 0; the scoreboard by date
(?dates=20251018) returns finished cards — the backfill's route.

BUILT (engines/ufc, views/UFC.py — "UFC" in all four navs after Site vs
DraftKings, a Home Explore card, a refresh button): read LIVE at page
time (cache 10 min — fight night needs no nightly). Per fight: win %
(moneylines de-vigged), the six method outcomes de-vigged together,
over / under rounds, goes the distance, "ends inside the distance" from
the method market. Sides: away = first competitor on the 10-24 card;
pair() reads "details" ("D. Santos -115") to confirm the favourite and
swaps when it disagrees. Distance order: the YES is the one agreeing
with the method market's decision share, else P(distance) <= P(over the
round line). The page says in words these are DraftKings' numbers and
the site's model is not here yet.

NEXT: ufc backfill from the scoreboard by date (cards, winners, method,
round, closing odds if the core feed keeps them for finished fights) ->
fighter ratings tested against the de-vigged moneylines -> method /
rounds; and a nightly snapshot of the UFC odds into data/props/ufc for
the Site vs DraftKings grading.

FILES: app/engines/ufc.py (NEW), app/views/UFC.py (NEW),
tests/test_ufc.py (NEW), app/app.py, app/views/Home.py, HANDOFF.md,
HANDOFF_ARCHIVE.md

---

## PICK UP HERE — "Site vs DraftKings" page; Bet Finder labels each market and caps no-edge markets at THIN; UFC probe. 2026-10-24 (2)

**Suite 164, FAILING: none.** tests/test_book_grade.py +3 checks (2 new
controls red: a verdict under MIN_GRADED; the Bet Finder not capping a
no-edge market); new tests/test_ufc_probe.py (control red: card_info
reading the last event). Site_vs_Book headless (scorecard, empty state);
Bet Finder headless with a no-edge NHL SOG scorecard: label shown, every
call THIN.

THE BAR, set BEFORE any grade existed (book_grade.MIN_GRADED = 300): a
market gets no verdict until 300 graded lines; then "beats" = the paired
verdict says the site's chances beat DraftKings' de-vigged ones; else
"no edge proven". market_status(card, league, stat) falls back to the
one-sided "stat*" grade (NFL). load_scorecard reads data/props/
scorecard.json from the published data or the repo.

PAGE views/Site_vs_Book.py ("Site vs DraftKings", after Bet Log in all
four navs — test_bet_log wants Bet Log right after Bet Finder; a Home
Explore card): per league, per market: graded, the site's Brier vs the
book's, verdict (BEATS DRAFTKINGS / NO EDGE PROVEN / BEING GRADED n of
300), flagged plays, hit %, units, ROI at DK's prices; the * caption.

BET FINDER: above each stat a line "<stat>: BEATS DRAFTKINGS (z, n)" /
"NO EDGE PROVEN vs DraftKings — calls capped at THIN" / "BEING GRADED
vs DraftKings (n of 300) — not proven yet"; a no-edge market's support
is marked untested, so guarded_tier caps every call at THIN.

UFC PROBE (ufc_probe.py, manual workflow ufc-probe.yml, print only):
next card on ESPN's MMA scoreboard (site.web.api then site.api), fights
= competitions, each fight's core odds providers + DraftKings propBets
types / samples (first 3 fights), the core 2025 event list size, a
finished card's fight keys + one fighter's statistics record, and
whether ufcstats.com answers from Actions. NEXT: read it, then the
backfill + fighter ratings (tested vs DK's moneylines), method / rounds.

FILES: app/views/Site_vs_Book.py (NEW), ufc_probe.py (NEW),
.github/workflows/ufc-probe.yml (NEW), tests/test_ufc_probe.py (NEW),
app/engines/book_grade.py, app/views/Bet_Finder.py, app/app.py,
app/views/Home.py, tests/test_book_grade.py, HANDOFF.md,
HANDOFF_ARCHIVE.md

---

## PICK UP HERE — Step 3: the site graded against DraftKings every run (capture the site's chance beside the book's, grade on the box score, scorecard). 2026-10-24

**Suite 163, FAILING: none.** New tests/test_book_grade.py (4 controls,
red by exit code: devig leaving the cut in; a DNP graded as a zero; an
event graded twice; a ladder price graded with the cut left in).

10-24 morning run read: MLB names for 20 players (WS game) and 72 / 72
over-first; NHL 548 / 564, NBA 257 / 265; NFL Sunday's 13 games saved.

WHY THE CAPTURE: grading "who was right" needs the SITE's chance at the
book's line as of the same moment; the pages compute chances on the fly
and never kept them. Every un-captured night is lost for good.

1. CAPTURE (book_props_snapshot, after the league steps): book_grade.
   capture(league, build_data/data/<lg>/games.json, the board just saved)
   -> for every player / stat the book lines (main + up to 6 ladder
   rungs nearest it): [pid, stat, line, raw over, DELIVERED over] —
   bet_finder.chance_at on the Bet Finder's own pmfs and curves (NHL
   skaters + goalie saves, NBA, NFL + its 1Q / 1H keys) — stored as
   entry["ours"] / "ours_at" in the day file; merge_snapshot keeps them.
   Measured on archived payloads + the real 10-24 board: NHL 1,624 lines
   in 6 s, NBA 807, NFL 821. MLB not captured (its props are built at
   page time from lineups) — later.
2. GRADE (book_props_grade.py, a nightly step before the props commit):
   every day file <= today with "ours" and no "graded" -> ESPN summary;
   when final: actuals (NHL nhl_precompute.parse_summary; NBA nba_box
   + combos; NFL parse_summary_final + game_values, quarter keys only
   where his quarters add up) -> grade_event: y = actual > line; book =
   de-vigged from both prices at that line. ONE-SIDED (ladder only, i.e.
   NFL, whose totals carry no price): implied / LADDER_OVERROUND 1.07 —
   MEASURED 10-23/24: a rung at a total's line carries exactly the
   total's overround, NHL 1.072 (IQR 1.067-1.077, n 1,281), NBA 1.068
   (1.063-1.072, n 1,756) — only rungs priced 15-85%, graded under
   "<stat>*", never mixed with the clean grade. Rows appended to
   data/props/graded/<league>.json; the event marked graded.
3. SCORECARD (data/props/scorecard.json + [verify] "SITE vs DRAFTKINGS
   <lg> <stat>" lines): n, the site's Brier vs the book's, paired verdict,
   flagged plays (site 3+ points from the book: the side it liked) with
   hits and units at the book's own price.

FIRST GRADES: tonight's games (captured by the 6 PM run) are graded by
the 4 AM / 6 AM runs. NEXT: (a) a "Site vs DraftKings" page reading
scorecard.json; (b) the Bet Finder labels each row's market "beats
DraftKings" / "no edge proven" once n is large enough (decide the bar
before looking: n >= 300 and the paired verdict); (c) MLB capture; (d)
the UFC probe (Izzy asked 10-24: "What can we do with ufc?").

FILES: app/engines/book_grade.py (NEW), book_props_grade.py (NEW),
tests/test_book_grade.py (NEW), app/engines/book_props.py,
book_props_snapshot.py, .github/workflows/nightly-data.yml, HANDOFF.md,
HANDOFF_ARCHIVE.md

---

## PICK UP HERE — MLB on the Bet Finder opens on DraftKings' line too (players matched by name). 2026-10-23 (5)

**Suite 162, FAILING: none.** tests/test_book_props.py +4 checks (2
controls red: name_key keeping "Jr."; walks mapped for MLB).

Izzy 6:28 PM (screenshot, TB @ MIL, Batters / Hits): "The lines aren't
showing for mlb". Cause: ESPN's MLB athlete ids are not MLBAM's (the
MLB pages' ids), so (4) left MLB out. Now: book_props_snapshot keeps
each MLB player's NAME in the day file (bp.athlete_names: one call to
the athlete $ref per new player, names already saved are reused;
merge_snapshot carries "names"); board() builds "_names" {name_key:
ESPN id}; the Bet Finder matches MLB rows by "Batter" / "Pitcher" name.
Starters use MARKETS["mlb_p"] (k: Total Strikeouts / Strikeouts Thrown
Milestones; h: Total Hits Allowed / Hits Allowed Milestones); batters
MARKETS["mlb"] (h, tb, hr ladder, k ladder, singles, doubles, rbi).
WALKS DELIBERATELY UNMAPPED: the site's walks include HBP, DK's do not —
not the same bet. The record saved before this push has no names: MLB
lines appear after the next nightly run (a manual run before first pitch
covers tonight's game).

FILES: app/engines/book_props.py, book_props_snapshot.py,
app/views/Bet_Finder.py, tests/test_book_props.py, HANDOFF.md,
HANDOFF_ARCHIVE.md

---

## PICK UP HERE — Step 2: the Bet Finder opens every player on DraftKings' own line and price (NHL, NBA, NFL). 2026-10-23 (4)

**Suite 162, FAILING: none.** tests/test_book_props.py +6 checks (2 new
controls red: board() taking the second of a pair as the over;
price_at giving the main line's price at a moved line). Bet Finder
headless (NHL, a real 10-23 DK board mapped onto an archived slate's
players): every row opened on DK's line, both prices filled, Book says
(de-vigged) and CHECK flags computed with no typing. This zip also
carries (3), the simulator counts (simcount.zip), so either install
order ends the same.

THE FIRST REAL RUN (10-23 2 PM nightly): side_check — the FIRST of a
pair is the over: NHL 100 / 103, NBA 604 / 615, MLB 83 / 83 (the rest
are ladder prices a few cents off the total's). NFL: 0 pairs — DK's NFL
totals carry a line and NO price; prices are on the "N+" ladders.
Saved: 14 NHL, 12 NBA, 13 NFL, 1 MLB game. MLB simulator on real data:
196,192 PAs, runs per team simulated 4.43 vs actual 4.17 (6% high —
look at it); SGP kinds all thin / fail.

READING THE RECORD (engines/book_props): FIRST_IS_OVER (measured, the
note beside it); MARKETS maps our stat keys to DK's total and its ladder
per league (NHL sog / pts / a / g / sv; NBA pts / reb / ast / tpm / pra /
pr / pa / ra / q1pts; NFL pass / rush / rec yards, receptions, carries,
attempts, completions, TDs, ints, rush+rec, 1Q / 1H rec / rush / pass
yards); YES = one-sided markets (anytime goal / TD, 2+). board() reads
the day files (latest + first prices), lookup() gives {line, over, under,
ladder}: the total's line, else the ladder rung nearest even money;
price_at() gives the price at a line — the main line's two sides, a
ladder rung's over, else None. load_board() reads data/props/<league>/
today (+1; NFL +2) from the published data or the repo, with the as-of.
Unmapped and not priced by the site: NHL PP points; NBA steals / blocks /
1Q assists; NFL kicking.

BET FINDER: _attach_book puts "_bk" on each row by ESPN id (rows now
carry "_pid"; the NFL 1Q / 1H group too); a stat with any book line goes
per-player; each row opens on DK's line with "Your price" and "Other
side" prefilled; a "DraftKings" column shows "2.5: O +115 · U -155"; a
moved line gets DK's ladder price there or none — never the main line's
price at the wrong line; the caption says the as-of. MLB not yet (ESPN
athlete ids vs MLBAM — needs a name map).

NEXT (step 3): the grader — after the games, every saved DK price vs the
site's chance at that line: per market, does the site beat DK's de-vigged
chance (Brier, paired)? Markets that don't -> "no edge proven", their
VALUE / BET calls capped. Then the same DK line on the Model pages and
Simulators (they still open on the model's line).

FILES: app/engines/book_props.py, app/views/Bet_Finder.py,
tests/test_book_props.py; + (3)'s files; HANDOFF.md, HANDOFF_ARCHIVE.md

---
