import pandas as pd
import baseball_scraper as bs

def get_bvp_history(pitcher_name: str, batter_name: str) -> pd.DataFrame:
    """
    Batter vs Pitcher history.
    Replace backend with your own DB/Statcast when ready.
    """

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
