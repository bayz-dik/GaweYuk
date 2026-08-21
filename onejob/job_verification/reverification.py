from __future__ import annotations

import sqlite3
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum

from onejob.ingestion.models import JobLifecycleState
from onejob.job_sources.models import SourceHealthState, SourceTrustTier
from onejob.persistence.db import Database


class SourceRefreshResult(str, Enum):
    STILL_ACTIVE = "STILL_ACTIVE"
    CONFIRMED_CLOSED = "CONFIRMED_CLOSED"
    RATE_LIMITED = "RATE_LIMITED"
    TIMEOUT = "TIMEOUT"
    TRANSIENT_ERROR = "TRANSIENT_ERROR"


class ReverificationError(str, Enum):
    RATE_LIMITED = "RATE_LIMITED"
    TRANSIENT_NETWORK = "TRANSIENT_NETWORK"
    AUTH_FAILURE = "AUTH_FAILURE"
    SCHEMA_CHANGED = "SCHEMA_CHANGED"
    PERMANENT_POLICY_BLOCK = "PERMANENT_POLICY_BLOCK"
    SYSTEM_FAILURE = "SYSTEM_FAILURE"


@dataclass(frozen=True)
class ReverificationOutcome:
    lifecycle_state: JobLifecycleState
    requires_publication_reevaluation: bool
    reason_codes: tuple[str, ...]


def apply_reverification_observation(
    *,
    current: JobLifecycleState,
    source_result: SourceRefreshResult,
    authoritative: bool,
) -> ReverificationOutcome:
    """Map a refresh result to a lifecycle decision.

    Only an authoritative confirmed-closed result closes a listing. Rate
    limiting, timeouts, and transient errors are operational failures, never
    closure evidence.
    """
    if (
        source_result is SourceRefreshResult.CONFIRMED_CLOSED
        and authoritative
        and current is not JobLifecycleState.CLOSED
    ):
        return ReverificationOutcome(
            lifecycle_state=JobLifecycleState.CLOSED,
            requires_publication_reevaluation=True,
            reason_codes=("AUTHORITATIVE_CLOSURE",),
        )

    if source_result in (
        SourceRefreshResult.RATE_LIMITED,
        SourceRefreshResult.TIMEOUT,
        SourceRefreshResult.TRANSIENT_ERROR,
    ):
        return ReverificationOutcome(
            lifecycle_state=current,
            requires_publication_reevaluation=False,
            reason_codes=("OPERATIONAL_FAILURE_NOT_CLOSURE",),
        )

    return ReverificationOutcome(
        lifecycle_state=current,
        requires_publication_reevaluation=False,
        reason_codes=("NO_CHANGE",),
    )


# Base reverification cadence per source tier. Deterministic; the scheduler
# does not use random jitter so domain tests stay reproducible.
_TIER_BASE_INTERVAL = {
    SourceTrustTier.TIER_1_OFFICIAL: timedelta(days=3),
    SourceTrustTier.TIER_2_AUTHORIZED: timedelta(days=5),
    SourceTrustTier.TIER_3_DISCOVERY: timedelta(days=10),
}


def next_verification_at(
    *,
    tier: SourceTrustTier,
    health: SourceHealthState,
    evaluated_at: datetime,
) -> datetime:
    interval = _TIER_BASE_INTERVAL.get(tier, timedelta(days=7))
    # A degraded/rate-limited source is checked sooner to detect recovery or
    # continued failure faster.
    if health in (
        SourceHealthState.DEGRADED,
        SourceHealthState.RATE_LIMITED,
        SourceHealthState.SCHEMA_CHANGED,
    ):
        interval = interval / 2
    return evaluated_at + interval


@dataclass(frozen=True)
class ReverificationWorkItem:
    work_id: str
    canonical_job_id: str
    due_at: datetime
    attempt_count: int


@dataclass(frozen=True)
class ReverificationRunSummary:
    processed: int
    failed: int


class ReverificationRepository:
    def schedule(
        self,
        conn: sqlite3.Connection,
        *,
        canonical_job_id: str,
        due_at: datetime,
    ) -> None:
        conn.execute(
            """
            INSERT OR IGNORE INTO reverification_work (
                work_id, canonical_job_id, due_at, status, attempt_count
            )
            VALUES (?, ?, ?, 'PENDING', 0)
            """,
            (uuid.uuid4().hex, canonical_job_id, due_at.isoformat()),
        )

    def claim_due(
        self, conn: sqlite3.Connection, *, limit: int, now: datetime
    ) -> list[ReverificationWorkItem]:
        rows = conn.execute(
            """
            SELECT work_id, canonical_job_id, due_at, attempt_count
            FROM reverification_work
            WHERE status = 'PENDING' AND due_at <= ?
            ORDER BY due_at
            LIMIT ?
            """,
            (now.isoformat(), limit),
        ).fetchall()
        items = [
            ReverificationWorkItem(
                work_id=row[0],
                canonical_job_id=row[1],
                due_at=datetime.fromisoformat(row[2]),
                attempt_count=row[3],
            )
            for row in rows
        ]
        for item in items:
            conn.execute(
                """
                UPDATE reverification_work
                SET status = 'CLAIMED', claimed_at = ?
                WHERE work_id = ?
                """,
                (now.isoformat(), item.work_id),
            )
        return items

    def mark_completed(
        self, conn: sqlite3.Connection, *, work_id: str, now: datetime
    ) -> None:
        conn.execute(
            """
            UPDATE reverification_work
            SET status = 'COMPLETED', completed_at = ?
            WHERE work_id = ?
            """,
            (now.isoformat(), work_id),
        )

    def mark_failed(
        self,
        conn: sqlite3.Connection,
        *,
        work_id: str,
        error_class: str,
        now: datetime,
    ) -> None:
        # Permanent policy blocks are terminal; other errors return to PENDING
        # with a bumped attempt count so retries use bounded backoff, not a
        # hot loop.
        terminal = error_class == ReverificationError.PERMANENT_POLICY_BLOCK.value
        conn.execute(
            """
            UPDATE reverification_work
            SET status = ?, last_error_class = ?, attempt_count = attempt_count + 1
            WHERE work_id = ?
            """,
            ("FAILED" if terminal else "PENDING", error_class, work_id),
        )


class ReverificationRunner:
    def __init__(self, db: Database, *, handler, repository=None):
        self.db = db
        self.handler = handler
        self.repo = repository or ReverificationRepository()

    def run_due(self, *, limit: int, now: datetime) -> ReverificationRunSummary:
        with self.db.transaction() as conn:
            due = self.repo.claim_due(conn, limit=limit, now=now)

        processed = 0
        failed = 0
        for item in due:
            try:
                self.handler(item.canonical_job_id, now=now)
            except Exception:
                failed += 1
                with self.db.transaction() as conn:
                    self.repo.mark_failed(
                        conn,
                        work_id=item.work_id,
                        error_class=ReverificationError.SYSTEM_FAILURE.value,
                        now=now,
                    )
                continue
            processed += 1
            with self.db.transaction() as conn:
                self.repo.mark_completed(conn, work_id=item.work_id, now=now)

        return ReverificationRunSummary(processed=processed, failed=failed)
