from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Mapping


class RecruitmentStage(str, Enum):
    DISCOVERY = "DISCOVERY"
    APPLICATION = "APPLICATION"
    SCREENING = "SCREENING"
    INTERVIEW = "INTERVIEW"
    OFFER = "OFFER"
    ONBOARDING = "ONBOARDING"
    UNKNOWN = "UNKNOWN"


class DimensionState(str, Enum):
    KNOWN = "KNOWN"
    UNKNOWN = "UNKNOWN"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class TrustDimension(str, Enum):
    COMPANY_IDENTITY = "COMPANY_IDENTITY"
    SOURCE_CREDIBILITY = "SOURCE_CREDIBILITY"
    LISTING_INTEGRITY = "LISTING_INTEGRITY"
    EVIDENCE_CONSENSUS = "EVIDENCE_CONSENSUS"
    RECRUITER_INTEGRITY = "RECRUITER_INTEGRITY"
    PRIVACY_SAFETY = "PRIVACY_SAFETY"
    FRESHNESS = "FRESHNESS"


class SignalLevel(str, Enum):
    L1 = "L1"
    L2 = "L2"
    L3 = "L3"
    L4 = "L4"


class SignalStatus(str, Enum):
    ACTIVE = "ACTIVE"
    RESOLVED = "RESOLVED"
    EXPIRED = "EXPIRED"


class DetectionMethod(str, Enum):
    RULE = "RULE"
    AI = "AI"
    EXTERNAL = "EXTERNAL"
    HUMAN = "HUMAN"


class TrustClassification(str, Enum):
    AUTOPILOT_ELIGIBLE = "AUTOPILOT_ELIGIBLE"
    ASSISTED_ALLOWED = "ASSISTED_ALLOWED"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"
    AUTOMATION_BLOCKED = "AUTOMATION_BLOCKED"
    ABSOLUTE_BLOCK = "ABSOLUTE_BLOCK"


class ActionMode(str, Enum):
    MANUAL = "MANUAL"
    ASSISTED = "ASSISTED"
    AUTOPILOT = "AUTOPILOT"


class ActionDecision(str, Enum):
    ALLOWED = "ALLOWED"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"
    DENIED = "DENIED"


@dataclass(frozen=True)
class DimensionScore:
    dimension: TrustDimension
    state: DimensionState
    score: float | None
    confidence: float | None
    reason_codes: tuple[str, ...]
    evidence_refs: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.state is DimensionState.KNOWN:
            if self.score is None or self.confidence is None:
                raise ValueError(
                    "KNOWN dimension requires score and confidence"
                )
        else:
            if self.score is not None:
                raise ValueError(
                    "non-KNOWN dimension cannot have score"
                )
            if self.confidence is not None:
                raise ValueError(
                    "non-KNOWN dimension cannot have confidence"
                )

        if self.score is not None and not 0 <= self.score <= 100:
            raise ValueError("score must be between 0 and 100")

        if self.confidence is not None and not 0 <= self.confidence <= 100:
            raise ValueError(
                "confidence must be between 0 and 100"
            )


@dataclass(frozen=True)
class TrustSignal:
    signal_id: str
    canonical_job_id: str
    signal_type: str
    level: SignalLevel
    status: SignalStatus
    confidence: float
    detection_method: DetectionMethod
    context_stage: RecruitmentStage
    evidence_refs: tuple[str, ...]
    extractor_version: str
    fingerprint: str
    first_seen_at: datetime
    last_seen_at: datetime
    resolved_at: datetime | None = None
    resolution_reason: str | None = None

    def __post_init__(self) -> None:
        if not 0 <= self.confidence <= 1:
            raise ValueError(
                "signal confidence must be between 0 and 1"
            )


@dataclass(frozen=True)
class GateHit:
    signal_id: str
    gate_code: str
    level: SignalLevel
    effect: TrustClassification
    override_policy: str


@dataclass(frozen=True)
class TrustDecision:
    evaluation_id: str
    canonical_job_id: str
    recruitment_stage: RecruitmentStage
    overall_score: float
    confidence: float
    dimensions: Mapping[TrustDimension, DimensionScore]
    classification: TrustClassification
    hard_gates: tuple[GateHit, ...]
    risk_signal_ids: tuple[str, ...]
    unknown_dimensions: tuple[TrustDimension, ...]
    not_applicable_dimensions: tuple[TrustDimension, ...]
    allowed_actions: tuple[str, ...]
    blocked_actions: tuple[str, ...]
    override_policy: str
    primary_reasons: tuple[str, ...]
    evidence_refs: tuple[str, ...]
    evaluated_at: datetime
    valid_until: datetime | None
    input_fingerprint: str
    policy_version: str

    def __post_init__(self) -> None:
        if not 0 <= self.overall_score <= 100:
            raise ValueError(
                "overall_score must be between 0 and 100"
            )
        if not 0 <= self.confidence <= 100:
            raise ValueError(
                "confidence must be between 0 and 100"
            )


@dataclass(frozen=True)
class ConsentGrant:
    consent_id: str
    user_id: str
    canonical_job_id: str
    company_id: str
    scope: str
    recruitment_stage: RecruitmentStage
    issued_at: datetime
    expires_at: datetime
    revoked_at: datetime | None = None
