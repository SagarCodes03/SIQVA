# src/db.py
import os
from supabase import create_client, Client
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

url: str = os.environ.get("SUPABASE_URL")
key: str = os.environ.get("SUPABASE_KEY")
supabase: Client = create_client(url, key)

def get_floats_in_bounding_box(lat_min: float, lat_max: float, lon_min: float, lon_max: float, limit: int = 5):
    """Finds active ARGO floats in Supabase within a given lat/lon bounding box."""
    try:
        response = supabase.table("argo_metadata") \
            .select("float_wmo, latitude, longitude, profile_date") \
            .gte("latitude", lat_min) \
            .lte("latitude", lat_max) \
            .gte("longitude", lon_min) \
            .lte("longitude", lon_max) \
            .order("profile_date", desc=True) \
            .limit(limit) \
            .execute()
        
        return response.data
    except Exception as e:
        print(f"Supabase spatial query error: {e}")
        return []

def get_all_active_floats():
    """Fetches the latest locations of all active floats globally."""
    try:
        response = supabase.table("argo_metadata") \
            .select("float_wmo, latitude, longitude, profile_date") \
            .execute()
        return response.data
    except Exception as e:
        print(f"Supabase global query error: {e}")
        return []