from datetime import datetime, timezone

from onejob.collectors.base import (
    CollectionBatch,
    CollectionStatus,
    CollectionTarget,
)
from onejob.ingestion.models import RawJobObservation, SourceType


class FixtureCollector:
    source_key = "fixture-ats"
    source_type = SourceType.ATS
    collector_version = "1"

    def collect(self, target: CollectionTarget) -> CollectionBatch:
        now = datetime.now(timezone.utc)

        observation = RawJobObservation(
            observation_id="fixture-observation-1",
            source_key=self.source_key,
            source_type=self.source_type,
            collector_version=self.collector_version,
            external_id="job-1001",
            source_url="https://example.test/jobs/1001",
            observed_at=now,
            title="Production Operator",
            company_name="PT Example Manufacturing",
            location_text="Bekasi",
            description="Operate production machines safely.",
            salary_min=6000000,
            salary_max=7000000,
            currency="IDR",
            employment_type="Full-time",
            source_payload_hash="fixture-hash-1",
        )

        return CollectionBatch(
            source_key=self.source_key,
            source_type=self.source_type,
            collector_version=self.collector_version,
            target=target,
            started_at=now,
            finished_at=now,
            status=CollectionStatus.SUCCESS,
            observations=[observation],
            warnings=[],
        )


def test_repeated_same_collection_is_idempotent(tmp_path):
    from onejob.ingestion.pipeline import IngestionPipeline
    from onejob.persistence.db import Database

    db = Database(tmp_path / "pipeline.db")
    db.initialize()

    pipeline = IngestionPipeline(db)
    collector = FixtureCollector()
    target = CollectionTarget(tenant="example")

    first = pipeline.collect_one(collector, target)
    second = pipeline.collect_one(collector, target)

    assert first.new_count == 1
    assert second.new_count == 0
    assert second.unchanged_count == 1

    assert first.canonical_job_ids == second.canonical_job_ids
    assert len(first.canonical_job_ids) == 1


class ChangingFixtureCollector:
    source_key = "fixture-ats"
    source_type = SourceType.ATS
    collector_version = "1"

    def __init__(self):
        self.calls = 0

    def collect(self, target: CollectionTarget) -> CollectionBatch:
        self.calls += 1
        now = datetime.now(timezone.utc)

        salary_min = (
            6000000
            if self.calls == 1
            else 6500000
        )

        observation = RawJobObservation(
            observation_id=f"fixture-change-{self.calls}",
            source_key=self.source_key,
            source_type=self.source_type,
            collector_version=self.collector_version,
            external_id="job-2001",
            source_url="https://example.test/jobs/2001",
            observed_at=now,
            title="Production Operator",
            company_name="PT Example Manufacturing",
            location_text="Bekasi",
            description="Operate production machines safely.",
            salary_min=salary_min,
            salary_max=7000000,
            currency="IDR",
            employment_type="Full-time",
            source_payload_hash=f"fixture-change-hash-{self.calls}",
        )

        return CollectionBatch(
            source_key=self.source_key,
            source_type=self.source_type,
            collector_version=self.collector_version,
            target=target,
            started_at=now,
            finished_at=now,
            status=CollectionStatus.SUCCESS,
            observations=[observation],
            warnings=[],
        )


def test_material_change_updates_same_job_and_creates_version_event(
    tmp_path,
):
    from onejob.ingestion.pipeline import IngestionPipeline
    from onejob.persistence.db import Database

    db = Database(tmp_path / "pipeline-change.db")
    db.initialize()

    pipeline = IngestionPipeline(db)
    collector = ChangingFixtureCollector()
    target = CollectionTarget(tenant="example")

    first = pipeline.collect_one(collector, target)
    second = pipeline.collect_one(collector, target)

    assert first.canonical_job_ids == second.canonical_job_ids

    canonical_job_id = first.canonical_job_ids[0]

    with db.connection() as conn:
        canonical = conn.execute(
            """
            SELECT salary_min
            FROM canonical_jobs
            WHERE canonical_job_id = ?
            """,
            (canonical_job_id,),
        ).fetchone()

        versions = conn.execute(
            """
            SELECT
                version_number,
                changed_fields_json,
                field_snapshot_json
            FROM job_versions
            WHERE canonical_job_id = ?
            ORDER BY version_number
            """,
            (canonical_job_id,),
        ).fetchall()

        events = conn.execute(
            """
            SELECT event_type
            FROM job_events
            WHERE canonical_job_id = ?
            ORDER BY rowid
            """,
            (canonical_job_id,),
        ).fetchall()

    assert canonical[0] == 6500000

    assert len(versions) == 2
    assert versions[0][0] == 1
    assert versions[1][0] == 2

    import json

    changed_fields = json.loads(versions[1][1])
    latest_snapshot = json.loads(versions[1][2])

    assert "salary_min" in changed_fields
    assert latest_snapshot["salary_min"] == 6500000

    assert [row[0] for row in events] == [
        "JOB_DISCOVERED",
        "JOB_CHANGED",
    ]


def test_each_collection_persists_run_metrics(tmp_path):
    from onejob.ingestion.pipeline import IngestionPipeline
    from onejob.persistence.db import Database

    db = Database(tmp_path / "pipeline-runs.db")
    db.initialize()

    pipeline = IngestionPipeline(db)
    collector = FixtureCollector()
    target = CollectionTarget(tenant="example")

    pipeline.collect_one(collector, target)
    pipeline.collect_one(collector, target)

    with db.connection() as conn:
        rows = conn.execute(
            """
            SELECT
                run_id,
                source_key,
                status,
                observations_count,
                new_count,
                changed_count,
                unchanged_count,
                warnings_count
            FROM collection_runs
            ORDER BY started_at, rowid
            """
        ).fetchall()

    assert len(rows) == 2

    first, second = rows

    assert first[0] != second[0]

    assert first[1] == "fixture-ats"
    assert first[2] == "SUCCESS"
    assert first[3] == 1
    assert first[4] == 1
    assert first[5] == 0
    assert first[6] == 0
    assert first[7] == 0

    assert second[1] == "fixture-ats"
    assert second[2] == "SUCCESS"
    assert second[3] == 1
    assert second[4] == 0
    assert second[5] == 0
    assert second[6] == 1
    assert second[7] == 0
