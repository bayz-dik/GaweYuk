from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from onejob.career_context.models import (
    ConstraintAssessment,
    EvaluationContext,
    PolicyGateResult,
    PolicyGateStatus,
    ResolvedTargetViewRecord,
)
from onejob.matching import MatchResult, match_job
from onejob.models import CanonicalJob
from onejob.profile import CareerTwin


def build_evaluation_context(
    *,
    twin_projection: dict,
    view: ResolvedTargetViewRecord,
    assessments: list[ConstraintAssessment],
    policy_gate: PolicyGateResult,
) -> EvaluationContext:
    """Assemble the stable EvaluationContext contract for matching.

    Exposes only resolved semantics/provenance; no persistence repositories
    are handed to matching.
    """
    strong_signals = list(policy_gate.strong_tradeoffs)
    soft_signals = list(policy_gate.soft_signals)
    return EvaluationContext(
        career_twin_projection=twin_projection,
        resolved_target_view=view,
        constraint_assessments=assessments,
        hard_gate_status=policy_gate.status,
        strong_preference_signals=strong_signals,
        soft_preference_signals=soft_signals,
        provenance={
            "intent_version_id": view.intent_version_id,
            "target_version_id": view.target_version_id,
            "routing_decision_id": view.routing_decision_id,
            "resolver_version": view.resolver_version,
            "resolved_view_id": view.resolved_view_id,
            "hard_violations": policy_gate.hard_violations,
            "hard_unknowns": policy_gate.hard_unknowns,
        },
    )


@dataclass(frozen=True)
class ContextualMatchResult:
    policy_gate: PolicyGateResult
    match_score: int | None
    match_positive_evidence: list[str]
    match_negative_evidence: list[str]
    decision: str
    strong_tradeoffs: list[str]
    soft_signals: list[str]
    provenance: dict[str, Any]


def match_with_context(
    job: CanonicalJob,
    legacy_profile: CareerTwin,
    context: EvaluationContext,
) -> ContextualMatchResult:
    """Adapter that lets the policy gate control decision eligibility.

    Reuses the existing ``match_job`` for similarity, but the hard policy gate
    result — not similarity — determines whether an APPLY decision is possible.
    Similarity can never override a HARD block.
    """
    gate = context.hard_gate_status

    if gate is PolicyGateStatus.INVALID_CONTEXT:
        return ContextualMatchResult(
            policy_gate=_gate_of(context),
            match_score=None,
            match_positive_evidence=[],
            match_negative_evidence=[],
            decision="INVALID_CONTEXT",
            strong_tradeoffs=context.strong_preference_signals,
            soft_signals=context.soft_preference_signals,
            provenance=context.provenance,
        )

    if gate is PolicyGateStatus.BLOCKED:
        # Do not even let similarity produce an APPLY.
        return ContextualMatchResult(
            policy_gate=_gate_of(context),
            match_score=None,
            match_positive_evidence=[],
            match_negative_evidence=[],
            decision="BLOCK",
            strong_tradeoffs=context.strong_preference_signals,
            soft_signals=context.soft_preference_signals,
            provenance=context.provenance,
        )

    match: MatchResult = match_job(job, legacy_profile)

    if gate is PolicyGateStatus.REVIEW_REQUIRED:
        decision = "REVIEW"
    else:  # ELIGIBLE
        decision = "APPLY" if match.score >= 60 else "REVIEW"

    return ContextualMatchResult(
        policy_gate=_gate_of(context),
        match_score=match.score,
        match_positive_evidence=match.positive_evidence,
        match_negative_evidence=match.negative_evidence,
        decision=decision,
        strong_tradeoffs=context.strong_preference_signals,
        soft_signals=context.soft_preference_signals,
        provenance=context.provenance,
    )


def _gate_of(context: EvaluationContext) -> PolicyGateResult:
    # Reconstruct a PolicyGateResult snapshot for the caller from context.
    return PolicyGateResult(
        status=context.hard_gate_status,
        hard_violations=context.provenance.get("hard_violations", []),
        hard_unknowns=context.provenance.get("hard_unknowns", []),
        strong_tradeoffs=context.strong_preference_signals,
        soft_signals=context.soft_preference_signals,
    )
