"""Unit tests for siqva.parser module (hybrid rules + LLM fallback + validation)."""

from datetime import date
from unittest.mock import MagicMock
import pytest

from siqva.parser import ClarificationNeeded, ParseOutcome, parse, parse_detailed
from siqva.spec import DataMode, DepthRange, Intent, QuerySpec, Variable


class FakeChatResponse:
    def __init__(self, content: str):
        self.message = MagicMock()
        self.message.content = content


class FakeLLMClient:
    def __init__(self, responses: dict[str, str]):
        self.responses = responses

    def chat(self, model: str, messages: list[dict], format: dict, options: dict):
        props = format.get("properties", {})
        for k, v in self.responses.items():
            if k in props:
                return FakeChatResponse(v)
        return FakeChatResponse("{}")


def test_parse_rules_complete_query():
    """Proves a complete natural language query is resolved purely by deterministic rules."""
    q = "temperature and salinity profiles in Arabian Sea between 2022-01-01 and 2022-01-10"
    res = parse(q, allow_llm=False)

    assert isinstance(res, QuerySpec)
    assert set(res.variables) == {Variable.TEMP, Variable.PSAL}
    assert res.date_range.start == date(2022, 1, 1)
    assert res.date_range.end == date(2022, 1, 10)
    assert res.depth_range == DepthRange(min_depth=0.0, max_depth=500.0)
    assert res.mode == DataMode.RESEARCH
    assert res.intent == Intent.PROFILE


def test_parse_detailed_provenance_tracking():
    """Proves provenance accurately marks fields as rules, llm, or default."""
    q = "temperature profiles in Arabian Sea in January 2022"
    outcome = parse_detailed(q, allow_llm=False)

    assert outcome.is_success is True
    assert outcome.spec is not None
    assert outcome.provenance["region"] == "rules"
    assert outcome.provenance["date_range"] == "rules"
    assert outcome.provenance["variables"] == "rules"
    assert outcome.provenance["depth_range"] == "default"
    assert outcome.provenance["mode"] == "default"
    assert outcome.provenance["intent"] == "rules"


def test_parse_ambiguous_date_asks_clarification():
    """Proves 'March' without year returns ClarificationNeeded and never guesses."""
    q = "salinity profiles in North Atlantic in March"
    res = parse(q, allow_llm=False)

    assert isinstance(res, ClarificationNeeded)
    assert "date_range" in res.ambiguous_fields
    assert "missing a year" in res.message.lower()


def test_parse_ambiguous_sst_asks_clarification():
    """Proves 'sst' returns ClarificationNeeded distinguishing surface from Argo subsurface."""
    q = "sst in Arabian Sea in January 2022"
    res = parse(q, allow_llm=False)

    assert isinstance(res, ClarificationNeeded)
    assert "variables" in res.ambiguous_fields
    assert "differs from argo subsurface" in res.message.lower()


def test_parse_missing_region_asks_clarification():
    """Proves query without region returns ClarificationNeeded."""
    q = "temperature profiles between 2022-01-01 and 2022-01-10"
    res = parse(q, allow_llm=False)

    assert isinstance(res, ClarificationNeeded)
    assert "region" in res.missing_fields


def test_parse_oversized_query_returns_suggestion():
    """Proves oversized query returns ClarificationNeeded with narrowing advice."""
    q = "temperature profiles in North Atlantic between 2010-01-01 and 2020-01-01"
    res = parse(q, allow_llm=False)

    assert isinstance(res, ClarificationNeeded)
    assert "exceeds allowable size cap" in res.message.lower()
    assert len(res.suggestions) > 0


def test_parse_llm_fallback_for_unfilled_intent():
    """Proves LLM client is used only for unfilled fields (e.g. intent tie-breaker)."""
    # Intent ambiguous in rules: "look at temperature in Arabian Sea in January 2022"
    client = FakeLLMClient({"intent": '{"intent": "trend"}'})
    outcome = parse_detailed(
        "look at temperature in Arabian Sea in January 2022",
        llm_client=client,
        allow_llm=True,
    )

    assert outcome.is_success is True
    assert outcome.spec is not None
    assert outcome.spec.intent == Intent.TREND
    assert outcome.provenance["intent"] == "llm"
    assert outcome.provenance["region"] == "rules"
    assert outcome.provenance["variables"] == "rules"


def test_parse_retry_recovers_inverted_dates():
    """Proves retry logic can recover when LLM produces inverted dates."""
    # When rules parser cannot parse phrased dates and LLM extracts inverted dates
    client = FakeLLMClient({"start": '{"start": "2022-01-10", "end": "2022-01-01"}'})
    outcome = parse_detailed(
        "temperature in Arabian Sea during period-A",
        llm_client=client,
        allow_llm=True,
    )

    assert outcome.is_success is True
    assert outcome.spec is not None
    assert outcome.spec.date_range.start == date(2022, 1, 1)
    assert outcome.spec.date_range.end == date(2022, 1, 10)
    assert "swapped" in outcome.provenance["date_range"]

import time
from siqva.llm_parser import reset_availability_cache


class UnreachableMockClient:
    def __init__(self, check_delay: float = 0.0):
        self.check_count = 0
        self.chat_count = 0
        self.check_delay = check_delay

    def is_available(self, timeout: float = 1.5) -> bool:
        self.check_count += 1
        if self.check_delay > 0:
            time.sleep(self.check_delay)
        return False

    def chat(self, *args, **kwargs):
        self.chat_count += 1
        raise RuntimeError("Chat must not be called when unavailable")


class ReachableMockClient:
    def __init__(self):
        self.check_count = 0

    def is_available(self, timeout: float = 1.5) -> bool:
        self.check_count += 1
        return True

    def chat(self, model: str, messages: list[dict], format: dict, options: dict):
        props = format.get("properties", {})
        if "region_name" in props:
            return FakeChatResponse('{"region_name": "Arabian Sea"}')
        if "intent" in props:
            return FakeChatResponse('{"intent": "trend"}')
        return FakeChatResponse("{}")


def test_ollama_unreachable_at_most_one_check_and_clean_clarification():
    """Proves unreachable Ollama makes at most one check, skips all fallbacks, and returns plain clarification."""
    reset_availability_cache()
    mock = UnreachableMockClient(check_delay=0.01)

    # Query has missing region and missing date_range; only variables='salinity' resolved by rules
    t0 = time.monotonic()
    outcome = parse_detailed("salinity", llm_client=mock, allow_llm=True)
    duration = time.monotonic() - t0

    assert outcome.is_success is False
    assert outcome.clarification is not None
    # At most one availability check performed
    assert mock.check_count == 1
    # Chat was never invoked
    assert mock.chat_count == 0
    # Fast completion well under 3 seconds
    assert duration < 3.0

    # Rules resolved field stays resolved
    assert outcome.provenance.get("variables") == "rules"

    # Clarification message plainly states LLM unavailable and lists missing fields
    msg = outcome.clarification.message
    assert "The language model is not available" in msg
    assert "region" in outcome.clarification.missing_fields
    assert "date_range" in outcome.clarification.missing_fields
    assert "spec panel" in msg.lower()


def test_ollama_unreachable_caches_unavailable_for_repeated_queries():
    """Proves repeated queries within 30s reuse cached unavailable status without waiting."""
    reset_availability_cache()
    mock = UnreachableMockClient(check_delay=0.01)

    # First query triggers check
    parse_detailed("salinity", llm_client=mock, allow_llm=True)
    assert mock.check_count == 1

    # Second query reuses 30s cache without re-checking
    parse_detailed("temperature", llm_client=mock, allow_llm=True)
    assert mock.check_count == 1  # Still 1


def test_ollama_reachable_behaves_as_before():
    """Proves reachable Ollama client extracts unfilled fields via fallback as expected."""
    reset_availability_cache()
    client = ReachableMockClient()

    outcome = parse_detailed("temperature between 2022-01-01 and 2022-01-10", llm_client=client, allow_llm=True)
    assert outcome.is_success is True
    assert outcome.spec is not None
    assert outcome.spec.region.lon_min == 50.0  # Arabian Sea resolved
    assert outcome.provenance.get("region") == "llm"
    assert outcome.provenance.get("variables") == "rules"
    assert outcome.provenance.get("date_range") == "rules"
