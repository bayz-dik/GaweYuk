from __future__ import annotations

import json
from dataclasses import dataclass
import sqlite3
from datetime import datetime

from onejob.job_verification.models import (
    ApplyDestinationStatus,
    JobVerificationSnapshot,
)
def _dt(value: datetime) -> str:
    return value.isoformat()


def _parse_dt(value: str) -> datetime:
    return datetime.fromisoformat(value)


def _row_to_snapshot(row: sqlite3.Row) -> JobVerificationSnapshot:
    return JobVerificationSnapshot(
        verification_id=row["verification_id"],
        canonical_job_id=row["canonical_job_id"],
        canonical_version_id=row["canonical_version_id"],
        identity_snapshot_id=row["identity_snapshot_id"],
        trust_evaluation_id=row["trust_evaluation_id"],
        identity_state=row["identity_state"],
        trust_classification=row["trust_classification"],
        destination_status=ApplyDestinationStatus(row["destination_status"]),
        freshness_state=row["freshness_state"],
        corroboration=json.loads(row["corroboration_json"]),
        hard_gate_hits=tuple(json.loads(row["hard_gate_hits_json"])),
        unknowns=tuple(json.loads(row["unknowns_json"])),
        evaluated_at=_parse_dt(row["evaluated_at"]),
        valid_until=_parse_dt(row["valid_until"]),
        input_fingerprint=row["input_fingerprint"],
        verification_policy_version=row["verification_policy_version"],
    )


class VerificationRepository:
    """Immutable verification snapshot persistence.

    Snapshots are never mutated. Content-addressed reuse is by
    ``(canonical_job_id, input_fingerprint)``; identical inputs return the
    existing snapshot rather than writing a duplicate.
    """

    def get_by_fingerprint(
        self,
        conn: sqlite3.Connection,
        *,
        canonical_job_id: str,
        input_fingerprint: str,
    ) -> JobVerificationSnapshot | None:
        row = conn.execute(
            """
            SELECT * FROM job_verification_snapshots
            WHERE canonical_job_id = ? AND input_fingerprint = ?
            """,
            (canonical_job_id, input_fingerprint),
        ).fetchone()
        return _row_to_snapshot(row) if row is not None else None

    def get(
        self, conn: sqlite3.Connection, verification_id: str
    ) -> JobVerificationSnapshot | None:
        row = conn.execute(
            "SELECT * FROM job_verification_snapshots WHERE verification_id = ?",
            (verification_id,),
        ).fetchone()
        return _row_to_snapshot(row) if row is not None else None

    def append(
        self,
        conn: sqlite3.Connection,
        snapshot: JobVerificationSnapshot,
        *,
        evidence_refs: tuple[str, ...],
    ) -> None:
        conn.execute(
            """
            INSERT INTO job_verification_snapshots (
                verification_id, canonical_job_id, canonical_version_id,
                identity_snapshot_id, trust_evaluation_id, identity_state,
                trust_classification, destination_status, freshness_state,
                corroboration_json, hard_gate_hits_json, unknowns_json,
                evaluated_at, valid_until, input_fingerprint,
                verification_policy_version
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                snapshot.verification_id,
                snapshot.canonical_job_id,
                snapshot.canonical_version_id,
                snapshot.identity_snapshot_id,
                snapshot.trust_evaluation_id,
                snapshot.identity_state,
                snapshot.trust_classification,
                snapshot.destination_status.value,
                snapshot.freshness_state,
                json.dumps(snapshot.corroboration, sort_keys=True),
                json.dumps(list(snapshot.hard_gate_hits)),
                json.dumps(list(snapshot.unknowns)),
                _dt(snapshot.evaluated_at),
                _dt(snapshot.valid_until),
                snapshot.input_fingerprint,
                snapshot.verification_policy_version,
            ),
        )
        for evidence_ref in evidence_refs:
            conn.execute(
                """
                INSERT OR IGNORE INTO job_verification_snapshot_evidence (
                    verification_id, evidence_ref
                )
                VALUES (?, ?)
                """,
                (snapshot.verification_id, evidence_ref),
            )


@dataclass(frozen=True)
class PublicationHead:
    canonical_job_id: str
    decision_id: str
    state: "object"
    updated_at: datetime


class _PublicationMixin:
    def append_publication_decision(
        self,
        conn: sqlite3.Connection,
        *,
        decision_id: str,
        canonical_job_id: str,
        verification_id: str | None,
        state,
        reason_codes: tuple[str, ...],
        decided_at: datetime,
        valid_until: datetime | None = None,
        policy_version: str = "job-verification-v1",
    ) -> None:
        # Append-only immutable decision, then move the head pointer. Both run
        # in the caller's transaction so a mid-write failure rolls back the
        # entire decision and leaves the previous head intact.
        conn.execute(
            """
            INSERT INTO publication_decisions (
                decision_id, canonical_job_id, verification_id, state,
                reason_codes_json, decided_at, valid_until, policy_version
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                decision_id,
                canonical_job_id,
                verification_id,
                state.value,
                json.dumps(list(reason_codes)),
                _dt(decided_at),
                _dt(valid_until) if valid_until is not None else None,
                policy_version,
            ),
        )
        conn.execute(
            """
            INSERT INTO job_publication_heads (
                canonical_job_id, decision_id, state, updated_at
            )
            VALUES (?, ?, ?, ?)
            ON CONFLICT(canonical_job_id) DO UPDATE SET
                decision_id = excluded.decision_id,
                state = excluded.state,
                updated_at = excluded.updated_at
            """,
            (canonical_job_id, decision_id, state.value, _dt(decided_at)),
        )

    def get_publication_head(
        self, conn: sqlite3.Connection, canonical_job_id: str
    ):
        from onejob.job_verification.policy import PublicationState

        row = conn.execute(
            "SELECT canonical_job_id, decision_id, state, updated_at "
            "FROM job_publication_heads WHERE canonical_job_id = ?",
            (canonical_job_id,),
        ).fetchone()
        if row is None:
            return None
        return PublicationHead(
            canonical_job_id=row[0],
            decision_id=row[1],
            state=PublicationState(row[2]),
            updated_at=_parse_dt(row[3]),
        )


for _name in ("append_publication_decision", "get_publication_head"):
    setattr(VerificationRepository, _name, getattr(_PublicationMixin, _name))
