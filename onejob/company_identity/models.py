from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, field_validator


class IdentityNodeType(str, Enum):
    COMPANY = "COMPANY"
    LEGAL_ENTITY = "LEGAL_ENTITY"
    BRAND = "BRAND"
    DOMAIN = "DOMAIN"
    CAREER_DOMAIN = "CAREER_DOMAIN"
    ATS_TENANT = "ATS_TENANT"


class IdentityRelationshipType(str, Enum):
    OWNED_BY = "OWNED_BY"
    CAREER_SITE_FOR = "CAREER_SITE_FOR"
    ATS_FOR = "ATS_FOR"
    BRAND_OF = "BRAND_OF"
    SUBSIDIARY_OF = "SUBSIDIARY_OF"
    ALIAS_OF = "ALIAS_OF"


class IdentityRelationshipStatus(str, Enum):
    VERIFIED = "VERIFIED"
    PROBABLE = "PROBABLE"
    DISPUTED = "DISPUTED"
    REVOKED = "REVOKED"


class CompanyIdentityResolutionState(str, Enum):
    VERIFIED = "VERIFIED"
    PROBABLE = "PROBABLE"
    AMBIGUOUS = "AMBIGUOUS"
    CONFLICTING = "CONFLICTING"
    UNKNOWN = "UNKNOWN"


class IdentityNode(BaseModel):
    model_config = ConfigDict(frozen=True)

    node_id: str
    node_type: IdentityNodeType
    value: str
    created_at: datetime


class IdentityRelationship(BaseModel):
    model_config = ConfigDict(frozen=True)

    relationship_id: str
    company_id: str
    node_id: str
    relationship_type: IdentityRelationshipType
    status: IdentityRelationshipStatus
    confidence: float
    verification_method: str
    evidence_refs: tuple[str, ...] = ()
    first_verified_at: datetime
    last_verified_at: datetime

    @field_validator("confidence")
    @classmethod
    def confidence_in_range(cls, value: float) -> float:
        if not 0.0 <= value <= 1.0:
            raise ValueError("confidence must be within 0.0..1.0")
        return value


class CompanyIdentitySnapshot(BaseModel):
    model_config = ConfigDict(frozen=True)

    snapshot_id: str
    company_id: str
    state: CompanyIdentityResolutionState
    input_fingerprint: str
    reason_codes: tuple[str, ...] = ()
    created_at: datetime


class CompanyIdentityResolution(BaseModel):
    model_config = ConfigDict(frozen=True)

    company_id: str
    state: CompanyIdentityResolutionState
    reason_codes: tuple[str, ...] = ()
