import ollama
import json
from config.settings import OLLAMA_MODEL  # Assumes you have this, or hardcode it as "llama3.2"

def parse_user_intent(user_query: str) -> dict:
    """Uses Ollama to extract intent, WMO IDs, or spatial bounding boxes."""
    system_prompt = """
    Analyze the oceanography query. Output ONLY a valid JSON object with these exact keys:
    - "intent": MUST be one of ["depth_profile", "position_map", "general_chat"]
      * Use "depth_profile" for temperature/salinity profiles or plots at depth.
      * Use "position_map" if the user wants to see WHERE floats are located (e.g., "Show all floats in Indian Ocean", "Map of floats").
    - "wmo_id": integer float WMO ID if mentioned, else null
    - "variable": "TEMP" for temperature, "PSAL" for salinity. Default to "TEMP".
    - "location_name": name of the ocean/region if mentioned (e.g. "West Bengal", "Arabian Sea"), else null
    - "bounding_box": null OR [lat_min, lat_max, lon_min, lon_max] matching the requested region.
      Examples:
      - "West Bengal / Bay of Bengal": [18.0, 22.5, 85.0, 92.0]
      - "Kerala Coast / Arabian Sea": [8.0, 15.0, 70.0, 77.0]
      - "Indian Ocean": [-10.0, 20.0, 50.0, 100.0]
    """
    
    try:
        response = ollama.chat(
            model=OLLAMA_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_query}
            ],
            format="json"
        )
        return json.loads(response['message']['content'])
    except Exception as e:
        print(f"LLM Parsing Error: {e}")
        return {"intent": "general_chat", "wmo_id": None, "variable": None, "location_name": None, "bounding_box": None}

def generate_chat_response(messages: list) -> str:
    try:
        response = ollama.chat(model=OLLAMA_MODEL, messages=messages)
        return response['message']['content']
    except Exception as e:
        return f"Error communicating with model: {e}"