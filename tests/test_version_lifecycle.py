def test_salary_change_creates_material_diff():
    from onejob.ingestion.lifecycle import diff_material_fields

    old = {
        "title": "Operator",
        "salary_min": 5500000,
        "salary_max": 6500000,
    }

    new = {
        "title": "Operator",
        "salary_min": 6000000,
        "salary_max": 7000000,
    }

    assert diff_material_fields(old, new) == [
        "salary_max",
        "salary_min",
    ]


def test_reappearance_after_closed_is_reopened():
    from onejob.ingestion.lifecycle import next_lifecycle_state
    from onejob.ingestion.models import JobLifecycleState

    assert next_lifecycle_state(
        JobLifecycleState.CLOSED,
        observed_now=True,
        materially_changed=False,
    ) == JobLifecycleState.REOPENED


def test_active_with_material_change_becomes_updated():
    from onejob.ingestion.lifecycle import next_lifecycle_state
    from onejob.ingestion.models import JobLifecycleState

    assert next_lifecycle_state(
        JobLifecycleState.ACTIVE,
        observed_now=True,
        materially_changed=True,
    ) == JobLifecycleState.UPDATED


def test_active_unchanged_stays_active():
    from onejob.ingestion.lifecycle import next_lifecycle_state
    from onejob.ingestion.models import JobLifecycleState

    assert next_lifecycle_state(
        JobLifecycleState.ACTIVE,
        observed_now=True,
        materially_changed=False,
    ) == JobLifecycleState.ACTIVE


def test_unobserved_active_can_become_stale():
    from onejob.ingestion.lifecycle import next_lifecycle_state
    from onejob.ingestion.models import JobLifecycleState

    assert next_lifecycle_state(
        JobLifecycleState.ACTIVE,
        observed_now=False,
        materially_changed=False,
    ) == JobLifecycleState.STALE


def test_source_health_maps_collection_outcomes():
    from onejob.collectors.base import CollectionStatus
    from onejob.source_health import (
        SourceHealthStatus,
        transition_source_health,
    )

    status, failures = transition_source_health(
        SourceHealthStatus.UNKNOWN,
        CollectionStatus.SUCCESS,
        0,
    )
    assert status == SourceHealthStatus.HEALTHY
    assert failures == 0

    status, failures = transition_source_health(
        SourceHealthStatus.HEALTHY,
        CollectionStatus.PARTIAL,
        0,
    )
    assert status == SourceHealthStatus.DEGRADED
    assert failures == 0

    status, failures = transition_source_health(
        SourceHealthStatus.HEALTHY,
        CollectionStatus.RATE_LIMITED,
        0,
    )
    assert status == SourceHealthStatus.RATE_LIMITED
    assert failures == 0


def test_third_consecutive_failure_breaks_source():
    from onejob.collectors.base import CollectionStatus
    from onejob.source_health import (
        SourceHealthStatus,
        transition_source_health,
    )

    status, failures = transition_source_health(
        SourceHealthStatus.HEALTHY,
        CollectionStatus.FAILED,
        0,
    )
    assert status == SourceHealthStatus.DEGRADED
    assert failures == 1

    status, failures = transition_source_health(
        status,
        CollectionStatus.FAILED,
        failures,
    )
    assert status == SourceHealthStatus.DEGRADED
    assert failures == 2

    status, failures = transition_source_health(
        status,
        CollectionStatus.FAILED,
        failures,
    )
    assert status == SourceHealthStatus.BROKEN
    assert failures == 3


def test_success_recovers_broken_source():
    from onejob.collectors.base import CollectionStatus
    from onejob.source_health import (
        SourceHealthStatus,
        transition_source_health,
    )

    status, failures = transition_source_health(
        SourceHealthStatus.BROKEN,
        CollectionStatus.SUCCESS,
        3,
    )

    assert status == SourceHealthStatus.HEALTHY
    assert failures == 0


def test_temporal_models_expose_version_and_event_contract():
    from datetime import datetime, timezone

    from onejob.ingestion.models import (
        JobEvent,
        JobEventType,
        JobVersion,
    )

    now = datetime.now(timezone.utc)

    version = JobVersion(
        version_id="ver-1",
        canonical_job_id="job-1",
        version_number=1,
        valid_from=now,
        valid_to=None,
        content_hash="hash-1",
        changed_fields=["salary_min", "salary_max"],
        field_snapshot={
            "title": "Operator",
            "salary_min": 6000000,
            "salary_max": 7000000,
        },
    )

    event = JobEvent(
        event_id="evt-1",
        canonical_job_id="job-1",
        event_type=JobEventType.JOB_CHANGED,
        occurred_at=now,
        payload={
            "changed_fields": ["salary_min", "salary_max"],
        },
    )

    assert version.version_number == 1
    assert event.event_type == JobEventType.JOB_CHANGED


def test_job_history_repository_round_trips_versions_and_events(tmp_path):
    from datetime import datetime, timezone

    from onejob.persistence.repositories import JobHistoryRepository
    from onejob.ingestion.models import (
        JobEvent,
        JobEventType,
        JobVersion,
    )
    from onejob.persistence.db import Database

    now = datetime.now(timezone.utc)

    db = Database(tmp_path / "history.db")
    db.initialize()
    repo = JobHistoryRepository()

    version = JobVersion(
        version_id="ver-1",
        canonical_job_id="job-1",
        version_number=1,
        valid_from=now,
        valid_to=None,
        content_hash="hash-1",
        changed_fields=["salary_min"],
        field_snapshot={
            "title": "Operator",
            "salary_min": 6000000,
        },
    )

    event = JobEvent(
        event_id="evt-1",
        canonical_job_id="job-1",
        event_type=JobEventType.JOB_CHANGED,
        occurred_at=now,
        payload={
            "changed_fields": ["salary_min"],
        },
    )

    with db.transaction() as conn:
        repo.append_version(conn, version)
        repo.append_event(conn, event)

    with db.connection() as conn:
        latest = repo.latest_version(conn, "job-1")
        versions = repo.list_versions(conn, "job-1")
        events = repo.list_events(conn, "job-1")

    assert latest is not None
    assert latest.version_id == "ver-1"
    assert [item.version_id for item in versions] == ["ver-1"]
    assert [item.event_id for item in events] == ["evt-1"]


def test_material_snapshot_ignores_collection_noise():
    from onejob.ingestion.lifecycle import material_snapshot

    first = {
        "title": "Production Operator",
        "company_name": "PT Example",
        "location_text": "Bekasi",
        "description": "Operate production machines",
        "salary_min": 6000000,
        "salary_max": 7000000,
        "currency": "IDR",
        "employment_type": "full-time",
        "contact_email": "hr@example.com",

        # collection/provenance noise
        "source_url": "https://example.com/jobs/1",
        "observed_at": "2026-08-20T10:00:00Z",
        "collector_version": "1.0",
        "source_payload_hash": "aaa",
    }

    second = {
        **first,
        "source_url": "https://example.com/jobs/1?ref=linkedin",
        "observed_at": "2026-08-20T11:00:00Z",
        "collector_version": "1.1",
        "source_payload_hash": "bbb",
    }

    assert material_snapshot(first) == material_snapshot(second)

    assert material_snapshot(first) == {
        "title": "Production Operator",
        "company_name": "PT Example",
        "location_text": "Bekasi",
        "description": "Operate production machines",
        "salary_min": 6000000,
        "salary_max": 7000000,
        "currency": "IDR",
        "employment_type": "full-time",
        "contact_email": "hr@example.com",
    }


def test_job_event_type_exposes_lifecycle_events():
    from onejob.ingestion.models import JobEventType

    assert {
        event.value
        for event in JobEventType
    } == {
        "JOB_DISCOVERED",
        "JOB_SEEN",
        "JOB_CHANGED",
        "JOB_REOPENED",
    }
