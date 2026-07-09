import sys
import os

# Ensure project root is in Python path
ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
if ROOT_DIR not in sys.path:
    sys.path.append(ROOT_DIR)

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
