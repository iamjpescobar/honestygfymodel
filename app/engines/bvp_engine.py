"""
Batter vs Pitcher history — computed from this app's own real pitch data.

Every number here is derived from actual recorded pitches (the same
per-player Statcast data the rest of the app runs on), filtered to
plate appearances where THIS batter faced THIS pitcher. Nothing is
estimated or filled in: if the two haven't met, the table is empty.

Honest scope: the data on disk covers the current season, so this is
2026 head-to-head history. Multi-season BvP would require extending
the precompute's date range — a deliberate future expansion, not a
data gap being papered over.

Stat definitions (standard scoring, computed per plate appearance from
the final pitch of each PA):
  PA   = plate appearances ending in a recorded event
  AB   = PAs ending in a hit, out, or reach-on-error (walks/HBP/sac excluded)
  AVG  = H / AB
  SLG  = total bases / AB
  OBP  = (H + BB + HBP) / (AB + BB + HBP + SF)
  OPS  = OBP + SLG
"""

import pandas as pd

_HIT_EVENTS = {"single", "double", "triple", "home_run"}
_AB_EVENTS = _HIT_EVENTS | {
    "field_out", "strikeout", "strikeout_double_play", "double_play",
    "grounded_into_double_play", "force_out", "fielders_choice_out",
    "field_error", "triple_play",
}
_STRIKEOUT_EVENTS = {"strikeout", "strikeout_double_play"}


def get_bvp_history(pitcher_name: str = None, batter_name: str = None,
                    pitcher_id=None, batter_id=None) -> pd.DataFrame:
    """
    Real batter-vs-pitcher history from the app's own pitch data.

    Callers should pass BOTH MLBAM ids (from the roster). Names are
    accepted for backward compatibility and display, but no name-based
    lookup is performed — without ids this returns an empty frame
    rather than guessing identities.
    """
    if pitcher_id is None or batter_id is None:
        return pd.DataFrame()

    try:
        pid = int(pitcher_id)
        bid = int(batter_id)
    except (TypeError, ValueError):
        return pd.DataFrame()

    # The batter's own data, read through the same cached parquet-first
    # loader the rest of the app uses.
    from engines.statcast_engine import _get_batter_df
    df, _error = _get_batter_df(bid)

    if df is None or df.empty or "pitcher" not in df.columns:
        # "pitcher" column absent means this player's file predates the
        # BvP-enabled data package — empty until the nightly refresh.
        return pd.DataFrame()

    faced = df[pd.to_numeric(df["pitcher"], errors="coerce") == pid]
    if faced.empty or "events" not in faced.columns:
        return pd.DataFrame()

    pa_events = faced["events"].dropna()
    pa = int(len(pa_events))
    if pa == 0:
        return pd.DataFrame()

    hits = int(pa_events.isin(_HIT_EVENTS).sum())
    hr = int((pa_events == "home_run").sum())
    k = int(pa_events.isin(_STRIKEOUT_EVENTS).sum())
    bb = int((pa_events == "walk").sum())
    hbp = int((pa_events == "hit_by_pitch").sum())
    sf = int((pa_events == "sac_fly").sum())
    ab = int(pa_events.isin(_AB_EVENTS).sum())

    total_bases = (
        int((pa_events == "single").sum()) * 1
        + int((pa_events == "double").sum()) * 2
        + int((pa_events == "triple").sum()) * 3
        + hr * 4
    )

    avg = round(hits / ab, 3) if ab > 0 else 0.0
    slg = round(total_bases / ab, 3) if ab > 0 else 0.0
    obp_denom = ab + bb + hbp + sf
    obp = round((hits + bb + hbp) / obp_denom, 3) if obp_denom > 0 else 0.0
    ops = round(obp + slg, 3)

    return pd.DataFrame([{
        "Plate Appearances": pa,
        "At Bats": ab,
        "Hits": hits,
        "Home Runs": hr,
        "Strikeouts": k,
        "Walks": bb,
        "Batting Avg": avg,
        "Slugging": slg,
        "OPS": ops,
    }])