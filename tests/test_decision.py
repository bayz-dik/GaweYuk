from onejob.decision import decide
from onejob.matching import MatchResult, PolicyResult
from onejob.trust import TrustResult


def test_decision_apply_for_high_quality_job():
    result = decide(MatchResult(score=91, positive_evidence=[], negative_evidence=[]), TrustResult(score=92, positive_reasons=[], risk_reasons=[], hard_block=False), PolicyResult(allowed=True, reasons=[]))
    assert result.status == 'APPLY'


def test_decision_block_for_hard_trust_risk():
    result = decide(MatchResult(score=99, positive_evidence=[], negative_evidence=[]), TrustResult(score=20, positive_reasons=[], risk_reasons=['payment request'], hard_block=True), PolicyResult(allowed=True, reasons=[]))
    assert result.status == 'BLOCK'


def test_decision_skip_for_policy_violation():
    result = decide(MatchResult(score=99, positive_evidence=[], negative_evidence=[]), TrustResult(score=95, positive_reasons=[], risk_reasons=[], hard_block=False), PolicyResult(allowed=False, reasons=['salary']))
    assert result.status == 'SKIP'


# --------------------------------------------------
# Trust Engine V2 decision integration
# --------------------------------------------------

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from onejob.trust_engine.models import (
    RecruitmentStage,
    TrustClassification,
    TrustDecision,
)


TRUST_V2_NOW = datetime.now(timezone.utc)


def _v2_trust(
    classification,
    *,
    reasons=("TRUST_V2_TEST",),
):
    return TrustDecision(
        evaluation_id=(
            "eval-decision-v2-"
            + classification.value
        ),
        canonical_job_id="job-v2",
        recruitment_stage=(
            RecruitmentStage.APPLICATION
        ),
        overall_score=95.0,
        confidence=95.0,
        dimensions={},
        classification=classification,
        hard_gates=(),
        risk_signal_ids=(),
        unknown_dimensions=(),
        not_applicable_dimensions=(),
        allowed_actions=(),
        blocked_actions=(),
        override_policy="NONE",
        primary_reasons=tuple(reasons),
        evidence_refs=(),
        evaluated_at=TRUST_V2_NOW,
        valid_until=(
            TRUST_V2_NOW
            + timedelta(hours=1)
        ),
        input_fingerprint=(
            "decision-"
            + classification.value
        ),
        policy_version="trust-v1",
    )


def test_decision_v2_hard_block_beats_perfect_match():
    result = decide(
        SimpleNamespace(score=100),
        _v2_trust(
            TrustClassification.ABSOLUTE_BLOCK,
            reasons=("OTP_REQUEST",),
        ),
        SimpleNamespace(violations=[]),
    )

    assert result.status == "BLOCK"
    assert "OTP_REQUEST" in result.reasons


def test_decision_v2_automation_block_beats_policy_skip():
    result = decide(
        SimpleNamespace(score=100),
        _v2_trust(
            TrustClassification.AUTOMATION_BLOCKED,
            reasons=("RECRUITMENT_PAYMENT",),
        ),
        SimpleNamespace(
            violations=["LOCATION_POLICY"]
        ),
    )

    assert result.status == "BLOCK"
    assert (
        "RECRUITMENT_PAYMENT"
        in result.reasons
    )


def test_decision_v2_review_required_never_auto_applies():
    result = decide(
        SimpleNamespace(score=100),
        _v2_trust(
            TrustClassification.REVIEW_REQUIRED,
        ),
        SimpleNamespace(violations=[]),
    )

    assert result.status == "REVIEW"


def test_decision_v2_policy_violation_still_skips_safe_job():
    result = decide(
        SimpleNamespace(score=100),
        _v2_trust(
            TrustClassification.AUTOPILOT_ELIGIBLE,
        ),
        SimpleNamespace(
            violations=["SALARY_POLICY"]
        ),
    )

    assert result.status == "SKIP"


def test_decision_v2_autopilot_eligible_high_match_applies():
    result = decide(
        SimpleNamespace(score=95),
        _v2_trust(
            TrustClassification.AUTOPILOT_ELIGIBLE,
        ),
        SimpleNamespace(violations=[]),
    )

    assert result.status == "APPLY"


def test_decision_v2_assisted_allowed_high_match_applies_assisted():
    result = decide(
        SimpleNamespace(score=95),
        _v2_trust(
            TrustClassification.ASSISTED_ALLOWED,
        ),
        SimpleNamespace(violations=[]),
    )

    assert result.status == "APPLY"

    assert any(
        "assisted" in reason.lower()
        for reason in result.reasons
    )
