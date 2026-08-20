from datetime import datetime, timedelta, timezone
import sqlite3

import pytest

from onejob.trust_engine.models import (
    ConsentGrant,
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
from onejob.trust_engine.repository import TrustRepository


NOW = datetime(2026, 8, 20, 12, 0, tzinfo=timezone.utc)


@pytest.fixture
def db():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute(
        """
        CREATE TABLE canonical_jobs (
            canonical_job_id TEXT PRIMARY KEY
        )
        """
    )
    conn.execute(
        "INSERT INTO canonical_jobs(canonical_job_id) VALUES (?)",
        ("job-1",),
    )

    repo = TrustRepository()
    repo.ensure_schema(conn)

    yield conn, repo
    conn.close()


def make_signal(
    *,
    signal_id="sig-1",
    first_seen=NOW,
    last_seen=NOW,
):
    return TrustSignal(
        signal_id=signal_id,
        canonical_job_id="job-1",
        signal_type="RECRUITMENT_PAYMENT",
        level=SignalLevel.L3,
        status=SignalStatus.ACTIVE,
        confidence=1.0,
        detection_method=DetectionMethod.RULE,
        context_stage=RecruitmentStage.APPLICATION,
        evidence_refs=("observation:1",),
        extractor_version="rules-v1",
        fingerprint="job-1:payment:obs-1",
        first_seen_at=first_seen,
        last_seen_at=last_seen,
    )


def make_decision(
    evaluation_id,
    classification,
    fingerprint,
    *,
    evaluated_at=NOW,
):
    dimension = DimensionScore(
        dimension=TrustDimension.PRIVACY_SAFETY,
        state=DimensionState.KNOWN,
        score=90.0,
        confidence=95.0,
        reason_codes=("SAFE_CONTEXT",),
        evidence_refs=("field-evidence:1",),
    )

    gates = ()
    if classification is TrustClassification.AUTOMATION_BLOCKED:
        gates = (
            GateHit(
                signal_id="sig-1",
                gate_code="RECRUITMENT_PAYMENT",
                level=SignalLevel.L3,
                effect=TrustClassification.AUTOMATION_BLOCKED,
                override_policy="MANUAL_ONLY",
            ),
        )

    return TrustDecision(
        evaluation_id=evaluation_id,
        canonical_job_id="job-1",
        recruitment_stage=RecruitmentStage.APPLICATION,
        overall_score=80.0,
        confidence=90.0,
        dimensions={
            TrustDimension.PRIVACY_SAFETY: dimension,
        },
        classification=classification,
        hard_gates=gates,
        risk_signal_ids=("sig-1",),
        unknown_dimensions=(),
        not_applicable_dimensions=(),
        allowed_actions=("MANUAL_REVIEW",),
        blocked_actions=("AUTOPILOT_SUBMIT",),
        override_policy="MANUAL_ONLY",
        primary_reasons=("RECRUITMENT_PAYMENT",),
        evidence_refs=("observation:1",),
        evaluated_at=evaluated_at,
        valid_until=evaluated_at + timedelta(hours=1),
        input_fingerprint=fingerprint,
        policy_version="trust-v1",
    )


def test_schema_installs_all_trust_tables(db):
    conn, _ = db

    names = {
        row["name"]
        for row in conn.execute(
            """
            SELECT name
            FROM sqlite_master
            WHERE type = 'table'
            """
        )
    }

    assert {
        "trust_signals",
        "trust_evaluations",
        "trust_dimension_scores",
        "trust_gate_hits",
        "trust_evaluation_attempts",
        "trust_consents",
        "trust_action_events",
        "trust_entity_links",
    } <= names


def test_signal_upsert_preserves_first_seen_and_updates_last_seen(db):
    conn, repo = db

    original = make_signal()
    repo.upsert_signal(conn, original)

    later = make_signal(
        first_seen=NOW + timedelta(hours=10),
        last_seen=NOW + timedelta(hours=2),
    )
    repo.upsert_signal(conn, later)

    row = conn.execute(
        """
        SELECT first_seen_at, last_seen_at
        FROM trust_signals
        WHERE signal_id = ?
        """,
        ("sig-1",),
    ).fetchone()

    assert row["first_seen_at"] == NOW.isoformat()
    assert row["last_seen_at"] == (
        NOW + timedelta(hours=2)
    ).isoformat()


def test_resolved_signal_is_retained_not_deleted(db):
    conn, repo = db

    repo.upsert_signal(conn, make_signal())

    repo.resolve_signal(
        conn,
        "sig-1",
        resolved_at=NOW + timedelta(hours=3),
        reason="FALSE_POSITIVE_CONFIRMED",
    )

    row = conn.execute(
        """
        SELECT status, resolved_at, resolution_reason
        FROM trust_signals
        WHERE signal_id = ?
        """,
        ("sig-1",),
    ).fetchone()

    assert row is not None
    assert row["status"] == "RESOLVED"
    assert row["resolution_reason"] == (
        "FALSE_POSITIVE_CONFIRMED"
    )


def test_evaluation_history_is_immutable(db):
    conn, repo = db

    repo.upsert_signal(conn, make_signal())

    blocked = make_decision(
        "eval-1",
        TrustClassification.AUTOMATION_BLOCKED,
        "fingerprint-1",
        evaluated_at=NOW,
    )
    allowed = make_decision(
        "eval-2",
        TrustClassification.ASSISTED_ALLOWED,
        "fingerprint-2",
        evaluated_at=NOW + timedelta(hours=1),
    )

    repo.append_evaluation(conn, blocked)
    repo.append_evaluation(conn, allowed)

    rows = conn.execute(
        """
        SELECT evaluation_id, classification
        FROM trust_evaluations
        ORDER BY evaluated_at
        """
    ).fetchall()

    assert [
        (row["evaluation_id"], row["classification"])
        for row in rows
    ] == [
        ("eval-1", "AUTOMATION_BLOCKED"),
        ("eval-2", "ASSISTED_ALLOWED"),
    ]

    latest = repo.latest_evaluation(conn, "job-1")

    assert latest is not None
    assert latest.evaluation_id == "eval-2"
    assert (
        latest.classification
        is TrustClassification.ASSISTED_ALLOWED
    )


def test_duplicate_input_fingerprint_is_rejected(db):
    conn, repo = db

    first = make_decision(
        "eval-1",
        TrustClassification.REVIEW_REQUIRED,
        "same-input",
    )
    second = make_decision(
        "eval-2",
        TrustClassification.REVIEW_REQUIRED,
        "same-input",
    )

    repo.append_evaluation(conn, first)

    with pytest.raises(sqlite3.IntegrityError):
        repo.append_evaluation(conn, second)


def test_consent_lookup_requires_exact_scope(db):
    conn, repo = db

    grant = ConsentGrant(
        consent_id="consent-1",
        user_id="user-1",
        canonical_job_id="job-1",
        company_id="company-1",
        scope="KTP_FOR_VERIFIED_ONBOARDING",
        recruitment_stage=RecruitmentStage.ONBOARDING,
        issued_at=NOW,
        expires_at=NOW + timedelta(hours=1),
        revoked_at=None,
    )

    repo.grant_consent(conn, grant)

    ktp = repo.get_valid_consent(
        conn,
        user_id="user-1",
        canonical_job_id="job-1",
        scope="KTP_FOR_VERIFIED_ONBOARDING",
        now=NOW + timedelta(minutes=10),
    )
    bank = repo.get_valid_consent(
        conn,
        user_id="user-1",
        canonical_job_id="job-1",
        scope="BANK_ACCOUNT_FOR_ONBOARDING",
        now=NOW + timedelta(minutes=10),
    )

    assert ktp is not None
    assert bank is None


def test_expired_consent_is_not_valid(db):
    conn, repo = db

    grant = ConsentGrant(
        consent_id="consent-2",
        user_id="user-1",
        canonical_job_id="job-1",
        company_id="company-1",
        scope="KTP_FOR_VERIFIED_ONBOARDING",
        recruitment_stage=RecruitmentStage.ONBOARDING,
        issued_at=NOW,
        expires_at=NOW + timedelta(minutes=5),
    )
    repo.grant_consent(conn, grant)

    assert repo.get_valid_consent(
        conn,
        user_id="user-1",
        canonical_job_id="job-1",
        scope="KTP_FOR_VERIFIED_ONBOARDING",
        now=NOW + timedelta(minutes=6),
    ) is None


def test_action_event_references_exact_evaluation(db):
    conn, repo = db

    decision = make_decision(
        "eval-action",
        TrustClassification.REVIEW_REQUIRED,
        "action-input",
    )
    repo.append_evaluation(conn, decision)

    repo.append_action_event(
        conn,
        action_event_id="action-1",
        canonical_job_id="job-1",
        evaluation_id="eval-action",
        action_type="SUBMIT_APPLICATION",
        requested_mode="AUTOPILOT",
        result="DENIED",
        reason_codes=("REVIEW_REQUIRED",),
        consent_id=None,
        override_id=None,
        occurred_at=NOW,
    )

    row = conn.execute(
        """
        SELECT evaluation_id, result
        FROM trust_action_events
        WHERE action_event_id = ?
        """,
        ("action-1",),
    ).fetchone()

    assert row["evaluation_id"] == "eval-action"
    assert row["result"] == "DENIED"
