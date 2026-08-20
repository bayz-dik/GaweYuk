from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

import onejob.api as api_module
from onejob.persistence.db import Database
from onejob.trust_engine.explainability import (
    TrustExplainabilityService,
)
from onejob.trust_engine.models import (
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


NOW = datetime.now(timezone.utc)


def make_db(tmp_path):
    db = Database(
        tmp_path / "trust-api.db"
    )

    with db.transaction() as conn:
        conn.execute(
            """
            CREATE TABLE canonical_jobs (
                canonical_job_id TEXT PRIMARY KEY
            )
            """
        )

        conn.execute(
            """
            INSERT INTO canonical_jobs(
                canonical_job_id
            )
            VALUES
                ('job-1'),
                ('job-no-eval')
            """
        )

        TrustRepository().ensure_schema(conn)

    return db


def make_signal():
    return TrustSignal(
        signal_id="sig-payment",
        canonical_job_id="job-1",
        signal_type="RECRUITMENT_PAYMENT",
        level=SignalLevel.L3,
        status=SignalStatus.ACTIVE,
        confidence=1.0,
        detection_method=DetectionMethod.RULE,
        context_stage=RecruitmentStage.APPLICATION,
        evidence_refs=("observation:payment-1",),
        extractor_version="rules-v1",
        fingerprint="payment-fingerprint",
        first_seen_at=NOW,
        last_seen_at=NOW,
    )


def make_decision(
    *,
    valid_until=None,
):
    if valid_until is None:
        valid_until = NOW + timedelta(hours=1)

    privacy = DimensionScore(
        dimension=TrustDimension.PRIVACY_SAFETY,
        state=DimensionState.KNOWN,
        score=20.0,
        confidence=100.0,
        reason_codes=(
            "RECRUITMENT_PAYMENT",
        ),
        evidence_refs=(
            "observation:payment-1",
        ),
    )

    identity = DimensionScore(
        dimension=TrustDimension.COMPANY_IDENTITY,
        state=DimensionState.KNOWN,
        score=95.0,
        confidence=90.0,
        reason_codes=(
            "CANONICAL_COMPANY_PRESENT",
        ),
        evidence_refs=(
            "evidence:company-1",
        ),
    )

    gate = GateHit(
        signal_id="sig-payment",
        gate_code="RECRUITMENT_PAYMENT",
        level=SignalLevel.L3,
        effect=TrustClassification.AUTOMATION_BLOCKED,
        override_policy="MANUAL_ONLY",
    )

    return TrustDecision(
        evaluation_id="eval-trust-api",
        canonical_job_id="job-1",
        recruitment_stage=RecruitmentStage.APPLICATION,
        overall_score=72.0,
        confidence=88.0,
        dimensions={
            TrustDimension.COMPANY_IDENTITY:
                identity,
            TrustDimension.PRIVACY_SAFETY:
                privacy,
        },
        classification=(
            TrustClassification.AUTOMATION_BLOCKED
        ),
        hard_gates=(gate,),
        risk_signal_ids=("sig-payment",),
        unknown_dimensions=(
            TrustDimension.RECRUITER_INTEGRITY,
        ),
        not_applicable_dimensions=(),
        allowed_actions=(
            "MANUAL_INVESTIGATION",
        ),
        blocked_actions=(
            "ASSISTED_SUBMIT",
            "AUTOPILOT_SUBMIT",
        ),
        override_policy="MANUAL_ONLY",
        primary_reasons=(
            "RECRUITMENT_PAYMENT",
        ),
        evidence_refs=(
            "observation:payment-1",
            "evidence:company-1",
        ),
        evaluated_at=NOW,
        valid_until=valid_until,
        input_fingerprint="trust-api-input",
        policy_version="trust-v1",
    )


def configure(
    tmp_path,
    monkeypatch,
    *,
    valid_until=None,
):
    db = make_db(tmp_path)
    repo = TrustRepository()

    with db.transaction() as conn:
        repo.upsert_signal(
            conn,
            make_signal(),
        )

        repo.append_evaluation(
            conn,
            make_decision(
                valid_until=valid_until,
            ),
        )

    explainer = TrustExplainabilityService(
        db
    )

    monkeypatch.setattr(
        api_module,
        "trust_explainer",
        explainer,
    )

    return TestClient(
        api_module.app
    )


def test_trust_endpoint_returns_explainable_snapshot(
    tmp_path,
    monkeypatch,
):
    client = configure(
        tmp_path,
        monkeypatch,
    )

    response = client.get(
        "/api/jobs/job-1/trust"
    )

    assert response.status_code == 200

    data = response.json()

    assert data["canonical_job_id"] == "job-1"
    assert data["evaluation_id"] == (
        "eval-trust-api"
    )

    assert data["classification"] == (
        "AUTOMATION_BLOCKED"
    )

    assert data["overall_score"] == 72.0
    assert data["confidence"] == 88.0

    assert data["freshness"]["state"] == (
        "FRESH"
    )

    assert (
        data["dimensions"]["PRIVACY_SAFETY"][
            "score"
        ]
        == 20.0
    )

    assert data["hard_gates"][0][
        "gate_code"
    ] == "RECRUITMENT_PAYMENT"

    assert (
        "AUTOPILOT_SUBMIT"
        in data["blocked_actions"]
    )

    assert (
        "observation:payment-1"
        in data["evidence_refs"]
    )


def test_trust_endpoint_exposes_signal_metadata_not_raw_text(
    tmp_path,
    monkeypatch,
):
    client = configure(
        tmp_path,
        monkeypatch,
    )

    data = client.get(
        "/api/jobs/job-1/trust"
    ).json()

    signal = data["active_signals"][0]

    assert signal["signal_type"] == (
        "RECRUITMENT_PAYMENT"
    )

    assert signal["level"] == "L3"

    assert set(signal) == {
        "signal_id",
        "signal_type",
        "level",
        "status",
        "confidence",
        "detection_method",
        "context_stage",
        "evidence_refs",
        "extractor_version",
        "first_seen_at",
        "last_seen_at",
    }


def test_trust_endpoint_marks_expired_snapshot_needs_refresh(
    tmp_path,
    monkeypatch,
):
    client = configure(
        tmp_path,
        monkeypatch,
        valid_until=NOW - timedelta(minutes=1),
    )

    response = client.get(
        "/api/jobs/job-1/trust"
    )

    assert response.status_code == 200

    assert response.json()[
        "freshness"
    ]["state"] == "NEEDS_REFRESH"


def test_trust_endpoint_returns_404_for_unknown_job(
    tmp_path,
    monkeypatch,
):
    db = make_db(tmp_path)

    monkeypatch.setattr(
        api_module,
        "trust_explainer",
        TrustExplainabilityService(db),
    )

    client = TestClient(
        api_module.app
    )

    response = client.get(
        "/api/jobs/missing-job/trust"
    )

    assert response.status_code == 404
    assert response.json()["detail"] == (
        "Job not found"
    )


def test_trust_endpoint_returns_404_when_job_has_no_evaluation(
    tmp_path,
    monkeypatch,
):
    db = make_db(tmp_path)

    monkeypatch.setattr(
        api_module,
        "trust_explainer",
        TrustExplainabilityService(db),
    )

    client = TestClient(
        api_module.app
    )

    response = client.get(
        "/api/jobs/job-no-eval/trust"
    )

    assert response.status_code == 404

    assert response.json()["detail"] == (
        "Trust evaluation not found"
    )


def test_trust_endpoint_is_503_when_database_not_configured(
    monkeypatch,
):
    monkeypatch.setattr(
        api_module,
        "trust_explainer",
        None,
    )

    client = TestClient(
        api_module.app
    )

    response = client.get(
        "/api/jobs/job-1/trust"
    )

    assert response.status_code == 503
    assert response.json()["detail"] == (
        "Trust database not configured"
    )
