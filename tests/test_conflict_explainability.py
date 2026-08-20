from datetime import datetime, timedelta, timezone

from onejob.collectors.base import (
    CollectionBatch,
    CollectionStatus,
    CollectionTarget,
)
from onejob.ingestion.models import (
    RawJobObservation,
    SourceType,
)
from onejob.ingestion.pipeline import IngestionPipeline
from onejob.persistence.db import Database


class ExplainCollector:
    collector_version = "1"

    def __init__(
        self,
        *,
        source_key,
        source_type,
        external_id,
        observation_id,
        salary_min,
        observed_at,
    ):
        self.source_key = source_key
        self.source_type = source_type

        self.observation = RawJobObservation(
            observation_id=observation_id,
            source_key=source_key,
            source_type=source_type,
            collector_version=self.collector_version,
            external_id=external_id,
            source_url=(
                f"https://example.test/"
                f"{source_key}/{external_id}"
            ),
            observed_at=observed_at,
            title="Production Operator",
            company_name="PT Example Manufacturing",
            location_text="Bekasi",
            description=(
                "Operate production machines safely."
            ),
            salary_min=salary_min,
            salary_max=7000000,
            currency="IDR",
            employment_type="Full-time",
            source_payload_hash=f"hash-{observation_id}",
        )

    def collect(self, target):
        at = self.observation.observed_at

        return CollectionBatch(
            source_key=self.source_key,
            source_type=self.source_type,
            collector_version=self.collector_version,
            target=target,
            started_at=at,
            finished_at=at,
            status=CollectionStatus.SUCCESS,
            observations=[self.observation],
            warnings=[],
        )


def test_conflict_is_persisted_and_explainable(tmp_path):
    from onejob.ingestion.explainability import (
        ConflictExplainabilityStore,
    )

    db = Database(tmp_path / "explain.db")
    db.initialize()

    pipeline = IngestionPipeline(db)
    target = CollectionTarget(tenant="example")

    now = datetime.now(timezone.utc)

    official = ExplainCollector(
        source_key="company-career",
        source_type=SourceType.COMPANY_CAREER,
        external_id="official-job",
        observation_id="official-1",
        salary_min=6000000,
        observed_at=now,
    )

    portal = ExplainCollector(
        source_key="job-portal",
        source_type=SourceType.JOB_PORTAL,
        external_id="portal-job",
        observation_id="portal-1",
        salary_min=6500000,
        observed_at=now + timedelta(seconds=1),
    )

    first = pipeline.collect_one(official, target)
    pipeline.collect_one(portal, target)

    canonical_job_id = first.canonical_job_ids[0]

    store = ConflictExplainabilityStore()

    with db.connection() as conn:
        explanation = store.explain_field(
            conn,
            canonical_job_id,
            "salary_min",
        )

        conflict = conn.execute(
            """
            SELECT status
            FROM field_conflict_records
            WHERE canonical_job_id = ?
              AND field_name = 'salary_min'
            """,
            (canonical_job_id,),
        ).fetchone()

    assert conflict is not None
    assert conflict[0] == "OPEN"

    assert explanation["status"] == "OPEN"
    assert explanation["selected_value"] == 6000000
    assert explanation["confidence"] < 1.0

    primary_sources = {
        item["source_key"]
        for item in explanation["primary_evidence"]
    }

    conflict_sources = {
        item["source_key"]
        for item in explanation["conflicting_evidence"]
    }

    assert "company-career" in primary_sources
    assert "job-portal" in conflict_sources

    assert explanation["resolution_reason"]


def test_conflict_resolves_when_sources_converge(tmp_path):
    from onejob.ingestion.explainability import (
        ConflictExplainabilityStore,
    )

    db = Database(tmp_path / "resolve.db")
    db.initialize()

    pipeline = IngestionPipeline(db)
    target = CollectionTarget(tenant="example")

    now = datetime.now(timezone.utc)

    official_old = ExplainCollector(
        source_key="company-career",
        source_type=SourceType.COMPANY_CAREER,
        external_id="official-job",
        observation_id="official-old",
        salary_min=6000000,
        observed_at=now,
    )

    portal = ExplainCollector(
        source_key="job-portal",
        source_type=SourceType.JOB_PORTAL,
        external_id="portal-job",
        observation_id="portal-1",
        salary_min=6500000,
        observed_at=now + timedelta(seconds=1),
    )

    official_new = ExplainCollector(
        source_key="company-career",
        source_type=SourceType.COMPANY_CAREER,
        external_id="official-job",
        observation_id="official-new",
        salary_min=6500000,
        observed_at=now + timedelta(minutes=5),
    )

    first = pipeline.collect_one(
        official_old,
        target,
    )

    pipeline.collect_one(
        portal,
        target,
    )

    pipeline.collect_one(
        official_new,
        target,
    )

    canonical_job_id = first.canonical_job_ids[0]

    store = ConflictExplainabilityStore()

    with db.connection() as conn:
        row = conn.execute(
            """
            SELECT
                status,
                resolved_at
            FROM field_conflict_records
            WHERE canonical_job_id = ?
              AND field_name = 'salary_min'
            """,
            (canonical_job_id,),
        ).fetchone()

        explanation = store.explain_field(
            conn,
            canonical_job_id,
            "salary_min",
        )

    assert row is not None
    assert row[0] == "RESOLVED"
    assert row[1] is not None

    assert explanation["status"] == "RESOLVED"
    assert explanation["selected_value"] == 6500000
    assert explanation["conflicting_evidence"] == []
