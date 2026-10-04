# src/fetcher.py
import streamlit as st
from argopy import DataFetcher
import pandas as pd

@st.cache_data(ttl=86400, show_spinner=False)  # Caches data for 24 hours (86,400 seconds)
def fetch_float_data(wmo_id: int) -> pd.DataFrame:
    """Fetches full telemetry profile data for a specific ARGO float and caches it."""
    try:
        # Fetch the heavy dataset from NOAA
        ds = DataFetcher().float(wmo_id).to_dataframe()
        
        # Ensure we only return necessary columns to save memory
        columns_to_keep = ['CYCLE_NUMBER', 'PRES', 'TEMP', 'PSAL', 'TIME', 'LATITUDE', 'LONGITUDE']
        
        # Drop rows where both Temperature and Salinity are missing
        df = ds[columns_to_keep].dropna(subset=['TEMP', 'PSAL'], how='all')
        
        return df
    except Exception as e:
        print(f"Argopy Fetch Error: {e}")
        return pd.DataFrame()