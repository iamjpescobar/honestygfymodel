"""
MATCHUP GRADE (10-26) — one letter, A to F, for how good tonight's
opponent is for THIS prop: Izzy: "DeBrincat anytime goal prop would be
graded a B or whatever grade the matchup might be — I want that to be a
factor on the whole site and anything prop related".

WHAT THE LETTER IS
------------------
The opponent's rank against the league on what it gives up for this
prop, cut in fifths:
    A  the softest fifth  (allows the most of this stat to his kind of player)
    B  next fifth
    C  the middle
    D  next fifth
    F  the toughest fifth (allows the least)
Each sport's own matchup number is ranked — nothing new is invented:
  NHL  defense vs position (engines/defense_matchup): goals / points /
       assists / shots allowed to centres, wingers or defencemen
  NFL  defense vs position, same engine (QB / RB / WR / TE)
  MLB  batters: tonight's starter's allowed per-PA rate — against THIS
       hitter's hand (lefty / righty / switch) on the stats where that
       split beat the starter's overall rate on unseen games, ranked among
       every starter against hitters of that hand (10-28, defense_matchup.
       fit_platoon; re-tested nightly); pitchers: tonight's lineup's rate
  NBA  what the defense ALLOWED to his position group (G / F / C) a game,
       this season + last (engines/defense_matchup via nba_context.
       dvp_table), ranked over the 30 NBA teams (10-28). It used to rank
       the projection's opponent factor: team-wide and within a percent or
       two of 1.0 for nearly every team (Dean Wade @ IND x0.999 read "B"),
       over 33 "teams" (three exhibition clubs). The projection keeps its
       own tested factor; the letter is context, as in NHL / NFL.
       Last season's split-half reliability (does a team's rank on half its
       games repeat on the other half): points to guards 0.57, centres
       0.40, FORWARDS 0.003 — what a team allows to forwards does not
       repeat, so a forward's points letter is mostly noise, in any app.
  Same position + same opponent = the same letter in every sport: the
  letter grades the DEFENSE against that kind of player, not the player.
A letter is about the OVER (an A is a good spot for the over, an F a good
spot for the under).

IS THE LETTER IN THE CHANCE?
----------------------------
A letter is a rank, not a probability. Whether the matchup MOVES the
chance is each sport's own tested question (rule 1), and the pages say
which:
  NBA  yes — the opponent factor is in every projection (tested, beats)
  NFL  yes — the matchup multiplier is in the projection
  MLB  yes — the batter-vs-starter rates are the projection
  NHL  the position split is CONTEXT (validate_dvp: did not beat); the
       team's goals / shots allowed are in through the game model
So adding the letter on top of the chance again would count the same
thing twice. What the letter adds is a fast read of WHY a chance is high
or low — and from 10-26 every captured line carries its letter, so the
Site vs DraftKings grade measures, per letter, whether A spots really go
over more than the site said (the test of whether the grade knows
something the chance does not).

Pure — no streamlit, no requests.
"""
LETTERS = ("A", "B", "C", "D", "F")
WORDS = {"A": "great spot", "B": "good spot", "C": "average", "D": "tough spot",
         "F": "very tough spot"}


def grade(rank, of):
    """'A'-'F' from a rank (1 = allows the most) out of `of`, or None."""
    try:
        rank, of = int(rank), int(of)
    except (TypeError, ValueError):
        return None
    if rank < 1 or of < 2 or rank > of:
        return None
    q = (rank - 1) / (of - 1)          # 0 = softest, 1 = toughest
    return LETTERS[min(4, int(q * 5))]


def from_card(card):
    """The letter for a defense_matchup card (its own grade, else from its
    rank), or None."""
    if not card:
        return None
    return card.get("grade") or grade(card.get("rank"), card.get("of"))


def rank_values(values, mine):
    """(rank, of) of `mine` among `values` (1 = the largest), ties share
    the better rank; (None, n) when mine is None."""
    vals = [v for v in values if v is not None]
    if mine is None or not vals:
        return None, len(vals)
    return 1 + sum(1 for v in vals if v > mine + 1e-12), len(vals)


def nba_grades(book, opp_id, grp, day, teams, combos, means):
    """{stat: {"grade", "rank", "of", "mult"}} for one NBA player tonight:
    the opponent's factor on each stat (the props model's own, engines/
    nba_context.OppBook.factor) ranked over every team in `teams` for his
    position group. Combos rank the league-mean-weighted factor of their
    parts. A stat whose factor is 1.0 for every team (the opponent is not
    in that stat's number) gets no grade."""
    allf = {str(t): book.factor(t, grp, day) for t in teams}
    mine = allf.get(str(opp_id)) or book.factor(opp_id, grp, day)
    out = {}
    stats = list(mine)

    def comb(f, parts):
        w = sum((means or {}).get(s, 1.0) for s in parts) or 1.0
        return sum(f[s] * (means or {}).get(s, 1.0) for s in parts) / w
    vals = {st: {t: f[st] for t, f in allf.items()} for st in stats}
    my = {st: mine[st] for st in stats}
    for c, parts in (combos or {}).items():
        vals[c] = {t: comb(f, parts) for t, f in allf.items()}
        my[c] = comb(mine, parts)
    for st, by in vals.items():
        if max(by.values(), default=1.0) - min(by.values(), default=1.0) < 1e-9:
            continue
        r, of = rank_values(list(by.values()), my[st])
        g = grade(r, of)
        if g:
            out[st] = {"grade": g, "rank": r, "of": of, "mult": round(my[st], 3),
                       "vs_league_pct": round(100 * (my[st] - 1), 1)}
    return out


def by_grade(graded, idx=10):
    """{letter: {"n", "site", "book", "actual"}} from graded rows whose
    element `idx` is the letter: per letter, the site's mean over chance,
    the book's, and how often the over really hit. The check of whether
    the letter knows something the chance does not: if A rows hit well
    above what the site said, and F rows well below, the grade is real
    information the chance is missing."""
    acc = {}
    for r in graded or []:
        g = r[idx] if len(r) > idx else None
        if g not in LETTERS:
            continue
        a = acc.setdefault(g, [0, 0.0, 0.0, 0])
        a[0] += 1
        a[1] += r[5]
        a[2] += r[6]
        a[3] += r[7]
    return {g: {"n": a[0], "site": round(a[1] / a[0], 4), "book": round(a[2] / a[0], 4),
                "actual": round(a[3] / a[0], 4)} for g, a in sorted(acc.items())}
