from datetime import datetime, timezone

import pytest

from onejob.trust_engine.models import (
    ActionDecision,
    ActionMode,
    ConsentGrant,
    DetectionMethod,
    DimensionScore,
    DimensionState,
    GateHit,
    RecruitmentStage,
    SignalLevel,
    SignalStatus,
    TrustClassification,
    TrustDecision,
    TrustDimension,
    TrustSignal,
)


def test_dimension_unknown_cannot_have_score():
    with pytest.raises(
        ValueError,
        match="non-KNOWN dimension cannot have score",
    ):
        DimensionScore(
            dimension=TrustDimension.PRIVACY_SAFETY,
            state=DimensionState.UNKNOWN,
            score=90.0,
            confidence=None,
            reason_codes=("MISSING_CONTEXT",),
            evidence_refs=(),
        )


def test_known_dimension_requires_score_and_confidence():
    with pytest.raises(
        ValueError,
        match="KNOWN dimension requires score and confidence",
    ):
        DimensionScore(
            dimension=TrustDimension.COMPANY_IDENTITY,
            state=DimensionState.KNOWN,
            score=None,
            confidence=None,
            reason_codes=(),
            evidence_refs=(),
        )


def test_not_applicable_dimension_has_no_score_or_confidence():
    score = DimensionScore(
        dimension=TrustDimension.RECRUITER_INTEGRITY,
        state=DimensionState.NOT_APPLICABLE,
        score=None,
        confidence=None,
        reason_codes=("NO_RECRUITER_AT_DISCOVERY",),
        evidence_refs=(),
    )

    assert score.score is None
    assert score.confidence is None


def test_trust_decision_contract_is_versioned():
    decision = TrustDecision(
        evaluation_id="eval-1",
        canonical_job_id="job-1",
        recruitment_stage=RecruitmentStage.APPLICATION,
        overall_score=88.0,
        confidence=82.0,
        dimensions={},
        classification=TrustClassification.AUTOPILOT_ELIGIBLE,
        hard_gates=(),
        risk_signal_ids=(),
        unknown_dimensions=(),
        not_applicable_dimensions=(),
        allowed_actions=("AUTOPILOT_SUBMIT",),
        blocked_actions=(),
        override_policy="NONE",
        primary_reasons=(),
        evidence_refs=(),
        evaluated_at=datetime.now(timezone.utc),
        valid_until=None,
        input_fingerprint="abc",
        policy_version="trust-v1",
    )

    assert decision.policy_version == "trust-v1"


def test_signal_contract_has_no_raw_secret_field():
    now = datetime.now(timezone.utc)

    signal = TrustSignal(
        signal_id="sig-1",
        canonical_job_id="job-1",
        signal_type="OTP_REQUEST",
        level=SignalLevel.L4,
        status=SignalStatus.ACTIVE,
        confidence=1.0,
        detection_method=DetectionMethod.RULE,
        context_stage=RecruitmentStage.SCREENING,
        evidence_refs=("observation:1",),
        extractor_version="rules-v1",
        fingerprint="fp-1",
        first_seen_at=now,
        last_seen_at=now,
    )

    assert not hasattr(signal, "secret")
    assert not hasattr(signal, "raw_secret")
    assert not hasattr(signal, "value")


def test_supporting_contract_enums_are_stable():
    assert ActionMode.AUTOPILOT.value == "AUTOPILOT"
    assert ActionDecision.DENIED.value == "DENIED"
    assert SignalLevel.L4.value == "L4"


def test_consent_contract_is_scoped():
    now = datetime.now(timezone.utc)

    consent = ConsentGrant(
        consent_id="consent-1",
        user_id="user-1",
        canonical_job_id="job-1",
        company_id="company-1",
        scope="KTP_FOR_VERIFIED_ONBOARDING",
        recruitment_stage=RecruitmentStage.ONBOARDING,
        issued_at=now,
        expires_at=now,
        revoked_at=None,
    )

    assert consent.scope == "KTP_FOR_VERIFIED_ONBOARDING"


def test_gate_hit_keeps_signal_reference():
    gate = GateHit(
        signal_id="sig-1",
        gate_code="OTP_REQUEST",
        level=SignalLevel.L4,
        effect=TrustClassification.ABSOLUTE_BLOCK,
        override_policy="NONE",
    )

    assert gate.signal_id == "sig-1"
