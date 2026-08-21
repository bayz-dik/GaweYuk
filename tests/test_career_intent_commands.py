from datetime import datetime, timezone

import pytest

from onejob.career_intent.commands import (
    CareerIntentCommandService,
    CreateCareerIntentVersionCommand,
    NewIntentStatement,
)
from onejob.career_intent.repositories import CareerIntentRepository
from onejob.career_twin.errors import (
    AuthorizationDenied,
    IdempotencyConflict,
)
from onejob.career_twin.repositories import CareerTwinRepository
from onejob.career_twin.ontology import ONTOLOGY_VERSION
from onejob.persistence.db import Database


AT = datetime(2026, 8, 21, 12, tzinfo=timezone.utc)


class SequentialIds:
    def __init__(self):
        self.counts = {}

    def __call__(self, kind: str) -> str:
        n = self.counts.get(kind, 0) + 1
        self.counts[kind] = n
        return f"{kind}-{n}"


def make_db(tmp_path) -> Database:
    db = Database(tmp_path / "gaweyuk.db")
    db.initialize()
    with db.transaction() as conn:
        CareerTwinRepository().ensure_twin(
            conn, "twin-1", "user-1", ONTOLOGY_VERSION
        )
    return db


def owner():
    return {"actor_id": "user-1", "twin_id": "twin-1", "is_owner": True, "actor_type": "USER"}


def min_salary_statement(value=6_000_000, strength="HARD_CONSTRAINT"):
    return NewIntentStatement(
        predicate="COMPENSATION.MIN_SALARY",
        operator="GTE",
        value=value,
        strength=strength,
        value_type="MONEY",
        unknown_policy="REQUIRE_VERIFICATION",
    )


def test_create_first_version_activates_and_writes_event_outbox(tmp_path):
    db = make_db(tmp_path)
    service = CareerIntentCommandService(db, id_factory=SequentialIds())

    result = service.create_version(
        CreateCareerIntentVersionCommand(
            actor_id="user-1",
            twin_id="twin-1",
            idempotency_key="intent-create-1",
            expected_active_version_id=None,
            statements=[min_salary_statement()],
        ),
        actor=owner(),
        now=AT,
    )

    repo = CareerIntentRepository()
    with db.connection() as conn:
        intent = repo.get(conn, result.intent_id)
        assert intent.active_version_id == result.intent_version_id
        version = repo.get_version(conn, result.intent_version_id)
        assert version.version_number == 1
        events = conn.execute(
            "SELECT event_type FROM career_events WHERE twin_id = ? ORDER BY event_id",
            ("twin-1",),
        ).fetchall()
        outbox = conn.execute(
            "SELECT COUNT(*) AS n FROM career_event_outbox"
        ).fetchone()["n"]

    event_types = {e["event_type"] for e in events}
    assert "CareerIntentVersionCreated" in event_types
    assert "CareerIntentActivated" in event_types
    assert outbox >= 2
    # safe result exposes IDs/version, not raw rows
    assert result.version_number == 1


def test_second_version_with_correct_expected_active_succeeds(tmp_path):
    db = make_db(tmp_path)
    service = CareerIntentCommandService(db, id_factory=SequentialIds())

    first = service.create_version(
        CreateCareerIntentVersionCommand(
            actor_id="user-1",
            twin_id="twin-1",
            idempotency_key="k1",
            expected_active_version_id=None,
            statements=[min_salary_statement(6_000_000)],
        ),
        actor=owner(),
        now=AT,
    )
    second = service.create_version(
        CreateCareerIntentVersionCommand(
            actor_id="user-1",
            twin_id="twin-1",
            idempotency_key="k2",
            expected_active_version_id=first.intent_version_id,
            statements=[min_salary_statement(7_000_000)],
        ),
        actor=owner(),
        now=AT,
    )
    assert second.version_number == 2

    with db.connection() as conn:
        intent = CareerIntentRepository().get(conn, first.intent_id)
        assert intent.active_version_id == second.intent_version_id


def test_stale_expected_active_version_raises(tmp_path):
    from onejob.career_intent.commands import StaleIntentVersion

    db = make_db(tmp_path)
    service = CareerIntentCommandService(db, id_factory=SequentialIds())

    first = service.create_version(
        CreateCareerIntentVersionCommand(
            actor_id="user-1",
            twin_id="twin-1",
            idempotency_key="k1",
            expected_active_version_id=None,
            statements=[min_salary_statement(6_000_000)],
        ),
        actor=owner(),
        now=AT,
    )
    service.create_version(
        CreateCareerIntentVersionCommand(
            actor_id="user-1",
            twin_id="twin-1",
            idempotency_key="k2",
            expected_active_version_id=first.intent_version_id,
            statements=[min_salary_statement(7_000_000)],
        ),
        actor=owner(),
        now=AT,
    )
    # Still expecting v1 after v2 exists.
    with pytest.raises(StaleIntentVersion):
        service.create_version(
            CreateCareerIntentVersionCommand(
                actor_id="user-1",
                twin_id="twin-1",
                idempotency_key="k3",
                expected_active_version_id=first.intent_version_id,
                statements=[min_salary_statement(8_000_000)],
            ),
            actor=owner(),
            now=AT,
        )


def test_unsatisfiable_intent_rejected_before_activation(tmp_path):
    from onejob.career_intent.commands import UnsatisfiableIntent

    db = make_db(tmp_path)
    service = CareerIntentCommandService(db, id_factory=SequentialIds())

    with pytest.raises(UnsatisfiableIntent):
        service.create_version(
            CreateCareerIntentVersionCommand(
                actor_id="user-1",
                twin_id="twin-1",
                idempotency_key="k1",
                expected_active_version_id=None,
                statements=[
                    NewIntentStatement(
                        predicate="COMPENSATION.MIN_SALARY",
                        operator="GTE",
                        value=7_000_000,
                        strength="HARD_CONSTRAINT",
                        value_type="MONEY",
                    ),
                    NewIntentStatement(
                        predicate="COMPENSATION.MAX_SALARY",
                        operator="LTE",
                        value=6_000_000,
                        strength="HARD_CONSTRAINT",
                        value_type="MONEY",
                    ),
                ],
            ),
            actor=owner(),
            now=AT,
        )

    # No orphan active version/event should exist.
    with db.connection() as conn:
        n_versions = conn.execute(
            "SELECT COUNT(*) AS n FROM career_intent_versions"
        ).fetchone()["n"]
        n_events = conn.execute(
            "SELECT COUNT(*) AS n FROM career_events WHERE twin_id = 'twin-1'"
        ).fetchone()["n"]
    assert n_versions == 0
    assert n_events == 0


def test_idempotent_retry_same_payload_returns_same_result(tmp_path):
    db = make_db(tmp_path)
    service = CareerIntentCommandService(db, id_factory=SequentialIds())

    cmd = CreateCareerIntentVersionCommand(
        actor_id="user-1",
        twin_id="twin-1",
        idempotency_key="k1",
        expected_active_version_id=None,
        statements=[min_salary_statement(6_000_000)],
    )
    first = service.create_version(cmd, actor=owner(), now=AT)
    second = service.create_version(cmd, actor=owner(), now=AT)
    assert first.intent_version_id == second.intent_version_id

    with db.connection() as conn:
        n = conn.execute(
            "SELECT COUNT(*) AS n FROM career_intent_versions"
        ).fetchone()["n"]
    assert n == 1


def test_idempotency_conflict_on_different_payload(tmp_path):
    db = make_db(tmp_path)
    service = CareerIntentCommandService(db, id_factory=SequentialIds())

    service.create_version(
        CreateCareerIntentVersionCommand(
            actor_id="user-1",
            twin_id="twin-1",
            idempotency_key="shared",
            expected_active_version_id=None,
            statements=[min_salary_statement(6_000_000)],
        ),
        actor=owner(),
        now=AT,
    )
    with pytest.raises(IdempotencyConflict):
        service.create_version(
            CreateCareerIntentVersionCommand(
                actor_id="user-1",
                twin_id="twin-1",
                idempotency_key="shared",
                expected_active_version_id=None,
                statements=[min_salary_statement(9_000_000)],
            ),
            actor=owner(),
            now=AT,
        )


def test_unauthorized_actor_cannot_create_intent(tmp_path):
    db = make_db(tmp_path)
    service = CareerIntentCommandService(db, id_factory=SequentialIds())

    with pytest.raises(AuthorizationDenied):
        service.create_version(
            CreateCareerIntentVersionCommand(
                actor_id="attacker",
                twin_id="twin-1",
                idempotency_key="k1",
                expected_active_version_id=None,
                statements=[min_salary_statement()],
            ),
            actor={"actor_id": "attacker", "twin_id": "twin-2", "is_owner": True},
            now=AT,
        )


def test_ai_actor_cannot_activate_hard_constraint(tmp_path):
    db = make_db(tmp_path)
    service = CareerIntentCommandService(db, id_factory=SequentialIds())

    with pytest.raises(AuthorizationDenied):
        service.create_version(
            CreateCareerIntentVersionCommand(
                actor_id="ai-1",
                twin_id="twin-1",
                idempotency_key="k1",
                expected_active_version_id=None,
                statements=[min_salary_statement()],
            ),
            actor={
                "actor_id": "ai-1",
                "twin_id": "twin-1",
                "is_owner": True,
                "actor_type": "AI",
            },
            now=AT,
        )
