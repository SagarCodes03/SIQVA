"""Provider-neutral LLM extraction backend with optional Ollama support.

Strictly adheres to AGENTS.md rules:
- The LLM never sees profile data values, statistics, or fetched results.
- Payload contains ONLY the question text and fixed instructions.
- LLM is only called as a fallback for fields that rules_parser left unfilled or ambiguous.
- Rules-resolved fields are NEVER overridden.
- Output is constrained via JSON and validated by Pydantic / gazetteer / enums.
- One call per question covering only missing fields.
- Circuit breaker, hourly session call limit, and daily call cap.
- API keys are never logged and never shown in cards or error messages.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
import json
import logging
import os
from pathlib import Path
import threading
import time
from typing import Any, Optional, Protocol, Union

import requests
from pydantic import BaseModel, Field

from .spec import DepthRange, Intent, Variable

logger = logging.getLogger(__name__)

# Named Constants
MAX_QUESTION_LENGTH: int = 500
LLM_TIMEOUT_SECONDS: float = 10.0
MAX_RETRY_AFTER_SECONDS: float = 10.0
CIRCUIT_BREAKER_FAILURES: int = 3
CIRCUIT_BREAKER_COOLDOWN_SECONDS: float = 60.0
SESSION_CALL_LIMIT_PER_HOUR: int = 20
DEFAULT_DAILY_CAP: int = 500
DEFAULT_MODEL: str = "llama3.2"
USAGE_FILE_PATH: Path = Path("data/llm_usage.json")


class LLMUnavailableError(RuntimeError):
    """Raised when the LLM service is unavailable, rate limited, or unreachable."""

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


# ==============================================================================
# CONFIGURATION RESOLUTION
# ==============================================================================


def get_llm_config_value(key: str, default: Optional[str] = None) -> Optional[str]:
    """Retrieve config value checking os.environ first, then Streamlit secrets safely.

    A missing secrets.toml or Streamlit error never raises or shows a warning.
    """
    # 1. Environment variable first
    val = os.environ.get(key)
    if val is not None and val.strip() != "":
        return val.strip()

    # 2. Streamlit secrets second, inside try/except
    try:
        import streamlit as st

        if hasattr(st, "secrets") and st.secrets is not None:
            if key in st.secrets:
                s_val = st.secrets[key]
                if s_val is not None and str(s_val).strip() != "":
                    return str(s_val).strip()
            if "siqva" in st.secrets and isinstance(st.secrets["siqva"], dict) and key in st.secrets["siqva"]:
                s_val = st.secrets["siqva"][key]
                if s_val is not None and str(s_val).strip() != "":
                    return str(s_val).strip()
    except Exception:
        pass

    return default


@dataclass
class LLMConfig:
    """Resolved configuration for the language model backend."""

    backend: str  # "openai_compatible" | "ollama" | "none"
    base_url: Optional[str] = None
    model: Optional[str] = None
    api_key: Optional[str] = None
    json_mode: str = "json_object"  # "none" | "json_object" | "json_schema"
    daily_cap: int = DEFAULT_DAILY_CAP


def get_llm_config() -> LLMConfig:
    """Resolve LLM configuration following strict lookup order and validation rules.

    Default backend is 'none' when base_url, model, or api_key are missing for openai_compatible.
    """
    raw_backend = (get_llm_config_value("SIQVA_LLM_BACKEND") or "").strip().lower()
    base_url = get_llm_config_value("SIQVA_LLM_BASE_URL")
    model = get_llm_config_value("SIQVA_LLM_MODEL")
    api_key = get_llm_config_value("SIQVA_LLM_API_KEY")
    json_mode = (get_llm_config_value("SIQVA_LLM_JSON_MODE", "json_object") or "json_object").strip().lower()
    if json_mode not in ("none", "json_object", "json_schema"):
        json_mode = "json_object"

    daily_cap_str = get_llm_config_value("SIQVA_LLM_DAILY_CAP", str(DEFAULT_DAILY_CAP))
    try:
        daily_cap = int(daily_cap_str) if daily_cap_str else DEFAULT_DAILY_CAP
    except (ValueError, TypeError):
        daily_cap = DEFAULT_DAILY_CAP

    if raw_backend == "none":
        return LLMConfig(backend="none", base_url=base_url, model=model, api_key=api_key, json_mode=json_mode, daily_cap=daily_cap)

    if raw_backend == "ollama":
        ollama_model = model or os.environ.get("OLLAMA_MODEL", DEFAULT_MODEL)
        return LLMConfig(backend="ollama", base_url=base_url, model=ollama_model, api_key=api_key, json_mode=json_mode, daily_cap=daily_cap)

    if raw_backend == "openai_compatible":
        # Default none when base_url, model, or api_key are missing
        if not base_url or not model or not api_key:
            return LLMConfig(backend="none", base_url=base_url, model=model, api_key=api_key, json_mode=json_mode, daily_cap=daily_cap)
        return LLMConfig(backend="openai_compatible", base_url=base_url.rstrip("/"), model=model, api_key=api_key, json_mode=json_mode, daily_cap=daily_cap)

    # If backend not explicitly set, auto-detect openai_compatible if all 3 credentials exist
    if base_url and model and api_key:
        return LLMConfig(backend="openai_compatible", base_url=base_url.rstrip("/"), model=model, api_key=api_key, json_mode=json_mode, daily_cap=daily_cap)

    return LLMConfig(backend="none", base_url=base_url, model=model, api_key=api_key, json_mode=json_mode, daily_cap=daily_cap)


def is_hosted_backend_active() -> bool:
    """Return True if an openai_compatible hosted backend is currently active."""
    return get_llm_config().backend == "openai_compatible"


# ==============================================================================
# CIRCUIT BREAKER & USAGE TRACKING
# ==============================================================================

_circuit_failures: int = 0
_circuit_cooldown_until: Optional[float] = None
_session_call_timestamps: list[float] = []
_usage_lock = threading.Lock()


def is_circuit_open() -> bool:
    """Return True if the circuit breaker is currently open (cooling down)."""
    global _circuit_cooldown_until
    if _circuit_cooldown_until is not None:
        if time.monotonic() < _circuit_cooldown_until:
            return True
        # Cooldown period has elapsed; allow trial request
        _circuit_cooldown_until = None
    return False


def record_circuit_failure() -> None:
    """Record a failure; trip circuit breaker after CIRCUIT_BREAKER_FAILURES."""
    global _circuit_failures, _circuit_cooldown_until
    _circuit_failures += 1
    if _circuit_failures >= CIRCUIT_BREAKER_FAILURES:
        _circuit_cooldown_until = time.monotonic() + CIRCUIT_BREAKER_COOLDOWN_SECONDS
        logger.warning(
            "LLM circuit breaker tripped after %d consecutive failures. Cooling down for %.0fs.",
            _circuit_failures,
            CIRCUIT_BREAKER_COOLDOWN_SECONDS,
        )


def record_circuit_success() -> None:
    """Record a successful call, resetting circuit breaker failure count."""
    global _circuit_failures, _circuit_cooldown_until
    _circuit_failures = 0
    _circuit_cooldown_until = None


def reset_circuit_breaker() -> None:
    """Reset circuit breaker state (used in tests)."""
    global _circuit_failures, _circuit_cooldown_until
    _circuit_failures = 0
    _circuit_cooldown_until = None


def get_session_calls_past_hour() -> int:
    """Return number of LLM calls made in the current session over the past 60 minutes."""
    global _session_call_timestamps
    now = time.time()
    cutoff = now - 3600.0
    _session_call_timestamps = [t for t in _session_call_timestamps if t >= cutoff]
    return len(_session_call_timestamps)


def can_make_session_call() -> bool:
    """Check if session is under the hourly call limit."""
    return get_session_calls_past_hour() < SESSION_CALL_LIMIT_PER_HOUR


def record_session_call() -> None:
    """Record an LLM call timestamp for the current session."""
    global _session_call_timestamps
    _session_call_timestamps.append(time.time())


def reset_session_tracker() -> None:
    """Reset session call timestamps (used in tests)."""
    global _session_call_timestamps
    _session_call_timestamps = []


def _read_usage_data(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _write_usage_data(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        tmp_path = path.with_suffix(".tmp")
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(data, f)
        tmp_path.replace(path)
    except Exception as e:
        logger.warning("Failed writing LLM usage data: %s", e)


def get_daily_calls(path: Optional[Path] = None) -> int:
    """Return number of calls made today according to local usage file."""
    p = path or USAGE_FILE_PATH
    with _usage_lock:
        data = _read_usage_data(p)
        today_str = date.today().isoformat()
        if data.get("date") == today_str:
            return int(data.get("calls", 0))
        return 0


def can_make_daily_call(cap: Optional[int] = None, path: Optional[Path] = None) -> bool:
    """Check if today's call count is below the daily ceiling."""
    c = cap if cap is not None else get_llm_config().daily_cap
    return get_daily_calls(path=path) < c


def record_daily_call(tokens: int = 0, path: Optional[Path] = None) -> None:
    """Record a completed call and token count for today, logging without question text."""
    p = path or USAGE_FILE_PATH
    today_str = date.today().isoformat()
    with _usage_lock:
        data = _read_usage_data(p)
        if data.get("date") == today_str:
            new_calls = int(data.get("calls", 0)) + 1
            new_tokens = int(data.get("total_tokens", 0)) + tokens
        else:
            new_calls = 1
            new_tokens = tokens
        _write_usage_data(p, {"date": today_str, "calls": new_calls, "total_tokens": new_tokens})

    # Log token counts and call counts (never question text) when SIQVA_SHARED_HISTORY is off
    if os.environ.get("SIQVA_SHARED_HISTORY") == "0":
        logger.info(
            "Hosted LLM usage: %d tokens recorded. Calls today: %d",
            tokens,
            new_calls,
        )


def reset_daily_tracker(path: Optional[Path] = None) -> None:
    """Reset the daily usage counter file (used in tests)."""
    p = path or USAGE_FILE_PATH
    with _usage_lock:
        if p.exists():
            try:
                p.unlink()
            except Exception:
                pass


# ==============================================================================
# OPENAI-COMPATIBLE CLIENT
# ==============================================================================


class OpenAICompatibleClient:
    """Provider-neutral client for OpenAI-compatible chat completion APIs."""

    def __init__(
        self,
        base_url: str,
        model: str,
        api_key: str,
        json_mode: str = "json_object",
        timeout: float = LLM_TIMEOUT_SECONDS,
        daily_cap: int = DEFAULT_DAILY_CAP,
        session: Optional[requests.Session] = None,
        usage_file_path: Optional[Path] = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.api_key = api_key
        self.json_mode = json_mode
        self.timeout = timeout
        self.daily_cap = daily_cap
        self.session = session or requests.Session()
        self.usage_file_path = usage_file_path

    def is_available(self) -> bool:
        """Check availability without making ping calls."""
        if is_circuit_open():
            return False
        if not can_make_session_call():
            return False
        if not can_make_daily_call(self.daily_cap, path=self.usage_file_path):
            return False
        return True

    def chat(
        self,
        messages: list[dict[str, str]],
        schema: Optional[dict[str, Any]] = None,
    ) -> str:
        """Send chat completion request to the OpenAI-compatible endpoint.

        Parameters sent: model, messages, temperature (0.0), max_tokens, and response_format.
        API key is never logged or included in exceptions.
        """
        if is_circuit_open():
            raise LLMUnavailableError("Circuit breaker active: 3 consecutive failures. Skipping API for 60s.")
        if not can_make_session_call():
            raise LLMUnavailableError(f"Session hourly call limit reached ({SESSION_CALL_LIMIT_PER_HOUR} calls/hr).")
        if not can_make_daily_call(self.daily_cap, path=self.usage_file_path):
            raise LLMUnavailableError(f"Daily call limit reached ({self.daily_cap} calls/day).")

        url = f"{self.base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": 0.0,
            "max_tokens": 500,
        }
        if self.json_mode == "json_object":
            payload["response_format"] = {"type": "json_object"}
        elif self.json_mode == "json_schema" and schema is not None:
            payload["response_format"] = {
                "type": "json_schema",
                "json_schema": {"name": "argo_query", "schema": schema},
            }

        resp = None
        try:
            resp = self.session.post(url, headers=headers, json=payload, timeout=self.timeout)
        except requests.Timeout as e:
            record_circuit_failure()
            raise LLMUnavailableError("Language model request timed out.") from e
        except requests.RequestException as e:
            record_circuit_failure()
            raise LLMUnavailableError("Language model connection error.") from e

        # Handle 429 rate limit with Retry-After
        if resp.status_code == 429:
            retry_header = resp.headers.get("Retry-After")
            if retry_header:
                try:
                    retry_s = float(retry_header)
                    if 0 < retry_s <= MAX_RETRY_AFTER_SECONDS:
                        time.sleep(retry_s)
                        try:
                            resp = self.session.post(url, headers=headers, json=payload, timeout=self.timeout)
                        except Exception:
                            pass
                except (ValueError, TypeError):
                    pass

            if resp.status_code == 429:
                record_circuit_failure()
                raise LLMUnavailableError("Language model rate limited (HTTP 429).")

        if resp.status_code != 200:
            record_circuit_failure()
            raise LLMUnavailableError(f"Language model returned HTTP error {resp.status_code}.")

        # Success
        record_circuit_success()
        record_session_call()

        try:
            data = resp.json()
        except Exception as e:
            raise LLMUnavailableError("Invalid JSON response from language model provider.") from e

        usage = data.get("usage", {})
        tokens = int(usage.get("total_tokens", 0))
        record_daily_call(tokens=tokens, path=self.usage_file_path)

        try:
            return str(data["choices"][0]["message"]["content"])
        except (KeyError, IndexError, TypeError) as e:
            raise LLMUnavailableError("Unexpected response structure from language model provider.") from e


# ==============================================================================
# LEGACY OLLAMA SUPPORT
# ==============================================================================

_LAST_UNAVAILABLE_TIMESTAMP: Optional[float] = None
UNAVAILABLE_CACHE_TTL_SECONDS: float = 30.0


def reset_availability_cache() -> None:
    """Reset cached unavailable status (used by tests)."""
    global _LAST_UNAVAILABLE_TIMESTAMP
    _LAST_UNAVAILABLE_TIMESTAMP = None


class OllamaClient:
    """Default client wrapping the official ollama Python package."""

    def __init__(self, host: Optional[str] = None, timeout: float = 2.0) -> None:
        self.host = host
        self.timeout = timeout
        try:
            import ollama

            self._client = ollama.Client(host=host, timeout=timeout)
        except ImportError:
            self._client = None

    def is_available(self, timeout: float = 1.5) -> bool:
        """Fast check (1-2s) to determine if Ollama daemon is reachable."""
        if self._client is None:
            return False
        try:
            import ollama

            check_client = ollama.Client(host=self.host, timeout=timeout)
            check_client.list()
            return True
        except Exception as e:
            logger.info("Ollama availability check failed: %s", e)
            return False

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


def check_llm_availability(client: Optional[Any] = None, timeout: float = 1.5) -> bool:
    """Check if the configured LLM backend is available.

    For custom clients (e.g. tests): invokes client.is_available() with 30s unavailable caching.
    For openai_compatible: checks circuit breaker and rate limits without ping calls.
    For ollama: runs fast probe with 30s cache.
    For none: returns False.
    """
    global _LAST_UNAVAILABLE_TIMESTAMP

    # Custom mock clients or explicit clients
    if client is not None:
        if hasattr(client, "is_available"):
            now = time.monotonic()
            if _LAST_UNAVAILABLE_TIMESTAMP is not None:
                if now - _LAST_UNAVAILABLE_TIMESTAMP < UNAVAILABLE_CACHE_TTL_SECONDS:
                    return False
                _LAST_UNAVAILABLE_TIMESTAMP = None
            try:
                available = bool(client.is_available(timeout=timeout))
            except TypeError:
                available = bool(client.is_available())
            except Exception:
                available = False

            if not available:
                _LAST_UNAVAILABLE_TIMESTAMP = now
            else:
                _LAST_UNAVAILABLE_TIMESTAMP = None
            return available
        return True

    cfg = get_llm_config()
    if cfg.backend == "none":
        return False

    if cfg.backend == "openai_compatible":
        if is_circuit_open():
            return False
        if not can_make_session_call():
            return False
        if not can_make_daily_call(cfg.daily_cap):
            return False
        return True

    if cfg.backend == "ollama":
        now = time.monotonic()
        if _LAST_UNAVAILABLE_TIMESTAMP is not None:
            if now - _LAST_UNAVAILABLE_TIMESTAMP < UNAVAILABLE_CACHE_TTL_SECONDS:
                logger.debug("Ollama availability cached as unavailable")
                return False
            _LAST_UNAVAILABLE_TIMESTAMP = None

        ollama_client = OllamaClient()
        available = ollama_client.is_available(timeout=timeout)
        if not available:
            _LAST_UNAVAILABLE_TIMESTAMP = now
        else:
            _LAST_UNAVAILABLE_TIMESTAMP = None
        return available

    return False


def warmup_ollama_async(client: Optional[Any] = None) -> Optional[threading.Thread]:
    """Non-blocking background probe for Ollama; no warmup thread for hosted backends."""
    cfg = get_llm_config()
    if cfg.backend == "openai_compatible":
        return None

    def _probe() -> None:
        try:
            check_llm_availability(client=client, timeout=1.5)
        except Exception:
            pass

    t = threading.Thread(target=_probe, name="ollama-warmup", daemon=True)
    t.start()
    return t


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
# ONE CALL PER QUESTION: COMBINED MISSING FIELDS EXTRACTION
# ==============================================================================


def build_missing_fields_schema(missing_fields: list[str]) -> dict[str, Any]:
    """Build a JSON Schema containing ONLY the fields rules left missing or ambiguous."""
    properties: dict[str, Any] = {}
    required: list[str] = []

    if "region" in missing_fields or "region_name" in missing_fields:
        properties["region_name"] = {
            "type": ["string", "null"],
            "description": "Exact ocean region, sea, or body of water name. Return null if none mentioned.",
        }
        required.append("region_name")

    if "date_range" in missing_fields:
        properties["date_range"] = {
            "type": ["object", "null"],
            "description": "Calendar date range in ISO YYYY-MM-DD. Single years span YYYY-01-01 to YYYY-12-31. If relative or ambiguous, return null.",
            "properties": {
                "start": {"type": ["string", "null"]},
                "end": {"type": ["string", "null"]},
            },
            "required": ["start", "end"],
        }
        required.append("date_range")

    if "variables" in missing_fields:
        properties["variables"] = {
            "type": ["array", "null"],
            "description": "Argo physical ocean variables: TEMP (temperature), PSAL (salinity), PRES (pressure).",
            "items": {"type": "string", "enum": ["TEMP", "PSAL", "PRES"]},
        }
        required.append("variables")

    if "depth_range" in missing_fields:
        properties["depth_range"] = {
            "type": ["object", "null"],
            "description": "Depth range in dbar (0 to 2000). Return null if unspecified.",
            "properties": {
                "min_depth": {"type": ["number", "null"]},
                "max_depth": {"type": ["number", "null"]},
            },
            "required": ["min_depth", "max_depth"],
        }
        required.append("depth_range")

    if "intent" in missing_fields:
        properties["intent"] = {
            "type": ["string", "null"],
            "description": "Standard Argo visualization intent.",
            "enum": ["profile", "map", "ts", "trend", None],
        }
        required.append("intent")

    return {
        "type": "object",
        "properties": properties,
        "required": required,
    }


def build_missing_fields_system_prompt(missing_fields: list[str]) -> str:
    """Generate minimal fixed system instructions covering only missing fields."""
    lines = [
        "You are an assistant for oceanographic Argo queries. "
        "Extract ONLY the requested fields from the user question into JSON. "
        "Always output strictly valid JSON conforming to the schema.",
        "Rules:",
    ]
    if "region" in missing_fields or "region_name" in missing_fields:
        lines.append("- region_name: Return the geographic body of water name, or null if none is mentioned.")
    if "date_range" in missing_fields:
        lines.append("- date_range: Explicit calendar dates in ISO YYYY-MM-DD (e.g. 2022 -> 2022-01-01 to 2022-12-31). If relative, vague, or missing a year (e.g. 'March', 'recent'), return null.")
    if "variables" in missing_fields:
        lines.append("- variables: Requested Argo variables: 'TEMP' (temperature, warm), 'PSAL' (salinity, salt), 'PRES' (pressure). Do not map depth to PRES.")
    if "depth_range" in missing_fields:
        lines.append("- depth_range: Depth span in meters/dbar (0-2000). If unspecified, return null.")
    if "intent" in missing_fields:
        lines.append("- intent: One of 'profile' (depth profiles), 'map' (locations/trajectories), 'ts' (temperature vs salinity), 'trend' (time series).")
    lines.append("Do not include explanations or markdown fences. Output JSON only.")
    return "\n".join(lines)


def _clean_json_content(content: str) -> str:
    """Strip markdown code fences and extraneous whitespace from LLM output."""
    c = content.strip()
    if c.startswith("```"):
        lines = c.splitlines()
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        c = "\n".join(lines).strip()
    return c


def extract_missing_fields_llm(
    question: str,
    missing_fields: list[str],
    client: Optional[Any] = None,
    config: Optional[LLMConfig] = None,
) -> Optional[dict[str, Any]]:
    """Single call per question to extract only fields rules left missing or ambiguous.

    Payload contains ONLY the question text and fixed instructions (never data, stats, or cards).
    Enforces MAX_QUESTION_LENGTH cap. Retries invalid JSON once before returning None.
    """
    if not missing_fields:
        return {}

    # Question length capped at MAX_QUESTION_LENGTH
    if len(question) > MAX_QUESTION_LENGTH:
        logger.warning("Question length (%d) exceeds cap (%d); skipping LLM call.", len(question), MAX_QUESTION_LENGTH)
        return None

    cfg = config or get_llm_config()
    schema = build_missing_fields_schema(missing_fields)
    system_prompt = build_missing_fields_system_prompt(missing_fields)

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": question},
    ]

    active_client = client
    if active_client is None:
        if cfg.backend == "openai_compatible" and cfg.base_url and cfg.model and cfg.api_key:
            active_client = OpenAICompatibleClient(
                base_url=cfg.base_url,
                model=cfg.model,
                api_key=cfg.api_key,
                json_mode=cfg.json_mode,
                daily_cap=cfg.daily_cap,
            )
        else:
            return None

    # Call attempt 1
    content_str: Optional[str] = None
    try:
        if hasattr(active_client, "chat"):
            # Check parameter signature of client.chat
            try:
                res = active_client.chat(messages=messages, schema=schema)
                content_str = _extract_content(res)
            except TypeError:
                res = active_client.chat(
                    model=cfg.model or DEFAULT_MODEL,
                    messages=messages,
                    format=schema,
                    options={"temperature": 0.0},
                )
                content_str = _extract_content(res)
    except Exception as e:
        logger.warning("LLM call for missing fields failed: %s", e)
        return None

    if not content_str:
        return None

    cleaned = _clean_json_content(content_str)
    try:
        parsed = json.loads(cleaned)
        if isinstance(parsed, dict):
            return parsed
    except Exception:
        pass

    # Invalid output: retry once
    logger.info("LLM returned invalid JSON; retrying once.")
    retry_messages = list(messages)
    retry_messages.append({"role": "assistant", "content": content_str})
    retry_messages.append({
        "role": "user",
        "content": "Your previous output was not valid JSON conforming to the schema. Output strictly valid JSON matching the schema.",
    })

    try:
        if hasattr(active_client, "chat"):
            try:
                res2 = active_client.chat(messages=retry_messages, schema=schema)
                content_str2 = _extract_content(res2)
            except TypeError:
                res2 = active_client.chat(
                    model=cfg.model or DEFAULT_MODEL,
                    messages=retry_messages,
                    format=schema,
                    options={"temperature": 0.0},
                )
                content_str2 = _extract_content(res2)
        else:
            return None
    except Exception as e:
        logger.warning("LLM retry for missing fields failed: %s", e)
        return None

    if not content_str2:
        return None

    cleaned2 = _clean_json_content(content_str2)
    try:
        parsed2 = json.loads(cleaned2)
        if isinstance(parsed2, dict):
            return parsed2
    except Exception as e:
        logger.warning("LLM retry also returned invalid JSON: %s", e)
        return None

    return None


# ==============================================================================
# LEGACY FIELD SCHEMAS & EXTRACTORS (PRESERVED FOR OLLAMA BACKWARD COMPATIBILITY)
# ==============================================================================

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


def _call_ollama(
    base_messages: list[dict[str, str]],
    user_prompt: str,
    schema: dict[str, Any],
    client: Optional[Any] = None,
    model: str = DEFAULT_MODEL,
) -> Optional[dict[str, Any]]:
    """Execute a single-field Ollama call with JSON schema enforcement and temp 0."""
    if len(user_prompt) > MAX_QUESTION_LENGTH:
        return None

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
        logger.warning("Ollama call for schema extraction failed: %s", e)
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
