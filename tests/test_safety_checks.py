"""Safety and verification tests for FIX 4.

Verifies:
1. Unquantified relative date phrases ("last month", "recent") produce clarification and are never guessed.
2. Ollama-unavailable path completes in under 3 seconds with mocked client and names missing fields.
3. Oversized/chunk message for basin-sized default-depth (Indian Ocean, 0-500 dbar, 1 month) is actionable with suggestions, not a stack trace.
"""

from datetime import date
import time
import pytest

from siqva.gazetteer import KNOWN_REGIONS
from siqva.llm_parser import reset_availability_cache
from siqva.parser import parse_detailed
from siqva.pipeline import PipelineStatus, run
from siqva.spec import DataMode, DateRange, Intent, QuerySpec, Variable
from siqva.validator import OversizedRequestError, validate_spec


class QuickUnreachableMockClient:
    """Mock LLM client simulating unreachable Ollama with instant failure."""

    def __init__(self):
        self.check_count = 0
        self.chat_count = 0

    def is_available(self) -> bool:
        self.check_count += 1
        return False

    def chat(self, *args, **kwargs):
        self.chat_count += 1
        raise RuntimeError("Chat must not be called when unavailable")


def test_unquantified_relative_dates_produce_clarification_never_guessed():
    ref_date = date(2026, 11, 7)

    # 1. "last month"
    res_last_month = parse_detailed("Salinity in Arabian Sea last month", today=ref_date, allow_llm=False)
    assert res_last_month.is_success is False
    assert res_last_month.spec is None
    assert res_last_month.clarification is not None
    assert "date_range" in res_last_month.clarification.ambiguous_fields
    assert "explicit year or date range" in res_last_month.clarification.message

    # 2. "recent"
    res_recent = parse_detailed("Recent temperature profiles in Arabian Sea", today=ref_date, allow_llm=False)
    assert res_recent.is_success is False
    assert res_recent.spec is None
    assert res_recent.clarification is not None
    assert "date_range" in res_recent.clarification.ambiguous_fields
    assert "explicit year or date range" in res_recent.clarification.message


def test_ollama_unavailable_path_under_3_seconds_with_missing_fields():
    reset_availability_cache()
    mock = QuickUnreachableMockClient()
    t0 = time.monotonic()
    outcome = parse_detailed("salinity", llm_client=mock, allow_llm=True)
    duration = time.monotonic() - t0

    assert duration < 3.0, f"Expected completion < 3s, took {duration:.2f}s"
    assert outcome.is_success is False
    assert outcome.clarification is not None
    assert mock.check_count == 1
    assert mock.chat_count == 0

    msg = outcome.clarification.message
    assert "The language model is not available" in msg
    assert "region" in outcome.clarification.missing_fields
    assert "date_range" in outcome.clarification.missing_fields


def test_oversized_basin_query_actionable_suggestions_not_stack_trace():
    io_bbox = KNOWN_REGIONS["Indian Ocean"]
    spec = QuerySpec(
        region=io_bbox,
        date_range=DateRange(start=date(2022, 1, 1), end=date(2022, 1, 31)),
        variables=[Variable.TEMP],
        depth_range=(0.0, 500.0),
        intent=Intent.PROFILE,
        mode=DataMode.RESEARCH,
    )

    # Direct validation check
    with pytest.raises(OversizedRequestError) as exc_info:
        validate_spec(spec)

    err_msg = str(exc_info.value)
    assert "exceeds the maximum limit" in err_msg
    assert "Indian Ocean" in err_msg
    assert "Shorter period" in err_msg
    assert "Shallower depth" in err_msg
    assert "Smaller region" in err_msg

    # Pipeline run check
    res = run("temperature in Indian Ocean in January 2022")
    assert res.status == PipelineStatus.CLARIFICATION_NEEDED
    assert res.clarification is not None
    assert "exceeds allowable size cap" in res.clarification.message
    assert len(res.clarification.suggestions) > 0
    assert "Shorter period" in res.clarification.suggestions[0]
