from datetime import datetime, timezone

import pytest

from onejob.career_twin.suggestions import (
    AtomicSuggestion,
    DecisionState,
    Disposition,
    InvalidSuggestionTransition,
    SuggestionAction,
    SuggestionState,
    transition,
)
from onejob.career_twin.candidates import (
    CandidateEntity,
    CandidateLifecycle,
    InvalidCandidateTransition,
    candidate_transition,
)
from onejob.career_twin.ontology import (
    EntityType,
    ONTOLOGY_VERSION,
    Predicate,
)


NOW = datetime(2026, 8, 21, 3, 0, tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# Two-axis separation
# ---------------------------------------------------------------------------


def test_decision_and_disposition_are_separate_axes():
    # decision states
    assert {s.value for s in DecisionState} == {
        "PENDING",
        "APPROVED",
        "REJECTED",
    }
    # disposition states
    assert {d.value for d in Disposition} == {
        "READY",
        "CONFLICT",
        "DUPLICATE",
        "STALE",
        "SUPPRESSED",
    }


def test_pending_suppressed_is_not_user_rejected():
    # System may suppress a duplicate without implying user rejection.
    result = transition(
        SuggestionState(
            decision=DecisionState.PENDING,
            disposition=Disposition.DUPLICATE,
        ),
        SuggestionAction.CLASSIFY_DUPLICATE,
    )
    assert result.decision is DecisionState.PENDING
    assert result.disposition is Disposition.SUPPRESSED


# ---------------------------------------------------------------------------
# PENDING + READY transitions
# ---------------------------------------------------------------------------


def test_ready_approve_goes_to_approved():
    result = transition(
        SuggestionState(
            decision=DecisionState.PENDING,
            disposition=Disposition.READY,
        ),
        SuggestionAction.APPROVE,
    )
    assert result.decision is DecisionState.APPROVED


def test_ready_reject_goes_to_rejected():
    result = transition(
        SuggestionState(
            decision=DecisionState.PENDING,
            disposition=Disposition.READY,
        ),
        SuggestionAction.REJECT,
    )
    assert result.decision is DecisionState.REJECTED
    assert result.disposition is Disposition.READY


def test_ready_reject_with_suppression_marks_suppressed():
    result = transition(
        SuggestionState(
            decision=DecisionState.PENDING,
            disposition=Disposition.READY,
        ),
        SuggestionAction.REJECT,
        suppress=True,
    )
    assert result.decision is DecisionState.REJECTED
    assert result.disposition is Disposition.SUPPRESSED


def test_ready_context_invalidated_goes_to_stale():
    result = transition(
        SuggestionState(
            decision=DecisionState.PENDING,
            disposition=Disposition.READY,
        ),
        SuggestionAction.INVALIDATE_CONTEXT,
    )
    assert result.decision is DecisionState.PENDING
    assert result.disposition is Disposition.STALE


# ---------------------------------------------------------------------------
# PENDING + CONFLICT transitions
# ---------------------------------------------------------------------------


def test_conflict_keep_current_rejects_and_may_suppress():
    result = transition(
        SuggestionState(
            decision=DecisionState.PENDING,
            disposition=Disposition.CONFLICT,
        ),
        SuggestionAction.KEEP_CURRENT,
        suppress=True,
    )
    assert result.decision is DecisionState.REJECTED
    assert result.disposition is Disposition.SUPPRESSED


def test_conflict_keep_current_without_suppression_still_rejects():
    result = transition(
        SuggestionState(
            decision=DecisionState.PENDING,
            disposition=Disposition.CONFLICT,
        ),
        SuggestionAction.KEEP_CURRENT,
    )
    assert result.decision is DecisionState.REJECTED
    assert result.disposition is not Disposition.SUPPRESSED


def test_conflict_accept_alternative_approves():
    result = transition(
        SuggestionState(
            decision=DecisionState.PENDING,
            disposition=Disposition.CONFLICT,
        ),
        SuggestionAction.ACCEPT_ALTERNATIVE,
    )
    assert result.decision is DecisionState.APPROVED


def test_conflict_edit_and_accept_approves():
    result = transition(
        SuggestionState(
            decision=DecisionState.PENDING,
            disposition=Disposition.CONFLICT,
        ),
        SuggestionAction.EDIT_AND_ACCEPT,
    )
    assert result.decision is DecisionState.APPROVED


def test_conflict_defer_remains_pending_conflict():
    result = transition(
        SuggestionState(
            decision=DecisionState.PENDING,
            disposition=Disposition.CONFLICT,
        ),
        SuggestionAction.DEFER,
    )
    assert result.decision is DecisionState.PENDING
    assert result.disposition is Disposition.CONFLICT


# ---------------------------------------------------------------------------
# PENDING + SUPPRESSED reopen transitions
# ---------------------------------------------------------------------------


def test_suppressed_reopens_to_ready_on_new_evidence():
    result = transition(
        SuggestionState(
            decision=DecisionState.PENDING,
            disposition=Disposition.SUPPRESSED,
        ),
        SuggestionAction.REOPEN_MATERIAL_EVIDENCE,
    )
    assert result.decision is DecisionState.PENDING
    assert result.disposition is Disposition.READY


def test_suppressed_reopens_to_conflict_when_conflicting():
    result = transition(
        SuggestionState(
            decision=DecisionState.PENDING,
            disposition=Disposition.SUPPRESSED,
        ),
        SuggestionAction.REOPEN_MATERIAL_EVIDENCE,
        reopen_conflict=True,
    )
    assert result.decision is DecisionState.PENDING
    assert result.disposition is Disposition.CONFLICT


# ---------------------------------------------------------------------------
# Invalid transitions
# ---------------------------------------------------------------------------


def test_cannot_approve_an_already_rejected_suggestion():
    with pytest.raises(InvalidSuggestionTransition):
        transition(
            SuggestionState(
                decision=DecisionState.REJECTED,
                disposition=Disposition.READY,
            ),
            SuggestionAction.APPROVE,
        )


def test_cannot_reapprove_a_terminal_approved_suggestion():
    with pytest.raises(InvalidSuggestionTransition):
        transition(
            SuggestionState(
                decision=DecisionState.APPROVED,
                disposition=Disposition.READY,
            ),
            SuggestionAction.APPROVE,
        )


def test_cannot_accept_alternative_from_ready_disposition():
    # ACCEPT_ALTERNATIVE only applies to a conflicting proposal.
    with pytest.raises(InvalidSuggestionTransition):
        transition(
            SuggestionState(
                decision=DecisionState.PENDING,
                disposition=Disposition.READY,
            ),
            SuggestionAction.ACCEPT_ALTERNATIVE,
        )


def test_cannot_keep_current_from_ready_disposition():
    with pytest.raises(InvalidSuggestionTransition):
        transition(
            SuggestionState(
                decision=DecisionState.PENDING,
                disposition=Disposition.READY,
            ),
            SuggestionAction.KEEP_CURRENT,
        )


# ---------------------------------------------------------------------------
# AtomicSuggestion model
# ---------------------------------------------------------------------------


def test_atomic_suggestion_is_immutable_and_carries_two_axes():
    suggestion = AtomicSuggestion(
        suggestion_id="suggestion-1",
        batch_id="batch-1",
        twin_id="twin-1",
        candidate_id="candidate-1",
        predicate=Predicate.EXPERIENCE_ROLE,
        proposed_value="role-stamping-operator",
        value_type="ROLE_REF",
        decision_state=DecisionState.PENDING,
        disposition=Disposition.READY,
        normalized_value_fingerprint="fp-1",
        version=1,
        created_at=NOW,
    )

    assert suggestion.model_config["frozen"] is True
    assert suggestion.decision_state is DecisionState.PENDING
    assert suggestion.disposition is Disposition.READY
    assert suggestion.resolved_entity_id is None
    assert suggestion.expected_active_claim_id is None


def test_atomic_suggestion_apply_transition_returns_new_record():
    suggestion = AtomicSuggestion(
        suggestion_id="suggestion-1",
        batch_id="batch-1",
        twin_id="twin-1",
        candidate_id="candidate-1",
        predicate=Predicate.EXPERIENCE_ROLE,
        proposed_value="role-stamping-operator",
        value_type="ROLE_REF",
        decision_state=DecisionState.PENDING,
        disposition=Disposition.READY,
        normalized_value_fingerprint="fp-1",
        version=1,
        created_at=NOW,
    )

    approved = suggestion.with_transition(
        SuggestionAction.APPROVE,
        decided_at=NOW,
        decision_actor_id="user-1",
    )

    # original remains immutable
    assert suggestion.decision_state is DecisionState.PENDING
    assert suggestion.version == 1

    # new record reflects the decision and bumps version
    assert approved.decision_state is DecisionState.APPROVED
    assert approved.version == 2
    assert approved.decided_at == NOW
    assert approved.decision_actor_id == "user-1"


# ---------------------------------------------------------------------------
# Candidate lifecycle
# ---------------------------------------------------------------------------


def test_candidate_lifecycle_states():
    assert {s.value for s in CandidateLifecycle} == {
        "STAGED",
        "LINKED",
        "PROMOTED",
        "REJECTED",
        "SUPERSEDED",
    }


def test_candidate_id_is_not_a_canonical_entity_id():
    candidate = CandidateEntity(
        candidate_id="candidate-1",
        batch_id="batch-1",
        twin_id="twin-1",
        proposed_entity_type=EntityType.EXPERIENCE,
        fingerprint="fp-1",
        display_hint="Operator @ PT Example",
        lifecycle_state=CandidateLifecycle.STAGED,
        created_at=NOW,
    )
    assert candidate.promoted_entity_id is None
    # a candidate is never itself a canonical entity id
    assert candidate.candidate_id != candidate.promoted_entity_id


@pytest.mark.parametrize(
    "action,expected",
    [
        ("LINK", CandidateLifecycle.LINKED),
        ("PROMOTE", CandidateLifecycle.PROMOTED),
        ("REJECT", CandidateLifecycle.REJECTED),
        ("SUPERSEDE", CandidateLifecycle.SUPERSEDED),
    ],
)
def test_candidate_transitions_from_staged(action, expected):
    assert (
        candidate_transition(CandidateLifecycle.STAGED, action)
        is expected
    )


def test_linked_candidate_can_be_superseded():
    assert (
        candidate_transition(CandidateLifecycle.LINKED, "SUPERSEDE")
        is CandidateLifecycle.SUPERSEDED
    )


def test_promoted_candidate_is_terminal():
    with pytest.raises(InvalidCandidateTransition):
        candidate_transition(CandidateLifecycle.PROMOTED, "REJECT")


def test_rejected_candidate_is_terminal():
    with pytest.raises(InvalidCandidateTransition):
        candidate_transition(CandidateLifecycle.REJECTED, "PROMOTE")
