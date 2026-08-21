from __future__ import annotations

from datetime import datetime
from typing import Callable

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from onejob.job_verification.review import (
    HardGateNotReviewOverrideable,
    IdempotencyConflict,
    ReviewActor,
    ReviewAuthorizationDenied,
    ReviewCommandService,
    ReviewDecision,
    StaleReviewContext,
    _ReviewRepository,
)
from onejob.persistence.db import Database


class ResolveCaseBody(BaseModel):
    expected_verification_id: str
    idempotency_key: str
    decision: str
    reason_codes: list[str]
    notes: str | None = None


class _StoreAdapter:
    """Bridges the review command service to persisted case + reevaluation.

    Keeps the review service store-agnostic while the internal API supplies the
    current verification id, hard-gate lookup, and post-commit reevaluation.
    """

    def __init__(self, db: Database, *, reevaluate):
        self.db = db
        self._reevaluate = reevaluate
        self._repo = _ReviewRepository()

    def latest_verification_id(self, canonical_job_id: str) -> str | None:
        with self.db.connection() as conn:
            row = conn.execute(
                """
                SELECT verification_id FROM verification_cases
                WHERE canonical_job_id = ?
                ORDER BY opened_at DESC LIMIT 1
                """,
                (canonical_job_id,),
            ).fetchone()
        return row[0] if row is not None else None

    def has_absolute_hard_gate(self, verification_id: str) -> bool:
        with self.db.connection() as conn:
            row = conn.execute(
                "SELECT hard_gate_hits_json FROM job_verification_snapshots "
                "WHERE verification_id = ?",
                (verification_id,),
            ).fetchone()
        if row is None:
            return False
        import json

        return bool(json.loads(row[0]))

    def trigger_reevaluation(self, canonical_job_id: str, *, now: datetime) -> None:
        self._reevaluate(canonical_job_id, now=now)


def create_internal_review_router(
    db: Database,
    *,
    actor_resolver: Callable[[], dict],
    now_factory: Callable[[], datetime],
    reevaluate: Callable[..., None],
) -> APIRouter:
    router = APIRouter(prefix="/internal/verification")
    store = _StoreAdapter(db, reevaluate=reevaluate)
    service = ReviewCommandService(db, store=store)
    repo = _ReviewRepository()

    def _actor() -> ReviewActor:
        raw = actor_resolver()
        return ReviewActor(actor_id=raw["actor_id"], roles=tuple(raw.get("roles", ())))

    @router.get("/cases")
    def list_cases():
        actor = _actor()
        if not (set(actor.roles) & {"job_verifier", "trust_admin"}):
            raise HTTPException(status_code=403, detail={"error_code": "UNAUTHORIZED_ACTOR"})
        with db.connection() as conn:
            rows = conn.execute(
                "SELECT case_id, canonical_job_id, state, priority FROM verification_cases "
                "ORDER BY opened_at DESC"
            ).fetchall()
        return [
            {
                "case_id": row[0],
                "canonical_job_id": row[1],
                "state": row[2],
                "priority": row[3],
            }
            for row in rows
        ]

    @router.get("/cases/{case_id}")
    def get_case(case_id: str):
        actor = _actor()
        if not (set(actor.roles) & {"job_verifier", "trust_admin"}):
            raise HTTPException(status_code=403, detail={"error_code": "UNAUTHORIZED_ACTOR"})
        with db.connection() as conn:
            case = repo.get_case(conn, case_id)
        if case is None:
            raise HTTPException(status_code=404, detail={"error_code": "NOT_FOUND"})
        # Reviewer-only notes are not exposed here; only case metadata.
        return {
            "case_id": case["case_id"],
            "canonical_job_id": case["canonical_job_id"],
            "verification_id": case["verification_id"],
            "state": case["state"],
            "priority": case["priority"],
        }

    @router.post("/cases/{case_id}/resolve")
    def resolve_case(case_id: str, body: ResolveCaseBody):
        actor = _actor()
        try:
            resolution = service.resolve_case(
                actor=actor,
                case_id=case_id,
                expected_verification_id=body.expected_verification_id,
                idempotency_key=body.idempotency_key,
                decision=ReviewDecision(body.decision),
                reason_codes=tuple(body.reason_codes),
                now=now_factory(),
                notes=body.notes,
            )
        except ReviewAuthorizationDenied:
            raise HTTPException(status_code=403, detail={"error_code": "UNAUTHORIZED_ACTOR"})
        except StaleReviewContext:
            raise HTTPException(status_code=409, detail={"error_code": "STALE_REVIEW_CONTEXT"})
        except IdempotencyConflict:
            raise HTTPException(status_code=409, detail={"error_code": "IDEMPOTENCY_CONFLICT"})
        except HardGateNotReviewOverrideable:
            raise HTTPException(
                status_code=422, detail={"error_code": "HARD_GATE_NOT_OVERRIDEABLE"}
            )
        except LookupError:
            raise HTTPException(status_code=404, detail={"error_code": "NOT_FOUND"})
        return {"resolution_id": resolution.resolution_id, "decision": resolution.decision.value}

    return router
