from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class ApplyDestinationStatus(str, Enum):
    VERIFIED = "VERIFIED"
    ALLOWED_EXTERNAL = "ALLOWED_EXTERNAL"
    UNKNOWN = "UNKNOWN"
    SUSPICIOUS = "SUSPICIOUS"
    BLOCKED = "BLOCKED"


class ApplyDestinationAssessment(BaseModel):
    model_config = ConfigDict(frozen=True)

    original_apply_url: str | None
    resolved_apply_url: str | None
    resolved_domain: str | None
    redirect_chain_fingerprint: str | None
    destination_status: ApplyDestinationStatus
    reason_codes: tuple[str, ...] = ()


class JobVerificationSnapshot(BaseModel):
    model_config = ConfigDict(frozen=True)

    verification_id: str
    canonical_job_id: str
    canonical_version_id: str | None
    identity_snapshot_id: str | None
    trust_evaluation_id: str | None
    identity_state: str
    trust_classification: str
    destination_status: ApplyDestinationStatus
    freshness_state: str
    corroboration: dict[str, object] = Field(default_factory=dict)
    hard_gate_hits: tuple[str, ...] = ()
    unknowns: tuple[str, ...] = ()
    evaluated_at: datetime
    valid_until: datetime
    input_fingerprint: str
    verification_policy_version: str
