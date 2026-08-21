from datetime import datetime, timedelta, timezone

import pytest

from onejob.job_verification.models import ApplyDestinationStatus
from onejob.job_verification.policy import (
    PublicationPolicy,
    PublicationState,
)


NOW = datetime(2026, 8, 21, tzinfo=timezone.utc)


class _Snapshot:
    def __init__(
        self,
        *,
        trust_classification="AUTOPILOT_ELIGIBLE",
        identity_state="VERIFIED",
        destination_status="VERIFIED",
        freshness_state="CURRENT",
        hard_gates=(),
        critical_unknowns=(),
    ):
        self.trust_classification = trust_classification
        self.identity_state = identity_state
        self.destination_status = (
            destination_status
            if isinstance(destination_status, ApplyDestinationStatus)
            else ApplyDestinationStatus(destination_status)
        )
        self.freshness_state = freshness_state
        self.hard_gate_hits = tuple(hard_gates)
        self.unknowns = tuple(critical_unknowns)


class _SourcePolicy:
    def __init__(self, *, publication_evidence_allowed):
        self.publication_evidence_allowed = publication_evidence_allowed


def _snapshot(**kwargs):
    return _Snapshot(**kwargs)


def _source_policy(*, publication_evidence_allowed):
    return _SourcePolicy(publication_evidence_allowed=publication_evidence_allowed)


def test_authoritative_current_safe_job_is_publishable():
    draft = PublicationPolicy().evaluate(
        _snapshot(),
        source_policy=_source_policy(publication_evidence_allowed=True),
    )
    assert draft.state is PublicationState.PUBLISHABLE


def test_review_required_trust_never_becomes_publishable():
    draft = PublicationPolicy().evaluate(
        _snapshot(trust_classification="REVIEW_REQUIRED"),
        source_policy=_source_policy(publication_evidence_allowed=True),
    )
    assert draft.state is PublicationState.REVIEW_REQUIRED


def test_automation_blocked_is_quarantined():
    draft = PublicationPolicy().evaluate(
        _snapshot(trust_classification="AUTOMATION_BLOCKED"),
        source_policy=_source_policy(publication_evidence_allowed=True),
    )
    assert draft.state is PublicationState.QUARANTINED


def test_absolute_block_is_rejected():
    draft = PublicationPolicy().evaluate(
        _snapshot(trust_classification="ABSOLUTE_BLOCK"),
        source_policy=_source_policy(publication_evidence_allowed=True),
    )
    assert draft.state is PublicationState.REJECTED


def test_confirmed_hard_gate_is_rejected():
    draft = PublicationPolicy().evaluate(
        _snapshot(hard_gates=("PAYMENT_REQUIRED",)),
        source_policy=_source_policy(publication_evidence_allowed=True),
    )
    assert draft.state is PublicationState.REJECTED


def test_policy_blocked_source_cannot_publish_even_with_high_trust():
    draft = PublicationPolicy().evaluate(
        _snapshot(),
        source_policy=_source_policy(publication_evidence_allowed=False),
    )
    assert draft.state is not PublicationState.PUBLISHABLE


def test_critical_identity_unknown_requires_review():
    draft = PublicationPolicy().evaluate(
        _snapshot(identity_state="UNKNOWN", critical_unknowns=("COMPANY_IDENTITY",)),
        source_policy=_source_policy(publication_evidence_allowed=True),
    )
    assert draft.state is PublicationState.REVIEW_REQUIRED


def test_expired_freshness_is_withdrawn():
    draft = PublicationPolicy().evaluate(
        _snapshot(freshness_state="EXPIRED"),
        source_policy=_source_policy(publication_evidence_allowed=True),
    )
    assert draft.state is PublicationState.WITHDRAWN


def test_closed_freshness_is_withdrawn():
    draft = PublicationPolicy().evaluate(
        _snapshot(freshness_state="CLOSED"),
        source_policy=_source_policy(publication_evidence_allowed=True),
    )
    assert draft.state is PublicationState.WITHDRAWN


def test_every_decision_has_reason_codes():
    draft = PublicationPolicy().evaluate(
        _snapshot(),
        source_policy=_source_policy(publication_evidence_allowed=True),
    )
    assert draft.reason_codes


def test_publication_decision_atomicity_preserves_old_head(tmp_path):
    from onejob.job_verification.repository import VerificationRepository
    from onejob.job_verification.models import JobVerificationSnapshot
    from onejob.persistence.db import Database

    db = Database(tmp_path / "pub.db")
    db.initialize()
    repo = VerificationRepository()

    snapshot = JobVerificationSnapshot(
        verification_id="verif-1",
        canonical_job_id="job-1",
        canonical_version_id=None,
        identity_snapshot_id=None,
        trust_evaluation_id=None,
        identity_state="VERIFIED",
        trust_classification="AUTOPILOT_ELIGIBLE",
        destination_status=ApplyDestinationStatus.VERIFIED,
        freshness_state="CURRENT",
        corroboration={},
        hard_gate_hits=(),
        unknowns=(),
        evaluated_at=NOW,
        valid_until=NOW + timedelta(days=7),
        input_fingerprint="fp-1",
        verification_policy_version="job-verification-v1",
    )
    with db.transaction() as conn:
        repo.append(conn, snapshot, evidence_refs=())

    # First decision commits.
    with db.transaction() as conn:
        repo.append_publication_decision(
            conn,
            decision_id="dec-1",
            canonical_job_id="job-1",
            verification_id="verif-1",
            state=PublicationState.PUBLISHABLE,
            reason_codes=("OK",),
            decided_at=NOW,
        )

    # Second decision transaction fails after the immutable insert but before
    # head update; nothing from the failed transaction should persist.
    with pytest.raises(RuntimeError, match="boom"):
        with db.transaction() as conn:
            repo.append_publication_decision(
                conn,
                decision_id="dec-2",
                canonical_job_id="job-1",
                verification_id="verif-1",
                state=PublicationState.WITHDRAWN,
                reason_codes=("X",),
                decided_at=NOW,
            )
            raise RuntimeError("boom")

    with db.connection() as conn:
        head = repo.get_publication_head(conn, "job-1")
        decisions = conn.execute(
            "SELECT COUNT(*) FROM publication_decisions WHERE canonical_job_id='job-1'"
        ).fetchone()[0]

    assert head.state is PublicationState.PUBLISHABLE
    assert head.decision_id == "dec-1"
    assert decisions == 1
