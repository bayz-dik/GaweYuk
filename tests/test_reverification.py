from datetime import datetime, timedelta, timezone

import pytest

from onejob.ingestion.models import JobLifecycleState
from onejob.job_verification.reverification import (
    ReverificationError,
    ReverificationRepository,
    ReverificationRunner,
    SourceRefreshResult,
    apply_reverification_observation,
    next_verification_at,
)
from onejob.job_sources.models import SourceTrustTier, SourceHealthState
from onejob.persistence.db import Database


NOW = datetime(2026, 8, 21, tzinfo=timezone.utc)


def test_rate_limit_does_not_close_job():
    result = apply_reverification_observation(
        current=JobLifecycleState.ACTIVE,
        source_result=SourceRefreshResult.RATE_LIMITED,
        authoritative=True,
    )
    assert result.lifecycle_state is JobLifecycleState.ACTIVE
    assert result.requires_publication_reevaluation is False


def test_timeout_does_not_close_job():
    result = apply_reverification_observation(
        current=JobLifecycleState.ACTIVE,
        source_result=SourceRefreshResult.TIMEOUT,
        authoritative=True,
    )
    assert result.lifecycle_state is JobLifecycleState.ACTIVE


def test_authoritative_closed_result_withdraws_active_listing():
    result = apply_reverification_observation(
        current=JobLifecycleState.ACTIVE,
        source_result=SourceRefreshResult.CONFIRMED_CLOSED,
        authoritative=True,
    )
    assert result.lifecycle_state is JobLifecycleState.CLOSED
    assert result.requires_publication_reevaluation is True


def test_non_authoritative_closed_does_not_close():
    result = apply_reverification_observation(
        current=JobLifecycleState.ACTIVE,
        source_result=SourceRefreshResult.CONFIRMED_CLOSED,
        authoritative=False,
    )
    assert result.lifecycle_state is JobLifecycleState.ACTIVE


def test_tier1_reverifies_sooner_than_tier3():
    tier1 = next_verification_at(
        tier=SourceTrustTier.TIER_1_OFFICIAL,
        health=SourceHealthState.HEALTHY,
        evaluated_at=NOW,
    )
    tier3 = next_verification_at(
        tier=SourceTrustTier.TIER_3_DISCOVERY,
        health=SourceHealthState.HEALTHY,
        evaluated_at=NOW,
    )
    assert tier1 > NOW
    assert tier3 > NOW
    # deterministic, no random jitter
    again = next_verification_at(
        tier=SourceTrustTier.TIER_1_OFFICIAL,
        health=SourceHealthState.HEALTHY,
        evaluated_at=NOW,
    )
    assert tier1 == again


def test_degraded_source_reverifies_sooner():
    healthy = next_verification_at(
        tier=SourceTrustTier.TIER_1_OFFICIAL,
        health=SourceHealthState.HEALTHY,
        evaluated_at=NOW,
    )
    degraded = next_verification_at(
        tier=SourceTrustTier.TIER_1_OFFICIAL,
        health=SourceHealthState.DEGRADED,
        evaluated_at=NOW,
    )
    assert degraded < healthy


def test_due_work_survives_and_is_claimable(tmp_path):
    db = Database(tmp_path / "rev.db")
    db.initialize()
    repo = ReverificationRepository()

    with db.transaction() as conn:
        repo.schedule(conn, canonical_job_id="job-1", due_at=NOW)

    later = NOW + timedelta(hours=1)
    with db.transaction() as conn:
        due = repo.claim_due(conn, limit=10, now=later)

    assert [item.canonical_job_id for item in due] == ["job-1"]

    # A restart re-reads persisted work; claimed items are marked in-progress.
    with db.connection() as conn:
        status = conn.execute(
            "SELECT status FROM reverification_work WHERE canonical_job_id='job-1'"
        ).fetchone()[0]
    assert status in {"CLAIMED", "IN_PROGRESS"}


def test_runner_processes_due_work(tmp_path):
    db = Database(tmp_path / "rev.db")
    db.initialize()
    repo = ReverificationRepository()
    with db.transaction() as conn:
        repo.schedule(conn, canonical_job_id="job-1", due_at=NOW)

    processed = []

    def handler(canonical_job_id, *, now):
        processed.append(canonical_job_id)

    runner = ReverificationRunner(db, handler=handler)
    summary = runner.run_due(limit=10, now=NOW + timedelta(hours=1))

    assert processed == ["job-1"]
    assert summary.processed == 1
