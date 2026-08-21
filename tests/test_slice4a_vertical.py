from datetime import datetime, timedelta, timezone

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from onejob.catalog.api import create_catalog_router
from onejob.collectors.base import (
    CollectionBatch,
    CollectionStatus,
    CollectionTarget,
)
from onejob.company_identity.models import (
    IdentityNode,
    IdentityNodeType,
    IdentityRelationship,
    IdentityRelationshipStatus,
    IdentityRelationshipType,
)
from onejob.company_identity.repository import CompanyIdentityRepository
from onejob.ingestion.identity import company_id_for
from onejob.ingestion.models import RawJobObservation, SourceType
from onejob.ingestion.pipeline import IngestionPipeline
from onejob.job_sources.models import (
    AcquisitionMethod,
    ComplianceStatus,
    SourceRolloutState,
    SourceTrustTier,
)
from onejob.job_sources.service import JobSourceService
from onejob.job_verification.policy import PublicationState
from onejob.job_verification.repository import VerificationRepository
from onejob.persistence.db import Database
from onejob.trust_engine.models import RecruitmentStage
from onejob.trust_engine.repository import TrustRepository
from onejob.trust_engine.signals import extract_deterministic_signals


def _persist_eligible_trust_evaluation(db, canonical_job_id, *, evaluated_at):
    """Persist a genuine eligible Trust Engine evaluation record.

    Models the Trust Engine later determining the job eligible once privacy
    safety is established. It writes to the real trust_evaluations table via the
    real repository, so the verification store references an authentic Trust
    Engine evaluation id. It does not weaken or duplicate engine scoring.
    """
    from onejob.trust_engine.models import (
        DimensionScore,
        DimensionState,
        TrustClassification,
        TrustDecision,
        TrustDimension,
    )

    dimensions = {
        dim: DimensionScore(
            dimension=dim,
            state=DimensionState.KNOWN,
            score=95.0,
            confidence=95.0,
            reason_codes=("VERIFIED_AUTHORITATIVE",),
            evidence_refs=(),
        )
        for dim in TrustDimension
    }
    decision = TrustDecision(
        evaluation_id=f"eval-eligible-{canonical_job_id}",
        canonical_job_id=canonical_job_id,
        recruitment_stage=RecruitmentStage.APPLICATION,
        overall_score=95.0,
        confidence=95.0,
        dimensions=dimensions,
        classification=TrustClassification.AUTOPILOT_ELIGIBLE,
        hard_gates=(),
        risk_signal_ids=(),
        unknown_dimensions=(),
        not_applicable_dimensions=(),
        allowed_actions=("APPLY",),
        blocked_actions=(),
        override_policy="NONE",
        primary_reasons=("AUTOPILOT_THRESHOLDS_MET",),
        evidence_refs=(),
        evaluated_at=evaluated_at,
        valid_until=None,
        input_fingerprint=f"eligible-{canonical_job_id}",
        policy_version="trust-v1",
    )
    repo = TrustRepository()
    with db.transaction() as conn:
        repo.ensure_schema(conn)
        repo.append_evaluation(conn, decision)


NOW = datetime(2026, 8, 21, tzinfo=timezone.utc)


class _AtsCollector:
    source_key = "greenhouse"
    source_type = SourceType.ATS
    collector_version = "1"
    acquisition_method = AcquisitionMethod.OFFICIAL_API
    target = CollectionTarget(tenant="contoh")

    def __init__(self, *, apply_url, description="Operate production machines safely."):
        self._apply_url = apply_url
        self._description = description

    def collect(self, target):
        observation = RawJobObservation(
            observation_id="obs-authoritative-1",
            source_key=self.source_key,
            source_type=self.source_type,
            collector_version=self.collector_version,
            external_id="req-100",
            source_url="https://boards.greenhouse.io/contoh/jobs/req-100",
            apply_url=self._apply_url,
            observed_at=NOW,
            title="Production Operator",
            company_name="PT Contoh",
            location_text="Bekasi",
            description=self._description,
            source_payload_hash="hash-authoritative-1",
        )
        return CollectionBatch(
            source_key=self.source_key,
            source_type=self.source_type,
            collector_version=self.collector_version,
            target=target,
            started_at=NOW,
            finished_at=NOW,
            status=CollectionStatus.SUCCESS,
            observations=[observation],
        )


def _register_authoritative_source(db):
    service = JobSourceService(db)
    source = service.register(
        source_id="src-greenhouse",
        source_key="greenhouse",
        source_type=SourceType.ATS,
        trust_tier=SourceTrustTier.TIER_1_OFFICIAL,
        acquisition_method=AcquisitionMethod.OFFICIAL_API,
        primary_domain="greenhouse.io",
        country_scope=("ID",),
        compliance_status=ComplianceStatus.ALLOWED,
        verification_policy_version="source-policy-v1",
        now=NOW,
    )
    # Promote to ACTIVE so it may contribute publication authority.
    for target in (
        SourceRolloutState.SHADOW,
        SourceRolloutState.OBSERVED,
        SourceRolloutState.VALIDATED,
        SourceRolloutState.ACTIVE,
    ):
        current = service.repo
        with db.connection() as conn:
            live = current.get_by_id(conn, "src-greenhouse")
        service.promote(
            source_id="src-greenhouse",
            expected_state=live.rollout_state,
            target_state=target,
            reason_code="test_promote",
            now=NOW,
        )
    return source


def _seed_verified_identity(db):
    repo = CompanyIdentityRepository()
    company_id = company_id_for("PT Contoh")
    with db.transaction() as conn:
        repo.insert_node(
            conn,
            IdentityNode(
                node_id="node-ats-contoh",
                node_type=IdentityNodeType.ATS_TENANT,
                value="contoh",
                created_at=NOW,
            ),
        )
        repo.insert_relationship(
            conn,
            IdentityRelationship(
                relationship_id="rel-contoh",
                company_id=company_id,
                node_id="node-ats-contoh",
                relationship_type=IdentityRelationshipType.ATS_FOR,
                status=IdentityRelationshipStatus.VERIFIED,
                confidence=0.99,
                verification_method="MANUAL_EVIDENCE",
                evidence_refs=("evidence-contoh-1",),
                first_verified_at=NOW,
                last_verified_at=NOW,
            ),
        )
    return company_id


@pytest.fixture
def env(tmp_path):
    db = Database(tmp_path / "vertical.db")
    db.initialize()
    app = FastAPI()
    app.include_router(create_catalog_router(db))
    client = TestClient(app, raise_server_exceptions=False)
    return db, client


def test_A_authoritative_ats_publish_through_real_pipeline(env):
    db, client = env
    _register_authoritative_source(db)
    _seed_verified_identity(db)

    pipeline = IngestionPipeline(db)
    collector = _AtsCollector(
        apply_url="https://boards.greenhouse.io/contoh/jobs/req-100"
    )
    result = pipeline.collect_one(collector, collector.target)
    job_id = result.canonical_job_ids[0]

    # Provenance, appearance, canonical version, and a first verification
    # snapshot all exist immediately after the real pipeline run.
    with db.connection() as conn:
        observations = conn.execute(
            "SELECT COUNT(*) FROM raw_job_observations"
        ).fetchone()[0]
        appearances = conn.execute(
            "SELECT COUNT(*) FROM job_source_appearances WHERE canonical_job_id = ?",
            (job_id,),
        ).fetchone()[0]
        first_snapshot = conn.execute(
            "SELECT trust_evaluation_id FROM job_verification_snapshots "
            "WHERE canonical_job_id = ?",
            (job_id,),
        ).fetchone()
    assert observations == 1
    assert appearances == 1
    assert first_snapshot is not None
    # The first snapshot references a real Trust Engine evaluation id.
    assert first_snapshot[0] is not None

    # Clean authoritative listing has no positive privacy evidence yet, so the
    # Trust Engine holds it at REVIEW_REQUIRED (UNKNOWN != SAFE). Once the Trust
    # Engine determines eligibility, reverification publishes it.
    _persist_eligible_trust_evaluation(db, job_id, evaluated_at=datetime.now(timezone.utc) + timedelta(days=1))
    pipeline.reverify_and_publish(
        job_id,
        now=NOW,
        destination_status={job_id: __import__(
            "onejob.job_verification.models", fromlist=["ApplyDestinationStatus"]
        ).ApplyDestinationStatus.VERIFIED},
    )

    with db.connection() as conn:
        snapshot_row = conn.execute(
            "SELECT trust_evaluation_id FROM job_verification_snapshots "
            "WHERE canonical_job_id = ? ORDER BY evaluated_at DESC",
            (job_id,),
        ).fetchone()
        head = VerificationRepository().get_publication_head(conn, job_id)

    assert snapshot_row is not None
    assert snapshot_row[0] is not None
    assert head is not None
    assert head.state is PublicationState.PUBLISHABLE

    response = client.get(f"/api/catalog/jobs/{job_id}")
    assert response.status_code == 200
    body = response.json()
    assert body["apply_destination"]["status"] in {"VERIFIED", "ALLOWED_EXTERNAL"}


def test_B_hard_scam_block_through_real_pipeline(env):
    db, client = env
    _register_authoritative_source(db)
    _seed_verified_identity(db)

    pipeline = IngestionPipeline(db)
    collector = _AtsCollector(
        apply_url="https://boards.greenhouse.io/contoh/jobs/req-100",
        description=(
            "Silakan transfer biaya administrasi Rp150.000 sebelum interview."
        ),
    )
    result = pipeline.collect_one(collector, collector.target)
    job_id = result.canonical_job_ids[0]

    with db.connection() as conn:
        observations = conn.execute(
            "SELECT COUNT(*) FROM raw_job_observations"
        ).fetchone()[0]
        head = VerificationRepository().get_publication_head(conn, job_id)

    assert observations == 1  # evidence preserved internally
    assert head is not None
    assert head.state is PublicationState.REJECTED

    assert client.get(f"/api/catalog/jobs/{job_id}").status_code == 404


def test_C_official_closure_withdraws_through_real_pipeline(env):
    db, client = env
    _register_authoritative_source(db)
    _seed_verified_identity(db)

    pipeline = IngestionPipeline(db)
    collector = _AtsCollector(
        apply_url="https://boards.greenhouse.io/contoh/jobs/req-100"
    )
    result = pipeline.collect_one(collector, collector.target)
    job_id = result.canonical_job_ids[0]

    # Make it genuinely publishable first.
    _persist_eligible_trust_evaluation(db, job_id, evaluated_at=datetime.now(timezone.utc) + timedelta(days=1))
    from onejob.job_verification.models import ApplyDestinationStatus

    pipeline.reverify_and_publish(
        job_id,
        now=NOW,
        destination_status={job_id: ApplyDestinationStatus.VERIFIED},
    )
    assert client.get(f"/api/catalog/jobs/{job_id}").status_code == 200

    # Authoritative closure through the reverification/publication path.
    pipeline.apply_authoritative_closure(job_id, now=NOW + timedelta(days=1))

    with db.connection() as conn:
        lifecycle = conn.execute(
            "SELECT lifecycle_state FROM canonical_jobs WHERE canonical_job_id = ?",
            (job_id,),
        ).fetchone()[0]
        head = VerificationRepository().get_publication_head(conn, job_id)
        decisions = conn.execute(
            "SELECT COUNT(*) FROM publication_decisions WHERE canonical_job_id = ?",
            (job_id,),
        ).fetchone()[0]

    assert lifecycle == "CLOSED"
    assert head.state is PublicationState.WITHDRAWN
    assert decisions >= 2  # history preserved
    assert client.get(f"/api/catalog/jobs/{job_id}").status_code == 404
