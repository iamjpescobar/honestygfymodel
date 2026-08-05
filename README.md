# Los Cappers

Streamlit sports-betting analytics app — MLB, WNBA, KBO, NPB. Every
board it publishes is graded against what actually happened, and the
grades are on the site.

Live at **loscappers.site**, deployed from `main` on Render.

---

## Running it

```bash
python app/fetch_data.py    # pulls the nightly Statcast archive
streamlit run app/app.py --server.enableCORS false --server.enableXsrfProtection false
```

`fetch_data.py` downloads the `nightly-data` GitHub release
(`statcast_data.tar.gz`) into `app/data/`. Without it the MLB boards have
no pitch data and fall through to their placeholders; the international
and WNBA pages read their own slate files and still work.

## Tests

55+ files in `tests/`, all **plain scripts, not pytest**. Each one exits
non-zero on failure and CI checks exit codes. There is no pytest
anywhere in this repo — don't add `assert`-collecting fixtures and
expect them to run.

```bash
fails=""
for t in tests/*.py; do python "$t" >/dev/null 2>&1 || fails="$fails $(basename $t)"; done
echo "FAILING:${fails:- none}"
```

---

## Layout

| Path | What's there |
| --- | --- |
| `app/app.py` | Entrypoint. Auth, sport switcher, routing. |
| `app/views/` | Pages. **Not** `pages/` — see below. |
| `app/engines/` | All computation. One concern per module. |
| `app/styles/kc_theme.py` | `COLOR`, `TYPE`, `SPACE`, `RADIUS` → `--lc-*` CSS vars. |
| `*_precompute.py` (root) | Nightly fetchers, run in CI, never in the app. |
| `.github/workflows/` | Nightly data, board recording, probes. |
| `tests/` | Plain scripts. |

**Pages live in `app/views/`, deliberately.** Streamlit auto-registers
anything in a `pages/` directory and would expose every page before the
login gate.

**Visual changes are edits to the token dicts** in `kc_theme.py`, not
inline CSS. 25 files and 541 call sites already read from `var(--lc-*)`.

---

## Where the data comes from

Nothing is computed at page load if it can be computed ahead of time.

- **Nightly** (`nightly-data.yml`) — Statcast pull, packed and published
  as a GitHub release. Render fetches it at build time.
- **Boards** (`slate-picks.yml`) — `calibration_picks.py` builds the same
  boards the site does, at 1, 5 and 7 PM ET, and commits them to
  `data/calibration.json`. That file is what Home and Results read, which
  is why they can't disagree with the boards themselves.
- **International** (`intl-late-refresh.yml`) — KBO and NPB slates, late
  enough to catch announced starters.
- **WNBA** (`wnba_precompute.py`, in the nightly) — slate, box scores and
  player logs from ESPN.

Slate files are always read through `engines/slate_guard.load_slate()`,
never opened directly. It refuses a slate built for a date already past,
so a night that has been played can't be shown as tonight's. Each league
stamps its own timezone key — a KBO slate for Aug 5 KST is correct while
it's still Aug 4 in Newark.

---

## Things that will bite you

- **`requirements.txt` is fully pinned, including transitive pins.**
  `pybaseball==2.2.7` scrapes Baseball Savant and a point release can
  silently rename columns. `starlette==0.52.1` is pinned because
  Streamlit declares it with no upper bound.
- **Never hand-write a dependency list in a workflow.** Use
  `pip install -r requirements.txt`, or `pip install -c requirements.txt
  <names>` for a trimmed install — `-c` lets the job pick packages while
  production picks versions. A workflow that listed its own deps and
  omitted `pandas` failed silently every night for a week.
- **ESPN blocks by IP range, not User-Agent.** The same path can return
  200 from a laptop and 403 from CI. Probe from Actions; a residential
  result predicts nothing. All ESPN WNBA access goes through
  `engines/espn_wnba.py` — one mirror chain, one normalizer, imported by
  both the pipeline and the live page.
- **Home makes zero network calls, on purpose.** Everything comes off
  disk via `calibration._load()` and `slate_guard.load_slate()`. Adding a
  fetch there costs the one page whose only job is to paint instantly.
- **Home looks empty before 1 PM ET.** That's correct — no board has been
  recorded yet, and it says so.
- **`Home.py` builds CSS from concatenated f-strings.** A literal `}` in
  an f-string must be `}}`; plain strings use one. Both styles are in the
  file. Run `python -m compileall -q app/views/Home.py` after editing it.

## House style

Comments explain **why**, and usually name what broke before. That's
deliberate and it's the most valuable thing in the codebase — a rule with
its incident attached doesn't get quietly undone six months later. Match
it.
