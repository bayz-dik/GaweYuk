from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from onejob.career_intent.models import IntentStrength


class TargetLifecycle(str, Enum):
    ACTIVE = "ACTIVE"
    PAUSED = "PAUSED"
    ARCHIVED = "ARCHIVED"


class OverrideOperation(str, Enum):
    INHERIT = "INHERIT"
    REPLACE = "REPLACE"
    ADD = "ADD"
    REMOVE = "REMOVE"
    CLEAR = "CLEAR"
    EXPLICIT_EXCEPTION = "EXPLICIT_EXCEPTION"


class TargetCompatibilityStatus(str, Enum):
    VALID = "VALID"
    NEEDS_REVIEW = "NEEDS_REVIEW"
    UNSATISFIABLE = "UNSATISFIABLE"


class RoutingMethod(str, Enum):
    USER_SELECTED = "USER_SELECTED"
    AUTO_ROUTED = "AUTO_ROUTED"
    AMBIGUOUS = "AMBIGUOUS"
    UNSCOPED = "UNSCOPED"


class RoutingEligibility(str, Enum):
    ELIGIBLE = "ELIGIBLE"
    INELIGIBLE = "INELIGIBLE"


class ConfidenceBand(str, Enum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    UNKNOWN = "UNKNOWN"


class SavedCareerTargetRecord(BaseModel):
    model_config = ConfigDict(frozen=True)

    target_id: str
    twin_id: str
    active_version_id: str | None
    lifecycle: TargetLifecycle
    created_at: datetime
    created_by_actor_id: str


class SavedCareerTargetVersionRecord(BaseModel):
    model_config = ConfigDict(frozen=True)

    target_version_id: str
    target_id: str
    version_number: int
    supersedes_version_id: str | None
    display_name: str
    role_focus: list[str] = Field(default_factory=list)
    domain_focus: list[str] = Field(default_factory=list)
    explicit_keywords: list[str] = Field(default_factory=list)
    scope_definition: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    input_fingerprint: str


class TargetIntentOverrideRecord(BaseModel):
    model_config = ConfigDict(frozen=True)

    override_id: str
    target_version_id: str
    predicate: str
    operation: OverrideOperation
    value: Any | None = None
    strength: IntentStrength | None = None
    effective_from: datetime | None = None
    expires_at: datetime | None = None
    overrides_statement_id: str | None = None
    explicit_exception_authority: str | None = None


class TargetCompatibilityRecord(BaseModel):
    model_config = ConfigDict(frozen=True)

    compatibility_id: str
    target_id: str
    target_version_id: str
    against_intent_version_id: str
    status: TargetCompatibilityStatus
    reasons: list[str] = Field(default_factory=list)
    checked_at: datetime
    validator_version: str


class RoutingSignal(BaseModel):
    model_config = ConfigDict(frozen=True)

    signal_type: str
    value: Any
    weight: float
    reason: str
    source: str


class TargetApplicabilityAssessment(BaseModel):
    model_config = ConfigDict(frozen=True)

    assessment_id: str
    twin_id: str
    job_context_fingerprint: str
    intent_version_id: str
    target_version_id: str
    eligibility: RoutingEligibility
    applicability_score: float
    confidence_band: ConfidenceBand
    signals: list[RoutingSignal] = Field(default_factory=list)
    reasons: list[str] = Field(default_factory=list)
    router_version: str
    created_at: datetime


class AlternativeTargetAssessment(BaseModel):
    model_config = ConfigDict(frozen=True)

    target_version_id: str
    applicability_score: float
    likely_policy_difference: list[str] = Field(default_factory=list)
    reason: str


class TargetRoutingDecision(BaseModel):
    model_config = ConfigDict(frozen=True)

    routing_decision_id: str
    twin_id: str
    job_context_fingerprint: str
    intent_version_id: str
    method: RoutingMethod
    selected_target_version_id: str | None = None
    winner_score: float | None = None
    winner_margin: float | None = None
    router_version: str
    reasons: list[str] = Field(default_factory=list)
    alternatives: list[AlternativeTargetAssessment] = Field(
        default_factory=list
    )
    created_at: datetime
