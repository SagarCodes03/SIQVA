"""Tests for the deterministic query intent router (Q6)."""

import pytest

from siqva.router import RouteTarget, route


def test_data_fetch_default():
    res = route("temperature profiles in the Arabian Sea for 2022")
    assert res.target == RouteTarget.DATA_FETCH
    assert res.provenance == "rules"


def test_glossary_route_what_is():
    res = route("what is MLD?")
    assert res.target == RouteTarget.GLOSSARY
    assert res.extracted_entity == "MLD"


def test_glossary_route_define():
    res = route("define TCHP")
    assert res.target == RouteTarget.GLOSSARY
    assert "TCHP" in res.extracted_entity


def test_glossary_route_bare_acronym():
    res = route("SOFAR")
    assert res.target == RouteTarget.GLOSSARY
    assert res.extracted_entity == "SOFAR"


def test_glossary_does_not_match_data_question():
    # "what is the temperature" should NOT route to glossary
    res = route("what is the temperature in the Arabian Sea in 2022?")
    assert res.target != RouteTarget.GLOSSARY


def test_meta_route_last_query():
    res = route("what did I just run?")
    assert res.target == RouteTarget.META


def test_meta_route_show_script():
    res = route("show me the script")
    assert res.target == RouteTarget.META


def test_meta_route_versions():
    res = route("which version of argopy is being used?")
    assert res.target == RouteTarget.META


def test_comparison_route_vs():
    res = route("compare Arabian Sea vs Bay of Bengal temperature in 2022")
    assert res.target == RouteTarget.COMPARISON


def test_comparison_route_difference():
    res = route("what is the difference between 2021 and 2022 temperature?")
    assert res.target == RouteTarget.COMPARISON


def test_operation_route_mean():
    res = route("what is the average temperature in the Arabian Sea in 2022?")
    assert res.target == RouteTarget.OPERATION


def test_operation_route_max():
    res = route("maximum salinity in the Bay of Bengal in January 2022")
    assert res.target == RouteTarget.OPERATION


def test_empty_query_routes_to_clarification():
    res = route("")
    assert res.target == RouteTarget.CLARIFICATION
    assert "Empty query" in res.reason


def test_route_confidence_is_in_valid_range():
    for question in [
        "SOFAR",
        "compare Arabian Sea vs Indian Ocean 2022",
        "temperature profiles in Arabian Sea in 2022",
        "what is the mean salinity in Arabian Sea in 2022?",
        "show me the script",
    ]:
        res = route(question)
        assert 0.0 <= res.confidence <= 1.0
