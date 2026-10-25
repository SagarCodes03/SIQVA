"""Constrained JSON-schema LLM extraction via Ollama (Llama 3.2 3B).

Strictly adheres to AGENTS.md rules:
- The LLM never sees profile data values.
- LLM is only called as a fallback for fields that rules_parser left unfilled or ambiguous.
- LLM outputs are constrained via JSON Schema (Ollama format parameter) with temperature 0.0.
- Single-field focused prompts with 4-6 few-shot examples.
- Injectable client interface for fast deterministic unit tests and swappable model backends.
"""

from __future__ import annotations

import json
import logging
from datetime import date, datetime
from typing import Any, Optional, Protocol

from pydantic import BaseModel, Field

from .spec import DepthRange, Intent, Variable

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "llama3.2"


class LLMUnavailableError(RuntimeError):
    """Raised when the LLM service (Ollama) is unavailable or unreachable."""

    pass


class LLMClient(Protocol):
    """Protocol for swappable LLM clients."""

    def chat(
        self,
        model: str,
        messages: list[dict[str, str]],
        format: dict[str, Any],
        options: dict[str, Any],
    ) -> Any:
        ...


class OllamaClient:
    """Default client wrapping the official ollama Python package."""

    def __init__(self, host: Optional[str] = None) -> None:
        try:
            import ollama

            self._client = ollama.Client(host=host) if host else ollama
        except ImportError:
            self._client = None

    def chat(
        self,
        model: str,
        messages: list[dict[str, str]],
        format: dict[str, Any],
        options: dict[str, Any],
    ) -> Any:
        if self._client is None:
            raise LLMUnavailableError("The 'ollama' Python package is not installed.")
        try:
            return self._client.chat(
                model=model,
                messages=messages,
                format=format,
                options=options,
            )
        except Exception as e:
            raise LLMUnavailableError(f"Ollama call failed: {e}") from e


def _extract_content(response: Any) -> str:
    """Helper to extract text content from an Ollama ChatResponse or dict."""
    if hasattr(response, "message") and hasattr(response.message, "content"):
        return str(response.message.content)
    if isinstance(response, dict):
        if "message" in response and "content" in response["message"]:
            return str(response["message"]["content"])
        if "content" in response:
            return str(response["content"])
    return str(response)


# ==============================================================================
# SCHEMAS AND PROMPTS (ONE FIELD PER CALL, TEMPERATURE 0, 4-6 EXAMPLES)
# ==============================================================================

# 1. INTENT EXTRACTION
INTENT_SCHEMA = {
    "type": "object",
    "properties": {
        "intent": {
            "type": "string",
            "enum": ["profile", "map", "ts", "trend"],
        }
    },
    "required": ["intent"],
}

_INTENT_MESSAGES = [
    {
        "role": "system",
        "content": (
            "You are an assistant for oceanographic Argo queries. "
            "Classify the user intent into exactly one of: 'profile' (depth profiles/vertical casts), "
            "'map' (spatial distribution/float trajectories/locations), 'ts' (temperature vs salinity diagrams), "
            "or 'trend' (time series or temporal changes). Return JSON."
        ),
    },
    {"role": "user", "content": "plot temperature in North Atlantic"},
    {"role": "assistant", "content": '{"intent": "map"}'},
    {"role": "user", "content": "show temperature vs depth near Hawaii"},
    {"role": "assistant", "content": '{"intent": "profile"}'},
    {"role": "user", "content": "salinity against temperature in Tasman Sea"},
    {"role": "assistant", "content": '{"intent": "ts"}'},
    {"role": "user", "content": "temperature change over time in Southern Ocean"},
    {"role": "assistant", "content": '{"intent": "trend"}'},
    {"role": "user", "content": "fetch salinity profiles in Mediterranean"},
    {"role": "assistant", "content": '{"intent": "profile"}'},
    {"role": "user", "content": "where are the active floats near Madagascar"},
    {"role": "assistant", "content": '{"intent": "map"}'},
]

# 2. VARIABLES EXTRACTION
VARIABLES_SCHEMA = {
    "type": "object",
    "properties": {
        "variables": {
            "type": "array",
            "items": {"type": "string", "enum": ["TEMP", "PSAL", "PRES"]},
        }
    },
    "required": ["variables"],
}

_VARIABLES_MESSAGES = [
    {
        "role": "system",
        "content": (
            "Extract requested ocean physical variables from the user query. "
            "Valid Argo variables: 'TEMP' (temperature, warm, heat), 'PSAL' (salinity, salt, practical salinity), "
            "'PRES' (pressure). Only include PRES if user explicitly says 'pressure'. "
            "Do not map depth or meters to PRES. Return JSON."
        ),
    },
    {"role": "user", "content": "show temperature in the Arabian Sea"},
    {"role": "assistant", "content": '{"variables": ["TEMP"]}'},
    {"role": "user", "content": "salinity and pressure in Bay of Bengal"},
    {"role": "assistant", "content": '{"variables": ["PSAL", "PRES"]}'},
    {"role": "user", "content": "heat content and saltiness in Indian Ocean"},
    {"role": "assistant", "content": '{"variables": ["TEMP", "PSAL"]}'},
    {"role": "user", "content": "water temperature down to 500 meters"},
    {"role": "assistant", "content": '{"variables": ["TEMP"]}'},
    {"role": "user", "content": "float salinity near Azores"},
    {"role": "assistant", "content": '{"variables": ["PSAL"]}'},
]

# 3. REGION NAME EXTRACTION
REGION_NAME_SCHEMA = {
    "type": "object",
    "properties": {
        "region_name": {"type": ["string", "null"]},
    },
    "required": ["region_name"],
}

_REGION_MESSAGES = [
    {
        "role": "system",
        "content": (
            "Extract the geographic ocean region, sea, or body of water name from the query. "
            "If no geographical body of water is mentioned, return null. Return JSON."
        ),
    },
    {"role": "user", "content": "temperature in the Weddell Sea during 2022"},
    {"role": "assistant", "content": '{"region_name": "Weddell Sea"}'},
    {"role": "user", "content": "salinity near Azores islands"},
    {"role": "assistant", "content": '{"region_name": "Azores"}'},
    {"role": "user", "content": "floats in the Eastern Mediterranean"},
    {"role": "assistant", "content": '{"region_name": "Eastern Mediterranean"}'},
    {"role": "user", "content": "temperature profiles between 0 and 500 dbar in 2021"},
    {"role": "assistant", "content": '{"region_name": null}'},
    {"role": "user", "content": "salinity measurements in North Pacific"},
    {"role": "assistant", "content": '{"region_name": "North Pacific"}'},
]

# 4. DATE RANGE EXTRACTION
DATE_RANGE_SCHEMA = {
    "type": "object",
    "properties": {
        "start": {"type": ["string", "null"]},
        "end": {"type": ["string", "null"]},
    },
    "required": ["start", "end"],
}

_DATE_MESSAGES = [
    {
        "role": "system",
        "content": (
            "Extract explicit calendar date ranges into ISO YYYY-MM-DD. "
            "If only a single year is given (e.g. 2021), span from YYYY-01-01 to YYYY-12-31. "
            "If relative, vague, or missing a year (e.g. 'March', 'recent', 'last month'), "
            "never guess: return null for both start and end. Return JSON."
        ),
    },
    {"role": "user", "content": "January to March 2022 in Arabian Sea"},
    {"role": "assistant", "content": '{"start": "2022-01-01", "end": "2022-03-31"}'},
    {"role": "user", "content": "temperature in year 2020"},
    {"role": "assistant", "content": '{"start": "2020-01-01", "end": "2020-12-31"}'},
    {"role": "user", "content": "between 2023-05-01 and 2023-05-15"},
    {"role": "assistant", "content": '{"start": "2023-05-01", "end": "2023-05-15"}'},
    {"role": "user", "content": "recent data in North Atlantic"},
    {"role": "assistant", "content": '{"start": null, "end": null}'},
    {"role": "user", "content": "salinity in March"},
    {"role": "assistant", "content": '{"start": null, "end": null}'},
    {"role": "user", "content": "from 2021-06-01 to 2021-08-31"},
    {"role": "assistant", "content": '{"start": "2021-06-01", "end": "2021-08-31"}'},
]

# 5. DEPTH RANGE EXTRACTION
DEPTH_RANGE_SCHEMA = {
    "type": "object",
    "properties": {
        "min_depth": {"type": ["number", "null"]},
        "max_depth": {"type": ["number", "null"]},
    },
    "required": ["min_depth", "max_depth"],
}

_DEPTH_MESSAGES = [
    {
        "role": "system",
        "content": (
            "Extract numeric depth range in meters or dbar from the user query. "
            "Surface level is 0. If unspecified, return null for both. Return JSON."
        ),
    },
    {"role": "user", "content": "top 500 m in North Atlantic"},
    {"role": "assistant", "content": '{"min_depth": 0.0, "max_depth": 500.0}'},
    {"role": "user", "content": "below 1000 m"},
    {"role": "assistant", "content": '{"min_depth": 1000.0, "max_depth": 2000.0}'},
    {"role": "user", "content": "between 100 and 300 dbar"},
    {"role": "assistant", "content": '{"min_depth": 100.0, "max_depth": 300.0}'},
    {"role": "user", "content": "upper ocean 200m"},
    {"role": "assistant", "content": '{"min_depth": 0.0, "max_depth": 200.0}'},
    {"role": "user", "content": "temperature profiles in Arabian Sea"},
    {"role": "assistant", "content": '{"min_depth": null, "max_depth": null}'},
]


# ==============================================================================
# CALL HELPERS
# ==============================================================================


def _call_ollama(
    base_messages: list[dict[str, str]],
    user_prompt: str,
    schema: dict[str, Any],
    client: Optional[Any] = None,
    model: str = DEFAULT_MODEL,
) -> Optional[dict[str, Any]]:
    """Execute a single-field Ollama call with JSON schema enforcement and temp 0."""
    if client is None:
        client = OllamaClient()

    messages = list(base_messages)
    messages.append({"role": "user", "content": user_prompt})

    try:
        resp = client.chat(
            model=model,
            messages=messages,
            format=schema,
            options={"temperature": 0.0},
        )
        content = _extract_content(resp).strip()
        if not content:
            return None
        return json.loads(content)
    except Exception as e:
        logger.warning(f"Ollama call for schema extraction failed: {e}")
        return None


def extract_intent_llm(
    question: str,
    client: Optional[Any] = None,
    model: str = DEFAULT_MODEL,
) -> Optional[Intent]:
    """Fallback LLM intent classification (profile | map | ts | trend)."""
    parsed = _call_ollama(_INTENT_MESSAGES, question, INTENT_SCHEMA, client=client, model=model)
    if parsed and "intent" in parsed and parsed["intent"]:
        try:
            return Intent(str(parsed["intent"]).lower())
        except ValueError:
            return None
    return None


def extract_variables_llm(
    question: str,
    client: Optional[Any] = None,
    model: str = DEFAULT_MODEL,
) -> Optional[list[Variable]]:
    """Fallback LLM variable extraction (TEMP, PSAL, PRES)."""
    parsed = _call_ollama(_VARIABLES_MESSAGES, question, VARIABLES_SCHEMA, client=client, model=model)
    if parsed and "variables" in parsed and isinstance(parsed["variables"], list):
        vars_list: list[Variable] = []
        for v in parsed["variables"]:
            try:
                vars_list.append(Variable(str(v).upper()))
            except ValueError:
                continue
        if vars_list:
            return vars_list
    return None


def extract_region_name_llm(
    question: str,
    client: Optional[Any] = None,
    model: str = DEFAULT_MODEL,
) -> Optional[str]:
    """Fallback LLM region name extraction. Result must be resolved via gazetteer."""
    parsed = _call_ollama(_REGION_MESSAGES, question, REGION_NAME_SCHEMA, client=client, model=model)
    if parsed and parsed.get("region_name"):
        val = str(parsed["region_name"]).strip()
        return val if val else None
    return None


def extract_date_range_llm(
    question: str,
    client: Optional[Any] = None,
    model: str = DEFAULT_MODEL,
) -> Optional[tuple[date, date]]:
    """Fallback LLM date range extraction. Never guesses ambiguous or relative dates."""
    parsed = _call_ollama(_DATE_MESSAGES, question, DATE_RANGE_SCHEMA, client=client, model=model)
    if parsed and parsed.get("start") and parsed.get("end"):
        try:
            s = datetime.strptime(str(parsed["start"]).strip(), "%Y-%m-%d").date()
            e = datetime.strptime(str(parsed["end"]).strip(), "%Y-%m-%d").date()
            return (s, e)
        except Exception:
            return None
    return None


def extract_depth_range_llm(
    question: str,
    client: Optional[Any] = None,
    model: str = DEFAULT_MODEL,
) -> Optional[DepthRange]:
    """Fallback LLM depth range extraction."""
    parsed = _call_ollama(_DEPTH_MESSAGES, question, DEPTH_RANGE_SCHEMA, client=client, model=model)
    if parsed and parsed.get("min_depth") is not None and parsed.get("max_depth") is not None:
        try:
            d_min = float(parsed["min_depth"])
            d_max = float(parsed["max_depth"])
            if 0.0 <= d_min <= d_max <= 2000.0:
                return DepthRange(min_depth=d_min, max_depth=d_max)
        except Exception:
            return None
    return None
