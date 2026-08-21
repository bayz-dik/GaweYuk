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


# ---------------------------------------------------------------------------
# Conflict creation decision + candidate-value clustering
# ---------------------------------------------------------------------------

from dataclasses import dataclass, field

from onejob.career_twin.resolution import (
    ValueRelationship,
    classify_value_relationship,
)


def should_open_conflict(
    predicate: Predicate,
    *,
    current: object,
    proposed: object,
) -> bool:
    """A ConflictSet is opened only for genuinely incompatible alternatives.

    Uses ontology-cardinality-aware value relationship classification. Only a
    CONFLICTING relationship (cardinality-ONE, mutually incompatible) opens a
    conflict. Equivalent, compatible, more/less specific, or missing-current
    values never open a conflict.
    """
    relationship = classify_value_relationship(
        predicate,
        current=current,
        proposed=proposed,
    )
    return relationship is ValueRelationship.CONFLICTING


@dataclass(frozen=True)
class ConflictAlternative:
    """A clustered review alternative preserving individual provenance."""

    normalized_value_fingerprint: str
    representative_value: object
    suggestion_ids: list[str] = field(default_factory=list)
    evidence_family_ids: list[str] = field(default_factory=list)

    @property
    def suggestion_count(self) -> int:
        return len(self.suggestion_ids)

    @property
    def evidence_family_count(self) -> int:
        # Independent evidence families, not raw source/suggestion count.
        return len({f for f in self.evidence_family_ids if f is not None})


def build_conflict_clusters(
    predicate: Predicate,
    suggestions: list,
) -> list[ConflictAlternative]:
    """Group equivalent proposed values into one review alternative each.

    Equivalence is decided by the normalized value fingerprint so that values
    differing only by formatting/alias collapse into a single alternative,
    while individual suggestion and evidence-family lineage is preserved. The
    resulting evidence_family_count prefers independent evidence-family counts
    over misleading raw source counts.
    """
    clusters: dict[str, ConflictAlternative] = {}
    order: list[str] = []

    for suggestion in suggestions:
        fingerprint = suggestion.normalized_value_fingerprint
        family = getattr(suggestion, "evidence_family_id", None)

        if fingerprint not in clusters:
            clusters[fingerprint] = ConflictAlternative(
                normalized_value_fingerprint=fingerprint,
                representative_value=suggestion.proposed_value,
                suggestion_ids=[],
                evidence_family_ids=[],
            )
            order.append(fingerprint)

        cluster = clusters[fingerprint]
        cluster.suggestion_ids.append(suggestion.suggestion_id)
        cluster.evidence_family_ids.append(family)

    return [clusters[fp] for fp in order]
