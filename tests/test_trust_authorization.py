from datetime import datetime, timedelta, timezone
import sqlite3

import pytest

from onejob.trust_engine.authorization import (
    AuthorizationRequest,
    SafetySwitches,
    authorize_action,
)
from onejob.trust_engine.models import (
    ActionDecision,
    ActionMode,
    ConsentGrant,
    DimensionScore,
    DimensionState,
    RecruitmentStage,
    TrustClassification,
    TrustDecision,
    TrustDimension,
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
        """
        INSERT INTO canonical_jobs(canonical_job_id)
        VALUES ('job-1')
        """
    )

    repo = TrustRepository()
    repo.ensure_schema(conn)

    yield conn, repo
    conn.close()


def decision(
    *,
    evaluation_id="eval-1",
    classification=TrustClassification.AUTOPILOT_ELIGIBLE,
    valid_until=None,
):
    if valid_until is None:
        valid_until = NOW + timedelta(hours=1)

    dimension = DimensionScore(
        dimension=TrustDimension.PRIVACY_SAFETY,
        state=DimensionState.KNOWN,
        score=100,
        confidence=100,
        reason_codes=("SAFE",),
        evidence_refs=(),
    )

    return TrustDecision(
        evaluation_id=evaluation_id,
        canonical_job_id="job-1",
        recruitment_stage=RecruitmentStage.ONBOARDING,
        overall_score=100,
        confidence=100,
        dimensions={
            TrustDimension.PRIVACY_SAFETY: dimension,
        },
        classification=classification,
        hard_gates=(),
        risk_signal_ids=(),
        unknown_dimensions=(),
        not_applicable_dimensions=(),
        allowed_actions=(
            "MANUAL_REVIEW",
            "ASSISTED_SUBMIT",
            "AUTOPILOT_SUBMIT",
        ),
        blocked_actions=(),
        override_policy="NONE",
        primary_reasons=("SAFE",),
        evidence_refs=(),
        evaluated_at=NOW,
        valid_until=valid_until,
        input_fingerprint=evaluation_id,
        policy_version="trust-v1",
    )


def request(
    *,
    action_type="UPLOAD_KTP",
    requested_mode=ActionMode.ASSISTED,
    consent_scope="KTP_FOR_VERIFIED_ONBOARDING",
):
    return AuthorizationRequest(
        request_id="req-1",
        user_id="user-1",
        canonical_job_id="job-1",
        company_id="company-1",
        action_type=action_type,
        requested_mode=requested_mode,
        consent_scope=consent_scope,
    )


def test_trust_100_does_not_authorize_ktp_without_consent(db):
    conn, repo = db
    repo.append_evaluation(conn, decision())

    result = authorize_action(
        conn,
        repo,
        request(),
        now=NOW + timedelta(minutes=5),
        switches=SafetySwitches(
            autopilot_enabled=True,
            sensitive_document_automation=True,
        ),
    )

    assert result.decision is ActionDecision.DENIED
    assert "CONSENT_REQUIRED" in result.reason_codes


def test_exact_valid_consent_allows_sensitive_assisted_action(db):
    conn, repo = db
    repo.append_evaluation(conn, decision())

    repo.grant_consent(
        conn,
        ConsentGrant(
            consent_id="consent-1",
            user_id="user-1",
            canonical_job_id="job-1",
            company_id="company-1",
            scope="KTP_FOR_VERIFIED_ONBOARDING",
            recruitment_stage=RecruitmentStage.ONBOARDING,
            issued_at=NOW,
            expires_at=NOW + timedelta(hours=1),
        ),
    )

    result = authorize_action(
        conn,
        repo,
        request(),
        now=NOW + timedelta(minutes=5),
        switches=SafetySwitches(
            autopilot_enabled=True,
            sensitive_document_automation=True,
        ),
    )

    assert result.decision is ActionDecision.ALLOWED
    assert result.consent_id == "consent-1"


def test_expired_consent_is_rejected(db):
    conn, repo = db
    repo.append_evaluation(conn, decision())

    repo.grant_consent(
        conn,
        ConsentGrant(
            consent_id="consent-expired",
            user_id="user-1",
            canonical_job_id="job-1",
            company_id="company-1",
            scope="KTP_FOR_VERIFIED_ONBOARDING",
            recruitment_stage=RecruitmentStage.ONBOARDING,
            issued_at=NOW,
            expires_at=NOW + timedelta(minutes=1),
        ),
    )

    result = authorize_action(
        conn,
        repo,
        request(),
        now=NOW + timedelta(minutes=5),
        switches=SafetySwitches(
            autopilot_enabled=True,
            sensitive_document_automation=True,
        ),
    )

    assert result.decision is ActionDecision.DENIED
    assert "CONSENT_REQUIRED" in result.reason_codes


def test_ktp_consent_does_not_authorize_bank_account(db):
    conn, repo = db
    repo.append_evaluation(conn, decision())

    repo.grant_consent(
        conn,
        ConsentGrant(
            consent_id="consent-ktp",
            user_id="user-1",
            canonical_job_id="job-1",
            company_id="company-1",
            scope="KTP_FOR_VERIFIED_ONBOARDING",
            recruitment_stage=RecruitmentStage.ONBOARDING,
            issued_at=NOW,
            expires_at=NOW + timedelta(hours=1),
        ),
    )

    result = authorize_action(
        conn,
        repo,
        request(
            action_type="UPLOAD_BANK_ACCOUNT",
            consent_scope="BANK_ACCOUNT_FOR_ONBOARDING",
        ),
        now=NOW + timedelta(minutes=5),
        switches=SafetySwitches(
            autopilot_enabled=True,
            sensitive_document_automation=True,
        ),
    )

    assert result.decision is ActionDecision.DENIED
    assert "CONSENT_REQUIRED" in result.reason_codes


def test_payment_action_is_permanently_denied(db):
    conn, repo = db
    repo.append_evaluation(conn, decision())

    result = authorize_action(
        conn,
        repo,
        request(
            action_type="RECRUITMENT_PAYMENT",
            consent_scope=None,
        ),
        now=NOW,
        switches=SafetySwitches(
            autopilot_enabled=True,
            sensitive_document_automation=True,
        ),
    )

    assert result.decision is ActionDecision.DENIED
    assert "PAYMENT_ACTION_PERMANENTLY_DISABLED" in (
        result.reason_codes
    )


def test_credential_action_is_permanently_denied(db):
    conn, repo = db
    repo.append_evaluation(conn, decision())

    result = authorize_action(
        conn,
        repo,
        request(
            action_type="SEND_OTP",
            consent_scope=None,
        ),
        now=NOW,
        switches=SafetySwitches(
            autopilot_enabled=True,
            sensitive_document_automation=True,
        ),
    )

    assert result.decision is ActionDecision.DENIED
    assert "CREDENTIAL_ACTION_PERMANENTLY_DISABLED" in (
        result.reason_codes
    )


def test_autopilot_is_disabled_by_default(db):
    conn, repo = db
    repo.append_evaluation(conn, decision())

    result = authorize_action(
        conn,
        repo,
        request(
            action_type="SUBMIT_APPLICATION",
            requested_mode=ActionMode.AUTOPILOT,
            consent_scope=None,
        ),
        now=NOW,
    )

    assert result.decision is ActionDecision.DENIED
    assert "AUTOPILOT_KILL_SWITCH" in result.reason_codes


def test_stale_evaluation_cannot_authorize_autopilot(db):
    conn, repo = db

    repo.append_evaluation(
        conn,
        decision(
            valid_until=NOW + timedelta(minutes=1),
        ),
    )

    result = authorize_action(
        conn,
        repo,
        request(
            action_type="SUBMIT_APPLICATION",
            requested_mode=ActionMode.AUTOPILOT,
            consent_scope=None,
        ),
        now=NOW + timedelta(minutes=5),
        switches=SafetySwitches(
            autopilot_enabled=True,
        ),
    )

    assert result.decision is ActionDecision.DENIED
    assert "TRUST_EVALUATION_STALE" in result.reason_codes


def test_autopilot_requires_autopilot_eligible_classification(db):
    conn, repo = db

    repo.append_evaluation(
        conn,
        decision(
            classification=TrustClassification.REVIEW_REQUIRED,
        ),
    )

    result = authorize_action(
        conn,
        repo,
        request(
            action_type="SUBMIT_APPLICATION",
            requested_mode=ActionMode.AUTOPILOT,
            consent_scope=None,
        ),
        now=NOW,
        switches=SafetySwitches(
            autopilot_enabled=True,
        ),
    )

    assert result.decision is ActionDecision.DENIED
    assert "TRUST_POLICY_DENIED_ACTION" in result.reason_codes


def test_sensitive_automation_switch_blocks_document_action(db):
    conn, repo = db
    repo.append_evaluation(conn, decision())

    result = authorize_action(
        conn,
        repo,
        request(),
        now=NOW,
        switches=SafetySwitches(
            autopilot_enabled=True,
            sensitive_document_automation=False,
        ),
    )

    assert result.decision is ActionDecision.DENIED
    assert "SENSITIVE_DOCUMENT_AUTOMATION_DISABLED" in (
        result.reason_codes
    )


def test_audit_write_failure_prevents_sensitive_execution(
    db,
    monkeypatch,
):
    conn, repo = db
    repo.append_evaluation(conn, decision())

    repo.grant_consent(
        conn,
        ConsentGrant(
            consent_id="consent-1",
            user_id="user-1",
            canonical_job_id="job-1",
            company_id="company-1",
            scope="KTP_FOR_VERIFIED_ONBOARDING",
            recruitment_stage=RecruitmentStage.ONBOARDING,
            issued_at=NOW,
            expires_at=NOW + timedelta(hours=1),
        ),
    )

    def fail_audit(*args, **kwargs):
        raise sqlite3.OperationalError(
            "simulated audit persistence failure"
        )

    monkeypatch.setattr(
        repo,
        "append_action_event",
        fail_audit,
    )

    result = authorize_action(
        conn,
        repo,
        request(),
        now=NOW,
        switches=SafetySwitches(
            autopilot_enabled=True,
            sensitive_document_automation=True,
        ),
    )

    assert result.decision is ActionDecision.DENIED
    assert "AUDIT_PERSISTENCE_FAILED" in result.reason_codes
