from datetime import datetime, timedelta, timezone
import json

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


class ConsensusCollector:
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
            source_payload_hash=(
                f"hash-{observation_id}"
            ),
        )

    def collect(self, target):
        observed_at = self.observation.observed_at

        return CollectionBatch(
            source_key=self.source_key,
            source_type=self.source_type,
            collector_version=self.collector_version,
            target=target,
            started_at=observed_at,
            finished_at=observed_at,
            status=CollectionStatus.SUCCESS,
            observations=[self.observation],
            warnings=[],
        )


def test_pipeline_does_not_use_last_source_wins(tmp_path):
    db = Database(tmp_path / "consensus.db")
    db.initialize()

    pipeline = IngestionPipeline(db)
    target = CollectionTarget(tenant="example")

    now = datetime.now(timezone.utc)

    official = ConsensusCollector(
        source_key="company-career",
        source_type=SourceType.COMPANY_CAREER,
        external_id="official-1",
        observation_id="official-observation-1",
        salary_min=6000000,
        observed_at=now,
    )

    portal = ConsensusCollector(
        source_key="job-portal",
        source_type=SourceType.JOB_PORTAL,
        external_id="portal-1",
        observation_id="portal-observation-1",
        salary_min=6500000,
        observed_at=now + timedelta(seconds=1),
    )

    first = pipeline.collect_one(official, target)
    second = pipeline.collect_one(portal, target)

    assert (
        first.canonical_job_ids
        == second.canonical_job_ids
    )

    canonical_job_id = first.canonical_job_ids[0]

    with db.connection() as conn:
        job = conn.execute(
            """
            SELECT salary_min
            FROM canonical_jobs
            WHERE canonical_job_id = ?
            """,
            (canonical_job_id,),
        ).fetchone()

        versions = conn.execute(
            """
            SELECT COUNT(*)
            FROM job_versions
            WHERE canonical_job_id = ?
            """,
            (canonical_job_id,),
        ).fetchone()[0]

        events = conn.execute(
            """
            SELECT event_type
            FROM job_events
            WHERE canonical_job_id = ?
            ORDER BY rowid
            """,
            (canonical_job_id,),
        ).fetchall()

        consensus = conn.execute(
            """
            SELECT
                selected_value_json,
                conflicting_evidence_ids_json
            FROM field_consensus
            WHERE canonical_job_id = ?
              AND field_name = 'salary_min'
            """,
            (canonical_job_id,),
        ).fetchone()

        evidence_count = conn.execute(
            """
            SELECT COUNT(*)
            FROM field_evidence
            WHERE canonical_job_id = ?
              AND field_name = 'salary_min'
            """,
            (canonical_job_id,),
        ).fetchone()[0]

    # Official company source remains canonical.
    assert job[0] == 6000000

    # Weaker conflicting source must NOT fabricate
    # a material job mutation.
    assert versions == 1
    assert [row[0] for row in events] == [
        "JOB_DISCOVERED"
    ]

    assert evidence_count == 2
    assert json.loads(consensus[0]) == 6000000
    assert len(json.loads(consensus[1])) == 1

    assert second.new_count == 0
    assert second.unchanged_count == 1


def test_official_listing_update_changes_consensus_and_version(
    tmp_path,
):
    db = Database(tmp_path / "consensus-update.db")
    db.initialize()

    pipeline = IngestionPipeline(db)
    target = CollectionTarget(tenant="example")

    now = datetime.now(timezone.utc)

    old = ConsensusCollector(
        source_key="company-career",
        source_type=SourceType.COMPANY_CAREER,
        external_id="same-official-job",
        observation_id="official-old",
        salary_min=6000000,
        observed_at=now,
    )

    new = ConsensusCollector(
        source_key="company-career",
        source_type=SourceType.COMPANY_CAREER,
        external_id="same-official-job",
        observation_id="official-new",
        salary_min=6200000,
        observed_at=now + timedelta(minutes=5),
    )

    first = pipeline.collect_one(old, target)
    second = pipeline.collect_one(new, target)

    assert (
        first.canonical_job_ids
        == second.canonical_job_ids
    )

    canonical_job_id = first.canonical_job_ids[0]

    with db.connection() as conn:
        job = conn.execute(
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
                changed_fields_json
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

    assert job[0] == 6200000
    assert len(versions) == 2
    assert versions[0][0] == 1
    assert versions[1][0] == 2

    assert "salary_min" in json.loads(
        versions[1][1]
    )

    assert [row[0] for row in events] == [
        "JOB_DISCOVERED",
        "JOB_CHANGED",
    ]
