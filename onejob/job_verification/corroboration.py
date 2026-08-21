from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class EvidenceAuthority:
    evidence_id: str
    evidence_family_id: str
    source_id: str
    authoritative: bool = False
    conflicting: bool = False


@dataclass(frozen=True)
class CorroborationSummary:
    appearance_count: int
    independent_family_count: int
    authoritative_family_count: int
    conflicting_family_count: int
    reason_codes: tuple[str, ...] = field(default_factory=tuple)


def summarize_corroboration(
    evidence: tuple[EvidenceAuthority, ...],
) -> CorroborationSummary:
    """Summarize corroboration by independent evidence family, not raw count.

    Multiple mirrors from one upstream family count as a single independent
    source. Raw appearance count is reported separately and never substitutes
    for independent-family count.
    """
    appearance_count = len(evidence)
    families = {e.evidence_family_id for e in evidence}
    authoritative_families = {
        e.evidence_family_id for e in evidence if e.authoritative
    }
    conflicting_families = {
        e.evidence_family_id for e in evidence if e.conflicting
    }

    reasons: list[str] = []
    if appearance_count > len(families):
        reasons.append("MIRRORS_COLLAPSED_TO_FAMILIES")
    if authoritative_families:
        reasons.append("AUTHORITATIVE_FAMILY_PRESENT")

    return CorroborationSummary(
        appearance_count=appearance_count,
        independent_family_count=len(families),
        authoritative_family_count=len(authoritative_families),
        conflicting_family_count=len(conflicting_families),
        reason_codes=tuple(reasons),
    )
