"""
Top Plays — the most likely outcomes tonight that have PROVEN themselves,
every one with the record that proves it.

Reads only files the workflows write (no fitting, no network):
  data/top_plays/{mlb,nhl}.json   plays logged before each game, graded
                                  after (engines/top_plays_board)
  the MLB / NHL / NFL slates      game bets, priced on the market-anchored
                                  Final chance; shown ONLY for markets
                                  whose model beat the market out of sample
  data/model_picks/*.json         the graded record of those game bets

What it promises, and only this: each number is what that kind of call
has DELIVERED on games the model had not seen, and every play shown is
written down before it starts and graded after. Never that a play hits.
"""
from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd
import streamlit as st

from styles.kc_theme import COLOR, card, footer, page_header
from engines import model_math as mm
from engines import model_picks as mpk
from engines import model_view as mv
from engines import top_plays_board as tpb
from engines import value as vl

EASTERN = ZoneInfo("America/New_York")
_NAMES = {"mlb": "MLB", "nhl": "NHL", "nfl": "NFL"}

page_header("Top Plays", "The most likely outcomes tonight that have proven themselves "
            "— and the record that proves it", eyebrow="LOS CAPPERS", align="left")

_stk = mv.staking_controls("top_plays")
_today = datetime.now(EASTERN).date().isoformat()


def _pct(x, nd=1):
    return "—" if x is None else f"{100 * x:.{nd}f}%"


# ---------------------------------------------------------------- record
recs = {s: tpb.load(s)["plays"] for s in tpb.SPORTS}
allp = [p for v in recs.values() for p in v]
sm = tpb.summary(allp)
a = sm["all"]
with card("tp_record"):
    st.markdown(f'<div class="pf-card-title" style="color:{COLOR["gold"]};">The record</div>',
                unsafe_allow_html=True)
    if a["n"]:
        c1, c2, c3 = st.columns(3)
        c1.metric("Plays graded", f"{a['n']:,}", f"{a['hits']} hit")
        c2.metric("Promised", _pct(a["promised"]))
        c3.metric("Delivered", _pct(a["hit_rate"]),
                  f"{100 * (a['hit_rate'] - a['promised']):+.1f} pts vs promised")
        rows = [{"Chance shown": b["band"], "Plays": b["n"], "Promised": _pct(b["promised"]),
                 "Delivered": _pct(b["hit_rate"])} for b in sm["by_band"]]
        for s in tpb.SPORTS:
            ss = tpb.summary(recs[s])["all"]
            if ss["n"]:
                rows.append({"Chance shown": f"{_NAMES[s]} only", "Plays": ss["n"],
                             "Promised": _pct(ss["promised"]), "Delivered": _pct(ss["hit_rate"])})
        _raw = [(b["promised"], b["hit_rate"]) for b in sm["by_band"]] + [
            (tpb.summary(recs[s_])["all"]["promised"], tpb.summary(recs[s_])["all"]["hit_rate"])
            for s_ in tpb.SPORTS if tpb.summary(recs[s_])["all"]["n"]]

        def _paint_rec(frame):
            # Delivered at or above what was promised reads green; below, red.
            out = pd.DataFrame("", index=frame.index, columns=frame.columns)
            for i in frame.index:
                pr, hr = _raw[i]
                if pr is not None and hr is not None:
                    out.at[i, "Delivered"] = (f"color:{COLOR['accent']}; font-weight:700;" if hr >= pr
                                              else f"color:{COLOR['error']}; font-weight:700;")
            return out

        st.dataframe(mv.painted(pd.DataFrame(rows), _paint_rec), hide_index=True,
                     width="stretch", key="tp_bands")
    else:
        st.caption("No plays graded yet — the first ones are logged with the next slate "
                   "and graded the morning after. This box fills in from there, and it is the "
                   "one to show anybody who asks whether the page can be trusted.")
    st.caption("Promised = the average chance the page showed for those plays. Delivered = how "
               "often they actually happened. Every play is written down before it starts; "
               "a player who doesn't play is void and counts nowhere.")

# ------------------------------------------------- tonight: player props
tonight = [dict(p, _sport=s) for s in tpb.SPORTS for p in recs[s] if p.get("date") == _today]
tonight.sort(key=lambda p: -(p.get("p_cal") or 0))
with card("tp_props"):
    st.markdown(f'<div class="pf-card-title" style="color:{COLOR["gold"]};">'
                f'Most likely tonight — player props</div>', unsafe_allow_html=True)
    if not tonight:
        st.caption("Nothing logged for today yet. MLB plays are logged at 1, 5 and 7 PM ET as "
                   "lineups post; NHL plays with the morning build. Only lines whose market has "
                   "beaten the players' own hit rates on games it had not seen can appear here.")
    else:
        df = pd.DataFrame([{
            "Sport": _NAMES.get(p["_sport"]),
            "Game": p.get("game"), "Player": p.get("player"), "Bet": p.get("label"),
            "Chance": _pct(p.get("p_cal")),
            "Worth it at": f"{mm.fmt_american(p.get('fair'))} or better",
            "Matchup": (mv.MATCHUP_STYLE.get(p.get("matchup_tier")) or ("\u2014",))[0],
            "Status": p.get("result") or "pending",
        } for p in tonight])
        # The decision first (who, what, how likely, what to pay, matchup,
        # result); sport and the long game name last — iPad width (10-06).
        df = df[mv.lead_columns(df.columns, ("Player", "Bet", "Chance", "Worth it at",
                                             "Matchup", "Status"))]
        _status_css = {"hit": f"color:{COLOR['bg']}; background-color:{COLOR['accent']}; font-weight:700;",
                       "miss": f"color:{COLOR['bg']}; background-color:{COLOR['error']}; font-weight:700;",
                       "void": f"color:{COLOR['text_faint']};"}

        def _paint(frame):
            out = pd.DataFrame("", index=frame.index, columns=frame.columns)
            for i in frame.index:
                out.at[i, "Chance"] = mv.chance_css(tonight[i].get("p_cal"))
                out.at[i, "Matchup"] = mv.matchup_css(tonight[i].get("matchup_tier"))
                out.at[i, "Status"] = _status_css.get(tonight[i].get("result"),
                                                      f"color:{COLOR['text_muted']};")
            return out

        st.dataframe(mv.painted(df, _paint), hide_index=True, width="stretch",
                     key="tp_tonight")
        mv.render_chance_legend("Status: green = hit, red = miss.")
        st.caption("Chance = what calls like this have DELIVERED on games the model had not "
                   "seen (the model's number run through that market's own track record). "
                   "Worth it at = the most you should pay: a price worse than that loses money "
                   "over time however likely the play is.")
        st.markdown("**Check a play at your book's price**")
        c1, c2 = st.columns([3, 1])
        idx = c1.selectbox("Play", range(len(tonight)), key="tp_pick",
                           format_func=lambda i: f"{tonight[i].get('player')} · "
                                                 f"{tonight[i].get('label')}")
        pl = tonight[idx]
        price = c2.number_input("Your price", value=int(pl.get("fair") or -110), step=5,
                                key=f"tp_px_{idx}")
        res = vl.assess(pl.get("p_cal"), price, _stk[0] or None, _stk[1], _stk[2])
        if res:
            # Same tiers and colours as every Model page's checker — the
            # fair price itself is break-even, not value (edge_tier).
            _tier = mv.edge_tier(res["edge"], res["value"])
            _lab, _fg, _bg = mv.TIER_STYLE[_tier]
            verdict = (f'<span style="color:{_fg}; font-weight:800;">{_lab}</span>'
                       if _tier != "none" else
                       f'<span style="color:{COLOR["error"]}; font-weight:800;">NO VALUE</span>')
            mv.render_verdict_box(_tier, (
                f"<b>{pl.get('player')}</b> \u00b7 {pl.get('label')} at "
                f"<b>{mm.fmt_american(int(price))}</b> \u2192 <b>{verdict}</b><br>"
                f"delivered chance <b>{_pct(pl.get('p_cal'))}</b> \u00b7 worth it at "
                f"<b>{mm.fmt_american(pl.get('fair'))}</b> or better \u00b7 break-even at your price "
                f"{_pct(res['break_even'])} \u00b7 edge <b>{100 * res['edge']:+.1f} pts</b> "
                f"\u00b7 EV {res['ev_per_100']:+.2f} per $100"
                + (f" \u00b7 stake ${res['stake']:.2f}" if res.get("stake") else "")))
        _bits = []
        if pl.get("matchup"):
            _mfg = (mv.MATCHUP_STYLE.get(pl.get("matchup_tier")) or ("", COLOR["text_muted"]))[1]
            _bits.append(f'<span style="color:{_mfg}; font-weight:700;">{pl["matchup"]}</span>')
        if pl.get("why"):
            _bits.append(f"<b>Why:</b> {pl['why']}")
        if _bits:
            st.markdown('<div style="font-size:var(--lc-text-small); line-height:1.6;">'
                        + "<br>".join(_bits) + "</div>", unsafe_allow_html=True)

# ------------------------------------------------------ tonight: game bets
entries, blends = [], {}
try:
    from engines import mlb_game_model as mgm
    from engines.slate_guard import load_slate, payload_field
    _m = mgm.load_model() or {}
    blends["mlb"] = _m.get("blend")
    g_mlb, _d, cur = load_slate("mlb")
    for g in (g_mlb if cur else []):
        if g.get("model") and g.get("odds"):
            entries.append(("mlb", g.get("away"), g.get("home"), g["model"], g["odds"]))
    g_nhl, _d2, cur2 = load_slate("nhl")
    blends["nhl"] = (payload_field("nhl", "model") or {}).get("blend")
    for g in (g_nhl if cur2 else []):
        if g.get("model") and g.get("game_type") != "preseason":
            entries.append(("nhl", g.get("away_abbr") or g.get("away"),
                            g.get("home_abbr") or g.get("home"), g["model"], g.get("odds")))
    from engines.nfl_week import load_week
    wk, state = load_week()
    blends["nfl"] = ((wk or {}).get("model") or {}).get("blend")
    for g in ((wk or {}).get("games") or [] if state == "current" else []):
        if g.get("model") and g.get("status") != "final":
            entries.append(("nfl", g.get("away_abbr") or g.get("away"),
                            g.get("home_abbr") or g.get("home"), g["model"], g.get("odds")))
except Exception as exc:  # noqa: BLE001 — a missing slate must not blank the page
    st.caption(f"Game slates unavailable right now ({type(exc).__name__}).")

rows, stakes = [], []
for sport, away, home, proj, odds in entries:
    for b in mpk.value_bets(proj, odds):
        if mv.market_trust(blends.get(sport), b["market"]) != "beats":
            continue
        res = vl.assess(b["p"], b["price"], _stk[0] or None, _stk[1], _stk[2])
        rows.append({"Sport": _NAMES[sport], "Game": f"{away} @ {home}",
                     "Bet": mv._bet_label(b, away, home), "Final": _pct(b["p"]),
                     "Price": mm.fmt_american(b["price"]), "Edge": f"{100 * res['edge']:+.1f}",
                     "EV / $100": f"{res['ev_per_100']:+.2f}", "_p": b["p"]})
        stakes.append(res.get("stake") or 0.0)
scaled, factor = mv.scale_to_slate(stakes, _stk[0], mv.slate_cap())
for r, x in zip(rows, scaled):
    r["Stake"] = f"${x:.2f}" if (_stk[0] and x) else "—"
rows.sort(key=lambda r: -r.pop("_p"))
with card("tp_games"):
    st.markdown(f'<div class="pf-card-title" style="color:{COLOR["gold"]};">'
                f'Game bets with a proven edge</div>', unsafe_allow_html=True)
    if rows:
        _gb = pd.DataFrame(rows)
        st.dataframe(_gb[mv.lead_columns(_gb.columns, ("Bet", "Final", "Price", "Edge", "Stake"))],
                     hide_index=True, width="stretch", key="tp_gb")
        if factor < 1.0:
            st.caption(f"Stakes scaled to {100 * factor:.0f}% to stay inside your per-slate ceiling.")
    else:
        st.caption("None tonight. A game bet appears here only when its market's model has "
                   "BEATEN the market on past games it was not fitted on AND the posted price "
                   "still leaves value. Until the Market history workflow has run, no market "
                   "is proven, so this stays empty on purpose — an empty list beats a "
                   "guess dressed as an edge.")
    gp = [p for s in mpk.SPORTS for p in mpk.load(s)["picks"] if p.get("formula")]
    gsum = mpk.summary(gp)["all"]
    if gsum["n"]:
        roi = "—" if gsum["roi"] is None else f"{gsum['roi']:+.1f}%"
        st.caption(f"Graded record of market-anchored game bets: {gsum['w']}-{gsum['l']}-"
                   f"{gsum['p']}, {gsum['units']:+.2f} units, ROI {roi} (Results has the detail).")

st.caption("What this page promises: every number is a measured track record, every play is "
           "recorded before it starts and graded after, and nothing appears that has not "
           "beaten its test. What it cannot promise: that any single play hits. An 85% play "
           "misses about 3 times in 20 — that is what 85% means. Bet what you can afford "
           "to lose.")
footer()
