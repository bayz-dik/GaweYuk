from datetime import datetime, timezone

import pytest

from onejob.career_context.matching_adapter import (
    ContextualMatchResult,
    build_evaluation_context,
    match_with_context,
)
from onejob.career_context.models import (
    PolicyGateResult,
    PolicyGateStatus,
    ResolvedScope,
    ResolvedTargetViewRecord,
)
from onejob.models import CanonicalJob
from onejob.profile import CareerTwin
from onejob.service import OneJobService
from onejob.repository import DemoRepository


AT = datetime(2026, 8, 21, 12, tzinfo=timezone.utc)


def job(**overrides):
    data = dict(
        id="job-1", title="Warehouse Operator", company="PT X", location="Bekasi",
        description="forklift warehouse", normalized_title="warehouse operator",
        normalized_company="pt x", normalized_location="bekasi",
        skills=["forklift"], salary_min=4_000_000, salary_max=5_000_000,
    )
    data.update(overrides)
    return CanonicalJob(**data)


def resolved_view(statements, validation_status="VALID", scope=ResolvedScope.TARGETED):
    return ResolvedTargetViewRecord(
        resolved_view_id="rv-1", twin_id="twin-1", intent_version_id="iv-1",
        target_version_id="tv-1", routing_decision_id="route-1", scope=scope,
        resolved_statements=statements, applied_overrides=[], explicit_exceptions=[],
        active_temporal_statements=[], tensions=[], validation_status=validation_status,
        resolver_version="r1", evaluated_at=AT, input_fingerprint="fp-1",
    )


def hard_min_salary_statement(value=6_000_000):
    return {
        "predicate": "COMPENSATION.MIN_SALARY", "operator": "GTE", "value": value,
        "strength": "HARD_CONSTRAINT", "value_type": "MONEY",
        "unknown_policy": "REQUIRE_VERIFICATION", "effect": "INHERIT",
        "source_statement_id": "is-1",
    }


def test_hard_block_outranks_high_similarity():
    # Job would score highly under legacy match, but violates HARD min salary.
    view = resolved_view([hard_min_salary_statement(6_000_000)])
    context = build_evaluation_context(
        twin_projection={"name": "Bayu"},
        view=view,
        assessments=[],
        policy_gate=PolicyGateResult(
            status=PolicyGateStatus.BLOCKED,
            hard_violations=["HARD_VIOLATION:COMPENSATION.MIN_SALARY"],
        ),
    )
    legacy_profile = CareerTwin(name="Bayu", skills=["forklift"], preferred_roles=["warehouse operator"], preferred_locations=["bekasi"])
    result = match_with_context(job(salary_max=5_000_000), legacy_profile, context)

    assert isinstance(result, ContextualMatchResult)
    assert result.policy_gate.status is PolicyGateStatus.BLOCKED
    assert result.decision != "APPLY"


def test_context_version_is_stamped():
    view = resolved_view([hard_min_salary_statement()])
    context = build_evaluation_context(
        twin_projection={}, view=view, assessments=[],
        policy_gate=PolicyGateResult(status=PolicyGateStatus.ELIGIBLE),
    )
    assert context.context_version == "career-context-v1"


def test_no_intent_service_preserves_legacy_evaluation():
    service = OneJobService(DemoRepository())
    jobs = service.list_jobs()
    assert jobs
    for j in jobs:
        assert "match_score" in j
        assert "decision" in j
        assert "contextual" not in j  # legacy path adds no contextual block


def test_contextual_failure_does_not_fall_back_to_legacy():
    from onejob.career_context.service import ContextResolutionFailed

    class FailingContext:
        def resolve(self, **kwargs):
            raise ContextResolutionFailed("resolver crashed")

    repo = DemoRepository()
    service = OneJobService(
        repo,
        career_context_service=FailingContext(),
        has_active_intent=lambda twin_id: True,
    )
    real_job_id = service.jobs[0].id
    # With active intent + failing resolver, evaluation must surface a
    # contextual failure rather than silently returning a legacy success.
    with pytest.raises(ContextResolutionFailed):
        service.evaluate_job_contextual(real_job_id, twin_id="twin-1", evaluated_at=AT)


def test_eligible_context_allows_match_result():
    view = resolved_view([hard_min_salary_statement(4_000_000)])
    context = build_evaluation_context(
        twin_projection={}, view=view, assessments=[],
        policy_gate=PolicyGateResult(status=PolicyGateStatus.ELIGIBLE),
    )
    legacy_profile = CareerTwin(name="Bayu", skills=["forklift"], preferred_roles=["warehouse operator"], preferred_locations=["bekasi"])
    result = match_with_context(job(salary_min=5_000_000), legacy_profile, context)
    assert result.policy_gate.status is PolicyGateStatus.ELIGIBLE
    assert result.match_score is not None
