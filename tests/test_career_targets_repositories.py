from datetime import datetime, timezone

import pytest

from onejob.career_targets.models import (
    OverrideOperation,
    SavedCareerTargetRecord,
    SavedCareerTargetVersionRecord,
    TargetCompatibilityRecord,
    TargetCompatibilityStatus,
    TargetIntentOverrideRecord,
    TargetLifecycle,
)
from onejob.career_targets.repositories import SavedCareerTargetRepository
from onejob.persistence.db import Database


AT = datetime(2026, 8, 21, 12, tzinfo=timezone.utc)


@pytest.fixture
def db(tmp_path):
    database = Database(tmp_path / "gaweyuk.db")
    database.initialize()
    return database


def make_target(**overrides):
    data = dict(
        target_id="target-1",
        twin_id="twin-1",
        active_version_id=None,
        lifecycle=TargetLifecycle.ACTIVE,
        created_at=AT,
        created_by_actor_id="user-1",
    )
    data.update(overrides)
    return SavedCareerTargetRecord(**data)


def make_version(**overrides):
    data = dict(
        target_version_id="tv-1",
        target_id="target-1",
        version_number=1,
        supersedes_version_id=None,
        display_name="Warehouse Operator",
        role_focus=["operator"],
        domain_focus=["logistics"],
        explicit_keywords=["forklift"],
        scope_definition={"region": "Bekasi"},
        created_at=AT,
        input_fingerprint="tfp-1",
    )
    data.update(overrides)
    return SavedCareerTargetVersionRecord(**data)


def test_target_identity_and_version_persistence(db):
    repo = SavedCareerTargetRepository()

    with db.transaction() as conn:
        repo.create_target(conn, target=make_target())
        repo.append_version(conn, version=make_version(), overrides=[])
        repo.move_active_pointer(
            conn,
            target_id="target-1",
            expected_active_version_id=None,
            new_active_version_id="tv-1",
        )

    with db.connection() as conn:
        target = repo.get(conn, "target-1")
        assert target.active_version_id == "tv-1"
        assert target.lifecycle is TargetLifecycle.ACTIVE
        assert repo.get_version(conn, "tv-1") == make_version()


def test_target_ownership_scoping(db):
    repo = SavedCareerTargetRepository()

    with db.transaction() as conn:
        repo.create_target(conn, target=make_target())

    with db.connection() as conn:
        # Wrong twin sees nothing (access-safe).
        assert repo.get_owned(conn, target_id="target-1", twin_id="twin-2") is None
        assert repo.get_owned(conn, target_id="target-1", twin_id="twin-1") is not None


def test_overrides_belong_to_target_version(db):
    repo = SavedCareerTargetRepository()
    override = TargetIntentOverrideRecord(
        override_id="ov-1",
        target_version_id="tv-1",
        predicate="COMPENSATION.MIN_SALARY",
        operation=OverrideOperation.REPLACE,
        value=7_000_000,
        strength=None,
        overrides_statement_id="is-1",
        explicit_exception_authority=None,
    )

    with db.transaction() as conn:
        repo.create_target(conn, target=make_target())
        repo.append_version(conn, version=make_version(), overrides=[override])

    with db.connection() as conn:
        loaded = repo.get_overrides(conn, "tv-1")
        assert len(loaded) == 1
        assert loaded[0].operation is OverrideOperation.REPLACE
        assert loaded[0].value == 7_000_000


def test_lifecycle_transition_with_expected_state(db):
    repo = SavedCareerTargetRepository()

    with db.transaction() as conn:
        repo.create_target(conn, target=make_target())

    with db.transaction() as conn:
        repo.set_lifecycle(
            conn,
            target_id="target-1",
            expected_lifecycle=TargetLifecycle.ACTIVE,
            new_lifecycle=TargetLifecycle.PAUSED,
        )

    with db.connection() as conn:
        assert repo.get(conn, "target-1").lifecycle is TargetLifecycle.PAUSED

    # stale expected lifecycle is rejected
    with pytest.raises(Exception):
        with db.transaction() as conn:
            repo.set_lifecycle(
                conn,
                target_id="target-1",
                expected_lifecycle=TargetLifecycle.ACTIVE,
                new_lifecycle=TargetLifecycle.ARCHIVED,
            )


def test_compatibility_keyed_to_exact_versions(db):
    repo = SavedCareerTargetRepository()
    record = TargetCompatibilityRecord(
        compatibility_id="cmp-1",
        target_id="target-1",
        target_version_id="tv-1",
        against_intent_version_id="iv-1",
        status=TargetCompatibilityStatus.VALID,
        reasons=["resolvable"],
        checked_at=AT,
        validator_version="target-compat-v1",
    )

    with db.transaction() as conn:
        repo.create_target(conn, target=make_target())
        repo.append_version(conn, version=make_version(), overrides=[])
        repo.save_compatibility(conn, record=record)

    with db.connection() as conn:
        latest = repo.latest_compatibility(
            conn, target_version_id="tv-1", against_intent_version_id="iv-1"
        )
        assert latest.status is TargetCompatibilityStatus.VALID
        # No assessment for a different intent version.
        assert (
            repo.latest_compatibility(
                conn, target_version_id="tv-1", against_intent_version_id="iv-2"
            )
            is None
        )


def test_list_owned_targets(db):
    repo = SavedCareerTargetRepository()

    with db.transaction() as conn:
        repo.create_target(conn, target=make_target())
        repo.create_target(
            conn, target=make_target(target_id="target-2")
        )
        repo.create_target(
            conn, target=make_target(target_id="target-3", twin_id="twin-2")
        )

    with db.connection() as conn:
        owned = repo.list_for_twin(conn, "twin-1")
        assert {t.target_id for t in owned} == {"target-1", "target-2"}


# ---------------------------------------------------------------------------
# Task 5: Target command service
# ---------------------------------------------------------------------------

from onejob.career_targets.commands import (
    CreateSavedCareerTargetCommand,
    ReviseSavedCareerTargetCommand,
    SetTargetLifecycleCommand,
    TargetCommandService,
    NewTargetOverride,
)
from onejob.career_twin.errors import AuthorizationDenied
from onejob.career_twin.repositories import CareerTwinRepository
from onejob.career_twin.ontology import ONTOLOGY_VERSION


class SequentialIds:
    def __init__(self):
        self.counts = {}

    def __call__(self, kind: str) -> str:
        n = self.counts.get(kind, 0) + 1
        self.counts[kind] = n
        return f"{kind}-{n}"


def command_db(tmp_path):
    database = Database(tmp_path / "gaweyuk.db")
    database.initialize()
    with database.transaction() as conn:
        CareerTwinRepository().ensure_twin(
            conn, "twin-1", "user-1", ONTOLOGY_VERSION
        )
    return database


def owner():
    return {"actor_id": "user-1", "twin_id": "twin-1", "is_owner": True, "actor_type": "USER"}


def make_create(**overrides):
    data = dict(
        actor_id="user-1",
        twin_id="twin-1",
        idempotency_key="tc-1",
        display_name="Warehouse Operator",
        role_focus=["operator"],
        domain_focus=["logistics"],
        explicit_keywords=["forklift"],
        scope_definition={"region": "Bekasi"},
        overrides=[],
    )
    data.update(overrides)
    return CreateSavedCareerTargetCommand(**data)


def test_create_target_produces_version_1(tmp_path):
    db = command_db(tmp_path)
    service = TargetCommandService(db, id_factory=SequentialIds())

    result = service.create_target(make_create(), actor=owner(), now=AT)

    with db.connection() as conn:
        target = SavedCareerTargetRepository().get(conn, result.target_id)
        assert target.active_version_id == result.target_version_id
        version = SavedCareerTargetRepository().get_version(
            conn, result.target_version_id
        )
        assert version.version_number == 1


def test_revise_target_creates_version_2_without_mutating_v1(tmp_path):
    db = command_db(tmp_path)
    service = TargetCommandService(db, id_factory=SequentialIds())
    created = service.create_target(make_create(), actor=owner(), now=AT)

    revised = service.revise_target(
        ReviseSavedCareerTargetCommand(
            actor_id="user-1",
            twin_id="twin-1",
            target_id=created.target_id,
            idempotency_key="tc-2",
            expected_active_version_id=created.target_version_id,
            display_name="Warehouse Lead",
            role_focus=["lead"],
            domain_focus=["logistics"],
            explicit_keywords=["forklift", "team"],
            scope_definition={"region": "Bekasi"},
            overrides=[],
        ),
        actor=owner(),
        now=AT,
    )
    assert revised.version_number == 2

    with db.connection() as conn:
        repo = SavedCareerTargetRepository()
        v1 = repo.get_version(conn, created.target_version_id)
        assert v1.display_name == "Warehouse Operator"
        assert repo.get(conn, created.target_id).active_version_id == revised.target_version_id


def test_revise_with_stale_expected_version_raises(tmp_path):
    from onejob.career_targets.commands import StaleTargetVersion

    db = command_db(tmp_path)
    service = TargetCommandService(db, id_factory=SequentialIds())
    created = service.create_target(make_create(), actor=owner(), now=AT)
    service.revise_target(
        ReviseSavedCareerTargetCommand(
            actor_id="user-1",
            twin_id="twin-1",
            target_id=created.target_id,
            idempotency_key="tc-2",
            expected_active_version_id=created.target_version_id,
            display_name="v2",
            role_focus=[],
            domain_focus=[],
            explicit_keywords=[],
            scope_definition={},
            overrides=[],
        ),
        actor=owner(),
        now=AT,
    )
    with pytest.raises(StaleTargetVersion):
        service.revise_target(
            ReviseSavedCareerTargetCommand(
                actor_id="user-1",
                twin_id="twin-1",
                target_id=created.target_id,
                idempotency_key="tc-3",
                expected_active_version_id=created.target_version_id,
                display_name="v3",
                role_focus=[],
                domain_focus=[],
                explicit_keywords=[],
                scope_definition={},
                overrides=[],
            ),
            actor=owner(),
            now=AT,
        )


def test_lifecycle_pause_resume_archive(tmp_path):
    db = command_db(tmp_path)
    service = TargetCommandService(db, id_factory=SequentialIds())
    created = service.create_target(make_create(), actor=owner(), now=AT)

    service.set_lifecycle(
        SetTargetLifecycleCommand(
            actor_id="user-1",
            twin_id="twin-1",
            target_id=created.target_id,
            idempotency_key="lc-1",
            action="PAUSE",
        ),
        actor=owner(),
        now=AT,
    )
    with db.connection() as conn:
        assert SavedCareerTargetRepository().get(conn, created.target_id).lifecycle is TargetLifecycle.PAUSED

    service.set_lifecycle(
        SetTargetLifecycleCommand(
            actor_id="user-1",
            twin_id="twin-1",
            target_id=created.target_id,
            idempotency_key="lc-2",
            action="RESUME",
        ),
        actor=owner(),
        now=AT,
    )
    with db.connection() as conn:
        assert SavedCareerTargetRepository().get(conn, created.target_id).lifecycle is TargetLifecycle.ACTIVE

    service.set_lifecycle(
        SetTargetLifecycleCommand(
            actor_id="user-1",
            twin_id="twin-1",
            target_id=created.target_id,
            idempotency_key="lc-3",
            action="ARCHIVE",
        ),
        actor=owner(),
        now=AT,
    )
    with db.connection() as conn:
        assert SavedCareerTargetRepository().get(conn, created.target_id).lifecycle is TargetLifecycle.ARCHIVED


def test_archived_target_cannot_resume(tmp_path):
    db = command_db(tmp_path)
    service = TargetCommandService(db, id_factory=SequentialIds())
    created = service.create_target(make_create(), actor=owner(), now=AT)
    service.set_lifecycle(
        SetTargetLifecycleCommand(
            actor_id="user-1", twin_id="twin-1", target_id=created.target_id,
            idempotency_key="lc-1", action="ARCHIVE",
        ),
        actor=owner(), now=AT,
    )
    with pytest.raises(Exception):
        service.set_lifecycle(
            SetTargetLifecycleCommand(
                actor_id="user-1", twin_id="twin-1", target_id=created.target_id,
                idempotency_key="lc-2", action="RESUME",
            ),
            actor=owner(), now=AT,
        )


def test_unauthorized_actor_cannot_create_target(tmp_path):
    db = command_db(tmp_path)
    service = TargetCommandService(db, id_factory=SequentialIds())
    with pytest.raises(AuthorizationDenied):
        service.create_target(
            make_create(),
            actor={"actor_id": "x", "twin_id": "twin-2", "is_owner": True, "actor_type": "USER"},
            now=AT,
        )


def test_create_target_writes_event_and_outbox(tmp_path):
    db = command_db(tmp_path)
    service = TargetCommandService(db, id_factory=SequentialIds())
    service.create_target(make_create(), actor=owner(), now=AT)
    with db.connection() as conn:
        events = {
            row["event_type"]
            for row in conn.execute(
                "SELECT event_type FROM career_events WHERE twin_id = 'twin-1'"
            ).fetchall()
        }
    assert "SavedCareerTargetCreated" in events
    assert "SavedCareerTargetVersionCreated" in events
