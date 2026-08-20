from datetime import datetime, timedelta, timezone

from onejob.trust_engine.models import (
    DimensionState,
    RecruitmentStage,
    TrustDecision,
    TrustClassification,
)
from onejob.trust_engine.recalculation import (
    RecalcPriority,
    TrustEventType,
    failure_dimension_input,
    input_fingerprint,
    is_evaluation_fresh,
    priority_for_event,
    should_recalculate,
    source_health_confidence_multiplier,
    source_health_creates_scam_signal,
)


NOW = datetime(2026, 8, 20, 12, 0, tzinfo=timezone.utc)


def test_l4_signal_is_p0_immediate():
    assert (
        priority_for_event(
            TrustEventType.L4_SIGNAL_CHANGED
        )
        is RecalcPriority.P0_IMMEDIATE
    )


def test_l3_signal_is_p0_immediate():
    assert (
        priority_for_event(
            TrustEventType.L3_SIGNAL_CHANGED
        )
        is RecalcPriority.P0_IMMEDIATE
    )


def test_company_identity_change_is_p1():
    assert (
        priority_for_event(
            TrustEventType.COMPANY_IDENTITY_CHANGED
        )
        is RecalcPriority.P1_HIGH
    )


def test_new_observation_is_p2():
    assert (
        priority_for_event(
            TrustEventType.NEW_OBSERVATION
        )
        is RecalcPriority.P2_NORMAL
    )


def test_freshness_decay_is_p3():
    assert (
        priority_for_event(
            TrustEventType.FRESHNESS_DECAY
        )
        is RecalcPriority.P3_BACKGROUND
    )


def test_policy_version_changes_input_fingerprint():
    common = dict(
        canonical_job_id="job-1",
        recruitment_stage=RecruitmentStage.APPLICATION,
        evidence_refs=("evidence:2", "evidence:1"),
        active_signal_ids=("sig-2", "sig-1"),
        source_health={"greenhouse": "HEALTHY"},
    )

    first = input_fingerprint(
        policy_version="trust-v1",
        **common,
    )
    second = input_fingerprint(
        policy_version="trust-v2",
        **common,
    )

    assert first != second


def test_mapping_and_sequence_order_do_not_change_fingerprint():
    first = input_fingerprint(
        canonical_job_id="job-1",
        recruitment_stage=RecruitmentStage.APPLICATION,
        policy_version="trust-v1",
        evidence_refs=("evidence:1", "evidence:2"),
        active_signal_ids=("sig-1", "sig-2"),
        source_health={
            "greenhouse": "HEALTHY",
            "lever": "RATE_LIMITED",
        },
    )

    second = input_fingerprint(
        canonical_job_id="job-1",
        recruitment_stage=RecruitmentStage.APPLICATION,
        policy_version="trust-v1",
        evidence_refs=("evidence:2", "evidence:1"),
        active_signal_ids=("sig-2", "sig-1"),
        source_health={
            "lever": "RATE_LIMITED",
            "greenhouse": "HEALTHY",
        },
    )

    assert first == second


def test_identical_inputs_skip_duplicate_evaluation():
    fingerprint = input_fingerprint(
        canonical_job_id="job-1",
        recruitment_stage=RecruitmentStage.APPLICATION,
        policy_version="trust-v1",
        evidence_refs=("evidence:1",),
        active_signal_ids=(),
        source_health={"greenhouse": "HEALTHY"},
    )

    assert not should_recalculate(
        previous_input_fingerprint=fingerprint,
        new_input_fingerprint=fingerprint,
    )


def test_changed_inputs_trigger_recalculation():
    assert should_recalculate(
        previous_input_fingerprint="old",
        new_input_fingerprint="new",
    )


def test_no_previous_evaluation_triggers_recalculation():
    assert should_recalculate(
        previous_input_fingerprint=None,
        new_input_fingerprint="new",
    )


def test_evaluation_before_valid_until_is_fresh():
    assert is_evaluation_fresh(
        evaluated_at=NOW,
        valid_until=NOW + timedelta(hours=1),
        now=NOW + timedelta(minutes=30),
        evaluation_policy_version="trust-v1",
        current_policy_version="trust-v1",
    )


def test_expired_evaluation_is_not_fresh():
    assert not is_evaluation_fresh(
        evaluated_at=NOW,
        valid_until=NOW + timedelta(minutes=10),
        now=NOW + timedelta(minutes=11),
        evaluation_policy_version="trust-v1",
        current_policy_version="trust-v1",
    )


def test_policy_version_mismatch_is_not_fresh():
    assert not is_evaluation_fresh(
        evaluated_at=NOW,
        valid_until=NOW + timedelta(hours=1),
        now=NOW + timedelta(minutes=5),
        evaluation_policy_version="trust-v1",
        current_policy_version="trust-v2",
    )


def test_missing_valid_until_is_not_fresh_for_authorization():
    assert not is_evaluation_fresh(
        evaluated_at=NOW,
        valid_until=None,
        now=NOW + timedelta(minutes=1),
        evaluation_policy_version="trust-v1",
        current_policy_version="trust-v1",
    )


def test_ai_failure_becomes_unknown_not_zero_score():
    failed = failure_dimension_input(
        reason="AI_EXTRACTOR_TIMEOUT"
    )

    assert failed.state is DimensionState.UNKNOWN
    assert failed.score is None
    assert failed.confidence is None
    assert failed.reason_codes == (
        "AI_EXTRACTOR_TIMEOUT",
    )


def test_source_rate_limit_reduces_reliability_confidence():
    healthy = source_health_confidence_multiplier(
        "HEALTHY"
    )
    limited = source_health_confidence_multiplier(
        "RATE_LIMITED"
    )

    assert healthy == 1.0
    assert 0 < limited < healthy


def test_source_rate_limit_does_not_become_scam_signal():
    assert not source_health_creates_scam_signal(
        "RATE_LIMITED"
    )


def test_broken_source_still_is_not_automatic_scam_signal():
    assert not source_health_creates_scam_signal(
        "BROKEN"
    )
