from __future__ import annotations

from dataclasses import dataclass, field
from difflib import SequenceMatcher
from enum import Enum


class JobIdentityDisposition(str, Enum):
    SAME = "SAME"
    DISTINCT = "DISTINCT"
    AMBIGUOUS = "AMBIGUOUS"


@dataclass(frozen=True)
class JobIdentityCandidate:
    canonical_job_id: str | None
    company_id: str
    source_id: str
    external_id: str
    authoritative_external_id: bool
    title: str
    location: str
    description: str
    employment_type: str | None = None


@dataclass(frozen=True)
class JobIdentityDecision:
    disposition: JobIdentityDisposition
    canonical_job_id: str | None
    score: float
    reason_codes: tuple[str, ...] = field(default_factory=tuple)


# Similarity thresholds. A single fuzzy score never decides identity on its
# own; these gate the tri-state outcome and a hard company mismatch vetoes SAME.
_SAME_THRESHOLD = 0.86
_DISTINCT_THRESHOLD = 0.55


def _norm(value: str | None) -> str:
    return " ".join((value or "").casefold().split())


def _similarity(a: str | None, b: str | None) -> float:
    left, right = _norm(a), _norm(b)
    if not left or not right:
        return 0.0
    if left == right:
        return 1.0
    return SequenceMatcher(None, left, right).ratio()


def _fuzzy_score(incoming: JobIdentityCandidate, existing: JobIdentityCandidate) -> float:
    title = _similarity(incoming.title, existing.title)
    location = _similarity(incoming.location, existing.location)
    description = _similarity(incoming.description, existing.description)
    return round(title * 0.45 + location * 0.25 + description * 0.30, 6)


class JobEntityResolver:
    """Three-way job identity resolution.

    A verified company + authoritative requisition identity match is a strong
    key that outranks fuzzy similarity. When multiple existing candidates score
    closely, the result is AMBIGUOUS and never silently merged.
    """

    def resolve(
        self,
        *,
        incoming: JobIdentityCandidate,
        existing: tuple[JobIdentityCandidate, ...],
    ) -> JobIdentityDecision:
        if not existing:
            return JobIdentityDecision(
                disposition=JobIdentityDisposition.DISTINCT,
                canonical_job_id=None,
                score=0.0,
                reason_codes=("NO_EXISTING_CANDIDATE",),
            )

        # Strong key: same verified company + authoritative requisition id.
        for candidate in existing:
            if (
                incoming.authoritative_external_id
                and candidate.authoritative_external_id
                and incoming.company_id == candidate.company_id
                and incoming.source_id == candidate.source_id
                and incoming.external_id == candidate.external_id
            ):
                return JobIdentityDecision(
                    disposition=JobIdentityDisposition.SAME,
                    canonical_job_id=candidate.canonical_job_id,
                    score=1.0,
                    reason_codes=("AUTHORITATIVE_REQUISITION_MATCH",),
                )

        # Fuzzy fallback only among same-company candidates. A company mismatch
        # is a hard contradiction that cannot be overridden by text similarity.
        same_company = [c for c in existing if c.company_id == incoming.company_id]
        if not same_company:
            return JobIdentityDecision(
                disposition=JobIdentityDisposition.DISTINCT,
                canonical_job_id=None,
                score=0.0,
                reason_codes=("COMPANY_MISMATCH",),
            )

        scored = sorted(
            ((_fuzzy_score(incoming, c), c) for c in same_company),
            key=lambda item: (-item[0], item[1].canonical_job_id or ""),
        )
        top_score, top = scored[0]
        second_score = scored[1][0] if len(scored) > 1 else 0.0

        if top_score < _DISTINCT_THRESHOLD:
            return JobIdentityDecision(
                disposition=JobIdentityDisposition.DISTINCT,
                canonical_job_id=None,
                score=top_score,
                reason_codes=("LOW_SIMILARITY_DISTINCT",),
            )

        # More than one plausible candidate (another also above the distinct
        # floor) means we cannot be sure which requisition this is -> ambiguous.
        if len(scored) > 1 and second_score >= _DISTINCT_THRESHOLD:
            return JobIdentityDecision(
                disposition=JobIdentityDisposition.AMBIGUOUS,
                canonical_job_id=None,
                score=top_score,
                reason_codes=("CLOSE_MULTIPLE_CANDIDATES",),
            )

        if top_score >= _SAME_THRESHOLD:
            return JobIdentityDecision(
                disposition=JobIdentityDisposition.SAME,
                canonical_job_id=top.canonical_job_id,
                score=top_score,
                reason_codes=("HIGH_SIMILARITY_SAME",),
            )

        # In the uncertain middle band: do not merge.
        return JobIdentityDecision(
            disposition=JobIdentityDisposition.AMBIGUOUS,
            canonical_job_id=None,
            score=top_score,
            reason_codes=("UNCERTAIN_SIMILARITY",),
        )
