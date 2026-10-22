"""
NBA roster-aware game margin (10-22) — the team ratings know what a TEAM
scored; they do not know who is playing tonight. Every team made an
offseason move, and a star out tonight is not in a rating.

THE ROSTER NUMBER: tonight's players' own projections (engines/nba_model,
before the game context), their minutes scaled so the team plays 240:
    roster points = sum(projected points) x 240 / sum(projected minutes)
A player who plays with no projection yet counts LOW_MIN minutes at
LOW_PTS points (a debut is a bench role more often than not).

THE BLEND: the game model's margin moves a share W toward the roster's
margin; the total stays the ratings' (MEASURED 10-22 on 2025-26: the
roster total did not help — 15.3 vs 15.3 MAE on the fit window, worse on
the test — while the margin did: MAE 11.84 -> 11.45 on the fit window,
paired z 3.4). W is fitted on the fit window by squared margin error and
SHIPS only when it beats the ratings alone on the unseen window (last
season's final 45 days + this season so far): paired on the win
chance's squared error. Until then W is 0 and Tonight shows the roster
margin beside the model's as information only.

Backtest note: "who plays" there is who played (a healthy scratch is not
in it); tonight it is the roster minus Out.

Pure — no streamlit, no requests.
"""
from engines import model_math as mm
from engines import nba_model as nm

W_GRID = (0.0, 0.1, 0.2, 0.3, 0.4, 0.5)
LOW_MIN = 10.0
LOW_PTS = 4.0
TEAM_MIN = 240.0


def roster_points(players):
    """players: [(projected minutes or None, projected points or None)]
    for everyone who plays -> the team's points, minutes summed to 240."""
    m = p = 0.0
    for mn, pt in players or []:
        if mn is None or pt is None:
            mn, pt = LOW_MIN, LOW_PTS
        m += mn
        p += pt
    return p * TEAM_MIN / m if m > 0 else None


def team_points(players, model):
    """{(team, date): roster points} walk-forward over every game in the
    file — each player's projection from his games before."""
    acc = {}
    lr = model.get("league") or {}
    for p in (players or {}).values():
        run = nm.Running(model["hl"], model.get("hl_long"))
        lrg = lr.get(nm.group(p.get("pos"))) or {}
        for g in sorted(p.get("games") or [], key=lambda x: x[0]):
            if nm.val(g, "min"):
                pr = run.project(model["k"], lrg, model.get("k_long"),
                                 model.get("down_pull") or 0.0) if run.n >= 1 else None
                acc.setdefault((str(g[1]), g[0]), []).append(
                    (pr["min"], pr["mu"]["pts"]) if pr else (None, None))
            run.add(g)
    return {k: roster_points(v) for k, v in acc.items()}


def blend_margin(model_margin, roster_margin, w):
    if roster_margin is None or not w:
        return model_margin
    return (1 - w) * model_margin + w * roster_margin


def fit(players, finals, model, gm_params, fit_window, test_window):
    """{"w", "w_tried", "n_fit", "n_test", "test": verdict (win chance),
    "margin_test": verdict (squared margin), "mae": {...}} or None.
    finals: game-model rows {"date", "home", "away", "hs", "as"} (last
    season + this one); gm_params: the NBA game model's params."""
    from engines import game_model as gm
    from engines import nfl_game_model as ngm
    tp = team_points(players, model)
    fin = gm.clean_finals(finals)
    preds = ngm._wf(fin, gm_params["shrink_k"])
    sd = gm_params["sd_margin"]
    rows = []
    for p in preds:
        rh, ra = tp.get((str(p["home"]), p["date"])), tp.get((str(p["away"]), p["date"]))
        if rh is None or ra is None:
            continue
        rows.append((p["date"], p["mu_h"] - p["mu_a"], rh - ra, p["hs"] - p["as"]))
    F = [r for r in rows if fit_window[0] <= r[0] < fit_window[1]]
    T = [r for r in rows if r[0] >= test_window[0]]
    if len(F) < 100 or len(T) < 100:
        return None

    def sq(sub, w):
        return [(blend_margin(m, rm, w) - y) ** 2 for _d, m, rm, y in sub]
    w = min(W_GRID, key=lambda x: sum(sq(F, x)))
    out = {"w_tried": w, "w": 0.0, "n_fit": len(F), "n_test": len(T),
           "mae": {"ratings": round(sum(abs(m - y) for _d, m, _r, y in T) / len(T), 2),
                   "roster": round(sum(abs(r - y) for _d, _m, r, y in T) / len(T), 2),
                   "blend": round(sum(abs(blend_margin(m, r, w) - y)
                                      for _d, m, r, y in T) / len(T), 2)}}
    if not w:
        return out
    win = [1 if y > 0 else 0 for *_x, y in T]
    a = [(mm.normal_cdf(blend_margin(m, r, w), 0, sd) - h) ** 2
         for (_d, m, r, _y), h in zip(T, win)]
    b = [(mm.normal_cdf(m, 0, sd) - h) ** 2 for (_d, m, _r, _y), h in zip(T, win)]
    out["test"] = mm.paired_verdict(a, b)
    out["margin_test"] = mm.paired_verdict(sq(T, w), sq(T, 0.0))
    if out["test"].get("verdict") == "beats":
        out["w"] = w
    return out
