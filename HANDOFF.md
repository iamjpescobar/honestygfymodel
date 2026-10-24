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

## PICK UP HERE — Simulator game views: 10,000 -> 50,000 games (MLB 25,000). 2026-10-23 (3)

**Suite 162, FAILING: none.** New tests/test_sim_counts.py (control red:
a page header put back to a literal "10,000 times").

Izzy: "We need to change that 10000 isn't it common". Measured before
changing (single game, this container): NHL 10k 0.23 s / 50k 0.97 s /
100k 1.9 s; NFL 50k 0.2 s; NBA 50k 0.1 s; MLB 10k 0.9 s / 50k 3.7 s.
Result memory ~0.6 MB per 1,000 games for a full NHL / NBA / NFL roster
(int16 arrays). So: NHL / NBA / NFL 50,000, MLB 25,000 — the
simulator's own noise on a 50% chance ±0.5 -> ±0.22 points (MLB ±0.32);
the game-run cache max_entries 8 -> 4 (a run is ~5x the memory; a
re-simulated game costs ~1 s). Headers, spinners, docstrings read
N_SIMS; Home's MLB card says 25,000. Parlay runs unchanged (NBA 500k,
NHL / NFL 200k, MLB 50k). NHL_Sim headless 4.6 s whole page, NFL 2.6 s.
Told Izzy plainly: this tightens the simulator's own noise, it is NOT
what makes numbers feel off — that is the book comparison (steps 2-3 of
the prop-lines work).

FILES: app/views/{NHL,NBA,NFL,MLB}_Sim.py, app/views/Home.py,
tests/test_sim_counts.py (NEW), HANDOFF.md, HANDOFF_ARCHIVE.md

---

## PICK UP HERE — The book's prop lines exist (DraftKings via ESPN's free core feed); every nightly run now saves them. Step 1 of 3 toward "does the site beat the book?". 2026-10-23 (2)

**Suite 161, FAILING: none.** New tests/test_book_props.py (4 controls,
red by exit code: the over taken as the member FARTHER from the
milestone, keep() keeping everything, merge overwriting the first price,
page 1 only). NOTE when writing controls: edit + re-run within the same
second can load a STALE .pyc (the first side-check control ran green that
way); a manual re-run showed it red.

IZZY 10-23: "worth it at" for MacKinnon's goal +100, book -135, skipped,
he scored; "the whole site feels off". MEASURED (last season's final 60
days, 17,102 NHL skater-games): projections by band match outcomes —
goals 0.087/0.085, 0.279/0.283, 0.475/0.480; top 1% 0.544 projected vs
0.477 actual (slightly HIGH, not low); shots and points the same. Stars
are not under-rated. The real gap: every props test compares the model
with HIS OWN RATE, never with the BOOK. Calibrated is not sharper than
the book; the props have no record against the people he bets against.

THE PROBE (10-23, prop-lines-probe log): ESPN's core API carries
DraftKings (provider 100) player props for NFL (1,460 items an event),
NHL (522), NBA (1,221), MLB (1,046): totals with line + both prices +
the open, and "Milestones" (N or more). Items have NO side field — a
total is two items (same player / type / line); a milestone is one-
sided. NFL samples sometimes carry no "odds" (line only).

BUILT: engines/book_props (fetch all pages, parse, side_check — the
member of a pair priced like the milestone at line + 0.5 is the over —
sides(), compact record, merge keeping the FIRST price beside the
latest); book_props_snapshot.py run every nightly (6 AM / 4 AM / 6 PM ET
— the 6 PM one is closest to puck drop) for games in the next 2 days
(NFL: 7), into data/props/<league>/<date>.json, committed by its own
step ("Commit the book's prop lines"). Not kept: first / last scorer,
team totals, exact, longest, period / game lines, double / triple
double. VERIFY LINES: "BOOK PROPS <lg>: events, items", "which of a pair
is the over ... {pairs, first_is_over, second_is_over}", types.
MLB: ESPN athlete ids, not MLBAM — a name map is needed before MLB props
can be matched.

NEXT, step 2: once a run shows which member is the over (the side check
must be one-sided — if it splits, stop and read samples), put the book's
line and price on every board row (Bet Finder, Model pages, Simulators,
1Q / 1H, 1st period): open on the BOOK's line, price filled, the model's
own line beside it. Step 3: the grader — after the games, every row the
site and the book disagreed on: who was right, per market; a market that
does not beat the book's de-vigged chance is labelled "no edge proven"
and its "worth it at" stops calling skips / bets on its own.

FILES: app/engines/book_props.py (NEW), book_props_snapshot.py (NEW),
tests/test_book_props.py (NEW), .github/workflows/nightly-data.yml,
HANDOFF.md, HANDOFF_ARCHIVE.md

---

## PICK UP HERE — Prop lines probe: does ESPN's free core feed carry the books' player-prop lines and prices? 2026-10-23

**Suite 160, FAILING: none.** New tests/test_prop_lines_probe.py
(control red: upcoming_event taking a final game).

WHY: Izzy, 10-23: "a lot of times i have to manually insert the line
and the price and most of the time it be off by 2 and up i want it to
make sense". Every board opens a player on a line the MODEL picks (NHL
SOG: the half-line under his projection; NFL / NBA / 1Q-1H: the line
nearest a coin flip; points / goals 0.5) and leaves the price blank,
because no prop lines were ever loaded — the public scoreboard and
summary carry GAME odds only (archive, NFL step 6: "Do not invent lines
to fill that column"). So the default line is a model number, often a
line or two from the book's, and the price is always typed.

THE PROBE (prop_lines_probe.py, manual workflow prop-lines-probe.yml,
print only, no commit): one upcoming event per league (NFL, NHL, NBA,
MLB) on ESPN's core API (sports.core.api.espn.com/v2/sports/{sport}/
leagues/{lg}/events/{id}/competitions/{id}/odds -> providers; .../odds/
{provider}/propBets?limit=1000 -> props): providers, item counts, prop
types, two raw samples (5 levels deep). Free; the same company's feed
the site already reads; rule "no paid odds API" holds.

NEXT: read its log. If props are there -> a parser to the real shape,
a nightly step that saves tonight's lines + prices per player, and every
board (Bet Finder, Model pages, Simulators, 1Q / 1H, 1st period) opens
on the BOOK's line with the book's price filled in, the edge computed
against it, the model's own line shown beside it. If not -> say so, and
look at other free sources before anything else.

FILES: prop_lines_probe.py (NEW), .github/workflows/prop-lines-probe.yml
(NEW), tests/test_prop_lines_probe.py (NEW), HANDOFF.md, HANDOFF_ARCHIVE.md

---

## PICK UP HERE — MLB simulator survives Statcast's NA; the 10-22 4 PM nightly read (NHL periods / shots / SGP, NFL 1Q / 1H). 2026-10-22 (11)

**Suite 159, FAILING: none.** tests/test_mlb_sim.py +1 check (control
red: _na() that only knows float NaN -> "Statcast's nullable columns ...
read exactly like plain ones" fails).

THE BUG: the real nightly's MLB simulator died — "TypeError: boolean
value of NA is ambiguous". Statcast's frame carries on_1b / on_2b /
on_3b (and friends) as pandas nullable integers; an empty base is pd.NA
and `x == x` / `x != x` on it raises inside `if`. The synthetic season
used float NaN, so the test never saw it. Fix: mlb_sim.state_rows turns
every missing value (None, NaN, pd.NA — mlb_sim._na) into None before
any comparison; mlb_prop_precompute._final_scores uses pd.notna. The
test now runs state_rows and _final_scores on the synthetic PAs recast
to Int64 with NA. The MLB simulator's real verdicts arrive with the
next nightly.

THE 4 PM NIGHTLY (read 10-22):
NHL — this season's shots from the NHL feed: 153 games, 100% matched,
SOG == ESPN 99.9%. Attempts -> SOG thin z 0.1, chances -> goals thin
z 1.7: context only (as measured in (10)). Ice time SOG z 7.9, pts 6.3.
1st period (now with this season): point z 14.1, 1+ SOG 15.7, 2+ SOG
13.6, goal 13.9 — all beat, calibrated; team lines thin (O1.5 z 0.3,
home leads z 0.9). SGP: PP 4.2, PPP 4.6, PW 3.6 beat; GG 2.0, GW 1.9,
PPPP 1.6, SS 0.5 thin; PPopp fails. Multi-goal watch: 19 of 61 two-goal
scorers in its top 25 (random 25 -> 5.3).
NFL — 1Q / 1H on 11,490 clean player-game stats: receptions 1Q z 6.2 /
1H 7.3, receiving yds 5.5 / 5.6, rushing yds 3.2 / 3.0, carries 2.2 /
2.8, 1Q completions 3.0 — beat. QB 1H (yds, completions, attempts)
fail; 1Q yds / attempts thin. QB props OVER-predict throughout
(predicted 0.48-0.54 vs actual 0.37-0.45, n ~150-170) — the next NFL
quarters item: the QB clean set is small and biased (games whose
quarters add up skew to simpler games?) or the QB ratio bands need
their own split. Not offered on the Bet Finder (offered() = beats only),
so no false bet meanwhile. SGP: UW beats z 2.7, TW thin 1.6; rest fail.

FILES: app/engines/mlb_sim.py, mlb_prop_precompute.py,
tests/test_mlb_sim.py, HANDOFF.md, HANDOFF_ARCHIVE.md

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
