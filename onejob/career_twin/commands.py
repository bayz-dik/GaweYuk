from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime
from typing import Callable, Protocol

from onejob.career_twin.errors import (
    AuthorizationDenied,
    StaleSuggestionState,
    SuggestionNotFound,
)
from onejob.career_twin.idempotency import (
    IdempotencyOutcome,
    request_fingerprint,
    reserve_idempotency,
)
from onejob.career_twin.ontology import Predicate, predicate_spec
from onejob.career_twin.repositories import (
    IdempotencyRepository,
    SuggestionRepository,
    SuppressionRepository,
)
from onejob.career_twin.suggestions import (
    AtomicSuggestion,
    DecisionState,
    SuggestionAction,
)
from onejob.career_twin.suppression import (
    SuppressionRecord,
    SuppressionStrength,
    suppression_fingerprint,
)
from onejob.career_twin.service import (
    ApproveClaimCommand,
    CareerTwinCommandService,
)
from onejob.persistence.db import Database


class IdFactory(Protocol):
    def __call__(self, kind: str) -> str:
        ...


Actor = dict


def _require_owner(actor: Actor, twin_id: str) -> None:
    if actor is None:
        raise AuthorizationDenied("missing actor context")
    if not actor.get("is_owner"):
        raise AuthorizationDenied("actor is not the twin owner")
    if actor.get("twin_id") != twin_id:
        raise AuthorizationDenied("actor not authorized for twin")


@dataclass(frozen=True)
class ApproveSuggestionCommand:
    twin_id: str
    suggestion_id: str
    expected_suggestion_version: int
    expected_active_claim_id: str | None
    selected_entity_id: str | None
    idempotency_key: str
    edited_value: object | None = None


@dataclass(frozen=True)
class RejectSuggestionCommand:
    twin_id: str
    suggestion_id: str
    expected_suggestion_version: int
    reason: str | None
    suppression_mode: str  # NONE | SOFT | STRONG
    idempotency_key: str


@dataclass(frozen=True)
class ApproveResult:
    claim_id: str
    suggestion_id: str
    replay: bool = False


@dataclass(frozen=True)
class RejectResult:
    suggestion_id: str
    replay: bool = False


class SuggestionCommandService:
    def __init__(self, db: Database, *, id_factory: IdFactory):
        self.db = db
        self.id_factory = id_factory
        self.canonical = CareerTwinCommandService(db, id_factory=id_factory)
        self.suggestions = SuggestionRepository()
        self.suppression = SuppressionRepository()
        self.idempotency = IdempotencyRepository()

        # Test hook for atomicity/failure injection. Called after the
        # canonical claim is created but before the transaction commits.
        self._after_claim_hook: Callable[..., None] | None = None

    # ------------------------------------------------------------------
    # Approve
    # ------------------------------------------------------------------

    def approve(
        self,
        command: ApproveSuggestionCommand,
        *,
        actor: Actor,
        now: datetime,
    ) -> ApproveResult:
        _require_owner(actor, command.twin_id)

        fingerprint = request_fingerprint(
            {
                "kind": "approve",
                "twin_id": command.twin_id,
                "suggestion_id": command.suggestion_id,
                "expected_suggestion_version": (
                    command.expected_suggestion_version
                ),
                "expected_active_claim_id": command.expected_active_claim_id,
                "selected_entity_id": command.selected_entity_id,
                "edited_value": command.edited_value,
            }
        )

        with self.db.transaction() as conn:
            outcome = reserve_idempotency(
                conn,
                self.idempotency,
                idempotency_key=command.idempotency_key,
                fingerprint=fingerprint,
                now=now,
            )
            if outcome.replay:
                return ApproveResult(
                    claim_id=outcome.result_reference,
                    suggestion_id=command.suggestion_id,
                    replay=True,
                )

            suggestion = self._load_suggestion(
                conn, command.suggestion_id, command.twin_id
            )

            if suggestion.version != command.expected_suggestion_version:
                raise StaleSuggestionState(
                    "stale suggestion version: "
                    f"expected={command.expected_suggestion_version} "
                    f"actual={suggestion.version}"
                )

            entity_id = (
                command.selected_entity_id or suggestion.resolved_entity_id
            )
            if entity_id is None:
                raise AuthorizationDenied(
                    "approval requires a resolved/selected entity"
                )

            value = (
                command.edited_value
                if command.edited_value is not None
                else suggestion.proposed_value
            )
            spec = predicate_spec(suggestion.predicate)

            evidence_ids = tuple(
                self.suggestions.evidence_ids(conn, suggestion.suggestion_id)
            )

            claim = self.canonical.approve_claim_in_transaction(
                conn,
                ApproveClaimCommand(
                    twin_id=command.twin_id,
                    entity_id=entity_id,
                    predicate=suggestion.predicate,
                    value=value,
                    value_type=spec.value_type,
                    evidence_ids=evidence_ids,
                    expected_active_claim_id=command.expected_active_claim_id,
                    ontology_version=spec.ontology_version,
                ),
                now=now,
            )

            if self._after_claim_hook is not None:
                self._after_claim_hook(conn, claim=claim)

            # Only now, after canonical success, mark the suggestion APPROVED.
            action = (
                SuggestionAction.EDIT_AND_ACCEPT
                if command.edited_value is not None
                else SuggestionAction.APPROVE
            )
            approved = suggestion.model_copy(
                update={"resolved_entity_id": entity_id}
            ).with_transition(
                action,
                decided_at=now,
                decision_actor_id=actor.get("actor_id"),
            )
            self.suggestions.update_versioned(
                conn,
                approved,
                expected_version=suggestion.version,
            )

            self.canonical._append_event(
                conn,
                twin_id=command.twin_id,
                event_type="SUGGESTION_APPROVED",
                subject_id=suggestion.suggestion_id,
                payload={
                    "suggestion_id": suggestion.suggestion_id,
                    "claim_id": claim.claim_id,
                    "predicate": suggestion.predicate.value,
                },
                now=now,
            )

            self._record_result(
                conn, command.idempotency_key, claim.claim_id
            )

            return ApproveResult(
                claim_id=claim.claim_id,
                suggestion_id=suggestion.suggestion_id,
            )

    # ------------------------------------------------------------------
    # Reject
    # ------------------------------------------------------------------

    def reject(
        self,
        command: RejectSuggestionCommand,
        *,
        actor: Actor,
        now: datetime,
    ) -> RejectResult:
        _require_owner(actor, command.twin_id)

        if command.suppression_mode not in ("NONE", "SOFT", "STRONG"):
            raise ValueError(
                f"invalid suppression_mode: {command.suppression_mode}"
            )

        fingerprint = request_fingerprint(
            {
                "kind": "reject",
                "twin_id": command.twin_id,
                "suggestion_id": command.suggestion_id,
                "expected_suggestion_version": (
                    command.expected_suggestion_version
                ),
                "reason": command.reason,
                "suppression_mode": command.suppression_mode,
            }
        )

        with self.db.transaction() as conn:
            outcome = reserve_idempotency(
                conn,
                self.idempotency,
                idempotency_key=command.idempotency_key,
                fingerprint=fingerprint,
                now=now,
            )
            if outcome.replay:
                return RejectResult(
                    suggestion_id=command.suggestion_id,
                    replay=True,
                )

            suggestion = self._load_suggestion(
                conn, command.suggestion_id, command.twin_id
            )

            if suggestion.version != command.expected_suggestion_version:
                raise StaleSuggestionState(
                    "stale suggestion version: "
                    f"expected={command.expected_suggestion_version} "
                    f"actual={suggestion.version}"
                )

            suppress = command.suppression_mode in ("SOFT", "STRONG")
            rejected = suggestion.with_transition(
                SuggestionAction.REJECT,
                decided_at=now,
                decision_actor_id=actor.get("actor_id"),
                suppress=suppress,
            )
            self.suggestions.update_versioned(
                conn,
                rejected,
                expected_version=suggestion.version,
            )

            if suppress:
                strength = (
                    SuppressionStrength.STRONG
                    if command.suppression_mode == "STRONG"
                    else SuppressionStrength.SOFT
                )
                self.suppression.insert(
                    conn,
                    SuppressionRecord(
                        suppression_id=self.id_factory("suppression"),
                        twin_id=command.twin_id,
                        entity_scope=suggestion.resolved_entity_id,
                        candidate_scope=suggestion.candidate_id,
                        predicate=suggestion.predicate,
                        normalized_value_fingerprint=(
                            suggestion.normalized_value_fingerprint
                        ),
                        strength=strength,
                        reason=command.reason,
                        created_at=now,
                    ),
                )
                self.canonical._append_event(
                    conn,
                    twin_id=command.twin_id,
                    event_type="SUPPRESSION_CREATED",
                    subject_id=suggestion.suggestion_id,
                    payload={
                        "suggestion_id": suggestion.suggestion_id,
                        "strength": strength.value,
                    },
                    now=now,
                )

            self.canonical._append_event(
                conn,
                twin_id=command.twin_id,
                event_type="SUGGESTION_REJECTED",
                subject_id=suggestion.suggestion_id,
                payload={
                    "suggestion_id": suggestion.suggestion_id,
                    "suppression_mode": command.suppression_mode,
                },
                now=now,
            )

            self._record_result(
                conn, command.idempotency_key, suggestion.suggestion_id
            )

            return RejectResult(suggestion_id=suggestion.suggestion_id)

    # ------------------------------------------------------------------
    # helpers
    # ------------------------------------------------------------------

    def _load_suggestion(
        self,
        conn: sqlite3.Connection,
        suggestion_id: str,
        twin_id: str,
    ) -> AtomicSuggestion:
        suggestion = self.suggestions.get(conn, suggestion_id)
        if suggestion is None or suggestion.twin_id != twin_id:
            raise SuggestionNotFound(
                f"suggestion not found: {suggestion_id}"
            )
        return suggestion

    def _record_result(
        self,
        conn: sqlite3.Connection,
        idempotency_key: str,
        result_reference: str,
    ) -> None:
        conn.execute(
            """
            UPDATE career_idempotency_keys
            SET result_reference = ?
            WHERE idempotency_key = ?
            """,
            (result_reference, idempotency_key),
        )
