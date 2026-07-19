"""
BvP + zones + spray — the deep-dive layer under the Batter Trend.

Three honest data sources, each labeled where it renders:

1. CAREER BvP vs a specific pitcher — MLB's official vs-player split
   (statsapi vsPlayerTotal): the real career H-AB, HR, BB, K, AVG/SLG
   line. Small samples are shown AS small samples, never dressed up.

2. THIS-SEASON pitch-level detail vs that pitcher — from the batter's
   own local Statcast parquet (which keeps the opposing pitcher id):
   pitches seen, batted balls, whiffs, hard-hit, against him this year.

3. Zone map + spray chart — the batter's own Statcast rows, sliced to
   the same window the trend chart is showing. Zone map: Statcast
   zones 1-9 (strike zone, catcher's view), colored by real xSLG on
   contact per zone; cells under 15 pitches gray out rather than
   pretend. Spray chart: real batted-ball landing coordinates
   (hc_x/hc_y), colored by outcome.

Everything cached (JSON strings where pickled), fetched on demand.
"""
import json
from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd
import requests
import streamlit as st

from styles.kc_theme import COLOR
from engines.statcast_engine import _get_batter_df
from engines.recency_windows import apply_window

EASTERN = ZoneInfo("America/New_York")
_URL = "https://statsapi.mlb.com/api/v1/people/{pid}/stats"

_WIN_KEY = {"Season": "season", "L25": "l25", "L15": "l15", "L10": "l10", "L5": "l5"}
_WHIFFS = {"swinging_strike", "swinging_strike_blocked"}
_SWINGS = {"hit_into_play", "foul", "foul_tip", "swinging_strike", "swinging_strike_blocked"}


# ---------------------------------------------------------------
# 1) Career BvP (official MLB vs-player split)
# ---------------------------------------------------------------
@st.cache_data(ttl=21600, max_entries=64, show_spinner=False)
def _career_bvp_json(batter_id: int, pitcher_id: int) -> str:
    try:
        resp = requests.get(
            _URL.format(pid=batter_id),
            params={"stats": "vsPlayerTotal", "group": "hitting",
                    "opposingPlayerId": pitcher_id},
            timeout=10,
        )
        resp.raise_for_status()
        stats = resp.json().get("stats") or []
        splits = (stats[0].get("splits") if stats else []) or []
    except Exception as e:
        return json.dumps({"found": False, "error": f"BvP request failed: {e}"})
    if not splits:
        return json.dumps({"found": False, "error": None})
    stat = splits[0].get("stat", {}) or {}

    def _i(k):
        try:
            return int(stat.get(k, 0))
        except Exception:
            return 0

    def _f(k):
        try:
            return float(stat.get(k))
        except Exception:
            return None

    out = {"found": True, "error": None,
           "pa": _i("plateAppearances"), "ab": _i("atBats"), "h": _i("hits"),
           "hr": _i("homeRuns"), "bb": _i("baseOnBalls"), "k": _i("strikeOuts"),
           "avg": _f("avg"), "slg": _f("slg")}
    return json.dumps(out)


def career_bvp(batter_id, pitcher_id):
    """dict or None — parsed career vs-player line."""
    try:
        d = json.loads(_career_bvp_json(int(batter_id), int(pitcher_id)))
    except Exception:
        return None
    return d if d.get("found") else None


def render_bvp_card(batter_id, batter_name, pitcher_id, pitcher_name) -> None:
    d = career_bvp(batter_id, pitcher_id)
    st.markdown(
        f'<div style="font-size:12px; font-weight:700; color:{COLOR["gold"]}; '
        f'margin-top:12px;">{batter_name} vs {pitcher_name}</div>',
        unsafe_allow_html=True,
    )
    if d is None or not d.get("ab"):
        st.caption(f"No career meetings on record between {batter_name} and {pitcher_name} \u2014 "
                   f"shown as exactly that, not guessed around.")
    else:
        avg = f'{d["avg"]:.3f}' if d.get("avg") is not None else "\u2014"
        slg = f'{d["slg"]:.3f}' if d.get("slg") is not None else "\u2014"
        small = " \u00b7 small sample \u2014 read gently" if d["pa"] < 10 else ""
        st.markdown(
            f'<div style="font-family:\'JetBrains Mono\',monospace; font-size:13px; color:{COLOR["text"]};">'
            f'Career: <b>{d["h"]}-for-{d["ab"]}</b> \u00b7 AVG <b style="color:{COLOR["stat_high"]};">{avg}</b> '
            f'\u00b7 SLG <b style="color:{COLOR["stat_high"]};">{slg}</b> \u00b7 HR {d["hr"]} '
            f'\u00b7 BB {d["bb"]} \u00b7 K {d["k"]} \u00b7 {d["pa"]} PA{small}</div>',
            unsafe_allow_html=True,
        )
        st.caption("Source: MLB official vs-player split (career).")

    # This-season pitch-level detail from the batter's own parquet
    try:
        df, _err = _get_batter_df(batter_id)
        if df is not None and not df.empty and "pitcher" in df.columns:
            vs = df[pd.to_numeric(df["pitcher"], errors="coerce") == int(pitcher_id)]
            if not vs.empty:
                pitches = len(vs)
                bbe = int((vs["type"] == "X").sum()) if "type" in vs.columns else 0
                desc = vs["description"] if "description" in vs.columns else pd.Series(dtype=object)
                whiffs = int(desc.isin(_WHIFFS).sum())
                swings = int(desc.isin(_SWINGS).sum())
                hh = 0
                if "launch_speed" in vs.columns:
                    hh = int((pd.to_numeric(vs["launch_speed"], errors="coerce") >= 95).sum())
                whiff_pct = f"{whiffs / swings * 100:.0f}%" if swings else "\u2014"
                st.caption(
                    f"This season, pitch level: {pitches} pitches seen \u00b7 {bbe} batted balls \u00b7 "
                    f"whiff {whiff_pct} \u00b7 {hh} hard-hit (95+ mph). Source: Statcast pitch data."
                )
    except Exception:
        pass


# ---------------------------------------------------------------
# 2) Zone map — real xSLG on contact per Statcast zone 1-9
# ---------------------------------------------------------------
def render_zone_map(batter_id, batter_name, window_label: str = "L10") -> None:
    try:
        df, _err = _get_batter_df(batter_id)
    except Exception:
        df = None
    if df is None or df.empty or "zone" not in df.columns:
        st.caption("No zone data available for this batter.")
        return
    w = _WIN_KEY.get(window_label, "l10")
    if w != "season":
        df = apply_window(df, w, "games")

    st.markdown(
        f'<div style="font-size:12px; font-weight:700; color:{COLOR["gold"]}; margin-top:12px;">'
        f'Zone map \u00b7 {window_label} \u00b7 xSLG on contact (catcher\'s view)</div>',
        unsafe_allow_html=True,
    )
    zones = pd.to_numeric(df["zone"], errors="coerce")
    xslg = pd.to_numeric(df.get("estimated_slg_using_speedangle"), errors="coerce")
    is_bbe = df["type"] == "X" if "type" in df.columns else pd.Series(False, index=df.index)

    cells_html = []
    for row in ((1, 2, 3), (4, 5, 6), (7, 8, 9)):
        row_html = []
        for z in row:
            mask = zones == z
            n = int(mask.sum())
            zx = xslg[mask & is_bbe].dropna()
            if n < 15 or zx.empty:
                row_html.append(
                    f'<td style="width:33%; padding:10px 4px; text-align:center; '
                    f'background:{COLOR["text"]}0A; border:1px solid {COLOR["text"]}14; border-radius:6px;">'
                    f'<div style="font-size:12px; color:{COLOR["text"]}; opacity:0.4;">\u2014</div>'
                    f'<div style="font-size:9px; color:{COLOR["text"]}; opacity:0.4;">{n} p</div></td>')
                continue
            v = float(zx.mean())
            col = (COLOR["stat_high"] if v >= 0.500
                   else COLOR["warn"] if v >= 0.350 else COLOR["error"])
            row_html.append(
                f'<td style="width:33%; padding:10px 4px; text-align:center; '
                f'background:{col}26; border:1px solid {col}55; border-radius:6px;">'
                f'<div style="font-size:13px; font-weight:800; color:{col};">{v:.3f}</div>'
                f'<div style="font-size:9px; color:{COLOR["text"]}; opacity:0.6;">{n} p</div></td>')
        cells_html.append("<tr>" + "".join(row_html) + "</tr>")
    st.markdown(
        f'<table style="width:100%; border-collapse:separate; border-spacing:4px;">'
        f'{"".join(cells_html)}</table>',
        unsafe_allow_html=True,
    )
    st.caption("Zones 1-9 = the strike zone (top row is up). Blue = real damage on contact "
               "there, red = weak. Cells under 15 pitches gray out \u2014 too small to color honestly.")


# ---------------------------------------------------------------
# 3) Spray chart — real hc_x / hc_y landing points
# ---------------------------------------------------------------
def render_spray_chart(batter_id, batter_name, window_label: str = "L10") -> None:
    import altair as alt
    try:
        df, _err = _get_batter_df(batter_id)
    except Exception:
        df = None
    if df is None or df.empty or "hc_x" not in df.columns or "hc_y" not in df.columns:
        st.caption("No spray data available for this batter.")
        return
    w = _WIN_KEY.get(window_label, "l10")
    if w != "season":
        df = apply_window(df, w, "games")

    bb = df[(df.get("type") == "X")].copy() if "type" in df.columns else df.copy()
    bb["hc_x"] = pd.to_numeric(bb["hc_x"], errors="coerce")
    bb["hc_y"] = pd.to_numeric(bb["hc_y"], errors="coerce")
    bb = bb.dropna(subset=["hc_x", "hc_y"])
    if bb.empty:
        st.caption("No batted balls with landing coordinates in this window.")
        return

    st.markdown(
        f'<div style="font-size:12px; font-weight:700; color:{COLOR["gold"]}; margin-top:12px;">'
        f'Spray chart \u00b7 {window_label} \u00b7 {len(bb)} batted balls</div>',
        unsafe_allow_html=True,
    )
    # Standard Statcast field transform: home plate at origin, fair
    # territory opening upward.
    bb["x"] = bb["hc_x"] - 125.42
    bb["y"] = 198.27 - bb["hc_y"]

    def _bucket(ev):
        if ev == "home_run":
            return "HR"
        if ev in ("single", "double", "triple"):
            return "Hit"
        return "Out"
    bb["Result"] = bb["events"].map(_bucket) if "events" in bb.columns else "Out"

    chart = alt.Chart(bb).mark_circle(size=60, opacity=0.75).encode(
        x=alt.X("x:Q", axis=None, scale=alt.Scale(domain=[-130, 130])),
        y=alt.Y("y:Q", axis=None, scale=alt.Scale(domain=[-10, 210])),
        color=alt.Color("Result:N",
                        scale=alt.Scale(domain=["HR", "Hit", "Out"],
                                        range=[COLOR["gold"], COLOR["stat_high"], "#8a3a40"]),
                        legend=alt.Legend(orient="bottom", title=None)),
        tooltip=[alt.Tooltip("Result:N")],
    ).properties(height=260).configure_view(strokeOpacity=0)
    st.altair_chart(chart, use_container_width=True)
    st.caption("Real Statcast landing coordinates \u2014 home plate at the bottom, left field on "
               "the left. Gold = HR, blue = other hits, red = outs.")
