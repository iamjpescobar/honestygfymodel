"""NFL — Defenses to Target.

Football's Pitchers to Target: every defense playing this week, with
the position and stat it gives away most for each of QB / RB / WR / TE,
how many SOFT spots it has, and the offense that gets to attack it.

Every rank is defense vs position from engines/defense_matchup — this
season + last season at a fitted weight, ranked 1 = allows the most.
Built nightly; this page fits nothing and calls nothing.
"""
import pandas as pd
import streamlit as st

from styles.kc_theme import COLOR, card, footer, how_to_read, page_header
from engines.nfl_week import load_week
from engines import defense_matchup as dm
from engines import edge_boards as eb
from engines import model_view as mv

page_header("Defenses to Target", "Where every defense bleeds — and who gets to attack it",
            eyebrow="NFL", align="left")


@st.cache_data(ttl=900, show_spinner=False)
def _load():
    wk, state = load_week()
    return wk or {}, state


wk, state = _load()
dvp = wk.get("dvp")
rows = eb.nfl_defense_rows(wk.get("games") or [], dvp, wk.get("teams")) if wk else []

how_to_read([
    ("vs QB / RB / WR / TE", "For each position, the stat this defense gives away MOST "
                             "(passing yards or TDs; rushing yards, TDs or catches; receiving "
                             "yards, catches or TDs) and its rank. SOFT = top quarter of the "
                             "league, TOUGH = bottom quarter."),
    ("Soft spots", "How many positions this defense is SOFT against. More = a better "
                   "defense to attack; ties are broken by how big the holes are (the % "
                   "above the league average in each cell)."),
    ("Attack with", "The offense facing this defense this week — go to its players on "
                    "TD Edge, the Model page or Prop Lab."),
    ("Pts allowed", "Points allowed per game and its rank (1 = fewest allowed)."),
    ("How real", "Each ranking's split-half reliability on last season: a stable trait, "
                 "partly repeatable, or mostly noise. NFL rush defense measured as mostly "
                 "noise — lean on the receiving and TD spots."),
])

if not rows or not dvp:
    st.info("Defenses to Target fills in when this week's NFL file carries the defense "
            f"table (built by the nightly; state: {state}).")
    footer()
    st.stop()

with card("dt_board"):
    st.markdown(f'<div class="pf-card-title" style="color:{COLOR["gold"]};">'
                f'Defenses to target this week</div>', unsafe_allow_html=True)

    def _cell(r, grp):
        b = r["best"].get(grp)
        if not b:
            return "—"
        pct = b[0].get("vs_league_pct")
        return f"{dm.badge(b[0])} {b[1]}" + (f" ({pct:+.0f}%)" if pct is not None else "")

    df = pd.DataFrame([{
        "Defense": r["defense"], "Attack with": r["attack"], "Soft spots": r["soft"],
        "Size": f"{r.get('soft_size', 0.0):+.0f}%",
        "vs QB": _cell(r, "QB"), "vs RB": _cell(r, "RB"), "vs WR": _cell(r, "WR"),
        "vs TE": _cell(r, "TE"),
        "Pts allowed": ("—" if r["pa_pg"] is None else
                        f"{r['pa_pg']:.1f} ({r['pa_rank']}/{r.get('of') or 32})"),
        "Game": r["game"],
    } for r in rows])

    def _paint(frame):
        out = pd.DataFrame("", index=frame.index, columns=frame.columns)
        for i in frame.index:
            for grp in ("QB", "RB", "WR", "TE"):
                b = rows[i]["best"].get(grp)
                out.at[i, f"vs {grp}"] = mv.matchup_css((b[0] if b else {}).get("tier"))
            n = rows[i]["soft"]
            if n >= 3:
                out.at[i, "Soft spots"] = (f"background-color:{COLOR['accent']}; "
                                           f"color:{COLOR['bg']}; font-weight:700;")
            elif n == 2:
                out.at[i, "Soft spots"] = f"background-color:{COLOR['accent_dim']}; font-weight:600;"
        return out

    st.dataframe(mv.painted(df, _paint), hide_index=True, width="stretch", key="dt_tab")
    st.caption("Each position cell is the stat this defense allows MOST to that position "
               "(this season + last, blended). Picking the worst of two or three stats makes "
               "any defense look a little softer than one stat alone would — treat a "
               "single SOFT as a lead and three or four as a pattern.")

with card("dt_detail"):
    st.markdown("**One defense in full**")
    i = st.selectbox("Defense", range(len(rows)),
                     format_func=lambda j: f"{rows[j]['defense']} (vs {rows[j]['attack']})",
                     key="dt_pick")
    r = rows[i]
    dname = next((g.get(s) for g in wk.get("games") or [] for s in ("home", "away")
                  if (g.get(f"{s}_abbr") or g.get(s)) == r["defense"]), r["defense"])
    lines = []
    for grp, keys in eb.DEFENSE_KEYS.items():
        for stat, lab in keys:
            c = dm.card(dvp, dname, grp, stat)
            if c and c.get("rank"):
                lines.append({"Position": grp, "Stat": lab, "Rank": dm.badge(c),
                              "Per game": c["per_game"], "League": c["league"],
                              "vs league": (f"{c['vs_league_pct']:+.0f}%"
                                            if c.get("vs_league_pct") is not None else "—"),
                              "This season": (f"{dm.ordinal(c['rank_cur'])} of {c['of_cur']}"
                                              if c.get("rank_cur") else "—"),
                              "Last season": (f"{dm.ordinal(c['rank_prior'])} of {c['of_prior']}"
                                              if c.get("rank_prior") else "—"),
                              "How real": dm.reliability_words(c.get("reliability")),
                              "_tier": c.get("tier")})
    if lines:
        ddf = pd.DataFrame([{k: v for k, v in x.items() if k != "_tier"} for x in lines])

        def _paint2(frame):
            out = pd.DataFrame("", index=frame.index, columns=frame.columns)
            for j in frame.index:
                out.at[j, "Rank"] = mv.matchup_css(lines[j]["_tier"])
            return out

        st.dataframe(mv.painted(ddf, _paint2), hide_index=True, width="stretch", key="dt_detail_tab")

footer()
