"""Tests for rules_parser deterministic extraction with 26 realistic test queries."""

from datetime import date
import pytest

from argocard.gazetteer import KNOWN_REGIONS
from argocard.rules_parser import parse_rules
from argocard.spec import BoundingBox, DataMode, DateRange, DepthRange, Intent, Variable

REF_DATE = date(2024, 6, 15)


def test_q1_complete_profile_march_2023():
    q = "Show me a temperature profile in the Arabian Sea for March 2023"
    res = parse_rules(q, today=REF_DATE)
    assert res.region == KNOWN_REGIONS["Arabian Sea"]
    assert res.region_name == "Arabian Sea"
    assert res.date_range == DateRange(start=date(2023, 3, 1), end=date(2023, 3, 31))
    assert res.variables == [Variable.TEMP]
    assert res.mode == DataMode.RESEARCH
    assert res.intent == Intent.PROFILE
    assert res.missing == []
    assert res.ambiguous == []


def test_q2_salinity_trend_year_range():
    q = "What is the salinity trend in the Indian Ocean for 2022-2023?"
    res = parse_rules(q, today=REF_DATE)
    assert res.region == KNOWN_REGIONS["Indian Ocean"]
    assert res.date_range == DateRange(start=date(2022, 1, 1), end=date(2023, 12, 31))
    assert res.variables == [Variable.PSAL]
    assert res.intent == Intent.TREND
    assert res.missing == []


def test_q3_float_map_last_6_months():
    q = "Map where floats are located in the North Atlantic over the last 6 months"
    res = parse_rules(q, today=REF_DATE)
    assert res.region == KNOWN_REGIONS["North Atlantic"]
    # 6 months before 2024-06-15 is ~2023-12-15
    assert res.date_range is not None
    assert res.date_range.end == REF_DATE
    assert res.date_range.start.year == 2023 and res.date_range.start.month == 12
    assert res.intent == Intent.MAP


def test_q4_ts_diagram_since_january_2024():
    q = "Draw a T-S diagram for Eastern equatorial Pacific since January 2024"
    res = parse_rules(q, today=REF_DATE)
    assert res.region == KNOWN_REGIONS["Eastern equatorial Pacific"]
    assert res.date_range == DateRange(start=date(2024, 1, 1), end=REF_DATE)
    assert res.intent == Intent.TS


def test_q5_realtime_mode_with_coordinates():
    q = "Real-time temperature profile near 10N-20N, 60E-70E for March 2023"
    res = parse_rules(q, today=REF_DATE)
    assert res.region == BoundingBox(lon_min=60.0, lon_max=70.0, lat_min=10.0, lat_max=20.0)
    assert res.mode == DataMode.STANDARD
    assert res.variables == [Variable.TEMP]
    assert res.intent == Intent.PROFILE


def test_q6_expert_mode_override():
    q = "Show all data including unchecked salinity profiles in Mediterranean Sea for 2022"
    res = parse_rules(q, today=REF_DATE)
    assert res.region == KNOWN_REGIONS["Mediterranean Sea"]
    assert res.mode == DataMode.EXPERT
    assert res.variables == [Variable.PSAL]
    assert res.date_range == DateRange(start=date(2022, 1, 1), end=date(2022, 12, 31))


def test_q7_depth_range_extraction():
    q = "Vertical profile of temperature in the top 500m of the Arabian Sea in 2022"
    res = parse_rules(q, today=REF_DATE)
    assert res.depth_range == DepthRange(min_depth=0.0, max_depth=500.0)
    assert res.variables == [Variable.TEMP]
    assert res.intent == Intent.PROFILE


def test_q8_missing_region():
    q = "What is the temperature profile for March 2023?"
    res = parse_rules(q, today=REF_DATE)
    assert res.region is None
    assert "region" in res.missing
    assert res.variables == [Variable.TEMP]
    assert res.intent == Intent.PROFILE


def test_q9_missing_dates():
    q = "Show salinity map in the Bay of Bengal"
    res = parse_rules(q, today=REF_DATE)
    assert res.date_range is None
    assert "date_range" in res.missing
    assert res.region == KNOWN_REGIONS["Bay of Bengal"]
    assert res.variables == [Variable.PSAL]
    assert res.intent == Intent.MAP


def test_q10_missing_variables():
    q = "Show a map of float trajectories in the Mediterranean Sea for 2023"
    res = parse_rules(q, today=REF_DATE)
    assert res.variables is None
    assert "variables" in res.missing
    assert res.intent == Intent.MAP


def test_q11_missing_intent():
    q = "Data for temperature and salinity in the Arabian Sea for 2022"
    res = parse_rules(q, today=REF_DATE)
    assert res.intent is None
    assert "intent" in res.missing
    assert res.variables == [Variable.PSAL, Variable.TEMP]


def test_q12_conflicting_intent_hints():
    q = "Show a map and vertical profile of temperature in the Arabian Sea for March 2023"
    res = parse_rules(q, today=REF_DATE)
    # Never guess when conflicting hints exist
    assert res.intent is None
    assert any("intent" in a and "map" in a and "profile" in a for a in res.ambiguous)


def test_q13_ambiguous_region():
    q = "Map of floats in the Sea for 2022"
    res = parse_rules(q, today=REF_DATE)
    assert res.region is None
    assert any("region" in a for a in res.ambiguous)


def test_q14_unsupported_region_north_pacific():
    q = "Show temperature profiles in the North Pacific for March 2023"
    res = parse_rules(q, today=REF_DATE)
    assert res.region is None
    assert "region" in res.missing


def test_q15_unsupported_region_red_sea():
    q = "Salinity observations in the Red Sea over the last 30 days"
    res = parse_rules(q, today=REF_DATE)
    assert res.region is None
    assert "region" in res.missing


def test_q16_coordinate_string_south_north():
    q = "Temperature profile at 5S to 15N, 80E to 90E for 2022-2023"
    res = parse_rules(q, today=REF_DATE)
    assert res.region == BoundingBox(lon_min=80.0, lon_max=90.0, lat_min=-5.0, lat_max=15.0)


def test_q17_region_typo_resolution():
    q = "Show temperature profiles in Arbian Sea for March 2023"
    res = parse_rules(q, today=REF_DATE)
    assert res.region == KNOWN_REGIONS["Arabian Sea"]
    assert res.region_name == "Arabian Sea"


def test_q18_region_alias_bob():
    q = "Find floats in the bob region for 2022"
    res = parse_rules(q, today=REF_DATE)
    assert res.region == KNOWN_REGIONS["Bay of Bengal"]
    assert res.intent == Intent.MAP


def test_q19_multiple_variables():
    q = "Temperature, salinity and pressure profiles in the Mediterranean for 2022"
    res = parse_rules(q, today=REF_DATE)
    assert res.variables == [Variable.PRES, Variable.PSAL, Variable.TEMP]
    assert res.region == KNOWN_REGIONS["Mediterranean Sea"]


def test_q20_single_year_during():
    q = "Map float positions in the North Atlantic during 2021"
    res = parse_rules(q, today=REF_DATE)
    assert res.date_range == DateRange(start=date(2021, 1, 1), end=date(2021, 12, 31))
    assert res.intent == Intent.MAP


def test_q21_explicit_iso_date_range():
    q = "Temperature trend in the Arabian Sea between 2023-01-01 and 2023-06-30"
    res = parse_rules(q, today=REF_DATE)
    assert res.date_range == DateRange(start=date(2023, 1, 1), end=date(2023, 6, 30))
    assert res.intent == Intent.TREND


def test_q22_operational_near_realtime_mode():
    # Bare 'operational' should no longer trigger standard mode (defaults to research)
    q_op = "Operational temperature profiles in the Indian Ocean since January 2024"
    res_op = parse_rules(q_op, today=REF_DATE)
    assert res_op.mode == DataMode.RESEARCH

    # Unambiguous 'near real-time' triggers standard mode
    q_nrt = "Near real-time temperature profiles in the Indian Ocean since January 2024"
    res_nrt = parse_rules(q_nrt, today=REF_DATE)
    assert res_nrt.mode == DataMode.STANDARD


def test_q23_raw_expert_mode():
    # Bare 'raw' without 'data' should not trigger expert mode (defaults to research)
    q_raw_bare = "Plot raw depth profile of temperature in Arabian Sea for March 2023"
    res_raw_bare = parse_rules(q_raw_bare, today=REF_DATE)
    assert res_raw_bare.mode == DataMode.RESEARCH

    # Unambiguous 'raw data' triggers expert mode
    q_raw_data = "Plot raw data depth profile of temperature in Arabian Sea for March 2023"
    res_raw_data = parse_rules(q_raw_data, today=REF_DATE)
    assert res_raw_data.mode == DataMode.EXPERT


def test_q24_conflicting_intent_ts_and_trend():
    q = "T-S diagram and temporal trend of salinity in Bay of Bengal for 2022"
    res = parse_rules(q, today=REF_DATE)
    assert res.intent is None
    assert any("intent" in a and "ts" in a and "trend" in a for a in res.ambiguous)


def test_q25_blank_or_uninformative_query():
    q = "Hello can you help me?"
    res = parse_rules(q, today=REF_DATE)
    assert res.region is None
    assert res.date_range is None
    assert res.variables is None
    assert res.intent is None
    assert set(res.missing) == {"region", "date_range", "variables", "intent"}


def test_q26_december_month_and_depth_range():
    q = "Salinity profile from 0 to 1000 dbar in the North Atlantic for December 2022"
    res = parse_rules(q, today=REF_DATE)
    assert res.region == KNOWN_REGIONS["North Atlantic"]
    assert res.date_range == DateRange(start=date(2022, 12, 1), end=date(2022, 12, 31))
    assert res.depth_range == DepthRange(min_depth=0.0, max_depth=1000.0)
    assert res.variables == [Variable.PSAL]
    assert res.intent == Intent.PROFILE


# --- Specific requirement tests ---


def test_requirement_1_depth_not_mapped_to_pres():
    """(1) Stop mapping 'depth' to PRES; PRES is only requested if explicitly 'pressure'."""
    # 'depth' present, should NOT map to PRES
    q1 = "Show temperature and depth profile in the Arabian Sea for 2022"
    res1 = parse_rules(q1, today=REF_DATE)
    assert res1.variables == [Variable.TEMP]
    assert Variable.PRES not in res1.variables

    # 'depth profile' with no other variables -> variables missing, not PRES
    q2 = "Show depth profile in the Arabian Sea for 2022"
    res2 = parse_rules(q2, today=REF_DATE)
    assert res2.variables is None
    assert "variables" in res2.missing

    # Explicit 'pressure' -> maps to PRES
    q3 = "Show pressure and temperature in the Arabian Sea for 2022"
    res3 = parse_rules(q3, today=REF_DATE)
    assert res3.variables == [Variable.PRES, Variable.TEMP]

    # Explicit 'pressure profile'
    q4 = "Show pressure profile in the Arabian Sea for 2022"
    res4 = parse_rules(q4, today=REF_DATE)
    assert res4.variables == [Variable.PRES]


def test_requirement_2_sst_not_in_synonyms_and_marked_ambiguous():
    """(2) Remove 'sst' from synonyms or mark it ambiguous with a note differing from Argo subsurface temperature."""
    # Query with only SST
    q1 = "Show sst in the Arabian Sea for March 2023"
    res1 = parse_rules(q1, today=REF_DATE)
    assert res1.variables is None
    assert "variables" in res1.missing
    assert any("sst" in a.lower() and "subsurface" in a.lower() for a in res1.ambiguous)

    # Query with SST and salinity
    q2 = "Show sst and salinity in the Arabian Sea for March 2023"
    res2 = parse_rules(q2, today=REF_DATE)
    assert res2.variables == [Variable.PSAL]
    assert Variable.TEMP not in (res2.variables or [])
    assert any("sst" in a.lower() and "subsurface" in a.lower() for a in res2.ambiguous)


def test_requirement_3_mode_unambiguous_phrases_and_bare_keywords_removed():
    """(3) Mode overrides require unambiguous phrases; bare 'rt', 'expert', and 'operational' removed."""
    # Bare keywords must NOT override default RESEARCH mode
    assert parse_rules("rt temperature profile in Arabian Sea for 2022", today=REF_DATE).mode == DataMode.RESEARCH
    assert parse_rules("expert salinity profile in Arabian Sea for 2022", today=REF_DATE).mode == DataMode.RESEARCH
    assert parse_rules("operational salinity map in Arabian Sea for 2022", today=REF_DATE).mode == DataMode.RESEARCH

    # Unambiguous STANDARD mode phrases
    assert parse_rules("real-time temperature profile in Arabian Sea for 2022", today=REF_DATE).mode == DataMode.STANDARD
    assert parse_rules("near real-time temperature profile in Arabian Sea for 2022", today=REF_DATE).mode == DataMode.STANDARD
    assert parse_rules("near-real-time temperature profile in Arabian Sea for 2022", today=REF_DATE).mode == DataMode.STANDARD

    # Unambiguous EXPERT mode phrases
    assert parse_rules("include all data for temperature in Arabian Sea for 2022", today=REF_DATE).mode == DataMode.EXPERT
    assert parse_rules("including unchecked salinity profile in Arabian Sea for 2022", today=REF_DATE).mode == DataMode.EXPERT
    assert parse_rules("raw data temperature profile in Arabian Sea for 2022", today=REF_DATE).mode == DataMode.EXPERT


def test_requirement_4_depth_range_extraction():
    """(4) Confirm and test depth-range extraction ('top 500 m', 'below 1000 m', 'between 100 and 500 m')."""
    # 'top 500 m'
    res_top = parse_rules("Temperature profile in the top 500 m of Arabian Sea for 2022", today=REF_DATE)
    assert res_top.depth_range == DepthRange(min_depth=0.0, max_depth=500.0)

    # 'top 500m'
    res_top_nospace = parse_rules("Temperature profile in the top 500m of Arabian Sea for 2022", today=REF_DATE)
    assert res_top_nospace.depth_range == DepthRange(min_depth=0.0, max_depth=500.0)

    # 'below 1000 m' -> deeper than 1000 m down to standard Argo 2000 dbar limit
    res_below = parse_rules("Salinity observations below 1000 m in Arabian Sea for 2022", today=REF_DATE)
    assert res_below.depth_range == DepthRange(min_depth=1000.0, max_depth=2000.0)

    # 'below 1000m'
    res_below_nospace = parse_rules("Salinity observations below 1000m in Arabian Sea for 2022", today=REF_DATE)
    assert res_below_nospace.depth_range == DepthRange(min_depth=1000.0, max_depth=2000.0)

    # 'between 100 and 500 m'
    res_between = parse_rules("Temperature profile between 100 and 500 m in Arabian Sea for 2022", today=REF_DATE)
    assert res_between.depth_range == DepthRange(min_depth=100.0, max_depth=500.0)

    # 'between 100m and 500m'
    res_between_units = parse_rules("Temperature profile between 100m and 500m in Arabian Sea for 2022", today=REF_DATE)
    assert res_between_units.depth_range == DepthRange(min_depth=100.0, max_depth=500.0)


def test_requirement_5_ambiguous_dates_not_guessed():
    """(5) Make 'March' without a year, 'last month', 'this year', and 'recent' resolve to missing or ambiguous, not guessed values."""
    # 'March' without a year
    res_march = parse_rules("Temperature profile in Arabian Sea in March", today=REF_DATE)
    assert res_march.date_range is None
    assert any("date_range" in a for a in res_march.ambiguous)

    # 'last month'
    res_last_month = parse_rules("Salinity in Arabian Sea last month", today=REF_DATE)
    assert res_last_month.date_range is None
    assert any("date_range" in a for a in res_last_month.ambiguous)

    # 'this year'
    res_this_year = parse_rules("Temperature profiles in Arabian Sea this year", today=REF_DATE)
    assert res_this_year.date_range is None
    assert any("date_range" in a for a in res_this_year.ambiguous)

    # 'recent'
    res_recent = parse_rules("Recent temperature profiles in Arabian Sea", today=REF_DATE)
    assert res_recent.date_range is None
    assert any("date_range" in a for a in res_recent.ambiguous)

    # Fully missing date (no temporal words at all) resolves to missing
    res_no_date = parse_rules("Temperature profiles in Arabian Sea", today=REF_DATE)
    assert res_no_date.date_range is None
    assert "date_range" in res_no_date.missing


