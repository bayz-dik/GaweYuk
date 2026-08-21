from datetime import datetime, timezone

import pytest

from onejob.career_intent.commands import (
    AcceptIntentSuggestionCommand,
    CareerIntentCommandService,
    CreateCareerIntentVersionCommand,
    CreateIntentSuggestionCommand,
    NewIntentStatement,
)
from onejob.career_targets.commands import (
    CreateSavedCareerTargetCommand,
    NewTargetOverride,
    ReviseSavedCareerTargetCommand,
    TargetCommandService,
)
from onejob.career_targets.resolver import (
    HardConstraintExceptionRequired,
    resolve_target_policy,
)
from onejob.career_intent.models import (
    IntentOperator,
    IntentStatementRecord,
    IntentStrength,
)
from onejob.career_targets.models import OverrideOperation, TargetIntentOverrideRecord
from onejob.career_twin.errors import AuthorizationDenied
from onejob.career_twin.ontology import ONTOLOGY_VERSION
from onejob.career_twin.repositories import CareerTwinRepository
from onejob.persistence.db import Database


AT = datetime(2026, 8, 21, 12, tzinfo=timezone.utc)


class SequentialIds:
    def __init__(self):
        self.counts = {}

    def __call__(self, kind: str) -> str:
        n = self.counts.get(kind, 0) + 1
        self.counts[kind] = n
        return f"{kind}-{n}"


def owner_a():
    return {"actor_id": "user-a", "twin_id": "twin-a", "is_owner": True, "actor_type": "USER"}


def owner_b():
    return {"actor_id": "user-b", "twin_id": "twin-b", "is_owner": True, "actor_type": "USER"}


@pytest.fixture
def env(tmp_path):
    db = Database(tmp_path / "gaweyuk.db")
    db.initialize()
    with db.transaction() as conn:
        CareerTwinRepository().ensure_twin(conn, "twin-a", "user-a", ONTOLOGY_VERSION)
        CareerTwinRepository().ensure_twin(conn, "twin-b", "user-b", ONTOLOGY_VERSION)
    ids = SequentialIds()
    return db, CareerIntentCommandService(db, id_factory=ids), TargetCommandService(db, id_factory=ids), ids


def salary_statement(value=6_000_000):
    return NewIntentStatement(
        predicate="COMPENSATION.MIN_SALARY", operator="GTE", value=value,
        strength="HARD_CONSTRAINT", value_type="MONEY",
        unknown_policy="REQUIRE_VERIFICATION",
    )


# ---------------------------------------------------------------------------
# Cross-user isolation
# ---------------------------------------------------------------------------


def test_actor_cannot_create_intent_for_other_twin(env):
    db, intent, targets, ids = env
    # actor B tries to write to twin-a
    with pytest.raises(AuthorizationDenied):
        intent.create_version(
            CreateCareerIntentVersionCommand(
                actor_id="user-b", twin_id="twin-a", idempotency_key="k1",
                expected_active_version_id=None, statements=[salary_statement()],
            ),
            actor=owner_b(),
            now=AT,
        )


def test_actor_cannot_revise_other_users_target(env):
    db, intent, targets, ids = env
    intent.create_version(
        CreateCareerIntentVersionCommand(
            actor_id="user-a", twin_id="twin-a", idempotency_key="ia",
            expected_active_version_id=None, statements=[salary_statement()],
        ),
        actor=owner_a(), now=AT,
    )
    created = targets.create_target(
        CreateSavedCareerTargetCommand(
            actor_id="user-a", twin_id="twin-a", idempotency_key="ta",
            display_name="A", role_focus=[], domain_focus=[], explicit_keywords=[],
            scope_definition={}, overrides=[],
        ),
        actor=owner_a(), now=AT,
    )
    # actor B attempts to revise A's target (claims own twin-b but target is A's)
    with pytest.raises(AuthorizationDenied):
        targets.revise_target(
            ReviseSavedCareerTargetCommand(
                actor_id="user-b", twin_id="twin-b", target_id=created.target_id,
                idempotency_key="tb", expected_active_version_id=created.target_version_id,
                display_name="hijack", role_focus=[], domain_focus=[],
                explicit_keywords=[], scope_definition={}, overrides=[],
            ),
            actor=owner_b(), now=AT,
        )


# ---------------------------------------------------------------------------
# Authority escalation
# ---------------------------------------------------------------------------


def test_ai_actor_cannot_activate_hard_intent(env):
    db, intent, targets, ids = env
    with pytest.raises(AuthorizationDenied):
        intent.create_version(
            CreateCareerIntentVersionCommand(
                actor_id="ai-1", twin_id="twin-a", idempotency_key="k1",
                expected_active_version_id=None, statements=[salary_statement()],
            ),
            actor={"actor_id": "ai-1", "twin_id": "twin-a", "is_owner": True, "actor_type": "AI"},
            now=AT,
        )


def test_system_actor_cannot_authorize_explicit_hard_exception():
    # Pure resolver-level authority check.
    with pytest.raises(HardConstraintExceptionRequired):
        resolve_target_policy(
            intent_statements=[
                IntentStatementRecord(
                    statement_id="is-1", intent_version_id="iv-1",
                    predicate="COMPENSATION.MIN_SALARY", operator=IntentOperator.GTE,
                    value=6_000_000, value_type="MONEY",
                    strength=IntentStrength.HARD_CONSTRAINT, provenance={},
                )
            ],
            target_overrides=[
                TargetIntentOverrideRecord(
                    override_id="ov-1", target_version_id="tv-1",
                    predicate="COMPENSATION.MIN_SALARY",
                    operation=OverrideOperation.EXPLICIT_EXCEPTION,
                    value=5_000_000, overrides_statement_id="is-1",
                    explicit_exception_authority="SYSTEM",
                )
            ],
            at=AT,
            exception_authority={"actor_type": "SYSTEM", "is_owner": True},
        )


def test_forged_actor_id_in_payload_does_not_bypass_authorization(env):
    db, intent, targets, ids = env
    # The command carries actor_id="user-a" but the real authorization context
    # (actor) is for twin-b and not authorized for twin-a.
    with pytest.raises(AuthorizationDenied):
        intent.create_version(
            CreateCareerIntentVersionCommand(
                actor_id="user-a", twin_id="twin-a", idempotency_key="k1",
                expected_active_version_id=None, statements=[salary_statement()],
            ),
            actor={"actor_id": "user-b", "twin_id": "twin-b", "is_owner": True, "actor_type": "USER"},
            now=AT,
        )


def test_high_confidence_ai_still_cannot_create_hard_suggestion(env):
    db, intent, targets, ids = env
    intent.create_version(
        CreateCareerIntentVersionCommand(
            actor_id="user-a", twin_id="twin-a", idempotency_key="ia",
            expected_active_version_id=None, statements=[salary_statement()],
        ),
        actor=owner_a(), now=AT,
    )
    with pytest.raises(AuthorizationDenied):
        intent.create_suggestion(
            CreateIntentSuggestionCommand(
                actor_id="ai-1", twin_id="twin-a", intent_id="intent-1",
                idempotency_key="s1", source="AI_INFERENCE",
                predicate="SHIFT.AVOID_NIGHT", operator="EQ",
                proposed_value=True, proposed_strength="HARD_CONSTRAINT",
                evidence=[], confidence=0.99,
            ),
            actor={"actor_id": "ai-1", "twin_id": "twin-a", "is_owner": True, "actor_type": "AI"},
            now=AT,
        )


# ---------------------------------------------------------------------------
# Disclosure boundary
# ---------------------------------------------------------------------------


def test_intent_statement_not_leaked_into_answer_or_profile_view():
    # Legacy profile/answer paths must not surface Career Intent statements.
    from onejob.service import OneJobService
    from onejob.repository import DemoRepository

    service = OneJobService(DemoRepository())
    profile = service.profile_view()
    # decision context (min salary intent) is not a profile disclosure field
    assert "COMPENSATION.MIN_SALARY" not in str(profile)
