# Los Cappers — session handoff

Paste this as your first message in a new session. Read RULES before
proposing any change; every one was learned by breaking something.

**State as of Aug 5, 11:51 AM ET: the roster/injury fix and the
test-gate fix are committed and verified ON DISK. `git pull`
fast-forwarded `cb3530c..3989bb0` and the suite reported
`FAILING: none` across all 60 tests. The nightly's test gate is
un-blocked.**

---

## Right now — do this first

**The WNBA slate has been missing from the published archive. Root
cause found and fixed — see item 18. This is the priority.**

Five files are attached. **All five are repo files:**

- `wnba_precompute.py` → repo root (full replacement) — **the outage fix**
- `test_wnba_boxscore_parse.py` → `tests/` (new)
- `wnba_props.py` → `app/engines/wnba_props.py` (full replacement)
- `test_wnba_injury_gate.py` → `tests/` (new)
- `nightly-data.yml` → `.github/workflows/nightly-data.yml`

The two big ones (`wnba_precompute.py` ~815 lines, `wnba_props.py` ~694)
go in by **upload**, not paste. The three short ones are fine in the web
file editor. Then:

```bash
cd /workspaces/honestygfymodel
git pull
python -m py_compile wnba_precompute.py app/engines/wnba_props.py \
  tests/test_wnba_boxscore_parse.py tests/test_wnba_injury_gate.py
python tests/test_wnba_boxscore_parse.py
python tests/test_wnba_injury_gate.py
fails=""
for t in tests/*.py; do python "$t" >/dev/null 2>&1 || fails="$fails $(basename $t)"; done
echo "FAILING:${fails:- none}"
```

Expected: `FAILING: none` across **62** tests. Then push and run the
nightly. Watch the **Fetch WNBA slate** step — it should print
`[roster] team N: X players...` lines and a parsed-games count, NOT
`WNBA fetch failed - continuing without it`. Then the **Verify the
archive** step should print `present  data/wnba/games.json`.

### Why the test-gate fix was urgent, not cosmetic

`tests/test_wnba_today.py` was **failing on `main`**, and the nightly's
`Run tests` step is a hard gate:

> `::error::Tests failed - refusing to fetch data or publish an archive.`

That step runs BEFORE the fetch and before `calibration_pipeline.py`.
So while that test was red: no Statcast fetch, no `nightly-data`
release asset, no calibration grading, no Render redeploy from fresh
data. **The whole nightly was down, silently, on a green-looking repo.**
That is almost certainly why the WNBA picks were still showing ungraded
— that symptom is *consistent with* this cause, but the confirmation to
run is: open Actions → nightly-data → find the first red run and check
whether the red step is `Run tests`. That also dates when it broke.

### What was actually wrong

The test was asserting the *spelling of a line*, not a behaviour:

```python
cap = re.search(r'if p\["gp"\] >= 3\]\[:(\d+)\]', build)
assert cap, "roster cap not found"
```

It demanded a build-time roster cap of at least 12. The cap has since
been removed **entirely** — `picks` is now built by walking the team's
full ESPN roster (`for pid, info in _roster.items()`), with the
`gp >= 3` filter surviving only as a fallback for when the roster fetch
fails. So the code got *better* than the test's requirement, and the
regex could only ever fail from then on.

The replacement asserts the property instead: the build must walk the
roster, and nothing may slice the pick list back down. Negative control
run — re-inserting `picks = picks[:9]` makes the new test fail with the
right message, so it still catches the regression it was written for.

---

## What is verified working (checked on disk this session)

- **Roster/injury fix is IN and correct.** `fetch_team_roster()` in
  `wnba_precompute.py` keeps `jersey`, `roster_status`,
  `injury_status`, `injury_date`, `exp` (lines ~243–303). Slate rows
  carry all five through (~lines 757–761). `app/views/WNBA.py` is 960
  lines and its Status column reads, in order: `today_status` →
  `injury_status` → `OUT {days}d` (lines 822–825). No `starter` field
  is read off the roster.
- `tests/test_wnba_roster_status.py` passes: *"reported roster status
  reaches the slate and outranks the guess"*.
- `python -m compileall` clean across the entire repo — no syntax
  damage anywhere, so the corruption from two sessions ago is fully
  behind us.
- 59 of 60 tests were passing before the fix above; 60 of 60 after.

## Findings from this session's read-through (not yet acted on)

1. **`likely_starters` double-docstring.** Two consecutive string
   literals open the function; the first becomes the docstring and the
   second is a no-op expression statement. Harmless, worth merging.
2. **Item A is genuinely not built.** `wnba_props.likely_starters` is
   still named that, and `WNBA.py` still prints a flat `START` in the
   Role column. The `announced` branch inside `likely_starters` keys off
   `today_starter is True`, which the roster probe confirmed ESPN never
   publishes for the WNBA — so that branch is dead in practice and every
   `START` badge on the site today is the minutes inference wearing a
   confident label.
3. **Item C still blocked exactly as described.** `data/` contains only
   `calibration.json`; `slate_guard._LEAGUES` has `wnba`/`kbo`/`npb`
   and no `mlb`.

---

## The repo

`iamjpescobar/honestygfymodel` — Streamlit sports betting analytics app,
branded **Los Cappers**. Deploys on Render. MLB, WNBA, KBO, NPB.

- Entrypoint is **`app/app.py`**, not `app.py`.
- Pages in **`app/views/`**, deliberately NOT `pages/` — Streamlit
  auto-registers `pages/` and would expose every page pre-auth.
- Engines in `app/engines/` (46 modules, all live, including
  `espn_wnba.py`). Theme and design tokens in `app/styles/kc_theme.py`.
- Tests in `tests/` — **60 files, plain scripts, not pytest.** CI runs
  `python tests/<file>.py` and checks exit codes.
- Data comes off disk. The nightly publishes a GitHub release
  (`nightly-data` tag, `statcast_data.tar.gz`); `app/fetch_data.py`
  pulls it at Render build time.
- `requirements.txt` fully pinned, including transitives.

Run the suite:

```bash
cd /workspaces/honestygfymodel
fails=""
for t in tests/*.py; do python "$t" >/dev/null 2>&1 || fails="$fails $(basename $t)"; done
echo "FAILING:${fails:- none}"
```

Run the app:

```bash
python app/fetch_data.py
streamlit run app/app.py --server.enableCORS false --server.enableXsrfProtection false
```

---

## How he works

- **iPad, GitHub Codespaces in Safari.** No local machine. Screenshots
  only — can't copy text out of the terminal. Uploading a file into
  the Codespace is the most reliable way to deliver anything long.
- **Anything longer than a short edit gets delivered as an uploaded
  file, never pasted as chat text.**
- He can hand a new session the **repo zip plus this handoff** and have
  it audited from scratch — that's how this session found the red test.
  It works; keep doing it.
- Commit messages go through `git commit -F- <<'MSG'` in the terminal
  (GitHub web UI URL-encodes the commit box).
- GitHub web **"Upload files" flattens folders into the repo root** —
  never use it for this repo. The web **file editor** (the pencil on an
  existing file) is different and he prefers it for copy-paste edits:
  it keeps the file at its exact path and auto-generates the commit
  message, which also sidesteps the URL-encoding problem in the commit
  box. Editor yes, Upload files no.
- **Always say whether a file is a repo file or a script to run.**
  Repo files stay; one-shot scripts get uploaded, run, then `rm`'d.
- **Workflows run from the branch, not the container.** Commit and
  push BEFORE hitting Run workflow.
- The Codespace **does not auto-fetch**. `git pull` before believing
  local state.

---

## SOURCES AND LICENCES — read before touching any fetch

Checked 2026-08-05. Not legal advice; a lawyer should see this if the
site ever charges.

**The site is PRIVATE.** No subscribers, no ads, login-gated, under ten
users, planned that way for at least a year. That fact is what makes
most of the below acceptable, and it is the hinge — **if it ever takes
subscriptions or runs ads, every line here must be re-examined.**

| Source | Used for | Status |
|---|---|---|
| **mykbostats** | KBO schedule, scores, probables | **CONFLICTS.** Acceptable Use cl. 6 forbids using their content to "run or promote sports betting, help others bet, or make sports bets". Not a commercial restriction — a USE restriction, so going private does not fix it. Terms eff. 2026-08-01. Run by Bigger Bird Creative, Hawaii law. |
| **ESPN** | all WNBA | Disney Terms: "personal, noncommercial use only", no right to reproduce or make available to the public. Fine while private; a problem the day it is not. |
| **Baseball Savant / MLB** | Statcast, MLB schedule | MLB Advanced Media ToU. The prohibitions section is about infringing content and load, **not** commercial use — but the full document was not read end to end. Unresolved. |
| **npb.jp** | NPB | **Never examined.** |
| **Open-Meteo** | KBO/NPB weather | OK. Their non-commercial definition explicitly covers "private or non-profit websites or apps that do not have subscriptions or advertising". 10,000 calls/day; we use ~10. **CC BY 4.0 requires attribution with a link wherever displayed.** |
| **api.weather.gov** | MLB park weather | Public domain, commercial use fine, no key. The model the others should follow. |
| **eng.koreabaseball.com** | candidate KBO source | **No terms of use page exists** — footer is a bare copyright line, nothing legal in nav or sitemap. No prohibition, but no permission either. |

**An email to mykbostats was drafted** asking permission for private,
non-commercial use, honest about the betting. Contact via
`https://mykbostats.com/feedback` (the ToS address is Cloudflare-
obfuscated and needs JS to read). Whether it was sent is unknown.

---

## RULES — how not to break things

1. **Verify what is ON DISK, never a script's own report.**
2. **Commit before running anything that reverts.**
3. **f-strings in the CSS blocks need `}}`.** Always
   `python -m compileall -q app/views/Home.py` after touching it.
4. **Home cannot write `lc_sport_seg`** — use `_goto_sport()`.
5. **Home makes zero network calls, on purpose.**
6. **Never hand-write a dependency list in a workflow** — use
   `pip install -r requirements.txt` or `-c requirements.txt <names>`.
7. **Home looks empty outside board hours (1, 5, 7 PM ET) — that's
   correct.**
8. **ESPN blocks paths by IP range, not User-Agent.** All WNBA ESPN
   access goes through `app/engines/espn_wnba.py`.
   `tests/test_espn_wnba.py` forbids any view holding an ESPN URL
   directly.
9. **Don't fix layout by guessing at Streamlit's internal classes** —
   content-based fixes survive vendor renames, selector-based ones
   don't.
10. **Above the "Today" tag, everything must be about today.**
11. **NEW — a test that greps source must assert the PROPERTY, not the
    spelling.** Several tests read `wnba_precompute.py` as text. When
    the source improves past what the regex describes, the test fails
    with no bug present, and because `Run tests` gates the nightly,
    that silently kills the data pipeline. Grep for the invariant
    ("nothing slices the pick list"), never for one line's exact
    wording. And when you change code a source-grepping test watches,
    run the suite before you push.
12. **NEVER `git clean -xfd` in this repo.** The `-x` includes
    ignored files, and `.gitignore` deliberately hides two things that
    are real and unrecoverable from git: `app/auth_config.yaml` (live
    credentials — nobody can log in without it) and `app/data/` (the
    fetched archive — every page falls back to its placeholder until
    the next nightly). Clearing junk is `git clean -nd` to LOOK, then
    `git clean -fd` — no `-x`, ever. `__pycache__` and `*.pyc` are safe
    to delete outright.
13. **NEW — `|| echo "... continuing"` hides real defects, so
    something must run the code.** The WNBA outage (item 18) passed
    through five layers of correct error handling and surfaced as a
    warning nobody read. Swallowing a step's failure is right — one
    league must not take down the others — but it means the ONLY thing
    that can catch a defect in that step is a test that actually
    executes it. Any parser in the pipeline needs a fixture test with a
    stubbed fetch. Also: run `python -m pyflakes wnba_precompute.py
    precompute.py kbo_precompute.py npb_precompute.py` after touching
    any of them; an undefined name inside a rarely-linted branch is
    exactly this bug.
14. **NEW — a green repo is not a green pipeline.** After any push that
    touches `wnba_precompute.py`, `precompute.py`, or `tests/`, check
    Actions for the nightly's next run. It can be red for days without
    anything on the site looking obviously wrong — the pages just keep
    serving the last archive.

---

## Done and verified

Through commit `cb3530c`:
1–7. Workflow install fixes, partial-failure handling, Node 24
   actions, `fetch_data.py` filter fix, cross-sport board cards on
   Home, `cleanup.py` removed, `starlette==0.52.1` pinned,
   "Beating baseline" tile, Track record moved above Explore.
8. Today-card heights fixed in markup (`_spacer_row`, `_card_rows`).
9. `_render_explore()` dead end replaced with `_goto_sport` links.
10. **WNBA live scores fixed.** `app/engines/espn_wnba.py` holds the
    mirror chain. `wnba_precompute.py` and `app/views/WNBA.py` both
    import from there; the old hardcoded `_SB_URL` is gone.
11. `tests/test_espn_wnba.py` added, verified to fail on the pre-fix
    tree.
12. Real `README.md`; probe workflows pinned; dead files removed.

Committed and confirmed present on `main` this session:
13. **Roster/injury status fix.** `fetch_team_roster()` keeps `jersey`,
    `roster_status`, `injury_status`, `injury_date`, `exp`. `WNBA.py`'s
    Status column consults `injury_status` before the inferred
    `OUT {days}d` guess. `tests/test_wnba_roster_status.py` pins the
    parsing and the precedence, and forbids reading a `starter` flag
    off the roster.
14. **Roster/injury probe run and analyzed.** Full roster payload is
    present and cheap (one request per team, already being made). No
    `starter`/`active` fields exist on it at all; the dedicated injury
    endpoints are both worse (one 500s, the other needs a fetch per
    player). Ranked starters are not obtainable from ESPN for the WNBA.
15. **Full-roster slate.** The build-time top-N cap is gone — every
    rostered player reaches the slate, sorted by minutes.

This session:
16. **Stale `test_wnba_today.py` assertion fixed**, which un-gates the
    nightly. Negative control run to confirm it still catches a
    re-introduced cap. **COMMITTED — in `3989bb0`.**
17. **A2 — the reported injury status now reaches every board.**
    Verified in a clean container, awaiting upload + commit (see "Right
    now"). `availability()` in `app/engines/wnba_props.py` consults the
    roster's `injury_status` between ESPN's per-game `today_out` block
    and the days-since-played inference. Props, Defense, Player of the
    Day and `likely_starters` all go through `availability()`, so all
    four inherit it; the `Status: Out` / `Role: START` contradiction on
    the WNBA page is gone. The rules, all pinned by
    `tests/test_wnba_injury_gate.py`:
    - Only unambiguous statuses rule anyone out — out, injured
      reserve, suspension, inactive, not-with-team, season-ending.
      Day-to-day, questionable, doubtful, probable and game-time
      decision stay AVAILABLE. Uncertainty is not absence, and
      dropping a questionable player is the same class of error in the
      other direction.
    - Anything unrecognised, missing or malformed falls through to the
      log inference. A new ESPN status string can never silently empty
      a board.
    - A game logged AFTER `injury_date` discards the note — an
      appearance is harder evidence than a report nobody cleared.
    - A note older than `INJURY_TRUST_DAYS` (10) stops deciding. That
      rarely clears anyone, since a genuinely absent player trips
      `STALE_DAYS` anyway; it protects the player who came back and
      whose return the feed never acknowledged.
    - An UNDATED note is trusted. It is the roster's current statement
      with nothing to weigh against it, and failing open there would
      reinstate the whole bug.
    - `today_out` still wins in both directions — it is about tonight,
      the roster note is about the player in general.
    Negative control run twice: the test fails on the pre-fix tree, and
    fails with the right message when only the gate call is unwired.
18. **THE WNBA OUTAGE — a one-character typo in `parse_boxscore`.**
    Found Aug 5 after a nightly run completed and the site still showed
    *"No WNBA slate on disk for 2026-08-05"* (four games were on the
    real schedule that night). `_made_att` in `wnba_precompute.py` wrote
    `line[al]` instead of `line[ak]`. `al` is undefined, so the FIRST
    player of EVERY box score raised NameError.

    Why nothing caught it — five correct defensive layers in a row, each
    doing its job, compounding into a silent league-wide outage on a
    green pipeline:
    1. `parse_boxscore` is called inside `except Exception as exc:
       print(...)`, so each game printed "boxscore NNN failed" and the
       crawl continued.
    2. Every game failing left `logs` empty, so the deliberate
       `RuntimeError("parsed ZERO box scores")` fired and killed the
       script — correctly.
    3. The nightly runs it as `python wnba_precompute.py || echo "WNBA
       fetch failed - continuing without it"`, which swallowed that.
    4. `Verify the archive before publishing` treats a missing
       international/WNBA slate as a `::warning::`, not an error — by
       design, so a real league break can't block MLB.
    5. `slate_guard` found no file at all and the page honestly said so.

    Note the diagnostic tell: *"No WNBA slate on disk"* means
    `slate_date is None` — the file is MISSING or unreadable. A merely
    stale slate produces a different sentence naming the date it holds.
    That distinction is what located this.

    Fixed, plus `tests/test_wnba_boxscore_parse.py` — runs the parser
    against a hand-built ESPN-shaped summary with a stubbed `get_json`
    (no network), asserting makes AND attempts, counting stats, the
    derived PRA/PR/PA/RA/stocks, opponent attribution, DNP skipping,
    and that the zero-box-scores RuntimeError is still there. Negative
    control: restoring `al` makes it fail with the NameError.
    `pyflakes` found this in seconds — worth running on the pipeline
    files as a habit.

---

## PENDING — in priority order

**Snapshot at handoff.** Done and confirmed: licensing review of every
source; weather rebuilt on Open-Meteo with attribution; KBO migration
probed and scoped; heat flag rebuilt properly. Open: the admin
credential check (item 0), the probables endpoint (F2), the best-games
hero card (C), the cold-start call (D), and the unread terms for
Baseball Savant and npb.jp (see SOURCES AND LICENCES).

### 0a. CREDENTIALS — CHECKED 2026-08-05. Passwords fine, COOKIE KEY WAS NOT.

The old item asked whether the live admin password was still the
template's `ChangeMe_Admin123!`. **It was not** — the live admin is
`iamjpescobar` with its own hash, and neither live password hash
appears in the committed example file. Compared byte-for-byte, not
eyeballed.

**The real finding was next to it.** The `cookie: key:` in the live
Render Secret File was IDENTICAL to the one committed in
`app/auth_config.example.yaml` — copied when the template was first
used and never rotated, because a plausible-looking value does not look
like something you still have to do.

That key signs the session cookie. Anyone holding it can forge a
session for any username and role, **admin included, without a
password**. It walks around the login rather than through it. And it
sat in a public repo.

**Fixed:** live key rotated in Render; the example file now carries
obvious placeholders with a comment explaining why. If a secret in that
file ever looks usable again, that is the bug.

**Standing rule from this:** a secret's only home is the Render field —
not a terminal, not a screenshot, not a chat. To copy one on the iPad
without the terminal-selection problem:

```bash
python -c "import secrets; print(secrets.token_hex(32))" > /tmp/newkey.txt
code /tmp/newkey.txt      # an editor tab you CAN select from
# paste into Render, then:
rm /tmp/newkey.txt
```

`/tmp` is outside the repo, so it cannot be committed by accident.

**Not yet done:** nobody has grepped the rest of the repo for other
committed secrets. One `grep -rn "key:\|token\|secret" --include=*.yaml`
would settle it.

### 0. DONE — the `concurrency:` block ships with this batch
`nightly-data.yml` was the only workflow that commits, publishes a
release AND triggers a Render deploy, and the only one without the
guard `slate-picks.yml` has always had. Group `nightly-data`,
`cancel-in-progress: false` so a ~15-minute Statcast fetch is never
killed mid-flight — the second run queues instead.

**What two overlapping runs did and did not break** (traced through the
workflow, not assumed):
- SAFE — the release publish is upload-then-`--clobber`, so there is
  never a window without an asset; the archive is verified before it
  publishes; and `grade()` skips any pick already marked
  hit/miss/dnp, so grading twice cannot double-count.
- THE ACTUAL RISK — `Commit graded calibration record`. Both runs write
  `data/calibration.json`, commit, then `git pull --rebase`. Whichever
  lands second rebases onto the first's commit to the same file and can
  conflict, turning a healthy run red for no real reason. If a run ever
  goes red at that step, this is why, and it is not data loss.
- WASTEFUL — two ~15-minute Statcast fetches hitting Baseball Savant in
  parallel, and two Render deploys queued back to back on the free tier.

### A. Honest starters — CLOSED. LIKELY is the final answer.

**(1) SHIPPED.** `announced_starters()` is its own function in
`wnba_props.py`; `likely_starters()` reads the flag through it so the
two cannot drift. `WNBA.py` prints **START** only for a reported
lineup, **LIKELY** for the minutes inference. `LIKELY` sorts at
priority 0 beside `START`, so table order is unchanged.

**(2) RAN, and the answer is no.** `wnba_lineup_probe.py` came back
`ReadTimeout` on `stats.wnba.com` — not a 403, it hung, which is how
that API family treats datacenter ranges. **Render is a datacenter
range too**, so a laptop success would not help: the constraint is
whether the thing that publishes the slate can reach it daily.

ESPN publishes no `today_starter`, the league's own API is unreachable
from where the code runs, and the inference now says what it is. **Do
not reopen without a new source.** The probe stays in the repo so the
finding is reproducible.

### A2. DONE — see item 17. Nothing left here.
Worth watching once it ships: the nightly's `[roster] team N: X
players, Y with a reported injury` lines say how many notes actually
exist on a given night. If Y is 0 league-wide for several days the
gate is inert and the payload changed shape; if a board suddenly
empties, check whether ESPN introduced a status string that belongs in
`_INJURY_OUT_STATUSES`.

### B. Full rosters with real status — his words
> make sure all of the players playing/available to play on the game
> listed no exemptions... and confirmed starting lineups the soonest
> possible

Status/injury half done (13) and the full roster now ships (15).
Starters confirmed unavailable from ESPN (14) — depends on A finding an
alternative source, or shipping the honest relabel as the final answer.

### C. Best-games hero card — BLOCKED on recording an MLB slate
Ranking is **DECIDED**: 1) biggest modeled edge, 2) highest projected
run total, 3) weather/park swing. Goes at the top of Home (rule 10).
Blocked on: no `data/mlb/games.json`, `slate_guard._LEAGUES` has no
`mlb` entry (both re-confirmed this session). Needs
`calibration_picks.py` extended to record an MLB slate to disk in the
shape `slate_guard` reads. Not started.

### D. Daily cold start — his call needed
Moving dome flags out of `intl_venues.py` into published data so the
late refresh stops triggering a Render deploy. Touches the nightly and
the engine — his call before starting. Not started.

### E. KBO probables — FOUND, FIXED, awaiting one live confirmation.
Four probes established that mykbostats' Aug 4 rewrite moved probables
off the game page onto the homepage. `parse_homepage_starters()` /
`fetch_homepage_starters()` replaced the old parser — one request for
the whole slate, keyed on href and visible text (rule 18), ids dropped
whole on a count mismatch (rule 19).

**Watch the 18:20 KST refresh.** It logs `KBO: homepage — N of M game
cards carried a Starters line`. N > 0 means probables are back. N = 0
on a played slate means the line moved again — **re-probe, do not widen
the regex.**

### E1. Weather — REBUILT PROPERLY. Done.
Was read off mykbostats' rendered homepage, which inherited their
terms, their upstream (that figure is Apple Weather) and their markup.
Now `app/engines/intl_weather.py` fetches Open-Meteo directly:
coordinates for all 9 KBO and 12 NPB venues, one call per slate date,
returning first-pitch temperature, precipitation probability, wind and
the day's max. Gives what their page never could — **tomorrow's** risk.

Three decisions to preserve:
- **The heat flag reads the DAY'S MAX, not first pitch.** A 4pm peak of
  36 easing to 33 by 18:30 is still the day a game gets called.
- **`HEAT_CANCEL_C = 35.0` is UNVERIFIED.** Matches the commonly cited
  figure and the 폭염경보 criteria but was never confirmed against a
  published KBO rule, which may key on apparent temperature or a KMA
  warning. Every run logs max temps whether or not the flag fires, so a
  week of logs beside real cancellations calibrates it. **Do not
  quietly tune the number without recording why.**
- **An unrecognised venue returns None, never a default.** A guessed
  stadium gives a confident forecast for the wrong city.

**Attribution shipped.** CC BY 4.0 requires it with a link wherever the
data shows. `KBO.py` imports `ATTRIBUTION` from the engine and renders
it once per page under the slate caption. **Removing it is a licence
violation. If the source changes, edit the engine, not the view.**

### E3. KBO source migration — scoped, blocked on one piece.
mykbostats clause 6 forbids betting use, so the rest should move to
`eng.koreabaseball.com`. Probed 2026-08-06:
- `DailySchedule.aspx` GET returns the **whole current month** — 98KB,
  ~130 games, a POSTPONED column. One request covers a nightly.
- **Query strings do NOT select a month.** All four spellings echoed
  the default; the control is `__doPostBack` with viewstate. Only
  matters for backfill, and only in the first days of a month.
- Scoreboard, standings, pitching leaders, team stats all HTTP 200.
- **Probables are the blocker.** The Korean schedule served 0
  occurrences of 선발 / 투수 / 예고 — drawn client-side. **Next step:
  one probe to find the XHR endpoint that page calls.** Until then the
  choice is keep mykbostats for probables only, or drop them.

### E2. WNBA mid-day recovery — DONE, verified in a real run.
`wnba_precompute.py` now runs in `intl-late-refresh.yml` as
`id: wnba`, in all three success gates, the verify loop and the
failure report. Confirmed live: 4 games, 307 players, 110 roster
players, `present data/wnba/`, 2530 entries, published + deployed.
Original problem, kept for the reasoning:
Observed live: the WNBA page showing *"No WNBA slate on disk for
2026-08-05"* — `slate_guard` correctly refusing to render an older
night's games as tonight's, because no archive had been published
since the nightly's test gate went red.

The gap: `intl-late-refresh.yml` re-fetches **KBO and NPB only**. The
WNBA slate is built solely inside `nightly-data.yml`, downstream of the
~15-minute Statcast pull. So the only way to recover a missing WNBA
slate mid-day is a full nightly run, and "Sync latest" cannot help —
it re-downloads the same release asset and will honestly report
"already on the latest data build".

Worth fixing: either add `wnba_precompute.py` to the late-refresh job
(it already does download-swap-repack-verify-upload, and WNBA is the
league with an evening ET slate that most needs a late look), or give
WNBA its own small refresh workflow on the same pattern. Note the
comment in that file about each republish triggering a Render deploy
and a free-tier cold start — that's the constraint to design around,
not ignore.

### F. Smaller
- `likely_starters` double-docstring (finding 3) — merge whenever that
  file is next open.
- Watch KBO voids for a week before deciding whether the forecast feed
  is worth chasing further.
- Weather for KBO/NPB + postponement-risk flag. Open-Meteo rejected
  (non-commercial free tier). JMA permits commercial use; KMA
  unverified.
- News section: pushed back on twice (rule 5 — Home can't fetch).

---

## Working agreements

- He asked for the whole app reviewed, not just reported bugs.
- Repo style: comments explain **why**, including what broke before.
- Be explicit about verified vs assumed — several findings have
  overturned a confident hypothesis (KBO: missing dependency, not
  outage; WNBA backfill: payload-shape mismatch, not a block; this
  session: a red test with no bug behind it).
- When Claude gets something wrong, say so plainly and move on.
- Don't build something you can't verify.
- **Long content is delivered as an uploaded file, never pasted into
  chat as text.**
