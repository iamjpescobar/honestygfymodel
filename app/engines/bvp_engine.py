import pandas as pd

try:
    import baseball_scraper as bs
    _SCRAPER_AVAILABLE = True
except ImportError:
    bs = None
    _SCRAPER_AVAILABLE = False


def get_bvp_history(pitcher_name: str, batter_name: str) -> pd.DataFrame:
    """
    Batter vs Pitcher history.
    Replace backend with your own DB/Statcast when ready.
    Returns an empty DataFrame (rather than crashing the whole page) if
    the baseball_scraper package isn't installed or the lookup fails.
    """
    if not _SCRAPER_AVAILABLE:
        return pd.DataFrame()

    try:
        df = bs.bvp(pitcher_name, batter_name)

        if df.empty:
            return pd.DataFrame()

        df = df.rename(columns={
            "PA": "Plate Appearances",
            "AB": "At Bats",
            "H": "Hits",
            "HR": "Home Runs",
            "K": "Strikeouts",
            "BB": "Walks",
            "AVG": "Batting Avg",
            "SLG": "Slugging",
            "OPS": "OPS"
        })

        return df

    except Exception:
        return pd.DataFrame()
