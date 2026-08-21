from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict


class ConfidenceBand(str, Enum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    UNKNOWN = "UNKNOWN"


class EntityResolution(BaseModel):
    """Appendable/versioned resolution assessment. Never mutable truth.

    Even a HIGH band only authorizes routing/linking; it never grants
    claim-approval authority.
    """

    model_config = ConfigDict(frozen=True)

    resolution_id: str
    candidate_id: str
    proposed_entity_id: str | None = None
    confidence: float | None = None
    confidence_band: ConfidenceBand
    method: str
    algorithm_version: str
    input_fingerprint: str
    signals_json: str = "{}"
    created_at: datetime
    supersedes_resolution_id: str | None = None
