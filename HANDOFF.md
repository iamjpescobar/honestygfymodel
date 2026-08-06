# Los Cappers — session handoff

Read RULES before proposing any change; every one was learned by
breaking something.

**This file was rewritten after an audit found several PENDING items
were already shipped. Verify before you build — the block below is the
whole point of this document.**

---

## READ THIS BEFORE YOU ACT ON ANYTHING BELOW

A stale handoff that gets trusted is worse than no handoff: it sends a
session to redo something already done. This file is a summary. **The
repo is the truth.**

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
wc -l wnba_precompute.py                                  # 1085 = comments restored
grep -c fetch_homepage_starters kbo_precompute.py         # 2  = KBO probables fix in
grep -c intl_weather npb_precompute.py                    # >0 = NPB weather WIRED
grep -c _weather_badges app/views/NPB.py                  # 2  = NPB shows weather
grep -c _weather_badges app/views/KBO.py                  # 2  = KBO shows weather
grep -c '"mlb"' app/engines/slate_guard.py                # 0  = item C still blocked
ls data/                                                  # C unblocks when mlb/ appears
grep -c 'class="venue"' kbo_precompute.py                 # >0 = venue regex STILL broken
ls .github/workflows/ | wc -l                             # 10
ls tests/*.py | wc -l                                     # 66
```

**Update this file in the same commit that ships the work.**

---

## AUDIT, 2026-08-06 — what the last handoff got wrong

Checked on disk, not believed. Items the previous version listed as
PENDING that were **already done**:

- **Admin credential (item 0).** Done and more serious than the item
  said. The password was fine, but the live `cookie: key:` was byte
  identical to the one committed in `app/auth_config.example.yaml` —
  anyone holding it could forge a session for any user including admin,
  no password needed. Rotated; the example now carries obvious
  placeholders.
- **Weather engine.** `app/engines/intl_weather.py` exists with
  Open-Meteo, coordinates for 9 KBO and 12 NPB parks, `HEAT_CANCEL_C`,
  CC BY attribution, and `venue_for_game()` venue fallback.
- **KBO heat flag, licensing review, source migration scoping,
  `concurrency:` guard, WNBA mid-day recovery** — all shipped.

Items that were **real, and are fixed in this batch** — see below.

---

## FIXED THIS SESSION

### 1. The weather was computed and never shown.
`kbo_precompute` attached `temp_c`, `max_temp_c`, `precip_prob` and
`heat_risk` to every game. **No view rendered any of it.** `KBO.py`
imported `ATTRIBUTION` and printed the CC BY credit for figures that
never appeared on screen. So the reason he was still catching
postponed games was not a missing feature — it was a feature that
stopped one step short of the page.

`weather_badges()` now lives in `intl_weather.py` and both boards
render through it. Heat risk (KBO) quotes the day's max, rain risk
fires at 50%, MONITOR at 25–49%, and a roofed park suppresses the rain
figure entirely and says `ROOFED` instead — `intl_venues.roof()` owns
that judgement and it is not duplicated. **Nothing known renders
nothing**, never a `0%` or an em dash that reads like a measurement.

### 2. NPB had no weather at all.
The engine carried `NPB_COORDS` for all twelve parks from the day it
was written and **nothing ever called them.** `npb_precompute` now
forecasts its slate the same way KBO does, one call per date, and
ships the same four keys.

Standing instruction, now structural rather than remembered: *every
change made to KBO is made to NPB.* Both markets get bet together, so a
badge on one board and not the other is worse than no badge — the
reader cannot tell "no risk" from "not measured".
`tests/test_intl_weather_parity.py` fails if the two drift.

### 3. NPB venue names silently failed to resolve.
npb.jp renders some two-character venues spaced out — Yokohama arrives
as `横 浜`, not `横浜` — so `STADIUMS.get(jp.strip())` missed and
`_en_stadium()` returned the raw Japanese. It looked harmless because
the string still rendered (the screenshot showed `横 浜 · 17:45 JST`),
but that value is not a key in `NPB_COORDS`, so **every Yokohama game
would have forecast nothing** the moment weather was wired. Fixed by
collapsing internal whitespace before the lookup, plus `NPB_HOME_VENUE`
as a backstop. The parity test asserts every club resolves to real
coordinates.

---

## OPEN — in priority order

### V. THE KBO VENUE AND TIME REGEXES ARE STILL BROKEN. Do this first.
The board currently reads **`TBD · TBD KST / TBD ET`** on every game.
`kbo_precompute.parse_week()` still keys on the pre-rewrite markup:

```python
venue = re.search(r'<div class="venue">\s*(.*?)\s*</div>', inner, re.S)
t     = re.search(r'datetime="([0-9T:+.Z-]+)"', inner)
```

Both come off the mykbostats schedule page, and the v3 rewrite that
killed `away-starter` killed these too — **rule 18, same file, two more
places.** Weather still works (the club fallback covers it), but the
displayed venue and first-pitch time are gone, and anything else
reading `stadium` is degraded.

**The homepage already carries both**, in the same card text the
starters come from: `Hanwha Eagles Samsung Lions 31° 6:30pm Daegu`.
Extending `parse_homepage_starters()` to take time and venue fixes
TODAY's slate — the one that matters for tonight's bets — without a new
request. Future dates need the schedule page's new markup, which needs
one probe. **Do not widen the old regex on a guess.**

### F2. KBO probables — fix shipped, ONE live confirmation outstanding.
`parse_homepage_starters()` is in and tested. The confirming run landed
at 06:36 KST — twelve hours before first pitch, on a heat-canceled
slate — so it measured 0 and proved nothing. **Watch the 18:20 KST
`intl-late-refresh` log:** `KBO: homepage — N of M game cards carried a
Starters line`. N > 0 means probables are back after weeks blind. N = 0
on a slate that actually gets played means the line moved again —
re-probe, do not widen the regex.

### 0b. Grep for other committed secrets.
The cookie-key finding was luck. Nobody has swept the rest:
`grep -rn "key:\|token\|secret\|password" --include=*.yaml --include=*.toml .`
One command, never run.

### C. Best-games hero card — BLOCKED on recording an MLB slate.
Ranking **DECIDED**: biggest modeled edge → highest projected run total
→ weather/park swing. Closest-matchup rejected. Goes at the **top of
Home** (rule 10 — the hero must be forward-looking). Blocked on: no
`data/mlb/games.json`, `slate_guard._LEAGUES` has no `mlb`. Needs
`calibration_picks.py` (already runs 1/5/7 PM ET with network) extended
to write an MLB slate in the shape `slate_guard` reads. Home must
degrade gracefully until CI populates it. **Biggest remaining product
item.**

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
it. **Do not quietly tune the number without recording why.**

### Smaller
- `likely_starters` double-docstring — merge when that file is open.
- Unread terms for Baseball Savant and npb.jp (see SOURCES section in
  git history of this file).
- KBO probables cover **TODAY only** — the homepage has no future
  slate. Not a bug.
- News section: pushed back on twice (rule 5 — Home can't fetch).

### CLOSED — do not reopen
- **WNBA starters.** ESPN publishes no `today_starter`;
  `stats.wnba.com` hangs on datacenter ranges and Render is one. The
  inference says LIKELY. `announced_starters()` exists, so a real
  source would light it up automatically. **Needs a new source, not
  another attempt.**

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
20. **NEW — a computed field nobody renders is not a feature.** The
    weather pipeline was complete and correct for days while every
    board showed nothing, and the licence credit was printed for data
    that never appeared. When wiring a signal, follow it to the pixel.
21. **NEW — parity between KBO and NPB is structural, not
    remembered.** Shared logic goes in an engine both views import; a
    test asserts neither hardcodes its own copy. A signal on one board
    and not the other is unreadable.

---

## The repo

`iamjpescobar/honestygfymodel` — Streamlit sports betting analytics app,
**Los Cappers**. Renders on Render. MLB, WNBA, KBO, NPB.

- Entrypoint is **`app/app.py`**, not `app.py`.
- Pages in **`app/views/`**, deliberately NOT `pages/` — Streamlit
  auto-registers `pages/` and would expose every page pre-auth.
- Engines in `app/engines/`. Theme in `app/styles/kc_theme.py`.
- Tests in `tests/` — **66 files, plain scripts, not pytest.**
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
  it audited from scratch. That is how this audit happened. Keep doing
  it.
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
  undercount of site chrome and the true figure was zero.
- When you get something wrong, say so plainly and move on.
- Don't build something you can't verify.
