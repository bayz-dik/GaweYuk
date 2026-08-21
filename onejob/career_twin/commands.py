from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime
from typing import Callable, Protocol

from onejob.career_twin.errors import (
    AuthorizationDenied,
    ConflictNotFound,
    InvalidConflictResolution,
    StaleClaimState,
    StaleConflictState,
    StaleSuggestionState,
    SuggestionNotFound,
)
from onejob.career_twin.idempotency import (
    IdempotencyOutcome,
    request_fingerprint,
    reserve_idempotency,
)
from onejob.career_twin.ontology import (
    EntityType,
    Predicate,
    PrivacyClass,
    predicate_spec,
)
from onejob.career_twin.repositories import (
    ConflictSetRepository,
    IdempotencyRepository,
    SuggestionRepository,
    SuppressionRepository,
)
from onejob.career_twin.conflicts import ConflictStatus
from onejob.career_twin.models import CareerEvidence, EntityLifecycle, CareerEntity
from onejob.career_twin.repositories import CareerEvidenceRepository
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


@dataclass(frozen=True)
class SubmitDirectFactCommand:
    twin_id: str
    entity_intent: str  # CREATE_NEW | EDIT_EXISTING
    predicate: Predicate
    value: object
    value_type: str
    expected_active_claim_id: str | None
    source_type: str
    evidence_family_id: str
    payload_fingerprint: str
    idempotency_key: str
    entity_id: str | None = None
    proposed_entity_type: EntityType | None = None
    trust_tier: str = "TIER_SELF"
    independence_status: str = "INDEPENDENT"
    privacy_class: PrivacyClass = PrivacyClass.CAREER_PRIVATE


@dataclass(frozen=True)
class ResolveConflictCommand:
    twin_id: str
    conflict_id: str
    action: str  # KEEP_CURRENT | ACCEPT_ALTERNATIVE | EDIT_AND_ACCEPT | DEFER
    selected_suggestion_id: str | None
    expected_active_claim_id: str | None
    expected_conflict_version: int
    idempotency_key: str
    edited_value: object | None = None


@dataclass(frozen=True)
class LiftSuppressionCommand:
    twin_id: str
    suppression_id: str
    idempotency_key: str


@dataclass(frozen=True)
class DirectFactResult:
    claim_id: str
    replay: bool = False


@dataclass(frozen=True)
class ResolveConflictResult:
    conflict_id: str
    claim_id: str | None
    replay: bool = False


@dataclass(frozen=True)
class LiftSuppressionResult:
    suppression_id: str
    replay: bool = False


class SuggestionCommandService:
    def __init__(self, db: Database, *, id_factory: IdFactory):
        self.db = db
        self.id_factory = id_factory
        self.canonical = CareerTwinCommandService(db, id_factory=id_factory)
        self.suggestions = SuggestionRepository()
        self.suppression = SuppressionRepository()
        self.idempotency = IdempotencyRepository()
        self.conflicts = ConflictSetRepository()
        self.evidence = CareerEvidenceRepository()

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
    # Submit direct fact
    # ------------------------------------------------------------------

    def submit_direct_fact(
        self,
        command: SubmitDirectFactCommand,
        *,
        actor: Actor,
        now: datetime,
    ) -> DirectFactResult:
        # Canonical direct-fact approval requires an owner-authorized human
        # actor. A non-human import actor may not invoke this path even if it
        # labels its source USER_INPUT.
        _require_owner(actor, command.twin_id)

        if command.entity_intent not in ("CREATE_NEW", "EDIT_EXISTING"):
            raise ValueError(
                f"invalid entity_intent: {command.entity_intent}"
            )
        if command.entity_intent == "EDIT_EXISTING" and not command.entity_id:
            raise ValueError(
                "EDIT_EXISTING requires target entity_id"
            )
        if command.entity_intent == "CREATE_NEW" and (
            command.proposed_entity_type is None
        ):
            raise ValueError(
                "CREATE_NEW requires proposed_entity_type"
            )

        fingerprint = request_fingerprint(
            {
                "kind": "direct_fact",
                "twin_id": command.twin_id,
                "entity_intent": command.entity_intent,
                "entity_id": command.entity_id,
                "predicate": command.predicate.value,
                "value": command.value,
                "expected_active_claim_id": command.expected_active_claim_id,
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
                return DirectFactResult(
                    claim_id=outcome.result_reference,
                    replay=True,
                )

            spec = predicate_spec(command.predicate)

            if command.entity_intent == "CREATE_NEW":
                entity_id = self.id_factory("entity")
                self.canonical.entities.insert(
                    conn,
                    CareerEntity(
                        entity_id=entity_id,
                        twin_id=command.twin_id,
                        entity_type=command.proposed_entity_type,
                        lifecycle_state=EntityLifecycle.ACTIVE,
                        created_at=now,
                    ),
                )
            else:
                entity_id = command.entity_id

            # Register USER_INPUT evidence (reference/fingerprint only).
            evidence_id = self.id_factory("evidence")
            self.evidence.insert(
                conn,
                CareerEvidence(
                    evidence_id=evidence_id,
                    twin_id=command.twin_id,
                    source_type=command.source_type,
                    evidence_family_id=command.evidence_family_id,
                    observed_at=now,
                    payload_fingerprint=command.payload_fingerprint,
                    trust_tier=command.trust_tier,
                    independence_status=command.independence_status,
                    privacy_class=command.privacy_class,
                ),
            )

            claim = self.canonical.approve_claim_in_transaction(
                conn,
                ApproveClaimCommand(
                    twin_id=command.twin_id,
                    entity_id=entity_id,
                    predicate=command.predicate,
                    value=command.value,
                    value_type=spec.value_type,
                    evidence_ids=(evidence_id,),
                    expected_active_claim_id=command.expected_active_claim_id,
                    ontology_version=spec.ontology_version,
                ),
                now=now,
            )

            self._record_result(
                conn, command.idempotency_key, claim.claim_id
            )

            return DirectFactResult(claim_id=claim.claim_id)

    # ------------------------------------------------------------------
    # Resolve conflict
    # ------------------------------------------------------------------

    def resolve_conflict(
        self,
        command: ResolveConflictCommand,
        *,
        actor: Actor,
        now: datetime,
    ) -> ResolveConflictResult:
        _require_owner(actor, command.twin_id)

        valid_actions = {
            "KEEP_CURRENT",
            "ACCEPT_ALTERNATIVE",
            "EDIT_AND_ACCEPT",
            "DEFER",
        }
        if command.action not in valid_actions:
            raise InvalidConflictResolution(
                f"invalid conflict action: {command.action}"
            )

        fingerprint = request_fingerprint(
            {
                "kind": "resolve_conflict",
                "twin_id": command.twin_id,
                "conflict_id": command.conflict_id,
                "action": command.action,
                "selected_suggestion_id": command.selected_suggestion_id,
                "expected_active_claim_id": command.expected_active_claim_id,
                "expected_conflict_version": (
                    command.expected_conflict_version
                ),
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
                return ResolveConflictResult(
                    conflict_id=command.conflict_id,
                    claim_id=outcome.result_reference,
                    replay=True,
                )

            conflict = self.conflicts.get(conn, command.conflict_id)
            if conflict is None or conflict.twin_id != command.twin_id:
                raise ConflictNotFound(
                    f"conflict not found: {command.conflict_id}"
                )
            if conflict.version != command.expected_conflict_version:
                raise StaleConflictState(
                    "stale conflict version: "
                    f"expected={command.expected_conflict_version} "
                    f"actual={conflict.version}"
                )

            # DEFER changes no canonical truth and leaves the conflict open.
            if command.action == "DEFER":
                self._record_result(
                    conn, command.idempotency_key, ""
                )
                return ResolveConflictResult(
                    conflict_id=conflict.conflict_id,
                    claim_id=None,
                )

            # Validate the caller's view of the active claim.
            current = self.canonical.claims.active_for_family(
                conn,
                conflict.twin_id,
                conflict.entity_id,
                conflict.predicate,
            )
            actual_active = current.claim_id if current is not None else None
            if actual_active != command.expected_active_claim_id:
                raise StaleClaimState(
                    "stale active claim: "
                    f"expected={command.expected_active_claim_id} "
                    f"actual={actual_active}"
                )

            resolution_claim_id: str | None = None
            resolution_type = command.action

            if command.action == "KEEP_CURRENT":
                # Preserve the active claim; reject the competing suggestion.
                if command.selected_suggestion_id is not None:
                    suggestion = self._load_suggestion(
                        conn,
                        command.selected_suggestion_id,
                        command.twin_id,
                    )
                    rejected = suggestion.with_transition(
                        SuggestionAction.KEEP_CURRENT,
                        decided_at=now,
                        decision_actor_id=actor.get("actor_id"),
                    )
                    self.suggestions.update_versioned(
                        conn, rejected, expected_version=suggestion.version
                    )
                resolution_claim_id = actual_active

            else:
                # ACCEPT_ALTERNATIVE / EDIT_AND_ACCEPT supersede current claim.
                if command.selected_suggestion_id is None:
                    raise InvalidConflictResolution(
                        "selected_suggestion_id required for "
                        f"{command.action}"
                    )
                suggestion = self._load_suggestion(
                    conn, command.selected_suggestion_id, command.twin_id
                )
                entity_id = suggestion.resolved_entity_id or conflict.entity_id
                value = (
                    command.edited_value
                    if command.edited_value is not None
                    else suggestion.proposed_value
                )
                spec = predicate_spec(suggestion.predicate)
                evidence_ids = tuple(
                    self.suggestions.evidence_ids(
                        conn, suggestion.suggestion_id
                    )
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
                        expected_active_claim_id=(
                            command.expected_active_claim_id
                        ),
                        ontology_version=spec.ontology_version,
                    ),
                    now=now,
                )
                resolution_claim_id = claim.claim_id

                action = (
                    SuggestionAction.EDIT_AND_ACCEPT
                    if command.edited_value is not None
                    else SuggestionAction.ACCEPT_ALTERNATIVE
                )
                approved = suggestion.model_copy(
                    update={"resolved_entity_id": entity_id}
                ).with_transition(
                    action,
                    decided_at=now,
                    decision_actor_id=actor.get("actor_id"),
                )
                self.suggestions.update_versioned(
                    conn, approved, expected_version=suggestion.version
                )

            resolved = conflict.model_copy(
                update={
                    "status": ConflictStatus.RESOLVED,
                    "version": conflict.version + 1,
                    "resolved_at": now,
                    "resolution_type": resolution_type,
                    "resolution_claim_id": resolution_claim_id,
                    "active_claim_id": resolution_claim_id,
                }
            )
            self.conflicts.update_versioned(
                conn, resolved, expected_version=conflict.version
            )

            self.canonical._append_event(
                conn,
                twin_id=command.twin_id,
                event_type="CONFLICT_RESOLVED",
                subject_id=conflict.conflict_id,
                payload={
                    "conflict_id": conflict.conflict_id,
                    "resolution_type": resolution_type,
                    "resolution_claim_id": resolution_claim_id,
                },
                now=now,
            )

            self._record_result(
                conn,
                command.idempotency_key,
                resolution_claim_id or "",
            )

            return ResolveConflictResult(
                conflict_id=conflict.conflict_id,
                claim_id=resolution_claim_id,
            )

    # ------------------------------------------------------------------
    # Lift suppression
    # ------------------------------------------------------------------

    def lift_suppression(
        self,
        command: LiftSuppressionCommand,
        *,
        actor: Actor,
        now: datetime,
    ) -> LiftSuppressionResult:
        _require_owner(actor, command.twin_id)

        fingerprint = request_fingerprint(
            {
                "kind": "lift_suppression",
                "twin_id": command.twin_id,
                "suppression_id": command.suppression_id,
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
                return LiftSuppressionResult(
                    suppression_id=command.suppression_id,
                    replay=True,
                )

            self.suppression.lift(conn, command.suppression_id, now=now)

            self.canonical._append_event(
                conn,
                twin_id=command.twin_id,
                event_type="SUPPRESSION_LIFTED",
                subject_id=command.suppression_id,
                payload={"suppression_id": command.suppression_id},
                now=now,
            )

            self._record_result(
                conn, command.idempotency_key, command.suppression_id
            )

            return LiftSuppressionResult(
                suppression_id=command.suppression_id
            )

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
