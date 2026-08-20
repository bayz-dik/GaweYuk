from datetime import datetime, timezone

from onejob.trust_engine.models import (
    DetectionMethod,
    DimensionScore,
    DimensionState,
    RecruitmentStage,
    SignalLevel,
    SignalStatus,
    TrustClassification,
    TrustDimension,
    TrustSignal,
)
from onejob.trust_engine.policy import (
    critical_dimensions,
    evaluate_policy,
)


NOW = datetime(2026, 8, 20, 12, 0, tzinfo=timezone.utc)


def known_dimensions(score=95.0, confidence=95.0):
    return {
        dimension: DimensionScore(
            dimension=dimension,
            state=DimensionState.KNOWN,
            score=score,
            confidence=confidence,
            reason_codes=(),
            evidence_refs=(),
        )
        for dimension in TrustDimension
    }


def make_signal(signal_type, level):
    return TrustSignal(
        signal_id=f"sig-{signal_type.lower()}",
        canonical_job_id="job-1",
        signal_type=signal_type,
        level=level,
        status=SignalStatus.ACTIVE,
        confidence=1.0,
        detection_method=DetectionMethod.RULE,
        context_stage=RecruitmentStage.APPLICATION,
        evidence_refs=("observation:1",),
        extractor_version="rules-v1",
        fingerprint=f"fp-{signal_type.lower()}",
        first_seen_at=NOW,
        last_seen_at=NOW,
    )


def evaluate(
    *,
    overall=95.0,
    confidence=95.0,
    dimensions=None,
    signals=(),
    stage=RecruitmentStage.APPLICATION,
    previous=None,
):
    return evaluate_policy(
        canonical_job_id="job-1",
        recruitment_stage=stage,
        overall_score=overall,
        confidence=confidence,
        dimensions=(
            known_dimensions()
            if dimensions is None
            else dimensions
        ),
        signals=signals,
        evaluated_at=NOW,
        input_fingerprint="input-1",
        previous_classification=previous,
    )


def test_l4_beats_perfect_score():
    decision = evaluate(
        overall=100,
        confidence=100,
        dimensions=known_dimensions(100, 100),
        signals=(
            make_signal("OTP_REQUEST", SignalLevel.L4),
        ),
    )

    assert (
        decision.classification
        is TrustClassification.ABSOLUTE_BLOCK
    )
    assert decision.hard_gates[0].gate_code == "OTP_REQUEST"


def test_l3_beats_perfect_score():
    decision = evaluate(
        overall=100,
        confidence=100,
        dimensions=known_dimensions(100, 100),
        signals=(
            make_signal(
                "RECRUITMENT_PAYMENT",
                SignalLevel.L3,
            ),
        ),
    )

    assert (
        decision.classification
        is TrustClassification.AUTOMATION_BLOCKED
    )


def test_l2_requires_review_even_with_perfect_score():
    decision = evaluate(
        overall=100,
        confidence=100,
        dimensions=known_dimensions(100, 100),
        signals=(
            make_signal(
                "RECRUITER_DOMAIN_MISMATCH",
                SignalLevel.L2,
            ),
        ),
    )

    assert (
        decision.classification
        is TrustClassification.REVIEW_REQUIRED
    )


def test_low_confidence_cannot_be_autopilot():
    decision = evaluate(
        overall=96,
        confidence=45,
        dimensions=known_dimensions(96, 96),
    )

    assert (
        decision.classification
        is TrustClassification.REVIEW_REQUIRED
    )

    assert "AUTOPILOT_SUBMIT" in decision.blocked_actions


def test_autopilot_requires_critical_dimension_floor():
    dimensions = known_dimensions(95, 95)

    dimensions[
        TrustDimension.PRIVACY_SAFETY
    ] = DimensionScore(
        dimension=TrustDimension.PRIVACY_SAFETY,
        state=DimensionState.KNOWN,
        score=65,
        confidence=95,
        reason_codes=("PRIVACY_UNCERTAIN",),
        evidence_refs=(),
    )

    decision = evaluate(
        overall=90,
        confidence=95,
        dimensions=dimensions,
    )

    assert (
        decision.classification
        is TrustClassification.ASSISTED_ALLOWED
    )


def test_critical_dimension_below_40_blocks_automation():
    dimensions = known_dimensions(90, 90)

    dimensions[
        TrustDimension.COMPANY_IDENTITY
    ] = DimensionScore(
        dimension=TrustDimension.COMPANY_IDENTITY,
        state=DimensionState.KNOWN,
        score=35,
        confidence=90,
        reason_codes=("IDENTITY_WEAK",),
        evidence_refs=(),
    )

    decision = evaluate(
        overall=80,
        confidence=90,
        dimensions=dimensions,
    )

    assert (
        decision.classification
        is TrustClassification.AUTOMATION_BLOCKED
    )


def test_unknown_critical_dimension_prevents_autopilot():
    dimensions = known_dimensions(95, 95)

    dimensions[
        TrustDimension.PRIVACY_SAFETY
    ] = DimensionScore(
        dimension=TrustDimension.PRIVACY_SAFETY,
        state=DimensionState.UNKNOWN,
        score=None,
        confidence=None,
        reason_codes=("MISSING_PRIVACY_CONTEXT",),
        evidence_refs=(),
    )

    decision = evaluate(
        overall=95,
        confidence=95,
        dimensions=dimensions,
    )

    assert (
        decision.classification
        is TrustClassification.REVIEW_REQUIRED
    )

    assert (
        TrustDimension.PRIVACY_SAFETY
        in decision.unknown_dimensions
    )


def test_recruiter_not_applicable_at_discovery_does_not_block():
    dimensions = known_dimensions(95, 95)

    dimensions[
        TrustDimension.RECRUITER_INTEGRITY
    ] = DimensionScore(
        dimension=TrustDimension.RECRUITER_INTEGRITY,
        state=DimensionState.NOT_APPLICABLE,
        score=None,
        confidence=None,
        reason_codes=("NO_RECRUITER_AT_DISCOVERY",),
        evidence_refs=(),
    )

    decision = evaluate(
        overall=95,
        confidence=95,
        dimensions=dimensions,
        stage=RecruitmentStage.DISCOVERY,
    )

    assert (
        decision.classification
        is TrustClassification.AUTOPILOT_ELIGIBLE
    )


def test_screening_requires_recruiter_integrity():
    assert (
        TrustDimension.RECRUITER_INTEGRITY
        in critical_dimensions(
            RecruitmentStage.SCREENING
        )
    )

    assert (
        TrustDimension.RECRUITER_INTEGRITY
        not in critical_dimensions(
            RecruitmentStage.DISCOVERY
        )
    )


def test_previous_autopilot_uses_hysteresis_at_83():
    decision = evaluate(
        overall=83,
        confidence=90,
        dimensions=known_dimensions(90, 90),
        previous=TrustClassification.AUTOPILOT_ELIGIBLE,
    )

    assert (
        decision.classification
        is TrustClassification.AUTOPILOT_ELIGIBLE
    )

    assert "HYSTERESIS_RETAINED" in decision.primary_reasons


def test_hysteresis_drops_below_82():
    decision = evaluate(
        overall=81.9,
        confidence=90,
        dimensions=known_dimensions(90, 90),
        previous=TrustClassification.AUTOPILOT_ELIGIBLE,
    )

    assert (
        decision.classification
        is TrustClassification.ASSISTED_ALLOWED
    )


def test_l3_bypasses_hysteresis_immediately():
    decision = evaluate(
        overall=99,
        confidence=99,
        dimensions=known_dimensions(99, 99),
        previous=TrustClassification.AUTOPILOT_ELIGIBLE,
        signals=(
            make_signal(
                "RECRUITMENT_PAYMENT",
                SignalLevel.L3,
            ),
        ),
    )

    assert (
        decision.classification
        is TrustClassification.AUTOMATION_BLOCKED
    )


def test_resolved_l4_signal_does_not_keep_blocking():
    original = make_signal(
        "OTP_REQUEST",
        SignalLevel.L4,
    )

    resolved = TrustSignal(
        signal_id=original.signal_id,
        canonical_job_id=original.canonical_job_id,
        signal_type=original.signal_type,
        level=original.level,
        status=SignalStatus.RESOLVED,
        confidence=original.confidence,
        detection_method=original.detection_method,
        context_stage=original.context_stage,
        evidence_refs=original.evidence_refs,
        extractor_version=original.extractor_version,
        fingerprint=original.fingerprint,
        first_seen_at=original.first_seen_at,
        last_seen_at=original.last_seen_at,
        resolved_at=NOW,
        resolution_reason="FALSE_POSITIVE",
    )

    decision = evaluate(
        overall=95,
        confidence=95,
        signals=(resolved,),
    )

    assert (
        decision.classification
        is TrustClassification.AUTOPILOT_ELIGIBLE
    )

    assert decision.hard_gates == ()
