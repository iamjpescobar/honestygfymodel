# Los Cappers — session handoff

Read RULES before proposing any change; every one was learned by
breaking something.

**Rewritten 2026-08-06. An earlier version of this file was itself
corrupt — a dead copy of item V dangled under the pitcher-H2H section,
describing as broken something the section twenty lines above described
as fixed. Verify before you build. START WITH "PICK UP HERE".**

---

## PICK UP HERE — 2026-08-10, KBO probe filter

**Suite 79 files, FAILING: none.** One file changed, one added.

### THE KBO PROBE COULD NOT HAVE ANSWERED ITS OWN QUESTION

v2 reported *"NAMES ARE ON THE PAGE: 10 candidates near starter markers,
server-rendered, no XHR. The KBO migration is unblocked."* It was not.
The ten were:

    기록이 됩니다 등록 라인업 선택 업데이트 전력 전력분석 전력비교 키플레이

"is recorded", "will be", "register", "lineup", "select", "update",
"power", "power analysis", "power comparison", "key play". UI vocabulary,
every one. **Two independent causes, both now fixed.**

**1. THE CORPUS.** The probe counted 선발 in RAW html, so eight
occurrences inside a `setPreview()` function and a **commented-out alert
string** were read as a server-rendered table. A commented-out alert is
not even executed. It now strips `<script>`/`<style>` and prints BOTH
counts, because the gap is the finding: raw high + rendered zero means
the page references starters and fetches them over AJAX — a completely
different next step from "parse the table".

**2. THE FILTER.** `[가-힣]{2,4}` plus a hand-written stoplist. A
stoplist cannot win: it needs the word foreseen, and rendered content has
its own nav labels and headers, so the same false positive would return
from a different corpus. Now structural — **exactly three syllables, and
the first is a common Korean surname.** Korean names are overwhelmingly
surname + two-syllable given name; surnames are a small closed set.

Syllable count must come first: 전 is a genuine surname, so 전력 and
전력분석 sail through a surname check alone.

**Precision over recall, deliberately.** Rare two- and four-syllable
names are dropped. For a probe that is the right trade — a missed name
understates, an invented one misdirects and cost a session here.

**MY FIRST VERSION LEAKED and I only caught it by testing against the
actual ten.** 기록이 passed: 기 IS a surname, and the word is a noun plus
a subject particle. The rare surname tail (기 반 왕 금 옥 육 맹 제 모 탁
국 어 은 편 용) is all genuine surnames AND common noun syllables — it
buys almost no recall and costs precision on every noun starting with
one. Dropped. Result: **0/10 UI words accepted, 11/11 real KBO pitcher
names caught.**

**It is still a heuristic.** 이용자 ("user") is three syllables starting
with the commonest surname in Korea; no syllable rule separates that from
a person. That is why the probe now prints the ACCEPTED names *and* the
REJECTS, and why the verdict says to check them against tonight's actual
probables. A count can be wrong in silence; a list cannot.

### `tests/test_kbo_name_filter.py` (NEW, #79)

Pins the exact ten verbatim, asserts real names still pass (a filter
rejecting everything would satisfy the first half alone), and asserts the
DATA FLOW rather than the presence of a line.

**That last part was a bug in my own test.** It first checked only that a
`re.sub(r"<script` call existed somewhere. Setting `rendered = html` on
the line above left that call in place doing nothing and the assertion
stayed green — the same failure as rule 26, where an assertion matched a
workflow's comment instead of its command. It now walks the AST: every
`rendered` assignment must be a Call, and nothing may slice raw `html`
afterwards. Six negative controls, all confirmed red.

### NOT DONE, and needs your other session

**The NPB label is NOT in this repo.** `grep -c "NO ADVANCE" app/views/NPB.py`
returns 0. A version of it existed in my workspace — well written, citing
run 85245341493 and correctly distinguishing "no forward WARNING"
(measured: 109 upcoming games, zero risk vocabulary) from "never cancels
in advance" (NOT measured: zero `<div class="cancel">` anywhere on the
page, so the case had no chance to appear). It was never committed. Find
it in that session or re-write it — do NOT let the two of you write it
twice.

### Still open
- **Tier 2 (`proj_total`)** — MLB probe correctly refused to half-fire:
  the one entry with runs is the LEAGUE AGGREGATE (591 runs in 118 G),
  not a club. Standings endpoint is the untested lead.
- **KBO AJAX** — `setPreview(... awayPit, homePit)` and
  `S2iAjaxHtml({url: "/Schedule/GameCenter..."})` are in the CONTEXT
  output. Extract the URL verbatim and call it with a real gameId. Do not
  guess `.asmx` names again — v1 did and got 401/401/500.

---

## PICK UP HERE — state as of 2026-08-10 (evening)

Perf audit + correctness sweep on the shipped item C. **Suite 77 files**
(one new). Everything below was MEASURED, not inferred.

### PERFORMANCE — no action needed, and here are the numbers

Benchmarked against real data with a cache shim standing in for
streamlit, so these reflect what the app does including cache hits:

| path | cold | warm |
|---|---|---|
| calibration record (162 KB) | 5.82 ms | **0.07 ms** |
| `summary()` | — | 0.09 ms |
| `load_slate("mlb")` | — | 0.08 ms |
| `rank_games()` over 10 real games | — | 0.03 ms |

One Home paint = **10 file reads, 0.6 ms**. `_load_cached(stamp)` is
earning its keep at 83x on the record.

- **`slate_guard` has no caching and reads two paths per call. Checked
  before flagging: 0.08 ms. Leave it.** A cache there would need the same
  mtime-stamp treatment or it would serve a stale slate.
- **Growth is the only thing to watch.** 158 KB over 15 days = 10.6
  KB/day, ~1.9 MB by season end. The cold merge is linear, so ~70 ms
  cold at 2 MB. Not urgent; know it before it surprises you.
- Cold start ~500 ms, essentially all pandas/requests/bs4 pulled through
  `statcast_engine`. Per PROCESS, not per request. Not worth restructuring.

### THREE REAL BUGS, all found by looking at the produced file

The 2026-08-10 slate looked complete — 10 games, both starters, 8 edges.
It was not. **Read the artifact your pipeline writes, not just its exit
code.**

**1. Weather was null on all ten games.** `weather_temp`, `weather_wind`,
`weather_condition` — zero of ten. `wind_adj` was 0 on every game (one
distinct value in the whole file). MLB does not post park weather until
close to first pitch, and slate-picks' FIRST and most important run is
1 PM ET, six hours early.

GameCard has done the right thing all along — its "in-house weather
desk" falls back to the National Weather Service and its own comment
says MLB posts late and it fills the gap "most of the day".
`_write_mlb_slate` never asked. **Two parts of one app disagreeing about
the weather for one game — rule 21, and the slate was the wrong side.**

Fixed: NWS fallback (roofed parks skipped, as Weather_Board does),
`weather_source` recorded so a forecast is never mistaken for an
observation, and the temperature now feeds `grade_matchup` so the
>=80F/<=65F O/U signals can fire on the 1 PM build at all.

**2. TWO WIND ENGINES, and the slate called the one that can't read
MLB's format.** `wind_engine.wind_hr_adj` handles compass
("12 mph SW", what NWS gives). `player_of_the_day._wind_hr_adj` handles
field-relative ("8 mph Out To CF", MLB's own). `_parse_wind` returns None
for field-relative ON PURPOSE — its docstring says so and names the other
function. So on the 5 and 7 PM runs, where MLB HAS posted a wind, the
slate wrote `wind_adj` 0 and `wind_note` None. Silently. Measured:

    "8 mph Out To CF"   -> (0, None)      "15 mph In From CF" -> (0, None)

Fixed with a router: field-relative first (it states which way the ball
carries), compass as fallback. Not merged into one function — they answer
with different confidence from different inputs. **`tests/test_mlb_slate_wind.py`
(NEW, #77)** asserts both engines are CALLED, not merely imported; two
negative controls confirm it catches the revert.

**3. `why_first` said "weather and park swing" having read no weather.**
Consequence of 1 and 2: the swing was real but came from the park factor
alone. A wrong number is catchable; **a right number under a wrong label
is not.** `_swing()` now returns which signals it measured and the label
names only those.

### Also fixed
- **`edge_signals` were published and read by nothing.** The file holds
  `"WHIP: edge Boston Red Sox (1.28 vs 1.55)"`; the card showed a bare
  letter. Rule 20, on the one page whose claim is "here is where the
  model has an opinion" — the reasoning IS the product. `edge_reasons()`
  now renders the lead game's signals.
- **NPB probe's played-check was wrong, and it is why v2's verdict was
  absurd.** Production requires DIGITS inside `<div class="score1">`;
  the probe tested for the tag's PRESENCE. Scheduled games carry an empty
  placeholder, so 154 of 157 future rows were discarded as played —
  that is the "3 upcoming" number. Now uses production's regex, and
  STRUCTURE prints both counts so the gap is visible. **Copying a
  selector is not copying a parser.**

### Two handoff items were stale
- `wnba-lineup-probe.yml` is ALREADY gone from the root.
- The admin-credential check cannot work as written: `auth_config.yaml`
  is gitignored and lives on Render's disk, so it never appears in a zip
  or a fresh clone. **It has to be checked on Render**, not from the repo.

### PITCHER SPLITS WINDOW — new, his request

The Game Card's STATS / STRIKES tables were **season only**, on a page
whose whole job is tonight's matchup. A starter's season line can be four
months old, and every other window control in the app — the grade window
ten lines above it, the lineup filter, Bullpen Board, Player of the Day
— already offered one.

Now: **Season / L10 / L5 / L3 / Last game**. Nothing estimated —
`get_pitcher_advanced_splits` slices raw Statcast rows through
`recency_windows` BEFORE any metric is computed, so IP, the games count
and every rate are honest for the window.

`l3` and `l1` are new keys in `recency_windows`, the ONE shared
definition — not a second map in the view.

**THE SAMPLE PROBLEM, and what was done about it.** `Last game` is about
25 batters faced. A .400 BA against on one night renders in the same
column, font and colour scale as a .240 over 700. statcast_engine already
carried a long comment about the empty-split case rendering "BA .000,
SLG .000, WHIP 0.00" — a line describing the most dominant pitcher who
ever lived — whose stated reason was that **"the table has no sample
column to contradict it."**

Three things fix that and are pinned by
`tests/test_pitcher_splits_window.py` (NEW, #78):

- **`G` (games) is now a column in BOTH tables**, second, right after
  Split — a denominator read after the number it qualifies has already
  done its damage. STRIKES had no IP either, so it previously had no
  sample at all.
- **`G` is never colour-ranked.** It is a sample size; shading it would
  claim more games is better or worse.
- **`THIN_WINDOWS` lives in `recency_windows`**, beside the slicing, so
  the warn-list cannot drift from the window list. A thin window prints
  a small-sample line above the table naming the actual game count, and
  calls out the platoon rows separately — a starter can face three
  lefties in a game, and "vs LHB" over three at-bats is an anecdote.

Also removed: `splits_vs_r` / `splits_vs_l`, the old season-only fetches.
The Matchup table was their only consumer and it now fetches per window,
so leaving them would have been two cached calls nothing read — rule 20,
in the same batch that fixed another instance of it.

**Six negative controls, all confirmed red:** drop G from STRIKES, offer
a window `apply_window` doesn't implement, wire the control to nothing,
remove the warning, colour-rank G, make `l1` slice to zero.

`_games` was also added to the `empty` return of
`get_pitcher_advanced_splits` — the populated path always had it, so a
caller reading the sample got a KeyError on exactly the case where the
sample matters most.

### Verify
1. `git pull`, run the suite. **78 files, FAILING: none.**
2. **After the next slate-picks run**, read the log line — it now ends
   `N weather from NWS forecast`. On the 1 PM run that number should be
   close to the open-air game count. If it is 0, the NWS fallback is not
   firing and tier 3 is back to park-only.
3. `grep -c nws_forecast data/mlb/games.json` — non-zero on a 1 PM build.
4. **The ranked card still has never been seen.** Three games, one line
   naming the tier the sort used, now with the lead game's actual
   signals beneath it.

---

## PICK UP HERE — state as of 2026-08-10 (afternoon)

**Everything below this block is still accurate. This is the delta.**

### The red test was the test's own bug, not a leaked fixture

`tests/test_slate_guard.py` was the only failing test. FIX-THIS-NEXT.md
ranked "a stale fixture on disk" first; **it was wrong, and the way it
was wrong is the interesting part.**

`staleness_note()` for MLB reads BOTH locations and keeps whichever
declares the later slate date — `app/data/mlb/games.json` (which the
test stubbed) and repo-root `data/mlb/games.json` (which it did not
touch at all). That second path was empty for months, so the omission
was invisible. The moment `calibration_picks` wrote a REAL dated slate
there, that file out-dated every fixture the test wrote, every MLB case
returned `ok=True`, and `staleness_note` returned `''` for all five.

**The test was defeated by the feature it was written to protect.** The
five assertions were fine; they were never reached. Fixed by backing up,
blanking and restoring the repo-root path too — the same
backup/blank/restore the other three leagues already had. Verified with
a real dated slate in place, and the real file is byte-identical
afterwards.

Generalises, and it is now rule 27: **a test that stubs a path must stub
every path the code under test reads.** `_read()` deliberately reads two
locations; a fixture covering one of them is a fixture covering none.

### Item C's before-1PM state is CONFIRMED LIVE

Screenshot at 11:02 ET: "Tonight's MLB slate builds around 1 PM ET, once
MLB posts probable starters." Framed section, hairline rule, no false
alarm. Verify-list step 2 is closed. **Step 3 — the ranked card itself —
is still unseen**, and needs a look after a same-day `slate-picks` run.

### Decisions taken, so nobody re-opens them

- **Dome flags stay in `intl_venues.py`. CLOSED, decided against.**
  Moving them to published data would break the "unknown ≠ open"
  guarantee that `roof()` exists to provide: a fetch failure or partial
  write would silently return `None` for every venue, where source code
  cannot fail to load. It also makes a fallback depend on the network
  that its caller already fell back FROM. And it buys nothing — 12 NPB
  venues and 11 KBO patterns that change about once a decade are a
  constant, not data. Same reasoning as `park_factors.py`. **Do not
  re-propose this as a cold-start fix.**
- **WNBA Volume now carries season AND L5, paired.** Not a swap. A bare
  "FTA L5" of 6 is unreadable — the reader cannot tell a player who
  always draws six from one whose attempts just doubled, and the
  doubling is the only reason to open the tab. The pair is the signal.
  L10 deliberately not added: six columns for two stats on a tab already
  carrying ten, read on an iPad, and L10 sits between two numbers the
  reader already has.
  **Stocks stays season-only on purpose** — the precompute windows the
  COMBINED `stocks` figure but not `stl`/`blk` separately, so there is no
  `l5_stl` to show, and deriving one from the combined number would put a
  label on a quantity that isn't what it says. Rule 21 cuts the other
  way here: the asymmetry is honest because the data is asymmetric.
- **mykbostats is going, not staying.** Clause 6 forbids betting use.
  This is no longer "unexamined" — it is decided. See E3 below; the only
  thing standing between here and dropping it is probables.

### Three probes delivered, NONE of them run yet

All three write nothing, commit nothing, and print a verdict line. **Run
them before building anything on top of what they ask about** — rule 22
exists because this repo has shipped correct, tested code with no
working source behind it.

**FIRST RUN 08-10, run 85209788549 — two probes were WRONG and were
rewritten. Read this before trusting any verdict from them.**

- **KBO: a real finding, from the CONTROLS rather than the guesses.**
  `Schedule/GameCenter/Main.aspx` is **server-rendered and already
  contains 선발 투수** (200, 57KB). The rendered schedule pages carry
  none, which is what this file already said — but nobody had looked at
  the game centre. **The premise that probables are only client-side was
  true of the schedule pages and false of this one.** The `.asmx`
  guesses returned 401/401/500; the seven endpoints the page references
  are recorded in the probe as a fallback, not the main line. v2 now
  asks the narrower question: can per-game starter NAMES be paired to
  both teams for today's slate? "The characters appear somewhere" is not
  that — a page can carry the word as a header on an empty table.
- **NPB: the probe was wrong, not the site.** v1 split on
  `<div class="date">`, which does not exist on that page, found zero
  dated blocks, and reported "no forward-looking warnings" — a verdict
  it had never measured. `npb_precompute.parse_games()` has parsed this
  exact page in production for months using `<tr id="dateMMDD">`. v2
  uses its selectors verbatim and prints a STRUCTURE line first; if that
  says zero rows, the NPB build is already broken and nothing after it
  is an answer.
- **MLB: verdict NOT earned, do not record it.** v1 tried one hydrate
  shape, got 0/30 and printed "NOT BUILDABLE HERE". **Zero out of thirty
  is the signature of a malformed query, not a missing field**, and v1
  could not tell those apart because it never checked whether any stats
  block came back. v2 tries four documented shapes and prints entries /
  w-stats / w-runs per shape. **Tier 2 is not closed.**

The generalisation, and it is the same one as rule 27: **a probe that
invents the structure it parses can manufacture either answer.** When
the pipeline already parses a page, the probe reads it the same way — a
second parser is a second thing to be wrong. Two of three v1 probes
guessed; both guessed wrong; one of them would have shipped a label
asserting something never checked.

| script | answers | if the answer is "no" |
|---|---|---|
| `npb_void_probe.py` | does npb.jp publish a forward-looking cancellation warning like KBO's? | ship a LABEL saying NPB publishes none, not an invented badge. That still closes the parity gap — rule 21 is about the reader being able to tell, not about both boards having the same badge |
| `mlb_rsra_probe.py` | can tier 2 (`proj_total`) be built from team RS/RA on statsapi, which we already depend on? | tier 2 stays dark. **Still do not substitute the O/U signal count** — it counts signals toward Over and is not a number of runs |
| `kbo_probables_probe.py` | is there a direct endpoint for KBO probables, which the rendered page draws client-side? | ship KBO without probables and label the board, rather than keeping a source clause 6 forbids |

`kbo_probables_probe` prints the `.asmx`/`.ashx` URLs the schedule page
itself references. **If the guessed endpoints 404, that list is the real
output** — it is ground truth and the guesses are not.

All three must run from **Actions**, not a Codespace: Korean and
Japanese sites geo-fence and rate-limit by region, and ESPN already
taught this repo that an IP-range result from a laptop predicts nothing.

`.github/workflows/open-question-probes.yml` runs all three on manual
dispatch — Actions tab, "Open-question probes", Run workflow. Three
SEPARATE jobs on purpose: they answer unrelated questions, and as
sequential steps a Japanese site being down would hide the MLB answer.
**Record what each verdict said in this file**, including a "cannot be
built" — that closes an item just as well as a yes, and an unrecorded
probe result means somebody runs it again in three weeks.

### Suite

**76 files** (was 75; `tests/test_wnba_context_windows.py` is new).
Same five streamlit-only failures in a bare container, green in the
Codespace.

`test_wnba_context_windows` asserts the PROPERTY, not the columns: for
every context column, the window named in the header and the window of
the key behind it must agree, and no recent-form column ships without
its season baseline. Rename or drop a column and it stays quiet; feed
"FTA L5" the season key and it goes red. **Three negative controls
confirmed red** — label/key mismatch, orphaned L5 with no baseline, and
a windowed key with the window stripped from its header.

---

## PICK UP HERE — state as of 2026-08-10

**Item C is LIVE and its CI half has really executed.** First real run of
`calibration_picks._write_mlb_slate()` produced:

```
2026-08-09 | 15 games | 14 with an edge
```

Tier 1 of the ranking is alive on a real slate — `grade_matchup`
resolved both starters' splits on 14 of 15 games. That was the single
biggest unknown in the whole item and it is closed. Suite in the
Codespace: **76 files, FAILING: none.** (My container shows 5 failing;
they are the streamlit-only ones documented below and are expected.)

**Still never seen: the ranked card itself.** Every load so far has hit
a degrade path, because the slate is only current on the ET day it was
built. First sighting will be after a `slate-picks` run, on that same
day.

### Two Home defects found by looking at the live page, both now fixed

Neither was in the item. Both showed up only once real screenshots
existed, which is the argument for looking at the page rather than the
suite.

**1. THE THIRTEEN-HOUR DEAD ZONE.** slate-picks runs at 1, 5 and 7 PM ET
because probables don't exist before midday. So from midnight to 1 PM —
over half of every day — there is legitimately no MLB slate for today,
and Home's top card was saying *"the slate-picks job hasn't published
since"*: the sentence for a broken workflow, fired daily at a workflow
that is fine, pointing whoever read it at something green.

Same mistake this repo already made once, with the WNBA warning that
said "the nightly fetch may be failing" through the All-Star break. The
rule left behind: **a confident wrong diagnosis is worse than no
message.**

`slate_guard._not_built_yet()` now separates *not due yet* from *broken*.
It is deliberately narrow and fires only when all three hold: the league
has a known build hour (`_FIRST_BUILD_HOUR`, **MLB alone** — the absence
of the other three is the mechanism, not an oversight); that hour hasn't
come round yet in the league's own timezone; and what's on disk is
either nothing or **exactly yesterday's** slate. That last clause is
what stops this becoming "mute the warning when it's inconvenient" — a
three-day-old slate is a real outage at any hour and keeps shouting.

`_FIRST_BUILD_HOUR["mlb"] = 13` duplicates slate-picks' first cron
(`0 17 * * *` UTC). The duplication is deliberate — reading a workflow
file at request time to render a sentence would be worse — and
`test_slate_guard` now **pins the constant to the cron** and fails if
either moves without the other. A known one-hour hole under EST is
written down in the constant's comment rather than left to be
discovered.

**2. THE EMPTY STATE WASN'T A CARD.** The no-slate branch was
`st.caption(note)` — loose grey text floating above the chip rail with
no frame, at the top of the landing page. Honest words in a presentation
that reads as "something failed to load", and it's the state a reader
sees for most of the day. It's a proper card now, matching "Today's
board isn't published yet" further down the same page. No "build it
live" button, unlike that card: rule 5, Home makes zero network calls.

### Five negative controls, all confirmed red

After two tests shipped last session that passed without proving
anything (rules 25 and 26), every case here was verified by breaking the
code on purpose:

| mutation | caught by |
|---|---|
| give the other leagues a build hour | kbo/npb/wnba each get MLB's message |
| drop the "exactly yesterday" guard | 3-day-old slate stops being a fault |
| drop the hour check | 15:00 gets the gentle message |
| revert the branch entirely | 06:00 gets the outage message |
| move the cron, not the constant | the cron/constant pin |

One note on method: the first mutation initially failed via a `KeyError`
crash in an unrelated earlier test rather than via its own assertion —
an artifact of an inconsistent mutation, not a weak test. Re-run in the
realistic shape (all four leagues given an hour) it fails on the three
intended assertions by name.

### Verify, in order

1. `git pull`, run the suite. **76 files, FAILING: none** in the
   Codespace.
2. Load Home **before 1 PM ET** → "Tonight's MLB slate builds around
   1 PM ET…", inside a card, not floating.
3. Load Home **after a slate-picks run, same ET day** → the ranked card.
   **Nobody has seen this yet.** Check three games, a one-line reason
   above them naming the tier the sort used, and the lead game genuinely
   holding the biggest `edge_net` in `data/mlb/games.json`.
4. KBO and NPB chips unchanged.

---

## PICK UP HERE — state as of 2026-08-09

**Everything below the NEXT "PICK UP HERE" is background from 08-07 and
is still accurate. This block is what changed today.**

### ITEM C IS BUILT. It has never executed. Read the next paragraph.

The best-games hero card is shipped, tested and wired end to end, and
**not one line of the CI half has run in production.** Rule 22 exists
because of exactly this: `parse_homepage_schedule()` was correct and
tested and had no caller, and KBO died every run while 66 tests stayed
green. `_write_mlb_slate()` is a new function whose first real execution
will be a scheduled job. Read the slate-picks log before believing it.

**The near-miss, recorded because it is the same bug twice.** The slate
was first written to repo-root `data/mlb/` while `slate_guard` read only
`app/data/`. That is a green run, a log line saying the file was
written, and a card that never sees it. Worse: `app/data/` is
GITIGNORED and only arrives via the nightly release archive, and
slate-picks publishes no archive — so writing there would have left the
file on the Actions runner to die with the job.

The repo had already solved this and I nearly missed it.
`engines/calibration._repo_path()` documents the identical split:
Render checks out the whole repository, so repo-root `data/` resolves in
production, and `app/` is the service root, not the checkout root.
`slate_guard._read` now reads BOTH locations and prefers whichever
declares the later slate date — not first-wins, because on the day both
exist first-wins would pin the app to whichever path was checked first
and the staleness would be invisible.

### The pieces

- **`app/engines/best_games.py` (NEW).** The ranking, and nothing else.
  No streamlit, no network, no file reads — which is the whole reason it
  is an engine and not code inside the view: it can be tested headlessly.
- **`slate_guard`** gains `mlb` (Eastern; an MLB schedule day IS an
  Eastern day) and the two-location read above.
- **`calibration_picks._write_mlb_slate()`** runs FIRST in `main()`,
  before the pick builders, in its own try. A slate failure must not cost
  the picks and a pick failure must not cost the slate. Every number it
  writes comes from an engine the site already uses — weather_engine for
  the schedule, matchup_grades for the edge, park_factors, wind_engine.
  There is no second copy of any ranking logic.
- **`Home._render_best_games()`** at the very top of `render()`.
- **`tests/test_best_games.py` (NEW, #76).**

### The ranking, as decided, and one thing it cannot do yet

Strict tiers: **biggest modeled edge → highest projected run total →
biggest weather/park swing.** Closest matchup rejected — a coin flip is
the ABSENCE of a modeled opinion. Tiers, not a weighted composite: the
weights would be invented, and the card can always say why a game is
first in one true clause.

**TIER 2 NEVER FIRES AND THAT IS NOT A BUG.** `engines/run_total` needs
each team's runs scored and allowed per game; nothing on disk carries
those for MLB. So `proj_total` is deliberately never written, ranking
falls through to tier 3, and the tier is wired and tested so it lights up
the day the field exists — same posture as `announced_starters()` for
WNBA. **Do not substitute the O/U signal count for it.** That counts
signals toward Over; it is not a number of runs, and ranking by it would
be a different quantity wearing the decided label. If you want tier 2
live, the work is a team RS/RA source for MLB, and it is a new scraper
with a new failure mode — probe it first.

**MISSING IS NOT ZERO**, per tier. A game with no posted starters has no
edge; that is not an edge of zero and must not outrank a game measured at
zero, nor be treated as the worst game on the slate. A game missing only
the total still competes normally on edge and on swing.

The weather/park swing weights in `best_games` are **calibration
constants, not measurements** — judgements about how much each signal
moves a game, in one file, like `styles/stat_scales.py`. The score is an
ORDERING quantity used to break a tie and is never displayed; the card
names the signals that fired, because those are real.

### Three degrade paths, all exercised by hand

| on disk | card shows |
|---|---|
| nothing, or a past date | slate_guard's own sentence, naming the date |
| slate, no starters posted | "N games — starters not posted yet" |
| slate with signals | the ranked card |

The middle one earns its branch: it is what every morning looks like, and
ranking an unscored slate produces ALPHABETICAL ORDER WEARING THE COSTUME
OF A RANKING. `has_any_signal()` is the guard.

### Rules held

Rule 5 (Home makes zero network calls) — the card reads CI's file;
`test_best_games` fails on `requests`/`urlopen`/`httpx`/
`get_todays_games_with_weather` appearing in Home.py. Rule 4 (Home cannot
write `lc_sport_seg`) — the jump uses `_goto_sport` when the switcher is
not on MLB. Rule 10 and the design rule — the hero is forward-looking and
last night's graded outcome stays below it; the test asserts the ORDER of
the `_render_*` calls by parsing `render()`, because a substring search
cannot see order.

### TWO TESTS THAT PASSED WITHOUT PROVING ANYTHING

Both caught by breaking the code on purpose. Both are the same lesson.

**1. The alphabetical tiebreak was rescuing broken tiers.**
`rank_games` ends with a team-name tiebreak so the card does not reshuffle
between refreshes. When a tier stops discriminating the sort falls
through to it — and three of the six ranking fixtures were named such
that alphabetical produced the RIGHT answer anyway. Re-introducing the
exact bug the module exists to prevent (missing edge sorting as zero)
left every assertion green.

Fixed by naming every expected winner `z-...` and every loser `a-...`, so
a broken tier now falls through to alphabetical and puts the LOSER first.
**Seven negative controls now run**: missing-as-zero, each tier deleted,
tiers 1 and 2 swapped, unverified park factor read, hero moved below Last
night, `has_any_signal` forced true. All seven go red.

**2. A workflow assertion matched the COMMENT, not the command.**
`test_calibration_picks` asserts slate-picks commits `data/mlb/games.json`.
Deleting the path from the git-add left the test green — because the long
explanatory comment above the step still named the file. This repo puts a
paragraph above every tricky step, so any assertion about what a workflow
DOES has to strip comment lines first. `_commands_only()` now does.

That test also had to change for a legitimate reason: it pinned the exact
string `git status --porcelain -- data/calibration.json`, and moving two
paths into a shell variable broke the spelling while keeping the
property. Rule 11. It now asserts git status / never git diff / both
paths present, and four controls confirm each clause bites.

### The rest of the batch (see the 08-07 block for context)

- **KBO was publishing a leaderboard to nobody.**
  `_render_batting_leaders()` was written in full and never called, while
  `kbo_precompute` wrote `batters.json` every run. Rule 20's third
  disguise: computed-never-rendered, written-never-called, and now
  **rendered-never-invoked**. `tests/test_no_dead_renderers.py` (NEW,
  #75) fails on any `_render_*` in a view without a call site in its own
  file. Exact rather than heuristic because nothing imports a view.
- **WNBA live tracking was a STARTING problem, not a fetching one.**
  `st.fragment` fixes `run_every` at creation and a fragment rerun does
  not re-run module scope, so the poll interval was decided from a
  snapshot taken before the fragment ever ran. Open the board at 6:55 for
  a 7:00 tip and it polled NEVER. The condition is now "is there a game
  tonight that has not finished". Also: `_render_slate` already returned
  the right answer and the caller threw it away while recomputing it.
- **WNBA context columns carry their window** — `FTA szn`, `TO szn`,
  `STL szn`, `BLK szn`. Zero columns added. `l5_fta`/`l10_fta`/`l5_to`/
  `l10_to` are published nightly and still read by nothing; switching to
  them is data-free and is HIS call, not a cleanup.
- `roster.py`'s `utcnow()` → ET, the only naive datetime in the repo.
- `sport_switcher()`'s docstring said "Only MLB is wired to real data",
  contradicting the caption twenty lines below it.
- `staleness_note` named the wrong job for MLB ("the nightly build"),
  which would have sent you to debug `nightly-data` while `slate-picks`
  was the one down.
- Four unused imports.

### A WRONG CALL IN THIS SESSION, recorded so it isn't repeated

A crude sweep for "fields a pipeline writes that no view reads" reported
KBO's **home/away splits and H2H run averages as unrendered.** Both are
rendered fine. The sweep collected dict-key literals and grepped `app/`,
so it could not follow keys consumed inside the same function
(`home_w`/`away_l` build `home_record`, which KBO.py draws) or keys
renamed at the publish boundary (`a_avg_runs` ships as `away_avg_runs`).
It also flagged `l15_pra`, which `player_of_the_day` builds with an
f-string. **A key-literal grep cannot see a rename or a dynamic access**,
and dynamic access is the normal idiom here for anything windowed.

What survived verification: `quality_starts`, `earned_runs`, `risp_avg`,
`high_total`, `low_total` are genuinely published and read by nothing.
Leaf stat fields, not features.

### Do these in order

1. Upload the batch, `git pull`, run the suite. Expect **`TESTS:76`**
   with the same five streamlit-only failures.
2. **Watch the next `slate-picks` run and read one line:**
   `mlb slate: wrote N game(s) for <date> (M with a modeled edge, ...)`.
   `M` will be 0 on an early run and that is expected — probables post
   one to three hours before first pitch. If the line is ABSENT, the
   slate step failed and the message above it says why.
3. **Then confirm the commit landed** — `data/mlb/games.json` must appear
   in the repo. If the log says it wrote the file and the repo has no such
   file, the commit step is the problem, not the writer. That distinction
   is the whole reason step 2 and step 3 are separate.
4. **Open Home after a slate-picks run.** Before probables: "N games —
   starters not posted yet". After: the ranked card.
5. **Open the WNBA board BEFORE a tipoff and leave it.** Scores should
   start moving within ~75s with no reload.
6. KBO board should show a **Batting Leaders** card.
7. Still watch the KBO coverage line on a day KBO actually plays (V2).

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

### Why KBO, NPB and Home missed the restyle — 2026-08-07

**Three selectors draw cards, and only one of them was flattened.**

- `div[class*="st-key-card_"]` — container cards, what the MLB views use.
  Flattened first.
- `.pf-card` — raw HTML from `card_open()`/`card_close()`. **This is what
  KBO and NPB render**, so both international boards kept the previous
  generation of the design while every other page moved on.
- A local override in `Home.py` for `st-key-card_home_`, which outlived
  the global rule it was overriding — the home page was the only page
  still drawing gradients and shadows.

Nothing in the code said the three had to agree, and they do: it is the
same object to a reader. `tests/test_control_language.py` now asserts
none of them paints a gradient or a shadow, wherever it is defined,
including the copy inside Home.py.

**What survived on Home, deliberately:** the coloured top rule and the
hover lift. Those carry information — which board is live, and that the
card is clickable. The fill and the shadow said nothing.

**Expanders joined the control language.** "Every pick from last night",
"Weak spots", the glossary — the one control that opens something, and
still a filled grey slab with a hard border while everything else had
gone quiet-until-active. Now a wide button: transparent, faint wash on
hover, hairlines above and below, 44px target, and the header takes the
accent when open. The open state keys off `details[open]` — the
browser's own flag — so it cannot drift with a Streamlit release the way
an internal class name would (rule 9).

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
ls tests/*.py | wc -l                                     # 76
python tests/test_no_dead_renderers.py | tail -1          # both leaderboards draw
python tests/test_best_games.py | tail -1                 # Home makes no network calls
grep -c _render_batting_leaders app/views/KBO.py          # 3 = def + 2 call sites
grep -c _could_go_live app/views/WNBA.py                  # 2 = live poll starts pre-tip
grep -c utcnow app/engines/roster.py                      # 0 = no naive datetimes left
grep -c \'"mlb"\' app/engines/slate_guard.py               # 2 = item C UNBLOCKED
grep -c _write_mlb_slate calibration_picks.py             # 2 = defined AND called
grep -c _render_best_games app/views/Home.py              # 2 = def + call
grep -c _not_built_yet app/engines/slate_guard.py         # 2 = def + call
grep -c 'st.caption(note)' app/views/Home.py              # 1 = the comment only
ls data/mlb/games.json                                    # appears after a slate-picks run
grep -c void_risk kbo_precompute.py                       # 3  = V3 in
grep -c void_reason app/views/KBO.py                      # 3  = board shows it
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
# (item C is now BUILT — see the 08-09 block. The two greps above
#  replace these; they said 0 when C was blocked.)
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
   starters"; `test_kbo_homepage_starters` depends on it. (This used to
   name `test_kbo_heat_risk`, which is DELETED — see O1-original.)
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

### O1. CLOSED, and it uncovered a worse bug. See V3 below.

### V3. A CANCELLATION WAS ONLY READ FOR GAMES ALREADY PLAYED.
`parse_week`'s status block sat behind `if gdate < today_str:`, so a
game called off for TODAY or any future date still shipped as
`scheduled`. Measured on the live page 2026-08-07: mykbostats listed
**every KBO game through 08-09 as Canceled** in a heat wave, and the
board would have shown all fifteen as on. That is the void problem
itself — the board saying a game is playable when the source says it is
not — and it is the worst direction to be wrong in on a betting site.

NPB never had it: `<div class="cancel">` is checked with no date gate.
KBO was the odd one out, which is rule 21 in its quiet form.

Fixed. The cancellation check now runs on every date. `FINAL_PAT` stays
past-only on purpose (a future game has no score to parse), and a
postponed game can no longer also be graded final.

Two new fields ship on every KBO slate row, deliberately separate
because they answer different questions and a game never has both:

- **`void_reason`** — why a called game was called (`Extreme Heat`).
  Absent on a bare `Canceled`, which is a real difference in the source
  and not a gap to fill in.
- **`void_risk`** — the site's forward-looking warning on a game that
  is STILL ON. Three phrasings measured: `Chance of Heat Cancellation`,
  `Chance of Rainout`, `Forecast Uncertain`.

This is what O1 was asking for, taken off the homepage (today only) and
onto the schedule page (the whole week). Quoted verbatim, never mapped
onto our own scale — Open-Meteo gives a temperature against
`HEAT_CANCEL_C`, which is still unverified; this is the site DECIDING.
Both render on the KBO board ahead of the measured badge.

`tests/test_kbo_void_signals.py` pins the separation both ways: the
warning must never be read as a cancellation, and a decision must never
be read as a warning. Negative controls run — the test throws on the
pre-fix tree, and fails if the risk pattern is widened to overlap
`Cancel`.

**NPB parity is OWED here and is not done.** npb.jp has not been
checked for a forward-looking warning of its own. Until someone looks,
KBO shows a signal NPB does not, and a missing badge is unreadable —
it means "no risk" on one board and "not measured" on the other. Check
npb.jp's schedule markup before building anything else on this.

**`fetch_homepage_conditions()` — RESOLVED 2026-08-10, deleted.** See
O1-original below for the reasoning and for where its test's properties
went.

### O1-original — CLOSED 2026-08-10. Deleted, and here is the why.
Open across four sessions as "delete it and say why, or keep it as a
cross-check and wire it — do not leave it neither." Deleted.

The argument FOR wiring it was real and is worth recording, because it
is why this sat open so long: Open-Meteo only gives a temperature
against `HEAT_CANCEL_C`, and that threshold is still UNVERIFIED, whereas
the site's own warning is the *league's actual judgement*, published in
advance. That is a thing our forecast genuinely cannot reproduce.

It was answered by V3. `parse_week()` now reads `VOID_RISK_PAT` off the
SCHEDULE page — the same league judgement, quoted verbatim, for THE
WHOLE WEEK instead of today only. So the signal was never lost; it was
already being read better, from a page already fetched. Wiring the
orphan would have meant two answers to one question from two requests,
with no rule for which wins.

Deleted with it: `parse_homepage_conditions()`, `HEAT_RISK_PAT`,
`TEMP_PAT`, and `tests/test_kbo_heat_risk.py` (**76 -> 75 test files**;
it tested only those two functions, so keeping it meant keeping dead
code to keep a test green).

**Every property that test held was checked for a home before deleting,
not assumed.** All but one were already covered — warning-vs-decision by
`test_kbo_void_signals` (and against the LIVE reader, which is strictly
better), and the leak/absent/independence checks by
`test_kbo_homepage_starters`. The one exception, "the two readers are
separate functions", was MOVED into `test_kbo_homepage_starters` along
with a new check that the deleted readers stay deleted. Deleting a test
that guards a real property, because the code it happened to name went
away, is how a guarantee evaporates without anyone deciding to drop it.

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

### C. Best-games hero card — BUILT 2026-08-09, NOT YET EXECUTED.
Everything this item asked for is on disk: `slate_guard` knows `mlb`,
`calibration_picks._write_mlb_slate()` writes the slate at 1/5/7 PM ET,
`engines/best_games.py` ranks it, Home leads with it and degrades three
ways. Details, the near-miss on WHERE the file goes, and the two tests
that passed without proving anything are all in the 08-09 block at the
top of this file.

**What is left is verification, not building.** The CI half has never
run. Read the `mlb slate: wrote N game(s)` line in the next slate-picks
log, then confirm `data/mlb/games.json` actually appears in the repo —
those are two separate failures and step 2 and step 3 of the top block
keep them apart on purpose.

**The one piece genuinely still missing is TIER 2.** `proj_total` is
never written because `engines/run_total` needs per-team runs scored and
allowed and nothing on disk carries them for MLB. The tier is wired and
tested and fires the day the field exists. Building it means a new MLB
team RS/RA source — a new scraper with a new failure mode, so probe it
before writing a parser. **Do not** substitute the O/U signal count:
that counts signals toward Over and is not a number of runs.

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

### E3. KBO source migration — probe DELIVERED, not yet run.
**Decided 08-10: mykbostats is going.** `kbo_probables_probe.py` is the
probe this section asked for. Run it from Actions and read the verdict
line; if no endpoint exists, ship KBO without probables and label the
board. See the top block.

### E3 (original note).
mykbostats clause 6 forbids betting use, so the rest should move to
`eng.koreabaseball.com`. `DailySchedule.aspx` returns a whole month
(98KB, ~130 games, a POSTPONED column) in one GET. **Probables are the
blocker** — the Korean schedule serves 0 occurrences of 선발/투수/예고,
drawn client-side. One probe to find the XHR endpoint settles it. Until
then: keep mykbostats for probables only, or drop them.

### D. Daily cold start — CLOSED 08-10, decided against.
Dome flags STAY in `intl_venues.py`. Reasoning in the top block: it
would break the "unknown is not open" guarantee, make a fallback depend
on the network its caller fell back from, and buy nothing on a table
that changes about once a decade. **Do not re-propose.** The cold-start
problem itself, if it still bites, needs a different fix.

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
25. **NEW — a ranking test can pass on its tiebreak.** `rank_games`
    ends with an alphabetical tiebreak so the card does not reshuffle
    between refreshes. Break a tier and the sort falls through to it —
    and three of six fixtures were named so that alphabetical produced
    the RIGHT answer anyway. Re-introducing the exact bug the module
    exists to prevent left every assertion green. **Name the expected
    winner so it loses the tiebreak**, then break the tier on purpose
    and watch the case go red. This generalises: whenever a sort has a
    fallback, a test of the primary key must be constructed so the
    fallback cannot supply the same answer.
27. **NEW — a test must stub every path the code under test reads.**
    `slate_guard._read()` deliberately reads TWO locations and keeps the
    later-dated one. `test_slate_guard` stubbed only `app/data/`, which
    was invisible for months because the repo-root path was empty. The
    day `calibration_picks` wrote a real dated slate there, that file
    out-dated every fixture, every MLB case returned ok, and five
    load-bearing assertions passed without ever being reached. **The
    test was defeated by the feature it was written to protect.** A
    fixture covering one of two read paths covers neither. Sibling of
    rule 25: both are a test going green for a reason that has nothing
    to do with the thing it asserts.

---
26. **NEW — an assertion about a workflow must read what it RUNS.**
    A test asserting slate-picks commits `data/mlb/games.json` stayed
    green after the path was deleted from the git-add, because the
    explanatory comment above the step still named the file. This repo
    puts a paragraph above every tricky step, so a substring search over
    a workflow matches prose far more often than code. Strip comment
    lines first. Sibling of rule 17: a substring is not an element, and
    a comment is not a command.

---

## The repo

`iamjpescobar/honestygfymodel` — Streamlit sports betting analytics app,
**Los Cappers**. Renders on Render. MLB, WNBA, KBO, NPB.

- Entrypoint is **`app/app.py`**, not `app.py`.
- Pages in **`app/views/`**, deliberately NOT `pages/` — Streamlit
  auto-registers `pages/` and would expose every page pre-auth.
- Engines in `app/engines/`. Theme in `app/styles/kc_theme.py`.
- Tests in `tests/` — **79 files, plain scripts, not pytest.**
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
