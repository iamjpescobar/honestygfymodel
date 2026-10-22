"""
NFL quarters (10-22) — each quarter's score, and every player's passing,
rushing and receiving line BY QUARTER, from ESPN's game summary (the
drives' plays). What the quarter / half lines and the 1st-quarter /
1st-half player props are fitted and tested on.

parse(summary) -> {
  "lines":   {team_id: [q1, q2, q3, q4, (ot)]}   team points per quarter
  "players": {pid: {stat: [q1, q2, q3, q4, ot]}}  stat in STATS
  "plays":   n plays read, "named": n of them a player was found in
}
ESPN's NFL plays name players only in the TEXT ("(Shotgun) J.Goff pass
short right to A.St. Brown to DET 45 for 12 yards (T.Smith)."), so each
team's box-score athletes are turned into the forms the text uses (first
initial(s) + "." + last name, suffix dropped too) and found in it:
  pass  -> passer = the first name in the text; att +1; a catch (not
           "incomplete" / "intercepted") -> cmp +1, his yards = the gain the
           text writes (play_yards); the receiver = the first name after " to "
           (targets +1 on every throw to him, a catch adds rec + yards)
  rush  -> the first name; carries +1, yards = the text's gain
  a touchdown on the play -> passer pass_td, receiver / rusher td
Skipped: "No Play" (penalty), two-point tries, sacks (not passing yards
in the box), kicks and returns.
Missing is never zero: the backfill checks, player by player, that his
quarters add up to his box score, and refuses to write when they don't.

Pure — no requests.
"""
import math
import re

STATS = ("pass_yds", "pass_att", "pass_cmp", "pass_td", "rush_yds", "carries", "rec_yds",
         "rec", "targets", "td")
SLOTS = 5                       # Q1-Q4, then all overtime
SUFFIX = re.compile(r"\s+(jr\.?|sr\.?|ii|iii|iv|v)$", re.I)


def _num(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def lines(summary):
    comp = (((summary or {}).get("header") or {}).get("competitions") or [{}])[0] or {}
    out = {}
    for c in comp.get("competitors") or []:
        tid = str((c.get("team") or {}).get("id") or c.get("id") or "")
        ls = [_num(x.get("displayValue") if isinstance(x, dict) else x)
              for x in c.get("linescores") or []]
        if tid and ls and None not in ls:
            out[tid] = ls
    return out


def roster(summary):
    """{pid: (team_id, name)} for every athlete in the box score's groups."""
    out = {}
    for b in (((summary or {}).get("boxscore") or {}).get("players") or []):
        tid = str((b.get("team") or {}).get("id") or "")
        for grp in b.get("statistics") or []:
            for ent in grp.get("athletes") or []:
                a = ent.get("athlete") or {}
                if a.get("id") is not None and a.get("displayName"):
                    out[str(a["id"])] = (tid, a["displayName"])
    return out


def forms(name):
    """The ways play text writes a player: 'Amon-Ra St. Brown' ->
    'A.St. Brown', 'Am.St. Brown', ...; suffixes dropped too; and his full
    name (scoring plays: 'Deebo Samuel 10 Yd pass from Jayden Daniels')."""
    parts = str(name or "").strip().split()
    if len(parts) < 2:
        return set()
    first, last = parts[0], " ".join(parts[1:])
    lasts = {last, SUFFIX.sub("", last)}
    out = {f"{first} {ln}" for ln in lasts}
    for ln in lasts:
        for k in range(1, min(len(first), 4) + 1):
            out.add(f"{first[:k]}.{ln}")
            out.add(f"{first[:k]}. {ln}")
    return out


class Names:
    """Finds a game's athletes in play text."""

    def __init__(self, ros):
        self.by_form = {}
        self.team = {pid: str(t) for pid, (t, _nm) in (ros or {}).items()}
        self.teams = set(self.team.values())
        self.whole = {}               # form -> ids whose WHOLE first name it spells
        for pid, (_t, nm) in (ros or {}).items():
            for f in forms(nm):
                self.by_form.setdefault(f, set()).add(pid)
            parts = str(nm or "").split()
            if len(parts) >= 2:
                for f in forms(nm):
                    if f.split(".")[0] == parts[0] or f.startswith(parts[0] + " "):
                        self.whole.setdefault(f, set()).add(pid)
        # longest forms first: 'Am.St. Brown' before 'A.St. Brown'
        keys = sorted(self.by_form, key=len, reverse=True)
        self.rx = re.compile("|".join(r"(?<![A-Za-z.])" + re.escape(k) + r"(?![a-z])"
                                      for k in keys)) if keys else None

    def find(self, text, team=None):
        """[(position, pid)] of the unambiguous names in the text. With the
        OFFENSE's team id, only its players count: 'C.Williams' is the
        Bears' quarterback, not the defender of the same initials, and a
        tackler in parentheses is never taken for the receiver."""
        if not self.rx:
            return []
        team = str(team) if team is not None and str(team) in self.teams else None
        out = []
        for m in self.rx.finditer(text or ""):
            ids = self.by_form.get(m.group(0)) or set()
            if team:
                ids = {i for i in ids if self.team.get(i) == team}
            if len(ids) > 1:
                # 'Ty.Johnson' is Ty Johnson before Tyler Johnson
                w = ids & self.whole.get(m.group(0), set())
                ids = w if len(w) == 1 else ids
            if len(ids) == 1:
                out.append((m.start(), next(iter(ids))))
        return out


def _plays(summary):
    return [p for p, _t in _plays_with_offense(summary)]


def _plays_with_offense(summary):
    """[(play, offense team id or None)] — the drive's team has the ball."""
    d = (summary or {}).get("drives") or {}
    out = []
    for dr in (d.get("previous") or []) + ([d["current"]] if isinstance(d.get("current"),
                                                                       dict) else []):
        tm = (dr.get("team") or {}).get("id") if isinstance(dr.get("team"), dict) else None
        out += [(p, tm) for p in dr.get("plays") or [] if isinstance(p, dict)]
    return out


YARDS = re.compile(r"for (-?\d+) yards?|for no gain|(-?\d+)\s+(?:yd|yard)s?\s+(?:pass|run|rush)",
                   re.I)


def play_yards(play, text):
    """The play's own gain as the text writes it ('for 12 yards', 'for no
    gain', '22 Yd pass from'); statYardage only when the text has none —
    statYardage can carry a penalty's yards enforced after the play."""
    m = YARDS.search(text or "")
    if m:
        g = m.group(1) or m.group(2)
        return float(g) if g is not None else 0.0
    return _num(play.get("statYardage")) or 0.0


PAT = re.compile(r"\([^()]*(two-point|two point|kick|conversion)[^()]*\)", re.I)
SCORING = re.compile(r"\d+\s+yd\s+(pass from|run)\b", re.I)


def _period(play):
    p = play.get("period")
    return (p or {}).get("number") if isinstance(p, dict) else p


def parse(summary):
    names = Names(roster(summary))
    out = {"lines": lines(summary), "players": {}, "plays": 0, "named": 0, "no_receiver": 0,
           "no_receiver_texts": []}

    def add(pid, stat, q, v):
        rec = out["players"].setdefault(pid, {s: [0] * SLOTS for s in STATS})
        rec[stat][q] += v
    seen = set()
    for pl, off in _plays_with_offense(summary):
        pid_ = pl.get("id")
        if pid_ is not None:
            if pid_ in seen:
                continue
            seen.add(pid_)
        # the try after a touchdown, written in parentheses on the scoring
        # play, is not the play (the touchdown itself still counts)
        txt = PAT.sub("", pl.get("text") or "")
        low = txt.lower()
        typ = (((pl.get("type") or {}).get("text")) or "").lower()
        per = _period(pl)
        if not isinstance(per, int) or per < 1:
            continue
        q = min(per, SLOTS) - 1
        if "no play" in low or "two-point" in low or "two point" in low:
            continue
        is_pass = (" pass " in f" {low} " or "pass" in typ) and "sack" not in low \
            and "sack" not in typ
        is_rush = (typ.startswith("rush") or "rushing" in typ) and not is_pass
        if not (is_pass or is_rush):
            continue
        out["plays"] += 1
        found = names.find(txt, off)
        if not found:
            continue
        out["named"] += 1
        yds = play_yards(pl, txt)
        td = "touchdown" in typ or "touchdown" in low
        sc = SCORING.search(txt)
        if sc and is_pass and "from" in sc.group(1).lower():
            # 'Deebo Samuel 10 Yd pass from Jayden Daniels': receiver first
            at = sc.end()
            passer = next((p for pos, p in found if pos >= at), None)
            rcv = next((p for pos, p in found if pos < sc.start()), None)
            if passer and rcv:
                for who, st in ((passer, "pass_att"), (passer, "pass_cmp"), (rcv, "targets"),
                                (rcv, "rec")):
                    add(who, st, q, 1)
                add(passer, "pass_yds", q, yds)
                add(rcv, "rec_yds", q, yds)
                add(passer, "pass_td", q, 1)
                add(rcv, "td", q, 1)
            continue
        if is_rush:
            r = found[0][1]
            add(r, "carries", q, 1)
            add(r, "rush_yds", q, yds)
            if td:
                add(r, "td", q, 1)
            continue
        passer = found[0][1]
        at = low.find(" to ", low.find("pass"))
        rcv = next((p for pos, p in found if at >= 0 and pos > at and p != passer), None)
        add(passer, "pass_att", q, 1)
        # a spike to stop the clock is an incomplete attempt in the box
        caught = "incomplete" not in low and "intercepted" not in low and "spiked" not in low
        if rcv:
            add(rcv, "targets", q, 1)
        if caught:
            # the passer's completion counts even when the catcher's name
            # is not found (his box does); the catch only when it is
            add(passer, "pass_cmp", q, 1)
            add(passer, "pass_yds", q, yds)
            if td:
                add(passer, "pass_td", q, 1)
            if rcv:
                add(rcv, "rec", q, 1)
                add(rcv, "rec_yds", q, yds)
                if td:
                    add(rcv, "td", q, 1)
            else:
                out["no_receiver"] += 1
                if len(out["no_receiver_texts"]) < 3:
                    out["no_receiver_texts"].append(txt[:160])
    return out


def check(rec, box):
    """{"players", stat: n that add up} — his quarters against his box
    line (box: {pid: {stat: total}}); yards within 1 for rounding."""
    out = {"players": 0}
    for pid, b in (box or {}).items():
        per = (rec.get("players") or {}).get(pid) or {}
        out["players"] += 1
        for st, v in b.items():
            if v is None:
                continue
            got = sum((per.get(st) or [0])) if per else 0
            tol = 1.0 if st.endswith("yds") else 0.0
            out[st] = out.get(st, 0) + int(abs(got - v) <= tol)
            out[f"{st}_n"] = out.get(f"{st}_n", 0) + 1
    return out


# ----------------------------------------------------------------------
# THE 1ST QUARTER / 1ST HALF MODEL (10-22). A player's 1Q / 1H line is his
# GAME projection (the props boards' number) times how a quarter's share
# of that stat actually lands for players projected like him: the
# measured distribution of (his 1Q value / his game projection) on last
# season's first half of weeks, in three projection bands (a 30-yard
# receiver blanks the 1st quarter far more often than a 90-yard one).
# Only player-games whose quarters ADD UP to his box score are used —
# missing is never zero. TESTED on the second half of weeks against his
# OWN 1Q / 1H hit rate over his last 8 games, at a line next to his own
# 1Q / 1H average (as books hang it).
# ----------------------------------------------------------------------
PERIODS = (("q1", "1st quarter", (0,)), ("h1", "1st half", (0, 1)))
Q_STATS = (("pass_yds", "passing yards"), ("pass_cmp", "completions"),
           ("pass_att", "pass attempts"), ("rush_yds", "rushing yards"),
           ("carries", "carries"), ("rec_yds", "receiving yards"), ("rec", "receptions"))
N_QUANT = 101
HIST_N, HIST_MIN = 8, 4


def key(per, stat):
    return f"{per}_{stat}"


def label(per, stat):
    return f"{dict((p, l) for p, l, _i in PERIODS)[per]} {dict(Q_STATS)[stat]}"


def _span(arr, per):
    ix = dict((p, i) for p, _l, i in PERIODS)[per]
    return sum((arr or [0] * SLOTS)[i] for i in ix)


def clean_rows(rows, quarters):
    """[(week, pid, stat, game projection, his quarters)] for every
    player-game in nfl_sim.collect's rows whose quarters add up to his box
    score for that stat (yards within 1)."""
    out = []
    for g in rows or []:
        qg = (quarters or {}).get(str(g.get("event_id")))
        if not qg:
            continue
        for p in g["players"]:
            qa = (qg.get("players") or {}).get(str(p["pid"])) or {}
            for s, _l in Q_STATS:
                mu, y = p["proj"].get(s), p["actual"].get(s)
                if mu is None or y is None or mu <= 0:
                    continue
                arr = qa.get(s) or [0] * SLOTS
                if abs(sum(arr) - y) > (1 if s.endswith("yds") else 0):
                    continue
                out.append((g["week"], str(p["pid"]), s, float(mu), list(arr)))
    return out


def fit(clean, hi):
    """{"q1": {stat: {"edges": [a, b], "q": [[quantiles of value / mu] x 3],
    "share", "n"}}, "h1": ...} from rows in weeks before `hi`."""
    import numpy as np
    out = {}
    for per, _l, _i in PERIODS:
        out[per] = {}
        for s, _sl in Q_STATS:
            xs = [r for r in clean if r[2] == s and r[0] < hi]
            if len(xs) < 150:
                continue
            mus = sorted(r[3] for r in xs)
            edges = [mus[len(mus) // 3], mus[2 * len(mus) // 3]]
            bands = [[], [], []]
            for r in xs:
                b = 0 if r[3] < edges[0] else (1 if r[3] < edges[1] else 2)
                bands[b].append(_span(r[4], per) / r[3])
            grid = np.linspace(0, 1, N_QUANT)
            tot = sum(sum(r[4]) for r in xs)
            out[per][s] = {"edges": [round(e, 2) for e in edges],
                           "q": [[round(float(v), 4) for v in np.quantile(b_, grid)]
                                 for b_ in bands],
                           "share": round(sum(_span(r[4], per) for r in xs) / tot, 4)
                           if tot else None, "n": len(xs)}
    return out


def pmf(model, per, stat, mu, top=None):
    """P(value = k), k = 0..top, for a player projected `mu` for the GAME:
    the measured ratio distribution of his band, scaled by mu."""
    import numpy as np
    m = ((model or {}).get(per) or {}).get(stat)
    if not m or mu is None or mu <= 0:
        return None
    e = m["edges"]
    b = 0 if mu < e[0] else (1 if mu < e[1] else 2)
    q = np.asarray(m["q"][b], dtype=float) * float(mu)
    top = int(top or max(3, math.ceil(q[-1]) + 2))

    def cdf(x):                       # share of the quantile points <= x
        return float(np.searchsorted(q, x, side="right")) / len(q)
    out = []
    prev = 0.0
    for k in range(top + 1):
        c = cdf(k + 0.5) if k < top else 1.0
        out.append(max(0.0, c - prev))
        prev = c
    return out


def test(clean, model, lo):
    """{key(per, stat): {n, model_brier, baseline_brier, verdict,
    calibration, predicted, actual}} on weeks from `lo`."""
    from engines import model_math as mm
    hist = {}
    for r in sorted(clean, key=lambda r: r[0]):
        hist.setdefault((r[1], r[2]), []).append((r[0], r[4]))
    out = {}
    for per, _l, _i in PERIODS:
        for s, _sl in Q_STATS:
            M, B = [], []
            for w, pid, st_, mu, arr in clean:
                if st_ != s or w < lo:
                    continue
                prev = [a for ww, a in hist[(pid, s)] if ww < w][-HIST_N:]
                if len(prev) < HIST_MIN:
                    continue
                pv = [_span(a, per) for a in prev]
                line = math.floor(sum(pv) / len(pv)) + 0.5
                pm = pmf(model, per, s, mu)
                if not pm:
                    continue
                y = 1 if _span(arr, per) > line else 0
                M.append((mm.prob_at_least(pm, int(line) + 1), y))
                B.append((sum(1 for v in pv if v > line) / len(pv), y))
            if not M:
                continue
            sm, sb = mm.score_predictions(M), mm.score_predictions(B)
            out[key(per, s)] = {
                "n": sm["n"], "model_brier": sm["brier"], "baseline_brier": sb["brier"],
                "verdict": mm.paired_verdict([(p - y) ** 2 for p, y in M],
                                             [(q - y) ** 2 for q, y in B]),
                "calibration": mm.calibration_bins(M),
                "predicted": round(sum(p for p, _y in M) / len(M), 4),
                "actual": round(sum(y for _p, y in M) / len(M), 4)}
    return out


def offered(test_block):
    """The 1Q / 1H player markets a bet can be priced on: only those that
    BEAT his own 1Q / 1H rate on unseen games (no false STRONG)."""
    return tuple(k for k, x in (test_block or {}).items()
                 if ((x or {}).get("verdict") or {}).get("verdict") == "beats")


# --- the game: points by quarter -----------------------------------------------------
def team_fit(rows, quarters, hi):
    """{"q1": {"share", "sd"}, "h1": ...} — the share of a team's points
    scored in the span and the spread of the span's MARGIN around the
    game model's margin x share, on weeks before `hi`."""
    import numpy as np
    out = {}
    for per, _l, _i in PERIODS:
        pts = tot = 0.0
        res = []
        for g in rows or []:
            qg = (quarters or {}).get(str(g.get("event_id")))
            if g["week"] >= hi or not qg:
                continue
            lh, la = (qg.get("lines") or {}).get(str(g["home_id"])), \
                (qg.get("lines") or {}).get(str(g["away_id"]))
            if not lh or not la or len(lh) < 4 or len(la) < 4:
                continue
            pts += _span(lh, per) + _span(la, per)
            tot += sum(lh) + sum(la)
            res.append((g, _span(lh, per) - _span(la, per)))
        if tot <= 0 or len(res) < 60:
            continue
        sh = pts / tot
        r = [m - (g["mu_h"] - g["mu_a"]) * sh for g, m in res]
        out[per] = {"share": round(sh, 4), "sd": round(float(np.std(r)), 3), "n": len(res)}
    return out


def team_lines(mu_h, mu_a, tf, per):
    """{"lead_home", "tie", "lead_away", "mu_total"} for the span — the
    margin normal around the game model's margin x share; a tie is the
    band within half a point."""
    from engines import model_math as mm
    t = (tf or {}).get(per)
    if not t:
        return None
    m, sd = (mu_h - mu_a) * t["share"], t["sd"]
    lead = 1 - mm.normal_cdf((0.5 - m) / sd)
    away = mm.normal_cdf((-0.5 - m) / sd)
    return {"lead_home": lead, "lead_away": away, "tie": max(0.0, 1 - lead - away),
            "mu_total": (mu_h + mu_a) * t["share"]}


def team_test(rows, quarters, tf, lo):
    """Home leads after the span: the model vs the league's own rate before
    `lo`. {per + "_lead_home": {...}}."""
    from engines import model_math as mm
    out = {}
    for per, _l, _i in PERIODS:
        base, M, B = [], [], []
        for g in rows or []:
            qg = (quarters or {}).get(str(g.get("event_id")))
            if not qg:
                continue
            lh, la = (qg.get("lines") or {}).get(str(g["home_id"])), \
                (qg.get("lines") or {}).get(str(g["away_id"]))
            if not lh or not la or len(lh) < 4 or len(la) < 4:
                continue
            y = 1 if _span(lh, per) > _span(la, per) else 0
            if g["week"] < lo:
                base.append(y)
                continue
            t = team_lines(g["mu_h"], g["mu_a"], tf, per)
            if t:
                M.append((t["lead_home"], y))
        if not M or not base:
            continue
        br = sum(base) / len(base)
        B = [(br, y) for _p, y in M]
        sm, sb = mm.score_predictions(M), mm.score_predictions(B)
        out[f"{per}_lead_home"] = {
            "n": sm["n"], "model_brier": sm["brier"], "baseline_brier": sb["brier"],
            "verdict": mm.paired_verdict([(p - y) ** 2 for p, y in M],
                                         [(q - y) ** 2 for q, y in B]),
            "predicted": round(sum(p for p, _y in M) / len(M), 4),
            "actual": round(sum(y for _p, y in M) / len(M), 4)}
    return out


def build(rows, quarters, cut):
    """The block the nightly ships: model fitted before `cut`, tested from it."""
    clean = clean_rows(rows, quarters)
    model = fit(clean, cut)
    tf = team_fit(rows, quarters, cut)
    return {"model": model, "test": test(clean, model, cut), "team": tf,
            "team_test": team_test(rows, quarters, tf, cut), "cut_week": cut,
            "clean_rows": len(clean)}
