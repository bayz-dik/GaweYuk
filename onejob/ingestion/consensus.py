from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class SourceConflict(BaseModel):
    conflict_id: str
    canonical_job_id: str
    field_name: str
    status: str
    evidence_ids: list[str]
    detected_at: object | None = None
    resolved_at: object | None = None


class ConsensusValue(BaseModel):
    field_name: str
    selected_value: Any
    confidence: float
    primary_evidence_ids: list[str]
    conflicting_evidence_ids: list[str]
    resolution_reason: str


def resolve_field_consensus(
    field_name: str,
    evidence: list[dict],
) -> ConsensusValue:
    if not evidence:
        return ConsensusValue(
            field_name=field_name,
            selected_value=None,
            confidence=0.10,
            primary_evidence_ids=[],
            conflicting_evidence_ids=[],
            resolution_reason="no_evidence",
        )

    ranked = sorted(
        evidence,
        key=lambda item: item["confidence"],
        reverse=True,
    )

    winner = ranked[0]
    selected_value = winner.get("value")
    winner_family = winner["evidence_family_id"]

    primary_ids = [winner["evidence_id"]]
    conflicting_ids: list[str] = []
    confirming_families: set[str] = {winner_family}
    conflicting_families: set[str] = set()

    confidence = float(winner["confidence"])

    for item in ranked[1:]:
        value = item.get("value")
        family = item["evidence_family_id"]

        if value == selected_value:
            primary_ids.append(item["evidence_id"])

            if family not in confirming_families:
                confirming_families.add(family)
                confidence += 0.04
        elif value is not None:
            conflicting_ids.append(item["evidence_id"])

            if family not in conflicting_families:
                conflicting_families.add(family)
                confidence -= 0.04

    confidence = max(0.10, min(0.99, confidence))

    reason = (
        "highest_confidence_with_conflict"
        if conflicting_ids
        else "highest_confidence"
    )

    return ConsensusValue(
        field_name=field_name,
        selected_value=selected_value,
        confidence=confidence,
        primary_evidence_ids=primary_ids,
        conflicting_evidence_ids=conflicting_ids,
        resolution_reason=reason,
    )
