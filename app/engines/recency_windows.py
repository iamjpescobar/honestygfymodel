"""
Real recency windows for slicing a batter's raw per-pitch Statcast
data — "last 25 PA," "last 25 BBE," "last 25 games," etc. Shared by
SLAM, the Lineup table's window filter, and the pitch-matchup stat, so
there's exactly one real definition of "last N" instead of three
slightly different ones scattered across files.

All windows are computed from the SAME raw per-pitch DataFrame
(as returned by pybaseball's statcast_batter) — nothing here re-fetches
data, it only slices what's already been pulled.
"""
import pandas as pd


def _sorted(df: pd.DataFrame) -> pd.DataFrame:
    """Guarantees chronological order — never assume the raw pull
    already came back sorted."""
    if df.empty:
        return df
    sort_cols = [c for c in ["game_date", "at_bat_number", "pitch_number"] if c in df.columns]
    return df.sort_values(sort_cols) if sort_cols else df


def last_n_games(df: pd.DataFrame, n: int) -> pd.DataFrame:
    """Every pitch from the batter's N most recent games (by real
    game_date), not just the last N rows — a batter can see 15+
    pitches in one game, so this isn't the same as last_n rows."""
    df = _sorted(df)
    if df.empty or "game_date" not in df.columns:
        return df
    recent_dates = sorted(df["game_date"].dropna().unique())[-n:]
    return df[df["game_date"].isin(recent_dates)]


def last_n_pa(df: pd.DataFrame, n: int) -> pd.DataFrame:
    """Every pitch from the batter's N most recent plate appearances.
    Identifies a unique PA by (game_pk, at_bat_number) — at_bat_number
    alone isn't unique across different games."""
    df = _sorted(df)
    if df.empty or not {"game_pk", "at_bat_number"}.issubset(df.columns):
        return df
    pa_keys = df[["game_pk", "at_bat_number", "game_date"]].drop_duplicates()
    pa_keys = pa_keys.sort_values(["game_date", "at_bat_number"])
    recent_pa = pa_keys.tail(n)
    merged = df.merge(recent_pa[["game_pk", "at_bat_number"]], on=["game_pk", "at_bat_number"], how="inner")
    return merged


def last_n_bbe(df: pd.DataFrame, n: int) -> pd.DataFrame:
    """
    Every pitch within the same stretch of games as the batter's N
    most recent Batted Ball Events (type == 'X') — NOT just the N BBE
    rows themselves. That distinction matters: contact-quality stats
    (Barrel%, HH%, etc.) only ever look at BBE rows anyway, so this
    doesn't change them. But SwStr%/Whiff%/Blast% need to see the
    swings that DIDN'T end in contact too — a swinging strike is by
    definition not a BBE row, so a version of this window that
    literally kept only the 25 BBE rows silently deleted every
    swing-and-miss before those stats ever got computed, guaranteeing
    a false 0 no matter how many real whiffs happened.
    """
    df = _sorted(df)
    if df.empty or "type" not in df.columns:
        return df
    bbe = df[df["type"] == "X"]
    if bbe.empty:
        return bbe
    recent_bbe = bbe.tail(n)
    if "game_date" not in df.columns:
        return recent_bbe
    earliest_date = recent_bbe["game_date"].min()
    return df[df["game_date"] >= earliest_date]


WINDOW_LABELS = {
    "season": "This Season",
    "l300": "Last 300",
    "l250": "Last 250",
    "l200": "Last 200",
    "l75": "Last 75 Games",
    "l60": "Last 60 Games",
    "l50": "Last 50 Games",
    "l25": "Last 25",
    "l20": "Last 20",
    "l15": "Last 15",
    "l10": "Last 10",
    "l5": "Last 5",
    "l3": "Last 3",
    "l1": "Last Game",
}

# THE SHORT WINDOWS ARE REAL BUT THIN, AND CALLERS HAVE TO SAY SO.
#
# l3 and l1 were added for the Game Card's pitcher splits, where the
# question is "what has he looked like lately" and a five-start window
# can still be a month old for a starter. They are honest slices of real
# data — nothing here estimates or smooths.
#
# But one start is roughly 25 batters faced, and a rate over 25 at-bats
# is noise wearing the costume of a measurement. A .400 BA against on one
# night says almost nothing about tomorrow, and it renders in the same
# table, in the same font, as a season figure computed over 700.
#
# So: this map exists for any caller that renders a window, and it is the
# reason the pitcher splits table shows IP and a games count beside the
# rates rather than the rates alone. If you add a control that offers
# these, show the sample next to the number. The reader cannot see the
# denominator unless you put it there.
THIN_WINDOWS = {"l1", "l3", "l5"}


# THE LONG WINDOWS HAVE THE OPPOSITE PROBLEM, AND IT IS QUIETER.
#
# l50 / l75 / l200 / l250 / l300 were added 2026-08-17 for research that
# wants a baseline past the point where the power stats carry real
# signal — HR rate needs ~170 PA and ISO ~160 AB, so a 25-game window
# (~110 PA) is under both.
#
# The failure mode is not a thin sample rendered as thick. It is a
# window that SILENTLY RETURNS LESS THAN IT SAYS. Every slice below is
# a tail(): ask for the last 250 PA from a rookie who has 90 and you get
# 90, correctly computed, under a label that reads 250. Nothing errors
# and no rate is wrong — the number is just built on a third of the
# sample the label claims, and on a page where it sits in the same font
# beside a veteran's real 250.
#
# Also worth knowing before setting one of these as a default: the
# parquet only holds THIS season. Nothing here can reach back further,
# so by late season "last 300 PA" and "season" converge for an everyday
# bat, while in April every long window IS the season.
#
# Any control offering these has to say so. The Game Card's window
# selector carries that note in its help text.
LONG_WINDOWS = {"l50", "l75", "l200", "l250", "l300"}


def apply_window(df: pd.DataFrame, window: str, unit: str) -> pd.DataFrame:
    """
    Slices df by a named window ("season"/"l300"/"l250"/"l200"/"l75"/
    "l60"/"l50"/"l25"/"l20"/"l15"/"l10"/"l5"/"l3"/"l1") and unit
    ("games"/"pa"/"bbe"). "season" returns df
    unchanged — the full pull already covers the season since
    statcast_engine.py pulls from the season start by default.

    An unrecognised window returns df UNCHANGED — i.e. the season. That
    is deliberate and is the safe direction: a typo shows more data than
    asked for, never a silently empty table that reads as "this pitcher
    has no history".
    """
    if window == "season" or df.empty:
        return df

    n = {"l300": 300, "l250": 250, "l200": 200, "l75": 75, "l60": 60,
         "l50": 50, "l25": 25, "l20": 20, "l15": 15, "l10": 10,
         "l5": 5, "l3": 3, "l1": 1}.get(window)
    if n is None:
        return df

    if unit == "games":
        return last_n_games(df, n)
    if unit == "pa":
        return last_n_pa(df, n)
    if unit == "bbe":
        return last_n_bbe(df, n)
    return df
