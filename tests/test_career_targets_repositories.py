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
