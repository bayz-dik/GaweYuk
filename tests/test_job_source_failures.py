from datetime import datetime, timezone

import pytest

from onejob.collectors.base import (
    CollectionBatch,
    CollectionStatus,
    CollectionTarget,
)
from onejob.ingestion.models import RawJobObservation, SourceType
from onejob.job_sources.models import AcquisitionMethod
from onejob.persistence.db import Database


NOW = datetime(2026, 8, 21, tzinfo=timezone.utc)


class FixtureCollector:
    source_key = "fixture-ats"
    source_type = SourceType.ATS
    collector_version = "1"
    acquisition_method = AcquisitionMethod.OFFICIAL_API
    target = CollectionTarget(tenant="example")

    def collect(self, target: CollectionTarget) -> CollectionBatch:
        observation = RawJobObservation(
            observation_id="fixture-observation-1",
            source_key=self.source_key,
            source_type=self.source_type,
            collector_version=self.collector_version,
            external_id="job-1001",
            source_url="https://example.test/jobs/1001",
            observed_at=NOW,
            title="Production Operator",
            company_name="PT Example Manufacturing",
            location_text="Bekasi",
            description="Operate production machines safely.",
            source_payload_hash="fixture-hash-1",
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
            warnings=[],
        )


def build_pipeline(db):
    from onejob.ingestion.pipeline import IngestionPipeline

    return IngestionPipeline(db)


def test_verification_crash_does_not_rollback_ingestion(tmp_path, monkeypatch):
    db = Database(tmp_path / "pipeline.db")
    db.initialize()
    pipeline = build_pipeline(db)
    collector = FixtureCollector()

    def crash(*args, **kwargs):
        raise RuntimeError("verification crashed")

    # The post-commit verification hook fails; ingestion must already be
    # durably committed and must not be rolled back.
    monkeypatch.setattr(pipeline, "_verify_after_commit", crash)

    with pytest.raises(RuntimeError, match="verification crashed"):
        pipeline.collect_one(collector, collector.target)

    with db.connection() as conn:
        observation_count = conn.execute(
            "SELECT COUNT(*) FROM raw_job_observations"
        ).fetchone()[0]

    assert observation_count > 0


def test_ingestion_still_produces_canonical_jobs(tmp_path):
    db = Database(tmp_path / "pipeline.db")
    db.initialize()
    pipeline = build_pipeline(db)
    collector = FixtureCollector()

    result = pipeline.collect_one(collector, collector.target)

    assert result.canonical_job_ids
    with db.connection() as conn:
        count = conn.execute("SELECT COUNT(*) FROM canonical_jobs").fetchone()[0]
    assert count == 1


# ---------------------------------------------------------------------------
# Task 17: failure injection, transaction invariants, system-failure semantics
# ---------------------------------------------------------------------------

from datetime import timedelta

from onejob.job_verification.models import (
    ApplyDestinationStatus,
    JobVerificationSnapshot,
)
from onejob.job_verification.policy import PublicationState
from onejob.job_verification.repository import VerificationRepository
from onejob.job_verification.service import (
    JobVerificationService,
    VerificationSystemFailure,
)


class _Store:
    def __init__(self):
        self.crash_identity = False

    def resolve_identity(self, job_id):
        if self.crash_identity:
            raise RuntimeError("resolver down")
        return "UNKNOWN" if job_id == "job-unknown-identity" else "VERIFIED"

    def trust(self, job_id):
        return "AUTOPILOT_ELIGIBLE"

    def destination(self, job_id):
        return ApplyDestinationStatus.VERIFIED

    def evidence_refs(self, job_id):
        return ("evidence-1",)


def _service(tmp_path):
    db = Database(tmp_path / "fail.db")
    db.initialize()
    store = _Store()
    svc = JobVerificationService(db, store=store, now_default=NOW)
    svc._store_obj = store
    return svc


def test_unknown_identity_is_domain_result_not_system_failure(tmp_path):
    service = _service(tmp_path)
    snapshot = service.evaluate("job-unknown-identity", now=NOW)
    assert "COMPANY_IDENTITY" in snapshot.unknowns


def test_identity_resolver_exception_is_system_failure(tmp_path):
    service = _service(tmp_path)
    service._store_obj.crash_identity = True
    with pytest.raises(VerificationSystemFailure):
        service.evaluate("job-1", now=NOW)


def test_publication_transaction_failure_preserves_old_head(tmp_path):
    db = Database(tmp_path / "head.db")
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
        repo.append_publication_decision(
            conn,
            decision_id="dec-1",
            canonical_job_id="job-1",
            verification_id="verif-1",
            state=PublicationState.PUBLISHABLE,
            reason_codes=("OK",),
            decided_at=NOW,
        )

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
    assert head.decision_id == "dec-1"
    assert head.state is PublicationState.PUBLISHABLE


def test_source_registration_db_error_leaves_no_partial_source(tmp_path):
    from onejob.job_sources.models import (
        AcquisitionMethod as AM,
        ComplianceStatus,
        SourceTrustTier,
    )
    from onejob.job_sources.service import JobSourceService
    from onejob.job_sources.repository import SourceRepository

    db = Database(tmp_path / "src.db")
    db.initialize()
    service = JobSourceService(db)

    original_insert = SourceRepository.insert

    def failing_insert(self, conn, source):
        original_insert(self, conn, source)
        raise RuntimeError("db write failed")

    import onejob.job_sources.service as svc_mod

    monkey_repo = SourceRepository()
    service.repo.insert = lambda conn, source: (_ for _ in ()).throw(
        RuntimeError("db write failed")
    )

    with pytest.raises(RuntimeError, match="db write failed"):
        service.register(
            source_id="src-x",
            source_key="x",
            source_type=SourceType.ATS,
            trust_tier=SourceTrustTier.TIER_1_OFFICIAL,
            acquisition_method=AM.OFFICIAL_API,
            primary_domain="x.example",
            country_scope=("ID",),
            compliance_status=ComplianceStatus.ALLOWED,
            verification_policy_version="source-policy-v1",
            now=NOW,
        )

    with db.connection() as conn:
        count = conn.execute("SELECT COUNT(*) FROM job_sources").fetchone()[0]
    assert count == 0
