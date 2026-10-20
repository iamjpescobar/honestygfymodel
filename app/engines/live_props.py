"""
Live props (10-18) — a player's chance over the REST of a game in
progress, from his pregame projection, the clock, and what he already has.

THE MATH
--------
Pregame, every board prices a stat from a distribution over the whole
game (goals Poisson, shots / counts negative binomial, yards normal).
Live, the question is "will he reach the line from HERE", so:

  - f = the fraction of regulation left (NHL 3 x 20, NFL 4 x 15).
  - Goals, assists, points, touchdowns (Poisson at mean m): what he gets
    from here is Poisson(m * f).
  - Counts with a game-level spread (shots, receptions, carries...):
    negative binomial, size r, mean m. The spread is the game's own
    rate; what he has done so far is evidence about it. The rate's
    gamma is updated on "have in (1 - f) of a game" and the rest of the
    game is negative binomial with size r + have, mean
    (r + have) / (r / m + 1 - f) * f — a hot first half raises the rest.
  - Yards (normal, cv measured per market): the rest is normal with
    mean m * f, sd cv * m * sqrt(f).

  Over line L: he needs k = floor(L) + 1 in all; need = k - have. Need
  <= 0 is already cashed; overtime is not priced (f would be 0, and OT
  props settle differently per book).

UNTESTED, SAID ON THE PAGE
--------------------------
This has not yet been checked against past games period by period, so
by the site's own guard (model_view.guarded_tier) a live call is at most
THIN. The edge is printed in points beside it. NOT in the number: score
effects (a trailing team shoots more and pulls its goalie, a blowout
sits stars), an in-game injury, power plays in progress.

Pure except fetch_summary (requests, imported inside it) — no streamlit.
"""
import math

from engines import espn_feed as ef
from engines import model_math as mm

UNTESTED = {"measured": False, "in_range": False, "n": 0, "untested": True}
REG = {"nhl": (3, 20.0), "nfl": (4, 15.0), "nba": (4, 12.0)}


# ----------------------------------------------------------------------
# The clock
# ----------------------------------------------------------------------
def clock_min(s):
    """Minutes left in the period, None if unreadable: '12:34' -> 12.567,
    '1:05.2' -> 1.087, and ESPN's NBA last-minute shape '45.3' / '0.0'
    (seconds, no colon) -> 0.755 / 0.0. Until 10-20 the colon-less shape
    read as unreadable, so every NBA game's final minute of each quarter
    and halftime showed "Overtime (or a clock the feed did not send)"."""
    t = str(s or "").strip()
    if not t:
        return None
    try:
        if ":" in t:
            m, _, sec = t.partition(":")
            return int(m) + (float(sec) if sec else 0.0) / 60.0
        return float(t) / 60.0
    except (TypeError, ValueError):
        return None


BREAK_WORDS = ("half", "end of", "intermission", "end ")


def remaining(sport, state, period, clock, detail=None):
    """Fraction of regulation left (1.0 before the start, 0.0 at the end),
    or None in overtime / when the clock cannot be read. A break between
    periods ("Halftime", "End of 2nd") with no clock is the period's end."""
    if state == "pre":
        return 1.0
    if state == "post":
        return 0.0
    n, length = REG[sport]
    try:
        p = int(period)
    except (TypeError, ValueError):
        return None
    if p > n:
        return None                       # overtime: not priced
    c = clock_min(clock)
    if c is None and any(w in str(detail or "").lower() for w in BREAK_WORDS):
        c = 0.0
    if c is None:
        return None
    left = (n - p) * length + max(0.0, min(length, c))
    return max(0.0, min(1.0, left / (n * length)))


# ----------------------------------------------------------------------
# What is left
# ----------------------------------------------------------------------
def rest_pmf(kind, mean, f, have=0, size=None, cv=None, top=None):
    """pmf of what he adds from here. kind: 'poisson' | 'nb' | 'normal'."""
    if mean is None or mean <= 0 or f is None or f <= 0:
        return [1.0]
    if kind == "poisson":
        return mm.poisson_pmf(mean * f, max(12, int(mean * f * 6) + 6))
    if kind == "nb":
        if not size:
            return mm.poisson_pmf(mean * f, max(12, int(mean * f * 6) + 6))
        r2 = size + max(0, have)
        beta = size / mean + (1.0 - f)
        m2 = r2 / beta * f
        return mm.nb_pmf(m2, r2, top or max(40, int(m2 * 5) + 10))
    if kind == "normal":
        sd = (cv or 0) * mean * math.sqrt(f)
        mu = mean * f
        if sd <= 0:
            return None
        hi = int(mu + 5 * sd) + 2
        out = []
        for k in range(0, hi + 1):
            lo_c = mm.normal_cdf(k - 0.5, mu, sd) if k > 0 else 0.0
            out.append(mm.normal_cdf(k + 0.5, mu, sd) - lo_c)
        out[-1] += max(0.0, 1.0 - sum(out))
        return out
    raise ValueError(kind)


def need(line, have):
    """What he still needs to go OVER line, given what he has."""
    return int(math.floor(line)) + 1 - int(have or 0)


def over_chance(pmf, still_needs):
    """P(rest >= still_needs); 1.0 when he has already cleared it."""
    if still_needs <= 0:
        return 1.0
    if not pmf:
        return None
    return max(0.0, min(1.0, sum(pmf[still_needs:])))


# ----------------------------------------------------------------------
# ESPN's live game summary
# ----------------------------------------------------------------------
def game_state(summary):
    """{"state", "period", "clock", "detail", "away", "home", "away_score",
    "home_score"} from a summary's header."""
    comp = (((summary or {}).get("header") or {}).get("competitions") or [{}])[0] or {}
    st = comp.get("status") or {}
    t = st.get("type") or {}
    out = {"state": t.get("state") or "pre", "period": st.get("period"),
           "clock": st.get("displayClock"), "detail": t.get("shortDetail") or t.get("detail")}
    for c in comp.get("competitors") or []:
        side = c.get("homeAway")
        if side in ("home", "away"):
            out[side] = (c.get("team") or {}).get("abbreviation")
            out[f"{side}_score"] = ef.num(c.get("score"))
    return out


NHL_LIVE = {"g": (("goals",), ("G",)), "a": (("assists",), ("A",)),
            "sog": (("shotsTotal", "shots"), ("S", "SOG")),
            "toi": (("timeOnIce",), ("TOI",))}
NFL_LIVE = {
    "passing": {"cmp_att": (("completions/passingAttempts",), ("C/ATT", "CMP/ATT")),
                "yds": (("passingYards",), ("YDS",)), "td": (("passingTouchdowns",), ("TD",)),
                "int": (("interceptions",), ("INT",))},
    "rushing": {"att": (("rushingAttempts",), ("CAR", "ATT")),
                "yds": (("rushingYards",), ("YDS",)), "td": (("rushingTouchdowns",), ("TD",))},
    "receiving": {"rec": (("receptions",), ("REC",)), "yds": (("receivingYards",), ("YDS",)),
                  "td": (("receivingTouchdowns",), ("TD",)),
                  "tgt": (("receivingTargets",), ("TGTS", "TAR", "TGT"))},
}


def _skater_group(grp):
    name = str(grp.get("name") or "").lower()
    labels = {str(x).upper() for x in (grp.get("labels") or [])}
    return "goal" not in name and not ("SV" in labels and "SA" in labels)


def nhl_box(summary):
    """{pid: {"g", "a", "pts", "sog"}} so far, skaters only."""
    out = {}
    for blk in (((summary or {}).get("boxscore") or {}).get("players") or []):
        for grp in blk.get("statistics") or []:
            if not _skater_group(grp):
                continue
            idx = ef.box_group_index(grp, NHL_LIVE)
            if not idx:
                continue
            for ent in grp.get("athletes") or []:
                pid = str((ent.get("athlete") or {}).get("id") or "")
                stats = ent.get("stats") or []
                if not pid or not stats:
                    continue
                ln = {k: ef.num(stats[j]) for k, j in idx.items() if j < len(stats) and k != "toi"}
                g, a = ln.get("g") or 0, ln.get("a") or 0
                out[pid] = {"g": int(g), "a": int(a), "pts": int(g + a),
                            "sog": int(ln.get("sog") or 0)}
    return out


def nfl_box(summary):
    """{pid: {stat: so far}} in the NFL board's stat keys."""
    raw = {}
    for blk in (((summary or {}).get("boxscore") or {}).get("players") or []):
        for grp in blk.get("statistics") or []:
            gname = str(grp.get("name") or "").lower()
            wanted = NFL_LIVE.get(gname)
            if not wanted:
                continue
            idx = ef.box_group_index(grp, wanted)
            for ent in grp.get("athletes") or []:
                pid = str((ent.get("athlete") or {}).get("id") or "")
                stats = ent.get("stats") or []
                if not pid or not stats:
                    continue
                cat = raw.setdefault(pid, {}).setdefault(gname, {})
                for k, j in idx.items():
                    if j >= len(stats):
                        continue
                    if k == "cmp_att":
                        c, a = ef.pair(stats[j])
                        cat["cmp"], cat["att"] = c, a
                    else:
                        cat[k] = ef.num(stats[j])
    out = {}
    for pid, c in raw.items():
        ps, ru, rc = c.get("passing") or {}, c.get("rushing") or {}, c.get("receiving") or {}

        def v(d, k):
            return int(d.get(k) or 0)
        out[pid] = {"pass_yds": v(ps, "yds"), "pass_td": v(ps, "td"), "pass_cmp": v(ps, "cmp"),
                    "pass_att": v(ps, "att"), "pass_int": v(ps, "int"),
                    "rush_yds": v(ru, "yds"), "carries": v(ru, "att"),
                    "rec_yds": v(rc, "yds"), "rec": v(rc, "rec"), "targets": v(rc, "tgt"),
                    "scrim_yds": v(ru, "yds") + v(rc, "yds"),
                    "td": v(ru, "td") + v(rc, "td")}
    return out


# ----------------------------------------------------------------------
# One player, one line
# ----------------------------------------------------------------------
NHL_KIND = {"g": "poisson", "a": "poisson", "pts": "poisson", "sog": "nb"}


def nhl_chance(mu, stat, line, have, f, sog_size=None):
    """(over chance for the rest of the game, still needs) for one skater."""
    nd = need(line, have)
    if nd <= 0:
        return 1.0, nd
    m = (mu or {}).get("g", 0) + (mu or {}).get("a", 0) if stat == "pts" else (mu or {}).get(stat)
    pmf = rest_pmf(NHL_KIND[stat], m, f, have=have, size=sog_size if stat == "sog" else None)
    return over_chance(pmf, nd), nd


def nfl_chance(mean, market, spreads, line, have, f):
    """(over chance for the rest of the game, still needs) for one player.
    market None = touchdowns (Poisson); else the measured spread decides."""
    nd = need(line, have)
    if nd <= 0:
        return 1.0, nd
    if market is None:
        return over_chance(rest_pmf("poisson", mean, f), nd), nd
    sp = (spreads or {}).get(market)
    if not sp:
        return None, nd
    if sp.get("kind") == "count":
        pmf = rest_pmf("nb", mean, f, have=have, size=sp.get("size"))
    else:
        pmf = rest_pmf("normal", mean, f, cv=sp.get("cv"))
    return over_chance(pmf, nd), nd


def nba_have(summary):
    """{pid: {stat: so far}} in engines/nba_model's stat keys, combos summed."""
    from engines import nba_box as nbx
    from engines import nba_model as nmod
    out = {}
    for pid, ln in nbx.parse(summary).items():
        d = {k: int(ln.get(k) or 0) for k in nmod.BASE}
        for c, parts in nmod.COMBOS.items():
            d[c] = sum(d[x] for x in parts)
        out[pid] = d
    return out


def nba_chance(mean, size, line, have, f):
    """(over chance for the rest of the game, still needs) for one player:
    negative binomial with the game rate updated on what he has."""
    nd = need(line, have)
    if nd <= 0:
        return 1.0, nd
    return over_chance(rest_pmf("nb", mean, f, have=have, size=size), nd), nd


# ----------------------------------------------------------------------
# The test's verdict (data/nhl/live_check.json, nhl_live_check.py)
# ----------------------------------------------------------------------
NHL_CHECK_KEY = {("g", 0.5): "g1", ("g", 1.5): "g2", ("pts", 0.5): "pt1",
                 ("pts", 1.5): "pt2", ("a", 0.5): "a1"}


def tested(check, stat, line, raw):
    """(chance, support) for one live call. A market whose live test
    BEAT the naive read gets its delivered chance and its curve's support
    (so VALUE / STRONG are possible inside the graded range); every other
    call keeps the raw chance and UNTESTED (THIN at most)."""
    from engines import model_view as mv
    from engines import top_plays_board as tpb
    key = NHL_CHECK_KEY.get((stat, float(line)))
    m = ((check or {}).get("markets") or {}).get(key) if key else None
    if not m or ((m.get("verdict") or {}).get("verdict")) != "beats" or raw is None:
        return raw, UNTESTED
    bins = m.get("calibration")
    c = tpb.calibrate(raw, bins) if bins else None
    return (c if c is not None else raw), mv.curve_support(raw, bins)


def load_check(path=None):
    """data/nhl/live_check.json, or {} before the test has run."""
    import json
    from pathlib import Path
    p = Path(path) if path else Path(__file__).resolve().parents[2] / "data" / "nhl" / "live_check.json"
    try:
        return json.loads(p.read_text())
    except Exception:  # noqa: BLE001 — no test yet is "untested", not an error
        return {}


# ----------------------------------------------------------------------
# The one network read (the view caches it 30 s)
# ----------------------------------------------------------------------
_SUMMARY = "https://{host}/apis/site/v2/sports/{path}/summary"
_HOSTS = ("site.web.api.espn.com", "site.api.espn.com")


def fetch_summary(sport, event_id, _get=None, timeout=8):
    """ESPN's live game summary, or None. Both hosts, one try each, a
    short timeout — a page never waits long on ESPN."""
    import requests
    path = {"nhl": "hockey/nhl", "nfl": "football/nfl", "nba": "basketball/nba"}[sport]
    for host in _HOSTS:
        url = _SUMMARY.format(host=host, path=path)
        try:
            if _get:
                return _get(url, {"event": event_id})
            r = requests.get(url, params={"event": event_id}, timeout=timeout,
                             headers={"User-Agent": "Mozilla/5.0"})
            r.raise_for_status()
            return r.json()
        except Exception:  # noqa: BLE001 — next host, then nothing
            continue
    return None
