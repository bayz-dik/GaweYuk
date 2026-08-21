from datetime import datetime, timezone

import pytest

from onejob.job_verification.review import (
    HardGateNotReviewOverrideable,
    IdempotencyConflict,
    ReviewActor,
    ReviewAuthorizationDenied,
    ReviewCommandService,
    ReviewDecision,
    StaleReviewContext,
    VerificationCaseState,
)
from onejob.persistence.db import Database


NOW = datetime(2026, 8, 21, tzinfo=timezone.utc)


class FakeCaseStore:
    def __init__(self):
        self.current_verification = "verif-1"
        self.hard_gate = False
        self.reevaluated = []

    def supersede_verification(self, canonical_job_id):
        self.current_verification = "verif-2"

    def latest_verification_id(self, canonical_job_id):
        return self.current_verification

    def has_absolute_hard_gate(self, verification_id):
        return self.hard_gate

    def trigger_reevaluation(self, canonical_job_id, *, now):
        self.reevaluated.append(canonical_job_id)


class OpenCase:
    def __init__(self):
        self.case_id = "case-1"
        self.canonical_job_id = "job-1"
        self.verification_id = "verif-1"


@pytest.fixture
def service(tmp_path):
    db = Database(tmp_path / "review.db")
    db.initialize()
    store = FakeCaseStore()
    svc = ReviewCommandService(db, store=store)
    svc.fixture_store = store
    with db.transaction() as conn:
        svc.repo.open_case(
            conn,
            case_id="case-1",
            canonical_job_id="job-1",
            verification_id="verif-1",
            reason_codes=("AMBIGUOUS_DUPLICATE",),
            priority="LOW",
            opened_at=NOW,
        )
    return svc


@pytest.fixture
def open_case():
    return OpenCase()


def _reviewer():
    return ReviewActor(actor_id="reviewer-1", roles=("job_verifier",))


def test_non_reviewer_cannot_resolve_case(service, open_case):
    with pytest.raises(ReviewAuthorizationDenied):
        service.resolve_case(
            actor=ReviewActor(actor_id="user-1", roles=("candidate",)),
            case_id=open_case.case_id,
            expected_verification_id=open_case.verification_id,
            idempotency_key="idem-1",
            decision=ReviewDecision.VERIFY,
            reason_codes=("MANUAL_CORROBORATION",),
            now=NOW,
        )


def test_stale_verification_context_cannot_be_resolved(service, open_case):
    service.fixture_store.supersede_verification(open_case.canonical_job_id)
    with pytest.raises(StaleReviewContext):
        service.resolve_case(
            actor=_reviewer(),
            case_id=open_case.case_id,
            expected_verification_id=open_case.verification_id,
            idempotency_key="idem-2",
            decision=ReviewDecision.VERIFY,
            reason_codes=("MANUAL_CORROBORATION",),
            now=NOW,
        )


def test_reviewer_can_resolve_and_triggers_reevaluation(service, open_case):
    resolution = service.resolve_case(
        actor=_reviewer(),
        case_id=open_case.case_id,
        expected_verification_id=open_case.verification_id,
        idempotency_key="idem-3",
        decision=ReviewDecision.VERIFY,
        reason_codes=("MANUAL_CORROBORATION",),
        now=NOW,
    )
    assert resolution.decision is ReviewDecision.VERIFY
    assert "job-1" in service.fixture_store.reevaluated

    with service.db.connection() as conn:
        case = service.repo.get_case(conn, "case-1")
    assert case["state"] == VerificationCaseState.RESOLVED.value


def test_absolute_hard_gate_cannot_be_review_overridden(service, open_case):
    service.fixture_store.hard_gate = True
    with pytest.raises(HardGateNotReviewOverrideable):
        service.resolve_case(
            actor=_reviewer(),
            case_id=open_case.case_id,
            expected_verification_id=open_case.verification_id,
            idempotency_key="idem-4",
            decision=ReviewDecision.VERIFY,
            reason_codes=("MANUAL_CORROBORATION",),
            now=NOW,
        )


def test_idempotent_replay_returns_same_resolution(service, open_case):
    first = service.resolve_case(
        actor=_reviewer(),
        case_id=open_case.case_id,
        expected_verification_id=open_case.verification_id,
        idempotency_key="idem-5",
        decision=ReviewDecision.VERIFY,
        reason_codes=("MANUAL_CORROBORATION",),
        now=NOW,
    )
    second = service.resolve_case(
        actor=_reviewer(),
        case_id=open_case.case_id,
        expected_verification_id=open_case.verification_id,
        idempotency_key="idem-5",
        decision=ReviewDecision.VERIFY,
        reason_codes=("MANUAL_CORROBORATION",),
        now=NOW,
    )
    assert first.resolution_id == second.resolution_id


def test_idempotency_conflict_on_different_payload(service, open_case):
    service.resolve_case(
        actor=_reviewer(),
        case_id=open_case.case_id,
        expected_verification_id=open_case.verification_id,
        idempotency_key="idem-6",
        decision=ReviewDecision.VERIFY,
        reason_codes=("MANUAL_CORROBORATION",),
        now=NOW,
    )
    with pytest.raises(IdempotencyConflict):
        service.resolve_case(
            actor=_reviewer(),
            case_id=open_case.case_id,
            expected_verification_id=open_case.verification_id,
            idempotency_key="idem-6",
            decision=ReviewDecision.REJECT,
            reason_codes=("DIFFERENT",),
            now=NOW,
        )
