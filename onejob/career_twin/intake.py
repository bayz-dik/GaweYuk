from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field

from onejob.career_twin.candidates import (
    CandidateEntity,
    CandidateLifecycle,
)
from onejob.career_twin.models import CareerEvidence
from onejob.career_twin.ontology import (
    EntityType,
    Predicate,
    PrivacyClass,
)
from onejob.career_twin.repositories import (
    CandidateEntityRepository,
    CareerEvidenceRepository,
    SuggestionBatchRepository,
    SuggestionRepository,
)
from onejob.career_twin.resolution import normalized_value_fingerprint
from onejob.career_twin.suggestions import (
    AtomicSuggestion,
    BatchLifecycle,
    DecisionState,
    Disposition,
    SuggestionBatch,
)
from onejob.persistence.db import Database


class IdFactory(Protocol):
    def __call__(self, kind: str) -> str:
        ...


class ProposedEvidence(BaseModel):
    model_config = ConfigDict(frozen=True)

    source_type: str
    trust_tier: str
    independence_status: str
    privacy_class: PrivacyClass
    payload_fingerprint: str
    source_reference: str | None = None
    extractor_version: str | None = None
    # A reference only -- never a raw sensitive payload body.
    payload_reference: str | None = None


class ProposedFact(BaseModel):
    model_config = ConfigDict(frozen=True)

    predicate: Predicate
    value: object | None
    value_type: str
    expected_active_claim_id: str | None = None


class CandidateProposal(BaseModel):
    model_config = ConfigDict(frozen=True)

    proposed_entity_type: EntityType
    display_hint: str
    facts: list[ProposedFact]
    evidence: list[ProposedEvidence] = Field(default_factory=list)


class IntakeRequest(BaseModel):
    model_config = ConfigDict(frozen=True)

    twin_id: str
    source_type: str
    intake_version: str
    evidence_family_id: str
    source_reference: str | None = None
    proposals: list[CandidateProposal] = Field(default_factory=list)


@dataclass(frozen=True)
class IntakeResult:
    batch_id: str
    candidate_ids: list[str]
    suggestion_ids: list[str]
    evidence_ids: list[str]


# Source types that a non-human import/adapter may use for intake. Intake only
# ever produces proposals -- never canonical truth -- so any source may enter
# here. Canonical approval authority is enforced separately in the command
# service (see spec 19.1).
class IntakeService:
    def __init__(self, db: Database, *, id_factory: IdFactory):
        self.db = db
        self.id_factory = id_factory
        self.batches = SuggestionBatchRepository()
        self.candidates = CandidateEntityRepository()
        self.suggestions = SuggestionRepository()
        self.evidence = CareerEvidenceRepository()

    def intake(
        self,
        request: IntakeRequest,
        *,
        now: datetime,
    ) -> IntakeResult:
        with self.db.transaction() as conn:
            return self.intake_in_transaction(conn, request, now=now)

    def intake_in_transaction(
        self,
        conn: sqlite3.Connection,
        request: IntakeRequest,
        *,
        now: datetime,
    ) -> IntakeResult:
        batch_id = self.id_factory("batch")

        self.batches.insert(
            conn,
            SuggestionBatch(
                batch_id=batch_id,
                twin_id=request.twin_id,
                source_type=request.source_type,
                source_reference=request.source_reference,
                intake_version=request.intake_version,
                evidence_family_id=request.evidence_family_id,
                lifecycle=BatchLifecycle.OPEN,
                created_at=now,
            ),
        )

        candidate_ids: list[str] = []
        suggestion_ids: list[str] = []
        evidence_ids: list[str] = []

        for proposal in request.proposals:
            candidate_id = self.id_factory("candidate")
            candidate_fingerprint = self._candidate_fingerprint(proposal)

            self.candidates.insert(
                conn,
                CandidateEntity(
                    candidate_id=candidate_id,
                    batch_id=batch_id,
                    twin_id=request.twin_id,
                    proposed_entity_type=proposal.proposed_entity_type,
                    fingerprint=candidate_fingerprint,
                    display_hint=proposal.display_hint,
                    lifecycle_state=CandidateLifecycle.STAGED,
                    created_at=now,
                ),
            )
            candidate_ids.append(candidate_id)

            # Register evidence for this proposal. Only references and
            # fingerprints are persisted -- never raw sensitive payloads.
            proposal_evidence_ids: list[str] = []
            for proposed_evidence in proposal.evidence:
                evidence_id = self.id_factory("evidence")
                self.evidence.insert(
                    conn,
                    CareerEvidence(
                        evidence_id=evidence_id,
                        twin_id=request.twin_id,
                        source_type=proposed_evidence.source_type,
                        source_reference=proposed_evidence.source_reference,
                        evidence_family_id=request.evidence_family_id,
                        observed_at=now,
                        extractor_version=proposed_evidence.extractor_version,
                        payload_reference=proposed_evidence.payload_reference,
                        payload_fingerprint=(
                            proposed_evidence.payload_fingerprint
                        ),
                        trust_tier=proposed_evidence.trust_tier,
                        independence_status=(
                            proposed_evidence.independence_status
                        ),
                        privacy_class=proposed_evidence.privacy_class,
                    ),
                )
                proposal_evidence_ids.append(evidence_id)
                evidence_ids.append(evidence_id)

            for fact in proposal.facts:
                suggestion_id = self.id_factory("suggestion")
                fingerprint = normalized_value_fingerprint(
                    fact.predicate, fact.value
                )

                self.suggestions.insert(
                    conn,
                    AtomicSuggestion(
                        suggestion_id=suggestion_id,
                        batch_id=batch_id,
                        twin_id=request.twin_id,
                        candidate_id=candidate_id,
                        predicate=fact.predicate,
                        proposed_value=fact.value,
                        value_type=fact.value_type,
                        decision_state=DecisionState.PENDING,
                        disposition=Disposition.READY,
                        normalized_value_fingerprint=fingerprint,
                        expected_active_claim_id=(
                            fact.expected_active_claim_id
                        ),
                        version=1,
                        created_at=now,
                    ),
                )
                suggestion_ids.append(suggestion_id)

                for evidence_id in proposal_evidence_ids:
                    self.suggestions.link_evidence(
                        conn, suggestion_id, evidence_id
                    )

        return IntakeResult(
            batch_id=batch_id,
            candidate_ids=candidate_ids,
            suggestion_ids=suggestion_ids,
            evidence_ids=evidence_ids,
        )

    @staticmethod
    def _candidate_fingerprint(proposal: CandidateProposal) -> str:
        parts = [proposal.proposed_entity_type.value]
        for fact in proposal.facts:
            parts.append(
                normalized_value_fingerprint(fact.predicate, fact.value)
            )
        return "|".join(parts)
