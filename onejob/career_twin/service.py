from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from typing import Callable, Protocol

from onejob.career_twin.events import CareerEvent
from onejob.career_twin.models import (
    ApprovalState,
    CareerClaim,
    ClaimLifecycle,
)
from onejob.career_twin.ontology import (
    Predicate,
    predicate_spec,
)
from onejob.career_twin.repositories import (
    CareerClaimRepository,
    CareerEntityRepository,
    CareerEvidenceRepository,
    CareerEventRepository,
)
from onejob.persistence.db import Database


class IdFactory(Protocol):
    def __call__(self, kind: str) -> str:
        ...


class StaleClaimState(RuntimeError):
    def __init__(
        self,
        *,
        expected_claim_id: str | None,
        actual_claim_id: str | None,
    ):
        self.expected_claim_id = expected_claim_id
        self.actual_claim_id = actual_claim_id

        super().__init__(
            "career claim state is stale: "
            f"expected={expected_claim_id!r} "
            f"actual={actual_claim_id!r}"
        )


@dataclass(frozen=True)
class ApproveClaimCommand:
    twin_id: str
    entity_id: str
    predicate: Predicate
    value: object
    value_type: str
    evidence_ids: tuple[str, ...]
    expected_active_claim_id: str | None
    ontology_version: str


class CareerTwinCommandService:
    def __init__(
        self,
        db: Database,
        *,
        id_factory: IdFactory,
    ):
        self.db = db
        self.id_factory = id_factory

        self.claims = CareerClaimRepository()
        self.entities = CareerEntityRepository()
        self.evidence = CareerEvidenceRepository()
        self.events = CareerEventRepository()

    def _append_event(
        self,
        conn: sqlite3.Connection,
        *,
        twin_id: str,
        event_type: str,
        subject_id: str | None,
        payload: dict[str, object],
        now: datetime,
    ) -> CareerEvent:
        event = CareerEvent(
            event_id=self.id_factory("event"),
            twin_id=twin_id,
            event_type=event_type,
            subject_id=subject_id,
            occurred_at=now,
            payload=payload,
        )

        self.events.append_with_outbox(
            conn,
            event,
        )

        return event

    def approve_claim(
        self,
        command: ApproveClaimCommand,
        *,
        now: datetime,
    ) -> CareerClaim:
        with self.db.transaction() as conn:
            return self.approve_claim_in_transaction(
                conn,
                command,
                now=now,
            )

    def approve_claim_in_transaction(
        self,
        conn: sqlite3.Connection,
        command: ApproveClaimCommand,
        *,
        now: datetime,
    ) -> CareerClaim:
        entity = self.entities.get(
            conn,
            command.entity_id,
        )

        if entity is None:
            raise LookupError(
                f"career entity not found: {command.entity_id}"
            )

        if entity.twin_id != command.twin_id:
            raise ValueError(
                "entity does not belong to requested twin"
            )

        spec = predicate_spec(command.predicate)

        if entity.entity_type is not spec.subject_type:
            raise ValueError(
                "predicate is invalid for entity type: "
                f"{command.predicate.value} "
                f"on {entity.entity_type.value}"
            )

        if command.value_type != spec.value_type:
            raise ValueError(
                "claim value type does not match ontology: "
                f"expected={spec.value_type} "
                f"actual={command.value_type}"
            )

        current = self.claims.active_for_family(
            conn,
            command.twin_id,
            command.entity_id,
            command.predicate,
        )

        actual_active_claim_id = (
            current.claim_id
            if current is not None
            else None
        )

        if (
            actual_active_claim_id
            != command.expected_active_claim_id
        ):
            raise StaleClaimState(
                expected_claim_id=(
                    command.expected_active_claim_id
                ),
                actual_claim_id=actual_active_claim_id,
            )

        claim_id = self.id_factory("claim")

        claim = CareerClaim(
            claim_id=claim_id,
            claim_family_id=(
                f"{command.entity_id}:"
                f"{command.predicate.value}"
            ),
            twin_id=command.twin_id,
            subject_entity_id=command.entity_id,
            predicate=command.predicate,
            object_kind="VALUE",
            value=command.value,
            value_type=command.value_type,
            approval_state=ApprovalState.APPROVED,
            lifecycle_state=ClaimLifecycle.ACTIVE,
            ontology_version=command.ontology_version,
            supersedes_claim_id=(
                current.claim_id
                if current is not None
                else None
            ),
            created_at=now,
            approved_at=now,
        )

        if current is not None:
            self.claims.mark_superseded(
                conn,
                current.claim_id,
                now=now,
            )

            self._append_event(
                conn,
                twin_id=command.twin_id,
                event_type="CLAIM_SUPERSEDED",
                subject_id=current.claim_id,
                payload={
                    "claim_id": current.claim_id,
                    "superseded_by_claim_id": claim.claim_id,
                    "claim_family_id": current.claim_family_id,
                    "predicate": current.predicate.value,
                },
                now=now,
            )

        self.claims.append(
            conn,
            claim,
        )

        for evidence_id in command.evidence_ids:
            self.evidence.link_to_claim(
                conn,
                claim_id=claim.claim_id,
                evidence_id=evidence_id,
                support_type="SUPPORTS",
                confidence=1.0,
            )

        self._append_event(
            conn,
            twin_id=command.twin_id,
            event_type="CLAIM_APPROVED",
            subject_id=claim.claim_id,
            payload={
                "claim_id": claim.claim_id,
                "claim_family_id": claim.claim_family_id,
                "predicate": claim.predicate.value,
            },
            now=now,
        )

        return claim
