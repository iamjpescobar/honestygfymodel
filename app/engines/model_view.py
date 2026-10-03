"""
How a model's output is drawn — one renderer for every sport.

The game card (projected score, win %, fair line, market gap), the "how
it's tested" panel, and the prop table look the same on MLB, NHL and
NFL, because a reader who learns to read one should be able to read
all three. Visual tokens only (kc_theme COLOR / --lc-* vars), per the
README.

THE TESTED PANEL IS NOT OPTIONAL
--------------------------------
Every projection on the site is shown beside its walk-forward record —
how it did on games it had not seen, against the baseline a reader
already has. A model that does not beat its baseline is still shown
(hiding it would hide the finding), but the card says so in the first
line of the panel, not in a footnote.
"""
import pandas as pd
import streamlit as st

from engines import model_math as mm
from engines import model_picks as mpk
from engines import value as vl
from styles.kc_theme import COLOR

DASH = "—"


def _pct(p, nd=1):
    return DASH if p is None else f"{100.0 * p:.{nd}f}%"


def _sign(v, nd=1):
    if v is None:
        return DASH
    return f"{'+' if v > 0 else ''}{100.0 * v:.{nd}f}"


def tested_line(validation, baseline_name="a coin flip"):
    """One sentence a reader can hold the model to."""
    v = validation or {}
    if not v.get("n"):
        return "Not yet tested — not enough finals this season to score it."
    m = (v.get("model") or {}).get("log_loss")
    c = (v.get("coin_flip") or {}).get("log_loss")
    h = (v.get("home_rate") or {}).get("log_loss")
    verdict = ("beats" if v.get("beats_coin") and v.get("beats_home_rate")
               else "does NOT beat")
    return (f"Tested on {v['n']:,} games it had not seen ({v.get('from')} → {v.get('to')}): "
            f"{verdict} the baselines — log loss {m} vs coin flip {c}, "
            f"vs always-take-the-home-rate {h} (lower is better). "
            f"The favourite it named won {v.get('favourite_won_pct')}% of the time.")


def render_game_projection(proj, away_label, home_label, key, note=None):
    """The card for one game. proj is game_model.project()'s dict."""
    if not proj:
        st.caption("No projection — one of these teams has no finals on record yet.")
        return
    ph, pa = proj["p_home"], proj["p_away"]
    fav_home = ph >= pa
    c_fav = COLOR["stat_high"]
    c_dim = COLOR["text_muted"]

    def side(label, score, p, fair, fav):
        col = c_fav if fav else c_dim
        return (f'<div style="flex:1; min-width:0;">'
                f'<div style="font-size:var(--lc-text-small); color:{COLOR["text_muted"]}; '
                f'white-space:nowrap; overflow:hidden; text-overflow:ellipsis;">{label}</div>'
                f'<div style="font-size:var(--lc-text-title); font-weight:800; color:{COLOR["text"]};">{score:.2f}</div>'
                f'<div style="font-weight:700; color:{col};">{_pct(p)} '
                f'<span style="font-weight:500; color:{COLOR["text_muted"]};">fair {mm.fmt_american(fair)}</span></div>'
                f'</div>')

    html = ('<div style="display:flex; gap:var(--lc-space-md); align-items:flex-end;">'
            + side(away_label, proj["away_score"], pa, proj.get("fair_away"), not fav_home)
            + f'<div style="color:{COLOR["text_faint"]}; padding-bottom:6px;">@</div>'
            + side(home_label, proj["home_score"], ph, proj.get("fair_home"), fav_home)
            + f'<div style="flex:1; min-width:0; text-align:right;">'
              f'<div style="font-size:var(--lc-text-small); color:{COLOR["text_muted"]};">Projected total</div>'
              f'<div style="font-size:var(--lc-text-title); font-weight:800; color:{COLOR["text"]};">{proj["total"]:.1f}</div>'
              f'</div></div>')
    st.markdown(html, unsafe_allow_html=True)

    bits = []
    if proj.get("market_home") is not None:
        edge = proj.get("edge_home")
        who = home_label if edge >= 0 else away_label
        bits.append(f"Market (no-vig) {away_label} {_pct(proj['market_away'])} / "
                    f"{home_label} {_pct(proj['market_home'])} · model gap "
                    f"{_sign(abs(edge))} pts toward {who}")
    if proj.get("market_total") is not None:
        bits.append(f"Total {proj['market_total']:g}: over {_pct(proj.get('p_over'))} "
                    f"(fair {mm.fmt_american(proj.get('fair_over'))}) / under "
                    f"{_pct(None if proj.get('p_over') is None else 1 - proj['p_over'])} "
                    f"(fair {mm.fmt_american(proj.get('fair_under'))})")
    if note:
        bits.append(note)
    if bits:
        st.caption(" · ".join(bits))


def render_validation(validation, key, extra=None, total_unit="runs"):
    """Expander with the walk-forward record and calibration curve."""
    v = validation or {}
    with st.expander("How this model is tested", expanded=False):
        st.markdown(tested_line(v))
        if v.get("n"):
            st.markdown(
                f"Projected totals: average miss **{v.get('total_mae_model')} {total_unit}** "
                f"vs **{v.get('total_mae_league_avg')}** for the league-average total "
                f"— {'better' if v.get('total_beats_league_avg') else 'NOT better'} "
                f"than just guessing the average.")
            cal = v.get("calibration") or []
            if cal:
                st.caption("Calibration — when the model said X%, how often the home side won:")
                df = pd.DataFrame([{"Model said": c["band"], "Games": c["n"],
                                    "Avg predicted": _pct(c["predicted"]),
                                    "Actually won": _pct(c["actual"])} for c in cal])
                st.dataframe(df, hide_index=True, width="stretch", key=f"cal_{key}")
        for line in extra or []:
            st.caption(line)


def render_prop_table(rows, columns, verdicts, key, favor_note=None):
    """rows: list of dicts already holding display strings. columns:
    [(market_key, header)] — a header gets a trailing ' *' when that
    market did NOT beat its baseline in the walk-forward. Keys starting
    with '_' (raw probabilities for the value tool) are not drawn."""
    if not rows:
        st.caption("No prop projections for this side yet.")
        return
    df = pd.DataFrame([{k: v for k, v in r.items() if not str(k).startswith("_")}
                       for r in rows])
    def _ok(v):
        return v is True or v == "beats"
    render_trust_row([(h, (verdicts.get(k) if isinstance(verdicts.get(k), str) or verdicts.get(k) is None
                          else ("beats" if verdicts.get(k) else "fails")))
                      for k, h in columns])
    rename = {}
    for k, header in columns:
        if k in df.columns:
            rename[k] = header if _ok(verdicts.get(k)) else f"{header} *"
    df = df.rename(columns=rename)
    st.dataframe(df, hide_index=True, width="stretch", key=f"props_{key}")
    flagged = [h for k, h in columns if k in rename and not _ok(verdicts.get(k))]
    if flagged:
        st.caption("* did not beat the player's own hit rate on games it had not seen "
                   "— shown, but don't lean on it: " + ", ".join(flagged) + ".")
    if favor_note:
        st.caption(favor_note)


def mlb_lineup_props(batters, opp_pitcher_id):
    """(rows, verdicts, note) for a lineup against tonight's starter.

    batters: roster.py lineup entries ({"id","name","battingOrder",...}).
    Rows are display-ready. Reads each player's season parquet through
    the app's existing cached loaders — the same frames the Game Card's
    profiles already hold, so on that page this is no extra I/O.
    """
    from engines import mlb_props as mp
    from engines.statcast_engine import _get_batter_df, _get_pitcher_df
    from engines.lineup_slot import _slot_from_batting_order

    pm = mp.load_prop_model()
    if not pm:
        return [], {}, ("The prop model is built by the nightly run and is not in this "
                        "deploy yet — it appears after the next nightly.")
    p_counts = None
    bf_dist = None
    if opp_pitcher_id:
        try:
            p_df, _err = _get_pitcher_df(int(opp_pitcher_id))
            p_counts = mp.outcome_counts(p_df)
        except Exception:
            p_counts = None
        bf_dist = mp.starter_bf_dist((pm.get("starter_bf") or {}).get(str(opp_pitcher_id)), pm)
    # One bat per slot. The projected lineup is last game's boxscore, and
    # a substitute carries his starter's slot (battingOrder 201 -> 2), so
    # without this a slot can appear twice (the 08-17 duplicate-ORD
    # finding) and both would be priced as if each batted there all game.
    seen, ordered = set(), []
    for i, b in enumerate(batters or []):
        slot = _slot_from_batting_order(b.get("battingOrder")) or (i + 1)
        if slot in seen or not (1 <= slot <= 9):
            continue
        seen.add(slot)
        ordered.append((slot, b))
    ordered.sort(key=lambda x: x[0])
    rows = []
    for slot, b in ordered:
        try:
            b_df, _err = _get_batter_df(int(b["id"]))
        except Exception:
            b_df = None
        b_counts = mp.outcome_counts(b_df)
        if not b_counts.get("PA"):
            # MISSING IS NOT ZERO (rule 6). With no PAs on record the
            # shrinkage would hand him exactly the league average, and a
            # league-average line under his name reads as a measurement of
            # him. Listed, priced as nothing.
            row = {"#": slot, "Batter": b.get("name"), "PA": 0, "Exp PA": DASH}
            for k, *_ in mp.MARKETS:
                row[k] = DASH
            rows.append(row)
            continue
        proj = mp.project_batter(slot, b_counts, p_counts, pm, bf_dist)
        if not proj:
            continue
        row = {"#": slot, "Batter": b.get("name"), "PA": proj["pa"], "Exp PA": proj["exp_pa"],
               "_name": b.get("name"), "_probs": proj["probs"]}
        for k, *_ in mp.MARKETS:
            row[k] = prob_cell(proj["probs"][k])
        rows.append(row)
    note = None
    if opp_pitcher_id and not (p_counts and p_counts.get("PA")):
        note = "Tonight's starter has no Statcast record — every PA priced against a league-average arm."
    elif not opp_pitcher_id:
        note = "Starter not announced — every PA priced against a league-average arm."
    return rows, mp.market_verdicts(pm), note


MLB_PROP_COLUMNS = (("h1", "Hits O0.5"), ("h2", "Hits O1.5"), ("tb2", "TB O1.5"),
                    ("hr1", "HR O0.5"), ("k1", "K O0.5"))

MLB_PROP_FOOTNOTE = (
    "Each cell: chance he clears the line, and the fair price at that chance. "
    "Built plate appearance by plate appearance — his rates against tonight's "
    "starter for as long as that starter usually lasts, then a league-average bullpen. "
    "NOT in the number: park, weather, platoon split, the specific relievers.")


def prob_cell(p):
    """'64% (-178)' — probability with its fair price."""
    if p is None:
        return DASH
    return f"{100.0 * p:.0f}% ({mm.fmt_american(mm.fair_american(p))})"


# ----------------------------------------------------------------------
# Value and staking
# ----------------------------------------------------------------------
_FRACTIONS = {"1/8 Kelly": 0.125, "1/4 Kelly": 0.25, "1/2 Kelly": 0.5}
_CAPS = {"1%": 0.01, "2%": 0.02, "3%": 0.03, "5%": 0.05}


def staking_controls(key):
    """Bankroll, Kelly fraction and per-bet cap — shared across every
    model page through session state, so it is set once per visit."""
    ss = st.session_state
    ss.setdefault("lc_bankroll", 0.0)
    ss.setdefault("lc_kelly", "1/4 Kelly")
    ss.setdefault("lc_cap", "2%")
    with st.expander("Your bankroll & staking", expanded=not ss["lc_bankroll"]):
        c1, c2, c3 = st.columns(3)
        c1.number_input("Bankroll ($)", min_value=0.0, step=50.0, key="lc_bankroll",
                        help="Leave at 0 to see value without stake sizes.")
        c2.selectbox("Stake size", list(_FRACTIONS), key="lc_kelly",
                     help="A fraction of the Kelly stake. Kelly assumes the model's "
                          "probability is exact; it never is, so bet a fraction.")
        c3.selectbox("Max per bet", list(_CAPS), key="lc_cap",
                     help="Hard ceiling as a share of bankroll, whatever Kelly says.")
        st.caption("A bet has VALUE only when the model's chance beats the price's break-even. "
                   "Stakes = your Kelly fraction of the model's edge, capped. The model's edge "
                   "over a coin flip is small and still being graded (Results \u2192 Model "
                   "picks) \u2014 size accordingly.")
    return ss["lc_bankroll"], _FRACTIONS[ss["lc_kelly"]], _CAPS[ss["lc_cap"]]


def current_staking():
    """The staking settings WITHOUT drawing the controls — for a second
    consumer on a page that already drew them (two staking_controls()
    calls on one page would be a duplicate-widget-key crash)."""
    ss = st.session_state
    return (ss.get("lc_bankroll") or 0.0, _FRACTIONS[ss.get("lc_kelly", "1/4 Kelly")],
            _CAPS[ss.get("lc_cap", "2%")])


def _bet_label(b, away, home):
    if b["market"] == "moneyline":
        return f"{home if b['side'] == 'home' else away} ML"
    if b["market"] == "total":
        return f"{'Over' if b['side'] == 'over' else 'Under'} {b['line']:g}"
    team = home if b["side"] == "home" else away
    return f"{team} {b['line']:+g}"


def render_value_panel(proj, odds, away, home, key, staking, validation=None):
    """Model % vs price for every side the model prices. Prices default
    to the posted line where there is one; type your own book's price in
    the Price column and the row recomputes."""
    bets = mpk.candidate_bets(proj, odds)
    if not bets:
        return
    bankroll, frac, cap = staking
    ed_key = f"val_{key}"
    edits = (st.session_state.get(ed_key) or {}).get("edited_rows") or {}
    rows, tiers, trusts = [], [], []
    for i, b in enumerate(bets):
        price = (edits.get(i) or {}).get("Price", b["price"])
        if isinstance(price, float) and price != price:      # NaN = empty cell
            price = None
        a = vl.assess(b["p"], price, bankroll or None, frac, cap) if price not in (None, "") else None
        tiers.append(edge_tier(a["edge"] if a else None, bool(a and a["value"])))
        trusts.append(market_trust(validation, b["market"]))
        rows.append({
            "Tier": TIER_STYLE[tiers[-1]][0],
            "Bet": _bet_label(b, away, home),
            "Model": f"{100 * b['p']:.1f}%",
            "Fair": mm.fmt_american(mm.fair_american(b["p"])),
            # An EMPTY cell, not the word "None", where no price was
            # posted — the reader types his book's price there.
            "Price": float("nan") if price in (None, "") else price,
            "Break-even": f"{100 * a['break_even']:.1f}%" if a else DASH,
            "Edge": f"{100 * a['edge']:+.1f}" if a else DASH,
            "EV / $100": f"{a['ev_per_100']:+.2f}" if a else DASH,
            "Stake": (f"${a['stake']:.2f}" if a and a.get("stake") else
                      ("\u2014" if not a or not bankroll else "$0 (no value)")),
            "Trust": TRUST_STYLE.get(trusts[-1], TRUST_STYLE[None])[0],
        })
    df = pd.DataFrame(rows)
    st.data_editor(
        # The editable Price column ignores Styler formatting, and an empty
        # editable number cell shows Streamlit's grey "None" placeholder —
        # never a filled-in price (no posted price is never assumed -110).
        # The caption below says what that placeholder means.
        _tier_styler(df, tiers, trusts),
        key=ed_key, hide_index=True, width="stretch",
        disabled=[c for c in df.columns if c != "Price"],
        column_config={"Price": st.column_config.NumberColumn(
            "Price", help="American odds at YOUR book. Posted line pre-filled where ESPN has one.",
            step=1, format="%d")})
    st.caption("Row colour = your edge at that price (STRONG / VALUE / THIN; no tint = no value). "
               "Trust = how that market tested. Tap Price to enter your book's number \u2014 a "
               "grey \u201cNone\u201d there means ESPN posted no price for that side.")


def render_prop_value_tool(rows, markets, key, staking, name_key="_name"):
    """Pick a player and a market, enter your book's price, get the
    verdict and stake. rows carry '_probs' {market_key: p}."""
    rows = [r for r in rows if r.get("_probs")]
    if not rows:
        return
    bankroll, frac, cap = staking
    st.markdown("**Check a prop at your price**")
    c1, c2, c3 = st.columns([2, 2, 1])
    names = [r[name_key] for r in rows]
    who = c1.selectbox("Player", names, key=f"pv_who_{key}")
    labels = {k: lab for k, lab in markets}
    mkt = c2.selectbox("Market", list(labels), format_func=lambda k: labels[k],
                       key=f"pv_mkt_{key}")
    price = c3.number_input("Price", value=-110, step=5, key=f"pv_px_{key}")
    p = next(r for r in rows if r[name_key] == who)["_probs"].get(mkt)
    a = vl.assess(p, price, bankroll or None, frac, cap) if p is not None else None
    if not a:
        st.caption("Enter an American price of -100 or lower, or +100 or higher.")
        return
    _tl, _tfg, _tbg = TIER_STYLE[edge_tier(a["edge"], a["value"])]
    verdict = (f'<span style="color:{_tfg}; font-weight:800;">{_tl}</span>'
               if a["value"] else "no value")
    stake_txt = (f" \u00b7 stake ${a['stake']:.2f}" if a["value"] and a.get("stake")
                 else "")
    st.markdown(f"{who} \u00b7 {labels[mkt]}: model **{100 * p:.1f}%** vs break-even "
                f"{100 * a['break_even']:.1f}% at {mm.fmt_american(int(price))} \u2192 "
                f"**{verdict}** (edge {100 * a['edge']:+.1f} pts, EV {a['ev_per_100']:+.2f} "
                f"per $100){stake_txt}", unsafe_allow_html=True)


# ----------------------------------------------------------------------
# Colour: what to DO (edge tier) and how far to TRUST it (verdict)
# ----------------------------------------------------------------------
# Edge tiers share their cut points with the Results scorecard
# (model_picks.EDGE_BUCKETS) so a row's colour names the bucket its
# record is graded in. Colours are kc_theme tokens; every colour also
# carries a text label, so nothing rests on colour alone.
TIER_STYLE = {
    "strong": ("STRONG", COLOR["stat_high"], COLOR["stat_high_dim"]),
    "value": ("VALUE", COLOR["gold"], COLOR["warn_dim"]),
    # Grey, not a third blue: on the first screenshot steel-blue THIN read
    # as a paler STRONG — a weak edge must not look like a strong one.
    "thin": ("THIN", COLOR["text_muted"], "rgba(152, 163, 173, 0.12)"),
    "none": ("\u2014", COLOR["text_faint"], None),
}
TRUST_STYLE = {
    "beats": ("BEATS BASELINE", COLOR["accent"], COLOR["accent_dim"], COLOR["accent_border"]),
    "thin": ("THIN EDGE", COLOR["warn"], COLOR["warn_dim"], COLOR["warn_border"]),
    "fails": ("NOT PROVEN", COLOR["error"], COLOR["error_dim"], COLOR["error_border"]),
    None: ("UNTESTED", COLOR["text_muted"], "transparent", COLOR["border"]),
}


def edge_tier(edge, is_value):
    if not is_value or edge is None:
        return "none"
    # On the 0.1-point grid the page prints. Raw 1.997 points showed as
    # "+2.0" under a THIN label; the picks log stores edge to 4 decimals
    # (0.0200), which Results buckets as VALUE — so the label follows the
    # number the reader sees, and agrees with the record.
    edge = round(edge, 3)
    names = ("thin", "value", "strong")          # in EDGE_BUCKETS order
    for name, (lo, hi, _label) in zip(names, mpk.EDGE_BUCKETS):
        if lo <= edge < hi:
            return name
    return "strong"


def market_trust(validation, market):
    """'beats' / 'thin' / 'fails' / None for one game-model market.

    Reads the paired-significance verdict the nightly writes; a model
    file from before verdicts existed falls back to the plain beat/fail
    booleans (never 'thin' — that needs the significance test)."""
    v = validation or {}
    key = {"moneyline": "ml_verdict", "total": "total_verdict",
           "spread": "spread_verdict"}.get(market)
    verdict = ((v.get(key) or {}).get("verdict")) if key else None
    if verdict:
        return verdict
    if not v.get("n"):
        return None
    if market == "moneyline":
        return "beats" if (v.get("beats_coin") and v.get("beats_home_rate")) else "fails"
    if market == "total":
        return "beats" if v.get("total_beats_league_avg") else "fails"
    if market == "spread":
        b = v.get("margin_beats_home_edge")
        return None if b is None else ("beats" if b else "fails")
    return None


def prop_trust(prop_validation, key):
    x = (prop_validation or {}).get(key) or {}
    verdict = (x.get("verdict") or {}).get("verdict")
    if verdict:
        return verdict
    if "beats_baseline" in x:
        return "beats" if x["beats_baseline"] else "fails"
    return None


def trust_pill(verdict, prefix=""):
    label, fg, bg, border = TRUST_STYLE.get(verdict, TRUST_STYLE[None])
    return (f'<span style="display:inline-block; padding:1px 8px; border-radius:999px; '
            f'border:1px solid {border}; background:{bg}; color:{fg}; '
            f'font-size:var(--lc-text-tiny); font-weight:700; letter-spacing:0.04em; '
            f'white-space:nowrap;">{prefix}{label}</span>')


def render_trust_row(items):
    """items: [(label, verdict)] — one line of pills."""
    parts = [f'<span style="color:{COLOR["text_muted"]}; font-size:var(--lc-text-small);">'
             f'{lab}</span> {trust_pill(v)}' for lab, v in items]
    st.markdown('<div style="display:flex; flex-wrap:wrap; gap:6px 14px; align-items:center; '
                'margin:2px 0 6px;">' + "".join(f"<span>{p}</span>" for p in parts) + "</div>",
                unsafe_allow_html=True)


def render_model_legend():
    sw = []
    for key in ("strong", "value", "thin"):
        label, fg, bg = TIER_STYLE[key]
        lo, hi, rng = mpk.EDGE_BUCKETS[{"thin": 0, "value": 1, "strong": 2}[key]]
        sw.append(f'<span style="display:inline-flex; align-items:center; gap:5px;">'
                  f'<span style="width:12px; height:12px; border-radius:3px; background:{bg}; '
                  f'border:1px solid {fg};"></span><span style="color:{fg}; font-weight:700; '
                  f'font-size:var(--lc-text-tiny);">{label}</span><span style="color:'
                  f'{COLOR["text_muted"]}; font-size:var(--lc-text-tiny);">{rng} edge</span></span>')
    pills = " ".join(trust_pill(v) for v in ("beats", "thin", "fails"))
    st.markdown(
        '<div style="display:flex; flex-wrap:wrap; gap:8px 18px; align-items:center;">'
        + "".join(sw) + "</div>"
        f'<div style="margin-top:6px; display:flex; flex-wrap:wrap; gap:6px; align-items:center;">'
        f'{pills}</div>'
        f'<div style="color:{COLOR["text_faint"]}; font-size:var(--lc-text-tiny); margin-top:4px; '
        f'line-height:1.6;">Row colour = your edge at the price (the same buckets Results grades). '
        f'Badge = how that market tested on games it had not seen: beats its baseline by more than '
        f'noise ({mm.SIGNIFICANCE_Z:g} standard errors), better but within noise, or not better.'
        f'</div>', unsafe_allow_html=True)


def _tier_styler(df, tiers, trusts=None):
    """Row background by tier, Tier/Trust cells in their colours."""
    def row_style(row):
        t = tiers[row.name]
        _l, fg, bg = TIER_STYLE[t]
        base = [f"background-color: {bg}" if bg else ""] * len(row)
        for i, col in enumerate(row.index):
            if col == "Tier":
                base[i] += f"; color: {fg}; font-weight: 700"
            if col == "Trust" and trusts is not None:
                tl, tfg, _b, _br = TRUST_STYLE.get(trusts[row.name], TRUST_STYLE[None])
                base[i] += f"; color: {tfg}; font-weight: 700"
        return base
    return df.style.apply(row_style, axis=1)


def render_best_value(entries, validation, staking, key, prop_note=None):
    """'Best value tonight': every side with a POSTED price and positive
    EV across the slate, strongest edge first, coloured like the rows.
    entries: [{"label","away","home","proj","odds"}]."""
    bankroll, frac, cap = staking
    rows = []
    for e in entries:
        for b in mpk.candidate_bets(e.get("proj"), e.get("odds")):
            if b["price"] is None:
                continue
            a = vl.assess(b["p"], b["price"], bankroll or None, frac, cap)
            if not a or not a["value"]:
                continue
            rows.append((a["edge"], {
                "Game": e["label"], "Bet": _bet_label(b, e["away"], e["home"]),
                "Model": f"{100 * b['p']:.1f}%", "Price": mm.fmt_american(b["price"]),
                "Edge": f"{100 * a['edge']:+.1f}", "EV / $100": f"{a['ev_per_100']:+.2f}",
                "Stake": f"${a['stake']:.2f}" if a.get("stake") else "\u2014",
                "Tier": TIER_STYLE[edge_tier(a["edge"], True)][0],
                "Trust": TRUST_STYLE.get(market_trust(validation, b["market"]),
                                         TRUST_STYLE[None])[0],
            }, edge_tier(a["edge"], True), market_trust(validation, b["market"])))
    rows.sort(key=lambda r: -r[0])
    with st.container(border=True):
        st.markdown(f'<div class="pf-card-title" style="color:{COLOR["gold"]};">'
                    f'Best value tonight</div>', unsafe_allow_html=True)
        if not rows:
            st.caption("No side has value at the POSTED prices right now. Lines move \u2014 "
                       "check your own book's price on each game below.")
            return
        df = pd.DataFrame([r[1] for r in rows])
        sty = _tier_styler(df, [r[2] for r in rows], [r[3] for r in rows])
        st.dataframe(sty, hide_index=True, width="stretch", key=f"best_{key}")
        st.caption("Posted prices only (ESPN). Your book may differ \u2014 the table on each game "
                   "recomputes at the price you type." + (f" {prop_note}" if prop_note else ""))
