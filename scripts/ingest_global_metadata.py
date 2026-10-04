import os
import pandas as pd
from argopy import IndexFetcher
from supabase import create_client, Client
from dotenv import load_dotenv
from datetime import datetime, timedelta

load_dotenv()

# Initialize Supabase
url: str = os.environ.get("SUPABASE_URL")
key: str = os.environ.get("SUPABASE_KEY")
supabase: Client = create_client(url, key)

def fetch_global_active_floats():
    print("Fetching global ARGO index for active floats...")
    
    # Look for floats that have reported data in the last 30 days
    end_date = datetime.now().strftime('%Y-%m-%d')
    start_date = (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d')
    
    # Global bounding box [lon_min, lon_max, lat_min, lat_max, date_min, date_max]
    box = [-180, 180, -90, 90, start_date, end_date]
    
    try:
        # IndexFetcher ONLY downloads the text index, making it incredibly fast
        ds = IndexFetcher().region(box).to_dataframe()
        
        # Rename columns to match Supabase schema
        df_meta = ds.rename(columns={
            'wmo': 'float_wmo',
            'date': 'profile_date',
            'latitude': 'latitude',
            'longitude': 'longitude'
        })
        
        # Sort by date and keep ONLY the single most recent row for each float
        df_meta = df_meta.sort_values('profile_date')
        df_meta = df_meta.drop_duplicates(subset=['float_wmo'], keep='last')
        
        # Format dates for Supabase JSON
        df_meta['profile_date'] = df_meta['profile_date'].dt.strftime('%Y-%m-%d %H:%M:%S')
        
        # Keep only the essential columns
        df_final = df_meta[['float_wmo', 'profile_date', 'latitude', 'longitude']]
        records = df_final.to_dict(orient='records')
        
        print(f" Found {len(records)} active global floats. Uploading to Supabase...")
        
        # Upsert in batches
        batch_size = 1000
        for i in range(0, len(records), batch_size):
            batch = records[i:i + batch_size]
            supabase.table("argo_metadata").upsert(batch).execute()
            print(f"Uploaded batch {i//batch_size + 1}/{(len(records)//batch_size) + 1}")
            
        print(" Global active float index complete!")
        
    except Exception as e:
        print(f"Error during global ingestion: {e}")

if __name__ == "__main__":
    fetch_global_active_floats()