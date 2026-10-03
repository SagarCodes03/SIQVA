# src/fetcher.py
from argopy import DataFetcher
import pandas as pd

def fetch_float_data(wmo_id: int) -> pd.DataFrame:
    """Fetch depth profile data for a specific ARGO float WMO ID."""
    try:
        ds = DataFetcher().float(wmo_id).to_dataframe()
        df = ds[['CYCLE_NUMBER', 'PRES', 'TEMP', 'PSAL', 'LATITUDE', 'LONGITUDE', 'TIME']].dropna(subset=['TEMP', 'PRES'])
        return df
    except Exception as e:
        print(f"Error fetching data for float {wmo_id}: {e}")
        return pd.DataFrame()