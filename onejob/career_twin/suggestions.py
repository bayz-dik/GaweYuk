from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict

from onejob.career_twin.ontology import Predicate


class BatchLifecycle(str, Enum):
    OPEN = "OPEN"
    PROCESSED = "PROCESSED"
    CANCELLED = "CANCELLED"


class SuggestionBatch(BaseModel):
    model_config = ConfigDict(frozen=True)

    batch_id: str
    twin_id: str
    source_type: str
    source_reference: str | None = None
    intake_version: str
    evidence_family_id: str
    lifecycle: BatchLifecycle
    created_at: datetime
    completed_at: datetime | None = None


class DecisionState(str, Enum):
    """User-authority axis. Whether the owner has decided the proposal."""

    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


class Disposition(str, Enum):
    """System-classification axis. How the proposal relates to current truth."""

    READY = "READY"
    CONFLICT = "CONFLICT"
    DUPLICATE = "DUPLICATE"
    STALE = "STALE"
    SUPPRESSED = "SUPPRESSED"


class SuggestionAction(str, Enum):
    APPROVE = "APPROVE"
    REJECT = "REJECT"
    INVALIDATE_CONTEXT = "INVALIDATE_CONTEXT"
    KEEP_CURRENT = "KEEP_CURRENT"
    ACCEPT_ALTERNATIVE = "ACCEPT_ALTERNATIVE"
    EDIT_AND_ACCEPT = "EDIT_AND_ACCEPT"
    DEFER = "DEFER"
    CLASSIFY_DUPLICATE = "CLASSIFY_DUPLICATE"
    REOPEN_MATERIAL_EVIDENCE = "REOPEN_MATERIAL_EVIDENCE"


class InvalidSuggestionTransition(RuntimeError):
    def __init__(
        self,
        *,
        decision: DecisionState,
        disposition: Disposition,
        action: SuggestionAction,
    ):
        self.decision = decision
        self.disposition = disposition
        self.action = action
        super().__init__(
            "invalid suggestion transition: "
            f"{decision.value}+{disposition.value} "
            f"--{action.value}-->"
        )


class SuggestionState(BaseModel):
    model_config = ConfigDict(frozen=True)

    decision: DecisionState
    disposition: Disposition


# Actions that finalize into APPROVED are the *only* path to canonical intent.
_APPROVING_ACTIONS = {
    SuggestionAction.APPROVE,
    SuggestionAction.ACCEPT_ALTERNATIVE,
    SuggestionAction.EDIT_AND_ACCEPT,
}


def transition(
    state: SuggestionState,
    action: SuggestionAction,
    *,
    suppress: bool = False,
    reopen_conflict: bool = False,
) -> SuggestionState:
    """Command-driven transition of the two-axis suggestion state.

    Only allowed (decision, disposition, action) combinations are permitted.
    Any other combination raises ``InvalidSuggestionTransition``. There is no
    generic mutator that would allow arbitrary decision/disposition pairs.
    """

    decision = state.decision
    disposition = state.disposition

    # Only PENDING suggestions can transition. APPROVED/REJECTED are terminal.
    if decision is not DecisionState.PENDING:
        raise InvalidSuggestionTransition(
            decision=decision,
            disposition=disposition,
            action=action,
        )

    # ------------------------------------------------------------------
    # PENDING + READY
    # ------------------------------------------------------------------
    if disposition is Disposition.READY:
        if action is SuggestionAction.APPROVE:
            return SuggestionState(
                decision=DecisionState.APPROVED,
                disposition=Disposition.READY,
            )
        if action is SuggestionAction.EDIT_AND_ACCEPT:
            # Approving a ready proposal with a user edit is still an approval.
            return SuggestionState(
                decision=DecisionState.APPROVED,
                disposition=Disposition.READY,
            )
        if action is SuggestionAction.REJECT:
            return SuggestionState(
                decision=DecisionState.REJECTED,
                disposition=(
                    Disposition.SUPPRESSED
                    if suppress
                    else Disposition.READY
                ),
            )
        if action is SuggestionAction.INVALIDATE_CONTEXT:
            return SuggestionState(
                decision=DecisionState.PENDING,
                disposition=Disposition.STALE,
            )

    # ------------------------------------------------------------------
    # PENDING + CONFLICT
    # ------------------------------------------------------------------
    elif disposition is Disposition.CONFLICT:
        if action is SuggestionAction.KEEP_CURRENT:
            # Keeping current rejects the competing proposal; policy may
            # additionally suppress recurrence.
            return SuggestionState(
                decision=DecisionState.REJECTED,
                disposition=(
                    Disposition.SUPPRESSED
                    if suppress
                    else Disposition.CONFLICT
                ),
            )
        if action in _APPROVING_ACTIONS and action is not SuggestionAction.APPROVE:
            return SuggestionState(
                decision=DecisionState.APPROVED,
                disposition=Disposition.CONFLICT,
            )
        if action is SuggestionAction.DEFER:
            return SuggestionState(
                decision=DecisionState.PENDING,
                disposition=Disposition.CONFLICT,
            )
        if action is SuggestionAction.INVALIDATE_CONTEXT:
            return SuggestionState(
                decision=DecisionState.PENDING,
                disposition=Disposition.STALE,
            )

    # ------------------------------------------------------------------
    # PENDING + DUPLICATE
    # ------------------------------------------------------------------
    elif disposition is Disposition.DUPLICATE:
        if action is SuggestionAction.CLASSIFY_DUPLICATE:
            # Suppress a duplicate WITHOUT implying user rejection.
            return SuggestionState(
                decision=DecisionState.PENDING,
                disposition=Disposition.SUPPRESSED,
            )
        if action is SuggestionAction.REJECT:
            return SuggestionState(
                decision=DecisionState.REJECTED,
                disposition=(
                    Disposition.SUPPRESSED
                    if suppress
                    else Disposition.DUPLICATE
                ),
            )

    # ------------------------------------------------------------------
    # PENDING + SUPPRESSED
    # ------------------------------------------------------------------
    elif disposition is Disposition.SUPPRESSED:
        if action is SuggestionAction.REOPEN_MATERIAL_EVIDENCE:
            return SuggestionState(
                decision=DecisionState.PENDING,
                disposition=(
                    Disposition.CONFLICT
                    if reopen_conflict
                    else Disposition.READY
                ),
            )

    # ------------------------------------------------------------------
    # PENDING + STALE
    # ------------------------------------------------------------------
    elif disposition is Disposition.STALE:
        if action is SuggestionAction.REOPEN_MATERIAL_EVIDENCE:
            return SuggestionState(
                decision=DecisionState.PENDING,
                disposition=(
                    Disposition.CONFLICT
                    if reopen_conflict
                    else Disposition.READY
                ),
            )
        if action is SuggestionAction.REJECT:
            return SuggestionState(
                decision=DecisionState.REJECTED,
                disposition=(
                    Disposition.SUPPRESSED
                    if suppress
                    else Disposition.STALE
                ),
            )

    raise InvalidSuggestionTransition(
        decision=decision,
        disposition=disposition,
        action=action,
    )


class AtomicSuggestion(BaseModel):
    model_config = ConfigDict(frozen=True)

    suggestion_id: str
    batch_id: str
    twin_id: str
    candidate_id: str
    resolved_entity_id: str | None = None

    predicate: Predicate
    proposed_value: object | None
    value_type: str

    decision_state: DecisionState
    disposition: Disposition

    normalized_value_fingerprint: str
    expected_active_claim_id: str | None = None

    version: int
    created_at: datetime
    decided_at: datetime | None = None
    decision_actor_id: str | None = None

    def with_transition(
        self,
        action: SuggestionAction,
        *,
        decided_at: datetime | None = None,
        decision_actor_id: str | None = None,
        suppress: bool = False,
        reopen_conflict: bool = False,
    ) -> "AtomicSuggestion":
        """Return a new immutable suggestion with the transition applied.

        The original record is never mutated; version is bumped so optimistic
        concurrency can detect stale decisions.
        """

        next_state = transition(
            SuggestionState(
                decision=self.decision_state,
                disposition=self.disposition,
            ),
            action,
            suppress=suppress,
            reopen_conflict=reopen_conflict,
        )

        decided = (
            decided_at
            if next_state.decision is not DecisionState.PENDING
            else self.decided_at
        )
        actor = (
            decision_actor_id
            if next_state.decision is not DecisionState.PENDING
            else self.decision_actor_id
        )

        return self.model_copy(
            update={
                "decision_state": next_state.decision,
                "disposition": next_state.disposition,
                "version": self.version + 1,
                "decided_at": decided,
                "decision_actor_id": actor,
            }
        )
