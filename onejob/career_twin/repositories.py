from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from typing import Any

from onejob.career_twin.events import CareerEvent
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
from onejob.career_twin.candidates import (
    CandidateEntity,
    CandidateLifecycle,
)
from onejob.career_twin.conflicts import (
    ConflictSet,
    ConflictStatus,
)
from onejob.career_twin.resolution import (
    ConfidenceBand,
    EntityResolution,
)
from onejob.career_twin.suggestions import (
    AtomicSuggestion,
    BatchLifecycle,
    DecisionState,
    Disposition,
    SuggestionBatch,
)
from onejob.career_twin.suppression import (
    SuppressionRecord,
    SuppressionStrength,
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


class CareerEventRepository:
    def append_with_outbox(
        self,
        conn: sqlite3.Connection,
        event: CareerEvent,
    ) -> None:
        conn.execute(
            """
            INSERT INTO career_events (
                event_id,
                twin_id,
                event_type,
                subject_id,
                occurred_at,
                payload_json,
                causation_id,
                correlation_id
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                event.event_id,
                event.twin_id,
                event.event_type,
                event.subject_id,
                _encode_datetime(event.occurred_at),
                json.dumps(
                    event.payload,
                    sort_keys=True,
                    separators=(",", ":"),
                ),
                event.causation_id,
                event.correlation_id,
            ),
        )

        conn.execute(
            """
            INSERT INTO career_event_outbox (
                event_id,
                status,
                attempt_count
            )
            VALUES (?, 'PENDING', 0)
            """,
            (event.event_id,),
        )


# ---------------------------------------------------------------------------
# Slice 2 repositories
# ---------------------------------------------------------------------------


class SuggestionBatchRepository:
    def insert(
        self,
        conn: sqlite3.Connection,
        batch: SuggestionBatch,
    ) -> None:
        conn.execute(
            """
            INSERT INTO career_suggestion_batches (
                batch_id,
                twin_id,
                source_type,
                source_reference,
                intake_version,
                evidence_family_id,
                lifecycle,
                created_at,
                completed_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                batch.batch_id,
                batch.twin_id,
                batch.source_type,
                batch.source_reference,
                batch.intake_version,
                batch.evidence_family_id,
                batch.lifecycle.value,
                _encode_datetime(batch.created_at),
                _encode_datetime(batch.completed_at),
            ),
        )

    def get(
        self,
        conn: sqlite3.Connection,
        batch_id: str,
    ) -> SuggestionBatch | None:
        row = conn.execute(
            """
            SELECT *
            FROM career_suggestion_batches
            WHERE batch_id = ?
            """,
            (batch_id,),
        ).fetchone()

        if row is None:
            return None

        return SuggestionBatch(
            batch_id=row["batch_id"],
            twin_id=row["twin_id"],
            source_type=row["source_type"],
            source_reference=row["source_reference"],
            intake_version=row["intake_version"],
            evidence_family_id=row["evidence_family_id"],
            lifecycle=BatchLifecycle(row["lifecycle"]),
            created_at=_decode_datetime(row["created_at"]),
            completed_at=_decode_datetime(row["completed_at"]),
        )

    def mark_lifecycle(
        self,
        conn: sqlite3.Connection,
        batch_id: str,
        lifecycle: BatchLifecycle,
        *,
        now: datetime,
    ) -> None:
        completed_at = (
            _encode_datetime(now)
            if lifecycle
            in (BatchLifecycle.PROCESSED, BatchLifecycle.CANCELLED)
            else None
        )
        cursor = conn.execute(
            """
            UPDATE career_suggestion_batches
            SET lifecycle = ?,
                completed_at = ?
            WHERE batch_id = ?
            """,
            (lifecycle.value, completed_at, batch_id),
        )
        if cursor.rowcount != 1:
            raise LookupError(
                f"suggestion batch not found: {batch_id}"
            )


def _row_to_candidate(row: sqlite3.Row) -> CandidateEntity:
    return CandidateEntity(
        candidate_id=row["candidate_id"],
        batch_id=row["batch_id"],
        twin_id=row["twin_id"],
        proposed_entity_type=EntityType(row["proposed_entity_type"]),
        fingerprint=row["fingerprint"],
        display_hint=row["display_hint"],
        lifecycle_state=CandidateLifecycle(row["lifecycle_state"]),
        created_at=_decode_datetime(row["created_at"]),
        promoted_entity_id=row["promoted_entity_id"],
    )


class CandidateEntityRepository:
    def insert(
        self,
        conn: sqlite3.Connection,
        candidate: CandidateEntity,
    ) -> None:
        conn.execute(
            """
            INSERT INTO career_candidate_entities (
                candidate_id,
                batch_id,
                twin_id,
                proposed_entity_type,
                fingerprint,
                display_hint,
                lifecycle_state,
                created_at,
                promoted_entity_id
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                candidate.candidate_id,
                candidate.batch_id,
                candidate.twin_id,
                candidate.proposed_entity_type.value,
                candidate.fingerprint,
                candidate.display_hint,
                candidate.lifecycle_state.value,
                _encode_datetime(candidate.created_at),
                candidate.promoted_entity_id,
            ),
        )

    def get(
        self,
        conn: sqlite3.Connection,
        candidate_id: str,
    ) -> CandidateEntity | None:
        row = conn.execute(
            """
            SELECT *
            FROM career_candidate_entities
            WHERE candidate_id = ?
            """,
            (candidate_id,),
        ).fetchone()

        if row is None:
            return None

        return _row_to_candidate(row)

    def update(
        self,
        conn: sqlite3.Connection,
        candidate: CandidateEntity,
    ) -> None:
        cursor = conn.execute(
            """
            UPDATE career_candidate_entities
            SET lifecycle_state = ?,
                promoted_entity_id = ?
            WHERE candidate_id = ?
            """,
            (
                candidate.lifecycle_state.value,
                candidate.promoted_entity_id,
                candidate.candidate_id,
            ),
        )
        if cursor.rowcount != 1:
            raise LookupError(
                f"candidate not found: {candidate.candidate_id}"
            )

    def list_for_batch(
        self,
        conn: sqlite3.Connection,
        batch_id: str,
    ) -> list[CandidateEntity]:
        rows = conn.execute(
            """
            SELECT *
            FROM career_candidate_entities
            WHERE batch_id = ?
            ORDER BY created_at, candidate_id
            """,
            (batch_id,),
        ).fetchall()
        return [_row_to_candidate(row) for row in rows]


def _row_to_suggestion(row: sqlite3.Row) -> AtomicSuggestion:
    return AtomicSuggestion(
        suggestion_id=row["suggestion_id"],
        batch_id=row["batch_id"],
        twin_id=row["twin_id"],
        candidate_id=row["candidate_id"],
        resolved_entity_id=row["resolved_entity_id"],
        predicate=Predicate(row["predicate"]),
        proposed_value=_decode_value(row["proposed_value_json"]),
        value_type=row["value_type"],
        decision_state=DecisionState(row["decision_state"]),
        disposition=Disposition(row["disposition"]),
        normalized_value_fingerprint=row["normalized_value_fingerprint"],
        expected_active_claim_id=row["expected_active_claim_id"],
        version=row["version"],
        created_at=_decode_datetime(row["created_at"]),
        decided_at=_decode_datetime(row["decided_at"]),
        decision_actor_id=row["decision_actor_id"],
    )


class SuggestionRepository:
    def insert(
        self,
        conn: sqlite3.Connection,
        suggestion: AtomicSuggestion,
    ) -> None:
        conn.execute(
            """
            INSERT INTO career_atomic_suggestions (
                suggestion_id,
                batch_id,
                twin_id,
                candidate_id,
                resolved_entity_id,
                predicate,
                proposed_value_json,
                value_type,
                decision_state,
                disposition,
                normalized_value_fingerprint,
                expected_active_claim_id,
                version,
                created_at,
                decided_at,
                decision_actor_id
            )
            VALUES (
                ?, ?, ?, ?, ?,
                ?, ?, ?,
                ?, ?,
                ?, ?,
                ?,
                ?, ?, ?
            )
            """,
            (
                suggestion.suggestion_id,
                suggestion.batch_id,
                suggestion.twin_id,
                suggestion.candidate_id,
                suggestion.resolved_entity_id,
                suggestion.predicate.value,
                _encode_value(suggestion.proposed_value),
                suggestion.value_type,
                suggestion.decision_state.value,
                suggestion.disposition.value,
                suggestion.normalized_value_fingerprint,
                suggestion.expected_active_claim_id,
                suggestion.version,
                _encode_datetime(suggestion.created_at),
                _encode_datetime(suggestion.decided_at),
                suggestion.decision_actor_id,
            ),
        )

    def get(
        self,
        conn: sqlite3.Connection,
        suggestion_id: str,
    ) -> AtomicSuggestion | None:
        row = conn.execute(
            """
            SELECT *
            FROM career_atomic_suggestions
            WHERE suggestion_id = ?
            """,
            (suggestion_id,),
        ).fetchone()

        if row is None:
            return None

        return _row_to_suggestion(row)

    def update_versioned(
        self,
        conn: sqlite3.Connection,
        suggestion: AtomicSuggestion,
        *,
        expected_version: int,
    ) -> None:
        """Optimistic concurrency: only apply if stored version matches.

        This is the only decision mutator, and it always writes a complete
        validated suggestion record produced by the state machine. Repositories
        do not expose a generic per-field state mutator.
        """
        cursor = conn.execute(
            """
            UPDATE career_atomic_suggestions
            SET resolved_entity_id = ?,
                decision_state = ?,
                disposition = ?,
                expected_active_claim_id = ?,
                version = ?,
                decided_at = ?,
                decision_actor_id = ?
            WHERE suggestion_id = ?
              AND version = ?
            """,
            (
                suggestion.resolved_entity_id,
                suggestion.decision_state.value,
                suggestion.disposition.value,
                suggestion.expected_active_claim_id,
                suggestion.version,
                _encode_datetime(suggestion.decided_at),
                suggestion.decision_actor_id,
                suggestion.suggestion_id,
                expected_version,
            ),
        )
        if cursor.rowcount != 1:
            raise LookupError(
                "stale suggestion version for "
                f"{suggestion.suggestion_id}: "
                f"expected_version={expected_version}"
            )

    def link_evidence(
        self,
        conn: sqlite3.Connection,
        suggestion_id: str,
        evidence_id: str,
    ) -> None:
        conn.execute(
            """
            INSERT OR IGNORE INTO career_suggestion_evidence (
                suggestion_id,
                evidence_id
            )
            VALUES (?, ?)
            """,
            (suggestion_id, evidence_id),
        )

    def evidence_ids(
        self,
        conn: sqlite3.Connection,
        suggestion_id: str,
    ) -> list[str]:
        rows = conn.execute(
            """
            SELECT evidence_id
            FROM career_suggestion_evidence
            WHERE suggestion_id = ?
            ORDER BY evidence_id
            """,
            (suggestion_id,),
        ).fetchall()
        return [row["evidence_id"] for row in rows]

    def find_by_fingerprint(
        self,
        conn: sqlite3.Connection,
        *,
        twin_id: str,
        predicate: Predicate,
        normalized_value_fingerprint: str,
    ) -> list[AtomicSuggestion]:
        rows = conn.execute(
            """
            SELECT *
            FROM career_atomic_suggestions
            WHERE twin_id = ?
              AND predicate = ?
              AND normalized_value_fingerprint = ?
            ORDER BY created_at, suggestion_id
            """,
            (
                twin_id,
                predicate.value,
                normalized_value_fingerprint,
            ),
        ).fetchall()
        return [_row_to_suggestion(row) for row in rows]

    def list_for_twin(
        self,
        conn: sqlite3.Connection,
        twin_id: str,
        *,
        decision_state: DecisionState | None = None,
        disposition: Disposition | None = None,
        batch_id: str | None = None,
    ) -> list[AtomicSuggestion]:
        query = [
            "SELECT * FROM career_atomic_suggestions WHERE twin_id = ?"
        ]
        params: list[object] = [twin_id]
        if decision_state is not None:
            query.append("AND decision_state = ?")
            params.append(decision_state.value)
        if disposition is not None:
            query.append("AND disposition = ?")
            params.append(disposition.value)
        if batch_id is not None:
            query.append("AND batch_id = ?")
            params.append(batch_id)
        query.append("ORDER BY created_at, suggestion_id")

        rows = conn.execute(" ".join(query), tuple(params)).fetchall()
        return [_row_to_suggestion(row) for row in rows]


def _row_to_resolution(row: sqlite3.Row) -> EntityResolution:
    return EntityResolution(
        resolution_id=row["resolution_id"],
        candidate_id=row["candidate_id"],
        proposed_entity_id=row["proposed_entity_id"],
        confidence=row["confidence"],
        confidence_band=ConfidenceBand(row["confidence_band"]),
        method=row["method"],
        algorithm_version=row["algorithm_version"],
        input_fingerprint=row["input_fingerprint"],
        signals_json=row["signals_json"],
        created_at=_decode_datetime(row["created_at"]),
        supersedes_resolution_id=row["supersedes_resolution_id"],
    )


class EntityResolutionRepository:
    def append(
        self,
        conn: sqlite3.Connection,
        resolution: EntityResolution,
    ) -> None:
        conn.execute(
            """
            INSERT INTO career_entity_resolutions (
                resolution_id,
                candidate_id,
                proposed_entity_id,
                confidence,
                confidence_band,
                method,
                algorithm_version,
                input_fingerprint,
                signals_json,
                created_at,
                supersedes_resolution_id
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                resolution.resolution_id,
                resolution.candidate_id,
                resolution.proposed_entity_id,
                resolution.confidence,
                resolution.confidence_band.value,
                resolution.method,
                resolution.algorithm_version,
                resolution.input_fingerprint,
                resolution.signals_json,
                _encode_datetime(resolution.created_at),
                resolution.supersedes_resolution_id,
            ),
        )

    def latest_for_candidate(
        self,
        conn: sqlite3.Connection,
        candidate_id: str,
    ) -> EntityResolution | None:
        row = conn.execute(
            """
            SELECT *
            FROM career_entity_resolutions
            WHERE candidate_id = ?
            ORDER BY created_at DESC, resolution_id DESC
            LIMIT 1
            """,
            (candidate_id,),
        ).fetchone()

        if row is None:
            return None

        return _row_to_resolution(row)


def _row_to_conflict(row: sqlite3.Row) -> ConflictSet:
    return ConflictSet(
        conflict_id=row["conflict_id"],
        twin_id=row["twin_id"],
        entity_id=row["entity_id"],
        predicate=Predicate(row["predicate"]),
        active_claim_id=row["active_claim_id"],
        status=ConflictStatus(row["status"]),
        version=row["version"],
        created_at=_decode_datetime(row["created_at"]),
        resolved_at=_decode_datetime(row["resolved_at"]),
        resolution_type=row["resolution_type"],
        resolution_claim_id=row["resolution_claim_id"],
    )


class ConflictSetRepository:
    def insert(
        self,
        conn: sqlite3.Connection,
        conflict: ConflictSet,
    ) -> None:
        conn.execute(
            """
            INSERT INTO career_conflict_sets (
                conflict_id,
                twin_id,
                entity_id,
                predicate,
                active_claim_id,
                status,
                version,
                created_at,
                resolved_at,
                resolution_type,
                resolution_claim_id
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                conflict.conflict_id,
                conflict.twin_id,
                conflict.entity_id,
                conflict.predicate.value,
                conflict.active_claim_id,
                conflict.status.value,
                conflict.version,
                _encode_datetime(conflict.created_at),
                _encode_datetime(conflict.resolved_at),
                conflict.resolution_type,
                conflict.resolution_claim_id,
            ),
        )

    def get(
        self,
        conn: sqlite3.Connection,
        conflict_id: str,
    ) -> ConflictSet | None:
        row = conn.execute(
            """
            SELECT *
            FROM career_conflict_sets
            WHERE conflict_id = ?
            """,
            (conflict_id,),
        ).fetchone()

        if row is None:
            return None

        return _row_to_conflict(row)

    def update_versioned(
        self,
        conn: sqlite3.Connection,
        conflict: ConflictSet,
        *,
        expected_version: int,
    ) -> None:
        cursor = conn.execute(
            """
            UPDATE career_conflict_sets
            SET active_claim_id = ?,
                status = ?,
                version = ?,
                resolved_at = ?,
                resolution_type = ?,
                resolution_claim_id = ?
            WHERE conflict_id = ?
              AND version = ?
            """,
            (
                conflict.active_claim_id,
                conflict.status.value,
                conflict.version,
                _encode_datetime(conflict.resolved_at),
                conflict.resolution_type,
                conflict.resolution_claim_id,
                conflict.conflict_id,
                expected_version,
            ),
        )
        if cursor.rowcount != 1:
            raise LookupError(
                "stale conflict version for "
                f"{conflict.conflict_id}: "
                f"expected_version={expected_version}"
            )

    def link_suggestion(
        self,
        conn: sqlite3.Connection,
        conflict_id: str,
        suggestion_id: str,
        *,
        cluster_key: str | None = None,
    ) -> None:
        conn.execute(
            """
            INSERT OR IGNORE INTO career_conflict_suggestions (
                conflict_id,
                suggestion_id,
                cluster_key
            )
            VALUES (?, ?, ?)
            """,
            (conflict_id, suggestion_id, cluster_key),
        )

    def suggestion_ids(
        self,
        conn: sqlite3.Connection,
        conflict_id: str,
    ) -> list[str]:
        rows = conn.execute(
            """
            SELECT suggestion_id
            FROM career_conflict_suggestions
            WHERE conflict_id = ?
            ORDER BY suggestion_id
            """,
            (conflict_id,),
        ).fetchall()
        return [row["suggestion_id"] for row in rows]

    def open_for_family(
        self,
        conn: sqlite3.Connection,
        *,
        twin_id: str,
        entity_id: str,
        predicate: Predicate,
    ) -> ConflictSet | None:
        row = conn.execute(
            """
            SELECT *
            FROM career_conflict_sets
            WHERE twin_id = ?
              AND entity_id = ?
              AND predicate = ?
              AND status = 'OPEN'
            ORDER BY created_at DESC, conflict_id DESC
            LIMIT 1
            """,
            (twin_id, entity_id, predicate.value),
        ).fetchone()

        if row is None:
            return None

        return _row_to_conflict(row)


def _row_to_suppression(row: sqlite3.Row) -> SuppressionRecord:
    return SuppressionRecord(
        suppression_id=row["suppression_id"],
        twin_id=row["twin_id"],
        entity_scope=row["entity_scope"],
        candidate_scope=row["candidate_scope"],
        predicate=Predicate(row["predicate"]),
        normalized_value_fingerprint=row["normalized_value_fingerprint"],
        evidence_family_scope=row["evidence_family_scope"],
        source_scope=row["source_scope"],
        strength=SuppressionStrength(row["strength"]),
        reason=row["reason"],
        created_at=_decode_datetime(row["created_at"]),
        expires_at=_decode_datetime(row["expires_at"]),
        lifted_at=_decode_datetime(row["lifted_at"]),
    )


class SuppressionRepository:
    def insert(
        self,
        conn: sqlite3.Connection,
        record: SuppressionRecord,
    ) -> None:
        conn.execute(
            """
            INSERT INTO career_suppression_records (
                suppression_id,
                twin_id,
                entity_scope,
                candidate_scope,
                predicate,
                normalized_value_fingerprint,
                evidence_family_scope,
                source_scope,
                strength,
                reason,
                created_at,
                expires_at,
                lifted_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                record.suppression_id,
                record.twin_id,
                record.entity_scope,
                record.candidate_scope,
                record.predicate.value,
                record.normalized_value_fingerprint,
                record.evidence_family_scope,
                record.source_scope,
                record.strength.value,
                record.reason,
                _encode_datetime(record.created_at),
                _encode_datetime(record.expires_at),
                _encode_datetime(record.lifted_at),
            ),
        )

    def get(
        self,
        conn: sqlite3.Connection,
        suppression_id: str,
    ) -> SuppressionRecord | None:
        row = conn.execute(
            """
            SELECT *
            FROM career_suppression_records
            WHERE suppression_id = ?
            """,
            (suppression_id,),
        ).fetchone()

        if row is None:
            return None

        return _row_to_suppression(row)

    def active_matches(
        self,
        conn: sqlite3.Connection,
        *,
        twin_id: str,
        predicate: Predicate,
        normalized_value_fingerprint: str,
    ) -> list[SuppressionRecord]:
        rows = conn.execute(
            """
            SELECT *
            FROM career_suppression_records
            WHERE twin_id = ?
              AND predicate = ?
              AND normalized_value_fingerprint = ?
              AND lifted_at IS NULL
            ORDER BY created_at, suppression_id
            """,
            (
                twin_id,
                predicate.value,
                normalized_value_fingerprint,
            ),
        ).fetchall()
        return [_row_to_suppression(row) for row in rows]

    def lift(
        self,
        conn: sqlite3.Connection,
        suppression_id: str,
        *,
        now: datetime,
    ) -> None:
        cursor = conn.execute(
            """
            UPDATE career_suppression_records
            SET lifted_at = ?
            WHERE suppression_id = ?
              AND lifted_at IS NULL
            """,
            (_encode_datetime(now), suppression_id),
        )
        if cursor.rowcount != 1:
            raise LookupError(
                f"active suppression not found: {suppression_id}"
            )


class IdempotencyRecord:
    __slots__ = (
        "idempotency_key",
        "request_fingerprint",
        "result_reference",
        "created_at",
    )

    def __init__(
        self,
        *,
        idempotency_key: str,
        request_fingerprint: str,
        result_reference: str | None,
        created_at: datetime,
    ):
        self.idempotency_key = idempotency_key
        self.request_fingerprint = request_fingerprint
        self.result_reference = result_reference
        self.created_at = created_at


class IdempotencyRepository:
    def store(
        self,
        conn: sqlite3.Connection,
        *,
        idempotency_key: str,
        request_fingerprint: str,
        result_reference: str | None,
        now: datetime,
    ) -> None:
        conn.execute(
            """
            INSERT INTO career_idempotency_keys (
                idempotency_key,
                request_fingerprint,
                result_reference,
                created_at
            )
            VALUES (?, ?, ?, ?)
            """,
            (
                idempotency_key,
                request_fingerprint,
                result_reference,
                _encode_datetime(now),
            ),
        )

    def get(
        self,
        conn: sqlite3.Connection,
        idempotency_key: str,
    ) -> IdempotencyRecord | None:
        row = conn.execute(
            """
            SELECT *
            FROM career_idempotency_keys
            WHERE idempotency_key = ?
            """,
            (idempotency_key,),
        ).fetchone()

        if row is None:
            return None

        return IdempotencyRecord(
            idempotency_key=row["idempotency_key"],
            request_fingerprint=row["request_fingerprint"],
            result_reference=row["result_reference"],
            created_at=_decode_datetime(row["created_at"]),
        )
