from __future__ import annotations
from pydantic import BaseModel, Field
from typing import Optional

class JobSource(BaseModel):
    name: str
    external_id: str
    apply_url: str
    official: bool = False

class RawJob(BaseModel):
    source: str
    external_id: str
    title: str
    company: str
    location: str
    description: str
    apply_url: str
    salary_min: Optional[int] = None
    salary_max: Optional[int] = None
    skills: list[str] = Field(default_factory=list)
    official_source: bool = False
    contact_email: Optional[str] = None

class CanonicalJob(BaseModel):
    id: str
    title: str
    company: str
    location: str
    description: str
    normalized_title: str
    normalized_company: str
    normalized_location: str
    salary_min: Optional[int] = None
    salary_max: Optional[int] = None
    skills: list[str] = Field(default_factory=list)
    contact_email: Optional[str] = None
    sources: list[JobSource] = Field(default_factory=list)
