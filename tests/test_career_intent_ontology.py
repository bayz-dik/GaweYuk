import pytest

from onejob.career_intent.models import (
    IntentCardinality,
    IntentOperator,
    IntentStrength,
    StrictnessDirection,
)
from onejob.career_intent.ontology import (
    compare_strictness,
    get_intent_predicate_definition,
)


def test_min_salary_is_typed_as_higher_is_stricter():
    definition = get_intent_predicate_definition(
        "COMPENSATION.MIN_SALARY"
    )
    assert definition.cardinality is IntentCardinality.ONE
    assert definition.operator is IntentOperator.GTE
    assert (
        definition.strictness_direction
        is StrictnessDirection.HIGHER_IS_STRICTER
    )
    assert IntentStrength.HARD_CONSTRAINT in definition.allowed_strengths


def test_min_salary_strictness_is_semantic():
    assert compare_strictness(
        "COMPENSATION.MIN_SALARY", 6_000_000, 7_000_000
    ) == "TIGHTER"
    assert compare_strictness(
        "COMPENSATION.MIN_SALARY", 6_000_000, 5_000_000
    ) == "WEAKER"


def test_min_salary_equal_values():
    assert compare_strictness(
        "COMPENSATION.MIN_SALARY", 6_000_000, 6_000_000
    ) == "EQUAL"


def test_max_commute_inverts_numeric_strictness():
    assert compare_strictness(
        "COMMUTE.MAX_KM", 25, 15
    ) == "TIGHTER"
    assert compare_strictness(
        "COMMUTE.MAX_KM", 25, 40
    ) == "WEAKER"


def test_max_salary_is_lower_is_stricter():
    definition = get_intent_predicate_definition(
        "COMPENSATION.MAX_SALARY"
    )
    assert (
        definition.strictness_direction
        is StrictnessDirection.LOWER_IS_STRICTER
    )
    assert compare_strictness(
        "COMPENSATION.MAX_SALARY", 6_000_000, 5_000_000
    ) == "TIGHTER"


def test_many_value_predicate_has_no_scalar_strictness_direction():
    definition = get_intent_predicate_definition("LOCATION.PREFERRED")
    assert definition.cardinality is IntentCardinality.MANY
    # set-valued preference has no scalar strictness direction
    assert definition.strictness_direction is StrictnessDirection.NONE


def test_strictness_none_direction_returns_unknown_unless_equal():
    assert compare_strictness(
        "LOCATION.PREFERRED", ["Cikarang"], ["Bekasi"]
    ) == "UNKNOWN"
    assert compare_strictness(
        "LOCATION.PREFERRED", ["Cikarang"], ["Cikarang"]
    ) == "EQUAL"


def test_unknown_predicate_is_rejected():
    with pytest.raises(KeyError):
        get_intent_predicate_definition("ARBITRARY.EXPRESSION")


def test_all_v1_predicates_are_registered():
    for predicate in [
        "COMPENSATION.MIN_SALARY",
        "COMPENSATION.MAX_SALARY",
        "COMMUTE.MAX_KM",
        "LOCATION.PREFERRED",
        "WORK_MODE.ALLOWED",
        "EMPLOYMENT_TYPE.PREFERRED",
        "SHIFT.AVOID_NIGHT",
        "ROLE.PREFERRED",
        "AVAILABILITY.START_DATE",
    ]:
        definition = get_intent_predicate_definition(predicate)
        assert definition.predicate == predicate
        assert definition.allowed_strengths
        assert definition.allowed_operators
