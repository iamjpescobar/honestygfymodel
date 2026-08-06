# Los Cappers — session handoff

Read RULES before proposing any change; every one was learned by
breaking something.

**Rewritten 2026-08-06 (second audit of the day). The previous version
of this file was itself corrupt — a dead copy of item V was left
dangling under the pitcher-H2H section, describing as broken something
the section twenty lines above described as fixed. Verify before you
build; the block below is the whole point of this document.**

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
ls tests/*.py | wc -l                                     # 67
python tests/test_return_arity.py | tail -1               # FAILING: none
grep -c fetch_homepage_schedule kbo_precompute.py         # 2  = defined AND called
grep -cE '^\s+_hp, _hs =' kbo_precompute.py               # 0  = the crash is gone
                                                          #      (anchored: the docstring
                                                          #       quotes the broken line)
wc -l wnba_precompute.py                                  # 1085 = comments restored
grep -c intl_weather npb_precompute.py                    # >0 = NPB weather WIRED
grep -c _weather_badges app/views/KBO.py                  # 2  = KBO shows weather
grep -c _weather_badges app/views/NPB.py                  # 2  = NPB shows weather
grep -c '"mlb"' app/engines/slate_guard.py                # 0  = item C still blocked
ls data/                                                  # C unblocks when mlb/ appears
grep -c 'class="venue"' kbo_precompute.py                 # 2  = schedule-page regex
                                                          #      still dead; TODAY is
                                                          #      repaired from the homepage
ls .github/workflows/ | wc -l                             # 10
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
   starters"; `test_kbo_heat_risk` depends on it.
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

### V1. CONFIRM THE REPAIR ACTUALLY RUNS. Do this first, it is one run.
Everything under item V is written and tested but has **executed zero
times in production.** Push the fix, then Actions → "Late slate refresh
(KBO, NPB, WNBA)" → Run workflow, and read three lines:

- `KBO: homepage — N of M game cards carried a time and venue` — new
  line, from the function that was missing.
- `KBO: repaired N venue and N start-time fields from the homepage` —
  the `TBD · TBD KST / TBD ET` fix landing.
- no `Traceback` in the KBO step, and the job green.

Then reload KBO and Sync latest: real venue and first-pitch time in the
header, like the NPB board already shows. **Until that run is green,
treat every item below it as untested.**

### V2. KBO venue + time for FUTURE dates — no longer blocked on a probe.
Today's slate is repaired from the homepage. Tomorrow onward still
shows `TBD` because `parse_week()` keys on the pre-rewrite markup:

```python
venue = re.search(r'<div class="venue">\s*(.*?)\s*</div>', inner, re.S)
t     = re.search(r'datetime="([0-9T:+.Z-]+)"', inner)
```

**A live fetch of the schedule page on 2026-08-06 settled the probe
question**: the v3 schedule page carries the whole week in plain card
text, same shape as the homepage —

```
Friday August 7
  Lotte Giants KT Wiz 34° 6:30pm Suwon      Chance of Heat Cancellation
  SSG Landers NC Dinos 32° 6:30pm Changwon  Forecast Uncertain
Saturday August 8
  Doosan Bears Samsung Lions 6:00pm Daegu
```

So the work is: read time and venue out of the schedule page's card
text the way `parse_homepage_schedule()` reads the homepage's, keyed on
the product and not the styling (rule 18). **Write it against a live
fetch, not against the block quoted above** — that text is a
transcription from a chat window and rule 15 exists because
transcriptions have already cost this repo an outage. Note the date
headings are their own rows, so the parser has to carry a current date
down the list rather than expect one per card.

Also visible in that same text: **`Forecast Uncertain`**, a third
weather state alongside `Chance of Heat Cancellation`. Worth reading,
not worth guessing at.

### F2. KBO probables — still ZERO live confirmations.
`parse_homepage_starters()` is in and tested. Every confirming run so
far has measured 0:

- 06:36 KST — twelve hours early, on a heat-canceled slate.
- 23:04 KST (run 84386218583) — `0 of 15 game cards`, after the day's
  games were over.
- 13:13 KST — every card had a time and venue, **not one had a
  starter**.

None of those is evidence either way. **Watch the 18:20 KST
`intl-late-refresh` log on a day that is actually played.** N > 0 means
probables are back after weeks blind. N = 0 there means the line moved
again — re-probe, do not widen the regex. Note that the crash above
meant the 18:20 run never completed at all, so this has had fewer real
chances than it looks.

### O1. `fetch_homepage_conditions()` is orphaned — decide, don't delete.
It parses the site's own **`Chance of Heat Cancellation`** warning off
the homepage and nothing calls it. Weather moved to Open-Meteo, which
was right — but Open-Meteo can only give a temperature against
`HEAT_CANCEL_C`, and that threshold is UNVERIFIED (below). The site's
warning is the *league's actual judgement*, published in advance, and
it is the one thing our own forecast cannot reproduce. Either wire it
back in as a second, clearly-labelled signal or delete it and say why.
Right now it is neither.

### C. Best-games hero card — BLOCKED on recording an MLB slate.
Ranking **DECIDED**: biggest modeled edge → highest projected run total
→ weather/park swing. Closest-matchup rejected. Goes at the **top of
Home** (rule 10 — the hero must be forward-looking). Blocked on: no
`data/mlb/games.json`, `slate_guard._LEAGUES` has `wnba`/`kbo`/`npb`
and no `mlb`. Needs `calibration_picks.py` (already runs 1/5/7 PM ET
with network) extended to write an MLB slate in the shape `slate_guard`
reads. Home must degrade gracefully until CI populates it. **Biggest
remaining product item.**

### PITCHER H2H — NOT BUILDABLE FROM THE CURRENT SOURCES.
Requested: starters always shown, with season data and head-to-head
against the opposing team. First two are in hand; **the third has no
data behind it.**

- KBO season lines come from `eng.koreabaseball.com` ERA/WHIP
  **leaderboards**, which list QUALIFIED pitchers only — the live run
  fetched 20 for a 10-team league, so most starters have no line at
  all. That is a coverage gap, not a bug.
- NPB fetches 59 from three npb.jp leaderboards, same shape. Run
  84386218583 shows the gap on the board: across five games, only one
  of ten listed starters had season stats attached.
- **Neither source gives per-start logs.** Both are season aggregates,
  so "this pitcher vs this opponent" cannot be computed from anything
  currently fetched.

What exists today is TEAM h2h (`h2h()` in both pipelines), which is
what the cards already show.

To build pitcher-vs-team you need a per-start game log per pitcher:
KBO would need the official site's player detail pages, NPB the
equivalent on npb.jp. **Probe one player page per league first** and
confirm the log is server-rendered before designing anything — that is
the lesson from four probes on the starters question. A probe script
for this was being written when the last session was cut off; it is
**not in the repo**, so it was never committed. Start it fresh.

### E3. KBO source migration — blocked on one probe.
mykbostats clause 6 forbids betting use, so the rest should move to
`eng.koreabaseball.com`. `DailySchedule.aspx` returns a whole month
(98KB, ~130 games, a POSTPONED column) in one GET. **Probables are the
blocker** — the Korean schedule serves 0 occurrences of 선발/투수/예고,
drawn client-side. One probe to find the XHR endpoint settles it. Until
then: keep mykbostats for probables only, or drop them.

### D. Daily cold start — his call needed.
Dome flags out of `intl_venues.py` into published data so the late
refresh stops triggering a Render deploy. Not started.

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

---

## The repo

`iamjpescobar/honestygfymodel` — Streamlit sports betting analytics app,
**Los Cappers**. Renders on Render. MLB, WNBA, KBO, NPB.

- Entrypoint is **`app/app.py`**, not `app.py`.
- Pages in **`app/views/`**, deliberately NOT `pages/` — Streamlit
  auto-registers `pages/` and would expose every page pre-auth.
- Engines in `app/engines/`. Theme in `app/styles/kc_theme.py`.
- Tests in `tests/` — **67 files, plain scripts, not pytest.**
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
