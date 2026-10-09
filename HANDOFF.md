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

## PICK UP HERE — every bet is priced on the market first, and there are far more props. 2026-10-04

**Suite 124, FAILING: none.** Fourteen negative controls red by exit code.
Python 3.11 venv (Render's runtime) runs the whole suite green too.
Pages looked at in a real browser against the site theme (NHL Model and
NFL Model from fixtures, the MLB prop board from the simulated season).

### WHY: THE FORMULA WAS PRICING THE MODEL AS IF IT WERE THE TRUTH

The first weekend of logged picks said so. NFL: **44 "value" bets out of
16 games**, edges up to 22 points — Colts-Commanders Over 46.5 at 75% on
a model whose total TIES the league average (MAE 10.96 vs 10.97). NHL
10-03: nine moneyline picks, mostly +170 to +230 dogs, 3-6. Every edge
was model % minus break-even, so whenever the model (team rates, plus
the MLB starter) disagreed with a market that also knows QBs, goalies,
injuries and weather, the page called the model right. Staking made it
worse: nearly every one of those 44 hit the 2% cap — about 88% of the
bankroll on one Sunday — and many were the same bet twice (ML + spread).

### THE FORMULA (engines/market_blend.py)

    logit(Final) = w * logit(model) + (1 - w) * logit(market no-vig)

w is the MODEL'S WEIGHT, fitted by maximum likelihood on past games that
have both a walk-forward model prediction and a recorded line, one per
market (moneyline / total / spread-run line-puck line). It is scored
CROSS-FITTED (fit on one half, score the other) against the market alone
with paired_verdict, and the model gets its say ONLY on "beats". "thin"
is NOT proof — on a simulated season where the market knew every true
strength, a noisy model still came out thin with w = 0.31 — so thin and
fails both price at the market. Badges: BEATS MARKET / NOT PROVEN YET /
MARKET WINS / UNTESTED. Every edge, tier, stake, logged pick and the
best-value strip use Final. No market line -> no Final -> no edge
claimed (the model is still shown).

A total with no over/under prices reads as 50% at its own line (that is
what a total line means); `priced` is recorded and the nightly prints
the share. The spread's sign is checked against BOTH `details` and the
moneyline (market_blend.home_spread) — either disagreeing means no
spread is priced.

**Until the Market history workflow runs, Final IS the market** — the
pages say so, and value can only come from a better price at the
reader's book than the posted one.

### THE HISTORY IT IS FITTED ON (market_history.py, NEW manual workflow)

`Market history` (Actions -> Run workflow) walks ESPN for NFL 2025, NHL
2025-26 and MLB 2026 regular season and writes data/market_lines/
{nfl_2025, nhl_2025-26, mlb_2026}.json — the scoreboard event's odds,
else the summary's pickcenter. ONLY writer of data/market_lines/.
Doubleheaders under one key are dropped, never guessed. The file says
"recorded line", not "closing line" — ESPN promises nothing more.
This season's NFL/NHL lines ride on the nightly's own finals rows
(`odds` via espn_feed.recorded_line), never a second fetch.

### STAKING

One bet per game SIDE: moneyline and spread on the same team are one
opinion (model_picks.GROUP) — value_bets keeps the higher-EV one, the
log's first-writer-wins key is (game, group). New "Max per slate"
setting (default 10%, a bettor preference like the per-bet cap): the
best-value strip scales every stake down together past it.
Results splits the record: "Market-anchored (from 10-04)" vs "Model only
(before 10-04)" — the new formula is judged on its own picks.

### MORE RESEARCH (all from distributions the models already had)

- **MLB batters** — 15 tested lines: hits 0.5/1.5/2.5, TB 0.5-3.5, HR,
  K 0.5/1.5, walks, singles, doubles, RBI 0.5/1.5. RBI = runs scoring on
  his PA (post_bat_score - bat_score), from a league table P(RBI | outcome,
  lineup slot) the nightly MEASURES — reads a touch high vs official RBI
  (errors, DPs); said under the table. No score columns -> no RBI market.
- **MLB starters** (mlb_props.project_pitcher) — K 3.5-6.5, hits allowed
  4.5/5.5, walks 1.5, HR 0.5: each slot of tonight's lineup against him,
  PA by PA, for his own (shrunk) batters-faced. Walk-forward vs his own
  rate (mlb_prop_precompute.validate_pitchers). BF is taken as
  independent of how the game goes (an early hook is not modelled) —
  stated on the page.
- **NHL** — skaters any line (SOG to 4.5, points 1.5 added) from stored
  means (nhl_model.skater_pmfs); **goalie saves** (shots NB at a measured
  size x his save rate shrunk by a fitted beta prior, last season + this),
  tested at TEAM level on last season (validate_saves). Both of a team's
  goalies are priced — who starts is not known until morning skate.
- **Team totals, alt spreads, alt totals** for all three sports
  (engines/alt_lines.py) — NFL one-side SD DERIVED from the measured
  margin/total SDs. Model only: no posted price exists to anchor them.
- **NFL QB** — completions, passing TDs, interceptions (his per-attempt
  rate shrunk by a FITTED beta prior, nfl_precompute.qb_rate_priors) and
  2+ TDs (the anytime Poisson read at two).
- **Prop board** (model_view.render_prop_board): pick a stat, every
  tested line in the table, and "check any line at your price" — line
  defaults to the one nearest 50% for that player, price defaults to the
  model's fair price so nothing reads as value until a real price is
  typed. Optional other-side price shows the book's own no-vig chance.

### RULES THIS BATCH ADDS

11, 12 and 13 in STANDING RULES above.

### FOR THE FIRST LOGS

    [verify] MLB moneyline: n=.. market LL .. vs blend (cross-fitted) .. -> beats|thin|fails
    [verify] NHL/NFL market coverage {... with_line ..}
    [verify] Hits O0.5 .. RBI O0.5 ..   [verify] K O4.5 .. (starters)
    [verify] Saves O24.5 (team level) ..   [verify] save prior ..
    [verify] RBI table measured: yes; slot 4 HR drives in 1/2/3/4: [..]

### FILES, 2026-10-04

    app/engines/market_blend.py, app/engines/alt_lines.py, market_history.py   NEW
    .github/workflows/market-history.yml                                         NEW
    tests/test_market_blend.py, tests/test_more_props.py                         NEW
    app/engines/{model_math,game_model,mlb_game_model,nfl_game_model,nhl_model,
                 model_picks,model_view,mlb_props,espn_feed,nfl_projection,
                 nfl_prop_odds}.py
    app/views/{MLB_Model,NHL_Model,NFL_Model,GameCard,Results,NFL_Projections}.py
    mlb_model_precompute.py, mlb_prop_precompute.py, nhl_precompute.py,
    nfl_precompute.py, nfl_projection_probe.py
    tests/test_value_picks.py, tests/test_mlb_props.py
    HANDOFF.md, HANDOFF_ARCHIVE.md (09-15 entry rotated out)

---

## PICK UP HERE — colour that says what to do, badges that say what to trust. 2026-10-03 (9)

**Suite 122, FAILING: none.** Six negative controls red by exit code.
Looked at in a real browser (Playwright screenshots of NFL/NHL Model
with the site theme) — that pass caught two things no test would:
steel-blue THIN read as a paler STRONG (now grey), and a raw 1.997-pt
edge printed "+2.0" under a THIN label (tier now on the printed 0.1-pt
grid, which is also how the log stores and Results buckets it).

### WHAT SHIPPED

**Edge tiers** on every value row and the new strip — STRONG (5+ pts,
cyan), VALUE (2-5, gold), THIN (0-2, grey), none — cut points shared
with model_picks.EDGE_BUCKETS so a colour names the Results bucket its
record lands in. Text label on every colour.

**Trust badges** per market: BEATS BASELINE / THIN EDGE / NOT PROVEN /
UNTESTED, from `model_math.paired_verdict` — paired per-game loss
differences vs the baseline, z >= 2 (a statistical convention, printed)
= beats, better-on-average = thin, else fails. Written into every
validation by the nightly (ml / total / spread verdicts on the game
models, a verdict per prop market). Older files fall back to the plain
booleans and can never show THIN. NFL prop chances are UNTESTED by
construction until graded.

**Best value tonight** atop MLB/NHL/NFL Model: every side with positive
EV at the POSTED price across the slate, strongest first, tinted, with
stake and trust. Games are projected once up front so strip and cards
read the same numbers.

Known: an editable data_editor cell ignores Styler formatting, so an
empty Price shows Streamlit's grey "None" placeholder; the caption says
what it means. Never pre-filled.

### FILES, 2026-10-03 (9)

    app/engines/model_math.py       paired_verdict, SIGNIFICANCE_Z
    app/engines/{game_model,nfl_game_model,nhl_model}.py, mlb_prop_precompute.py  verdicts
    app/engines/model_view.py       tiers, trust, legend, styled tables, best-value strip
    app/engines/mlb_props.py        market_verdicts -> verdict strings
    app/views/{MLB_Model,NHL_Model,NFL_Model,GameCard,NFL_Projections}.py
    tests/test_value_picks.py       section 8

---

## PICK UP HERE — a picks file with two writers, and a second leaking test. 2026-10-03 (8)

**Suite 122, FAILING: none.** Four negative controls red by exit code.

The first nightly after the value batch died at "Commit graded model
picks": `CONFLICT (add/add) in data/model_picks/mlb.json`. Two causes,
both fixed at the mechanism:

1. **A second test leaked.** tests/test_calibration_lines ran
   calibration_picks.main() with only RECORD_PATH sandboxed, so in CI it
   wrote the real games.json AND created data/model_picks/mlb.json (3
   real value picks off real ESPN lines — the odds path works: "4/4
   projected, 4 with an ESPN line"). The restore step fixed the tracked
   file but not the NEW one. It now also removes untracked files under
   data/ by explicit path (never git clean — rule 7); run against a
   throwaway repo before shipping: tracked restored, leaked file gone,
   ignored app/data and root files untouched.
2. **mlb.json had two writers** — slate-picks logs it, the nightly
   graded it, and Izzy ran both at once. ONE OWNER PER FILE now:
   slate-picks logs AND grades MLB (`model_picks_grade.py mlb`); the
   nightly logs and grades NHL/NFL (`model_picks_grade.py nhl nfl`) and
   never stages mlb.json.

tests/test_ci_hygiene.py now pins all of it, reading CODE not comments
(its first draft failed on its own explanatory comments): restore step
position and untracked cleanup; every test that runs calibration_picks
.main() sandboxes BOTH MLB_SLATE_PATH and PICKS_ROOT (suite-wide — the
leak moved from one test to another); every log_picks call passes
root=PICKS_ROOT (AST); grading ownership per workflow.

### FILES, 2026-10-03 (8)

    tests/test_calibration_lines.py, tests/test_calibration_picks.py
    calibration_picks.py      PICKS_ROOT module-level
    model_picks_grade.py      sports as arguments
    .github/workflows/nightly-data.yml, slate-picks.yml
    tests/test_ci_hygiene.py

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
