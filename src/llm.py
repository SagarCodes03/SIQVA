# src/llm.py
import ollama
import json
from config.settings import OLLAMA_MODEL

def parse_user_intent(user_query: str) -> dict:
    """Uses Ollama to extract intent, WMO ID, and the specific variable to plot."""
    system_prompt = """
    Analyze the user's oceanography query. Output ONLY a strict JSON object with these exact keys:
    - "intent": either "plot_profile" or "general_chat"
    - "wmo_id": the 7-digit float number as an integer, or null if none is mentioned
    - "variable": "TEMP" for temperature, "PSAL" for salinity, or null. If they ask to plot but don't specify, default to "TEMP".
    """
    
    try:
        response = ollama.chat(
            model=OLLAMA_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_query}
            ],
            format="json" # Forces Ollama to output valid JSON
        )
        return json.loads(response['message']['content'])
    except Exception as e:
        print(f"JSON Parsing Error: {e}")
        return {"intent": "general_chat", "wmo_id": None, "variable": None}

def generate_chat_response(messages: list) -> str:
    """Standard conversational fallback."""
    try:
        response = ollama.chat(model=OLLAMA_MODEL, messages=messages)
        return response['message']['content']
    except Exception as e:
        return f"Error communicating with model: {e}"