from __future__ import annotations

from dataclasses import dataclass

from onejob.job_sources.models import (
    ComplianceStatus,
    JobSource,
    SourceRolloutState,
)


@dataclass(frozen=True)
class SourcePolicyDecision:
    collection_allowed: bool
    publication_evidence_allowed: bool
    reason_codes: tuple[str, ...]


# Rollout states whose sources may contribute authority to a public
# publication decision. Only ACTIVE qualifies (spec 7.4).
_PUBLICATION_ROLLOUT_STATES = {SourceRolloutState.ACTIVE}

# Rollout states permitted to collect/observe at all.
_COLLECTION_ROLLOUT_STATES = {
    SourceRolloutState.SHADOW,
    SourceRolloutState.OBSERVED,
    SourceRolloutState.VALIDATED,
    SourceRolloutState.ACTIVE,
    SourceRolloutState.DEGRADED,
}


class SourcePolicy:
    """Deterministic acquisition + rollout eligibility.

    Collection eligibility and publication-authority eligibility are separate:
    a Tier 3 discovery source may collect in shadow yet never authorize
    publication on its own.
    """

    def evaluate(self, source: JobSource) -> SourcePolicyDecision:
        reasons: list[str] = []

        if source.compliance_status is ComplianceStatus.POLICY_BLOCKED:
            return SourcePolicyDecision(
                collection_allowed=False,
                publication_evidence_allowed=False,
                reason_codes=("COMPLIANCE_POLICY_BLOCKED",),
            )

        if source.rollout_state is SourceRolloutState.POLICY_BLOCKED:
            return SourcePolicyDecision(
                collection_allowed=False,
                publication_evidence_allowed=False,
                reason_codes=("ROLLOUT_POLICY_BLOCKED",),
            )

        collection_allowed = source.rollout_state in _COLLECTION_ROLLOUT_STATES
        if not collection_allowed:
            reasons.append("ROLLOUT_NOT_COLLECTION_ELIGIBLE")

        publication_allowed = (
            source.rollout_state in _PUBLICATION_ROLLOUT_STATES
            and source.compliance_status is ComplianceStatus.ALLOWED
        )
        if not publication_allowed:
            reasons.append("SOURCE_NOT_PUBLICATION_AUTHORITATIVE")

        return SourcePolicyDecision(
            collection_allowed=collection_allowed,
            publication_evidence_allowed=publication_allowed,
            reason_codes=tuple(reasons),
        )
