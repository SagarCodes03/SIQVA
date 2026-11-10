"""Tests verifying reproduction scope and honesty in generated scripts for all 13 intents."""

import pytest

from siqva.card import UNSUPPORTED_SCRIPT_PLOT_INTENTS, build_card, generate_script
from siqva.spec import (
    BoundingBox,
    DataMode,
    DateRange,
    DepthRange,
    Intent,
    QuerySpec,
    Variable,
)


@pytest.mark.parametrize("intent", list(Intent))
def test_generate_script_reproducibility_honesty_for_all_intents(intent, sample_fetch_result):
    """Verify that script header explicitly declares reproduction scope for every intent."""
    spec = QuerySpec(
        region=BoundingBox(lon_min=60.0, lon_max=65.0, lat_min=10.0, lat_max=15.0),
        date_range=DateRange(start="2022-01-01", end="2022-01-05"),
        variables=[Variable.TEMP, Variable.PSAL],
        depth_range=DepthRange(min_depth=0.0, max_depth=500.0),
        mode=DataMode.RESEARCH,
        intent=intent,
    )

    card = build_card(spec, sample_fetch_result, None)
    script = generate_script(card)

    assert f"Intent: {intent.value}" in script

    if intent in UNSUPPORTED_SCRIPT_PLOT_INTENTS:
        # Must contain exact honest disclaimer
        assert "data fetch and counts only; plots for this intent are not included" in script
    else:
        # Core intents state reproduction scope without claiming full UI plotting
        assert f"data fetch, QC filtering, and profile counts for {intent.value} analysis" in script

    # Verify script compiles syntactically
    compile(script, f"<script_{intent.value}>", "exec")


@pytest.mark.parametrize("intent", list(Intent))
def test_generate_script_chunked_reproducibility_honesty(intent, sample_fetch_result):
    """Verify that chunked script also contains explicit reproduction scope for every intent."""
    spec = QuerySpec(
        region=BoundingBox(lon_min=60.0, lon_max=65.0, lat_min=10.0, lat_max=15.0),
        date_range=DateRange(start="2022-01-01", end="2022-03-31"),
        variables=[Variable.TEMP],
        depth_range=DepthRange(min_depth=0.0, max_depth=500.0),
        mode=DataMode.STANDARD,
        intent=intent,
    )

    card = build_card(spec, sample_fetch_result, None, chunks=[("2022-01-01", "2022-01-31"), ("2022-02-01", "2022-02-28")])
    script = generate_script(card)

    assert f"Intent: {intent.value}" in script
    if intent in UNSUPPORTED_SCRIPT_PLOT_INTENTS:
        assert "data fetch and counts only; plots for this intent are not included" in script
    else:
        assert f"data fetch, QC filtering, and profile counts for {intent.value} analysis" in script

    compile(script, f"<script_chunked_{intent.value}>", "exec")

