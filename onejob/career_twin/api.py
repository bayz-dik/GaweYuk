from __future__ import annotations

from typing import Callable

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from onejob.career_twin.commands import (
    ApproveSuggestionCommand,
    LiftSuppressionCommand,
    RejectSuggestionCommand,
    ResolveConflictCommand,
    SubmitDirectFactCommand,
    SuggestionCommandService,
)
from onejob.career_twin.errors import (
    AuthorizationDenied,
    CandidateNotFound,
    CareerTwinError,
    ConflictNotFound,
    DuplicateSuggestion,
    IdempotencyConflict,
    InvalidConflictResolution,
    InvalidEntityResolution,
    InvalidSuggestionTransition,
    OntologyViolation,
    PrivacyBoundaryViolation,
    StaleClaimState,
    StaleConflictState,
    StaleSuggestionState,
    SuggestionNotFound,
    SuppressedSuggestion,
)
from onejob.career_twin.ontology import Predicate
from onejob.career_twin.repositories import (
    ConflictSetRepository,
    SuggestionRepository,
)
from onejob.career_twin.suggestions import DecisionState, Disposition
from onejob.persistence.db import Database


# Stable error -> HTTP status mapping (spec section 21).
_ERROR_STATUS: dict[type, int] = {
    AuthorizationDenied: 403,
    PrivacyBoundaryViolation: 403,
    SuggestionNotFound: 404,
    CandidateNotFound: 404,
    ConflictNotFound: 404,
    StaleSuggestionState: 409,
    StaleClaimState: 409,
    StaleConflictState: 409,
    IdempotencyConflict: 409,
    DuplicateSuggestion: 409,
    SuppressedSuggestion: 409,
    OntologyViolation: 422,
    InvalidEntityResolution: 422,
    InvalidSuggestionTransition: 422,
    InvalidConflictResolution: 422,
}

# Stable, non-leaking client messages per status.
_STATUS_MESSAGE = {
    400: "malformed or structurally invalid command",
    403: "authorization or privacy denied",
    404: "resource not found",
    409: "command conflict or stale state",
    422: "domain validation failed",
    500: "internal error",
}


def _safe_suggestion(suggestion) -> dict:
    """Project a suggestion to safe, website-ready fields only.

    Never exposes normalized fingerprints, raw payloads, secrets, or internal
    storage details.
    """
    return {
        "suggestion_id": suggestion.suggestion_id,
        "batch_id": suggestion.batch_id,
        "candidate_id": suggestion.candidate_id,
        "resolved_entity_id": suggestion.resolved_entity_id,
        "predicate": suggestion.predicate.value,
        "proposed_value": suggestion.proposed_value,
        "value_type": suggestion.value_type,
        "decision_state": suggestion.decision_state.value,
        "disposition": suggestion.disposition.value,
        "version": suggestion.version,
    }


def _safe_conflict(conflict) -> dict:
    return {
        "conflict_id": conflict.conflict_id,
        "entity_id": conflict.entity_id,
        "predicate": conflict.predicate.value,
        "status": conflict.status.value,
        "version": conflict.version,
    }


class ApproveBody(BaseModel):
    expected_suggestion_version: int
    idempotency_key: str
    expected_active_claim_id: str | None = None
    selected_entity_id: str | None = None
    edited_value: object | None = None


class RejectBody(BaseModel):
    expected_suggestion_version: int
    suppression_mode: str
    idempotency_key: str
    reason: str | None = None


class DirectFactBody(BaseModel):
    entity_intent: str
    predicate: str
    value: object
    value_type: str
    source_type: str
    evidence_family_id: str
    payload_fingerprint: str
    idempotency_key: str
    expected_active_claim_id: str | None = None
    entity_id: str | None = None
    proposed_entity_type: str | None = None


class ResolveConflictBody(BaseModel):
    action: str
    expected_active_claim_id: str | None
    expected_conflict_version: int
    idempotency_key: str
    selected_suggestion_id: str | None = None
    edited_value: object | None = None


def create_career_twin_router(
    db: Database,
    *,
    id_factory: Callable[[str], str],
    actor_resolver: Callable[[], dict],
    now_factory: Callable[[], object],
) -> APIRouter:
    router = APIRouter(prefix="/api/career-twin")
    commands = SuggestionCommandService(db, id_factory=id_factory)
    suggestions = SuggestionRepository()
    conflicts = ConflictSetRepository()

    def _twin_id() -> str:
        actor = actor_resolver()
        return actor["twin_id"]

    def _handle(exc: Exception) -> HTTPException:
        if isinstance(exc, HTTPException):
            return exc
        status = _ERROR_STATUS.get(type(exc))
        if status is None and isinstance(exc, CareerTwinError):
            status = 422
        if status is None and isinstance(exc, ValueError):
            status = 400
        if status is None:
            status = 500
        return HTTPException(
            status_code=status,
            detail=_STATUS_MESSAGE.get(status, "error"),
        )

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    @router.get("/suggestions")
    def list_suggestions(
        decision_state: str | None = None,
        disposition: str | None = None,
        batch_id: str | None = None,
    ):
        try:
            ds = DecisionState(decision_state) if decision_state else None
            disp = Disposition(disposition) if disposition else None
        except ValueError:
            raise HTTPException(status_code=400, detail=_STATUS_MESSAGE[400])

        with db.connection() as conn:
            items = suggestions.list_for_twin(
                conn,
                _twin_id(),
                decision_state=ds,
                disposition=disp,
                batch_id=batch_id,
            )
        return [_safe_suggestion(s) for s in items]

    @router.get("/suggestions/{suggestion_id}")
    def get_suggestion(suggestion_id: str):
        with db.connection() as conn:
            suggestion = suggestions.get(conn, suggestion_id)
        if suggestion is None or suggestion.twin_id != _twin_id():
            raise HTTPException(
                status_code=404, detail=_STATUS_MESSAGE[404]
            )
        return _safe_suggestion(suggestion)

    @router.get("/conflicts/{conflict_id}")
    def get_conflict(conflict_id: str):
        with db.connection() as conn:
            conflict = conflicts.get(conn, conflict_id)
        if conflict is None or conflict.twin_id != _twin_id():
            raise HTTPException(
                status_code=404, detail=_STATUS_MESSAGE[404]
            )
        return _safe_conflict(conflict)

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    @router.post("/suggestions/{suggestion_id}/approve")
    def approve(suggestion_id: str, body: ApproveBody):
        actor = actor_resolver()
        try:
            result = commands.approve(
                ApproveSuggestionCommand(
                    twin_id=actor["twin_id"],
                    suggestion_id=suggestion_id,
                    expected_suggestion_version=(
                        body.expected_suggestion_version
                    ),
                    expected_active_claim_id=body.expected_active_claim_id,
                    selected_entity_id=body.selected_entity_id,
                    edited_value=body.edited_value,
                    idempotency_key=body.idempotency_key,
                ),
                actor=actor,
                now=now_factory(),
            )
        except Exception as exc:
            raise _handle(exc)
        return {"claim_id": result.claim_id, "suggestion_id": result.suggestion_id}

    @router.post("/suggestions/{suggestion_id}/reject")
    def reject(suggestion_id: str, body: RejectBody):
        actor = actor_resolver()
        try:
            result = commands.reject(
                RejectSuggestionCommand(
                    twin_id=actor["twin_id"],
                    suggestion_id=suggestion_id,
                    expected_suggestion_version=(
                        body.expected_suggestion_version
                    ),
                    reason=body.reason,
                    suppression_mode=body.suppression_mode,
                    idempotency_key=body.idempotency_key,
                ),
                actor=actor,
                now=now_factory(),
            )
        except Exception as exc:
            raise _handle(exc)
        return {"suggestion_id": result.suggestion_id}

    @router.post("/facts")
    def submit_fact(body: DirectFactBody):
        actor = actor_resolver()
        try:
            predicate = Predicate(body.predicate)
            proposed_entity_type = None
            if body.proposed_entity_type is not None:
                from onejob.career_twin.ontology import EntityType

                proposed_entity_type = EntityType(body.proposed_entity_type)
            result = commands.submit_direct_fact(
                SubmitDirectFactCommand(
                    twin_id=actor["twin_id"],
                    entity_intent=body.entity_intent,
                    entity_id=body.entity_id,
                    proposed_entity_type=proposed_entity_type,
                    predicate=predicate,
                    value=body.value,
                    value_type=body.value_type,
                    expected_active_claim_id=body.expected_active_claim_id,
                    source_type=body.source_type,
                    evidence_family_id=body.evidence_family_id,
                    payload_fingerprint=body.payload_fingerprint,
                    idempotency_key=body.idempotency_key,
                ),
                actor=actor,
                now=now_factory(),
            )
        except Exception as exc:
            raise _handle(exc)
        return {"claim_id": result.claim_id}

    @router.post("/conflicts/{conflict_id}/resolve")
    def resolve_conflict(conflict_id: str, body: ResolveConflictBody):
        actor = actor_resolver()
        try:
            result = commands.resolve_conflict(
                ResolveConflictCommand(
                    twin_id=actor["twin_id"],
                    conflict_id=conflict_id,
                    action=body.action,
                    selected_suggestion_id=body.selected_suggestion_id,
                    expected_active_claim_id=body.expected_active_claim_id,
                    expected_conflict_version=body.expected_conflict_version,
                    edited_value=body.edited_value,
                    idempotency_key=body.idempotency_key,
                ),
                actor=actor,
                now=now_factory(),
            )
        except Exception as exc:
            raise _handle(exc)
        return {
            "conflict_id": result.conflict_id,
            "claim_id": result.claim_id,
        }

    @router.post("/suppressions/{suppression_id}/lift")
    def lift_suppression(suppression_id: str, idempotency_key: str):
        actor = actor_resolver()
        try:
            result = commands.lift_suppression(
                LiftSuppressionCommand(
                    twin_id=actor["twin_id"],
                    suppression_id=suppression_id,
                    idempotency_key=idempotency_key,
                ),
                actor=actor,
                now=now_factory(),
            )
        except Exception as exc:
            raise _handle(exc)
        return {"suppression_id": result.suppression_id}

    return router
