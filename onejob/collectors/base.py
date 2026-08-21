from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Protocol

from pydantic import BaseModel, Field

from onejob.ingestion.models import RawJobObservation, SourceType
from onejob.job_sources.models import AcquisitionMethod


class CollectorHealthStatus(str, Enum):
    HEALTHY = "HEALTHY"
    DEGRADED = "DEGRADED"
    RATE_LIMITED = "RATE_LIMITED"
    BROKEN = "BROKEN"
    DISABLED = "DISABLED"
    UNKNOWN = "UNKNOWN"


class CollectionStatus(str, Enum):
    SUCCESS = "SUCCESS"
    PARTIAL = "PARTIAL"
    FAILED = "FAILED"
    RATE_LIMITED = "RATE_LIMITED"


class CollectionTarget(BaseModel):
    tenant: str


class CollectionBatch(BaseModel):
    source_key: str
    source_type: SourceType
    collector_version: str
    target: CollectionTarget
    started_at: datetime
    finished_at: datetime
    status: CollectionStatus
    observations: list[RawJobObservation] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    error_summary: str | None = None


class Collector(Protocol):
    source_key: str
    source_type: SourceType
    collector_version: str
    acquisition_method: AcquisitionMethod

    def collect(self, target: CollectionTarget) -> CollectionBatch: ...
