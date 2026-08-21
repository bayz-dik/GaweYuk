from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Protocol

from onejob.career_intent.models import (
    CareerIntentVersionRecord,
    IntentOperator,
    IntentStatementRecord,
    IntentStrength,
    UnknownPolicy,
)
from onejob.career_intent.repositories import (
    CareerIntentRepository,
    StaleIntentPointer,
)
from onejob.career_intent.validation import (
    IntentValidationStatus,
    validate_intent_statements,
)
from onejob.career_twin.errors import AuthorizationDenied, CareerTwinError
from onejob.career_twin.events import CareerEvent
from onejob.career_twin.idempotency import (
    request_fingerprint,
    reserve_idempotency,
)
from onejob.career_twin.repositories import (
    CareerEventRepository,
    IdempotencyRepository,
)
from onejob.persistence.db import Database


class IdFactory(Protocol):
    def __call__(self, kind: str) -> str:
        ...


Actor = dict


class StaleIntentVersion(CareerTwinError):
    pass


class UnsatisfiableIntent(CareerTwinError):
    pass


def require_intent_authority(actor: Actor, twin_id: str) -> None:
    """Only an owner-authorized USER actor may create/activate Career Intent.

    AI/SYSTEM/inference actors may never activate authoritative intent — even
    at high confidence. Confidence is not authority.
    """
    if actor is None:
        raise AuthorizationDenied("missing actor context")
    if actor.get("twin_id") != twin_id:
        raise AuthorizationDenied("actor not authorized for twin")
    if not actor.get("is_owner"):
        raise AuthorizationDenied("actor is not the twin owner")
    actor_type = actor.get("actor_type", "USER")
    if actor_type != "USER":
        raise AuthorizationDenied(
            f"actor type {actor_type} may not activate Career Intent"
        )


@dataclass(frozen=True)
class NewIntentStatement:
    predicate: str
    operator: str
    value: Any
    strength: str
    value_type: str
    unknown_policy: str | None = None
    effective_from: datetime | None = None
    expires_at: datetime | None = None
    provenance: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class CreateCareerIntentVersionCommand:
    actor_id: str
    twin_id: str
    idempotency_key: str
    expected_active_version_id: str | None
    statements: list[NewIntentStatement]


@dataclass(frozen=True)
class CareerIntentVersionResult:
    intent_id: str
    intent_version_id: str
    version_number: int
    replay: bool = False


def _canonical_statements_payload(
    statements: list[NewIntentStatement],
) -> list[dict[str, Any]]:
    return [
        {
            "predicate": s.predicate,
            "operator": s.operator,
            "value": s.value,
            "strength": s.strength,
            "value_type": s.value_type,
            "unknown_policy": s.unknown_policy,
            "effective_from": s.effective_from.isoformat()
            if s.effective_from
            else None,
            "expires_at": s.expires_at.isoformat() if s.expires_at else None,
        }
        for s in statements
    ]


class CareerIntentCommandService:
    def __init__(self, db: Database, *, id_factory: IdFactory):
        self.db = db
        self.id_factory = id_factory
        self.intents = CareerIntentRepository()
        self.events = CareerEventRepository()
        self.idempotency = IdempotencyRepository()

    def _append_event(
        self,
        conn,
        *,
        twin_id: str,
        event_type: str,
        subject_id: str,
        payload: dict[str, Any],
        now: datetime,
    ) -> None:
        self.events.append_with_outbox(
            conn,
            CareerEvent(
                event_id=self.id_factory("event"),
                twin_id=twin_id,
                event_type=event_type,
                subject_id=subject_id,
                occurred_at=now,
                payload=payload,
            ),
        )

    def _record_result(self, conn, idempotency_key: str, reference: str) -> None:
        conn.execute(
            """
            UPDATE career_idempotency_keys
            SET result_reference = ?
            WHERE idempotency_key = ?
            """,
            (reference, idempotency_key),
        )

    def create_version(
        self,
        command: CreateCareerIntentVersionCommand,
        *,
        actor: Actor,
        now: datetime,
    ) -> CareerIntentVersionResult:
        require_intent_authority(actor, command.twin_id)

        fingerprint = request_fingerprint(
            {
                "kind": "create_intent_version",
                "twin_id": command.twin_id,
                "expected_active_version_id": command.expected_active_version_id,
                "statements": _canonical_statements_payload(command.statements),
            }
        )

        # Validate BEFORE opening the transaction / moving any pointer.
        with self.db.connection() as conn:
            intent = self.intents.get_for_twin(conn, command.twin_id)

        materialized = self._materialize_statements(
            command.statements, intent_version_id="__pending__"
        )
        validation = validate_intent_statements(materialized, at=now)
        if validation.status == IntentValidationStatus.UNSATISFIABLE.value:
            raise UnsatisfiableIntent(
                "career intent is internally unsatisfiable: "
                + "; ".join(c.reason for c in validation.hard_conflicts)
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
                version = self.intents.get_version(
                    conn, outcome.result_reference
                )
                return CareerIntentVersionResult(
                    intent_id=version.intent_id,
                    intent_version_id=version.intent_version_id,
                    version_number=version.version_number,
                    replay=True,
                )

            intent = self.intents.get_for_twin(conn, command.twin_id)
            if intent is None:
                intent_id = self.id_factory("intent")
                intent = self.intents.create_intent(
                    conn,
                    twin_id=command.twin_id,
                    actor_id=command.actor_id,
                    intent_id=intent_id,
                )

            # Optimistic concurrency: expected active version must match.
            if intent.active_version_id != command.expected_active_version_id:
                raise StaleIntentVersion(
                    "stale expected active intent version: "
                    f"expected={command.expected_active_version_id!r} "
                    f"actual={intent.active_version_id!r}"
                )

            version_number = (
                self.intents.latest_version_number(conn, intent.intent_id) + 1
            )
            intent_version_id = self.id_factory("intent_version")

            version = CareerIntentVersionRecord(
                intent_version_id=intent_version_id,
                intent_id=intent.intent_id,
                version_number=version_number,
                supersedes_version_id=command.expected_active_version_id,
                created_by_actor_id=command.actor_id,
                created_at=now,
                input_fingerprint=fingerprint,
            )
            statements = self._materialize_statements(
                command.statements, intent_version_id=intent_version_id
            )

            self.intents.append_version(
                conn, version=version, statements=statements
            )
            self.intents.move_active_pointer(
                conn,
                intent.intent_id,
                expected_active_version_id=command.expected_active_version_id,
                new_active_version_id=intent_version_id,
            )

            self._append_event(
                conn,
                twin_id=command.twin_id,
                event_type="CareerIntentVersionCreated",
                subject_id=intent_version_id,
                payload={
                    "intent_id": intent.intent_id,
                    "intent_version_id": intent_version_id,
                    "version_number": version_number,
                },
                now=now,
            )
            self._append_event(
                conn,
                twin_id=command.twin_id,
                event_type="CareerIntentActivated",
                subject_id=intent_version_id,
                payload={
                    "intent_id": intent.intent_id,
                    "intent_version_id": intent_version_id,
                },
                now=now,
            )

            self._record_result(conn, command.idempotency_key, intent_version_id)

            return CareerIntentVersionResult(
                intent_id=intent.intent_id,
                intent_version_id=intent_version_id,
                version_number=version_number,
            )

    def _materialize_statements(
        self,
        statements: list[NewIntentStatement],
        *,
        intent_version_id: str,
    ) -> list[IntentStatementRecord]:
        materialized: list[IntentStatementRecord] = []
        for s in statements:
            materialized.append(
                IntentStatementRecord(
                    statement_id=self.id_factory("intent_statement"),
                    intent_version_id=intent_version_id,
                    predicate=s.predicate,
                    operator=IntentOperator(s.operator),
                    value=s.value,
                    value_type=s.value_type,
                    strength=IntentStrength(s.strength),
                    effective_from=s.effective_from,
                    expires_at=s.expires_at,
                    unknown_policy=(
                        UnknownPolicy(s.unknown_policy)
                        if s.unknown_policy is not None
                        else None
                    ),
                    provenance=dict(s.provenance),
                )
            )
        return materialized


# ---------------------------------------------------------------------------
# Task 7: Intent suggestions and suppression
# ---------------------------------------------------------------------------

import hashlib as _hashlib
import json as _json


class InvalidSuggestion(CareerTwinError):
    pass


class SuggestionNotFound(CareerTwinError):
    pass


_SUGGESTION_SOURCES = {
    "USER_PATTERN",
    "OUTCOME_LEARNING",
    "AI_INFERENCE",
    "SYSTEM_INSIGHT",
}


def intent_suggestion_fingerprint(
    *,
    intent_id: str,
    predicate: str,
    proposed_value,
    proposed_strength: str,
    source: str,
) -> str:
    payload = _json.dumps(
        {
            "intent_id": intent_id,
            "predicate": predicate,
            "value": proposed_value,
            "strength": proposed_strength,
            "source": source,
        },
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    return _hashlib.sha256(payload.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class CreateIntentSuggestionCommand:
    actor_id: str
    twin_id: str
    intent_id: str
    idempotency_key: str
    source: str
    predicate: str
    operator: str
    proposed_value: Any
    proposed_strength: str
    evidence: list = field(default_factory=list)
    confidence: float | None = None


@dataclass(frozen=True)
class AcceptIntentSuggestionCommand:
    actor_id: str
    twin_id: str
    suggestion_id: str
    idempotency_key: str
    expected_active_version_id: str | None


@dataclass(frozen=True)
class EditAndAcceptIntentSuggestionCommand:
    actor_id: str
    twin_id: str
    suggestion_id: str
    idempotency_key: str
    expected_active_version_id: str | None
    edited_value: Any
    edited_strength: str


@dataclass(frozen=True)
class RejectIntentSuggestionCommand:
    actor_id: str
    twin_id: str
    suggestion_id: str
    idempotency_key: str
    suppress: bool = False
    reason: str | None = None


@dataclass(frozen=True)
class IntentSuggestionRecord:
    suggestion_id: str
    intent_id: str
    predicate: str
    proposed_value: Any
    proposed_strength: str
    source: str
    decision_state: str
    fingerprint: str


def _suggestion_authority(actor: Actor, twin_id: str) -> None:
    if actor is None or actor.get("twin_id") != twin_id or not actor.get("is_owner"):
        raise AuthorizationDenied("actor not authorized for twin")


class _SuggestionMixin:
    """Mixin providing suggestion workflow on the intent command service."""

    def create_suggestion(
        self,
        command: "CreateIntentSuggestionCommand",
        *,
        actor: Actor,
        now: datetime,
    ) -> IntentSuggestionRecord:
        # A suggestion is a proposal, not an activation. Any authenticated
        # actor for the twin may create one, but inference may never propose a
        # HARD constraint directly.
        _suggestion_authority(actor, command.twin_id)

        if command.source not in _SUGGESTION_SOURCES:
            raise InvalidSuggestion(f"unknown source: {command.source}")

        actor_type = actor.get("actor_type", "USER")
        if (
            command.proposed_strength == IntentStrength.HARD_CONSTRAINT.value
            and actor_type != "USER"
        ):
            raise AuthorizationDenied(
                "inference may not propose a HARD constraint directly"
            )

        fingerprint = intent_suggestion_fingerprint(
            intent_id=command.intent_id,
            predicate=command.predicate,
            proposed_value=command.proposed_value,
            proposed_strength=command.proposed_strength,
            source=command.source,
        )

        suggestion_id = self.id_factory("intent_suggestion")
        with self.db.transaction() as conn:
            self.intents.insert_suggestion(
                conn,
                suggestion_id=suggestion_id,
                intent_id=command.intent_id,
                predicate=command.predicate,
                operator=command.operator,
                proposed_value=command.proposed_value,
                proposed_strength=command.proposed_strength,
                evidence=command.evidence,
                confidence=command.confidence,
                source=command.source,
                decision_state="PENDING",
                created_at=now,
                fingerprint=fingerprint,
            )
            self._append_event(
                conn,
                twin_id=command.twin_id,
                event_type="IntentSuggestionCreated",
                subject_id=suggestion_id,
                payload={"suggestion_id": suggestion_id, "source": command.source},
                now=now,
            )

        return IntentSuggestionRecord(
            suggestion_id=suggestion_id,
            intent_id=command.intent_id,
            predicate=command.predicate,
            proposed_value=command.proposed_value,
            proposed_strength=command.proposed_strength,
            source=command.source,
            decision_state="PENDING",
            fingerprint=fingerprint,
        )

    def _accept_common(
        self,
        *,
        twin_id: str,
        suggestion_id: str,
        actor: Actor,
        expected_active_version_id: str | None,
        idempotency_key: str,
        now: datetime,
        value_override=None,
        strength_override=None,
    ) -> CareerIntentVersionResult:
        # Acceptance activates authoritative intent → requires USER authority.
        require_intent_authority(actor, twin_id)

        with self.db.connection() as conn:
            suggestion = self.intents.get_suggestion(conn, suggestion_id)
        if suggestion is None or suggestion["intent_id"] is None:
            raise SuggestionNotFound(suggestion_id)

        with self.db.connection() as conn:
            intent = self.intents.get_for_twin(conn, twin_id)
            prior_statements = (
                self.intents.get_statements(conn, intent.active_version_id)
                if intent and intent.active_version_id
                else []
            )

        value = value_override if value_override is not None else suggestion["proposed_value"]
        strength = strength_override or suggestion["proposed_strength"]

        # Build new statement set: prior statements (as new records) plus the
        # accepted change, replacing any same-predicate prior statement.
        new_statements: list[NewIntentStatement] = []
        for s in prior_statements:
            if s.predicate == suggestion["predicate"]:
                continue
            new_statements.append(
                NewIntentStatement(
                    predicate=s.predicate,
                    operator=s.operator.value,
                    value=s.value,
                    strength=s.strength.value,
                    value_type=s.value_type,
                    unknown_policy=s.unknown_policy.value if s.unknown_policy else None,
                    effective_from=s.effective_from,
                    expires_at=s.expires_at,
                    provenance=dict(s.provenance),
                )
            )
        new_statements.append(
            NewIntentStatement(
                predicate=suggestion["predicate"],
                operator=suggestion["operator"],
                value=value,
                strength=strength,
                value_type=self._value_type_for(suggestion["predicate"]),
                provenance={"from_suggestion": suggestion_id},
            )
        )

        result = self.create_version(
            CreateCareerIntentVersionCommand(
                actor_id=actor.get("actor_id"),
                twin_id=twin_id,
                idempotency_key=idempotency_key,
                expected_active_version_id=expected_active_version_id,
                statements=new_statements,
            ),
            actor=actor,
            now=now,
        )

        with self.db.transaction() as conn:
            self.intents.set_suggestion_decision(conn, suggestion_id, "ACCEPTED")
            self._append_event(
                conn,
                twin_id=twin_id,
                event_type="IntentSuggestionAccepted",
                subject_id=suggestion_id,
                payload={
                    "suggestion_id": suggestion_id,
                    "intent_version_id": result.intent_version_id,
                },
                now=now,
            )
        return result

    def accept_suggestion(
        self, command: "AcceptIntentSuggestionCommand", *, actor: Actor, now: datetime
    ) -> CareerIntentVersionResult:
        return self._accept_common(
            twin_id=command.twin_id,
            suggestion_id=command.suggestion_id,
            actor=actor,
            expected_active_version_id=command.expected_active_version_id,
            idempotency_key=command.idempotency_key,
            now=now,
        )

    def edit_and_accept_suggestion(
        self,
        command: "EditAndAcceptIntentSuggestionCommand",
        *,
        actor: Actor,
        now: datetime,
    ) -> CareerIntentVersionResult:
        return self._accept_common(
            twin_id=command.twin_id,
            suggestion_id=command.suggestion_id,
            actor=actor,
            expected_active_version_id=command.expected_active_version_id,
            idempotency_key=command.idempotency_key,
            now=now,
            value_override=command.edited_value,
            strength_override=command.edited_strength,
        )

    def reject_suggestion(
        self, command: "RejectIntentSuggestionCommand", *, actor: Actor, now: datetime
    ) -> IntentSuggestionRecord:
        _suggestion_authority(actor, command.twin_id)

        with self.db.connection() as conn:
            suggestion = self.intents.get_suggestion(conn, command.suggestion_id)
        if suggestion is None:
            raise SuggestionNotFound(command.suggestion_id)

        with self.db.transaction() as conn:
            self.intents.set_suggestion_decision(
                conn, command.suggestion_id, "REJECTED"
            )
            if command.suppress:
                self.intents.insert_suppression(
                    conn,
                    suppression_id=self.id_factory("intent_suppression"),
                    intent_id=suggestion["intent_id"],
                    fingerprint=suggestion["fingerprint"],
                    reason=command.reason,
                    created_at=now,
                )
            self._append_event(
                conn,
                twin_id=command.twin_id,
                event_type="IntentSuggestionRejected",
                subject_id=command.suggestion_id,
                payload={"suggestion_id": command.suggestion_id},
                now=now,
            )

        return IntentSuggestionRecord(
            suggestion_id=command.suggestion_id,
            intent_id=suggestion["intent_id"],
            predicate=suggestion["predicate"],
            proposed_value=suggestion["proposed_value"],
            proposed_strength=suggestion["proposed_strength"],
            source=suggestion["source"],
            decision_state="REJECTED",
            fingerprint=suggestion["fingerprint"],
        )

    def _value_type_for(self, predicate: str) -> str:
        from onejob.career_intent.ontology import get_intent_predicate_definition

        return get_intent_predicate_definition(predicate).value_type.value


# Attach suggestion workflow methods to the command service.
for _method_name in (
    "create_suggestion",
    "accept_suggestion",
    "edit_and_accept_suggestion",
    "reject_suggestion",
    "_accept_common",
    "_value_type_for",
):
    setattr(
        CareerIntentCommandService,
        _method_name,
        getattr(_SuggestionMixin, _method_name),
    )
