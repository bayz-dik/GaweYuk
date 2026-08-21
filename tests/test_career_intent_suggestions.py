from datetime import datetime, timezone

import pytest

from onejob.career_intent.commands import (
    AcceptIntentSuggestionCommand,
    CareerIntentCommandService,
    CreateCareerIntentVersionCommand,
    CreateIntentSuggestionCommand,
    EditAndAcceptIntentSuggestionCommand,
    NewIntentStatement,
    RejectIntentSuggestionCommand,
)
from onejob.career_intent.repositories import CareerIntentRepository
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


def owner():
    return {"actor_id": "user-1", "twin_id": "twin-1", "is_owner": True, "actor_type": "USER"}


def system_actor():
    return {"actor_id": "sys-1", "twin_id": "twin-1", "is_owner": True, "actor_type": "SYSTEM"}


@pytest.fixture
def env(tmp_path):
    db = Database(tmp_path / "gaweyuk.db")
    db.initialize()
    with db.transaction() as conn:
        CareerTwinRepository().ensure_twin(conn, "twin-1", "user-1", ONTOLOGY_VERSION)
    ids = SequentialIds()
    service = CareerIntentCommandService(db, id_factory=ids)
    # seed an initial intent version
    first = service.create_version(
        CreateCareerIntentVersionCommand(
            actor_id="user-1",
            twin_id="twin-1",
            idempotency_key="seed",
            expected_active_version_id=None,
            statements=[
                NewIntentStatement(
                    predicate="COMPENSATION.MIN_SALARY",
                    operator="GTE",
                    value=6_000_000,
                    strength="HARD_CONSTRAINT",
                    value_type="MONEY",
                    unknown_policy="REQUIRE_VERIFICATION",
                )
            ],
        ),
        actor=owner(),
        now=AT,
    )
    return db, service, ids, first


def make_suggestion(service, *, source="AI_INFERENCE", predicate="SHIFT.AVOID_NIGHT",
                    value=True, strength="SOFT_PREFERENCE", key="suggest-1", intent_id="intent-1"):
    return service.create_suggestion(
        CreateIntentSuggestionCommand(
            actor_id="system-1",
            twin_id="twin-1",
            intent_id=intent_id,
            idempotency_key=key,
            source=source,
            predicate=predicate,
            operator="EQ",
            proposed_value=value,
            proposed_strength=strength,
            evidence=[{"kind": "behavior", "count": 5}],
        ),
        actor=system_actor(),
        now=AT,
    )


def test_ai_suggestion_does_not_change_active_intent(env):
    db, service, ids, first = env
    suggestion = make_suggestion(service, intent_id=first.intent_id)

    with db.connection() as conn:
        assert (
            CareerIntentRepository().get(conn, first.intent_id).active_version_id
            == first.intent_version_id
        )
    assert suggestion.decision_state == "PENDING"


def test_accept_suggestion_creates_new_immutable_version(env):
    db, service, ids, first = env
    suggestion = make_suggestion(service, intent_id=first.intent_id)

    result = service.accept_suggestion(
        AcceptIntentSuggestionCommand(
            actor_id="user-1",
            twin_id="twin-1",
            suggestion_id=suggestion.suggestion_id,
            idempotency_key="accept-1",
            expected_active_version_id=first.intent_version_id,
        ),
        actor=owner(),
        now=AT,
    )
    assert result.version_number == 2

    with db.connection() as conn:
        repo = CareerIntentRepository()
        assert repo.get(conn, first.intent_id).active_version_id == result.intent_version_id
        # new version includes prior + accepted statement
        statements = repo.get_statements(conn, result.intent_version_id)
        predicates = {s.predicate for s in statements}
        assert "COMPENSATION.MIN_SALARY" in predicates
        assert "SHIFT.AVOID_NIGHT" in predicates
        sug = repo.get_suggestion(conn, suggestion.suggestion_id)
        assert sug["decision_state"] == "ACCEPTED"


def test_edit_and_accept_uses_user_value_and_can_promote_to_hard(env):
    db, service, ids, first = env
    suggestion = make_suggestion(service, intent_id=first.intent_id, strength="SOFT_PREFERENCE")

    result = service.edit_and_accept_suggestion(
        EditAndAcceptIntentSuggestionCommand(
            actor_id="user-1",
            twin_id="twin-1",
            suggestion_id=suggestion.suggestion_id,
            idempotency_key="edit-1",
            expected_active_version_id=first.intent_version_id,
            edited_value=True,
            edited_strength="HARD_CONSTRAINT",
        ),
        actor=owner(),
        now=AT,
    )

    with db.connection() as conn:
        statements = CareerIntentRepository().get_statements(conn, result.intent_version_id)
        shift = [s for s in statements if s.predicate == "SHIFT.AVOID_NIGHT"][0]
        assert shift.strength.value == "HARD_CONSTRAINT"


def test_reject_does_not_change_intent(env):
    db, service, ids, first = env
    suggestion = make_suggestion(service, intent_id=first.intent_id)

    service.reject_suggestion(
        RejectIntentSuggestionCommand(
            actor_id="user-1",
            twin_id="twin-1",
            suggestion_id=suggestion.suggestion_id,
            idempotency_key="reject-1",
            suppress=False,
        ),
        actor=owner(),
        now=AT,
    )

    with db.connection() as conn:
        repo = CareerIntentRepository()
        assert repo.get(conn, first.intent_id).active_version_id == first.intent_version_id
        assert repo.get_suggestion(conn, suggestion.suggestion_id)["decision_state"] == "REJECTED"


def test_rejected_suggestion_can_be_suppressed_separately_from_history(env):
    db, service, ids, first = env
    suggestion = make_suggestion(service, intent_id=first.intent_id)

    service.reject_suggestion(
        RejectIntentSuggestionCommand(
            actor_id="user-1",
            twin_id="twin-1",
            suggestion_id=suggestion.suggestion_id,
            idempotency_key="reject-1",
            suppress=True,
        ),
        actor=owner(),
        now=AT,
    )

    with db.connection() as conn:
        repo = CareerIntentRepository()
        assert repo.active_suppression(
            conn, first.intent_id, suggestion.fingerprint
        ) is True
        # intent history not altered
        assert repo.get(conn, first.intent_id).active_version_id == first.intent_version_id


def test_ai_actor_cannot_accept_suggestion_to_hard(env):
    db, service, ids, first = env
    suggestion = make_suggestion(service, intent_id=first.intent_id)

    with pytest.raises(AuthorizationDenied):
        service.accept_suggestion(
            AcceptIntentSuggestionCommand(
                actor_id="ai-1",
                twin_id="twin-1",
                suggestion_id=suggestion.suggestion_id,
                idempotency_key="accept-1",
                expected_active_version_id=first.intent_version_id,
            ),
            actor={"actor_id": "ai-1", "twin_id": "twin-1", "is_owner": True, "actor_type": "AI"},
            now=AT,
        )


def test_inference_cannot_directly_create_hard_suggestion(env):
    db, service, ids, first = env
    # An AI source proposing HARD strength must be rejected at suggestion time.
    with pytest.raises(Exception):
        make_suggestion(
            service, intent_id=first.intent_id, strength="HARD_CONSTRAINT", key="s-hard"
        )


def test_suggestion_fingerprint_is_stable_across_calls(env):
    db, service, ids, first = env
    s1 = make_suggestion(service, intent_id=first.intent_id, key="a")
    # same semantic proposal → same fingerprint
    s2_service = CareerIntentCommandService(db, id_factory=SequentialIds())
    # recompute fingerprint via helper
    from onejob.career_intent.commands import intent_suggestion_fingerprint

    fp = intent_suggestion_fingerprint(
        intent_id=first.intent_id,
        predicate="SHIFT.AVOID_NIGHT",
        proposed_value=True,
        proposed_strength="SOFT_PREFERENCE",
        source="AI_INFERENCE",
    )
    assert s1.fingerprint == fp
