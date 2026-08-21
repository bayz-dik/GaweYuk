from datetime import datetime, timezone

import pytest

from onejob.career_context.models import (
    ResolvedScope,
    ResolvedTargetViewRecord,
)
from onejob.career_context.repositories import CareerContextRepository
from onejob.persistence.db import Database


AT = datetime(2026, 8, 21, 12, tzinfo=timezone.utc)


@pytest.fixture
def db(tmp_path):
    database = Database(tmp_path / "gaweyuk.db")
    database.initialize()
    return database


def make_view(**overrides):
    data = dict(
        resolved_view_id="rv-1",
        twin_id="twin-1",
        intent_version_id="iv-1",
        target_version_id="tv-1",
        routing_decision_id="route-1",
        scope=ResolvedScope.TARGETED,
        resolved_statements=[],
        applied_overrides=[],
        explicit_exceptions=[],
        active_temporal_statements=[],
        tensions=[],
        validation_status="VALID",
        resolver_version="resolver-v1",
        evaluated_at=AT,
        input_fingerprint="same-fp",
    )
    data.update(overrides)
    return ResolvedTargetViewRecord(**data)


def test_resolved_view_is_reused_by_twin_and_fingerprint(db):
    repo = CareerContextRepository()
    first_input = make_view()
    second_input = first_input.model_copy(update={"resolved_view_id": "rv-2"})

    with db.transaction() as conn:
        first = repo.get_or_create_resolved_view(conn, view=first_input)
        second = repo.get_or_create_resolved_view(conn, view=second_input)

    assert second.resolved_view_id == first.resolved_view_id


def test_distinct_fingerprint_creates_new_view(db):
    repo = CareerContextRepository()

    with db.transaction() as conn:
        first = repo.get_or_create_resolved_view(conn, view=make_view())
        second = repo.get_or_create_resolved_view(
            conn,
            view=make_view(
                resolved_view_id="rv-2", input_fingerprint="different-fp"
            ),
        )

    assert first.resolved_view_id != second.resolved_view_id


def test_get_resolved_view_by_id_is_ownership_scoped(db):
    repo = CareerContextRepository()

    with db.transaction() as conn:
        repo.get_or_create_resolved_view(conn, view=make_view())

    with db.connection() as conn:
        assert repo.get_resolved_view(conn, "rv-1", twin_id="twin-1") is not None
        assert repo.get_resolved_view(conn, "rv-1", twin_id="twin-2") is None


def test_view_roundtrip_preserves_scope_and_versions(db):
    repo = CareerContextRepository()

    with db.transaction() as conn:
        repo.get_or_create_resolved_view(
            conn,
            view=make_view(
                scope=ResolvedScope.UNSCOPED,
                target_version_id=None,
                routing_decision_id=None,
                input_fingerprint="unscoped-fp",
            ),
        )

    with db.connection() as conn:
        loaded = repo.get_resolved_view(conn, "rv-1", twin_id="twin-1")
        assert loaded.scope is ResolvedScope.UNSCOPED
        assert loaded.target_version_id is None
        assert loaded.intent_version_id == "iv-1"
