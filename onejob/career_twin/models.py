from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from onejob.career_twin.ontology import (
    EntityType,
    Predicate,
    PrivacyClass,
)


class ApprovalState(str, Enum):
    APPROVED = "APPROVED"


class ClaimLifecycle(str, Enum):
    ACTIVE = "ACTIVE"
    SUPERSEDED = "SUPERSEDED"
    RETIRED = "RETIRED"
    ERASED = "ERASED"


class EntityLifecycle(str, Enum):
    ACTIVE = "ACTIVE"
    MERGED = "MERGED"
    SPLIT = "SPLIT"
    RETIRED = "RETIRED"
    ERASED = "ERASED"


class CareerEntity(BaseModel):
    model_config = ConfigDict(frozen=True)

    entity_id: str
    twin_id: str
    entity_type: EntityType
    lifecycle_state: EntityLifecycle
    canonicalized_from_candidate_id: str | None = None
    canonical_successor_id: str | None = None
    created_at: datetime
    retired_at: datetime | None = None
    erased_at: datetime | None = None


class CareerClaim(BaseModel):
    model_config = ConfigDict(frozen=True)

    claim_id: str
    claim_family_id: str
    twin_id: str
    subject_entity_id: str

    predicate: Predicate
    object_kind: str
    value: Any | None
    value_type: str

    approval_state: ApprovalState
    lifecycle_state: ClaimLifecycle
    ontology_version: str

    supersedes_claim_id: str | None = None
    rebased_from_claim_id: str | None = None

    valid_from: datetime | None = None
    valid_to: datetime | None = None

    created_at: datetime
    approved_at: datetime | None = None
    retired_at: datetime | None = None
    erased_at: datetime | None = None


class CareerEvidence(BaseModel):
    model_config = ConfigDict(frozen=True)

    evidence_id: str
    twin_id: str

    source_type: str
    source_reference: str | None = None
    evidence_family_id: str

    observed_at: datetime
    extractor_version: str | None = None

    payload_reference: str | None = None
    payload_fingerprint: str

    trust_tier: str
    independence_status: str
    privacy_class: PrivacyClass

    erased_at: datetime | None = None


class ClaimAssessment(BaseModel):
    model_config = ConfigDict(frozen=True)

    assessment_id: str
    claim_id: str
    provenance_trust_tier: str
    claim_confidence: float = Field(ge=0.0, le=1.0)
    evidence_fingerprint: str
    assessed_at: datetime
    algorithm_version: str
