"""
MLB game model — the reader side.

mlb_model_precompute.py fits the model in CI and writes
data/mlb/model.json; this module reads that file and projects a game.
It makes no network calls and imports no streamlit, so the Game Card,
the MLB Model page and the CI slate builder all share it and the tests
run it bare.

THE STARTER LAYER
-----------------
A starter covers some share of the game and allows runs at some rate;
both come from his real game log, each shrunk toward the league's
starters by a prior the nightly FITTED (see the precompute's docstring):

    outs/start = (his outs + m_o * s_o) / (his starts + s_o)
    RA9        = (his runs + m_r * s_r) / (his innings / 9 + s_r)
    share      = outs/start / 27

His RA9 enters RELATIVE to the league's starters — rate = league runs
per game x (his RA9 / league starter RA9) — so an exactly average
starter leaves the team's number untouched rather than nudging it by
the gap between starter and bullpen run environments.

Only applied when the nightly's walk-forward showed it beat the
team-only model (`use_starters`). Otherwise the card shows team-only
and says so.
"""
import json
from pathlib import Path

from engines import game_model as gm

_ROOTS = (Path(__file__).resolve().parents[2] / "data" / "mlb",
          Path(__file__).resolve().parents[1] / "data" / "mlb")

_memo = {}


def _path():
    for root in _ROOTS:
        p = root / "model.json"
        if p.exists():
            return p
    return None


def load_model():
    """The fitted model dict, or None. A plain memo keyed on the file's
    mtime and size — st.cache_data would re-unpickle the dict on every
    call (the lineup-lock lesson, 08-17)."""
    p = _path()
    if p is None:
        return None
    try:
        st = p.stat()
        key = (str(p), st.st_mtime_ns, st.st_size)
        if key not in _memo:
            _memo.clear()
            _memo[key] = json.loads(p.read_text())
        return _memo[key]
    except Exception:
        return None


def starter_layer(rec, priors, league_rate, prior_rec=None, weights=None):
    """(share, rate) for a starter's season record, or None.

    rec: {"r": runs, "outs": outs, "gs": starts} this season.
    prior_rec: the same for LAST season, counted at the FITTED weights
    {"ra": w, "outs": w} (model_math.fit_prior_weight) — how much a run
    allowed last year is worth next to one this year, measured on the
    starters who pitched both seasons. A pitcher with no starts on record
    in either season returns None (team rate stands) rather than the
    league prior dressed up as his.
    """
    rec = rec or {"r": 0, "outs": 0, "gs": 0}
    pr = prior_rec or {}
    w = weights or {}
    wo, wr = (w.get("outs") or 0.0), (w.get("ra") or 0.0)
    if not priors or not league_rate or not (rec.get("gs") or (pr.get("gs") and (wo or wr))):
        return None
    try:
        so, mo = priors["outs_strength_starts"], priors["outs_mean"]
        sr, mr = priors["ra9_strength_games"], priors["ra9_mean"]
    except KeyError:
        return None
    outs_ps = ((rec["outs"] + wo * (pr.get("outs") or 0) + mo * so)
               / (rec["gs"] + wo * (pr.get("gs") or 0) + so))
    ra9 = ((rec["r"] + wr * (pr.get("r") or 0) + mr * sr)
           / (rec["outs"] / 27.0 + wr * (pr.get("outs") or 0) / 27.0 + sr))
    share = max(0.0, min(1.0, outs_ps / 27.0))
    return share, league_rate * ra9 / mr


def starter_summary(model, pid):
    """What the card prints about a starter: his line and the shrunk
    numbers the model actually used."""
    rec = ((model or {}).get("starters") or {}).get(str(pid)) if pid else None
    prior = ((model or {}).get("starters_prior") or {}).get(str(pid)) if pid else None
    if not rec and not prior:
        return None
    lg = ((model or {}).get("league") or {}).get("league_rate")
    lay = starter_layer(rec, (model or {}).get("starter_priors"), lg, prior,
                        (model or {}).get("starter_prior_weight"))
    if not lay:
        return None
    rec = rec or {"r": 0, "outs": 0, "gs": 0, "name": (prior or {}).get("name")}
    ip = rec["outs"] / 3.0
    return {
        "name": rec.get("name") or (prior or {}).get("name"), "gs": rec["gs"],
        "gs_last_season": (prior or {}).get("gs", 0),
        "ra9_raw": round(rec["r"] * 27.0 / rec["outs"], 2) if rec["outs"] else None,
        "ip_per_start": round(ip / rec["gs"], 1) if rec["gs"] else None,
        "share": round(lay[0], 3),
        "ra9_model": round(lay[1] * model["starter_priors"]["ra9_mean"] / lg, 2),
    }


def project_game(home, away, home_sp=None, away_sp=None, model=None, market=None):
    """Projection dict for one MLB game, or None.

    home/away are statsapi full names ("Atlanta Braves") — the same
    vocabulary the schedule uses everywhere in the app.
    """
    model = model if model is not None else load_model()
    if not model:
        return None
    lg = (model.get("league") or {}).get("league_rate")
    s_h = s_a = None
    used = False
    if model.get("use_starters"):
        pri = model.get("starter_priors")
        sts = model.get("starters") or {}
        stp = model.get("starters_prior") or {}
        wts = model.get("starter_prior_weight")
        s_h = starter_layer(sts.get(str(home_sp)) if home_sp else None, pri, lg,
                            stp.get(str(home_sp)) if home_sp else None, wts) if home_sp else None
        s_a = starter_layer(sts.get(str(away_sp)) if away_sp else None, pri, lg,
                            stp.get(str(away_sp)) if away_sp else None, wts) if away_sp else None
        used = bool(s_h and s_a)
        if not used:
            # One starter known and one not would tilt the game toward
            # whichever side happened to have a record. Both or neither.
            s_h = s_a = None
    try:
        from engines.mlb_run_rates import canonical
        h_ab, a_ab = canonical(home) or "", canonical(away) or ""
    except Exception:
        h_ab = a_ab = ""
    out = gm.project(model, home, away, market=market, s_home=s_h, s_away=s_a,
                     home_abbr=h_ab, away_abbr=a_ab)
    if out is None:
        return None
    out["starters_used"] = used
    out["home_starter"] = starter_summary(model, home_sp)
    out["away_starter"] = starter_summary(model, away_sp)
    return out


def posted_lines():
    """{game_pk: odds} from the slate file slate-picks writes (ESPN's
    posted MLB line, refreshed at 1, 5 and 7 PM ET). Read through
    slate_guard so a past day's lines can never price tonight's game."""
    try:
        from engines.slate_guard import load_slate
        games, _d, _cur = load_slate("mlb")
    except Exception:
        return {}
    return {g.get("game_pk"): g["odds"] for g in games or [] if g.get("odds")}
