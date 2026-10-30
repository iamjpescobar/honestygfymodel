"""
MATCHUP GRADE (10-26) — one letter, A to F, for how good tonight's
opponent is for THIS prop: Izzy: "DeBrincat anytime goal prop would be
graded a B or whatever grade the matchup might be — I want that to be a
factor on the whole site and anything prop related".

WHAT THE LETTER IS
------------------
(10-28) For defense-vs-position letters (NBA, NHL, NFL) the standing is
adjusted for how much of it is REAL before it is cut in fifths
(defense_matchup.reliability_grade): a ranking that does not repeat from
one half of a season to the other, or rests on a handful of games, reads
C — however extreme its rank. When the standing is fully reliable this is
exactly the old cut in fifths:
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
  NBA  how players did against their OWN projections vs this defense —
       the props model's opponent factor (nba_context.OppBook; by position
       only on stats where the nightly fit says that predicts better),
       ranked over the 30 NBA teams (10-29). Walk-forward on last season
       (20,333 player-games, each day from earlier days only), points vs
       the projection by letter: A +4.7% B +1.8 C -1.3 D -4.3 F -5.1%.
       The raw "points allowed to guards a game" letter (10-28, what other
       apps show) sorted the same games A +0.4 B +1.6 C -1.4 D -0.9
       F -3.3% — weaker and out of order; it stays on the row as a
       context card. Position split on top of the factor: R2 0.44% ->
       0.47% on points (nothing). The factor is already IN the projection.
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


# PLUS / MINUS (10-28). Izzy: "don't ignore C grades ... ours [must be]
# super sharp". Five letters hid which way a C leaned: each letter is now
# split in thirds (A+ A A- B+ ... F-), fifteen steps, so a C+ is a defense
# that leans soft for this player without the evidence for a B, and a C-
# leans tough. The base letter (A-F) still drives colours, the Under flip
# and the per-letter check; the label carries the direction.
MODS = ("+", "", "-")


def label_from_q(q):
    """'A+'..'F-' from q in [0, 1] (0 = softest, 1 = toughest), in fifteen
    equal steps."""
    q = min(max(float(q), 0.0), 1.0)
    i = min(14, int(q * 15))
    return LETTERS[i // 3] + MODS[i % 3]


def grade_pm(rank, of):
    """grade() with its plus / minus, or None."""
    try:
        rank, of = int(rank), int(of)
    except (TypeError, ValueError):
        return None
    if rank < 1 or of < 2 or rank > of:
        return None
    return label_from_q((rank - 1) / (of - 1))


def base(g):
    """'B+' -> 'B' (also 'B+ · +4%'); None / anything else -> None."""
    g = str(g or "").split(" ", 1)[0]
    return g[0] if g[:1] in LETTERS and len(g) <= 2 and g[1:] in ("", "+", "-") else None


def with_size(g, pct, side="Over", rank=None):
    """'B+ · +4% (9th)' — the letter (flipped for the Under) with the size of
    the matchup (its sign flipped too) and, when given, the defense's rank
    counted from the TOUGHEST (1st = allows the least — how HOF and most
    research apps count, 10-30); the rank is a fact about the defense, so it
    is not flipped."""
    if not base(g):
        return g
    g = str(g).split(" ", 1)[0]
    if side == "Under":
        g = flip(g)
        pct = -pct if pct is not None else None
    if pct is not None and round(pct) == 0:
        pct = 0.0
    out = g if pct is None else (f"{g} · ±0%" if pct == 0 else f"{g} · {pct:+.0f}%")
    return out + (f" ({rank})" if rank else "")


def tough_rank(card):
    """'1st' .. '30th' counted from the toughest defense (the card's rank is
    1 = allows the MOST), or None."""
    try:
        rank, of = int(card.get("rank")), int(card.get("of"))
    except (TypeError, ValueError, AttributeError):
        return None
    if rank < 1 or rank > of:
        return None
    n = of - rank + 1
    suf = "th" if 10 <= n % 100 <= 20 else {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suf}"


def flip(g):
    """The label for the Under: A+ <-> F-, B- <-> D+, C+ <-> C-."""
    b = base(g)
    if not b:
        return g
    m = str(g).split(" ", 1)[0][1:]
    return LETTERS[4 - LETTERS.index(b)] + {"+": "-", "-": "+", "": ""}[m]


def from_card(card):
    """The letter for a defense_matchup card (its own grade, else from its
    rank), or None."""
    if not card:
        return None
    return card.get("grade") or grade_pm(card.get("rank"), card.get("of"))


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
        g = grade_pm(r, of)
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
        g = base(r[idx] if len(r) > idx else None)
        if g not in LETTERS:
            continue
        a = acc.setdefault(g, [0, 0.0, 0.0, 0])
        a[0] += 1
        a[1] += r[5]
        a[2] += r[6]
        a[3] += r[7]
    return {g: {"n": a[0], "site": round(a[1] / a[0], 4), "book": round(a[2] / a[0], 4),
                "actual": round(a[3] / a[0], 4)} for g, a in sorted(acc.items())}
