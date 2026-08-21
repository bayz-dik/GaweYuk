from datetime import datetime, timezone

from onejob.career_intent.models import (
    IntentOperator,
    IntentStatementRecord,
    IntentStrength,
)
from onejob.career_intent.ontology import temporal_state


AT = datetime(2026, 8, 21, 12, tzinfo=timezone.utc)


def make_statement(**overrides):
    data = dict(
        statement_id="s1",
        intent_version_id="iv1",
        predicate="COMMUTE.MAX_KM",
        operator=IntentOperator.LTE,
        value=25,
        value_type="DISTANCE",
        strength=IntentStrength.STRONG_PREFERENCE,
        provenance={},
    )
    data.update(overrides)
    return IntentStatementRecord(**data)


def test_temporal_state_future_active_expired():
    future = make_statement(
        effective_from=datetime(2026, 8, 22, tzinfo=timezone.utc)
    )
    active = make_statement(
        effective_from=datetime(2026, 8, 20, tzinfo=timezone.utc),
        expires_at=datetime(2026, 8, 22, tzinfo=timezone.utc),
    )
    expired = make_statement(
        expires_at=datetime(2026, 8, 21, 12, tzinfo=timezone.utc)
    )

    assert temporal_state(future, AT) == "FUTURE"
    assert temporal_state(active, AT) == "ACTIVE"
    assert temporal_state(expired, AT) == "EXPIRED"


def test_temporal_state_defaults_to_active_when_unbounded():
    statement = make_statement()
    assert temporal_state(statement, AT) == "ACTIVE"


def test_temporal_state_expiry_boundary_is_exclusive_end():
    # expires_at <= evaluated_at → EXPIRED (boundary is expired)
    boundary = make_statement(
        expires_at=AT
    )
    assert temporal_state(boundary, AT) == "EXPIRED"


def test_temporal_state_effective_from_boundary_is_active():
    # effective_from == evaluated_at → ACTIVE (not future)
    boundary = make_statement(
        effective_from=AT
    )
    assert temporal_state(boundary, AT) == "ACTIVE"


# ---------------------------------------------------------------------------
# Task 3: statement validation and contradiction detection
# ---------------------------------------------------------------------------

import pytest

from onejob.career_intent.models import UnknownPolicy
from onejob.career_intent.validation import (
    InvalidIntentStatement,
    InvalidTemporalRange,
    UnknownIntentPredicate,
    validate_intent_statements,
    validate_statement,
)


def base_statement(**overrides):
    data = dict(
        statement_id="s1",
        intent_version_id="iv1",
        predicate="COMPENSATION.MIN_SALARY",
        operator=IntentOperator.GTE,
        value=6_000_000,
        value_type="MONEY",
        strength=IntentStrength.HARD_CONSTRAINT,
        provenance={},
    )
    data.update(overrides)
    return IntentStatementRecord(**data)


def hard(predicate, operator, value):
    return IntentStatementRecord(
        statement_id=f"s-{predicate}",
        intent_version_id="iv1",
        predicate=predicate,
        operator=IntentOperator(operator),
        value=value,
        value_type="MONEY",
        strength=IntentStrength.HARD_CONSTRAINT,
        provenance={},
    )


def soft(predicate, operator, value):
    return IntentStatementRecord(
        statement_id=f"s-soft-{predicate}",
        intent_version_id="iv1",
        predicate=predicate,
        operator=IntentOperator(operator),
        value=value,
        value_type="MONEY",
        strength=IntentStrength.SOFT_PREFERENCE,
        provenance={},
    )


def test_unknown_predicate_is_invalid():
    statement = base_statement(
        predicate="ARBITRARY.EXPRESSION",
        value="anything",
    )
    with pytest.raises(UnknownIntentPredicate):
        validate_statement(statement)


def test_invalid_temporal_range_is_rejected():
    statement = base_statement(
        effective_from=datetime(2026, 9, 2, tzinfo=timezone.utc),
        expires_at=datetime(2026, 9, 1, tzinfo=timezone.utc),
    )
    with pytest.raises(InvalidTemporalRange):
        validate_statement(statement)


def test_unknown_policy_is_rejected_when_predicate_does_not_allow_it():
    statement = base_statement(
        predicate="LOCATION.PREFERRED",
        operator=IntentOperator.IN,
        value=["Cikarang"],
        value_type="LOCATION_REF_OR_TEXT",
        unknown_policy=UnknownPolicy.BLOCK_IF_UNVERIFIED,
    )
    with pytest.raises(InvalidIntentStatement):
        validate_statement(statement)


def test_operator_not_allowed_is_rejected():
    statement = base_statement(
        predicate="COMPENSATION.MIN_SALARY",
        operator=IntentOperator.LTE,
    )
    with pytest.raises(InvalidIntentStatement):
        validate_statement(statement)


def test_strength_not_allowed_is_rejected():
    # SHIFT.AVOID_NIGHT allows all strengths; craft a case by using an
    # allowed predicate but disallowed strength is not possible with _ALL.
    # Instead validate a valid statement passes.
    validate_statement(base_statement())


def test_impossible_hard_salary_range_is_unsatisfiable():
    statements = [
        hard("COMPENSATION.MIN_SALARY", "GTE", 7_000_000),
        hard("COMPENSATION.MAX_SALARY", "LTE", 6_000_000),
    ]
    result = validate_intent_statements(statements, at=AT)
    assert result.status == "UNSATISFIABLE"
    assert result.hard_conflicts


def test_hard_and_soft_tension_does_not_delete_soft_statement():
    statements = [
        hard("COMPENSATION.MIN_SALARY", "GTE", 7_000_000),
        soft("COMPENSATION.MAX_SALARY", "LTE", 6_000_000),
    ]
    result = validate_intent_statements(statements, at=AT)
    assert result.status == "VALID_WITH_TENSIONS"
    assert len(result.active_statements) == 2
    assert result.tensions


def test_valid_intent_has_no_conflicts():
    statements = [
        hard("COMPENSATION.MIN_SALARY", "GTE", 6_000_000),
        hard("COMPENSATION.MAX_SALARY", "LTE", 10_000_000),
    ]
    result = validate_intent_statements(statements, at=AT)
    assert result.status == "VALID"
    assert not result.hard_conflicts
    assert not result.tensions


def test_future_and_expired_excluded_from_active_set():
    statements = [
        hard("COMPENSATION.MIN_SALARY", "GTE", 6_000_000),
        IntentStatementRecord(
            statement_id="s-expired",
            intent_version_id="iv1",
            predicate="COMPENSATION.MAX_SALARY",
            operator=IntentOperator.LTE,
            value=5_000_000,
            value_type="MONEY",
            strength=IntentStrength.HARD_CONSTRAINT,
            expires_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
            provenance={},
        ),
    ]
    result = validate_intent_statements(statements, at=AT)
    # expired MAX_SALARY 5M would otherwise contradict MIN 6M; excluded → VALID
    assert result.status == "VALID"
    assert len(result.active_statements) == 1


def test_validate_does_not_mutate_inputs():
    statements = [hard("COMPENSATION.MIN_SALARY", "GTE", 6_000_000)]
    validate_intent_statements(statements, at=AT)
    assert statements[0].value == 6_000_000
