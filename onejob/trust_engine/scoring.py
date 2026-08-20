from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping

from .models import (
    DimensionScore,
    DimensionState,
    TrustDimension,
)


DIMENSION_WEIGHTS: dict[TrustDimension, float] = {
    TrustDimension.COMPANY_IDENTITY: 0.18,
    TrustDimension.SOURCE_CREDIBILITY: 0.16,
    TrustDimension.LISTING_INTEGRITY: 0.14,
    TrustDimension.EVIDENCE_CONSENSUS: 0.14,
    TrustDimension.RECRUITER_INTEGRITY: 0.14,
    TrustDimension.PRIVACY_SAFETY: 0.16,
    TrustDimension.FRESHNESS: 0.08,
}


@dataclass(frozen=True)
class DimensionInput:
    state: DimensionState
    score: float | None
    confidence: float | None
    reason_codes: tuple[str, ...] = ()
    evidence_refs: tuple[str, ...] = ()


@dataclass(frozen=True)
class TrustInputs:
    dimensions: Mapping[
        TrustDimension,
        DimensionInput,
    ] = field(default_factory=dict)


def score_dimensions(
    inputs: TrustInputs,
) -> dict[TrustDimension, DimensionScore]:
    result: dict[TrustDimension, DimensionScore] = {}

    for dimension in TrustDimension:
        raw = inputs.dimensions.get(dimension)

        if raw is None:
            raw = DimensionInput(
                state=DimensionState.UNKNOWN,
                score=None,
                confidence=None,
                reason_codes=("MISSING_DIMENSION_INPUT",),
                evidence_refs=(),
            )

        result[dimension] = DimensionScore(
            dimension=dimension,
            state=raw.state,
            score=raw.score,
            confidence=raw.confidence,
            reason_codes=tuple(raw.reason_codes),
            evidence_refs=tuple(raw.evidence_refs),
        )

    return result


def aggregate_trust(
    dimensions: Mapping[
        TrustDimension,
        DimensionScore,
    ],
) -> tuple[float, float]:
    known_weight = 0.0
    applicable_weight = 0.0

    weighted_score = 0.0
    weighted_confidence = 0.0

    for dimension in TrustDimension:
        weight = DIMENSION_WEIGHTS[dimension]

        item = dimensions.get(dimension)

        if item is None:
            # Missing entry behaves as UNKNOWN:
            # applicable, but unsupported.
            applicable_weight += weight
            continue

        if item.state is DimensionState.NOT_APPLICABLE:
            continue

        applicable_weight += weight

        if item.state is not DimensionState.KNOWN:
            continue

        assert item.score is not None
        assert item.confidence is not None

        known_weight += weight
        weighted_score += weight * item.score
        weighted_confidence += weight * item.confidence

    if known_weight == 0:
        # No supported trust estimate exists.
        # Confidence=0 prevents autonomous use.
        return 0.0, 0.0

    overall_score = weighted_score / known_weight

    if applicable_weight == 0:
        overall_confidence = 0.0
    else:
        # UNKNOWN contributes no confidence while still remaining
        # applicable. NOT_APPLICABLE is excluded entirely.
        overall_confidence = (
            weighted_confidence / applicable_weight
        )

    return (
        round(overall_score, 6),
        round(overall_confidence, 6),
    )
