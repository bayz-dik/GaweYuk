from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import hashlib
from typing import Mapping, Sequence

from .models import (
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


@dataclass(frozen=True)
class TrustPolicy:
    version: str = "trust-v1"

    autopilot_enter_score: float = 85.0
    autopilot_exit_score: float = 82.0
    autopilot_confidence: float = 80.0
    autopilot_critical_floor: float = 70.0

    assisted_score: float = 70.0
    assisted_confidence: float = 60.0
    assisted_critical_floor: float = 55.0

    automation_block_score: float = 60.0
    automation_block_critical_floor: float = 40.0


DEFAULT_POLICY = TrustPolicy()


def critical_dimensions(
    stage: RecruitmentStage,
) -> set[TrustDimension]:

    if stage in {
        RecruitmentStage.DISCOVERY,
        RecruitmentStage.APPLICATION,
    }:
        return {
            TrustDimension.COMPANY_IDENTITY,
            TrustDimension.SOURCE_CREDIBILITY,
            TrustDimension.LISTING_INTEGRITY,
            TrustDimension.PRIVACY_SAFETY,
        }

    if stage in {
        RecruitmentStage.SCREENING,
        RecruitmentStage.INTERVIEW,
    }:
        return {
            TrustDimension.COMPANY_IDENTITY,
            TrustDimension.SOURCE_CREDIBILITY,
            TrustDimension.LISTING_INTEGRITY,
            TrustDimension.RECRUITER_INTEGRITY,
            TrustDimension.PRIVACY_SAFETY,
        }

    if stage in {
        RecruitmentStage.OFFER,
        RecruitmentStage.ONBOARDING,
    }:
        return {
            TrustDimension.COMPANY_IDENTITY,
            TrustDimension.RECRUITER_INTEGRITY,
            TrustDimension.PRIVACY_SAFETY,
        }

    # UNKNOWN is deliberately conservative.
    return {
        TrustDimension.COMPANY_IDENTITY,
        TrustDimension.SOURCE_CREDIBILITY,
        TrustDimension.LISTING_INTEGRITY,
        TrustDimension.RECRUITER_INTEGRITY,
        TrustDimension.PRIVACY_SAFETY,
    }


def _gate_effect(
    level: SignalLevel,
) -> TrustClassification:

    if level is SignalLevel.L4:
        return TrustClassification.ABSOLUTE_BLOCK

    if level is SignalLevel.L3:
        return TrustClassification.AUTOMATION_BLOCKED

    return TrustClassification.REVIEW_REQUIRED


def _override_policy(
    level: SignalLevel,
) -> str:

    if level is SignalLevel.L4:
        return "NONE"

    if level is SignalLevel.L3:
        return "MANUAL_ONLY"

    if level is SignalLevel.L2:
        return "REVIEW_ACKNOWLEDGEMENT"

    return "NONE"



def _active_gates(
    signals: Sequence[TrustSignal],
) -> tuple[GateHit, ...]:

    result = []

    for signal in signals:
        if signal.status is not SignalStatus.ACTIVE:
            continue

        if signal.level is SignalLevel.L1:
            continue

        if (
            signal.detection_method is DetectionMethod.AI
            and signal.level in {SignalLevel.L3, SignalLevel.L4}
        ):
            effect = TrustClassification.REVIEW_REQUIRED
            override_policy = "REQUIRES_CORROBORATION"
        else:
            effect = _gate_effect(signal.level)
            override_policy = _override_policy(signal.level)

        result.append(
            GateHit(
                signal_id=signal.signal_id,
                gate_code=signal.signal_type,
                level=signal.level,
                effect=effect,
                override_policy=override_policy,
            )
        )

    return tuple(
        sorted(
            result,
            key=lambda gate: (
                -int(gate.level.value[1:]),
                gate.gate_code,
                gate.signal_id,
            ),
        )
    )


def _dimension_state_sets(
    dimensions: Mapping[
        TrustDimension,
        DimensionScore,
    ],
) -> tuple[
    tuple[TrustDimension, ...],
    tuple[TrustDimension, ...],
]:

    unknown = {
        dimension
        for dimension, score in dimensions.items()
        if score.state is DimensionState.UNKNOWN
    }

    not_applicable = {
        dimension
        for dimension, score in dimensions.items()
        if score.state is DimensionState.NOT_APPLICABLE
    }

    return (
        tuple(sorted(unknown, key=lambda x: x.value)),
        tuple(
            sorted(
                not_applicable,
                key=lambda x: x.value,
            )
        ),
    )


def _critical_state(
    dimensions: Mapping[
        TrustDimension,
        DimensionScore,
    ],
    stage: RecruitmentStage,
) -> tuple[bool, float | None]:

    unknown = False
    scores = []

    for dimension in critical_dimensions(stage):

        value = dimensions.get(dimension)

        if value is None:
            unknown = True
            continue

        if value.state is DimensionState.UNKNOWN:
            unknown = True
            continue

        if value.state is DimensionState.NOT_APPLICABLE:
            unknown = True
            continue

        if value.score is not None:
            scores.append(value.score)

    return (
        unknown,
        min(scores) if scores else None,
    )


def _classify_scores(
    *,
    overall_score: float,
    confidence: float,
    dimensions: Mapping[
        TrustDimension,
        DimensionScore,
    ],
    stage: RecruitmentStage,
    previous_classification: TrustClassification | None,
    policy: TrustPolicy,
) -> tuple[
    TrustClassification,
    tuple[str, ...],
]:

    critical_unknown, minimum = _critical_state(
        dimensions,
        stage,
    )

    if overall_score < policy.automation_block_score:
        return (
            TrustClassification.AUTOMATION_BLOCKED,
            ("LOW_OVERALL_TRUST",),
        )

    if (
        minimum is not None
        and minimum
        < policy.automation_block_critical_floor
    ):
        return (
            TrustClassification.AUTOMATION_BLOCKED,
            ("CRITICAL_DIMENSION_BELOW_40",),
        )

    if critical_unknown:
        return (
            TrustClassification.REVIEW_REQUIRED,
            ("INSUFFICIENT_CRITICAL_EVIDENCE",),
        )

    if minimum is None:
        return (
            TrustClassification.REVIEW_REQUIRED,
            ("INSUFFICIENT_CRITICAL_EVIDENCE",),
        )

    # Hysteresis affects only soft numeric boundaries.
    if (
        previous_classification
        is TrustClassification.AUTOPILOT_ELIGIBLE
        and overall_score
        >= policy.autopilot_exit_score
        and confidence
        >= policy.autopilot_confidence
        and minimum
        >= policy.autopilot_critical_floor
    ):
        return (
            TrustClassification.AUTOPILOT_ELIGIBLE,
            ("HYSTERESIS_RETAINED",),
        )

    if (
        overall_score
        >= policy.autopilot_enter_score
        and confidence
        >= policy.autopilot_confidence
        and minimum
        >= policy.autopilot_critical_floor
    ):
        return (
            TrustClassification.AUTOPILOT_ELIGIBLE,
            ("AUTOPILOT_THRESHOLDS_MET",),
        )

    if (
        overall_score >= policy.assisted_score
        and confidence >= policy.assisted_confidence
        and minimum >= policy.assisted_critical_floor
    ):
        return (
            TrustClassification.ASSISTED_ALLOWED,
            ("ASSISTED_THRESHOLDS_MET",),
        )

    reasons = []

    if confidence < policy.assisted_confidence:
        reasons.append("LOW_CONFIDENCE")

    if minimum < policy.assisted_critical_floor:
        reasons.append(
            "CRITICAL_DIMENSION_NEEDS_REVIEW"
        )

    if not reasons:
        reasons.append("TRUST_REVIEW_REQUIRED")

    return (
        TrustClassification.REVIEW_REQUIRED,
        tuple(reasons),
    )


def _actions_for(
    classification: TrustClassification,
) -> tuple[
    tuple[str, ...],
    tuple[str, ...],
    str,
]:

    if (
        classification
        is TrustClassification.AUTOPILOT_ELIGIBLE
    ):
        return (
            (
                "MANUAL_REVIEW",
                "ASSISTED_SUBMIT",
                "AUTOPILOT_SUBMIT",
            ),
            (),
            "NONE",
        )

    if (
        classification
        is TrustClassification.ASSISTED_ALLOWED
    ):
        return (
            (
                "MANUAL_REVIEW",
                "ASSISTED_SUBMIT",
            ),
            ("AUTOPILOT_SUBMIT",),
            "NONE",
        )

    if (
        classification
        is TrustClassification.REVIEW_REQUIRED
    ):
        return (
            ("MANUAL_REVIEW",),
            (
                "ASSISTED_SUBMIT",
                "AUTOPILOT_SUBMIT",
            ),
            "REVIEW_ACKNOWLEDGEMENT",
        )

    if (
        classification
        is TrustClassification.AUTOMATION_BLOCKED
    ):
        return (
            ("MANUAL_INVESTIGATION",),
            (
                "ASSISTED_SUBMIT",
                "AUTOPILOT_SUBMIT",
            ),
            "MANUAL_ONLY",
        )

    return (
        ("MANUAL_INVESTIGATION",),
        (
            "ASSISTED_SUBMIT",
            "AUTOPILOT_SUBMIT",
            "SECRET_TRANSMISSION",
        ),
        "NONE",
    )


def _evaluation_id(
    canonical_job_id: str,
    input_fingerprint: str,
    policy_version: str,
) -> str:

    value = (
        f"{canonical_job_id}|"
        f"{input_fingerprint}|"
        f"{policy_version}"
    )

    digest = hashlib.sha256(
        value.encode("utf-8")
    ).hexdigest()

    return f"eval-{digest[:24]}"



def evaluate_policy(
    *,
    canonical_job_id: str,
    recruitment_stage: RecruitmentStage,
    overall_score: float,
    confidence: float,
    dimensions: Mapping[
        TrustDimension,
        DimensionScore,
    ],
    signals: Sequence[TrustSignal],
    evaluated_at: datetime,
    input_fingerprint: str,
    previous_classification: TrustClassification | None = None,
    policy: TrustPolicy = DEFAULT_POLICY,
) -> TrustDecision:

    gates = _active_gates(signals)

    absolute_gates = tuple(
        gate
        for gate in gates
        if gate.effect is TrustClassification.ABSOLUTE_BLOCK
    )

    automation_gates = tuple(
        gate
        for gate in gates
        if gate.effect is TrustClassification.AUTOMATION_BLOCKED
    )

    review_gates = tuple(
        gate
        for gate in gates
        if gate.effect is TrustClassification.REVIEW_REQUIRED
    )

    if absolute_gates:
        classification = TrustClassification.ABSOLUTE_BLOCK
        reasons = tuple(gate.gate_code for gate in absolute_gates)

    elif automation_gates:
        classification = TrustClassification.AUTOMATION_BLOCKED
        reasons = tuple(gate.gate_code for gate in automation_gates)

    elif review_gates:
        classification = TrustClassification.REVIEW_REQUIRED
        reasons = tuple(gate.gate_code for gate in review_gates)

    else:
        classification, reasons = _classify_scores(
            overall_score=overall_score,
            confidence=confidence,
            dimensions=dimensions,
            stage=recruitment_stage,
            previous_classification=previous_classification,
            policy=policy,
        )

    unknown, not_applicable = _dimension_state_sets(dimensions)

    allowed, blocked, override = _actions_for(classification)

    if absolute_gates:
        override = "NONE"
    elif automation_gates:
        override = "MANUAL_ONLY"
    elif review_gates:
        if any(
            gate.override_policy == "REQUIRES_CORROBORATION"
            for gate in review_gates
        ):
            override = "REQUIRES_CORROBORATION"
        else:
            override = "REVIEW_ACKNOWLEDGEMENT"

    evidence_refs = tuple(
        sorted(
            {
                ref
                for signal in signals
                for ref in signal.evidence_refs
            }
            |
            {
                ref
                for score in dimensions.values()
                for ref in score.evidence_refs
            }
        )
    )

    return TrustDecision(
        evaluation_id=_evaluation_id(
            canonical_job_id,
            input_fingerprint,
            policy.version,
        ),
        canonical_job_id=canonical_job_id,
        recruitment_stage=recruitment_stage,
        overall_score=overall_score,
        confidence=confidence,
        dimensions=dict(dimensions),
        classification=classification,
        hard_gates=gates,
        risk_signal_ids=tuple(
            sorted(
                signal.signal_id
                for signal in signals
                if signal.status is SignalStatus.ACTIVE
            )
        ),
        unknown_dimensions=unknown,
        not_applicable_dimensions=not_applicable,
        allowed_actions=allowed,
        blocked_actions=blocked,
        override_policy=override,
        primary_reasons=tuple(reasons),
        evidence_refs=evidence_refs,
        evaluated_at=evaluated_at,
        valid_until=None,
        input_fingerprint=input_fingerprint,
        policy_version=policy.version,
    )
