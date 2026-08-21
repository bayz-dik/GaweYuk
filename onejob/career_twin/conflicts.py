from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict

from onejob.career_twin.ontology import Predicate


class ConflictStatus(str, Enum):
    OPEN = "OPEN"
    RESOLVED = "RESOLVED"


class ConflictSet(BaseModel):
    """Mutually incompatible alternatives for a canonical claim family."""

    model_config = ConfigDict(frozen=True)

    conflict_id: str
    twin_id: str
    entity_id: str
    predicate: Predicate
    active_claim_id: str | None = None
    status: ConflictStatus
    version: int
    created_at: datetime
    resolved_at: datetime | None = None
    resolution_type: str | None = None
    resolution_claim_id: str | None = None
