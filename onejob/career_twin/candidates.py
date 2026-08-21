from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict

from onejob.career_twin.ontology import EntityType


class CandidateLifecycle(str, Enum):
    STAGED = "STAGED"
    LINKED = "LINKED"
    PROMOTED = "PROMOTED"
    REJECTED = "REJECTED"
    SUPERSEDED = "SUPERSEDED"


class InvalidCandidateTransition(RuntimeError):
    def __init__(self, *, state: CandidateLifecycle, action: str):
        self.state = state
        self.action = action
        super().__init__(
            "invalid candidate transition: "
            f"{state.value} --{action}-->"
        )


# STAGED can go anywhere; LINKED may still be superseded by a newer
# resolution/candidate; PROMOTED and REJECTED are terminal; SUPERSEDED is
# terminal.
_CANDIDATE_TRANSITIONS: dict[
    CandidateLifecycle, dict[str, CandidateLifecycle]
] = {
    CandidateLifecycle.STAGED: {
        "LINK": CandidateLifecycle.LINKED,
        "PROMOTE": CandidateLifecycle.PROMOTED,
        "REJECT": CandidateLifecycle.REJECTED,
        "SUPERSEDE": CandidateLifecycle.SUPERSEDED,
    },
    CandidateLifecycle.LINKED: {
        "PROMOTE": CandidateLifecycle.PROMOTED,
        "REJECT": CandidateLifecycle.REJECTED,
        "SUPERSEDE": CandidateLifecycle.SUPERSEDED,
    },
    CandidateLifecycle.PROMOTED: {},
    CandidateLifecycle.REJECTED: {},
    CandidateLifecycle.SUPERSEDED: {},
}


def candidate_transition(
    state: CandidateLifecycle,
    action: str,
) -> CandidateLifecycle:
    allowed = _CANDIDATE_TRANSITIONS.get(state, {})
    if action not in allowed:
        raise InvalidCandidateTransition(state=state, action=action)
    return allowed[action]


class CandidateEntity(BaseModel):
    model_config = ConfigDict(frozen=True)

    candidate_id: str
    batch_id: str
    twin_id: str
    proposed_entity_type: EntityType
    fingerprint: str
    display_hint: str
    lifecycle_state: CandidateLifecycle
    created_at: datetime
    promoted_entity_id: str | None = None

    def with_state(
        self,
        action: str,
        *,
        promoted_entity_id: str | None = None,
    ) -> "CandidateEntity":
        next_state = candidate_transition(self.lifecycle_state, action)

        update: dict[str, object] = {"lifecycle_state": next_state}
        if next_state is CandidateLifecycle.PROMOTED:
            if promoted_entity_id is None:
                raise ValueError(
                    "promoted_entity_id required when promoting a candidate"
                )
            update["promoted_entity_id"] = promoted_entity_id

        return self.model_copy(update=update)
