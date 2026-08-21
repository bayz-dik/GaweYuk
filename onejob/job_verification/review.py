from __future__ import annotations

import hashlib
import json
import sqlite3
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

from onejob.persistence.db import Database


class VerificationCaseState(str, Enum):
    OPEN = "OPEN"
    IN_REVIEW = "IN_REVIEW"
    DEFERRED = "DEFERRED"
    RESOLVED = "RESOLVED"
    SUPERSEDED = "SUPERSEDED"


class ReviewDecision(str, Enum):
    VERIFY = "VERIFY"
    REJECT = "REJECT"
    DEFER = "DEFER"


class ReviewAuthorizationDenied(RuntimeError):
    pass


class StaleReviewContext(RuntimeError):
    pass


class IdempotencyConflict(RuntimeError):
    pass


class HardGateNotReviewOverrideable(RuntimeError):
    pass


_REVIEWER_ROLES = {"job_verifier", "trust_admin"}


@dataclass(frozen=True)
class ReviewActor:
    actor_id: str
    roles: tuple[str, ...]


@dataclass(frozen=True)
class VerificationResolution:
    resolution_id: str
    case_id: str
    reviewer_id: str
    evidence_snapshot_id: str
    decision: ReviewDecision
    reason_codes: tuple[str, ...] = field(default_factory=tuple)
    notes: str | None = None


def _fingerprint(payload: dict) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(encoded.encode()).hexdigest()


class _ReviewRepository:
    def open_case(
        self,
        conn: sqlite3.Connection,
        *,
        case_id: str,
        canonical_job_id: str,
        verification_id: str,
        reason_codes: tuple[str, ...],
        priority: str,
        opened_at: datetime,
    ) -> None:
        conn.execute(
            """
            INSERT INTO verification_cases (
                case_id, canonical_job_id, verification_id, reason_codes_json,
                priority, state, opened_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                case_id,
                canonical_job_id,
                verification_id,
                json.dumps(list(reason_codes)),
                priority,
                VerificationCaseState.OPEN.value,
                opened_at.isoformat(),
            ),
        )

    def get_case(self, conn: sqlite3.Connection, case_id: str) -> dict | None:
        row = conn.execute(
            "SELECT * FROM verification_cases WHERE case_id = ?", (case_id,)
        ).fetchone()
        if row is None:
            return None
        return {key: row[key] for key in row.keys()}

    def resolve_case(
        self,
        conn: sqlite3.Connection,
        *,
        resolution: VerificationResolution,
        decided_at: datetime,
    ) -> None:
        conn.execute(
            """
            INSERT INTO verification_resolutions (
                resolution_id, case_id, reviewer_id, evidence_snapshot_id,
                decision, reason_codes_json, notes, decided_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                resolution.resolution_id,
                resolution.case_id,
                resolution.reviewer_id,
                resolution.evidence_snapshot_id,
                resolution.decision.value,
                json.dumps(list(resolution.reason_codes)),
                resolution.notes,
                decided_at.isoformat(),
            ),
        )
        conn.execute(
            """
            UPDATE verification_cases
            SET state = ?, resolved_at = ?, resolution_id = ?
            WHERE case_id = ?
            """,
            (
                VerificationCaseState.RESOLVED.value,
                decided_at.isoformat(),
                resolution.resolution_id,
                resolution.case_id,
            ),
        )

    def record_idempotency(
        self,
        conn: sqlite3.Connection,
        *,
        idempotency_key: str,
        request_fingerprint: str,
        resolution_id: str,
        created_at: datetime,
    ) -> None:
        conn.execute(
            """
            INSERT INTO verification_review_idempotency (
                idempotency_key, request_fingerprint, resolution_id, created_at
            )
            VALUES (?, ?, ?, ?)
            """,
            (idempotency_key, request_fingerprint, resolution_id, created_at.isoformat()),
        )

    def get_idempotency(
        self, conn: sqlite3.Connection, idempotency_key: str
    ) -> dict | None:
        row = conn.execute(
            "SELECT * FROM verification_review_idempotency WHERE idempotency_key = ?",
            (idempotency_key,),
        ).fetchone()
        return {key: row[key] for key in row.keys()} if row is not None else None

    def get_resolution(
        self, conn: sqlite3.Connection, resolution_id: str
    ) -> VerificationResolution | None:
        row = conn.execute(
            "SELECT * FROM verification_resolutions WHERE resolution_id = ?",
            (resolution_id,),
        ).fetchone()
        if row is None:
            return None
        return VerificationResolution(
            resolution_id=row["resolution_id"],
            case_id=row["case_id"],
            reviewer_id=row["reviewer_id"],
            evidence_snapshot_id=row["evidence_snapshot_id"],
            decision=ReviewDecision(row["decision"]),
            reason_codes=tuple(json.loads(row["reason_codes_json"])),
            notes=row["notes"],
        )


class ReviewCommandService:
    """Authorized, idempotent, stale-safe verification review commands.

    A human resolution never mutates the catalog directly; it records evidence,
    closes the case, and triggers a fresh verification/publication evaluation.
    Hard gates and publication policy still apply, so a reviewer cannot clear an
    absolute block.
    """

    def __init__(self, db: Database, *, store):
        self.db = db
        self.store = store
        self.repo = _ReviewRepository()

    def resolve_case(
        self,
        *,
        actor: ReviewActor,
        case_id: str,
        expected_verification_id: str,
        idempotency_key: str,
        decision: ReviewDecision,
        reason_codes: tuple[str, ...],
        now: datetime,
        notes: str | None = None,
    ) -> VerificationResolution:
        if not (set(actor.roles) & _REVIEWER_ROLES):
            raise ReviewAuthorizationDenied(
                f"actor {actor.actor_id} lacks a reviewer role"
            )

        fingerprint = _fingerprint(
            {
                "case_id": case_id,
                "expected_verification_id": expected_verification_id,
                "decision": decision.value,
                "reason_codes": list(reason_codes),
                "notes": notes,
            }
        )

        with self.db.transaction() as conn:
            case = self.repo.get_case(conn, case_id)
            if case is None:
                raise LookupError(f"verification case not found: {case_id}")

            existing = self.repo.get_idempotency(conn, idempotency_key)
            if existing is not None:
                if existing["request_fingerprint"] != fingerprint:
                    raise IdempotencyConflict(
                        f"idempotency key reused with different request: {idempotency_key}"
                    )
                resolution = self.repo.get_resolution(
                    conn, existing["resolution_id"]
                )
                assert resolution is not None
                return resolution

            # Reviewer must act on the current evidence snapshot. If evidence
            # has advanced, force a refresh rather than deciding on stale data.
            current = self.store.latest_verification_id(case["canonical_job_id"])
            if current != expected_verification_id:
                raise StaleReviewContext(
                    "verification context advanced; expected "
                    f"{expected_verification_id}, current {current}"
                )

            if (
                decision is ReviewDecision.VERIFY
                and self.store.has_absolute_hard_gate(expected_verification_id)
            ):
                raise HardGateNotReviewOverrideable(
                    "an absolute hard gate cannot be cleared by review"
                )

            resolution = VerificationResolution(
                resolution_id=f"resolution-{uuid.uuid4().hex}",
                case_id=case_id,
                reviewer_id=actor.actor_id,
                evidence_snapshot_id=expected_verification_id,
                decision=decision,
                reason_codes=reason_codes,
                notes=notes,
            )
            self.repo.resolve_case(conn, resolution=resolution, decided_at=now)
            self.repo.record_idempotency(
                conn,
                idempotency_key=idempotency_key,
                request_fingerprint=fingerprint,
                resolution_id=resolution.resolution_id,
                created_at=now,
            )

        # Reevaluation happens after the resolution transaction commits; the
        # resolution is an authorized input, not a direct catalog mutation.
        self.store.trigger_reevaluation(case["canonical_job_id"], now=now)
        return resolution
