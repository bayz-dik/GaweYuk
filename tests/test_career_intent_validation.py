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
