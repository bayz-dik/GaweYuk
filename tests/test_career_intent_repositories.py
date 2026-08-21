from datetime import datetime, timezone

import pytest

from onejob.career_intent.models import (
    CareerIntentVersionRecord,
    IntentOperator,
    IntentStatementRecord,
    IntentStrength,
    UnknownPolicy,
)
from onejob.career_intent.repositories import CareerIntentRepository
from onejob.persistence.db import Database


AT = datetime(2026, 8, 21, 12, tzinfo=timezone.utc)


@pytest.fixture
def db(tmp_path):
    database = Database(tmp_path / "gaweyuk.db")
    database.initialize()
    return database


def make_version(**overrides):
    data = dict(
        intent_version_id="iv-1",
        intent_id="intent-1",
        version_number=1,
        supersedes_version_id=None,
        created_by_actor_id="user-1",
        created_at=AT,
        input_fingerprint="fp-1",
    )
    data.update(overrides)
    return CareerIntentVersionRecord(**data)


def make_statement(**overrides):
    data = dict(
        statement_id="is-1",
        intent_version_id="iv-1",
        predicate="COMPENSATION.MIN_SALARY",
        operator=IntentOperator.GTE,
        value=6_000_000,
        value_type="MONEY",
        strength=IntentStrength.HARD_CONSTRAINT,
        unknown_policy=UnknownPolicy.REQUIRE_VERIFICATION,
        provenance={"source": "USER_INPUT"},
    )
    data.update(overrides)
    return IntentStatementRecord(**data)


def test_intent_repository_persists_version_and_moves_active_pointer_atomically(db):
    repo = CareerIntentRepository()
    version = make_version()
    statement = make_statement()

    with db.transaction() as conn:
        repo.create_intent(
            conn,
            twin_id="twin-1",
            actor_id="user-1",
            intent_id="intent-1",
        )
        repo.append_version(conn, version=version, statements=[statement])
        repo.move_active_pointer(
            conn,
            intent_id="intent-1",
            expected_active_version_id=None,
            new_active_version_id="iv-1",
        )

    with db.connection() as conn:
        assert repo.get(conn, "intent-1").active_version_id == "iv-1"
        assert repo.get_version(conn, "iv-1") == version
        statements = repo.get_statements(conn, "iv-1")
        assert len(statements) == 1
        assert statements[0].predicate == "COMPENSATION.MIN_SALARY"
        assert statements[0].strength is IntentStrength.HARD_CONSTRAINT


def test_second_version_does_not_mutate_first_row(db):
    repo = CareerIntentRepository()

    with db.transaction() as conn:
        repo.create_intent(
            conn, twin_id="twin-1", actor_id="user-1", intent_id="intent-1"
        )
        repo.append_version(conn, version=make_version(), statements=[make_statement()])
        repo.move_active_pointer(
            conn,
            intent_id="intent-1",
            expected_active_version_id=None,
            new_active_version_id="iv-1",
        )

    v2 = make_version(
        intent_version_id="iv-2",
        version_number=2,
        supersedes_version_id="iv-1",
        input_fingerprint="fp-2",
    )
    with db.transaction() as conn:
        repo.append_version(
            conn,
            version=v2,
            statements=[make_statement(statement_id="is-2", intent_version_id="iv-2", value=7_000_000)],
        )
        repo.move_active_pointer(
            conn,
            intent_id="intent-1",
            expected_active_version_id="iv-1",
            new_active_version_id="iv-2",
        )

    with db.connection() as conn:
        # v1 unchanged
        assert repo.get_version(conn, "iv-1") == make_version()
        assert repo.get(conn, "intent-1").active_version_id == "iv-2"


def test_move_active_pointer_rejects_stale_expected_version(db):
    repo = CareerIntentRepository()

    with db.transaction() as conn:
        repo.create_intent(
            conn, twin_id="twin-1", actor_id="user-1", intent_id="intent-1"
        )
        repo.append_version(conn, version=make_version(), statements=[make_statement()])
        repo.move_active_pointer(
            conn,
            intent_id="intent-1",
            expected_active_version_id=None,
            new_active_version_id="iv-1",
        )

    # Stale expected pointer (still None) must be rejected, not overwrite.
    with pytest.raises(Exception):
        with db.transaction() as conn:
            repo.move_active_pointer(
                conn,
                intent_id="intent-1",
                expected_active_version_id=None,
                new_active_version_id="iv-1",
            )


def test_get_active_intent_for_twin(db):
    repo = CareerIntentRepository()

    with db.transaction() as conn:
        repo.create_intent(
            conn, twin_id="twin-1", actor_id="user-1", intent_id="intent-1"
        )
        repo.append_version(conn, version=make_version(), statements=[make_statement()])
        repo.move_active_pointer(
            conn,
            intent_id="intent-1",
            expected_active_version_id=None,
            new_active_version_id="iv-1",
        )

    with db.connection() as conn:
        intent = repo.get_for_twin(conn, "twin-1")
        assert intent is not None
        assert intent.intent_id == "intent-1"
        assert intent.active_version_id == "iv-1"
