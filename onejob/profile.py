from pydantic import BaseModel, Field
from typing import Optional

class WorkExperience(BaseModel):
    title: str
    months: int
    skills: list[str] = Field(default_factory=list)
    responsibilities: list[str] = Field(default_factory=list)

class CareerPolicy(BaseModel):
    min_salary: Optional[int] = None
    excluded_roles: list[str] = Field(default_factory=list)
    max_commute_km: Optional[float] = None

class CareerTwin(BaseModel):
    name: str
    skills: list[str] = Field(default_factory=list)
    preferred_roles: list[str] = Field(default_factory=list)
    preferred_locations: list[str] = Field(default_factory=list)
    experiences: list[WorkExperience] = Field(default_factory=list)
    policy: CareerPolicy = Field(default_factory=CareerPolicy)
    expected_salary: Optional[int] = None
    available_in_days: Optional[int] = None
