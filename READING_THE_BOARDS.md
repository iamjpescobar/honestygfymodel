# Reading the boards

The complete guide. Every number here was measured from your own data on
2026-08-12 — nothing is estimated. Re-measure with the probes every few
weeks; league distributions drift.

---

## 0. The only thing that matters: baselines

Every board on the Results page prints a grey league-average number
beside its hit rate. **Beating that number is the entire game**, and the
gap you need is completely different board to board.

| board | league rate | what beating it looks like |
|---|---|---|
| Daily 13 (a hit) | ~62% | 65% is a real edge. 70% would be enormous. |
| HR Edge (a homer) | ~12% | 18% is a real edge. Most nights still miss. |
| Player of the Day | ~28% | one pick a night — takes months to read |

Two consequences, and they're the two most useful lines in this file.

**A hit is easy, so the edge is thin.** Any qualifying starter gets a hit
62% of the time. The Daily 13 going 6-for-12 looks bad and *is* below
average — but the honest ceiling is maybe 68-70%. You're grinding a few
points, not finding gold.

**A homer is rare, so the edge is fat but invisible night to night.** At a
12% base rate, a genuinely excellent board still misses far more than it
hits. **1-for-5 on HR Edge is above the league rate.** 0-for-5 is
completely normal and tells you nothing. You cannot feel a 12%-to-18%
improvement — you can only measure it.

### On other people's screenshots

Some people really are hitting. Most are showing you the nights that
worked; nobody screenshots the 0-for-6. And almost none of them grade
against a league baseline, which means they don't actually know whether
they're up.

What this site has that almost nothing else does is that it publishes its
own misses next to the number it has to beat. Don't tune it toward
looking like those screenshots.

---

## 1. The grammar every board shares

**FLOOR → RANK → CONTEXT**

1. A **qualification floor** decides who is eligible (sample minimums,
   playing tonight).
2. A **ranking** orders survivors, usually recent form plus season skill.
3. A **context layer** adjusts for tonight — opponent, park, weather,
   bullpen, pace.

When a name surprises you, ask which of the three put it there. A name
that's high on context is a different bet from one that's high on skill,
and they fail differently.

### Colours and blanks

Colour is that number's grade **on a fixed league scale**, not its rank
among rows on screen. A .285 is the same colour everywhere and doesn't
change when you filter. Colour answers "is this good", not "is this the
best one here".

An em dash (—) or N/A means **not measured**. Never zero. This site
refuses to print a 0 it didn't measure, so blanks are common — that's the
honesty convention working.

---

## 2. MLB — home runs

### HR Edge Board

Three layers:

- **HR Score** — the hitter with tonight removed. Pure skill.
- **Matchup / Context** — tonight only. Worth up to **±67 points**
  (BvP ±15, zone fit ±15, bullpen ±10, park ±10, temperature ±4, pitch
  matchup ±8, lineup slot ±5).
- **HR Edge** — the two added, clamped 0-100.

**Read the gap between Score and Edge first.**

| shape | means |
|---|---|
| Edge ≈ Score, both high | the hitter is the pick |
| Edge ≫ Score | the *spot* is the pick |
| Edge < Score | good hitter, bad spot tonight |

A spot-driven pick is fragile — lineup change, wind flip, scratched
starter, and most of its case evaporates. A skill-driven pick doesn't
care.

#### What HR Score is actually made of

Four axes, no column appearing in two of them:

| axis | weight | inputs |
|---|---|---|
| POWER | 40% | Brl/PA (70%), EV90 (30%) |
| CONVERGENCE | 30% | FB95% (60%), Clears Anywhere% (40%) |
| LAUNCH | 22% | HR window% (50%), pull-air% (50%) |
| PROCESS | 8% | bat speed, alone |

Plus a bounded **±8 conversion adjustment** from the xHR gap — expected
home runs minus actual, per scoreable batted ball. A hitter well under
his xHR has been hitting home-run trajectories and not being paid for
them, and that tends to close.

A score needs at least 60% of its own definition measurable, and must
include POWER. Below that it falls back to the Savant percentile average,
and returns nothing if neither source has him.

**These weights are considered, not fitted.** Nothing here has been
backtested against outcomes yet. That's what the research log is for.

#### The second-opinion columns

Built from different inputs than HR Score, so they're worth most when
they *disagree* with it.

- **Floors (N/9)** — hard qualification thresholds cleared. **Only 7
  hitters in all of MLB clear 9/9**, so 6/9 is genuinely strong and 3/9
  is the board telling you the situation is carrying this bat.
- **Clears%** — how often he puts a ball on a trajectory that leaves
  *any* park. **League median is 0.00** — over half of qualified hitters
  have never done it once. Least redundant column on the board; when it
  disagrees, listen.
- **PA** — how much evidence the rest rests on. 65 PA and 543 PA sit in
  the same table in the same type. Not the same claim.

#### The 2-per-game cap

At most two bats per **game** make the board. Park, weather and the
opposing arsenal lift a whole lineup at once, so without it one matinee
takes over the top fifteen. Per game, not per team — both sides share
that context.

Held-back bats are in the expander underneath. They're often strong
plays that lost their slot to two teammates, not to a better hitter.

On a thin slate the list comes back short — two confirmed games at 5 PM
means four picks, not five. Deliberate.

### Pitchers to Target

The other side, and the one most people skip. Ranked by **HR/9 allowed**,
tiebreak Brl% allowed. No composite — every column is on the table,
graded from the batter's perspective, so high = friendlier for power.

Qualification: 3+ appearances, 10+ estimated IP.

**Flip the basis to L10.** A pitcher whose L10 is far worse than his
season is either hurt or tipping, and the season number hides it.

Use it as a cross-check: if a bat is high on HR Edge but the arm is
mid-table here, the edge is coming from park and weather, not the
pitcher.

### Weather Board

Cheap, fast, moves home runs more than almost anything. Wind out and warm
is real; wind in kills a park.

Precipitation tiers: **≥50% PPD RISK** (red), **25-49% MONITOR** (gold),
**<25%** clear. Roofed parks show a **ROOF** badge instead — rain closes
a roof, it doesn't postpone.

Check before you lock. A postponement isn't a loss, it's a void, but it
wrecks a parlay's timing.

### Bullpen Board

**About a third of a hitter's plate appearances come against relievers**,
and every other page reads the starter. This covers the rest.

**The hand splits are the point.** A pooled team bullpen number can't
tell you the only lefty in the pen gets hammered by right-handed bats,
and that's frequently the whole story of a late-inning spot.

---

## 3. MLB — hits and strikeouts

### Daily 13

**Floor:** playing today, ≥50% of games with a hit, ≥25 games played.
That's qualification, not a reason to bet.

**What actually ranks him:**

- **40% recent form** — L15 hit rate, L5 as tiebreak
- **35% pitcher matchup** — the starter's real BA allowed and K%
  (contact-friendly arms rank higher), plus career BvP when the sample
  clears its floor
- **25% context** — the opposing **bullpen's** real BA allowed

Season consistency only qualifies you. It doesn't rank you — ranking on
season hit rate produced the same thirteen names nightly regardless of
who was pitching.

**The most useful thing here is the pitcher-matchup component.** A
contact-friendly arm with a bad bullpen behind him is where this board
adds something over "these guys get hits."

### Strikeout Board

Fully transparent:

```
proj_K = (K/9 ÷ 9) × (season est IP ÷ starts) × opp_factor
opp_factor = opposing team K% ÷ league K%, clamped to [0.85, 1.15]
```

The clamp means one extreme lineup can never swing a projection more than
15%, so a big projection is driven by the pitcher's own K/9 and innings.

**This is a projection, not a line.** The edge is the *gap* between it
and the posted number, so it's only useful with a book open beside you.

### Game Card

The deep dive once a board has pointed you at a game. Answers "why" after
a board answers "who". Not for browsing.

---

## 4. WNBA

### WNBA Props

Same philosophy as Daily 13: **consistency qualifies, tonight ranks.**
Covers Points / Rebounds / Assists / PRA / 3PM.

**Floors:** 8+ games played, 15+ minutes per game, 10+ games in the log,
8+ minutes in the most recent game. Anyone under is listed with the
reason instead of a score.

**Weights:**
- **35% consistency** — half is how often she cleared the line over her
  last 15 and 10. The other half is how often she stayed **within 20% of
  the line even when she missed**, and that half is what finds mispriced
  lines. A line at a player's own average gets cleared ~50% of the time
  by anybody; only the downside separates a metronome from a
  boom-or-bust scorer with the same average.
- **25% form** — recent production vs her own season baseline
- **25% matchup** — how much of this stat tonight's opponent allows to
  her position
- **15% pace** — the game's scoring environment. Cheapest free win on the
  slate.

**The profile to hunt: high consistency, mediocre form, good matchup.**
Form is what the book has already moved the line for. Consistency is what
it prices worst.

**MINUTES ARE THE WHOLE GAME.** Rotations swing far harder than in
baseball. Check Without Player the moment injury news lands.

### WNBA Defense Matchup

Basketball has no starting-pitcher analog, so the honest version of
"which pitcher is easiest to hit" is **which team bleeds production to
this position.**

Ranked by how far above league-average allowance the opponent sits for
that position, scaled by the player's own recent production. Floors: 5+
games of positional data for the team, 5+ games played for the player.

Use it to *explain* a Props rank, not as a separate signal — Props
already contains a 25% matchup term, so acting on both counts it twice.

### Without Player

How a team performs when someone sits. Check it the instant an injury
report lands; usage redistributes in ways season averages can't see yet.

---

## 5. Thresholds — what number is good enough

### First: this site has no odds

Every board rates the quality of a spot. **None knows what price you're
being offered.** A 100 HR Edge at -150 is a bad bet; a 70 at +600 may be
good. The number here says how unusual the spot is; the book says what
you're paid for it. The bet lives in the gap, and only one side is on
this screen.

Read everything below as **"this is a strong reading"**, never as
"this is profitable."

### Second: none of it is validated yet

Every threshold is measured from your league distribution — much better
than guessing — but **none has been tested against whether it predicts
the outcome.** That's what the research log is collecting.

### MLB batters — measured, 373 hitters at 150+ PA

"Elite" = actual top decile of the league.

| stat | median | good (75th) | elite (90th) | league max |
|---|---|---|---|---|
| Brl/PA | 5.06 | 6.88 | **8.79** | ~13 |
| Brl % | 7.65 | 10.65 | 13.49 | ~20 |
| HH % | 39.95 | 44.59 | 48.61 | — |
| FB % | 26.87 | 30.59 | 33.68 | — |
| Avg EV | 88.60 | 90.10 | 91.80 | — |
| EV90 | 104.20 | 105.90 | 107.40 | — |
| Blast % | 16.04 | 19.57 | 22.22 | — |
| PullAir % | 11.89 | 15.21 | 18.36 | — |
| ISO | .150 | .190 | .230 | ~.35 |
| **Clears %** | **0.00** | 0.63 | 0.93 | ~1.1 |
| FB95 % | 11.49 | 15.07 | 18.66 | 30.89 |
| HR window % | 25.10 | 27.74 | 30.14 | 41.94 |

League anchors, measured nightly: bat speed 69.4 mph · HR window 25.1% ·
pull air 12.3% · Brl/PA 5.28% · Clears Anywhere 0.32%.

### The bar on the board itself

- **HR Edge 90+** to be in the conversation — but check the Score gap.
- **HR Score 80+** if you want the *hitter* to be the reason. Under 70
  and you're betting park and pitcher.
- **Floors 6/9 or better.** Only 7 hitters in MLB clear 9/9.
- **Clears% above 0.63** = top quarter at the least-redundant thing on
  the board. Above 0.93 = top decile. Zero = never once all season.
- **PA 300+** for full confidence. Under 150 he isn't even in the scale
  core.
- **Pitcher HR/9 allowed 1.40+** is a target; **1.75+** is a big one.

### The nine qualification floors

Measured as percentiles, re-derived nightly so they don't go stale:

```
Brl%      ≥ 10.65   (75th)      Blast%     ≥ 19.57   (75th)
Brl/PA    ≥  8.79   (90th)      PullAir%   ≥ 15.21   (75th)
HH%       ≥ 44.59   (75th)      ISO        ≥  .200   (~78th)
FB%       ≥ 30.59   (75th)      Clears%    >  0       (has done it)
AvgEV     ≥ 90.20   (75th)
```

**7 of 373 hitters clear all nine. 12 more miss by exactly one.** That's
why it's a tier on the board and not a filter — a hard gate leaves about
two or three bats in a night's lineups, and you can't build a top-15 from
that.

**Brl% does most of the cutting** (373 → 95). ISO and AvgEV remove zero
once the power floors have run — they're not wrong, they're just implied
by what came before.

### MLB — hits

- **L15 hit rate 65%+** is a real hot stretch. Near 50% is just the
  qualification floor showing up again.
- **Opposing starter: .270+ BA allowed is friendly, .300+ very
  friendly.** You want a **low** K% — under 20% is contact-friendly, over
  25% is a strikeout arm and a bad hit spot regardless.
- **Bullpen: .270+ BA allowed.** A quarter of the score, and the term
  most people ignore.

Look for all three agreeing. Two of three is ordinary.

### MLB — strikeouts

The threshold is a **gap**, not a level. Half a strikeout from the posted
line is noise; **a full strikeout or more** is worth acting on. Support:
Whiff% 28+ and K% 25+ are the "good" and "elite" tiers for an arm.

### WNBA — measured, 123 qualified players of 308

| stat | CONSISTENCY median | 75th | 90th | **league max** |
|---|---|---|---|---|
| Points | 33.3 | 41.8 | 50.3 | 63.6 |
| Rebounds | 28.5 | 38.2 | 50.3 | 70.9 |
| Assists | 27.3 | 36.4 | 48.8 | 62.4 |
| PRA | 40.6 | 50.3 | 57.3 | 69.7 |
| 3PM | 18.2 | 29.6 | 43.8 | 68.5 |

**A consistency score of 50 is a strong reading, not a mediocre one.**
Nobody in the league exceeds ~71, and medians sit in the twenties and
thirties. The bar differs by stat: 45 is top-decile on 3PM and ordinary
on PRA.

**Two known problems with the props score, not yet fixed:**

1. **Form saturates on low-count stats.** It scales recent-vs-season
   deviation across a ±25% band. For 3PM, where a typical line is 1.0,
   going to 1.4 is +40% and clamps to 100. The 75th percentile of 3PM
   form is 94.9 and the 90th is exactly 100 — a quarter of the league
   pinned at the ceiling. **Treat a form score above ~90 as "recent
   uptick" and nothing more precise.**
2. **Consistency can't reach 100 and form can.** So at the top of the
   range, form moves a score more than its nominal 25% suggests.

---

## 6. A workflow

**Homers**
1. **Weather Board first.** Rule out wrecked parks, note wind-out. Two
   minutes.
2. **HR Edge.** Read Score vs Edge. Prefer agreement.
3. **Floors and Clears% as the veto.** A 3/9 bat riding a big context
   number is the profile most likely to be noise.
4. **Pitchers to Target**, flipped to L10, to confirm the arm is really
   giving up power rather than the park being small.
5. **PA last** — equal bats, take the one with 500 behind him.

**Hits**
1. **Daily 13**, reading the pitcher-matchup component rather than the
   final rank.
2. **Pitchers to Target** — high BA allowed, low K% is the same signal
   from the other side.
3. **Bullpen Board** — which arms, against which hand.

**WNBA**
1. **Without Player** for injury news.
2. **Defense Matchup** for soft spots by position.
3. **Props** last — it already folds in matchup and pace, so use the
   other two to understand *why* a name sits where it does.

**On parlays.** Two bats from the same game are correlated — same park,
same weather, same pitcher. That raises the payout and means they tend to
hit or miss *together*, which increases variance rather than spreading
it. Same correlation the 2-per-game cap exists to stop from dominating
the board. Know which one you're doing.

---

## 7. Judging any of it

**The Results page is the only place.** Every board, graded, with the
league rate beside it. Never judge on a night — the site prints "one
night, not a trend" for a reason.

The honest horizon is weeks. For HR Edge at a 12% baseline it's closer to
a couple of months before a real edge separates from noise.

**Worked example.** HR Edge went 2-for-5 one night and 3-for-5 the next:
5-for-10, 50% against a 12% baseline, roughly four times the league rate.
That is a genuinely good stretch **and it is ten picks.** Ten coin flips
land 8 heads about 4% of the time — unusual runs are not rare when you
only look at ten of them. Two weeks of this and it starts to mean
something. Two nights is a story, not evidence.

**What's being logged now:** every rated bat on every slate — around 270
a night, not just the five that publish — with the full metric set, the
edge components kept separate from the skill score, the floors count, and
the result. In a few weeks that answers the question none of this can
answer today: **does an 88 HR Edge homer more often than a 71?**

Until then, every weight and every floor on this site is a considered
opinion, honestly labelled as one.
