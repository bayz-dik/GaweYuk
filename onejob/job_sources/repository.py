from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime

from onejob.ingestion.models import SourceType
from onejob.job_sources.models import (
    AcquisitionMethod,
    ComplianceStatus,
    JobSource,
    SourceHealthState,
    SourceRolloutState,
    SourceTrustTier,
)


def _dt(value: datetime) -> str:
    return value.isoformat()


def _parse_dt(value: str) -> datetime:
    return datetime.fromisoformat(value)


def _row_to_source(row: sqlite3.Row) -> JobSource:
    return JobSource(
        source_id=row["source_id"],
        source_key=row["source_key"],
        source_type=SourceType(row["source_type"]),
        trust_tier=SourceTrustTier(row["trust_tier"]),
        acquisition_method=AcquisitionMethod(row["acquisition_method"]),
        primary_domain=row["primary_domain"],
        country_scope=tuple(json.loads(row["country_scope_json"])),
        compliance_status=ComplianceStatus(row["compliance_status"]),
        rollout_state=SourceRolloutState(row["rollout_state"]),
        health_state=SourceHealthState(row["health_state"]),
        verification_policy_version=row["verification_policy_version"],
        created_at=_parse_dt(row["created_at"]),
        updated_at=_parse_dt(row["updated_at"]),
    )


class SourceRepository:
    """Stateless persistence for the source registry.

    Repositories never hold a connection; every method takes a caller-owned
    ``sqlite3.Connection`` so the Database owns the transaction boundary.
    """

    def insert(self, conn: sqlite3.Connection, source: JobSource) -> None:
        conn.execute(
            """
            INSERT INTO job_sources (
                source_id, source_key, source_type, trust_tier,
                acquisition_method, primary_domain, country_scope_json,
                compliance_status, rollout_state, health_state,
                verification_policy_version, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                source.source_id,
                source.source_key,
                source.source_type.value,
                source.trust_tier.value,
                source.acquisition_method.value,
                source.primary_domain,
                json.dumps(list(source.country_scope)),
                source.compliance_status.value,
                source.rollout_state.value,
                source.health_state.value,
                source.verification_policy_version,
                _dt(source.created_at),
                _dt(source.updated_at),
            ),
        )

    def get_by_id(
        self, conn: sqlite3.Connection, source_id: str
    ) -> JobSource | None:
        row = conn.execute(
            "SELECT * FROM job_sources WHERE source_id = ?", (source_id,)
        ).fetchone()
        return _row_to_source(row) if row is not None else None

    def get_by_key(
        self, conn: sqlite3.Connection, source_key: str
    ) -> JobSource | None:
        row = conn.execute(
            "SELECT * FROM job_sources WHERE source_key = ?", (source_key,)
        ).fetchone()
        return _row_to_source(row) if row is not None else None

    def list_all(self, conn: sqlite3.Connection) -> list[JobSource]:
        rows = conn.execute(
            "SELECT * FROM job_sources ORDER BY source_key"
        ).fetchall()
        return [_row_to_source(row) for row in rows]

    def update_state(
        self,
        conn: sqlite3.Connection,
        *,
        source_id: str,
        rollout_state: SourceRolloutState | None = None,
        health_state: SourceHealthState | None = None,
        updated_at: datetime,
        reason_code: str = "state_update",
    ) -> JobSource:
        current = self.get_by_id(conn, source_id)
        if current is None:
            raise LookupError(f"job source not found: {source_id}")

        new_rollout = rollout_state or current.rollout_state
        new_health = health_state or current.health_state

        conn.execute(
            """
            UPDATE job_sources
            SET rollout_state = ?, health_state = ?, updated_at = ?
            WHERE source_id = ?
            """,
            (
                new_rollout.value,
                new_health.value,
                _dt(updated_at),
                source_id,
            ),
        )

        if rollout_state is not None and rollout_state is not current.rollout_state:
            self._record_event(
                conn,
                source_id=source_id,
                event_type="ROLLOUT_STATE_CHANGED",
                old_state=current.rollout_state.value,
                new_state=new_rollout.value,
                reason_code=reason_code,
                occurred_at=updated_at,
            )
        if health_state is not None and health_state is not current.health_state:
            self._record_event(
                conn,
                source_id=source_id,
                event_type="HEALTH_STATE_CHANGED",
                old_state=current.health_state.value,
                new_state=new_health.value,
                reason_code=reason_code,
                occurred_at=updated_at,
            )

        reloaded = self.get_by_id(conn, source_id)
        assert reloaded is not None
        return reloaded

    def _record_event(
        self,
        conn: sqlite3.Connection,
        *,
        source_id: str,
        event_type: str,
        old_state: str | None,
        new_state: str | None,
        reason_code: str,
        occurred_at: datetime,
    ) -> None:
        conn.execute(
            """
            INSERT INTO job_source_state_events (
                event_id, source_id, event_type, old_state, new_state,
                reason_code, occurred_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                uuid.uuid4().hex,
                source_id,
                event_type,
                old_state,
                new_state,
                reason_code,
                _dt(occurred_at),
            ),
        )
