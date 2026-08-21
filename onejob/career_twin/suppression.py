from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict

from onejob.career_twin.ontology import Predicate


class SuppressionStrength(str, Enum):
    SOFT = "SOFT"
    STRONG = "STRONG"


class SuppressionRecord(BaseModel):
    """User/system memory about repeated proposals.

    Never projected as a career fact and never written into the Claim Ledger.
    """

    model_config = ConfigDict(frozen=True)

    suppression_id: str
    twin_id: str
    entity_scope: str | None = None
    candidate_scope: str | None = None
    predicate: Predicate
    normalized_value_fingerprint: str
    evidence_family_scope: str | None = None
    source_scope: str | None = None
    strength: SuppressionStrength
    reason: str | None = None
    created_at: datetime
    expires_at: datetime | None = None
    lifted_at: datetime | None = None
