# Reading the boards

How to use this site. Written 2026-08-12 against the boards as they
exist; if a formula changes, fix this file in the same commit.

---

## 0. Start here: what "good" actually looks like

Every board on the Results page prints a grey league-average number
beside its hit rate. **That number is the whole game.** Beating it is
the only thing that matters, and the size of the gap you need is
completely different board to board.

| board | league rate | what beating it looks like |
|---|---|---|
| Daily 13 (a hit) | ~62% | 65% is a real edge. 70% would be enormous. |
| HR Edge (a homer) | ~12% | 18% is a real edge. Most nights still go 0-for-5 or 1-for-5. |
| Player of the Day | ~28% | one pick a night, so this takes months to read |

Two things follow from this table and they are the two most useful
things on this page.

**A hit is easy, so the edge is thin.** Any random qualifying starter
gets a hit 62% of the time. The Daily 13 going 6-for-12 looks bad and
*is* below average — but the honest ceiling on that board is maybe
68-70%. You are grinding out a few points, not finding gold.

**A homer is rare, so the edge is fat but invisible night to night.**
12% baseline means even a genuinely excellent HR board misses far more
than it hits. A 1-for-5 night on HR Edge is *above* the league rate. A
0-for-5 night is completely normal and tells you nothing at all. You
cannot feel a 12%-to-18% improvement. You can only measure it.

### About everyone else's screenshots

You said other people are hitting crazy numbers on the same data. Some
are. Most are showing you the nights that worked — nobody screenshots
the 0-for-6. Almost none of them are grading themselves against a
league baseline the way this site does, which means they genuinely do
not know whether they are up or down.

The thing this site has that almost nothing else does is that it
publishes its own misses and prints the number it has to beat. That is
harder to look at and it is the only version that can actually be
improved. Do not tune this site toward looking like those screenshots.

---

## 1. The grammar every board shares

Once you see this, all of them read the same way:

**FLOOR → RANK → CONTEXT**

1. **A qualification floor** decides who is even eligible. Sample-size
   minimums, playing tonight, enough games.
2. **A ranking** orders the survivors, usually on recent form and
   season skill.
3. **A context layer** adjusts for tonight specifically — opponent,
   park, weather, bullpen, pace.

So when a name surprises you, ask which of the three put him there. A
name that is high because of context is a different bet from a name
that is high because of skill, and they fail in different ways.

### Colours and bars

Colour is that number's grade **on a fixed league scale**, not its rank
among the rows on screen. A .285 is the same colour on every page and
does not change when you filter. So colour answers "is this good", not
"is this the best one here."

An em dash (—) or N/A means **not measured**. It never means zero. This
site refuses to print a 0 it did not measure, which is why blanks are
common — that is the honesty convention working, not a broken page.

---

## 2. MLB — home runs

### HR Edge Board

The three-layer read:

- **HR Score** — the hitter with tonight removed. Pure skill.
- **Matchup / Context** — tonight only. Park, weather, bullpen,
  arsenal, lineup slot. Worth up to ±67 points.
- **HR Edge** — the two added, clamped 0-100. The board sorts on this.

**The gap between Score and Edge is the first thing to read.**

| shape | means |
|---|---|
| Edge ≈ Score, both high | the hitter is the pick |
| Edge ≫ Score | the *spot* is the pick |
| Edge < Score | good hitter, bad spot tonight |

A spot-driven pick is fragile. If the lineup changes, the wind flips or
the starter is scratched, most of its case evaporates. A skill-driven
pick does not care.

**The second-opinion columns.** These are built from different inputs
than HR Score, so they are worth most when they *disagree* with it.

- **Floors (N/9)** — hard qualification thresholds cleared. Only 7
  hitters in all of MLB clear 9/9, so 6/9 is genuinely good and 3/9 is
  a warning. High Edge with low Floors = the board likes the situation,
  not the bat.
- **Clears%** — how often he puts a ball on a trajectory that leaves
  *any* park. **League median is 0.00** — over half of qualified
  hitters have never done it once. This is the least redundant column
  on the board, so when it disagrees with everything else, listen.
- **PA** — how much evidence all of it rests on. 65 PA and 543 PA sit
  in the same table in the same size type. They are not the same claim.

**Held back by the cap.** At most two bats per *game* make the board.
Park, weather and the opposing arsenal lift a whole lineup at once, so
without the cap one matinee takes over the top fifteen. The bats it
held back are in the expander underneath — they are often strong plays
that lost their slot to two teammates, not to a better hitter.

### Pitchers to Target

The other side of the same question, and the one most people skip.
Ranked by **HR/9 allowed**, tiebreak Brl% allowed. No composite, no
weights — every column is on the table, colour-graded from the
*batter's* perspective, so high = friendlier for power.

Qualification: 3+ appearances and 10+ estimated IP. Switch the basis
between **season** and **L10** — a pitcher whose L10 is far worse than
his season is either hurt or tipping, and that is a live edge the
season number hides.

**Use it as a cross-check.** If a bat is high on HR Edge but the arm he
faces is mid-table here, most of that edge is coming from park and
weather rather than the pitcher.

### Weather Board

Cheap, fast, and it moves home runs more than almost anything else.
Wind out and warm temperatures are real; wind in kills a park.

Precipitation tiers are honest: **≥50% PPD RISK** (red), **25-49%
MONITOR** (gold), **<25% clear**. Roofed and retractable parks show a
**ROOF** badge instead — rain there closes a roof, it does not
postpone, and the board will not wave a false flag.

Check this **before** you lock anything. A postponed game is not a
loss, it is a void, but it wrecks a parlay's timing.

### Bullpen Board

**Roughly a third of a hitter's plate appearances come against
relievers**, and every other page on this site reads the starter. This
is the page that covers the rest.

**The splits by batter hand are the point.** A pooled team bullpen
number cannot tell you that the only lefty in the pen has been hammered
by right-handed bats, and that is frequently the entire story of a
late-inning spot.

Built for the live question: the starter is out, an arm is warming, is
this a spot to take the batter or leave it alone.

---

## 3. MLB — hits and strikeouts

### Daily 13

**Floor:** playing today, ≥50% of games with a hit, ≥25 games played.
(The page header currently says 60% — that text is stale, the engine
uses 50. Believe the engine.)

**Ranking, weights printed on the page:**

- **40% recent form** — L15 hit rate, L5 as a tiebreak
- **35% pitcher matchup** — the starter's real BA allowed and K%
  (contact-friendly arms rank higher), plus career BvP when the sample
  clears its floor
- **25% context** — the opposing *bullpen's* real BA allowed

Season consistency only qualifies you here. It does not rank you. That
was deliberate — ranking on season hit rate produced the same thirteen
names every night regardless of who was pitching.

**How to read it:** this board's edge is thin by nature (62% baseline).
The most useful thing on it is the pitcher-matchup component — a
contact-friendly arm with a bad bullpen behind him is where the 13 is
actually adding something over "these guys get hits."

### Strikeout Board

Fully transparent, no black box:

```
proj_K = (K/9 ÷ 9) × (season est IP ÷ starts) × opp_factor
opp_factor = opposing team K% ÷ league K%, clamped to [0.85, 1.15]
```

The clamp means one extreme lineup can never swing a projection more
than 15%. Everything feeding it is the pitcher's own Statcast rows plus
MLB's own team K%.

**This is our projection, not a sportsbook line.** The edge is in the
*gap* between this number and the posted line, so it is only useful
with a book open next to it. Pitchers with no probable or too little
data are listed with the reason instead of a fabricated number.

### Game Card

The deep dive for one game once a board has pointed you at it. Splits,
arsenal, bullpen, lineup. Use it to answer "why" after a board has
answered "who" — not to browse.

---

## 4. WNBA

### WNBA Props

The basketball Daily 13, same philosophy: **consistency qualifies,
tonight ranks.** Covers Points / Rebounds / Assists / PRA / 3PM.

- **35% consistency** — half is how often he cleared the line over his
  last 15 and 10. The other half is how often he stayed **within 20% of
  the line even when he missed**, and that second half is the one that
  matters. A line set at a player's own average gets cleared ~50% of
  the time by anybody; only downside risk separates a steady 20-a-night
  scorer from one alternating 2 and 38.
- **25% form** — recent production vs his own season baseline
- **25% matchup** — how much of this stat tonight's opponent allows to
  his position, vs the slate average
- **15% pace** — the game's combined scoring environment. More
  possessions, more chances.

**Where the edge lives:** the within-20% half of consistency. Books
price the average; they price the *floor* much less well. A player with
a high consistency score and a mediocre form score is exactly the
profile a line tends to misprice.

### WNBA Defense Matchup

Basketball has no starting-pitcher analog, so the honest version of
"which pitcher is easiest to hit" is **which team bleeds production to
this player's position.**

Ranked by **matchup edge**: how far above league-average allowance
tonight's opponent sits for that position, scaled by the player's own
recent production — so a bench player facing a soft defense does not
outrank a starter facing an average one.

Floors: opposing team needs 5+ games of positional data, player needs
5+ games played.

**Use it with Props, not instead of it.** Props already includes a 25%
matchup term. This page shows you the raw matchup so you can see
whether a prop's rank is being carried by it.

### Without Player

How a team performs when a specific player sits. Check it the moment an
injury report lands — usage redistributes in ways the season averages
on every other page cannot see yet.

---

## 5. A workflow that actually uses all of it

**Homers**

1. **Weather Board first.** Rule out the wrecked parks, note the ones
   with wind out. Two minutes.
2. **HR Edge.** Read Score vs Edge. Prefer bats where they agree.
3. **Floors and Clears%** as the veto. A 3/9 bat riding a big context
   number is the profile most likely to be noise.
4. **Pitchers to Target** to confirm the arm is genuinely giving up
   power, not just that the park is small. Flip to L10.
5. **PA column** last — if two bats look equal, take the one with 500
   PA behind him over the one with 90.

**Hits**

1. **Daily 13**, but read the pitcher-matchup component rather than the
   final rank.
2. **Pitchers to Target** — a high BA-allowed, low-K arm is the same
   signal from the other direction.
3. **Bullpen Board** — the 25% context term is bullpen BA allowed, so
   look at *which* arms, and against which hand.

**WNBA**

1. **Without Player** for tonight's injury news.
2. **Defense Matchup** for the soft spots by position.
3. **Props** last — it already folds in matchup and pace, so use the
   other two to understand *why* a name is where it is.

**On parlays.** Two bats from the same game are correlated — same park,
same weather, same pitcher. That raises the payout and it also means
they tend to hit or miss *together*, which increases variance rather
than spreading it. That is the same correlation the 2-per-game cap
exists to stop from dominating the board. Know which one you are doing.

---

## 6. Judging any of it

**The Results page is the only place.** Every board, graded, with the
league rate beside it. Never judge a board on a night — the site prints
"one night, not a trend" under each one and that caption is doing real
work.

The honest reading horizon is weeks, and for HR Edge at a 12% baseline
it is closer to a couple of months before a real edge separates from
noise.

**What is being logged right now:** every rated bat on every slate,
not just the five that publish, with the full metric set and the
result. In a few weeks that answers the question none of us can answer
today — whether an 88 HR Edge actually homers more often than a 71.
Until then, every weight and every floor on this site is a considered
opinion, honestly labelled as one.


---

## 7. Thresholds — what number is good enough

### First, the half this site does not have

**There are no odds anywhere in this app.** Every board ranks players by
the quality of their spot. Not one of them knows what price you are
being offered.

That makes "is this good enough to bet" unanswerable in principle from
this site alone. A 100 HR Edge at -150 is a bad bet. A 70 at +600 may
be a good one. The number here tells you **how unusual the spot is**;
the book tells you **what you are paid for it**. The bet lives in the
gap between those two, and only one of them is on this screen.

So read everything below as **"this is a strong reading"**, never as
"this is profitable."

### Second, none of these are validated yet

Every threshold below is either measured from your own league
distribution or taken from the site's own grade tiers. **None has been
tested against whether it actually predicts the outcome.** That is
precisely what the research log is now collecting. In a few weeks these
can be replaced with numbers that earned their place. Today they are
well-informed starting points and should be held that loosely.

### Third, sizing

At a 12% base rate, a genuinely good HR board still loses four nights
out of five on a single pick. Any staking plan that cannot survive a
0-for-15 stretch will not survive this board even if the board is
right. The hit boards are the opposite — small edge, low variance.

---

### MLB — HOME RUNS

Measured across 373 hitters at 150+ PA (2026-08-12). "Elite" = top
decile of the actual league, not a guess.

| stat | league median | good (75th) | elite (90th) |
|---|---|---|---|
| Brl/PA | 5.06 | 6.88 | **8.79** |
| Brl % | 7.65 | 10.65 | 13.49 |
| HH % | 39.95 | 44.59 | 48.61 |
| FB % | 26.87 | 30.59 | 33.68 |
| Avg EV | 88.60 | 90.10 | 91.80 |
| EV90 | 104.20 | 105.90 | 107.40 |
| Blast % | 16.04 | 19.57 | 22.22 |
| PullAir % | 11.89 | 15.21 | 18.36 |
| ISO | .150 | .190 | .230 |
| Clears % | **0.00** | 0.63 | 0.93 |

**The bar I would use on the board itself:**

- **HR Edge 90+** to be in the conversation at all — but see the Score
  gap below, because a 90 built from context is not a 90 built from
  skill.
- **HR Score 80+** if you want the *hitter* to be the reason. Under 70
  and you are betting the park and the pitcher, not the bat.
- **Floors 6/9 or better.** 7 hitters in all of baseball clear 9/9, so
  6 is genuinely strong and 3-4 is the board telling you the situation
  is carrying this.
- **Clears% above 0.63** puts him in the top quarter of the league at
  the one thing least correlated with everything else on the board.
  Above 0.93 is top decile. Zero means never once all season.
- **PA 300+** for full confidence. Under 150 he is not even in the
  scale core — the number is real, the evidence behind it is thin.

**The pitcher, from Pitchers to Target** (site's own grade tiers):

- **HR/9 allowed 1.40+** is a target. **1.75+** is a big one.
- Flip the basis to **L10**. An arm whose L10 HR/9 is far above his
  season number is the live edge; the season figure hides it.

**Weather:** wind out and warm is worth more than most single stats on
the board. Wind in kills the whole game. Check before locking.

---

### MLB — HITS

The floor to even appear on the Daily 13 is **≥50% of games with a hit
and ≥25 games played**. That is qualification, not a reason to bet.

**What actually ranks him** — and therefore what to read:

- **L15 hit rate (40% of the score).** The floor is a season number; the
  rank is recent. **65%+ over the last 15** is a real hot stretch.
  Anything near 50% is just the qualification floor showing up again.
- **The opposing starter (35%).** Using the site's own BA-allowed tiers:
  **.270+ allowed is friendly, .300+ is very friendly.** And you want a
  **low** K% — under 20% is contact-friendly, over 25% is a strikeout
  arm and a bad hit spot no matter what he is allowing.
- **The bullpen (25%).** The context term is the opposing pen's real BA
  allowed. Same tiers: .270+ is where you want it. This is the term
  most people ignore and it is a quarter of the score.

**The shape to look for:** high L15 form **and** a contact-friendly arm
**and** a soft pen. When those three agree you have the strongest
version this board produces. Two out of three is ordinary.

**Reality check:** the baseline is 62%. Even the best name on this board
is not a lock, and the honest ceiling for the board as a whole is
somewhere around 68-70%. Price accordingly — this is a grind, not a
green light.

---

### MLB — STRIKEOUTS

Different in kind: the Strikeout Board produces a **projection**, not a
rating. So the threshold is not a level, it is a **gap**.

```
proj_K = (K/9 ÷ 9) × (est IP ÷ starts) × opp_factor
opp_factor clamped to [0.85, 1.15]
```

- The edge is **projection minus the posted line**. Half a strikeout is
  noise. **A full strikeout or more of separation** is the point at
  which the gap is worth acting on, and even then only with the book
  open beside you.
- The clamp matters: opponent quality can never move this more than
  15%, so a big projection is being driven by the *pitcher's own* K/9
  and innings, not by a soft lineup.
- Supporting reads: **Whiff% 28+** and **K% 25+** are the site's "good"
  and "elite" tiers for an arm.

---

### WNBA — PROPS

**Floors, applied before anything ranks:** 8+ games played, 15+ minutes
per game, 10+ games in the log, and 8+ minutes in the most recent game.
A player under any of those is listed with the reason instead of a
score — that is the board refusing to rate someone whose usage it
cannot see.

**What to read, in priority order:**

1. **The consistency term (35%), and specifically its second half.**
   Half is how often he cleared the line over his last 15 and 10; the
   other half is how often he stayed **within 20% of the line even when
   he missed.** That second half is the one that finds mispriced lines.
   A line set at a player's own average gets cleared about half the
   time by anybody — only the downside separates a steady 20-a-night
   scorer from one alternating 2 and 38.
2. **Matchup (25%)**, cross-checked on the Defense Matchup board. You
   want the opponent measurably above league-average allowance to that
   position, not marginally.
3. **Pace (15%).** Small, but it is the cheapest free win on the slate:
   a fast game gives every prop in it more possessions.
4. **Form (25%)** last, deliberately. Form is what the book has already
   moved the line for. Consistency is what it prices worst.

**The profile to hunt:** high consistency, **mediocre form**, good
matchup. That is a player whose floor is solid and whose recent numbers
have not dragged the line up with them.

**MINUTES ARE THE WHOLE GAME IN THE WNBA.** Rotations swing far harder
than in baseball, and a prop is dead if the minutes are not there.
Check **Without Player** the moment any injury news lands — usage
redistributes immediately and every season average on every other page
is still describing the old rotation.

**Getting the absolute bar.** Run `python wnba_props_probe.py` (after
`python app/fetch_data.py`). It reports the median, 75th and 90th for
CONSISTENCY and FORM across every qualified player, per stat — the same
thing `hr_floors_probe.py` does for MLB batters. Re-run it every few
weeks; these drift through a season.

**It measures 60% of the score, and only 60%.** Consistency (35%) and
form (25%) are properties of the player and readable from her season
log. Matchup (25%) and pace (15%) are properties of tonight's game and
cannot be measured without a slate — so the final score on the board
sits above or below the probe's distribution depending on the matchup.

**FORM sits near 50 for most players by construction.** It measures
recent production against her OWN season baseline, so half the league is
above and half below at any moment. A form score far from 50 in either
direction is a real departure. And the board weights it at only 25% on
purpose: form is what the book has already moved the line for.

---

### WNBA — DEFENSE MATCHUP

Floors: opposing team needs 5+ games of positional data, player needs
5+ games played.

Ranked by how far above league-average allowance the opponent sits for
that position, **scaled by the player's own recent production**, so a
bench player facing a soft defense cannot outrank a starter facing an
average one.

Use it to *explain* a Props rank, not as a signal on its own — Props
already contains a 25% matchup term, so acting on both is counting the
same thing twice.
