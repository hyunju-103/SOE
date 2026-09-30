"""
Shared portfolio-level helper: reducing a SOE-year panel down to one row
per SOE so counts/averages aren't inflated by counting the same SOE once
per year it appears.
"""

import pandas as pd


def latest_per_entity(df: pd.DataFrame) -> pd.DataFrame:
    """One row per Entity: its most recent year if Year varies, else the
    row as-is (already one row per Entity)."""
    if df.empty:
        return df
    if df["Year"].nunique() > 1:
        return df.sort_values("Year").groupby("Entity", as_index=False).last()
    return df.drop_duplicates(subset=["Entity"], keep="first")
