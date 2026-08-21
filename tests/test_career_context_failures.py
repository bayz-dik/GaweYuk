from datetime import datetime, timezone

import pytest

from onejob.career_context.service import (
    CareerContextService,
    ContextResolutionFailed,
)
from onejob.career_intent.commands import (
    CareerIntentCommandService,
    CreateCareerIntentVersionCommand,
    NewIntentStatement,
)
from onejob.career_intent.repositories import CareerIntentRepository
from onejob.career_targets.commands import (
    CreateSavedCareerTargetCommand,
    TargetCommandService,
)
from onejob.career_targets.compatibility import TargetCompatibilityService
from onejob.career_targets.repositories import SavedCareerTargetRepository
from onejob.career_targets.routing import TargetRoutingService
from onejob.career_twin.ontology import ONTOLOGY_VERSION
from onejob.career_twin.repositories import CareerTwinRepository
from onejob.models import CanonicalJob
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


def make_db(tmp_path):
    db = Database(tmp_path / "gaweyuk.db")
    db.initialize()
    with db.transaction() as conn:
        CareerTwinRepository().ensure_twin(conn, "twin-1", "user-1", ONTOLOGY_VERSION)
    return db


def salary_statement(value=6_000_000):
    return NewIntentStatement(
        predicate="COMPENSATION.MIN_SALARY", operator="GTE", value=value,
        strength="HARD_CONSTRAINT", value_type="MONEY",
        unknown_policy="REQUIRE_VERIFICATION",
    )


def job():
    return CanonicalJob(
        id="job-1", title="Op", company="X", location="Bekasi", description="d",
        normalized_title="warehouse operator", normalized_company="x",
        normalized_location="bekasi", skills=["forklift"], salary_min=7_000_000,
    )


# ---------------------------------------------------------------------------
# Intent command atomicity
# ---------------------------------------------------------------------------


def test_failure_before_outbox_rolls_back_intent_version(tmp_path):
    db = make_db(tmp_path)
    service = CareerIntentCommandService(db, id_factory=SequentialIds())

    # Force the event/outbox append to fail during the command.
    original = service.events.append_with_outbox

    calls = {"n": 0}

    def boom(conn, event):
        calls["n"] += 1
        raise RuntimeError("injected outbox failure")

    service.events.append_with_outbox = boom

    with pytest.raises(RuntimeError):
        service.create_version(
            CreateCareerIntentVersionCommand(
                actor_id="user-1", twin_id="twin-1", idempotency_key="k1",
                expected_active_version_id=None, statements=[salary_statement()],
            ),
            actor=owner(), now=AT,
        )

    service.events.append_with_outbox = original

    with db.connection() as conn:
        n_versions = conn.execute(
            "SELECT COUNT(*) AS n FROM career_intent_versions"
        ).fetchone()["n"]
        n_events = conn.execute(
            "SELECT COUNT(*) AS n FROM career_events"
        ).fetchone()["n"]
        n_idem = conn.execute(
            "SELECT COUNT(*) AS n FROM career_idempotency_keys"
        ).fetchone()["n"]
        intent = CareerIntentRepository().get_for_twin(conn, "twin-1")

    assert n_versions == 0
    assert n_events == 0
    assert n_idem == 0
    # no active pointer created
    assert intent is None or intent.active_version_id is None


def test_target_version_rollback_leaves_previous_active(tmp_path):
    db = make_db(tmp_path)
    ids = SequentialIds()
    intent = CareerIntentCommandService(db, id_factory=ids)
    targets = TargetCommandService(db, id_factory=ids)
    intent.create_version(
        CreateCareerIntentVersionCommand(
            actor_id="user-1", twin_id="twin-1", idempotency_key="i1",
            expected_active_version_id=None, statements=[salary_statement()],
        ),
        actor=owner(), now=AT,
    )
    created = targets.create_target(
        CreateSavedCareerTargetCommand(
            actor_id="user-1", twin_id="twin-1", idempotency_key="t1",
            display_name="A", role_focus=[], domain_focus=[], explicit_keywords=[],
            scope_definition={}, overrides=[],
        ),
        actor=owner(), now=AT,
    )

    # Inject failure into the event append during revise.
    def boom(conn, event):
        raise RuntimeError("injected failure before pointer commit")

    targets.events.append_with_outbox = boom

    with pytest.raises(RuntimeError):
        targets.revise_target(
            __import__("onejob.career_targets.commands", fromlist=["ReviseSavedCareerTargetCommand"]).ReviseSavedCareerTargetCommand(
                actor_id="user-1", twin_id="twin-1", target_id=created.target_id,
                idempotency_key="t2", expected_active_version_id=created.target_version_id,
                display_name="B", role_focus=[], domain_focus=[], explicit_keywords=[],
                scope_definition={}, overrides=[],
            ),
            actor=owner(), now=AT,
        )

    with db.connection() as conn:
        target = SavedCareerTargetRepository().get(conn, created.target_id)
        n_versions = conn.execute(
            "SELECT COUNT(*) AS n FROM saved_career_target_versions WHERE target_id = ?",
            (created.target_id,),
        ).fetchone()["n"]

    # previous version still active; the failed revision did not persist
    assert target.active_version_id == created.target_version_id
    assert n_versions == 1


# ---------------------------------------------------------------------------
# Context materialization failure classification
# ---------------------------------------------------------------------------


def test_snapshot_materialization_failure_is_technical_not_domain(tmp_path):
    db = make_db(tmp_path)
    ids = SequentialIds()
    intent = CareerIntentCommandService(db, id_factory=ids)
    targets = TargetCommandService(db, id_factory=ids)
    compat = TargetCompatibilityService(db, id_factory=ids)
    routing = TargetRoutingService(db, id_factory=ids)
    service = CareerContextService(
        db, id_factory=ids, intent_service=intent, target_service=targets,
        compatibility_service=compat, routing_service=routing,
    )
    intent.create_version(
        CreateCareerIntentVersionCommand(
            actor_id="user-1", twin_id="twin-1", idempotency_key="i1",
            expected_active_version_id=None, statements=[salary_statement()],
        ),
        actor=owner(), now=AT,
    )

    outcome = service.resolve(twin_id="twin-1", job=job(), evaluated_at=AT)

    # Force snapshot persistence to fail.
    def boom(conn, *, view):
        raise RuntimeError("db write failed")

    service.repo.get_or_create_resolved_view = boom

    with pytest.raises(ContextResolutionFailed):
        service.materialize(outcome)


def test_resolver_crash_is_context_resolution_failed_not_unscoped(tmp_path):
    db = make_db(tmp_path)
    ids = SequentialIds()
    intent = CareerIntentCommandService(db, id_factory=ids)
    targets = TargetCommandService(db, id_factory=ids)
    compat = TargetCompatibilityService(db, id_factory=ids)
    routing = TargetRoutingService(db, id_factory=ids)
    service = CareerContextService(
        db, id_factory=ids, intent_service=intent, target_service=targets,
        compatibility_service=compat, routing_service=routing,
    )
    intent.create_version(
        CreateCareerIntentVersionCommand(
            actor_id="user-1", twin_id="twin-1", idempotency_key="i1",
            expected_active_version_id=None, statements=[salary_statement()],
        ),
        actor=owner(), now=AT,
    )

    def boom(**kwargs):
        raise RuntimeError("router crashed")

    routing.route = boom

    with pytest.raises(ContextResolutionFailed):
        service.resolve(twin_id="twin-1", job=job(), evaluated_at=AT)
