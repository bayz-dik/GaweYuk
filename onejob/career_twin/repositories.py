from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from typing import Any

from onejob.career_twin.models import (
    ApprovalState,
    CareerClaim,
    CareerEntity,
    CareerEvidence,
    ClaimAssessment,
    ClaimLifecycle,
    EntityLifecycle,
)
from onejob.career_twin.ontology import (
    Cardinality,
    EntityType,
    Predicate,
    predicate_spec,
)


class ActiveClaimConflict(RuntimeError):
    def __init__(
        self,
        *,
        twin_id: str,
        entity_id: str,
        predicate: Predicate,
        active_claim_id: str,
    ):
        self.twin_id = twin_id
        self.entity_id = entity_id
        self.predicate = predicate
        self.active_claim_id = active_claim_id

        super().__init__(
            "active singular claim already exists: "
            f"{twin_id=} {entity_id=} "
            f"{predicate.value=} {active_claim_id=}"
        )


def _encode_value(value: Any | None) -> str | None:
    if value is None:
        return None

    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )


def _decode_value(value_json: str | None) -> Any | None:
    if value_json is None:
        return None
    return json.loads(value_json)


def _encode_datetime(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.isoformat()


def _decode_datetime(value: str | None) -> datetime | None:
    if value is None:
        return None
    return datetime.fromisoformat(value)


def _row_to_claim(row: sqlite3.Row) -> CareerClaim:
    return CareerClaim(
        claim_id=row["claim_id"],
        claim_family_id=row["claim_family_id"],
        twin_id=row["twin_id"],
        subject_entity_id=row["subject_entity_id"],
        predicate=Predicate(row["predicate"]),
        object_kind=row["object_kind"],
        value=_decode_value(row["value_json"]),
        value_type=row["value_type"],
        approval_state=ApprovalState(
            row["approval_state"]
        ),
        lifecycle_state=ClaimLifecycle(
            row["lifecycle_state"]
        ),
        ontology_version=row["ontology_version"],
        supersedes_claim_id=row[
            "supersedes_claim_id"
        ],
        rebased_from_claim_id=row[
            "rebased_from_claim_id"
        ],
        valid_from=_decode_datetime(
            row["valid_from"]
        ),
        valid_to=_decode_datetime(
            row["valid_to"]
        ),
        created_at=_decode_datetime(
            row["created_at"]
        ),
        approved_at=_decode_datetime(
            row["approved_at"]
        ),
        retired_at=_decode_datetime(
            row["retired_at"]
        ),
        erased_at=_decode_datetime(
            row["erased_at"]
        ),
    )


def _row_to_entity(row: sqlite3.Row) -> CareerEntity:
    return CareerEntity(
        entity_id=row["entity_id"],
        twin_id=row["twin_id"],
        entity_type=EntityType(row["entity_type"]),
        lifecycle_state=EntityLifecycle(
            row["lifecycle_state"]
        ),
        canonicalized_from_candidate_id=row[
            "canonicalized_from_candidate_id"
        ],
        canonical_successor_id=row[
            "canonical_successor_id"
        ],
        created_at=_decode_datetime(
            row["created_at"]
        ),
        retired_at=_decode_datetime(
            row["retired_at"]
        ),
        erased_at=_decode_datetime(
            row["erased_at"]
        ),
    )


class CareerTwinRepository:
    def ensure_twin(
        self,
        conn: sqlite3.Connection,
        twin_id: str,
        user_id: str,
        ontology_version: str,
    ) -> None:
        conn.execute(
            """
            INSERT INTO career_twins (
                twin_id,
                user_id,
                ontology_version,
                status,
                created_at
            )
            VALUES (
                ?,
                ?,
                ?,
                'ACTIVE',
                datetime('now')
            )
            ON CONFLICT(twin_id) DO NOTHING
            """,
            (
                twin_id,
                user_id,
                ontology_version,
            ),
        )


class CareerEntityRepository:
    def insert(
        self,
        conn: sqlite3.Connection,
        entity: CareerEntity,
    ) -> None:
        conn.execute(
            """
            INSERT INTO career_entities (
                entity_id,
                twin_id,
                entity_type,
                lifecycle_state,
                canonicalized_from_candidate_id,
                canonical_successor_id,
                created_at,
                retired_at,
                erased_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                entity.entity_id,
                entity.twin_id,
                entity.entity_type.value,
                entity.lifecycle_state.value,
                entity.canonicalized_from_candidate_id,
                entity.canonical_successor_id,
                _encode_datetime(entity.created_at),
                _encode_datetime(entity.retired_at),
                _encode_datetime(entity.erased_at),
            ),
        )


    def get(
        self,
        conn: sqlite3.Connection,
        entity_id: str,
    ) -> CareerEntity | None:
        row = conn.execute(
            """
            SELECT *
            FROM career_entities
            WHERE entity_id = ?
            """,
            (entity_id,),
        ).fetchone()

        if row is None:
            return None

        return _row_to_entity(row)

    def list_active(
        self,
        conn: sqlite3.Connection,
        twin_id: str,
    ) -> list[CareerEntity]:
        rows = conn.execute(
            """
            SELECT *
            FROM career_entities
            WHERE twin_id = ?
              AND lifecycle_state = 'ACTIVE'
              AND erased_at IS NULL
            ORDER BY created_at, entity_id
            """,
            (twin_id,),
        ).fetchall()

        return [
            _row_to_entity(row)
            for row in rows
        ]


class CareerClaimRepository:
    def append(
        self,
        conn: sqlite3.Connection,
        claim: CareerClaim,
    ) -> None:
        spec = predicate_spec(claim.predicate)

        if (
            spec.cardinality is Cardinality.ONE
            and claim.approval_state
            is ApprovalState.APPROVED
            and claim.lifecycle_state
            is ClaimLifecycle.ACTIVE
        ):
            existing = self.active_for_family(
                conn,
                claim.twin_id,
                claim.subject_entity_id,
                claim.predicate,
            )

            if existing is not None:
                raise ActiveClaimConflict(
                    twin_id=claim.twin_id,
                    entity_id=claim.subject_entity_id,
                    predicate=claim.predicate,
                    active_claim_id=existing.claim_id,
                )

        conn.execute(
            """
            INSERT INTO career_claims (
                claim_id,
                claim_family_id,
                twin_id,
                subject_entity_id,

                predicate,
                object_kind,
                value_json,
                value_type,

                approval_state,
                lifecycle_state,
                ontology_version,

                supersedes_claim_id,
                rebased_from_claim_id,

                valid_from,
                valid_to,

                created_at,
                approved_at,
                retired_at,
                erased_at
            )
            VALUES (
                ?, ?, ?, ?,
                ?, ?, ?, ?,
                ?, ?, ?,
                ?, ?,
                ?, ?,
                ?, ?, ?, ?
            )
            """,
            (
                claim.claim_id,
                claim.claim_family_id,
                claim.twin_id,
                claim.subject_entity_id,

                claim.predicate.value,
                claim.object_kind,
                _encode_value(claim.value),
                claim.value_type,

                claim.approval_state.value,
                claim.lifecycle_state.value,
                claim.ontology_version,

                claim.supersedes_claim_id,
                claim.rebased_from_claim_id,

                _encode_datetime(claim.valid_from),
                _encode_datetime(claim.valid_to),

                _encode_datetime(claim.created_at),
                _encode_datetime(claim.approved_at),
                _encode_datetime(claim.retired_at),
                _encode_datetime(claim.erased_at),
            ),
        )

    def active_for_family(
        self,
        conn: sqlite3.Connection,
        twin_id: str,
        entity_id: str,
        predicate: Predicate,
    ) -> CareerClaim | None:
        row = conn.execute(
            """
            SELECT *
            FROM career_claims
            WHERE twin_id = ?
              AND subject_entity_id = ?
              AND predicate = ?
              AND approval_state = 'APPROVED'
              AND lifecycle_state = 'ACTIVE'
              AND erased_at IS NULL
            ORDER BY created_at DESC, claim_id DESC
            LIMIT 1
            """,
            (
                twin_id,
                entity_id,
                predicate.value,
            ),
        ).fetchone()

        if row is None:
            return None

        return _row_to_claim(row)


    def list_active_for_twin(
        self,
        conn: sqlite3.Connection,
        twin_id: str,
    ) -> list[CareerClaim]:
        rows = conn.execute(
            """
            SELECT *
            FROM career_claims
            WHERE twin_id = ?
              AND approval_state = 'APPROVED'
              AND lifecycle_state = 'ACTIVE'
              AND erased_at IS NULL
            ORDER BY created_at, claim_id
            """,
            (twin_id,),
        ).fetchall()

        return [
            _row_to_claim(row)
            for row in rows
        ]

    def mark_superseded(
        self,
        conn: sqlite3.Connection,
        claim_id: str,
        *,
        now: datetime,
    ) -> None:
        cursor = conn.execute(
            """
            UPDATE career_claims
            SET lifecycle_state = 'SUPERSEDED',
                retired_at = ?
            WHERE claim_id = ?
              AND lifecycle_state = 'ACTIVE'
              AND erased_at IS NULL
            """,
            (
                _encode_datetime(now),
                claim_id,
            ),
        )

        if cursor.rowcount != 1:
            raise LookupError(
                "active claim not found for supersession: "
                f"{claim_id}"
            )


    def history_for_family(
        self,
        conn: sqlite3.Connection,
        claim_family_id: str,
    ) -> list[CareerClaim]:
        rows = conn.execute(
            """
            SELECT *
            FROM career_claims
            WHERE claim_family_id = ?
            ORDER BY created_at, claim_id
            """,
            (claim_family_id,),
        ).fetchall()

        return [
            _row_to_claim(row)
            for row in rows
        ]


class CareerEvidenceRepository:
    def insert(
        self,
        conn: sqlite3.Connection,
        evidence: CareerEvidence,
    ) -> None:
        conn.execute(
            """
            INSERT INTO career_evidence (
                evidence_id,
                twin_id,
                source_type,
                source_reference,
                evidence_family_id,
                observed_at,
                extractor_version,
                payload_reference,
                payload_fingerprint,
                trust_tier,
                independence_status,
                privacy_class,
                erased_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                evidence.evidence_id,
                evidence.twin_id,
                evidence.source_type,
                evidence.source_reference,
                evidence.evidence_family_id,
                _encode_datetime(evidence.observed_at),
                evidence.extractor_version,
                evidence.payload_reference,
                evidence.payload_fingerprint,
                evidence.trust_tier,
                evidence.independence_status,
                evidence.privacy_class.value,
                _encode_datetime(evidence.erased_at),
            ),
        )

    def link_to_claim(
        self,
        conn: sqlite3.Connection,
        *,
        claim_id: str,
        evidence_id: str,
        support_type: str,
        confidence: float,
    ) -> None:
        conn.execute(
            """
            INSERT INTO career_claim_evidence (
                claim_id,
                evidence_id,
                support_type,
                confidence
            )
            VALUES (?, ?, ?, ?)
            """,
            (
                claim_id,
                evidence_id,
                support_type,
                confidence,
            ),
        )


def _row_to_claim_assessment(
    row: sqlite3.Row,
) -> ClaimAssessment:
    return ClaimAssessment(
        assessment_id=row["assessment_id"],
        claim_id=row["claim_id"],
        provenance_trust_tier=row[
            "provenance_trust_tier"
        ],
        claim_confidence=row["claim_confidence"],
        evidence_fingerprint=row[
            "evidence_fingerprint"
        ],
        assessed_at=_decode_datetime(
            row["assessed_at"]
        ),
        algorithm_version=row[
            "algorithm_version"
        ],
    )


class ClaimAssessmentRepository:
    def append(
        self,
        conn: sqlite3.Connection,
        assessment: ClaimAssessment,
    ) -> None:
        conn.execute(
            """
            INSERT INTO career_claim_assessments (
                assessment_id,
                claim_id,
                provenance_trust_tier,
                claim_confidence,
                evidence_fingerprint,
                assessed_at,
                algorithm_version
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                assessment.assessment_id,
                assessment.claim_id,
                assessment.provenance_trust_tier,
                assessment.claim_confidence,
                assessment.evidence_fingerprint,
                _encode_datetime(
                    assessment.assessed_at
                ),
                assessment.algorithm_version,
            ),
        )

    def latest_for_claim(
        self,
        conn: sqlite3.Connection,
        claim_id: str,
    ) -> ClaimAssessment | None:
        row = conn.execute(
            """
            SELECT *
            FROM career_claim_assessments
            WHERE claim_id = ?
            ORDER BY assessed_at DESC,
                     assessment_id DESC
            LIMIT 1
            """,
            (claim_id,),
        ).fetchone()

        if row is None:
            return None

        return _row_to_claim_assessment(row)
