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
