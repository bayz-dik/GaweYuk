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
