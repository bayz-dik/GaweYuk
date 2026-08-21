from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class PublicVerificationSummary(BaseModel):
    model_config = ConfigDict(frozen=True)

    confidence: float | None = None
    checked_at: str | None = None
    appearance_count: int = 0
    independent_evidence_family_count: int = 0
    primary_reason_codes: tuple[str, ...] = ()


class PublicApplyDestination(BaseModel):
    model_config = ConfigDict(frozen=True)

    status: str
    domain: str | None = None


class PublicJob(BaseModel):
    model_config = ConfigDict(frozen=True)

    canonical_job_id: str
    title: str
    company: str
    location: str
    employment_type: str | None = None
    salary_min: int | None = None
    salary_max: int | None = None
    currency: str | None = None
    lifecycle: str = "ACTIVE"
    catalog_published_at: str | None = None
    verification_summary: PublicVerificationSummary = Field(
        default_factory=PublicVerificationSummary
    )
