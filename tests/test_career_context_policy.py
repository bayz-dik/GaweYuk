from datetime import datetime, timezone

import pytest

from onejob.career_context.models import (
    ConstraintResult,
    PolicyGateStatus,
    ResolvedScope,
    ResolvedTargetViewRecord,
)
from onejob.career_context.policy import (
    evaluate_constraint,
    evaluate_policy_gate,
)
from onejob.models import CanonicalJob


AT = datetime(2026, 8, 21, 12, tzinfo=timezone.utc)


def job(**overrides):
    data = dict(
        id="job-1", title="Operator", company="PT X", location="Bekasi",
        description="desc", normalized_title="operator",
        normalized_company="pt x", normalized_location="bekasi",
        skills=[], salary_min=None, salary_max=None,
    )
    data.update(overrides)
    return CanonicalJob(**data)


def statement(predicate, value, strength, unknown_policy=None, operator="GTE", value_type="MONEY"):
    return {
        "predicate": predicate,
        "operator": operator,
        "value": value,
        "strength": strength,
        "value_type": value_type,
        "unknown_policy": unknown_policy,
        "effect": "INHERIT",
        "source_statement_id": f"is-{predicate}",
    }


def view(statements, scope=ResolvedScope.TARGETED, validation_status="VALID"):
    return ResolvedTargetViewRecord(
        resolved_view_id="rv-1", twin_id="twin-1", intent_version_id="iv-1",
        target_version_id="tv-1", routing_decision_id="route-1", scope=scope,
        resolved_statements=statements, applied_overrides=[],
        explicit_exceptions=[], active_temporal_statements=[], tensions=[],
        validation_status=validation_status, resolver_version="r1",
        evaluated_at=AT, input_fingerprint="fp-1",
    )


# ---------------------------------------------------------------------------
# Three states
# ---------------------------------------------------------------------------


def test_hard_min_salary_satisfied():
    s = statement("COMPENSATION.MIN_SALARY", 6_000_000, "HARD_CONSTRAINT",
                  unknown_policy="REQUIRE_VERIFICATION")
    assessment = evaluate_constraint(s, job(salary_min=7_000_000), resolved_view_id="rv-1")
    assert assessment.result is ConstraintResult.SATISFIED


def test_hard_min_salary_known_violation():
    s = statement("COMPENSATION.MIN_SALARY", 6_000_000, "HARD_CONSTRAINT",
                  unknown_policy="REQUIRE_VERIFICATION")
    assessment = evaluate_constraint(s, job(salary_min=5_000_000), resolved_view_id="rv-1")
    assert assessment.result is ConstraintResult.VIOLATED


def test_hard_min_salary_missing_job_salary_is_unknown():
    s = statement("COMPENSATION.MIN_SALARY", 6_000_000, "HARD_CONSTRAINT",
                  unknown_policy="REQUIRE_VERIFICATION")
    assessment = evaluate_constraint(s, job(salary_min=None), resolved_view_id="rv-1")
    assert assessment.result is ConstraintResult.UNKNOWN
    assert assessment.unknown_reason


# ---------------------------------------------------------------------------
# Unknown policy → gate
# ---------------------------------------------------------------------------


def test_unknown_require_verification_gate_review():
    s = statement("COMPENSATION.MIN_SALARY", 6_000_000, "HARD_CONSTRAINT",
                  unknown_policy="REQUIRE_VERIFICATION")
    gate = evaluate_policy_gate(view([s]), job(salary_min=None))
    assert gate.status is PolicyGateStatus.REVIEW_REQUIRED


def test_unknown_allow_with_warning_stays_eligible():
    s = statement("COMPENSATION.MIN_SALARY", 6_000_000, "HARD_CONSTRAINT",
                  unknown_policy="ALLOW_WITH_WARNING")
    gate = evaluate_policy_gate(view([s]), job(salary_min=None))
    assert gate.status is PolicyGateStatus.ELIGIBLE
    assert gate.reasons


def test_unknown_block_if_unverified_blocks_with_reason_but_result_unknown():
    s = statement("COMPENSATION.MIN_SALARY", 6_000_000, "HARD_CONSTRAINT",
                  unknown_policy="BLOCK_IF_UNVERIFIED")
    v = view([s])
    gate = evaluate_policy_gate(v, job(salary_min=None))
    assert gate.status is PolicyGateStatus.BLOCKED
    assert any("HARD_UNVERIFIED" in r for r in gate.reasons)
    # underlying assessment remains UNKNOWN
    assessment = evaluate_constraint(s, job(salary_min=None), resolved_view_id="rv-1")
    assert assessment.result is ConstraintResult.UNKNOWN


# ---------------------------------------------------------------------------
# Precedence
# ---------------------------------------------------------------------------


def test_hard_violation_blocks():
    s = statement("COMPENSATION.MIN_SALARY", 6_000_000, "HARD_CONSTRAINT")
    gate = evaluate_policy_gate(view([s]), job(salary_min=5_000_000))
    assert gate.status is PolicyGateStatus.BLOCKED
    assert gate.hard_violations


def test_strong_violation_alone_does_not_block():
    s = statement("COMPENSATION.MIN_SALARY", 6_000_000, "STRONG_PREFERENCE")
    gate = evaluate_policy_gate(view([s]), job(salary_min=5_000_000))
    assert gate.status is PolicyGateStatus.ELIGIBLE
    assert gate.strong_tradeoffs


def test_soft_violation_alone_does_not_block():
    s = statement("COMPENSATION.MIN_SALARY", 6_000_000, "SOFT_PREFERENCE")
    gate = evaluate_policy_gate(view([s]), job(salary_min=5_000_000))
    assert gate.status is PolicyGateStatus.ELIGIBLE
    assert gate.soft_signals


def test_invalid_context_returns_invalid_context_status():
    s = statement("COMPENSATION.MIN_SALARY", 6_000_000, "HARD_CONSTRAINT")
    gate = evaluate_policy_gate(
        view([s], validation_status="UNSATISFIABLE"), job(salary_min=7_000_000)
    )
    assert gate.status is PolicyGateStatus.INVALID_CONTEXT


def test_hard_block_takes_precedence_over_strong_and_soft():
    statements = [
        statement("COMPENSATION.MIN_SALARY", 6_000_000, "HARD_CONSTRAINT"),
        statement("COMPENSATION.MAX_SALARY", 4_000_000, "STRONG_PREFERENCE",
                  operator="LTE"),
    ]
    gate = evaluate_policy_gate(view(statements), job(salary_min=5_000_000, salary_max=9_000_000))
    # HARD min violated → BLOCKED regardless of strong signal
    assert gate.status is PolicyGateStatus.BLOCKED
