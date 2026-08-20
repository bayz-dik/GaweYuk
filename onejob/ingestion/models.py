from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class SourceType(str, Enum):
    ATS = "ats"
    JOB_PORTAL = "job_portal"
    COMPANY_CAREER = "company_career"
    GOVERNMENT = "government"
    AGENCY = "agency"
    UNIVERSITY = "university"
    EVENT = "event"
    OPEN_WEB = "open_web"
    USER_SUPPLIED = "user_supplied"


class RawJobObservation(BaseModel):
    model_config = ConfigDict(frozen=True)

    observation_id: str
    source_key: str
    source_type: SourceType
    collector_version: str
    external_id: str
    source_url: str
    canonical_hint_url: Optional[str] = None
    observed_at: datetime
    published_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    expires_at: Optional[datetime] = None
    title: str
    company_name: str
    location_text: str
    description: str
    salary_min: Optional[int] = None
    salary_max: Optional[int] = None
    currency: Optional[str] = None
    employment_type: Optional[str] = None
    skills: list[str] = Field(default_factory=list)
    contact_email: Optional[str] = None
    source_payload_hash: str
    raw_payload_reference: Optional[str] = None
