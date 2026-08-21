from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from onejob.job_verification.models import ApplyDestinationStatus


class PublicationState(str, Enum):
    NOT_EVALUATED = "NOT_EVALUATED"
    VERIFYING = "VERIFYING"
    PUBLISHABLE = "PUBLISHABLE"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"
    QUARANTINED = "QUARANTINED"
    REJECTED = "REJECTED"
    WITHDRAWN = "WITHDRAWN"


@dataclass(frozen=True)
class PublicationDecisionDraft:
    state: PublicationState
    reason_codes: tuple[str, ...] = field(default_factory=tuple)


_ELIGIBLE_TRUST = {"AUTOPILOT_ELIGIBLE", "ASSISTED_ALLOWED"}
_ELIGIBLE_DESTINATIONS = {
    ApplyDestinationStatus.VERIFIED,
    ApplyDestinationStatus.ALLOWED_EXTERNAL,
}


class PublicationPolicy:
    """Deterministic, fail-closed publication decision matrix.

    Precedence (spec 22): confirmed hard block / ABSOLUTE_BLOCK -> REJECTED;
    AUTOMATION_BLOCKED -> QUARANTINED; source not publication-authoritative ->
    REVIEW_REQUIRED; expired/closed -> WITHDRAWN; critical unknown -> REVIEW;
    REVIEW_REQUIRED trust -> REVIEW; only eligible trust with sufficient
    identity/destination/freshness -> PUBLISHABLE. Similarity is never an input.
    """

    def evaluate(self, snapshot, *, source_policy) -> PublicationDecisionDraft:
        reasons: list[str] = []

        if snapshot.hard_gate_hits:
            return PublicationDecisionDraft(
                state=PublicationState.REJECTED,
                reason_codes=("HARD_GATE_" + snapshot.hard_gate_hits[0],),
            )

        if snapshot.trust_classification == "ABSOLUTE_BLOCK":
            return PublicationDecisionDraft(
                state=PublicationState.REJECTED,
                reason_codes=("TRUST_ABSOLUTE_BLOCK",),
            )

        if snapshot.trust_classification == "AUTOMATION_BLOCKED":
            return PublicationDecisionDraft(
                state=PublicationState.QUARANTINED,
                reason_codes=("TRUST_AUTOMATION_BLOCKED",),
            )

        # Closure/expiry withdraw active visibility regardless of trust.
        if snapshot.freshness_state in ("EXPIRED", "CLOSED"):
            return PublicationDecisionDraft(
                state=PublicationState.WITHDRAWN,
                reason_codes=(f"FRESHNESS_{snapshot.freshness_state}",),
            )

        # A source that cannot contribute publication authority can never yield
        # a public PUBLISHABLE decision, even at high trust.
        if not source_policy.publication_evidence_allowed:
            return PublicationDecisionDraft(
                state=PublicationState.REVIEW_REQUIRED,
                reason_codes=("SOURCE_NOT_PUBLICATION_AUTHORITATIVE",),
            )

        if snapshot.unknowns:
            return PublicationDecisionDraft(
                state=PublicationState.REVIEW_REQUIRED,
                reason_codes=tuple(f"UNKNOWN_{u}" for u in snapshot.unknowns),
            )

        if snapshot.trust_classification == "REVIEW_REQUIRED":
            return PublicationDecisionDraft(
                state=PublicationState.REVIEW_REQUIRED,
                reason_codes=("TRUST_REVIEW_REQUIRED",),
            )

        if snapshot.trust_classification not in _ELIGIBLE_TRUST:
            return PublicationDecisionDraft(
                state=PublicationState.REVIEW_REQUIRED,
                reason_codes=("TRUST_NOT_ELIGIBLE",),
            )

        if snapshot.identity_state not in ("VERIFIED", "PROBABLE"):
            return PublicationDecisionDraft(
                state=PublicationState.REVIEW_REQUIRED,
                reason_codes=("IDENTITY_INSUFFICIENT",),
            )

        if snapshot.destination_status not in _ELIGIBLE_DESTINATIONS:
            return PublicationDecisionDraft(
                state=PublicationState.REVIEW_REQUIRED,
                reason_codes=("DESTINATION_NOT_ALLOWED",),
            )

        if snapshot.freshness_state not in ("CURRENT", "DUE_SOON"):
            return PublicationDecisionDraft(
                state=PublicationState.REVIEW_REQUIRED,
                reason_codes=("FRESHNESS_INSUFFICIENT",),
            )

        return PublicationDecisionDraft(
            state=PublicationState.PUBLISHABLE,
            reason_codes=("ALL_PUBLICATION_CONDITIONS_MET",),
        )
