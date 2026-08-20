from pydantic import BaseModel, Field
from onejob.matching import MatchResult, PolicyResult
from onejob.trust import TrustResult
from onejob.trust_engine.models import TrustClassification, TrustDecision

class DecisionResult(BaseModel):
    status: str
    reasons: list[str] = Field(default_factory=list)

def _policy_violations(policy_result) -> list[str]:
    explicit = getattr(policy_result, "violations", None)
    if explicit is not None:
        return list(explicit)
    if getattr(policy_result, "allowed", True):
        return []
    return list(getattr(policy_result, "reasons", ()))


def decide(match, trust, policy_result) -> DecisionResult:
    # Trust Engine V2:
    # security gates always take precedence.
    if isinstance(trust, TrustDecision):
        if trust.classification in {
            TrustClassification.ABSOLUTE_BLOCK,
            TrustClassification.AUTOMATION_BLOCKED,
        }:
            reasons = list(
                trust.primary_reasons
            ) or [
                "Trust Engine blocked this opportunity"
            ]

            return DecisionResult(
                status="BLOCK",
                reasons=reasons,
            )

        if (
            trust.classification
            is TrustClassification.REVIEW_REQUIRED
        ):
            reasons = list(
                trust.primary_reasons
            ) or [
                "Trust Engine requires manual review"
            ]

            return DecisionResult(
                status="REVIEW",
                reasons=reasons,
            )

        # Personal policy is evaluated only after
        # security gates have passed.
        if _policy_violations(policy_result):
            return DecisionResult(
                status="SKIP",
                reasons=list(
                    _policy_violations(policy_result)
                ),
            )

        if match.score >= 80:
            if (
                trust.classification
                is TrustClassification.AUTOPILOT_ELIGIBLE
            ):
                return DecisionResult(
                    status="APPLY",
                    reasons=[
                        "High match and Trust Engine "
                        "autopilot eligibility"
                    ],
                )

            if (
                trust.classification
                is TrustClassification.ASSISTED_ALLOWED
            ):
                return DecisionResult(
                    status="APPLY",
                    reasons=[
                        "High match; assisted application "
                        "allowed by Trust Engine"
                    ],
                )

        return DecisionResult(
            status="REVIEW",
            reasons=[
                "Opportunity needs manual review"
            ],
        )

    # Legacy TrustResult compatibility.
    if trust.hard_block or trust.score < 40:
        return DecisionResult(
            status="BLOCK",
            reasons=[
                "Trust below safety threshold"
            ],
        )

    if _policy_violations(policy_result):
        return DecisionResult(
            status="SKIP",
            reasons=list(
                _policy_violations(policy_result)
            ),
        )

    if (
        trust.score >= 75
        and match.score >= 80
    ):
        return DecisionResult(
            status="APPLY",
            reasons=[
                "High match and trust with no hard "
                "policy violation"
            ],
        )

    return DecisionResult(
        status="REVIEW",
        reasons=[
            "Opportunity needs manual review"
        ],
    )
