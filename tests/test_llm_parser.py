"""Unit tests for siqva.llm_parser module using mock/fake clients."""

import os
from datetime import date
from unittest.mock import MagicMock
import pytest

from siqva.llm_parser import (
    DEFAULT_MODEL,
    INTENT_SCHEMA,
    VARIABLES_SCHEMA,
    LLMUnavailableError,
    OllamaClient,
    extract_date_range_llm,
    extract_depth_range_llm,
    extract_intent_llm,
    extract_region_name_llm,
    extract_variables_llm,
)
from siqva.spec import DepthRange, Intent, Variable


class FakeChatResponse:
    def __init__(self, content: str):
        self.message = MagicMock()
        self.message.content = content


class FakeLLMClient:
    """Mock client that responds deterministically based on schema."""

    def __init__(self, responses: dict[str, str]):
        self.responses = responses
        self.call_history: list[dict] = []

    def chat(self, model: str, messages: list[dict], format: dict, options: dict):
        self.call_history.append(
            {"model": model, "messages": messages, "format": format, "options": options}
        )
        schema_type = format.get("properties", {})
        for key, response_json in self.responses.items():
            if key in schema_type:
                return FakeChatResponse(response_json)
        return FakeChatResponse("{}")


def test_extract_intent_llm_mock():
    client = FakeLLMClient({"intent": '{"intent": "ts"}'})
    intent = extract_intent_llm("plot salinity against temperature", client=client)
    assert intent == Intent.TS
    assert len(client.call_history) == 1
    assert client.call_history[0]["options"]["temperature"] == 0.0


def test_extract_variables_llm_mock():
    client = FakeLLMClient({"variables": '{"variables": ["TEMP", "PSAL"]}'})
    vars_list = extract_variables_llm("measure heat and salt content", client=client)
    assert vars_list == [Variable.TEMP, Variable.PSAL]


def test_extract_region_name_llm_mock():
    client = FakeLLMClient({"region_name": '{"region_name": "Tasman Sea"}'})
    region_name = extract_region_name_llm("profiles in Tasman Sea", client=client)
    assert region_name == "Tasman Sea"


def test_extract_date_range_llm_mock():
    client = FakeLLMClient({"start": '{"start": "2021-06-01", "end": "2021-08-31"}'})
    dates = extract_date_range_llm("summer 2021", client=client)
    assert dates == (date(2021, 6, 1), date(2021, 8, 31))


def test_extract_depth_range_llm_mock():
    client = FakeLLMClient({"min_depth": '{"min_depth": 0.0, "max_depth": 300.0}'})
    depth = extract_depth_range_llm("top 300 m", client=client)
    assert depth == DepthRange(min_depth=0.0, max_depth=300.0)


def test_llm_unavailable_handled_gracefully():
    broken_client = MagicMock()
    broken_client.chat.side_effect = RuntimeError("Connection refused")

    # Should not raise exception to caller, but return None
    assert extract_intent_llm("test question", client=broken_client) is None
    assert extract_variables_llm("test question", client=broken_client) is None
    assert extract_region_name_llm("test question", client=broken_client) is None


@pytest.mark.skipif(
    not os.getenv("RUN_OLLAMA_TESTS"),
    reason="Requires live Ollama server; run with RUN_OLLAMA_TESTS=1",
)
def test_live_ollama_intent_extraction():
    """Live integration check with local Ollama server."""
    intent = extract_intent_llm("plot temperature map in North Atlantic")
    assert intent in (Intent.MAP, Intent.PROFILE)

