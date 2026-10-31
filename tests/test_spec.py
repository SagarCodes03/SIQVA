"""Tests for QuerySpec creation, normalization, and hash stability."""

from datetime import date
import pytest
from pydantic import ValidationError

from siqva.spec import (
    BoundingBox,
    DataMode,
    DateRange,
    DepthRange,
    Intent,
    QuerySpec,
    Variable,
)


def test_valid_spec_creation():
    spec = QuerySpec(
        region=BoundingBox(lon_min=65.0, lon_max=75.0, lat_min=10.0, lat_max=20.0),
        date_range=DateRange(start=date(2023, 1, 1), end=date(2023, 1, 31)),
        variables=[Variable.TEMP, Variable.PSAL],
        depth_range=DepthRange(min_depth=0.0, max_depth=1000.0),
        mode=DataMode.RESEARCH,
        intent=Intent.PROFILE,
    )
    assert spec.mode == DataMode.RESEARCH
    assert spec.intent == Intent.PROFILE
    assert len(spec.variables) == 2


def test_default_mode_is_research():
    spec = QuerySpec(
        region=[65.0, 75.0, 10.0, 20.0],
        date_range=["2023-01-01", "2023-01-31"],
        variables=["TEMP"],
        intent=Intent.MAP,
    )
    assert spec.mode == DataMode.RESEARCH
    assert spec.depth_range is None


def test_invalid_variable_raises():
    with pytest.raises(ValidationError):
        QuerySpec(
            region=[65.0, 75.0, 10.0, 20.0],
            date_range=["2023-01-01", "2023-01-31"],
            variables=["INVALID_VAR"],
            intent=Intent.PROFILE,
        )


def test_invalid_intent_raises():
    with pytest.raises(ValidationError):
        QuerySpec(
            region=[65.0, 75.0, 10.0, 20.0],
            date_range=["2023-01-01", "2023-01-31"],
            variables=["TEMP"],
            intent="unknown_intent",  # type: ignore
        )


def test_hash_stability_same_instance():
    spec = QuerySpec(
        region=[60.0, 70.0, 10.0, 15.0],
        date_range=["2022-05-01", "2022-05-15"],
        variables=["TEMP", "PSAL"],
        intent=Intent.PROFILE,
    )
    h1 = spec.spec_hash()
    h2 = spec.spec_hash()
    assert h1 == h2
    assert len(h1) == 64  # SHA-256 length in hex


def test_hash_stability_variable_ordering_and_duplicates():
    spec1 = QuerySpec(
        region=[60.0, 70.0, 10.0, 15.0],
        date_range=["2022-05-01", "2022-05-15"],
        variables=[Variable.TEMP, Variable.PSAL],
        intent=Intent.PROFILE,
    )
    spec2 = QuerySpec(
        region=[60.0, 70.0, 10.0, 15.0],
        date_range=["2022-05-01", "2022-05-15"],
        variables=[Variable.PSAL, Variable.TEMP, Variable.PSAL],
        intent=Intent.PROFILE,
    )
    assert spec1.spec_hash() == spec2.spec_hash()
    assert spec1.normalized_json() == spec2.normalized_json()


def test_hash_stability_float_representation():
    spec1 = QuerySpec(
        region=[60, 70, 10, 15],
        date_range=["2022-05-01", "2022-05-15"],
        variables=["TEMP"],
        intent=Intent.TS,
    )
    spec2 = QuerySpec(
        region=[60.0, 70.0, 10.0, 15.0],
        date_range=["2022-05-01", "2022-05-15"],
        variables=["TEMP"],
        intent=Intent.TS,
    )
    assert spec1.spec_hash() == spec2.spec_hash()


def test_distinct_specs_have_distinct_hashes():
    spec1 = QuerySpec(
        region=[60.0, 70.0, 10.0, 15.0],
        date_range=["2022-05-01", "2022-05-15"],
        variables=["TEMP"],
        intent=Intent.PROFILE,
    )
    spec2 = QuerySpec(
        region=[60.0, 70.0, 10.0, 15.0],
        date_range=["2022-05-01", "2022-05-16"],  # different date
        variables=["TEMP"],
        intent=Intent.PROFILE,
    )
    assert spec1.spec_hash() != spec2.spec_hash()


def test_fetch_key_shares_across_differing_intents():
    spec_profile = QuerySpec(
        region=[60.0, 70.0, 10.0, 15.0],
        date_range=["2022-05-01", "2022-05-15"],
        depth_range=[0.0, 1000.0],
        variables=["TEMP", "PSAL"],
        mode=DataMode.RESEARCH,
        intent=Intent.PROFILE,
    )
    spec_map = QuerySpec(
        region=[60.0, 70.0, 10.0, 15.0],
        date_range=["2022-05-01", "2022-05-15"],
        depth_range=[0.0, 1000.0],
        variables=["TEMP", "PSAL"],
        mode=DataMode.RESEARCH,
        intent=Intent.MAP,
    )
    # Different intents produce different spec_hash values
    assert spec_profile.spec_hash() != spec_map.spec_hash()

    # But they share the exact same fetch_key for cached data reuse
    assert spec_profile.fetch_key() == spec_map.fetch_key()
    assert len(spec_profile.fetch_key()) == 64


def test_fetch_key_differs_when_data_parameters_differ():
    base_spec = QuerySpec(
        region=[60.0, 70.0, 10.0, 15.0],
        date_range=["2022-05-01", "2022-05-15"],
        variables=["TEMP"],
        mode=DataMode.RESEARCH,
        intent=Intent.PROFILE,
    )
    different_mode = QuerySpec(
        region=[60.0, 70.0, 10.0, 15.0],
        date_range=["2022-05-01", "2022-05-15"],
        variables=["TEMP"],
        mode=DataMode.EXPERT,
        intent=Intent.PROFILE,
    )
    assert base_spec.fetch_key() != different_mode.fetch_key()

