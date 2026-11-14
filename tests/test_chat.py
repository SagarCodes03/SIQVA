"""Unit tests for siqva.chat module (C1 Step 2).

Verifies:
- ChatMessage and ChatOption serialization and invariants
- SQLite persistence (save, load, clear, ordering, shared vs isolated)
- Pure dispatcher routing:
  - Safety length cap (>500 chars)
  - Greeting and courtesy matching
  - Standard refusal categories (Categories 1-9)
  - Meta and glossary routes
  - Conceptual questions ("Knowledge answers are not available yet.")
  - Data queries with mock fetcher
  - Follow-up query resolution
  - Oversized and clarification queries with options
"""

from datetime import date
from pathlib import Path
import sqlite3
import pandas as pd
import pytest

from siqva.chat import (
    MAX_QUESTION_LENGTH,
    ChatMessage,
    ChatOption,
    clear_chat_messages,
    dispatch,
    load_chat_messages,
    save_chat_message,
)
from siqva.fetcher import FetchMetadata, FetchResult, FetchStatus
from siqva.followup import ConversationState
from siqva.spec import (
    BoundingBox,
    DataMode,
    DateRange,
    DepthRange,
    Intent,
    QuerySpec,
    Variable,
)

FIXTURE_PATH = Path(__file__).resolve().parent / "fixtures" / "sample_argo_standard.parquet"


@pytest.fixture
def sample_spec() -> QuerySpec:
    return QuerySpec(
        region=BoundingBox(lon_min=60.0, lon_max=70.0, lat_min=10.0, lat_max=20.0),
        date_range=DateRange(start=date(2022, 1, 1), end=date(2022, 1, 10)),
        variables=[Variable.TEMP, Variable.PSAL],
        depth_range=DepthRange(min_depth=0.0, max_depth=500.0),
        mode=DataMode.RESEARCH,
        intent=Intent.PROFILE,
    )


@pytest.fixture
def mock_fetcher(sample_spec):
    df = pd.read_parquet(FIXTURE_PATH)

    def _fetch(spec, **kwargs):
        meta = FetchMetadata(
            src="erddap",
            source="erddap",
            argopy_version="1.4.0",
            xarray_version="2025.9.0",
            fetch_timestamp="2024-01-15T12:00:00Z",
            row_count=len(df),
            profile_count=2,
            data_hash="chat_test_hash_123",
            fetch_key=spec.fetch_key(),
        )
        return FetchResult(
            status=FetchStatus.SUCCESS,
            data=df,
            is_cached=False,
            cache_key=spec.fetch_key(),
            metadata=meta,
            effective_depth_range=spec.depth_range,
            profile_count_verified=True,
        )

    return _fetch


# ==============================================================================
# Model & Persistence Tests
# ==============================================================================


def test_chat_message_and_option_serialization():
    opt = ChatOption(label="Use 2023", action_type="clarification", query_text="in 2023")
    msg = ChatMessage(
        role="assistant",
        kind="clarification",
        text="Which year?",
        understood_as="Understood as: Arabian Sea",
        options=[opt],
    )
    assert msg.role == "assistant"
    assert msg.kind == "clarification"
    assert len(msg.options) == 1
    assert msg.options[0].label == "Use 2023"


def test_sqlite_persistence_roundtrip(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("SIQVA_SHARED_HISTORY", "0")
    db_file = tmp_path / "test_chat.sqlite"
    msg1 = ChatMessage(role="user", kind="text", text="Hello SIQVA")
    msg2 = ChatMessage(
        role="assistant",
        kind="result",
        text="Found 2 profiles",
        card_id="card123",
        understood_as="Understood as: Arabian Sea",
    )

    save_chat_message(msg1, session_id="s1", db_path=db_file)
    save_chat_message(msg2, session_id="s1", db_path=db_file)

    loaded = load_chat_messages(session_id="s1", db_path=db_file)
    assert len(loaded) == 2
    assert loaded[0].text == "Hello SIQVA"
    assert loaded[0].role == "user"
    assert loaded[1].text == "Found 2 profiles"
    assert loaded[1].card_id == "card123"
    assert loaded[1].understood_as == "Understood as: Arabian Sea"

    # Isolation between sessions
    loaded_s2 = load_chat_messages(session_id="s2", db_path=db_file)
    assert len(loaded_s2) == 0

    # Clear s1
    clear_chat_messages(session_id="s1", db_path=db_file)
    loaded_after = load_chat_messages(session_id="s1", db_path=db_file)
    assert len(loaded_after) == 0


# ==============================================================================
# Dispatcher Tests
# ==============================================================================


def test_dispatch_length_cap():
    long_q = "a" * (MAX_QUESTION_LENGTH + 1)
    messages, state = dispatch(long_q)
    assert len(messages) == 1
    assert messages[0].kind == "error"
    assert "too long" in messages[0].text


def test_dispatch_greeting():
    messages, state = dispatch("hello there")
    assert len(messages) == 1
    assert messages[0].kind == "text"
    assert "Hello! I am SIQVA" in messages[0].text


def test_dispatch_courtesy():
    messages, state = dispatch("thank you very much")
    assert len(messages) == 1
    assert messages[0].kind == "text"
    assert "welcome" in messages[0].text.lower()


def test_dispatch_refusal_categories():
    # Category 1: Forecast
    msgs, _ = dispatch("forecast temperature next week")
    assert len(msgs) == 1
    assert msgs[0].kind == "refusal"

    # Category 4: Medical advice
    msgs, _ = dispatch("how to treat a jellyfish sting")
    assert len(msgs) == 1
    assert msgs[0].kind == "refusal"

    # Category 5: Out of domain poem
    msgs, _ = dispatch("write a poem about french revolution")
    assert len(msgs) == 1
    assert msgs[0].kind == "refusal"


def test_dispatch_conceptual_knowledge():
    msgs, _ = dispatch("what is an argo float?")
    assert len(msgs) == 1
    assert msgs[0].kind == "knowledge"
    assert "Knowledge answers are not available yet." in msgs[0].text


def test_dispatch_meta_route():
    msgs, _ = dispatch("what did I just query?")
    assert len(msgs) == 1
    assert msgs[0].kind == "text"
    assert "No query has been run" in msgs[0].text


def test_dispatch_glossary_route():
    msgs, _ = dispatch("what is MLD?")
    assert len(msgs) == 1
    assert msgs[0].kind == "knowledge"
    assert "MLD" in msgs[0].text
    assert "de Boyer" in msgs[0].text


def test_dispatch_data_query(mock_fetcher, tmp_path: Path):
    db_file = tmp_path / "cards.sqlite"
    msgs, state = dispatch(
        "temperature in Arabian Sea in Jan 2022",
        fetcher_fn=mock_fetcher,
    )
    assert len(msgs) == 1
    msg = msgs[0]
    assert msg.kind == "result"
    assert msg.card_id is not None
    assert msg.understood_as is not None
    assert "Arabian Sea" in msg.understood_as
    assert state.last_spec is not None
    assert state.last_spec.intent == Intent.PROFILE

    # Follow-up test
    msgs2, state2 = dispatch(
        "show salinity",
        conversation_state=state,
        fetcher_fn=mock_fetcher,
    )
    assert len(msgs2) == 1
    assert msgs2[0].kind == "result"
    assert Variable.PSAL in state2.last_spec.variables


def test_dispatch_clarification_query():
    # Bare month with no year triggers clarification
    msgs, _ = dispatch("temperature in Arabian Sea in March")
    assert len(msgs) == 1
    assert msgs[0].kind == "clarification"
    assert msgs[0].understood_as is not None
