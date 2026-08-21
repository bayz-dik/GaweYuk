from __future__ import annotations

from typing import Any

from onejob.career_context.models import (
    ConstraintAssessment,
    ConstraintResult,
    PolicyGateResult,
    PolicyGateStatus,
)
from onejob.career_intent.models import IntentStrength, UnknownPolicy


EVALUATOR_VERSION = "career-policy-evaluator-v1"


# Reason codes.
HARD_VIOLATION = "HARD_VIOLATION"
HARD_UNVERIFIED = "HARD_UNVERIFIED"
HARD_REVIEW_REQUIRED = "HARD_REVIEW_REQUIRED"
STRONG_TRADEOFF = "STRONG_TRADEOFF"
SOFT_MISS = "SOFT_MISS"


def _observed_value(predicate: str, job) -> tuple[Any, bool]:
    """Return (observed_value, present). Never fabricates missing data."""
    if predicate == "COMPENSATION.MIN_SALARY":
        return job.salary_min, job.salary_min is not None
    if predicate == "COMPENSATION.MAX_SALARY":
        # A max-salary preference is compared against the job's offered floor.
        return job.salary_min, job.salary_min is not None
    if predicate == "LOCATION.PREFERRED":
        return getattr(job, "normalized_location", None), bool(
            getattr(job, "normalized_location", None)
        )
    # Predicates without observable job data in v1 → not present.
    return None, False


def _compare(predicate: str, operator: str, expected: Any, observed: Any) -> bool:
    if operator == "GTE":
        return observed >= expected
    if operator == "LTE":
        return observed <= expected
    if operator == "EQ":
        return observed == expected
    if operator == "IN":
        expected_set = expected if isinstance(expected, (list, tuple, set)) else [expected]
        if isinstance(observed, str):
            return any(str(e).lower() in observed.lower() for e in expected_set)
        return observed in expected_set
    return False


def evaluate_constraint(
    statement: dict, job, *, resolved_view_id: str
) -> ConstraintAssessment:
    predicate = statement["predicate"]
    operator = statement["operator"]
    expected = statement["value"]

    observed, present = _observed_value(predicate, job)

    if not present:
        return ConstraintAssessment(
            assessment_id=f"ca-{resolved_view_id}-{statement['source_statement_id']}",
            resolved_view_id=resolved_view_id,
            statement_id=statement["source_statement_id"],
            result=ConstraintResult.UNKNOWN,
            observed_value=None,
            evidence_status="MISSING",
            unknown_reason=f"observed value for {predicate} unavailable",
            required_action="VERIFY" if statement.get("unknown_policy") else None,
            reasons=[f"no observed value for {predicate}"],
            evaluator_version=EVALUATOR_VERSION,
        )

    satisfied = _compare(predicate, operator, expected, observed)
    return ConstraintAssessment(
        assessment_id=f"ca-{resolved_view_id}-{statement['source_statement_id']}",
        resolved_view_id=resolved_view_id,
        statement_id=statement["source_statement_id"],
        result=ConstraintResult.SATISFIED if satisfied else ConstraintResult.VIOLATED,
        observed_value=observed,
        evidence_status="OBSERVED",
        unknown_reason=None,
        reasons=[
            f"{predicate} {operator} {expected!r} vs observed {observed!r}"
        ],
        evaluator_version=EVALUATOR_VERSION,
    )


def evaluate_policy_gate(view, job) -> PolicyGateResult:
    """Aggregate three-valued constraint results into a policy gate.

    Precedence:
      INVALID_CONTEXT
      > known HARD violation
      > HARD unknown + BLOCK_IF_UNVERIFIED
      > HARD unknown + REQUIRE_VERIFICATION
      > STRONG trade-offs
      > SOFT signals
    Similarity is never consumed here, so it can never override the gate.
    """
    if view.validation_status not in ("VALID", "VALID_WITH_TENSIONS"):
        return PolicyGateResult(
            status=PolicyGateStatus.INVALID_CONTEXT,
            reasons=[f"resolved context is {view.validation_status}"],
        )

    hard_violations: list[str] = []
    hard_unknowns: list[str] = []
    strong_tradeoffs: list[str] = []
    soft_signals: list[str] = []
    reasons: list[str] = []

    block_if_unverified = False
    require_verification = False

    for statement in view.resolved_statements:
        assessment = evaluate_constraint(
            statement, job, resolved_view_id=view.resolved_view_id
        )
        strength = statement["strength"]
        predicate = statement["predicate"]

        if strength == IntentStrength.HARD_CONSTRAINT.value:
            if assessment.result is ConstraintResult.VIOLATED:
                hard_violations.append(f"{HARD_VIOLATION}:{predicate}")
            elif assessment.result is ConstraintResult.UNKNOWN:
                policy = statement.get("unknown_policy")
                hard_unknowns.append(f"{predicate}:{policy}")
                if policy == UnknownPolicy.BLOCK_IF_UNVERIFIED.value:
                    block_if_unverified = True
                    reasons.append(f"{HARD_UNVERIFIED}:{predicate}")
                elif policy == UnknownPolicy.REQUIRE_VERIFICATION.value:
                    require_verification = True
                    reasons.append(f"{HARD_REVIEW_REQUIRED}:{predicate}")
                elif policy == UnknownPolicy.ALLOW_WITH_WARNING.value:
                    reasons.append(f"WARNING_UNVERIFIED:{predicate}")
        elif strength == IntentStrength.STRONG_PREFERENCE.value:
            if assessment.result is ConstraintResult.VIOLATED:
                strong_tradeoffs.append(f"{STRONG_TRADEOFF}:{predicate}")
        else:  # SOFT
            if assessment.result is ConstraintResult.VIOLATED:
                soft_signals.append(f"{SOFT_MISS}:{predicate}")

    if hard_violations:
        status = PolicyGateStatus.BLOCKED
    elif block_if_unverified:
        status = PolicyGateStatus.BLOCKED
    elif require_verification:
        status = PolicyGateStatus.REVIEW_REQUIRED
    else:
        status = PolicyGateStatus.ELIGIBLE

    return PolicyGateResult(
        status=status,
        hard_violations=hard_violations,
        hard_unknowns=hard_unknowns,
        strong_tradeoffs=strong_tradeoffs,
        soft_signals=soft_signals,
        reasons=reasons,
    )
