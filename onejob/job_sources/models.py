from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

from onejob.ingestion.models import SourceType


class SourceTrustTier(str, Enum):
    TIER_1_OFFICIAL = "TIER_1_OFFICIAL"
    TIER_2_AUTHORIZED = "TIER_2_AUTHORIZED"
    TIER_3_DISCOVERY = "TIER_3_DISCOVERY"


class AcquisitionMethod(str, Enum):
    OFFICIAL_API = "OFFICIAL_API"
    PARTNER_API = "PARTNER_API"
    PUBLIC_FEED = "PUBLIC_FEED"
    STRUCTURED_PUBLIC_PAGE = "STRUCTURED_PUBLIC_PAGE"
    PERMITTED_HTML = "PERMITTED_HTML"
    MANUAL_IMPORT = "MANUAL_IMPORT"
    USER_SUPPLIED = "USER_SUPPLIED"


class ComplianceStatus(str, Enum):
    ALLOWED = "ALLOWED"
    UNKNOWN = "UNKNOWN"
    POLICY_BLOCKED = "POLICY_BLOCKED"


class SourceRolloutState(str, Enum):
    REGISTERED = "REGISTERED"
    SHADOW = "SHADOW"
    OBSERVED = "OBSERVED"
    VALIDATED = "VALIDATED"
    ACTIVE = "ACTIVE"
    DEGRADED = "DEGRADED"
    DISABLED = "DISABLED"
    POLICY_BLOCKED = "POLICY_BLOCKED"


class SourceHealthState(str, Enum):
    UNKNOWN = "UNKNOWN"
    HEALTHY = "HEALTHY"
    DEGRADED = "DEGRADED"
    RATE_LIMITED = "RATE_LIMITED"
    AUTH_REQUIRED = "AUTH_REQUIRED"
    SCHEMA_CHANGED = "SCHEMA_CHANGED"
    DISABLED = "DISABLED"
    POLICY_BLOCKED = "POLICY_BLOCKED"


class JobSource(BaseModel):
    model_config = ConfigDict(frozen=True)

    source_id: str
    source_key: str
    source_type: SourceType
    trust_tier: SourceTrustTier
    acquisition_method: AcquisitionMethod
    primary_domain: str | None = None
    country_scope: tuple[str, ...] = ()
    compliance_status: ComplianceStatus
    rollout_state: SourceRolloutState
    health_state: SourceHealthState
    verification_policy_version: str
    created_at: datetime
    updated_at: datetime

    @field_validator("country_scope")
    @classmethod
    def normalize_countries(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        # ISO country codes only; no default region is assumed so the model
        # stays global-ready even though rollout prioritizes Indonesia.
        return tuple(sorted({country.upper() for country in value}))

    @model_validator(mode="after")
    def enforce_activation_policy(self):
        # A source cannot be ACTIVE (contribute publication authority) unless
        # its acquisition is explicitly compliant. UNKNOWN never self-promotes.
        if (
            self.rollout_state is SourceRolloutState.ACTIVE
            and self.compliance_status is not ComplianceStatus.ALLOWED
        ):
            raise ValueError("ACTIVE source requires allowed compliance")
        return self
