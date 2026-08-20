from datetime import datetime, timedelta, timezone
import json

from onejob.collectors.base import (
    CollectionBatch,
    CollectionStatus,
    CollectionTarget,
)
from onejob.ingestion.models import RawJobObservation, SourceType
from onejob.ingestion.pipeline import IngestionPipeline
from onejob.persistence.db import Database


class StaticCollector:
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
        return CollectionBatch(
            source_key=self.source_key,
            source_type=self.source_type,
            collector_version=self.collector_version,
            target=target,
            started_at=self.observation.observed_at,
            finished_at=self.observation.observed_at,
            status=CollectionStatus.SUCCESS,
            observations=[self.observation],
            warnings=[],
        )


def test_stronger_source_wins_but_conflict_is_retained(
    tmp_path,
):
    from onejob.ingestion.evidence_store import (
        EvidenceConsensusStore,
    )

    db = Database(tmp_path / "evidence.db")
    db.initialize()

    pipeline = IngestionPipeline(db)
    target = CollectionTarget(tenant="example")

    now = datetime.now(timezone.utc)

    official = StaticCollector(
        source_key="company-career",
        source_type=SourceType.COMPANY_CAREER,
        external_id="job-1",
        observation_id="official-obs-1",
        salary_min=6000000,
        observed_at=now,
    )

    portal = StaticCollector(
        source_key="job-portal",
        source_type=SourceType.JOB_PORTAL,
        external_id="portal-9001",
        observation_id="portal-obs-1",
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

    store = EvidenceConsensusStore()

    with db.transaction() as conn:
        store.record_observation(
            conn,
            canonical_job_id,
            official.observation,
        )

        result = store.record_observation(
            conn,
            canonical_job_id,
            portal.observation,
        )

    salary = result["salary_min"]

    assert salary.selected_value == 6000000
    assert len(salary.primary_evidence_ids) == 1
    assert len(salary.conflicting_evidence_ids) == 1
    assert salary.confidence < 1.0

    with db.connection() as conn:
        evidence_count = conn.execute(
            """
            SELECT COUNT(*)
            FROM field_evidence
            WHERE canonical_job_id = ?
              AND field_name = 'salary_min'
            """,
            (canonical_job_id,),
        ).fetchone()[0]

        row = conn.execute(
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

    assert evidence_count == 2
    assert json.loads(row[0]) == 6000000
    assert len(json.loads(row[1])) == 1


def test_latest_evidence_supersedes_same_listing_family(
    tmp_path,
):
    from onejob.ingestion.evidence_store import (
        EvidenceConsensusStore,
    )

    db = Database(tmp_path / "supersede.db")
    db.initialize()

    pipeline = IngestionPipeline(db)
    target = CollectionTarget(tenant="example")

    now = datetime.now(timezone.utc)

    old = StaticCollector(
        source_key="company-career",
        source_type=SourceType.COMPANY_CAREER,
        external_id="same-job",
        observation_id="same-job-old",
        salary_min=6000000,
        observed_at=now,
    )

    new = StaticCollector(
        source_key="company-career",
        source_type=SourceType.COMPANY_CAREER,
        external_id="same-job",
        observation_id="same-job-new",
        salary_min=6200000,
        observed_at=now + timedelta(minutes=5),
    )

    first = pipeline.collect_one(old, target)
    second = pipeline.collect_one(new, target)

    canonical_job_id = first.canonical_job_ids[0]

    assert (
        first.canonical_job_ids
        == second.canonical_job_ids
    )

    store = EvidenceConsensusStore()

    with db.transaction() as conn:
        store.record_observation(
            conn,
            canonical_job_id,
            old.observation,
        )

        result = store.record_observation(
            conn,
            canonical_job_id,
            new.observation,
        )

    salary = result["salary_min"]

    # Bukti terbaru dari listing yang sama menggantikan
    # bukti lamanya sebagai current evidence.
    assert salary.selected_value == 6200000
    assert salary.conflicting_evidence_ids == []

    with db.connection() as conn:
        rows = conn.execute(
            """
            SELECT independence_status
            FROM field_evidence
            WHERE canonical_job_id = ?
              AND field_name = 'salary_min'
            ORDER BY observed_at
            """,
            (canonical_job_id,),
        ).fetchall()

    # Ledger tetap menyimpan sejarah keduanya.
    assert len(rows) == 2
    assert rows[0][0] == "INDEPENDENT"
    assert rows[1][0] == "RELATED"
