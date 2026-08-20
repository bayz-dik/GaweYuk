from collections import OrderedDict

import pytest

from onejob.trust_engine.models import (
    DimensionState,
    TrustDimension,
)
from onejob.trust_engine.scoring import (
    DIMENSION_WEIGHTS,
    DimensionInput,
    TrustInputs,
    aggregate_trust,
    score_dimensions,
)


def known(score, confidence=100.0):
    return DimensionInput(
        state=DimensionState.KNOWN,
        score=score,
        confidence=confidence,
    )


def unknown(reason="MISSING_EVIDENCE"):
    return DimensionInput(
        state=DimensionState.UNKNOWN,
        score=None,
        confidence=None,
        reason_codes=(reason,),
    )


def na(reason="NOT_RELEVANT"):
    return DimensionInput(
        state=DimensionState.NOT_APPLICABLE,
        score=None,
        confidence=None,
        reason_codes=(reason,),
    )


def test_weights_sum_to_100_percent():
    assert sum(DIMENSION_WEIGHTS.values()) == pytest.approx(1.0)


def test_score_dimensions_always_returns_all_seven_dimensions():
    result = score_dimensions(
        TrustInputs(
            dimensions={
                TrustDimension.COMPANY_IDENTITY: known(90),
            }
        )
    )

    assert set(result) == set(TrustDimension)
    assert (
        result[TrustDimension.SOURCE_CREDIBILITY].state
        is DimensionState.UNKNOWN
    )


def test_all_known_equal_scores_preserve_that_score():
    dimensions = score_dimensions(
        TrustInputs(
            dimensions={
                dimension: known(80)
                for dimension in TrustDimension
            }
        )
    )

    overall, confidence = aggregate_trust(dimensions)

    assert overall == pytest.approx(80.0)
    assert confidence == pytest.approx(100.0)


def test_unknown_does_not_fabricate_trust_score_but_reduces_confidence():
    dimensions = score_dimensions(
        TrustInputs(
            dimensions={
                TrustDimension.COMPANY_IDENTITY: known(90),
                TrustDimension.PRIVACY_SAFETY: unknown(),
                TrustDimension.SOURCE_CREDIBILITY: na(),
                TrustDimension.LISTING_INTEGRITY: na(),
                TrustDimension.EVIDENCE_CONSENSUS: na(),
                TrustDimension.RECRUITER_INTEGRITY: na(),
                TrustDimension.FRESHNESS: na(),
            }
        )
    )

    overall, confidence = aggregate_trust(dimensions)

    # UNKNOWN privacy must not be converted to fake 0 or 50.
    assert overall == pytest.approx(90.0)

    # But missing applicable evidence must reduce confidence.
    assert confidence < 100.0
    assert confidence == pytest.approx(
        100.0 * 0.18 / (0.18 + 0.16)
    )


def test_not_applicable_does_not_reduce_confidence():
    dimensions = score_dimensions(
        TrustInputs(
            dimensions={
                TrustDimension.COMPANY_IDENTITY: known(91),
                TrustDimension.SOURCE_CREDIBILITY: na(),
                TrustDimension.LISTING_INTEGRITY: na(),
                TrustDimension.EVIDENCE_CONSENSUS: na(),
                TrustDimension.RECRUITER_INTEGRITY: na(),
                TrustDimension.PRIVACY_SAFETY: na(),
                TrustDimension.FRESHNESS: na(),
            }
        )
    )

    overall, confidence = aggregate_trust(dimensions)

    assert overall == pytest.approx(91.0)
    assert confidence == pytest.approx(100.0)


def test_dimension_confidence_contributes_to_overall_confidence():
    dimensions = score_dimensions(
        TrustInputs(
            dimensions={
                TrustDimension.COMPANY_IDENTITY: known(
                    95,
                    confidence=50,
                ),
                TrustDimension.SOURCE_CREDIBILITY: na(),
                TrustDimension.LISTING_INTEGRITY: na(),
                TrustDimension.EVIDENCE_CONSENSUS: na(),
                TrustDimension.RECRUITER_INTEGRITY: na(),
                TrustDimension.PRIVACY_SAFETY: na(),
                TrustDimension.FRESHNESS: na(),
            }
        )
    )

    overall, confidence = aggregate_trust(dimensions)

    assert overall == pytest.approx(95.0)
    assert confidence == pytest.approx(50.0)


def test_source_outage_reduces_confidence_not_trust_score():
    healthy = score_dimensions(
        TrustInputs(
            dimensions={
                TrustDimension.COMPANY_IDENTITY: known(95, 100),
                TrustDimension.SOURCE_CREDIBILITY: known(85, 100),
                TrustDimension.LISTING_INTEGRITY: na(),
                TrustDimension.EVIDENCE_CONSENSUS: na(),
                TrustDimension.RECRUITER_INTEGRITY: na(),
                TrustDimension.PRIVACY_SAFETY: na(),
                TrustDimension.FRESHNESS: na(),
            }
        )
    )

    degraded = score_dimensions(
        TrustInputs(
            dimensions={
                TrustDimension.COMPANY_IDENTITY: known(95, 100),
                # Same trust score, weaker reliability/coverage confidence.
                TrustDimension.SOURCE_CREDIBILITY: known(85, 25),
                TrustDimension.LISTING_INTEGRITY: na(),
                TrustDimension.EVIDENCE_CONSENSUS: na(),
                TrustDimension.RECRUITER_INTEGRITY: na(),
                TrustDimension.PRIVACY_SAFETY: na(),
                TrustDimension.FRESHNESS: na(),
            }
        )
    )

    healthy_score, healthy_conf = aggregate_trust(healthy)
    degraded_score, degraded_conf = aggregate_trust(degraded)

    assert degraded_score == pytest.approx(healthy_score)
    assert degraded_conf < healthy_conf

    assert (
        degraded[TrustDimension.COMPANY_IDENTITY].score
        == pytest.approx(95)
    )


def test_mapping_order_does_not_change_result():
    forward = OrderedDict(
        (
            dimension,
            known(60 + index * 5, 70 + index),
        )
        for index, dimension in enumerate(TrustDimension)
    )

    reverse = OrderedDict(reversed(list(forward.items())))

    a = aggregate_trust(
        score_dimensions(
            TrustInputs(dimensions=forward)
        )
    )
    b = aggregate_trust(
        score_dimensions(
            TrustInputs(dimensions=reverse)
        )
    )

    assert a == pytest.approx(b)


def test_invalid_known_score_fails_in_domain_contract():
    inputs = TrustInputs(
        dimensions={
            TrustDimension.COMPANY_IDENTITY: DimensionInput(
                state=DimensionState.KNOWN,
                score=101,
                confidence=100,
            )
        }
    )

    with pytest.raises(
        ValueError,
        match="score must be between 0 and 100",
    ):
        score_dimensions(inputs)
