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
        if proj.get("p_home_final") is not None:
            w = (proj.get("model_weight") or {}).get("moneyline") or 0.0
            if w:
                why_txt = f"model weight {100 * w:.0f}%"
            elif proj.get("blend_state") == "untested":
                why_txt = ("the market's own number — the model is not yet measured "
                           "against recorded lines")
            else:
                why_txt = "the market's own number — the model has not beaten it"
            bits.append(f"Final {away_label} {_pct(1 - proj['p_home_final'])} / {home_label} "
                        f"{_pct(proj['p_home_final'])} ({why_txt})")
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


def mlb_calibration(pitcher=False):
    """{market_key: bins} from the prop model's walk-forward, for the
    delivered chances on the MLB boards."""
    from engines import mlb_props as mp
    pm = mp.load_prop_model() or {}
    return calibration_map(pm.get("pitcher_validation" if pitcher else "validation"),
                           mp.PITCHER_MARKETS if pitcher else mp.MARKETS)


MLB_DVP_STATS = ("h", "tb", "hr", "k", "bb", "s", "d")


def _mlb_batter_context(pm, b_counts, proj, opp_pitcher_id, opp_name):
    """(_dvp, _notice, _why) for one batter row — the starter he faces,
    on each stat, with his allowed rate ranked among this season's
    starters (engines/defense_matchup.mlb_starter_card)."""
    from engines import defense_matchup as dm
    from engines import mlb_props as mp
    table = (pm or {}).get("starter_allowed")
    cards, notes = {}, {}
    who = opp_name or "Tonight's starter"
    for stat in MLB_DVP_STATS:
        c = dm.mlb_starter_card(table, opp_pitcher_id, stat) if opp_pitcher_id else None
        if c:
            cards[stat] = c
            notes[stat] = dm.notice(c, dm.MLB_STAT_LABELS[stat], "batters", who)
    bits = []
    shr = mp.shrunk_rates(b_counts, (pm or {}).get("batter_priors"))
    if shr:
        bits.append(f"his rates over {_pa_label(b_counts)} PA (last season at the fitted "
                    f"weight, shrunk toward the league): {100 * (shr['1B'] + shr['2B'] + shr['3B'] + shr['HR']):.1f}% "
                    f"hit, {100 * shr['HR']:.1f}% HR, {100 * shr['K']:.1f}% K per PA")
    hc = cards.get("h")
    if hc:
        bits.append(f"{who} allows {hc['per_game']:.3f} hits per PA ({dm.rank_text(hc)} of "
                    f"this season's starters; league {hc['league']:.3f})")
    elif opp_pitcher_id:
        bits.append(f"{who}: no allowed-rate ranking on file yet")
    if proj:
        bits.append(f"{proj['exp_pa']:.1f} expected PA from his slot, then a league-average bullpen")
    return cards, notes, " · ".join(bits)


def mlb_lineup_props(batters, opp_pitcher_id, opp_name=None):
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
        p_counts = mp.player_counts(pm, opp_pitcher_id, p_counts, "pitcher")
        bf_dist = mp.starter_bf_dist((pm.get("starter_bf") or {}).get(str(opp_pitcher_id)), pm,
                                     (pm.get("prior_bf") or {}).get(str(opp_pitcher_id)))
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
        b_counts = mp.player_counts(pm, b.get("id"), mp.outcome_counts(b_df), "batter")
        if not b_counts.get("PA"):
            # MISSING IS NOT ZERO (rule 6). With no PAs on record the
            # shrinkage would hand him exactly the league average, and a
            # league-average line under his name reads as a measurement of
            # him. Listed, priced as nothing.
            row = {"#": slot, "Batter": b.get("name"), "PA": "0", "Exp PA": DASH}
            for k, *_ in mp.MARKETS:
                row[k] = DASH
            rows.append(row)
            continue
        proj = mp.project_batter(slot, b_counts, p_counts, pm, bf_dist)
        if not proj:
            continue
        _dvp, _notes, _why = _mlb_batter_context(pm, b_counts, proj, opp_pitcher_id, opp_name)
        row = {"#": slot, "Batter": b.get("name"),
               "PA": _pa_label(b_counts), "Exp PA": proj["exp_pa"],
               "_name": b.get("name"), "_probs": proj["probs"], "_pmfs": proj.get("pmfs") or {},
               "_dvp": _dvp, "_notice": _notes, "_why": _why}
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


def _pa_label(counts):
    """'612 + 580 last yr' when last season is folded in, else this season's PAs."""
    c = counts or {}
    if "PA_last_season" in c:
        return f"{int(c.get('PA_this_season') or 0)} + {int(c['PA_last_season'])} last yr"
    return str(int(c.get("PA") or 0))


def mlb_starter_props(batters, pitcher_id, pitcher_name=None):
    """(row, verdicts, note) for tonight's starter against the lineup he
    faces — strikeouts, hits, walks and homers allowed — or (None, {}, why).

    Same per-PA model as the batter props, seen from the mound: each slot
    of THIS lineup against him, for as long as he usually lasts."""
    from engines import mlb_props as mp
    from engines.statcast_engine import _get_batter_df, _get_pitcher_df
    from engines.lineup_slot import _slot_from_batting_order

    pm = mp.load_prop_model()
    if not pm:
        return None, {}, "The prop model appears after the next nightly."
    if not pitcher_id:
        return None, {}, "Starter not announced \u2014 no pitcher props yet."
    try:
        p_df, _err = _get_pitcher_df(int(pitcher_id))
        p_counts = mp.outcome_counts(p_df)
    except Exception:
        p_counts = None
    p_counts = mp.player_counts(pm, pitcher_id, p_counts, "pitcher")
    if not (p_counts and p_counts.get("PA")):
        return None, {}, ("No record for this starter this season or last \u2014 his props "
                          "would be the league average under his name, so none are shown.")
    bf_dist = mp.starter_bf_dist((pm.get("starter_bf") or {}).get(str(pitcher_id)), pm,
                                 (pm.get("prior_bf") or {}).get(str(pitcher_id)))
    order = [None] * 9
    known = 0
    names = [None] * 9
    for i, b in enumerate(batters or []):
        slot = _slot_from_batting_order(b.get("battingOrder")) or (i + 1)
        if not (1 <= slot <= 9) or order[slot - 1] is not None:
            continue
        try:
            b_df, _e = _get_batter_df(int(b["id"]))
            c = mp.outcome_counts(b_df)
        except Exception:
            c = None
        c = mp.player_counts(pm, b.get("id"), c, "batter")
        if c and c.get("PA"):
            order[slot - 1] = c
            names[slot - 1] = b.get("name")
            known += 1
    proj = mp.project_pitcher(order, p_counts, pm, bf_dist)
    if not proj:
        return None, {}, "Not enough on record to price this starter."
    starts = len((pm.get("starter_bf") or {}).get(str(pitcher_id)) or [])
    starts_ly = len((pm.get("prior_bf") or {}).get(str(pitcher_id)) or [])
    row = {"Pitcher": pitcher_name or "Starter",
           "Starts": f"{starts} + {starts_ly} last yr" if starts_ly else str(starts),
           "Exp BF": proj["exp_bf"], "Exp K": proj["exp"].get("k"),
           "_name": pitcher_name or "Starter", "_pmfs": proj["pmfs"], "_probs": proj["probs"]}
    # MATCHUP (10-06): tonight's lineup, from the nine bats the model
    # prices, placed among this season's team batting lines.
    from engines import defense_matchup as dm
    _bpri = pm.get("batter_priors")
    _lu = [c for c in order if c]
    _dvp, _notes = {}, {}
    for stat in ("k", "h", "bb", "hr"):
        vals = [dm.per_pa(c, _bpri, stat) for c in _lu]
        vals = [v for v in vals if v is not None]
        card_ = dm.mlb_lineup_card(pm.get("team_batting"), sum(vals) / len(vals) if vals else None,
                                   stat)
        if card_:
            _dvp[stat] = card_
            _lab = {"k": "strikeouts", "h": "hits", "bb": "walks", "hr": "home runs"}[stat]
            _notes[stat] = (f"{dm.badge(card_)} \u2014 tonight's lineup gives up {_lab} at "
                            f"{card_['per_game']:.3f} per PA (league {card_['league']:.3f}, "
                            f"{card_['vs_league_pct']:+.0f}%); among this season's team lineups "
                            f"that is the {dm.rank_text(card_)}.")
    _shr = mp.shrunk_rates(p_counts, pm.get("pitcher_priors"))
    _why = []
    if _shr:
        _why.append(f"his allowed rates (this season + last at the fitted weight, shrunk): "
                    f"{100 * _shr['K']:.1f}% K, {100 * _shr['BB']:.1f}% BB, "
                    f"{100 * _shr['HR']:.1f}% HR per batter")
    _why.append(f"{proj['exp_bf']:.1f} batters faced expected (his own starts vs the league's)")
    if _dvp.get("k"):
        _why.append(f"lineup K rate {100 * _dvp['k']['per_game']:.1f}% vs league "
                    f"{100 * _dvp['k']['league']:.1f}%")
    row.update({"_dvp": _dvp, "_notice": _notes, "_why": " · ".join(_why)})
    note = None
    if known < 9:
        note = (f"{9 - known} lineup spot(s) have no Statcast record and are priced as a "
                f"league-average bat.")
    return row, mp.market_verdicts(pm, pitcher=True), note


MLB_PITCHER_FOOTNOTE = (
    "Each cell: chance he clears the line, and the fair price at that chance. Every batter he "
    "is expected to face, in order, against his allowed rates, for as long as he usually lasts "
    "(his own batters-faced, shrunk toward the league's). NOT in the number: park, weather, "
    "pitch count limits announced today, an early hook when he is getting hit.")


# ----------------------------------------------------------------------
# The prop board: pick a stat, see every standard line; check ANY line
# ----------------------------------------------------------------------
def _pmf_mean(pmf):
    return sum(i * p for i, p in enumerate(pmf or []))


def _line_verdict(markets, verdicts, stat, line):
    """Verdict of the tested market at this exact line, or None."""
    for k, _label, s, n in markets:
        if s == stat and abs((n - 0.5) - line) < 1e-9:
            return verdicts.get(k)
    return None


def _tested_lines(markets, stat):
    return [n - 0.5 for _k, _l, s, n in markets if s == stat]


# ----------------------------------------------------------------------
# Delivered chance, colour and matchup (10-06) — every sport
# ----------------------------------------------------------------------
def calibration_map(validation, markets):
    """{market_key: calibration bins} from a validation block, for the
    markets that have a curve."""
    out = {}
    for k, *_ in markets or ():
        bins = ((validation or {}).get(k) or {}).get("calibration")
        if bins:
            out[k] = bins
    return out


def delivered_over(p_over, stat, line, markets, calibration):
    """(chance, basis) for the OVER at `line`: the model's chance mapped
    through what calls like it DELIVERED on games it had not seen
    (top_plays_board.calibrate) — the exact line's curve when it was
    tested, else the nearest tested line of the same stat. basis is
    "exact", "nearest O<x>", or "raw" when there is no curve at all (the
    model's own number, labelled as such — rule 9)."""
    from engines import top_plays_board as tpb
    if p_over is None:
        return None, "raw"
    cands = [(k, n - 0.5) for k, _l, s_, n in (markets or ()) if s_ == stat
             and (calibration or {}).get(k)]
    if not cands:
        # A STAT-LEVEL curve ("@stat"): NFL props are tested at a line next
        # to each player's own average, not at one fixed line, so their
        # record is one curve per stat.
        bins = (calibration or {}).get(f"@{stat}")
        c = tpb.calibrate(p_over, bins) if bins else None
        return (c, "this stat's record") if c is not None else (p_over, "raw")
    k, ln = min(cands, key=lambda x: abs(x[1] - line))
    c = tpb.calibrate(p_over, calibration[k])
    if c is None:
        return p_over, "raw"
    return c, ("exact" if abs(ln - line) < 1e-9 else f"nearest O{ln:g}")


# Chance bands for COLOUR ONLY — where the eye should land, on the
# absolute scale a bettor reads (not ranked within the column, so the
# same 72% is the same colour on every table). They change no number;
# the legend under each board prints them.
CHANCE_BANDS = (
    (0.80, "elite", "80%+"), (0.65, "good", "65-79%"), (0.50, "average", "50-64%"),
    (0.35, "below", "35-49%"), (0.0, "poor", "under 35%"),
)
_CHANCE_HEX = {"elite": COLOR["stat_high"], "good": "#E8B33C", "average": COLOR["stat_mid"],
               "below": "#9B6BC7", "poor": COLOR["text_faint"]}
MATCHUP_STYLE = {
    "soft": ("SOFT", COLOR["accent"], COLOR["accent_dim"]),
    "neutral": ("NEUTRAL", COLOR["text_muted"], None),
    "tough": ("TOUGH", COLOR["error"], COLOR["error_dim"]),
}


def chance_band(p):
    if p is None:
        return None
    for lo, name, _rng in CHANCE_BANDS:
        if p >= lo:
            return name
    return "poor"


def chance_css(p):
    """Cell style for a chance: a filled band with readable text."""
    band = chance_band(p)
    if band is None:
        return f"color: {COLOR['text_faint']};"
    if band == "poor":
        # A long shot is not a warning — the eye should skip it, not stop
        # on it. No fill, faint text.
        return f"color: {COLOR['text_faint']};"
    hx = _CHANCE_HEX[band]
    r, g, b = (int(hx.lstrip("#")[i:i + 2], 16) for i in (0, 2, 4))
    strong = band == "elite"
    a = {"elite": 0.75, "good": 0.55, "average": 0.35, "below": 0.22}[band]
    return (f"background-color: rgba({r},{g},{b},{a:.2f}); "
            f"color: {COLOR['bg'] if strong else COLOR['text']}; font-weight: {700 if strong else 600};")


def matchup_css(tier_name):
    lab, fg, bg = MATCHUP_STYLE.get(tier_name, ("", COLOR["text_faint"], None))
    return (f"color: {fg}; font-weight: 700;" + (f" background-color: {bg};" if bg else ""))


def painted(df, painter):
    """The site's base table styling (dark cells, 2-dp floor, em-dash for
    missing — table_style._base_styler) with a cell painter on top."""
    from styles.table_style import _base_styler
    return _base_styler(df).apply(painter, axis=None)


def render_chance_legend(extra=""):
    sw = []
    for _lo, name, rng in CHANCE_BANDS:
        hx = _CHANCE_HEX[name]
        sw.append(f'<span style="display:inline-flex; align-items:center; gap:4px;">'
                  f'<span style="width:11px; height:11px; border-radius:3px; background:{hx};">'
                  f'</span><span style="color:{COLOR["text_muted"]}; '
                  f'font-size:var(--lc-text-tiny);">{rng}</span></span>')
    for t in ("soft", "tough"):
        lab, fg, _bg = MATCHUP_STYLE[t]
        sw.append(f'<span style="color:{fg}; font-weight:700; font-size:var(--lc-text-tiny);">'
                  f'{lab}</span>')
    st.markdown('<div style="display:flex; flex-wrap:wrap; gap:6px 14px; align-items:center; '
                'margin:2px 0 4px;">' + "".join(sw) + "</div>"
                f'<div style="color:{COLOR["text_faint"]}; font-size:var(--lc-text-tiny);">'
                f'Cell colour = chance band (colour only, no number changes). SOFT / TOUGH = the '
                f'defense sits in the top / bottom quarter of the league for what it allows to '
                f'this position on this stat.{(" " + extra) if extra else ""}</div>',
                unsafe_allow_html=True)


def render_verdict_box(tier_name, html_body):
    """The checker's answer as a coloured panel — the tier's colour on the
    border and a tint behind it, so the call reads before the numbers."""
    _l, fg, bg = TIER_STYLE.get(tier_name, TIER_STYLE["none"])
    st.markdown(f'<div style="border:1px solid {fg}; border-left:6px solid {fg}; '
                f'background:{bg or "transparent"}; border-radius:var(--lc-radius-lg); '
                f'padding:8px 12px; margin:6px 0; line-height:1.55;">{html_body}</div>',
                unsafe_allow_html=True)


def render_prop_board(rows, stats, markets, verdicts, key, staking, info_cols,
                      favor_note=None, footnote=None, unit_note=None, calibration=None):
    """rows: [{"_name", "_pmfs": {stat: [P(0), P(1), ...]}, <info_cols>...,
    optional "_dvp": {stat: matchup card}, "_why": str}].
    stats: [(stat, label, lines shown)]. markets: the TESTED (key, label,
    stat, at_least) list — a line's header is starred when its test did
    not beat the player's own rate, and lines with no test say so.
    calibration: {market_key: bins} — when given, every chance shown is
    the DELIVERED chance (delivered_over), the same number the checker
    and Top Plays use."""
    rows = [r for r in rows if r.get("_pmfs")]
    if not rows:
        st.caption("No prop projections for this side yet.")
        if favor_note:
            st.caption(favor_note)
        return
    labels = {s: lab for s, lab, _ in stats}
    avail = [s for s, _lab, _ in stats if any(s in (r.get("_pmfs") or {}) for r in rows)]
    stat = st.selectbox("Stat", avail, format_func=lambda s: labels[s], key=f"pb_stat_{key}")
    lines = next(ln for s, _l, ln in stats if s == stat)
    render_trust_row([(f"O{ln:g}", _line_verdict(markets, verdicts, stat, ln)) for ln in lines])
    has_dvp = any(((r.get("_dvp") or {}).get(stat)) for r in rows)
    table, chances, tiers = [], [], []
    from engines import defense_matchup as dm
    for r in rows:
        pmf = (r.get("_pmfs") or {}).get(stat)
        row = {c: r.get(c) for c in info_cols}
        row["Avg"] = DASH if pmf is None else round(_pmf_mean(pmf), 2)
        cmap = {}
        for ln in lines:
            v = _line_verdict(markets, verdicts, stat, ln)
            head = f"O{ln:g}" + ("" if v == "beats" else " *")
            po = None if pmf is None else mm.over_prob_pmf(pmf, ln)
            pc, _basis = delivered_over(po, stat, ln, markets, calibration)
            row[head] = DASH if pc is None else prob_cell(pc)
            cmap[head] = pc
        c = (r.get("_dvp") or {}).get(stat)
        if has_dvp:
            row["Defense vs pos"] = dm.badge(c)
        table.append(row)
        chances.append(cmap)
        tiers.append((c or {}).get("tier"))
    df = pd.DataFrame(table)

    def _paint(frame):
        out = pd.DataFrame("", index=frame.index, columns=frame.columns)
        for i in frame.index:
            for col, pc in chances[i].items():
                out.at[i, col] = chance_css(pc)
            if "Defense vs pos" in frame.columns:
                out.at[i, "Defense vs pos"] = matchup_css(tiers[i])
        return out

    st.dataframe(painted(df, _paint), hide_index=True, width="stretch",
                 key=f"pb_tab_{key}_{stat}")
    render_chance_legend()
    cal_txt = (" Chances are what calls like these DELIVERED on games the model had not seen "
               "(its own number mapped through that line's record)." if calibration else
               " Chances are the model's own (no graded record for this market yet).")
    st.caption("Avg = expected count. * = that line did not beat the player's own hit rate on "
               "games it had not seen (or has no test yet) — shown, but don't lean on it."
               + cal_txt)
    if unit_note and stat == "rbi":
        st.caption(unit_note)
    if favor_note:
        st.caption(favor_note)
    _any_line_tool(rows, stats, markets, verdicts, key, staking, stat, calibration=calibration)
    if footnote:
        st.caption(footnote)


def _price_default(p):
    """The fair price for p, clamped to what a book prints — the neutral
    starting value for a price box (no edge until the reader types one)."""
    f = mm.fair_american(p) if p is not None else None
    if f is None:
        return -110
    return int(max(-2000, min(2000, f)))


def balanced_line(pmf, fn=None, lo=0.5, hi=None):
    """The x.5 line whose over chance is nearest 50% — a sensible default
    for a line the reader has not typed yet. pmf, or fn(line) -> P(over)."""
    if pmf is None and fn is None:
        return lo
    hi = hi if hi is not None else (len(pmf) if pmf is not None else 60)
    best, best_d = lo, 9.0
    x = lo
    while x <= hi:
        p = mm.over_prob_pmf(pmf, x) if pmf is not None else fn(x)
        if p is not None and abs(p - 0.5) < best_d:
            best, best_d = x, abs(p - 0.5)
        x += 1.0
    return best


def _any_line_tool(rows, stats, markets, verdicts, key, staking, default_stat, calibration=None):
    bankroll, frac, cap = staking
    labels = {s: lab for s, lab, _ in stats}
    st.markdown("**Check any line at your price**")
    c1, c2, c3 = st.columns([2, 2, 1])
    who = c1.selectbox("Player", [r["_name"] for r in rows], key=f"al_who_{key}")
    avail = [s for s, _l, _ in stats if s in (next(r for r in rows if r["_name"] == who)
                                              .get("_pmfs") or {})]
    stat = c2.selectbox("Stat", avail, index=avail.index(default_stat) if default_stat in avail else 0,
                        format_func=lambda s: labels[s], key=f"al_stat_{key}")
    _pmf0 = (next(r for r in rows if r["_name"] == who).get("_pmfs") or {}).get(stat)
    # Default to the line nearest a coin flip for HIM, so the first thing
    # the tool shows is never "STRONG" at a line nobody would post.
    line = c3.number_input("Line", min_value=0.0, value=float(balanced_line(_pmf0)), step=0.5,
                           key=f"al_line_{key}_{stat}_{who}")
    c4, c5, c6 = st.columns([1, 1, 1])
    side = c4.radio("Side", ["Over", "Under"], horizontal=True, key=f"al_side_{key}")
    _pmf_now = (next(r for r in rows if r["_name"] == who).get("_pmfs") or {}).get(stat)
    _po_now, _b = delivered_over(mm.over_prob_pmf(_pmf_now, line), stat, line, markets, calibration)
    # The price box starts at the MODEL's own fair price, so nothing shows
    # as value until the reader types the number his book actually posts.
    _p_now = None if _po_now is None else (_po_now if side == "Over" else 1 - _po_now)
    price = c5.number_input("Your book's price", value=_price_default(_p_now), step=5,
                            key=f"al_px_{key}_{who}_{stat}_{line}_{side}")
    other = c6.number_input("Other side's price (optional)", value=0, step=5,
                            key=f"al_ox_{key}",
                            help="Enter the opposite side's price too and the book's own no-vig "
                                 "chance is shown beside the model's.")
    sel = next(r for r in rows if r["_name"] == who)
    pmf = (sel.get("_pmfs") or {}).get(stat)
    po_raw = mm.over_prob_pmf(pmf, line)
    if po_raw is None:
        st.caption("No distribution for that player and stat.")
        return
    # THE CHANCE A PRICE IS JUDGED ON is the delivered one (10-06): the
    # model's number mapped through what calls like it actually did on
    # games it had not seen. Judging a -200 against the raw number
    # would call an overconfident 78% "STRONG" when calls like it hit 70%.
    po, basis = delivered_over(po_raw, stat, line, markets, calibration)
    p = po if side == "Over" else 1 - po
    p_raw = po_raw if side == "Over" else 1 - po_raw
    a = vl.assess(p, price, bankroll or None, frac, cap)
    if not a:
        st.caption("Enter an American price of -100 or lower, or +100 or higher.")
        return
    tested = _tested_lines(markets, stat)
    v = _line_verdict(markets, verdicts, stat, line)
    if v is not None:
        trust_txt = f"this exact line tested: {trust_label(v)}"
    elif tested:
        near = min(tested, key=lambda t: abs(t - line))
        trust_txt = (f"this line has no test of its own \u2014 nearest tested line O{near:g}: "
                     f"{trust_label(_line_verdict(markets, verdicts, stat, near))}")
    else:
        trust_txt = "untested"
    mkt_txt = ""
    if other and (other <= -100 or other >= 100):
        pair = mm.no_vig_pair(price, other)
        if pair[0] is not None:
            mkt_txt = (f" \u00b7 the book's own no-vig chance {100 * pair[0]:.1f}% "
                       f"(model {'above' if p > pair[0] else 'below'} it by "
                       f"{100 * abs(p - pair[0]):.1f} pts)")
    _tier = edge_tier(a["edge"], a["value"])
    _tl, _tfg, _tbg = TIER_STYLE[_tier]
    verdict = (f'<span style="color:{_tfg}; font-weight:800;">{_tl}</span>'
               if _tier != "none" else
               f'<span style="color:{COLOR["error"]}; font-weight:800;">NO VALUE</span>')
    stake_txt = (f" \u00b7 stake ${a['stake']:.2f}" if a["value"] and a.get("stake") else "")
    if basis == "raw":
        chance_txt = (f"model <b>{100 * p:.1f}%</b> <span style='color:{COLOR['text_faint']};'>"
                      f"(no graded record for this stat yet \u2014 the model's own number)</span>")
    else:
        chance_txt = (f"delivered chance <b>{100 * p:.1f}%</b> "
                      f"<span style='color:{COLOR['text_faint']};'>(model said "
                      f"{100 * p_raw:.1f}%; calls like it hit {100 * p:.1f}% on games it had "
                      f"not seen \u2014 {'this line' if basis == 'exact' else basis + '’s record'})"
                      f"</span>")
    render_verdict_box(_tier, (
        f"<b>{who}</b> \u00b7 {labels[stat]} {side} {line:g} at "
        f"<b>{mm.fmt_american(int(price))}</b> \u2192 <b>{verdict}</b><br>"
        f"{chance_txt} \u00b7 worth it at <b>{mm.fmt_american(mm.fair_american(p))}</b> or "
        f"better \u00b7 break-even at your price {100 * a['break_even']:.1f}% \u00b7 edge "
        f"<b>{100 * a['edge']:+.1f} pts</b> \u00b7 EV {a['ev_per_100']:+.2f} per $100"
        f"{stake_txt}{mkt_txt}"))
    _why = sel.get("_why")
    _card = (sel.get("_dvp") or {}).get(stat)
    _note = sel.get("_notice", {}).get(stat) if isinstance(sel.get("_notice"), dict) else None
    if _why or _card or _note:
        _mt = (_card or {}).get("tier")
        _lab, _fg, _bg = MATCHUP_STYLE.get(_mt, ("", COLOR["text_muted"], None))
        parts = []
        if _note:
            parts.append(f'<span style="color:{_fg}; font-weight:700;">{_note}</span>')
        if _why:
            parts.append(f'<span style="color:{COLOR["text"]};"><b>Why:</b> {_why}</span>')
        st.markdown('<div style="font-size:var(--lc-text-small); line-height:1.6; '
                    'margin:2px 0 6px;">' + "<br>".join(parts) + "</div>",
                    unsafe_allow_html=True)
    st.caption(f"Props are the model alone \u2014 {trust_txt}. Prop prices are not yet "
               f"recorded, so unlike the game lines these are NOT measured against the books; "
               f"a big gap to the book's no-vig chance is more often the book knowing something "
               f"(a lineup spot, a pitch count, an injury) than a gift.")

MLB_PROP_FOOTNOTE = (
    "Each cell: chance he clears the line, and the fair price at that chance. "
    "Built plate appearance by plate appearance — his rates (this season, plus last season "
    "at the weight the nightly measured it is worth) against tonight's starter for as long "
    "as that starter usually lasts, then a league-average bullpen. "
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
# Ceiling on the WHOLE slate's stakes as a share of bankroll. A risk
# preference like the two above, not a number about the world (rule 1
# is about those): Kelly sizes each bet as if it were the only one, and
# a Sunday with a dozen value rows would otherwise stake a dozen caps.
_SLATE_CAPS = {"5%": 0.05, "10%": 0.10, "15%": 0.15, "25%": 0.25}


def staking_controls(key):
    """Bankroll, Kelly fraction and per-bet cap — shared across every
    model page through session state, so it is set once per visit."""
    ss = st.session_state
    ss.setdefault("lc_bankroll", 0.0)
    ss.setdefault("lc_kelly", "1/4 Kelly")
    ss.setdefault("lc_cap", "2%")
    ss.setdefault("lc_slate_cap", "10%")
    with st.expander("Your bankroll & staking", expanded=not ss["lc_bankroll"]):
        c1, c2, c3, c4 = st.columns(4)
        c1.number_input("Bankroll ($)", min_value=0.0, step=50.0, key="lc_bankroll",
                        help="Leave at 0 to see value without stake sizes.")
        c2.selectbox("Stake size", list(_FRACTIONS), key="lc_kelly",
                     help="A fraction of the Kelly stake. Kelly assumes the model's "
                          "probability is exact; it never is, so bet a fraction.")
        c3.selectbox("Max per bet", list(_CAPS), key="lc_cap",
                     help="Hard ceiling as a share of bankroll, whatever Kelly says.")
        c4.selectbox("Max per slate", list(_SLATE_CAPS), key="lc_slate_cap",
                     help="Ceiling on everything staked across the slate. When the value "
                          "rows add up to more, every stake is scaled down together.")
        st.caption("Every chance a bet is priced on is the MARKET's, moved toward the model only "
                   "as far as the model has beaten the market on past games (Final %). A bet has "
                   "VALUE when that beats the price's break-even \u2014 usually because your "
                   "book's price is better than the posted one, or the model has earned a say. "
                   "Stakes = your Kelly fraction, capped per bet and per slate. One bet per game "
                   "side: a moneyline and a spread on the same team are the same opinion.")
    return ss["lc_bankroll"], _FRACTIONS[ss["lc_kelly"]], _CAPS[ss["lc_cap"]]


def slate_cap():
    """The per-slate ceiling as a share of bankroll."""
    return _SLATE_CAPS.get(st.session_state.get("lc_slate_cap", "10%"), 0.10)


def scale_to_slate(stakes, bankroll, cap_share):
    """Scale a list of dollar stakes down together so they sum to at most
    cap_share x bankroll. Returns (scaled, factor)."""
    tot = sum(x for x in stakes if x)
    lim = (bankroll or 0) * (cap_share or 0)
    if not tot or not lim or tot <= lim:
        return list(stakes), 1.0
    f = lim / tot
    return [round(x * f, 2) if x else x for x in stakes], f


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


def _final_pct(b):
    return DASH if b.get("p") is None else f"{100 * b['p']:.1f}%"


def render_value_panel(proj, odds, away, home, key, staking, validation=None, blend=None):
    """Every side the model prices: the model's chance, the market's
    (no-vig), and the FINAL chance the bet is priced on (engines/
    market_blend). Prices default to the posted line where there is one;
    type your own book's price in the Price column and the row recomputes."""
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
        a = (vl.assess(b["p"], price, bankroll or None, frac, cap)
             if price not in (None, "") and b["p"] is not None else None)
        tiers.append(edge_tier(a["edge"] if a else None, bool(a and a["value"])))
        trusts.append(market_trust(blend, b["market"]))
        rows.append({
            "Tier": TIER_STYLE[tiers[-1]][0],
            "Bet": _bet_label(b, away, home),
            "Model": f"{100 * b['p_model']:.1f}%" if b.get("p_model") is not None else DASH,
            "Market": f"{100 * b['p_market']:.1f}%" if b.get("p_market") is not None else DASH,
            "Final": _final_pct(b),
            "Fair": mm.fmt_american(mm.fair_american(b["p"])) if b["p"] is not None else DASH,
            # An EMPTY cell, not the word "None", where no price was
            # posted — the reader types his book's price there.
            "Price": float("nan") if price in (None, "") else price,
            "Break-even": f"{100 * a['break_even']:.1f}%" if a else DASH,
            "Edge": f"{100 * a['edge']:+.1f}" if a else DASH,
            "EV / $100": f"{a['ev_per_100']:+.2f}" if a else DASH,
            "Stake": (f"${a['stake']:.2f}" if a and a.get("stake") else
                      ("\u2014" if not a or not bankroll else "$0 (no value)")),
            "Trust": trust_label(trusts[-1], market=True),
        })
    df = pd.DataFrame(rows)
    st.data_editor(
        # The editable Price column ignores Styler formatting, and an empty
        # editable number cell shows Streamlit's grey "None" placeholder —
        # never a filled-in price (no posted price is never assumed -110).
        # The caption below says what that placeholder means.
        _tier_styler(df, tiers, trusts, market=True),
        key=ed_key, hide_index=True, width="stretch",
        disabled=[c for c in df.columns if c != "Price"],
        column_config={"Price": st.column_config.NumberColumn(
            "Price", help="American odds at YOUR book. Posted line pre-filled where ESPN has one.",
            step=1, format="%d")})
    st.caption(weight_line(proj, blend))
    st.caption("Model = the model alone · Market = the posted line with the margin removed · "
               "Final = what the bet is priced on. Row colour = your edge at that price "
               "(STRONG / VALUE / THIN; no tint = no value). Tap Price to enter your book's "
               "number \u2014 a grey \u201cNone\u201d there means ESPN posted no price for that side.")


def weight_line(proj, blend):
    """One sentence: how much say the model has, per market, and why."""
    names = {"moneyline": "moneyline", "total": "total", "spread": "spread"}
    if not any(((blend or {}).get(m) or {}).get("n") for m in names):
        return ("Final = the market's own chance: the model has not yet been measured against "
                "recorded market lines (run the Market history workflow once). Value here can "
                "only come from a better price at your book than the posted one.")
    bits = []
    for m, lab in names.items():
        x = (blend or {}).get(m) or {}
        if not x.get("n"):
            continue
        v = (x.get("verdict") or {}).get("verdict")
        w = x.get("w_used") or 0.0
        if w:
            bits.append(f"{lab} {100 * w:.0f}% model / {100 * (1 - w):.0f}% market")
        elif v == "thin":
            bits.append(f"{lab} 100% market (model ahead on {x['n']:,} past games, but "
                        f"inside the noise \u2014 not proven yet)")
        else:
            bits.append(f"{lab} 100% market (model did not beat it on {x['n']:,} past games)")
    return "How Final is weighted, measured on past games with recorded lines: " + "; ".join(bits) + "."


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
               if edge_tier(a["edge"], a["value"]) != "none" else "no value")
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
    if edge <= 0:
        # +0.0 on the printed grid is break-even, not value — a price box
        # that starts at the fair price must not read THIN.
        return "none"
    names = ("thin", "value", "strong")          # in EDGE_BUCKETS order
    for name, (lo, hi, _label) in zip(names, mpk.EDGE_BUCKETS):
        if lo <= edge < hi:
            return name
    return "strong"


# Game markets are tested against the MARKET (engines/market_blend), so
# their badges say so; props are tested against the player's own rate.
MARKET_TRUST_LABEL = {"beats": "BEATS MARKET", "thin": "NOT PROVEN YET",
                      "fails": "MARKET WINS", None: "UNTESTED"}


def market_trust(blend, market):
    """'beats' / 'thin' / 'fails' / None for one game-model market: the
    cross-fitted model-plus-market against the market alone, from the
    blend block the nightly writes (model["blend"]). Anything else (an
    old validation dict, None) is UNTESTED — beating a coin flip is not
    beating the book, and the badge must not suggest it is."""
    m = (blend or {}).get(market) if isinstance(blend, dict) else None
    if not isinstance(m, dict) or not m.get("n"):
        return None
    return (m.get("verdict") or {}).get("verdict")


def trust_label(verdict, market=False):
    if market:
        return MARKET_TRUST_LABEL.get(verdict, MARKET_TRUST_LABEL[None])
    return TRUST_STYLE.get(verdict, TRUST_STYLE[None])[0]


def prop_trust(prop_validation, key):
    x = (prop_validation or {}).get(key) or {}
    verdict = (x.get("verdict") or {}).get("verdict")
    if verdict:
        return verdict
    if "beats_baseline" in x:
        return "beats" if x["beats_baseline"] else "fails"
    return None


def trust_pill(verdict, prefix="", market=False):
    label, fg, bg, border = TRUST_STYLE.get(verdict, TRUST_STYLE[None])
    if market:
        label = trust_label(verdict, market=True)
    return (f'<span style="display:inline-block; padding:1px 8px; border-radius:999px; '
            f'border:1px solid {border}; background:{bg}; color:{fg}; '
            f'font-size:var(--lc-text-tiny); font-weight:700; letter-spacing:0.04em; '
            f'white-space:nowrap;">{prefix}{label}</span>')


def render_trust_row(items, market=False):
    """items: [(label, verdict)] — one line of pills. market=True labels
    them against the market (game markets) rather than a baseline."""
    parts = [f'<span style="color:{COLOR["text_muted"]}; font-size:var(--lc-text-small);">'
             f'{lab}</span> {trust_pill(v, market=market)}' for lab, v in items]
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
    pills = " ".join(trust_pill(v, market=True) for v in ("beats", "thin", "fails"))
    st.markdown(
        '<div style="display:flex; flex-wrap:wrap; gap:8px 18px; align-items:center;">'
        + "".join(sw) + "</div>"
        f'<div style="margin-top:6px; display:flex; flex-wrap:wrap; gap:6px; align-items:center;">'
        f'{pills}</div>'
        f'<div style="color:{COLOR["text_faint"]}; font-size:var(--lc-text-tiny); margin-top:4px; '
        f'line-height:1.6;">Row colour = your edge at the price (the same buckets Results grades). '
        f'Badge = whether adding the model to the market predicted past games better than the '
        f'market alone, scored on games the weight never saw: better by more than noise '
        f'({mm.SIGNIFICANCE_Z:g} standard errors) \u2014 the only case the model gets a say '
        f'\u2014, better but within noise, or not better. In the last two, Final is the '
        f'market\u2019s own chance.'
        f'</div>', unsafe_allow_html=True)


def _tier_styler(df, tiers, trusts=None, market=False):
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


def render_best_value(entries, blend, staking, key, prop_note=None):
    """'Best value tonight': per game the best side bet and the best total
    with a POSTED price and positive EV on the FINAL probability,
    strongest edge first, coloured like the rows, stakes scaled together
    to the reader's per-slate ceiling.
    entries: [{"label","away","home","proj","odds"}]."""
    bankroll, frac, cap = staking
    rows = []
    for e in entries:
        for b in mpk.value_bets(e.get("proj"), e.get("odds")):
            a = vl.assess(b["p"], b["price"], bankroll or None, frac, cap)
            if not a or not a["value"]:
                continue
            tr = market_trust(blend, b["market"])
            rows.append([a["edge"], {
                "Game": e["label"], "Bet": _bet_label(b, e["away"], e["home"]),
                "Model": f"{100 * b['p_model']:.1f}%" if b.get("p_model") is not None else DASH,
                "Market": f"{100 * b['p_market']:.1f}%" if b.get("p_market") is not None else DASH,
                "Final": f"{100 * b['p']:.1f}%", "Price": mm.fmt_american(b["price"]),
                "Edge": f"{100 * a['edge']:+.1f}", "EV / $100": f"{a['ev_per_100']:+.2f}",
                "Stake": a.get("stake") or 0.0,
                "Tier": TIER_STYLE[edge_tier(a["edge"], True)][0],
                "Trust": trust_label(tr, market=True),
            }, edge_tier(a["edge"], True), tr])
    rows.sort(key=lambda r: -r[0])
    scaled, factor = scale_to_slate([r[1]["Stake"] for r in rows], bankroll, slate_cap())
    for r, x in zip(rows, scaled):
        r[1]["Stake"] = f"${x:.2f}" if (bankroll and x) else "\u2014"
    with st.container(border=True):
        st.markdown(f'<div class="pf-card-title" style="color:{COLOR["gold"]};">'
                    f'Best value tonight</div>', unsafe_allow_html=True)
        if not rows:
            st.caption("No side has value at the POSTED prices right now \u2014 the Final chance "
                       "(market, moved by the model only where it has earned it) does not beat "
                       "any posted price. Check your own book's price on each game below; a "
                       "better number than the posted one is where value comes from.")
            return
        df = pd.DataFrame([r[1] for r in rows])
        sty = _tier_styler(df, [r[2] for r in rows], [r[3] for r in rows], market=True)
        st.dataframe(sty, hide_index=True, width="stretch", key=f"best_{key}")
        note = ""
        if factor < 1.0:
            note = (f" Stakes scaled to {100 * factor:.0f}% so the slate stays inside your "
                    f"{100 * slate_cap():.0f}% per-slate ceiling.")
        st.caption("Posted prices only (ESPN). One bet per game side (moneyline or spread, "
                   "whichever is worth more) plus the total. Your book may differ \u2014 the "
                   "table on each game recomputes at the price you type." + note
                   + (f" {prop_note}" if prop_note else ""))


# ----------------------------------------------------------------------
# Team totals, alt spreads, alt totals — and any line at your price
# ----------------------------------------------------------------------
def render_alt_lines(proj, away, home, key, sport, staking=None):
    """An expander with every team total / alt spread / alt total the
    game's own score distributions price (engines/alt_lines), plus a
    checker for any line at the reader's price. Model only: no posted
    price exists to anchor these, and the page says so."""
    from engines import alt_lines as al
    t = al.tables(proj, sport)
    if not t:
        return
    bankroll, frac, cap = staking or current_staking()
    unit = {"mlb": "runs", "nhl": "goals", "nfl": "points"}.get(sport, "")
    with st.expander("Team totals & alt lines — any line", expanded=False):
        c1, c2 = st.columns(2)
        tt = {}
        for side, ln, p in t["team_totals"]:
            tt.setdefault(ln, {})[side] = p
        c1.markdown(f"**Team totals** ({unit})")
        c1.dataframe(pd.DataFrame([{"Line": f"O{ln:g}", away: prob_cell(v.get("away")),
                                    home: prob_cell(v.get("home"))} for ln, v in tt.items()]),
                     hide_index=True, width="stretch", key=f"alt_tt_{key}")
        c2.markdown("**Alt spreads**")
        c2.dataframe(pd.DataFrame([{"Spread": f"{home} {s:+g}", "Covers": prob_cell(p),
                                    "Other side": f"{away} {-s:+g}",
                                    "Covers ": prob_cell(None if p is None else 1 - p)}
                                   for s, p in t["spreads"]]),
                     hide_index=True, width="stretch", key=f"alt_sp_{key}")
        st.markdown("**Alt totals**")
        st.dataframe(pd.DataFrame([{"Total": f"{ln:g}", "Over": prob_cell(p),
                                    "Under": prob_cell(None if p is None else 1 - p)}
                                   for ln, p in t["totals"]]),
                     hide_index=True, width="stretch", key=f"alt_to_{key}")
        st.markdown("**Check any line at your price**")
        k1, k2, k3, k4 = st.columns([2, 1, 1, 1])
        kinds = {"tt_away": f"{away} team total", "tt_home": f"{home} team total",
                 "spread": f"{home} spread", "total": "Game total"}
        kind = k1.selectbox("Market", list(kinds), format_func=lambda x: kinds[x],
                            key=f"alt_kind_{key}")
        hi = 60.0 if sport == "nfl" else 15.0
        default = {
            "tt_away": balanced_line(None, lambda x: al.team_total_over(proj, "away", x, sport), 0.5, hi),
            "tt_home": balanced_line(None, lambda x: al.team_total_over(proj, "home", x, sport), 0.5, hi),
            "spread": proj.get("market_spread_home") if proj.get("market_spread_home") is not None
            else (-1.5 if sport != "nfl" else round(proj.get("fair_spread_home", -3.0) * 2) / 2),
            "total": proj.get("market_total") or balanced_line(
                None, lambda x: al.total_over(proj, x, sport), 0.5, 2 * hi)}[kind]
        line = k2.number_input("Line", value=float(default), step=0.5, key=f"alt_line_{key}_{kind}")
        side_opts = ["Over", "Under"] if kind != "spread" else [f"{home}", f"{away}"]
        side = k3.radio("Side", side_opts, horizontal=True, key=f"alt_side_{key}_{kind}")
        if kind == "spread":
            _pc0 = al.home_cover(proj, line, sport)
            _p0 = _pc0 if side == home else (None if _pc0 is None else 1 - _pc0)
        else:
            _po0 = (al.total_over(proj, line, sport) if kind == "total"
                    else al.team_total_over(proj, kind[3:], line, sport))
            _p0 = _po0 if side == "Over" else (None if _po0 is None else 1 - _po0)
        price = k4.number_input("Your book's price", value=_price_default(_p0), step=5,
                                key=f"alt_px_{key}_{kind}_{line}_{side}")
        if kind == "spread":
            pc = al.home_cover(proj, line, sport)
            p = pc if side == home else (None if pc is None else 1 - pc)
            what = f"{home} {line:+g}" if side == home else f"{away} {-line:+g}"
        else:
            po = (al.total_over(proj, line, sport) if kind == "total"
                  else al.team_total_over(proj, kind[3:], line, sport))
            p = po if side == "Over" else (None if po is None else 1 - po)
            what = f"{kinds[kind]} {side} {line:g}"
        a = vl.assess(p, price, bankroll or None, frac, cap) if p is not None else None
        if not a:
            st.caption("Enter an American price of -100 or lower, or +100 or higher.")
        else:
            _tl, _tfg, _tbg = TIER_STYLE[edge_tier(a["edge"], a["value"])]
            verdict = (f'<span style="color:{_tfg}; font-weight:800;">{_tl}</span>'
                       if edge_tier(a["edge"], a["value"]) != "none" else "no value")
            st.markdown(f"{what}: model **{100 * p:.1f}%** (fair {mm.fmt_american(mm.fair_american(p))}) "
                        f"vs break-even {100 * a['break_even']:.1f}% at {mm.fmt_american(int(price))} "
                        f"→ **{verdict}** (edge {100 * a['edge']:+.1f} pts)",
                        unsafe_allow_html=True)
        note = ("Model only — no posted price exists for these lines, so they are NOT "
                "anchored to the market the way the main moneyline / total / spread are; treat "
                "an edge here as the model's opinion, and remember the main markets show how "
                "often the market has been right instead.")
        if sport == "nfl":
            note += (f" Team totals use a one-side spread DERIVED from the measured margin and "
                     f"total spreads (±{al.team_sd(proj) or 0:.1f} pts).")
        st.caption(note)


# ----------------------------------------------------------------------
# NFL player props on the Model page (10-04)
# ----------------------------------------------------------------------
# NFL_STATS and nfl_stat_pmf live in engines/nfl_prop_odds (pure) since
# 10-06, so the nightly prop test prices EXACTLY what this page prices.
from engines.nfl_prop_odds import STATS as NFL_STATS          # noqa: E402
from engines.nfl_prop_odds import stat_pmf as nfl_stat_pmf    # noqa: E402


NFL_DVP_OF = {"pass_yds": "pass_yds", "pass_cmp": "pass_cmp", "pass_att": "pass_att",
              "pass_td": "pass_td", "pass_int": "pass_int", "rush_yds": "rush_yds",
              "carries": "carries", "rec_yds": "rec_yds", "rec": "rec", "targets": "targets",
              "scrim_yds": "scrim_yds", "td": "td"}
NFL_DVP_GROUP = {"QB": "QB", "RB": "RB", "FB": "RB", "HB": "RB", "WR": "WR", "TE": "TE"}
NFL_GROUP_LABELS = {"QB": "quarterbacks", "RB": "running backs", "WR": "wide receivers",
                    "TE": "tight ends", "ALL": "all players"}
NFL_STAT_LABELS = {"pass_yds": "passing yards", "pass_cmp": "completions",
                   "pass_att": "pass attempts", "pass_td": "passing TDs",
                   "pass_int": "interceptions", "rush_yds": "rushing yards",
                   "carries": "carries", "rec_yds": "receiving yards", "rec": "receptions",
                   "targets": "targets", "scrim_yds": "rush + rec yards", "td": "touchdowns"}


def nfl_calibration(league):
    """{"@stat": bins} from the nightly's NFL prop test (nfl_prop_check)."""
    pv = (league or {}).get("prop_validation") or {}
    return {f"@{k}": v["calibration"] for k, v in pv.items()
            if isinstance(v, dict) and v.get("calibration")}


def nfl_verdicts(league):
    pv = (league or {}).get("prop_validation") or {}
    return {k: ((v.get("verdict") or {}).get("verdict")) for k, v in pv.items()
            if isinstance(v, dict) and "verdict" in v}


def nfl_game_prop_rows(g, league, dvp=None):
    """[{"_name", "_pmfs", "Player", ...}] for both sides of one game.
    With the defense table, each row carries its matchup cards, one
    notice per stat, and a why line."""
    from engines import defense_matchup as dm
    from engines.nfl_projection import implied_totals, project_player, attach_td_shares
    attach_td_shares([g], league)
    spreads = (league or {}).get("prop_spreads") or {}
    a_pts, h_pts, _note = implied_totals(g.get("odds") or {}, g.get("away_abbr"), g.get("home_abbr"))
    rows = []
    for side, other in (("away", "home"), ("home", "away")):
        team, opp = g.get(f"{side}_profile"), g.get(f"{other}_profile")
        implied = a_pts if side == "away" else h_pts
        for p in g.get(f"{side}_players") or []:
            proj = project_player(p, team, opp, league, implied)
            pmfs, means = {}, {}
            for stat, _lab, key, market, roles in NFL_STATS:
                if p.get("role") not in roles:
                    continue
                pm = nfl_stat_pmf(market, proj.get(key), spreads)
                if pm:
                    pmfs[stat] = pm
                    means[stat] = proj.get(key)
            if not pmfs:
                continue
            gp = p.get("gp")
            ly = p.get("gp_last_season")
            grp = NFL_DVP_GROUP.get(str(p.get("pos") or "").upper())
            opp_name = g.get(other)
            opp_lab = g.get(f"{other}_abbr") or opp_name
            cards, notes = {}, {}
            for stat in pmfs:
                c = dm.card(dvp, opp_name, grp, NFL_DVP_OF[stat]) if (dvp and grp) else None
                if c:
                    cards[stat] = c
                    notes[stat] = dm.notice(c, NFL_STAT_LABELS[stat], NFL_GROUP_LABELS[grp], opp_lab)
            row_why = _nfl_why(p, proj, g.get(f"{side}_abbr") or side, opp_lab, implied)
            rows.append({"Player": p.get("name"), "Pos": p.get("pos") or p.get("role"),
                         "Team": g.get(f"{side}_abbr") or g.get(side),
                         "Status": p.get("status") or "",
                         "GP": f"{gp} + {ly} last yr" if ly else str(gp),
                         "_name": f"{p.get('name')} ({g.get(f'{side}_abbr') or side})",
                         "_pmfs": pmfs, "_means": means,
                         "_dvp": cards, "_notice": notes, "_why": row_why,
                         "_moved": p.get("last_season_team")})
    return rows


def _nfl_why(p, proj, team, opp, implied):
    """One sentence per player: volume x rate x the defense, and whether
    each defense multiplier is IN the number (from the nightly's test)."""
    bits = []
    use = proj.get("matchup_in_number") or {}
    if proj.get("carries") is not None:
        bits.append(f"{(p.get('carry_share') or 0) * 100:.0f}% of {team}'s carries "
                    f"\u2192 {proj['carries']:.1f}")
        if proj.get("rush_matchup"):
            bits.append(f"{opp} allows {proj['rush_matchup']:.2f}x the league per carry "
                        f"({'in the number' if use.get('rush', True) else 'context only'})")
    if proj.get("targets") is not None:
        bits.append(f"{(p.get('target_share') or 0) * 100:.0f}% of {team}'s targets "
                    f"\u2192 {proj['targets']:.1f}")
        if proj.get("rec_matchup"):
            bits.append(f"{opp} allows {proj['rec_matchup']:.2f}x the league per target "
                        f"({'in the number' if use.get('rec', True) else 'context only'})")
    if proj.get("pass_att") is not None:
        bits.append(f"{proj['pass_att']:.0f} attempts at {proj.get('ypa_adj') or 0:.2f} yds "
                    f"({'defense in the number' if use.get('pass', True) else 'defense context only'})")
    if implied is not None:
        bits.append(f"market implies {team} {implied:g} pts")
    if p.get("gp_last_season"):
        bits.append(f"last season's {p['gp_last_season']} games folded in at the fitted weight")
    return " \u00b7 ".join(bits)


def _ladder(mean):
    """Three lines around a projection: below, at, above (x.5)."""
    if mean is None:
        return ()
    if mean < 3:
        return (0.5, 1.5, 2.5)
    step = max(1.0, round(mean * 0.15))
    mid = float(int(mean)) + 0.5
    return (max(0.5, mid - step), mid, mid + step)


def render_nfl_props(g, league, key, staking, dvp=None):
    """Pick a stat: every player's projection and a three-line ladder of
    chances (coloured by band, DELIVERED chances once the nightly's test
    has a record), the defense-vs-position badge; then any line at your
    price. Status from the team's injury report is printed on the row
    (Out players are left off)."""
    from engines import defense_matchup as dm
    rows = [r for r in nfl_game_prop_rows(g, league, dvp)
            if str(r["Status"]).lower() != "out"]
    if not rows:
        st.caption("No player projections for this game yet.")
        return
    cal = nfl_calibration(league)
    verd = nfl_verdicts(league)
    labels = {s: lab for s, lab, *_ in NFL_STATS}
    avail = [s for s, *_ in NFL_STATS if any(s in r["_pmfs"] for r in rows)]
    stat = st.selectbox("Stat", avail, format_func=lambda s: labels[s], key=f"nflp_stat_{key}")
    table, chances, tiers = [], [], []
    for r in rows:
        pm = r["_pmfs"].get(stat)
        if not pm:
            continue
        mean = r["_means"][stat]
        row = {c: r.get(c) for c in ("Player", "Pos", "Team", "Status", "GP")}
        row["Proj"] = round(mean, 2 if stat == "td" else 1)
        cm = {}
        for i, ln in enumerate(_ladder(mean)):
            pc, _b = delivered_over(mm.over_prob_pmf(pm, ln), stat, ln, (), cal)
            col = ("Low", "Mid", "High")[i]
            row[col] = f"O{ln:g}: {prob_cell(pc)}"
            cm[col] = pc
        c = (r.get("_dvp") or {}).get(stat)
        row["Defense vs pos"] = dm.badge(c)
        if r.get("_moved"):
            row["Status"] = (row["Status"] + " · " if row["Status"] else "") + f"new team (was {r['_moved']})"
        table.append(row)
        chances.append(cm)
        tiers.append((c or {}).get("tier"))
    order = sorted(range(len(table)), key=lambda i: -(table[i]["Proj"] or 0))
    table = [table[i] for i in order]
    chances = [chances[i] for i in order]
    tiers = [tiers[i] for i in order]
    render_trust_row([(labels[stat], verd.get(stat))])
    df = pd.DataFrame(table)

    def _paint(frame):
        out = pd.DataFrame("", index=frame.index, columns=frame.columns)
        for i in frame.index:
            for col, pc in chances[i].items():
                out.at[i, col] = chance_css(pc)
            out.at[i, "Defense vs pos"] = matchup_css(tiers[i])
        return out

    st.dataframe(painted(df, _paint), hide_index=True, width="stretch",
                 key=f"nflp_tab_{key}_{stat}")
    render_chance_legend()
    tested = verd.get(stat) is not None
    st.caption("Proj = projected line (this season, plus last season at the weight the nightly "
               "measured it is worth). Low / Mid / High = chance he goes OVER that line, with its "
               "fair price. " + (
                   "TESTED: the nightly grades every NFL prop week by week on games the model "
                   "had not seen; the badge above is this stat's verdict against the player's "
                   "own hit rate, and the chances are what calls like these delivered."
                   if tested else
                   "UNTESTED until two weeks of finals exist \u2014 the model's own chances, "
                   "research, not a recommendation."))
    stats = tuple((s, lab, (0.5,)) for s, lab, *_ in NFL_STATS)
    _any_line_tool([r for r in rows if r["_pmfs"]], stats, (), {}, f"nfl_{key}", staking, stat,
                   calibration=cal)