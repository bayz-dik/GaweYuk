from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict


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
