"""Unit tests for the in-domain query gate and out-of-domain refusals (U3-4)."""

from pathlib import Path
from unittest.mock import patch
import pandas as pd
import pytest

from siqva.chat import ChatMessage, dispatch
from siqva.fetcher import FetchMetadata, FetchResult, FetchStatus
from siqva.router import has_domain_signal
from siqva.spec import DepthRange

FIXTURE_PATH = Path("tests/fixtures/sample_argo_standard.parquet")
CAT5_REFUSAL = "SIQVA only answers questions regarding physical oceanography and the international Argo float array; general non-marine topics are not supported."


@pytest.fixture
def mock_fetcher():
    df_fixture = pd.read_parquet(FIXTURE_PATH)
    meta = FetchMetadata(
        src="erddap",
        source="erddap",
        argopy_version="1.5.0",
        xarray_version="2026.9.0",
        fetch_timestamp="2026-11-07T12:00:00Z",
        row_count=len(df_fixture),
        profile_count=2,
        data_hash="dummyhash_gate",
        fetch_key="dummykey_gate",
    )
    res = FetchResult(
        status=FetchStatus.SUCCESS,
        data=df_fixture,
        is_cached=True,
        cache_key="dummykey_gate",
        metadata=meta,
        effective_depth_range=DepthRange(min_depth=0.0, max_depth=500.0),
        profile_count_verified=True,
        profile_count=2,
    )

    class DummyFetcher:
        def fetch(self, spec):
            return res

    return DummyFetcher


@pytest.mark.parametrize(
    "question",
    [
        "how to build a llm",
        "write me a python script",
        "best pizza recipe",
        "who won the match",
        "what is the capital of France",
        "tell me a joke",
        "how to fix my car",
        "latest stock market news",
        "who is the president",
        "how to bake sourdough bread",
    ],
)
def test_out_of_domain_queries_refused_with_category_5(tmp_path, question):
    """General non-marine questions must be refused with Category 5 without being clarified."""
    db_file = tmp_path / "cards.sqlite"
    with patch("siqva.card.DEFAULT_DB_PATH", db_file), patch("siqva.chat.DEFAULT_DB_PATH", db_file):
        assert has_domain_signal(question) is False
        msgs, _ = dispatch(question)
        assert len(msgs) == 1
        assert msgs[0].kind == "refusal"
        assert msgs[0].text == CAT5_REFUSAL


def test_small_talk_ok_handled_first(tmp_path):
    """'ok' must be handled under small talk / courtesy, not refused or clarified."""
    db_file = tmp_path / "cards.sqlite"
    with patch("siqva.card.DEFAULT_DB_PATH", db_file), patch("siqva.chat.DEFAULT_DB_PATH", db_file):
        msgs, _ = dispatch("ok")
        assert len(msgs) == 1
        assert msgs[0].kind == "text"
        assert "welcome" in msgs[0].text.lower() or "questions" in msgs[0].text.lower()


def test_typo_temparature_runs_data_query(tmp_path, mock_fetcher):
    """Typo 'temparature' matches 'temperature' via rapidfuzz and passes domain gate to run query."""
    db_file = tmp_path / "cards.sqlite"
    with patch("siqva.card.DEFAULT_DB_PATH", db_file), \
         patch("siqva.chat.DEFAULT_DB_PATH", db_file), \
         patch("siqva.pipeline.fetch", return_value=mock_fetcher().fetch(None)):
        q = "temparature profiles in the Arabian sea in 2022"
        assert has_domain_signal(q) is True
        msgs, _ = dispatch(q, fetcher_fn=mock_fetcher)
        assert len(msgs) == 1
        assert msgs[0].kind == "result"


def test_typo_temparature_conceptual_knowledge_route(tmp_path):
    """'how does temparature and depth are related' passes domain gate and routes to knowledge."""
    db_file = tmp_path / "cards.sqlite"
    with patch("siqva.card.DEFAULT_DB_PATH", db_file), patch("siqva.chat.DEFAULT_DB_PATH", db_file):
        q = "how does temparature and depth are related"
        assert has_domain_signal(q) is True
        msgs, _ = dispatch(q)
        assert len(msgs) == 1
        assert msgs[0].kind == "knowledge"
        # Since not covered in verified notes, gives not_in_notes guidance
        assert "verified knowledge notes" in msgs[0].text or "Sources" in msgs[0].text


def test_show_floats_in_indian_ocean(tmp_path, mock_fetcher):
    """'show floats in the Indian Ocean' passes domain gate via floats/ocean signals."""
    db_file = tmp_path / "cards.sqlite"
    with patch("siqva.card.DEFAULT_DB_PATH", db_file), \
         patch("siqva.chat.DEFAULT_DB_PATH", db_file), \
         patch("siqva.pipeline.fetch", return_value=mock_fetcher().fetch(None)):
        q = "show floats in the Indian Ocean"
        assert has_domain_signal(q) is True
        msgs, _ = dispatch(q, fetcher_fn=mock_fetcher)
        assert len(msgs) == 1
        assert msgs[0].kind in ("result", "clarification")


def test_in_domain_standard_temperature_query(tmp_path, mock_fetcher):
    """'temperature in the Arabian Sea in 2022' is recognized as domain query and executes."""
    db_file = tmp_path / "cards.sqlite"
    with patch("siqva.card.DEFAULT_DB_PATH", db_file), \
         patch("siqva.chat.DEFAULT_DB_PATH", db_file), \
         patch("siqva.pipeline.fetch", return_value=mock_fetcher().fetch(None)):
        q = "temperature in the Arabian Sea in 2022"
        assert has_domain_signal(q) is True
        msgs, _ = dispatch(q, fetcher_fn=mock_fetcher)
        assert len(msgs) == 1
        assert msgs[0].kind == "result"


def test_in_domain_standard_salinity_query(tmp_path, mock_fetcher):
    """'salinity in Bay of Bengal April 2022' is recognized as domain query and executes."""
    db_file = tmp_path / "cards.sqlite"
    with patch("siqva.card.DEFAULT_DB_PATH", db_file), \
         patch("siqva.chat.DEFAULT_DB_PATH", db_file), \
         patch("siqva.pipeline.fetch", return_value=mock_fetcher().fetch(None)):
        q = "salinity in Bay of Bengal April 2022"
        assert has_domain_signal(q) is True
        msgs, _ = dispatch(q, fetcher_fn=mock_fetcher)
        assert len(msgs) == 1
        assert msgs[0].kind == "result"


def test_in_domain_thermocline_missing_date_gets_clarification(tmp_path):
    """'thermocline in the Arabian Sea' passes gate, asks targeted clarification for date."""
    db_file = tmp_path / "cards.sqlite"
    with patch("siqva.card.DEFAULT_DB_PATH", db_file), patch("siqva.chat.DEFAULT_DB_PATH", db_file):
        q = "thermocline in the Arabian Sea"
        assert has_domain_signal(q) is True
        msgs, _ = dispatch(q)
        assert len(msgs) == 1
        assert msgs[0].kind == "clarification"
        assert "year" in msgs[0].text.lower() or "date" in msgs[0].text.lower()


def test_in_domain_coordinates_sound_speed(tmp_path, mock_fetcher):
    """'sound speed profile at 10N, 65E in 2021' passes domain gate via coordinates/acoustic signal."""
    db_file = tmp_path / "cards.sqlite"
    with patch("siqva.card.DEFAULT_DB_PATH", db_file), \
         patch("siqva.chat.DEFAULT_DB_PATH", db_file), \
         patch("siqva.pipeline.fetch", return_value=mock_fetcher().fetch(None)):
        q = "sound speed profile at 10N, 65E in 2021"
        assert has_domain_signal(q) is True
        msgs, _ = dispatch(q, fetcher_fn=mock_fetcher)
        assert len(msgs) == 1
        assert msgs[0].kind in ("result", "clarification")


def test_in_domain_glossary_what_is_mld(tmp_path):
    """'what is MLD' passes domain gate and routes to knowledge/glossary."""
    db_file = tmp_path / "cards.sqlite"
    with patch("siqva.card.DEFAULT_DB_PATH", db_file), patch("siqva.chat.DEFAULT_DB_PATH", db_file):
        q = "what is MLD"
        assert has_domain_signal(q) is True
        msgs, _ = dispatch(q)
        assert len(msgs) == 1
        assert msgs[0].kind == "knowledge"


def test_in_domain_explain_argo_floats(tmp_path):
    """'explain argo floats' passes domain gate and routes to knowledge."""
    db_file = tmp_path / "cards.sqlite"
    with patch("siqva.card.DEFAULT_DB_PATH", db_file), patch("siqva.chat.DEFAULT_DB_PATH", db_file):
        q = "explain argo floats"
        assert has_domain_signal(q) is True
        msgs, _ = dispatch(q)
        assert len(msgs) == 1
        assert msgs[0].kind == "knowledge"
