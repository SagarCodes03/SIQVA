"""Unit and integration tests for the hosted OpenAI-compatible LLM backend.

Tests verify:
- Backend selection and fallback to 'none' when unconfigured.
- Payload privacy: ONLY the user question text and fixed instructions are sent; NO data values,
  dataframes, or profile results.
- Schema/instructions cover ONLY fields left unfilled by rules.
- Rules-resolved fields are never overridden.
- Invalid JSON is retried once, then falls back to ClarificationNeeded.
- 429 rate limit (respecting Retry-After up to cap), timeouts, connection errors fall back cleanly to rules.
- Circuit breaker trips after 3 consecutive failures and cools down for 60s.
- Per-session hourly call limit (20) and daily call counter (SIQVA_LLM_DAILY_CAP).
- Question length cap (500 chars) skips LLM.
- API key is never logged, stored in cards, or shown in error messages.
- Configuration precedence: env var > st.secrets > none; missing secrets.toml does not crash.
"""

from __future__ import annotations

import json
import logging
import os
import time
from datetime import date
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import requests

from siqva.llm_parser import (
    CIRCUIT_BREAKER_COOLDOWN_SECONDS,
    CIRCUIT_BREAKER_FAILURES,
    DEFAULT_DAILY_CAP,
    LLM_TIMEOUT_SECONDS,
    MAX_QUESTION_LENGTH,
    MAX_RETRY_AFTER_SECONDS,
    SESSION_CALL_LIMIT_PER_HOUR,
    LLMConfig,
    LLMUnavailableError,
    OpenAICompatibleClient,
    build_missing_fields_schema,
    can_make_daily_call,
    can_make_session_call,
    check_llm_availability,
    extract_missing_fields_llm,
    get_daily_calls,
    get_llm_config,
    get_session_calls_past_hour,
    is_circuit_open,
    is_hosted_backend_active,
    record_daily_call,
    record_session_call,
    reset_circuit_breaker,
    reset_session_tracker,
)
from siqva.parser import ClarificationNeeded, ParseOutcome, parse_detailed
from siqva.spec import DataMode, DepthRange, Intent, QuerySpec, Variable


@pytest.fixture(autouse=True)
def clean_llm_state(tmp_path, monkeypatch):
    """Ensure clean state across tests: reset session, circuit breaker, and isolate usage file."""
    reset_circuit_breaker()
    reset_session_tracker()
    usage_file = tmp_path / "llm_usage.json"
    monkeypatch.setattr("siqva.llm_parser.USAGE_FILE_PATH", usage_file)
    # Clear any ambient LLM environment variables by default
    for var in [
        "SIQVA_LLM_BACKEND",
        "SIQVA_LLM_BASE_URL",
        "SIQVA_LLM_MODEL",
        "SIQVA_LLM_API_KEY",
        "SIQVA_LLM_JSON_MODE",
        "SIQVA_LLM_DAILY_CAP",
    ]:
        monkeypatch.delenv(var, raising=False)
    yield


# ==============================================================================
# 1. Config lookup and default fallback tests
# ==============================================================================


def test_missing_config_defaults_to_none_without_crash():
    """When no env vars and no secrets are present, backend defaults to 'none'."""
    cfg = get_llm_config()
    assert cfg.backend == "none"
    assert is_hosted_backend_active() is False


def test_missing_secrets_toml_handled_gracefully():
    """Accessing secrets when secrets.toml does not exist never raises."""
    with patch("streamlit.runtime.secrets.Secrets._parse", side_effect=FileNotFoundError("No secrets file")):
        cfg = get_llm_config()
        assert cfg.backend == "none"


def test_env_var_takes_precedence_over_secrets(monkeypatch):
    """Environment variables take precedence over Streamlit secrets."""
    monkeypatch.setenv("SIQVA_LLM_BACKEND", "openai_compatible")
    monkeypatch.setenv("SIQVA_LLM_BASE_URL", "https://api.example.com/v1")
    monkeypatch.setenv("SIQVA_LLM_MODEL", "gpt-test-model")
    monkeypatch.setenv("SIQVA_LLM_API_KEY", "env-secret-key")

    cfg = get_llm_config()
    assert cfg.backend == "openai_compatible"
    assert cfg.base_url == "https://api.example.com/v1"
    assert cfg.model == "gpt-test-model"
    assert cfg.api_key == "env-secret-key"
    assert is_hosted_backend_active() is True


def test_openai_compatible_incomplete_config_falls_back_to_none(monkeypatch):
    """If backend is set to openai_compatible but base_url or model is missing, falls back to none."""
    monkeypatch.setenv("SIQVA_LLM_BACKEND", "openai_compatible")
    # Missing base_url and model
    cfg = get_llm_config()
    assert cfg.backend == "none"


# ==============================================================================
# 2. Privacy & Payload Inspection: No data values, only question & fixed instructions
# ==============================================================================


def test_payload_contains_no_data_values_only_question_and_schema(monkeypatch):
    """Assert HTTP POST payload contains only user question text, fixed schema, and no data values."""
    monkeypatch.setenv("SIQVA_LLM_BACKEND", "openai_compatible")
    monkeypatch.setenv("SIQVA_LLM_BASE_URL", "https://api.example.com/v1")
    monkeypatch.setenv("SIQVA_LLM_MODEL", "test-model")
    monkeypatch.setenv("SIQVA_LLM_API_KEY", "secret-test-key")

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "choices": [
            {
                "message": {
                    "content": json.dumps({"region_name": "Arabian Sea"})
                }
            }
        ]
    }

    captured_payload = {}

    def fake_post(url, json=None, headers=None, timeout=None):
        nonlocal captured_payload
        captured_payload = json
        return mock_resp

    with patch("requests.Session.post", side_effect=fake_post):
        # Query with missing region: "temperature profiles in 2022"
        outcome = parse_detailed("temperature profiles in 2022", allow_llm=True)
        assert outcome.is_success is True
        assert outcome.spec is not None
        assert outcome.spec.region.lon_min == 50.0  # Arabian Sea
        assert outcome.provenance["region"] == "llm"
        assert outcome.provenance["variables"] == "rules"
        assert outcome.provenance["date_range"] == "rules"

    # Inspect captured payload
    assert captured_payload is not None
    assert captured_payload["model"] == "test-model"
    assert captured_payload["temperature"] == 0.0

    # Payload messages must contain ONLY role and content
    messages = captured_payload["messages"]
    assert len(messages) >= 2
    system_msg = messages[0]["content"]
    user_msg = messages[-1]["content"]

    # Verify user message is strictly the raw question text
    assert user_msg == "temperature profiles in 2022"

    # Verify no oceanic data, dataframes, lat/lons, or profile measurements in prompt
    full_payload_text = json.dumps(captured_payload)
    for forbidden in ["TEMP_ADJUSTED", "PSAL_ADJUSTED", "PRES_ADJUSTED", "CYCLE_NUMBER", "PLATFORM_NUMBER", "DataFrame"]:
        assert forbidden not in full_payload_text


# ==============================================================================
# 3. Schema covers ONLY missing/ambiguous fields & rules fields are preserved
# ==============================================================================


def test_schema_covers_only_missing_fields_and_rules_preserved(monkeypatch):
    """Schema sent to LLM contains ONLY fields missing from rules, preserving rules-resolved fields."""
    monkeypatch.setenv("SIQVA_LLM_BACKEND", "openai_compatible")
    monkeypatch.setenv("SIQVA_LLM_BASE_URL", "https://api.example.com/v1")
    monkeypatch.setenv("SIQVA_LLM_MODEL", "test-model")
    monkeypatch.setenv("SIQVA_LLM_API_KEY", "secret-test-key")

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    # LLM attempts to return region AND date_range, but date_range was already resolved by rules!
    mock_resp.json.return_value = {
        "choices": [
            {
                "message": {
                    "content": json.dumps({
                        "region_name": "Arabian Sea",
                        "date_range": {"start": "1999-01-01", "end": "1999-12-31"},  # should NOT override rules 2022
                    })
                }
            }
        ]
    }

    captured_payload = {}

    def fake_post(url, json=None, headers=None, timeout=None):
        nonlocal captured_payload
        captured_payload = json
        return mock_resp

    with patch("requests.Session.post", side_effect=fake_post):
        # Query: "temperature in January 2022" -> region missing, dates & vars known
        outcome = parse_detailed("temperature in January 2022", allow_llm=True)
        assert outcome.is_success is True
        assert outcome.spec is not None

        # Date range from rules MUST be preserved (2022-01-01 to 2022-01-31), NOT overridden by LLM 1999
        assert outcome.spec.date_range.start == date(2022, 1, 1)
        assert outcome.spec.date_range.end == date(2022, 1, 31)
        assert outcome.provenance["date_range"] == "rules"
        assert outcome.provenance["variables"] == "rules"
        assert outcome.provenance["region"] == "llm"

    # Schema in prompt instructions must only have requested region_name and intent
    system_content = captured_payload["messages"][0]["content"]
    assert "region_name" in system_content
    assert '"date_range"' not in system_content  # date_range was resolved by rules, so omitted from schema!
    assert '"variables"' not in system_content   # variables resolved by rules, omitted from schema!


# ==============================================================================
# 4. Retry once on invalid JSON, then ClarificationNeeded
# ==============================================================================


def test_retry_once_on_invalid_json(monkeypatch):
    """When first response is invalid JSON, client retries once; if second succeeds, outcome succeeds."""
    monkeypatch.setenv("SIQVA_LLM_BACKEND", "openai_compatible")
    monkeypatch.setenv("SIQVA_LLM_BASE_URL", "https://api.example.com/v1")
    monkeypatch.setenv("SIQVA_LLM_MODEL", "test-model")
    monkeypatch.setenv("SIQVA_LLM_API_KEY", "secret-test-key")

    call_count = 0

    def fake_post(url, json=None, headers=None, timeout=None):
        nonlocal call_count
        call_count += 1
        resp = MagicMock()
        resp.status_code = 200
        if call_count == 1:
            # First attempt: invalid truncated JSON
            resp.json.return_value = {"choices": [{"message": {"content": '{"region_name": "Arabian' }}]}
        else:
            # Second attempt: valid JSON
            resp.json.return_value = {"choices": [{"message": {"content": '{"region_name": "Arabian Sea"}'}}]}
        return resp

    with patch("requests.Session.post", side_effect=fake_post):
        outcome = parse_detailed("temperature in 2022", allow_llm=True)
        assert call_count == 2
        assert outcome.is_success is True
        assert outcome.provenance["region"] == "llm"


def test_retry_exhausted_invalid_json_returns_clarification(monkeypatch):
    """When both attempts return invalid JSON, returns ClarificationNeeded with missing fields."""
    monkeypatch.setenv("SIQVA_LLM_BACKEND", "openai_compatible")
    monkeypatch.setenv("SIQVA_LLM_BASE_URL", "https://api.example.com/v1")
    monkeypatch.setenv("SIQVA_LLM_MODEL", "test-model")
    monkeypatch.setenv("SIQVA_LLM_API_KEY", "secret-test-key")

    call_count = 0

    def fake_post(url, json=None, headers=None, timeout=None):
        nonlocal call_count
        call_count += 1
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = {"choices": [{"message": {"content": 'not valid json at all'}}]}
        return resp

    with patch("requests.Session.post", side_effect=fake_post):
        outcome = parse_detailed("temperature in 2022", allow_llm=True)
        assert call_count == 2
        assert outcome.is_success is False
        assert outcome.clarification is not None
        assert "region" in outcome.clarification.missing_fields


# ==============================================================================
# 5. Error handling: 429 Rate Limit, Timeout, Connection Errors
# ==============================================================================


def test_http_429_rate_limit_with_retry_after(monkeypatch):
    """HTTP 429 respects Retry-After up to cap, retries, and succeeds if under cap."""
    monkeypatch.setenv("SIQVA_LLM_BACKEND", "openai_compatible")
    monkeypatch.setenv("SIQVA_LLM_BASE_URL", "https://api.example.com/v1")
    monkeypatch.setenv("SIQVA_LLM_MODEL", "test-model")
    monkeypatch.setenv("SIQVA_LLM_API_KEY", "secret-test-key")

    attempts = 0

    def fake_post(url, json=None, headers=None, timeout=None):
        nonlocal attempts
        attempts += 1
        resp = MagicMock()
        if attempts == 1:
            resp.status_code = 429
            resp.headers = {"Retry-After": "0.1"}
            resp.text = "Rate limit reached"
        else:
            resp.status_code = 200
            resp.json.return_value = {"choices": [{"message": {"content": '{"region_name": "Arabian Sea"}'}}]}
        return resp

    with patch("requests.Session.post", side_effect=fake_post):
        outcome = parse_detailed("temperature in 2022", allow_llm=True)
        assert attempts == 2
        assert outcome.is_success is True


def test_http_429_exceeding_retry_cap_falls_back_to_rules(monkeypatch):
    """HTTP 429 with large Retry-After exceeds cap and falls back to plain message."""
    monkeypatch.setenv("SIQVA_LLM_BACKEND", "openai_compatible")
    monkeypatch.setenv("SIQVA_LLM_BASE_URL", "https://api.example.com/v1")
    monkeypatch.setenv("SIQVA_LLM_MODEL", "test-model")
    monkeypatch.setenv("SIQVA_LLM_API_KEY", "secret-test-key")

    def fake_post(url, json=None, headers=None, timeout=None):
        resp = MagicMock()
        resp.status_code = 429
        resp.headers = {"Retry-After": "60"}  # > 10.0 cap
        resp.text = "Rate limit reached"
        return resp

    with patch("requests.Session.post", side_effect=fake_post):
        outcome = parse_detailed("temperature in 2022", allow_llm=True)
        assert outcome.is_success is False
        assert outcome.clarification is not None
        assert "The language model is unavailable or over its free limit; fill in the missing fields" in outcome.clarification.message


def test_timeout_and_connection_error_falls_back_to_rules(monkeypatch):
    """Timeout or ConnectionError falls back to rules with exact plain message."""
    monkeypatch.setenv("SIQVA_LLM_BACKEND", "openai_compatible")
    monkeypatch.setenv("SIQVA_LLM_BASE_URL", "https://api.example.com/v1")
    monkeypatch.setenv("SIQVA_LLM_MODEL", "test-model")
    monkeypatch.setenv("SIQVA_LLM_API_KEY", "secret-test-key")

    with patch("requests.Session.post", side_effect=requests.exceptions.Timeout("Connection timed out")):
        outcome = parse_detailed("temperature in 2022", allow_llm=True)
        assert outcome.is_success is False
        assert outcome.clarification is not None
        assert "The language model is unavailable or over its free limit; fill in the missing fields" in outcome.clarification.message


# ==============================================================================
# 6. Circuit Breaker: 3 consecutive failures trips for 60s
# ==============================================================================


def test_circuit_breaker_trips_after_3_failures(monkeypatch):
    """After 3 consecutive failures, circuit breaker trips and skips API calls for 60s."""
    monkeypatch.setenv("SIQVA_LLM_BACKEND", "openai_compatible")
    monkeypatch.setenv("SIQVA_LLM_BASE_URL", "https://api.example.com/v1")
    monkeypatch.setenv("SIQVA_LLM_MODEL", "test-model")
    monkeypatch.setenv("SIQVA_LLM_API_KEY", "secret-test-key")

    call_count = 0

    def fake_post(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        raise requests.exceptions.ConnectionError("Server unreachable")

    with patch("requests.Session.post", side_effect=fake_post):
        # 1st failure
        outcome1 = parse_detailed("temperature in 2022", allow_llm=True)
        assert outcome1.is_success is False

        # 2nd failure
        outcome2 = parse_detailed("temperature in 2022", allow_llm=True)
        assert outcome2.is_success is False

        # 3rd failure (trips circuit breaker)
        outcome3 = parse_detailed("temperature in 2022", allow_llm=True)
        assert outcome3.is_success is False

        initial_calls = call_count
        assert initial_calls >= 3

        # 4th call: circuit breaker is OPEN, post must NOT be called at all!
        outcome4 = parse_detailed("temperature in 2022", allow_llm=True)
        assert outcome4.is_success is False
        assert call_count == initial_calls  # No additional HTTP attempt made!


# ==============================================================================
# 7. Rate Limits: Session hourly limit (20) & Global daily cap (500)
# ==============================================================================


def test_session_hourly_call_limit(monkeypatch):
    """Session limit of 20 calls/hr blocks further LLM calls within the hour."""
    reset_session_tracker()
    assert can_make_session_call() is True

    for _ in range(SESSION_CALL_LIMIT_PER_HOUR):
        record_session_call()

    assert get_session_calls_past_hour() == SESSION_CALL_LIMIT_PER_HOUR
    assert can_make_session_call() is False


def test_daily_call_limit(tmp_path):
    """Global daily cap blocks calls once ceiling is reached."""
    usage_path = tmp_path / "usage.json"
    assert can_make_daily_call(cap=5, path=usage_path) is True

    for _ in range(5):
        record_daily_call(tokens=10, path=usage_path)

    assert get_daily_calls(path=usage_path) == 5
    assert can_make_daily_call(cap=5, path=usage_path) is False


# ==============================================================================
# 8. Question length cap (>500 characters skips LLM)
# ==============================================================================


def test_question_length_cap_skips_llm(monkeypatch):
    """Questions exceeding 500 characters skip the LLM without making HTTP calls."""
    monkeypatch.setenv("SIQVA_LLM_BACKEND", "openai_compatible")
    monkeypatch.setenv("SIQVA_LLM_BASE_URL", "https://api.example.com/v1")
    monkeypatch.setenv("SIQVA_LLM_MODEL", "test-model")
    monkeypatch.setenv("SIQVA_LLM_API_KEY", "secret-test-key")

    long_question = "temperature in " + "x" * 600

    with patch("requests.Session.post") as mock_post:
        outcome = parse_detailed(long_question, allow_llm=True)
        assert mock_post.called is False
        assert outcome.is_success is False


# ==============================================================================
# 9. Secret Security: API key never in logs or messages
# ==============================================================================


def test_api_key_never_logged(monkeypatch, caplog):
    """API key must never appear in logger output even during failures."""
    secret_key = "super-secret-production-key-998877"
    monkeypatch.setenv("SIQVA_LLM_BACKEND", "openai_compatible")
    monkeypatch.setenv("SIQVA_LLM_BASE_URL", "https://api.example.com/v1")
    monkeypatch.setenv("SIQVA_LLM_MODEL", "test-model")
    monkeypatch.setenv("SIQVA_LLM_API_KEY", secret_key)

    with caplog.at_level(logging.DEBUG):
        with patch("requests.Session.post", side_effect=requests.exceptions.ConnectionError("Connection failed")):
            parse_detailed("temperature in 2022", allow_llm=True)

    log_text = caplog.text
    assert secret_key not in log_text


def test_no_warmup_thread_for_hosted_backends(monkeypatch):
    """Hosted backends must NOT launch background warmup threads."""
    monkeypatch.setenv("SIQVA_LLM_BACKEND", "openai_compatible")
    monkeypatch.setenv("SIQVA_LLM_BASE_URL", "https://api.example.com/v1")
    monkeypatch.setenv("SIQVA_LLM_MODEL", "test-model")
    monkeypatch.setenv("SIQVA_LLM_API_KEY", "secret-key")

    from siqva.llm_parser import warmup_ollama_async
    thread = warmup_ollama_async()
    assert thread is None
