from datetime import datetime, timedelta, timezone

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from onejob.catalog.api import create_catalog_router
from onejob.job_verification.models import ApplyDestinationStatus, JobVerificationSnapshot
from onejob.job_verification.policy import PublicationState
from onejob.job_verification.repository import VerificationRepository
from onejob.persistence.db import Database


NOW = datetime(2026, 8, 21, tzinfo=timezone.utc)


class SeededCatalog:
    def __init__(self, db):
        self.db = db
        self.publishable_job_id = "job-pub"
        self.review_job_id = "job-review"
        self.rejected_job_id = "job-rejected"


def _seed_job(conn, job_id, title):
    conn.execute(
        "INSERT OR IGNORE INTO companies (company_id, normalized_name, display_name) "
        "VALUES ('cmp-1', 'pt example', 'PT Example')"
    )
    conn.execute(
        """
        INSERT INTO canonical_jobs (
            canonical_job_id, company_id, title, normalized_title, location,
            normalized_location, description, salary_min, salary_max, currency,
            employment_type, contact_email, lifecycle_state, first_seen_at,
            last_seen_at, active_status_confidence
        )
        VALUES (?, 'cmp-1', ?, ?, 'Bekasi', 'bekasi', 'desc', 6000000, 8000000,
                'IDR', 'FULL_TIME', NULL, 'ACTIVE', ?, ?, 1.0)
        """,
        (job_id, title, title.lower(), NOW.isoformat(), NOW.isoformat()),
    )


def _seed(db):
    repo = VerificationRepository()
    seeded = SeededCatalog(db)
    with db.transaction() as conn:
        for job_id, title in [
            (seeded.publishable_job_id, "Publishable Operator"),
            (seeded.review_job_id, "Review Operator"),
            (seeded.rejected_job_id, "Rejected Operator"),
        ]:
            _seed_job(conn, job_id, title)

        snapshot = JobVerificationSnapshot(
            verification_id="verif-pub",
            canonical_job_id=seeded.publishable_job_id,
            canonical_version_id=None,
            identity_snapshot_id=None,
            trust_evaluation_id=None,
            identity_state="VERIFIED",
            trust_classification="AUTOPILOT_ELIGIBLE",
            destination_status=ApplyDestinationStatus.VERIFIED,
            freshness_state="CURRENT",
            corroboration={"independent_family_count": 1, "appearance_count": 1},
            hard_gate_hits=(),
            unknowns=(),
            evaluated_at=NOW,
            valid_until=NOW + timedelta(days=7),
            input_fingerprint="fp-pub",
            verification_policy_version="job-verification-v1",
        )
        repo.append(conn, snapshot, evidence_refs=("SECRET_INTERNAL_EVIDENCE_MARKER",))

        repo.append_publication_decision(
            conn,
            decision_id="dec-pub",
            canonical_job_id=seeded.publishable_job_id,
            verification_id="verif-pub",
            state=PublicationState.PUBLISHABLE,
            reason_codes=("ALL_PUBLICATION_CONDITIONS_MET",),
            decided_at=NOW,
        )
        repo.append_publication_decision(
            conn,
            decision_id="dec-review",
            canonical_job_id=seeded.review_job_id,
            verification_id=None,
            state=PublicationState.REVIEW_REQUIRED,
            reason_codes=("PRIVATE_REVIEW_NOTE",),
            decided_at=NOW,
        )
        repo.append_publication_decision(
            conn,
            decision_id="dec-rejected",
            canonical_job_id=seeded.rejected_job_id,
            verification_id=None,
            state=PublicationState.REJECTED,
            reason_codes=("HARD_GATE_PAYMENT_REQUIRED",),
            decided_at=NOW,
        )
    return seeded


@pytest.fixture
def env(tmp_path):
    db = Database(tmp_path / "catalog.db")
    db.initialize()
    seeded = _seed(db)
    app = FastAPI()
    app.include_router(create_catalog_router(db))
    client = TestClient(app, raise_server_exceptions=False)
    return client, seeded


def test_catalog_lists_only_publishable_jobs(env):
    client, seeded = env
    response = client.get("/api/catalog/jobs")
    assert response.status_code == 200
    ids = {item["canonical_job_id"] for item in response.json()}
    assert seeded.publishable_job_id in ids
    assert seeded.review_job_id not in ids
    assert seeded.rejected_job_id not in ids


def test_rejected_job_returns_404_from_public_catalog(env):
    client, seeded = env
    response = client.get(f"/api/catalog/jobs/{seeded.rejected_job_id}")
    assert response.status_code == 404


def test_publishable_job_detail_returns_safe_shape(env):
    client, seeded = env
    response = client.get(f"/api/catalog/jobs/{seeded.publishable_job_id}")
    assert response.status_code == 200
    body = response.json()
    assert body["canonical_job_id"] == seeded.publishable_job_id
    assert body["title"] == "Publishable Operator"
    assert "verification_summary" in body


def test_verification_endpoint_exposes_safe_summary(env):
    client, seeded = env
    response = client.get(
        f"/api/catalog/jobs/{seeded.publishable_job_id}/verification"
    )
    assert response.status_code == 200
    body = response.json()
    assert body["independent_evidence_family_count"] == 1


def test_catalog_never_leaks_internal_markers(env):
    client, seeded = env
    listing = client.get("/api/catalog/jobs").text
    detail = client.get(f"/api/catalog/jobs/{seeded.publishable_job_id}").text
    verification = client.get(
        f"/api/catalog/jobs/{seeded.publishable_job_id}/verification"
    ).text
    for blob in (listing, detail, verification):
        assert "SECRET_INTERNAL_EVIDENCE_MARKER" not in blob
        assert "PRIVATE_REVIEW_NOTE" not in blob
