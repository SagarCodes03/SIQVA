"""Tests for conversational follow-ups and ConversationState (Q7)."""

from datetime import date
import pytest

from siqva.followup import ConversationState, FollowUpResult, try_resolve_followup
from siqva.spec import DataMode, DateRange, Intent, QuerySpec, Variable


@pytest.fixture
def arabian_sea_spec() -> QuerySpec:
    return QuerySpec(
        region=[50.0, 75.0, 10.0, 25.0],
        date_range=["2022-01-01", "2022-12-31"],
        variables=["TEMP"],
        intent=Intent.PROFILE,
    )


@pytest.fixture
def base_state(arabian_sea_spec: QuerySpec) -> ConversationState:
    return ConversationState(
        last_spec=arabian_sea_spec,
        last_question="temperature profiles in the Arabian Sea in 2022",
        turn_count=1,
    )


def test_no_previous_query_returns_unresolved():
    empty_state = ConversationState()
    res = try_resolve_followup("same for salinity", empty_state)
    assert res.resolved is False
    assert "No previous query" in res.failure_reason


def test_variable_swap_salinity(base_state: ConversationState):
    res = try_resolve_followup("same for salinity", base_state)
    assert res.resolved is True
    assert res.spec is not None
    assert Variable.PSAL in res.spec.variables
    assert "variable" in res.edit_summary


def test_variable_swap_temperature(base_state: ConversationState):
    # Start with PSAL spec
    psal_spec = base_state.last_spec.model_copy(update={"variables": [Variable.PSAL]})
    state = base_state.model_copy(update={"last_spec": psal_spec})
    res = try_resolve_followup("now for temperature", state)
    assert res.resolved is True
    assert Variable.TEMP in res.spec.variables


def test_year_swap(base_state: ConversationState):
    res = try_resolve_followup("now 2023", base_state)
    assert res.resolved is True
    assert res.spec.date_range.start == date(2023, 1, 1)
    assert res.spec.date_range.end == date(2023, 12, 31)
    assert "date_range" in res.edit_summary


def test_year_swap_explicit(base_state: ConversationState):
    res = try_resolve_followup("do it for 2021", base_state)
    assert res.resolved is True
    assert res.spec.date_range.start.year == 2021


def test_region_swap_bay_of_bengal(base_state: ConversationState):
    res = try_resolve_followup("do it for Bay of Bengal", base_state)
    assert res.resolved is True
    assert res.spec.region is not None
    assert "region" in res.edit_summary


def test_combined_variable_and_year(base_state: ConversationState):
    res = try_resolve_followup("same for salinity now 2021", base_state)
    assert res.resolved is True
    assert Variable.PSAL in res.spec.variables
    assert res.spec.date_range.start.year == 2021


def test_unrelated_question_returns_unresolved(base_state: ConversationState):
    res = try_resolve_followup("temperature profiles in the Arabian Sea for 2022", base_state)
    assert res.resolved is False


def test_state_with_new_query_increments_turns(arabian_sea_spec: QuerySpec):
    state = ConversationState()
    new_state = state.with_new_query(arabian_sea_spec, question="test")
    assert new_state.turn_count == 1
    assert new_state.last_spec == arabian_sea_spec
    assert new_state.last_question == "test"


def test_state_is_immutable(arabian_sea_spec: QuerySpec):
    state = ConversationState(last_spec=arabian_sea_spec, turn_count=3)
    new_state = state.with_new_query(arabian_sea_spec)
    # original unchanged
    assert state.turn_count == 3
    assert new_state.turn_count == 4
