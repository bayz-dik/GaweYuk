from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import inspect
import sqlite3

from onejob.ingestion.pipeline import IngestionPipeline
from onejob.trust_engine.models import (
    RecruitmentStage,
    SignalLevel,
    TrustClassification,
)
from onejob.trust_engine.repository import TrustRepository
from onejob.trust_engine.service import TrustEngineService
from onejob.trust_engine.signals import (
    extract_deterministic_signals,
)


NOW = datetime(
    2026,
    8,
    20,
    12,
    0,
    tzinfo=timezone.utc,
)


class TinyDB:
    def __init__(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")

        self.conn.execute(
            """
            CREATE TABLE canonical_jobs (
                canonical_job_id TEXT PRIMARY KEY,
                company_id TEXT,
                title TEXT,
                company_name TEXT,
                location TEXT,
                description TEXT,
                updated_at TEXT
            )
            """
        )

        self.conn.execute(
            """
            INSERT INTO canonical_jobs (
                canonical_job_id,
                company_id,
                title,
                company_name,
                location,
                description,
                updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "job-1",
                "company-1",
                "Backend Engineer",
                "Example Corp",
                "Jakarta",
                "Build reliable systems",
                NOW.isoformat(),
            ),
        )

        self.conn.execute(
            """
            CREATE TABLE canonical_job_sources (
                canonical_job_id TEXT NOT NULL,
                source_key TEXT NOT NULL
            )
            """
        )

        self.conn.execute(
            """
            INSERT INTO canonical_job_sources (
                canonical_job_id,
                source_key
            )
            VALUES ('job-1', 'greenhouse:example')
            """
        )

        self.conn.execute(
            """
            CREATE TABLE field_evidence (
                evidence_id TEXT PRIMARY KEY,
                canonical_job_id TEXT NOT NULL
            )
            """
        )

        self.conn.execute(
            """
            INSERT INTO field_evidence (
                evidence_id,
                canonical_job_id
            )
            VALUES ('evidence-1', 'job-1')
            """
        )

        self.conn.commit()

    @contextmanager
    def transaction(self):
        try:
            self.conn.execute("BEGIN")
            yield self.conn
            self.conn.commit()
        except Exception:
            self.conn.rollback()
            raise


def test_shadow_service_creates_evaluation():
    db = TinyDB()
    service = TrustEngineService(db)

    result = service.shadow_evaluate_after_ingestion(
        ["job-1"],
        now=NOW,
    )

    assert len(result) == 1

    with db.transaction() as conn:
        row = conn.execute(
            """
            SELECT classification, policy_version
            FROM trust_evaluations
            WHERE canonical_job_id = 'job-1'
            """
        ).fetchone()

    assert row is not None
    assert row["policy_version"] == "trust-v1"


def test_repeated_identical_shadow_evaluation_is_deduplicated():
    db = TinyDB()
    service = TrustEngineService(db)

    service.shadow_evaluate_after_ingestion(
        ["job-1"],
        now=NOW,
    )

    service.shadow_evaluate_after_ingestion(
        ["job-1"],
        now=NOW + timedelta(minutes=1),
    )

    with db.transaction() as conn:
        count = conn.execute(
            """
            SELECT COUNT(*) AS count
            FROM trust_evaluations
            WHERE canonical_job_id = 'job-1'
            """
        ).fetchone()["count"]

    assert count == 1


def test_new_l3_signal_creates_blocking_snapshot():
    db = TinyDB()
    service = TrustEngineService(db)
    repo = TrustRepository()

    service.shadow_evaluate_after_ingestion(
        ["job-1"],
        now=NOW,
    )

    signals = extract_deterministic_signals(
        canonical_job_id="job-1",
        text=(
            "Silakan transfer biaya administrasi "
            "Rp150.000 sebelum interview."
        ),
        stage=RecruitmentStage.APPLICATION,
        evidence_ref="observation:risk-1",
        observed_at=NOW + timedelta(minutes=10),
    )

    signal = next(
        item
        for item in signals
        if item.signal_type == "RECRUITMENT_PAYMENT"
    )

    assert signal.level is SignalLevel.L3

    with db.transaction() as conn:
        repo.ensure_schema(conn)
        repo.upsert_signal(conn, signal)

    service.shadow_evaluate_after_ingestion(
        ["job-1"],
        stage=RecruitmentStage.APPLICATION,
        now=NOW + timedelta(minutes=11),
    )

    with db.transaction() as conn:
        latest = repo.latest_evaluation(
            conn,
            "job-1",
        )

        count = conn.execute(
            """
            SELECT COUNT(*) AS count
            FROM trust_evaluations
            WHERE canonical_job_id = 'job-1'
            """
        ).fetchone()["count"]

    assert count == 2
    assert latest is not None
    assert (
        latest.classification
        is TrustClassification.AUTOMATION_BLOCKED
    )


def test_signal_resolution_creates_new_snapshot_without_rewriting_history():
    db = TinyDB()
    service = TrustEngineService(db)
    repo = TrustRepository()

    signals = extract_deterministic_signals(
        canonical_job_id="job-1",
        text="Bayar deposit training Rp200.000.",
        stage=RecruitmentStage.APPLICATION,
        evidence_ref="observation:risk-2",
        observed_at=NOW,
    )

    signal = signals[0]

    with db.transaction() as conn:
        repo.ensure_schema(conn)
        repo.upsert_signal(conn, signal)

    service.shadow_evaluate_after_ingestion(
        ["job-1"],
        stage=RecruitmentStage.APPLICATION,
        now=NOW,
    )

    with db.transaction() as conn:
        repo.resolve_signal(
            conn,
            signal.signal_id,
            resolved_at=NOW + timedelta(minutes=10),
            reason="FALSE_POSITIVE_CONFIRMED",
        )

    service.shadow_evaluate_after_ingestion(
        ["job-1"],
        stage=RecruitmentStage.APPLICATION,
        now=NOW + timedelta(minutes=11),
    )

    with db.transaction() as conn:
        rows = conn.execute(
            """
            SELECT classification
            FROM trust_evaluations
            WHERE canonical_job_id = 'job-1'
            ORDER BY evaluated_at
            """
        ).fetchall()

    assert len(rows) == 2
    assert rows[0]["classification"] == (
        "AUTOMATION_BLOCKED"
    )
    assert rows[1]["classification"] != (
        "AUTOMATION_BLOCKED"
    )


def test_ingestion_pipeline_owns_trust_service():
    pipeline = IngestionPipeline(object())

    assert isinstance(
        pipeline.trust,
        TrustEngineService,
    )


def test_collect_one_contains_post_transaction_shadow_hook():
    source = inspect.getsource(
        IngestionPipeline.collect_one
    )

    assert "shadow_evaluate_after_ingestion" in source
    assert "result.canonical_job_ids" in source


def test_shadow_failure_does_not_raise_into_ingestion_caller():
    class BrokenDB:
        @contextmanager
        def transaction(self):
            raise sqlite3.OperationalError(
                "simulated trust storage failure"
            )
            yield

    service = TrustEngineService(BrokenDB())

    result = service.shadow_evaluate_after_ingestion(
        ["job-1"],
        now=NOW,
    )

    assert result == []
