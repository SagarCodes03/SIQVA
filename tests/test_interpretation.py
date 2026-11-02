"""Tests for deterministic parser-interpretation display text."""

from datetime import date

from siqva.interpretation import format_understood_as
from siqva.parser import UnderstoodQuery
from siqva.spec import BoundingBox, DataMode, DateRange, DepthRange, Intent, Variable


def test_format_understood_as_for_rules_filled_query():
    understood = UnderstoodQuery(
        region=BoundingBox(lon_min=50.0, lon_max=80.0, lat_min=0.0, lat_max=30.0),
        region_name="Arabian Sea",
        date_range=DateRange(start=date(2022, 1, 1), end=date(2022, 12, 31)),
        variables=[Variable.PSAL, Variable.TEMP],
        depth_range=DepthRange(min_depth=0.0, max_depth=1000.0),
        mode=DataMode.RESEARCH,
        intent=Intent.PROFILE,
    )

    line = format_understood_as(
        understood,
        {
            "region": "rules",
            "date_range": "rules",
            "variables": "rules",
            "depth_range": "rules",
            "mode": "rules",
            "intent": "rules",
        },
    )

    assert line.startswith("Understood as:")
    assert "Region: Arabian Sea (box [50.00, 80.00, 0.00, 30.00]) [rules]" in line
    assert "Dates: 2022-01-01 to 2022-12-31 [rules]" in line
    assert "Variables: PSAL, TEMP [rules]" in line
    assert "Depth: 0\u20131000 dbar [rules]" in line
    assert "Mode: research [rules]" in line
    assert "Intent: profile [rules]" in line


def test_format_understood_as_marks_llm_filled_fields():
    understood = UnderstoodQuery(
        region=BoundingBox(lon_min=50.0, lon_max=80.0, lat_min=0.0, lat_max=30.0),
        region_name="Arabian Sea",
        date_range=DateRange(start=date(2022, 1, 1), end=date(2022, 1, 31)),
        variables=[Variable.TEMP],
        depth_range=DepthRange(min_depth=0.0, max_depth=500.0),
        mode=DataMode.RESEARCH,
        intent=Intent.PROFILE,
    )

    line = format_understood_as(
        understood,
        {
            "region": "llm",
            "date_range": "llm",
            "variables": "rules",
            "depth_range": "rules",
            "mode": "default",
            "intent": "llm",
        },
    )

    assert "Region: Arabian Sea (box [50.00, 80.00, 0.00, 30.00]) [LLM]" in line
    assert "Dates: 2022-01-01 to 2022-01-31 [LLM]" in line
    assert "Intent: profile [LLM]" in line
    assert "Mode: research [default]" in line


def test_format_understood_as_flags_default_depth():
    understood = UnderstoodQuery(
        depth_range=DepthRange(min_depth=0.0, max_depth=500.0),
        mode=DataMode.RESEARCH,
    )

    line = format_understood_as(
        understood,
        {"depth_range": "default", "mode": "default"},
    )

    assert "Depth: 0\u2013500 dbar (default) [default]" in line
