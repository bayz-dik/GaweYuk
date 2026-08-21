from datetime import datetime, timedelta, timezone

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from onejob.catalog.api import create_catalog_router
from onejob.company_identity.models import (
    IdentityRelationship,
    IdentityRelationshipStatus,
    IdentityRelationshipType,
)
from onejob.company_identity.repository import CompanyIdentityRepository
from onejob.job_verification.models import (
    ApplyDestinationStatus,
    JobVerificationSnapshot,
)
from onejob.job_verification.policy import (
    PublicationPolicy,
    PublicationState,
)
from onejob.job_verification.repository import VerificationRepository
from onejob.persistence.db import Database


NOW = datetime(2026, 8, 21, tzinfo=timezone.utc)


class _SourcePolicy:
    def __init__(self, publication_evidence_allowed):
        self.publication_evidence_allowed = publication_evidence_allowed


def _identity_node(node_id):
    from onejob.company_identity.models import IdentityNode, IdentityNodeType

    return IdentityNode(
        node_id=node_id,
        node_type=IdentityNodeType.ATS_TENANT,
        value="contoh.ats.example",
        created_at=NOW,
    )


def _seed_company_and_job(conn, *, job_id, title):
    conn.execute(
        "INSERT OR IGNORE INTO companies (company_id, normalized_name, display_name) "
        "VALUES ('cmp-1', 'pt contoh', 'PT Contoh')"
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


def _snapshot(job_id, *, freshness="CURRENT", verification_id="verif-1", fp="fp-1"):
    return JobVerificationSnapshot(
        verification_id=verification_id,
        canonical_job_id=job_id,
        canonical_version_id=None,
        identity_snapshot_id="identity-snap-1",
        trust_evaluation_id="trust-1",
        identity_state="VERIFIED",
        trust_classification="AUTOPILOT_ELIGIBLE",
        destination_status=ApplyDestinationStatus.VERIFIED,
        freshness_state=freshness,
        corroboration={"independent_family_count": 1, "appearance_count": 1},
        hard_gate_hits=(),
        unknowns=(),
        evaluated_at=NOW,
        valid_until=NOW + timedelta(days=7),
        input_fingerprint=fp,
        verification_policy_version="job-verification-v1",
    )


@pytest.fixture
def env(tmp_path):
    db = Database(tmp_path / "acceptance.db")
    db.initialize()
    app = FastAPI()
    app.include_router(create_catalog_router(db))
    client = TestClient(app, raise_server_exceptions=False)
    return db, client


def test_authoritative_publish_end_to_end(env):
    db, client = env
    repo = VerificationRepository()
    identity_repo = CompanyIdentityRepository()

    with db.transaction() as conn:
        _seed_company_and_job(conn, job_id="job-1", title="Operator Produksi")
        # verified ATS<->company relationship establishes identity
        identity_repo.insert_node(
            conn,
            _identity_node("node-ats"),
        )
        identity_repo.insert_relationship(
            conn,
            IdentityRelationship(
                relationship_id="rel-1",
                company_id="cmp-1",
                node_id="node-ats",
                relationship_type=IdentityRelationshipType.ATS_FOR,
                status=IdentityRelationshipStatus.VERIFIED,
                confidence=0.99,
                verification_method="MANUAL_EVIDENCE",
                evidence_refs=("evidence-1",),
                first_verified_at=NOW,
                last_verified_at=NOW,
            ),
        )
        snapshot = _snapshot("job-1")
        repo.append(conn, snapshot, evidence_refs=("evidence-1",))

        draft = PublicationPolicy().evaluate(
            snapshot, source_policy=_SourcePolicy(True)
        )
        assert draft.state is PublicationState.PUBLISHABLE
        repo.append_publication_decision(
            conn,
            decision_id="dec-1",
            canonical_job_id="job-1",
            verification_id="verif-1",
            state=draft.state,
            reason_codes=draft.reason_codes,
            decided_at=NOW,
        )

    listing = client.get("/api/catalog/jobs").json()
    ids = {j["canonical_job_id"] for j in listing}
    assert "job-1" in ids

    detail = client.get("/api/catalog/jobs/job-1").json()
    assert detail["verification_summary"]["independent_evidence_family_count"] == 1


def test_official_closure_withdraws_from_catalog(env):
    db, client = env
    repo = VerificationRepository()

    with db.transaction() as conn:
        _seed_company_and_job(conn, job_id="job-1", title="Operator Produksi")
        repo.append(conn, _snapshot("job-1"), evidence_refs=("evidence-1",))
        repo.append_publication_decision(
            conn,
            decision_id="dec-1",
            canonical_job_id="job-1",
            verification_id="verif-1",
            state=PublicationState.PUBLISHABLE,
            reason_codes=("OK",),
            decided_at=NOW,
        )

    assert client.get("/api/catalog/jobs/job-1").status_code == 200

    # Authoritative closure -> new verification -> WITHDRAWN publication head.
    later = NOW + timedelta(days=1)
    with db.transaction() as conn:
        closed_snapshot = _snapshot(
            "job-1", freshness="CLOSED", verification_id="verif-2", fp="fp-2"
        )
        repo.append(conn, closed_snapshot, evidence_refs=("evidence-1",))
        draft = PublicationPolicy().evaluate(
            closed_snapshot, source_policy=_SourcePolicy(True)
        )
        assert draft.state is PublicationState.WITHDRAWN
        repo.append_publication_decision(
            conn,
            decision_id="dec-2",
            canonical_job_id="job-1",
            verification_id="verif-2",
            state=draft.state,
            reason_codes=draft.reason_codes,
            decided_at=later,
        )

    # Active catalog no longer returns it, but history remains internally.
    assert client.get("/api/catalog/jobs/job-1").status_code == 404
    with db.connection() as conn:
        history = conn.execute(
            "SELECT COUNT(*) FROM publication_decisions WHERE canonical_job_id='job-1'"
        ).fetchone()[0]
        snapshots = conn.execute(
            "SELECT COUNT(*) FROM job_verification_snapshots WHERE canonical_job_id='job-1'"
        ).fetchone()[0]
    assert history == 2
    assert snapshots == 2


def test_scam_impersonation_never_reaches_catalog(env):
    db, client = env
    repo = VerificationRepository()

    with db.transaction() as conn:
        _seed_company_and_job(conn, job_id="job-scam", title="Admin Lowongan")
        scam = _snapshot("job-scam", verification_id="verif-scam", fp="fp-scam")
        scam = scam.model_copy(
            update={
                "trust_classification": "ABSOLUTE_BLOCK",
                "hard_gate_hits": ("PAYMENT_REQUIRED",),
            }
        )
        repo.append(conn, scam, evidence_refs=("evidence-scam",))
        draft = PublicationPolicy().evaluate(scam, source_policy=_SourcePolicy(True))
        assert draft.state is PublicationState.REJECTED
        repo.append_publication_decision(
            conn,
            decision_id="dec-scam",
            canonical_job_id="job-scam",
            verification_id="verif-scam",
            state=draft.state,
            reason_codes=draft.reason_codes,
            decided_at=NOW,
        )

    assert client.get("/api/catalog/jobs/job-scam").status_code == 404
    # Raw evidence preserved internally despite rejection.
    with db.connection() as conn:
        preserved = conn.execute(
            "SELECT COUNT(*) FROM job_verification_snapshot_evidence "
            "WHERE verification_id='verif-scam'"
        ).fetchone()[0]
    assert preserved == 1


def test_mirror_lineage_counts_one_independent_family():
    from onejob.job_verification.corroboration import (
        EvidenceAuthority,
        summarize_corroboration,
    )

    summary = summarize_corroboration(
        (
            EvidenceAuthority("e1", "family-ats", "src-ats", authoritative=True),
            EvidenceAuthority("e2", "family-ats", "src-board-a"),
            EvidenceAuthority("e3", "family-ats", "src-board-b"),
        )
    )
    assert summary.appearance_count == 3
    assert summary.independent_family_count == 1


def test_ambiguous_duplicate_does_not_merge():
    from onejob.ingestion.entity_resolution import (
        JobEntityResolver,
        JobIdentityCandidate,
        JobIdentityDisposition,
    )

    def cand(**o):
        base = dict(
            canonical_job_id=None,
            company_id="cmp-1",
            source_id="s",
            external_id="e",
            authoritative_external_id=False,
            title="Operator Produksi",
            location="Bekasi",
            description="Production line operator",
            employment_type=None,
        )
        base.update(o)
        return JobIdentityCandidate(**base)

    decision = JobEntityResolver().resolve(
        incoming=cand(),
        existing=(
            cand(canonical_job_id="job-a", title="Operator Production", description="Production line operator day"),
            cand(canonical_job_id="job-b", description="Production line operator night"),
        ),
    )
    assert decision.disposition is JobIdentityDisposition.AMBIGUOUS
    assert decision.canonical_job_id is None


def test_legacy_jobs_api_still_available():
    from onejob.api import app

    legacy_client = TestClient(app, raise_server_exceptions=False)
    response = legacy_client.get("/api/jobs")
    assert response.status_code == 200
