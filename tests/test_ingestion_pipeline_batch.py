from datetime import datetime, timezone

import pytest

from onejob.collectors.base import (
    CollectionBatch,
    CollectionStatus,
    CollectionTarget,
)
from onejob.ingestion.models import RawJobObservation, SourceType
from onejob.ingestion.pipeline import IngestionPipeline
from onejob.persistence.db import Database


def make_observation(
    *,
    source_key: str,
    external_id: str,
    observation_id: str,
) -> RawJobObservation:
    now = datetime.now(timezone.utc)

    return RawJobObservation(
        observation_id=observation_id,
        source_key=source_key,
        source_type=SourceType.ATS,
        collector_version="1",
        external_id=external_id,
        source_url=f"https://example.test/{source_key}/{external_id}",
        observed_at=now,
        title="Production Operator",
        company_name="PT Example Manufacturing",
        location_text="Bekasi",
        description="Operate production machines safely.",
        salary_min=6000000,
        salary_max=7000000,
        currency="IDR",
        employment_type="Full-time",
        source_payload_hash=f"hash-{observation_id}",
    )


class VariantCollector:
    source_type = SourceType.ATS
    collector_version = "1"

    def __init__(
        self,
        source_key: str,
        external_id: str,
        observation_id: str,
    ):
        self.source_key = source_key
        self.external_id = external_id
        self.observation_id = observation_id

    def collect(self, target):
        now = datetime.now(timezone.utc)

        return CollectionBatch(
            source_key=self.source_key,
            source_type=self.source_type,
            collector_version=self.collector_version,
            target=target,
            started_at=now,
            finished_at=now,
            status=CollectionStatus.SUCCESS,
            observations=[
                make_observation(
                    source_key=self.source_key,
                    external_id=self.external_id,
                    observation_id=self.observation_id,
                )
            ],
            warnings=[],
        )


class TwoObservationCollector:
    source_key = "atomic-fixture"
    source_type = SourceType.ATS
    collector_version = "1"

    def collect(self, target):
        now = datetime.now(timezone.utc)

        return CollectionBatch(
            source_key=self.source_key,
            source_type=self.source_type,
            collector_version=self.collector_version,
            target=target,
            started_at=now,
            finished_at=now,
            status=CollectionStatus.SUCCESS,
            observations=[
                make_observation(
                    source_key=self.source_key,
                    external_id="atomic-1",
                    observation_id="atomic-observation-1",
                ),
                make_observation(
                    source_key=self.source_key,
                    external_id="atomic-2",
                    observation_id="atomic-observation-2",
                ),
            ],
            warnings=[],
        )


def test_collection_transaction_rolls_back_on_mid_batch_failure(
    tmp_path,
):
    db = Database(tmp_path / "atomic.db")
    db.initialize()

    pipeline = IngestionPipeline(db)
    collector = TwoObservationCollector()
    target = CollectionTarget(tenant="example")

    original_insert = pipeline.observations.insert
    calls = 0

    def exploding_insert(conn, observation):
        nonlocal calls
        calls += 1

        result = original_insert(conn, observation)

        if calls == 2:
            raise RuntimeError("forced mid-batch failure")

        return result

    pipeline.observations.insert = exploding_insert

    with pytest.raises(
        RuntimeError,
        match="forced mid-batch failure",
    ):
        pipeline.collect_one(collector, target)

    tables = (
        "raw_job_observations",
        "companies",
        "canonical_jobs",
        "canonical_job_sources",
        "job_versions",
        "job_events",
        "collection_runs",
    )

    with db.connection() as conn:
        for table in tables:
            count = conn.execute(
                f"SELECT COUNT(*) FROM {table}"
            ).fetchone()[0]

            assert count == 0, (
                f"{table} leaked {count} rows after rollback"
            )


def test_collect_many_merges_same_job_across_sources(tmp_path):
    db = Database(tmp_path / "multi-source.db")
    db.initialize()

    pipeline = IngestionPipeline(db)
    target = CollectionTarget(tenant="example")

    results = pipeline.collect_many(
        [
            (
                VariantCollector(
                    "greenhouse",
                    "gh-1001",
                    "obs-greenhouse-1001",
                ),
                target,
            ),
            (
                VariantCollector(
                    "lever",
                    "lever-9001",
                    "obs-lever-9001",
                ),
                target,
            ),
        ]
    )

    assert len(results) == 2

    assert (
        results[0].canonical_job_ids
        == results[1].canonical_job_ids
    )

    assert len(results[0].canonical_job_ids) == 1

    with db.connection() as conn:
        canonical_jobs = conn.execute(
            "SELECT COUNT(*) FROM canonical_jobs"
        ).fetchone()[0]

        source_links = conn.execute(
            "SELECT COUNT(*) FROM canonical_job_sources"
        ).fetchone()[0]

        versions = conn.execute(
            "SELECT COUNT(*) FROM job_versions"
        ).fetchone()[0]

        events = conn.execute(
            "SELECT COUNT(*) FROM job_events"
        ).fetchone()[0]

        runs = conn.execute(
            "SELECT COUNT(*) FROM collection_runs"
        ).fetchone()[0]

    assert canonical_jobs == 1
    assert source_links == 2

    # Source noise must not create a fake material version.
    assert versions == 1
    assert events == 1

    assert runs == 2
