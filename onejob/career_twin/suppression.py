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


# ---------------------------------------------------------------------------
# Suppression policy
# ---------------------------------------------------------------------------

import hashlib
from dataclasses import dataclass


def suppression_fingerprint(
    *,
    twin_id: str,
    predicate: Predicate,
    normalized_value_fingerprint: str,
    entity_scope: str | None = None,
    candidate_scope: str | None = None,
    evidence_family_scope: str | None = None,
    source_scope: str | None = None,
) -> str:
    """Deterministic suppression fingerprint over the relevant scope combo."""
    payload = "\x1f".join(
        [
            twin_id,
            predicate.value,
            normalized_value_fingerprint,
            entity_scope or "",
            candidate_scope or "",
            evidence_family_scope or "",
            source_scope or "",
        ]
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class SuppressionDecision:
    suppressed: bool
    strength: SuppressionStrength | None = None
    reopen: bool = False
    reason: str | None = None


def evaluate_suppression(
    *,
    active_records: list[SuppressionRecord],
    incoming_evidence_family_id: str | None,
    incoming_evidence_independent: bool,
) -> SuppressionDecision:
    """Decide whether an incoming proposal is suppressed.

    Rules (spec section 13):
    - STRONG suppression blocks recurrence until explicitly lifted, even with
      materially new independent evidence.
    - SOFT suppression blocks repeated proposals with materially identical
      evidence (same family, or non-independent evidence). Materially new
      *independent* evidence reopens review.
    - INDEPENDENCE_UNKNOWN (independent=False) never counts as independent
      support, so it cannot reopen a SOFT suppression.
    """
    if not active_records:
        return SuppressionDecision(suppressed=False)

    strong = [
        r for r in active_records if r.strength is SuppressionStrength.STRONG
    ]
    if strong:
        return SuppressionDecision(
            suppressed=True,
            strength=SuppressionStrength.STRONG,
            reopen=False,
            reason="strong suppression active",
        )

    # Only SOFT records remain.
    # Materially new independent evidence reopens SOFT suppression.
    soft_scopes = {r.evidence_family_scope for r in active_records}
    materially_new = (
        incoming_evidence_independent
        and incoming_evidence_family_id is not None
        and incoming_evidence_family_id not in soft_scopes
    )

    if materially_new:
        return SuppressionDecision(
            suppressed=False,
            strength=SuppressionStrength.SOFT,
            reopen=True,
            reason="materially new independent evidence",
        )

    return SuppressionDecision(
        suppressed=True,
        strength=SuppressionStrength.SOFT,
        reopen=False,
        reason="soft suppression, no materially new independent evidence",
    )
