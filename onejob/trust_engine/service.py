from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
import sqlite3
from uuid import uuid4

from .models import (
    DimensionState,
    RecruitmentStage,
    TrustClassification,
    TrustDimension,
)
from .policy import DEFAULT_POLICY, evaluate_policy
from .recalculation import (
    TrustEventType,
    input_fingerprint,
    should_recalculate,
)
from .repository import TrustRepository
from .scoring import (
    DimensionInput,
    TrustInputs,
    aggregate_trust,
    score_dimensions,
)


class TrustEngineService:
    def __init__(
        self,
        db,
        *,
        evaluation_ttl: timedelta = timedelta(hours=1),
    ):
        self.db = db
        self.repo = TrustRepository()
        self.evaluation_ttl = evaluation_ttl

    def _table_exists(
        self,
        conn: sqlite3.Connection,
        name: str,
    ) -> bool:
        return (
            conn.execute(
                """
                SELECT 1
                FROM sqlite_master
                WHERE type = 'table'
                  AND name = ?
                """,
                (name,),
            ).fetchone()
            is not None
        )

    def _columns(
        self,
        conn: sqlite3.Connection,
        table: str,
    ) -> set[str]:
        if not self._table_exists(conn, table):
            return set()

        return {
            row["name"]
            for row in conn.execute(
                f"PRAGMA table_info({table})"
            ).fetchall()
        }

    def _job_row(
        self,
        conn: sqlite3.Connection,
        canonical_job_id: str,
    ):
        if not self._table_exists(
            conn,
            "canonical_jobs",
        ):
            return None

        return conn.execute(
            """
            SELECT *
            FROM canonical_jobs
            WHERE canonical_job_id = ?
            """,
            (canonical_job_id,),
        ).fetchone()

    def _evidence_refs(
        self,
        conn: sqlite3.Connection,
        canonical_job_id: str,
    ) -> tuple[str, ...]:
        columns = self._columns(
            conn,
            "field_evidence",
        )

        if not {
            "canonical_job_id",
            "evidence_id",
        } <= columns:
            return ()

        rows = conn.execute(
            """
            SELECT evidence_id
            FROM field_evidence
            WHERE canonical_job_id = ?
            ORDER BY evidence_id
            """,
            (canonical_job_id,),
        ).fetchall()

        return tuple(
            row["evidence_id"]
            for row in rows
        )

    def _source_count(
        self,
        conn: sqlite3.Connection,
        canonical_job_id: str,
    ) -> int | None:
        columns = self._columns(
            conn,
            "canonical_job_sources",
        )

        if "canonical_job_id" not in columns:
            return None

        row = conn.execute(
            """
            SELECT COUNT(*) AS count
            FROM canonical_job_sources
            WHERE canonical_job_id = ?
            """,
            (canonical_job_id,),
        ).fetchone()

        return int(row["count"])

    def _open_conflict_count(
        self,
        conn: sqlite3.Connection,
        canonical_job_id: str,
    ) -> int | None:
        for table in (
            "field_conflict_records",
            "field_conflicts",
        ):
            columns = self._columns(
                conn,
                table,
            )

            if "canonical_job_id" not in columns:
                continue

            if "status" in columns:
                row = conn.execute(
                    f"""
                    SELECT COUNT(*) AS count
                    FROM {table}
                    WHERE canonical_job_id = ?
                      AND status = 'OPEN'
                    """,
                    (canonical_job_id,),
                ).fetchone()
            else:
                row = conn.execute(
                    f"""
                    SELECT COUNT(*) AS count
                    FROM {table}
                    WHERE canonical_job_id = ?
                    """,
                    (canonical_job_id,),
                ).fetchone()

            return int(row["count"])

        return None

    def _dimension_inputs(
        self,
        conn: sqlite3.Connection,
        canonical_job_id: str,
        stage: RecruitmentStage,
        signals,
    ) -> TrustInputs:
        row = self._job_row(
            conn,
            canonical_job_id,
        )

        if row is None:
            raise KeyError(
                f"canonical job not found: "
                f"{canonical_job_id}"
            )

        keys = set(row.keys())

        # -----------------------------
        # Company Identity
        # -----------------------------

        company_value = None

        for key in (
            "company_id",
            "company_name",
            "company",
        ):
            if key in keys and row[key]:
                company_value = row[key]
                break

        if company_value:
            company_identity = DimensionInput(
                state=DimensionState.KNOWN,
                score=90.0,
                confidence=90.0,
                reason_codes=(
                    "CANONICAL_COMPANY_PRESENT",
                ),
                evidence_refs=(),
            )
        else:
            company_identity = DimensionInput(
                state=DimensionState.UNKNOWN,
                score=None,
                confidence=None,
                reason_codes=(
                    "COMPANY_IDENTITY_UNVERIFIED",
                ),
            )

        # -----------------------------
        # Source Credibility
        # -----------------------------

        source_count = self._source_count(
            conn,
            canonical_job_id,
        )

        if source_count is None:
            source_credibility = DimensionInput(
                state=DimensionState.UNKNOWN,
                score=None,
                confidence=None,
                reason_codes=(
                    "SOURCE_PROVENANCE_UNAVAILABLE",
                ),
            )
        elif source_count <= 0:
            source_credibility = DimensionInput(
                state=DimensionState.UNKNOWN,
                score=None,
                confidence=None,
                reason_codes=(
                    "NO_LINKED_SOURCE",
                ),
            )
        else:
            score = min(
                98.0,
                75.0 + min(source_count, 4) * 5.0,
            )

            source_credibility = DimensionInput(
                state=DimensionState.KNOWN,
                score=score,
                confidence=min(
                    98.0,
                    75.0 + source_count * 5.0,
                ),
                reason_codes=(
                    "LINKED_SOURCE_PRESENT",
                ),
            )

        # -----------------------------
        # Listing Integrity
        # -----------------------------

        candidates = (
            "title",
            "company_name",
            "location",
            "description",
        )

        available = [
            key
            for key in candidates
            if key in keys
        ]

        present = [
            key
            for key in available
            if row[key]
        ]

        if not available:
            listing_integrity = DimensionInput(
                state=DimensionState.UNKNOWN,
                score=None,
                confidence=None,
                reason_codes=(
                    "LISTING_FIELDS_UNAVAILABLE",
                ),
            )
        else:
            ratio = (
                len(present)
                / len(available)
            )

            listing_integrity = DimensionInput(
                state=DimensionState.KNOWN,
                score=round(
                    50.0 + ratio * 45.0,
                    2,
                ),
                confidence=round(
                    60.0 + ratio * 35.0,
                    2,
                ),
                reason_codes=(
                    "CANONICAL_LISTING_COVERAGE",
                ),
            )

        # -----------------------------
        # Evidence Consensus
        # -----------------------------

        conflicts = self._open_conflict_count(
            conn,
            canonical_job_id,
        )

        if conflicts is None:
            consensus = DimensionInput(
                state=DimensionState.UNKNOWN,
                score=None,
                confidence=None,
                reason_codes=(
                    "CONSENSUS_LEDGER_UNAVAILABLE",
                ),
            )
        elif conflicts == 0:
            consensus = DimensionInput(
                state=DimensionState.KNOWN,
                score=95.0,
                confidence=90.0,
                reason_codes=(
                    "NO_OPEN_CONFLICTS",
                ),
            )
        else:
            consensus = DimensionInput(
                state=DimensionState.KNOWN,
                score=max(
                    30.0,
                    80.0 - conflicts * 15.0,
                ),
                confidence=85.0,
                reason_codes=(
                    "OPEN_EVIDENCE_CONFLICT",
                ),
            )

        # -----------------------------
        # Recruiter Integrity
        # -----------------------------

        if stage in {
            RecruitmentStage.DISCOVERY,
            RecruitmentStage.APPLICATION,
        }:
            recruiter = DimensionInput(
                state=DimensionState.NOT_APPLICABLE,
                score=None,
                confidence=None,
                reason_codes=(
                    "RECRUITER_NOT_APPLICABLE_YET",
                ),
            )
        else:
            recruiter = DimensionInput(
                state=DimensionState.UNKNOWN,
                score=None,
                confidence=None,
                reason_codes=(
                    "RECRUITER_EVIDENCE_MISSING",
                ),
            )

        # -----------------------------
        # Privacy Safety
        # -----------------------------

        active_types = {
            signal.signal_type
            for signal in signals
        }

        if active_types:
            privacy = DimensionInput(
                state=DimensionState.KNOWN,
                score=20.0,
                confidence=95.0,
                reason_codes=tuple(
                    sorted(active_types)
                ),
            )
        else:
            # Absence of detected red flags is not proof
            # of safety. Keep this UNKNOWN until enough
            # contextual privacy evidence exists.
            privacy = DimensionInput(
                state=DimensionState.UNKNOWN,
                score=None,
                confidence=None,
                reason_codes=(
                    "PRIVACY_CONTEXT_INSUFFICIENT",
                ),
            )

        # -----------------------------
        # Freshness
        # -----------------------------

        freshness_value = None

        for key in (
            "updated_at",
            "last_seen_at",
            "seen_at",
        ):
            if key in keys and row[key]:
                freshness_value = row[key]
                break

        if freshness_value:
            freshness = DimensionInput(
                state=DimensionState.KNOWN,
                score=85.0,
                confidence=80.0,
                reason_codes=(
                    "RECENT_CANONICAL_TIMESTAMP_PRESENT",
                ),
            )
        else:
            freshness = DimensionInput(
                state=DimensionState.UNKNOWN,
                score=None,
                confidence=None,
                reason_codes=(
                    "FRESHNESS_TIMESTAMP_MISSING",
                ),
            )

        evidence_refs = self._evidence_refs(
            conn,
            canonical_job_id,
        )

        def attach(item: DimensionInput):
            return DimensionInput(
                state=item.state,
                score=item.score,
                confidence=item.confidence,
                reason_codes=item.reason_codes,
                evidence_refs=evidence_refs,
            )

        return TrustInputs(
            dimensions={
                TrustDimension.COMPANY_IDENTITY:
                    attach(company_identity),
                TrustDimension.SOURCE_CREDIBILITY:
                    attach(source_credibility),
                TrustDimension.LISTING_INTEGRITY:
                    attach(listing_integrity),
                TrustDimension.EVIDENCE_CONSENSUS:
                    attach(consensus),
                TrustDimension.RECRUITER_INTEGRITY:
                    attach(recruiter),
                TrustDimension.PRIVACY_SAFETY:
                    attach(privacy),
                TrustDimension.FRESHNESS:
                    attach(freshness),
            }
        )

    def evaluate_job(
        self,
        conn: sqlite3.Connection,
        canonical_job_id: str,
        *,
        stage: RecruitmentStage,
        now: datetime,
    ):
        self.repo.ensure_schema(conn)

        job = self._job_row(
            conn,
            canonical_job_id,
        )

        if job is None:
            return None

        signals = self.repo.list_active_signals(
            conn,
            canonical_job_id,
        )

        evidence_refs = self._evidence_refs(
            conn,
            canonical_job_id,
        )

        fingerprint = input_fingerprint(
            canonical_job_id=canonical_job_id,
            recruitment_stage=stage,
            policy_version=DEFAULT_POLICY.version,
            evidence_refs=evidence_refs,
            active_signal_ids=tuple(
                signal.signal_id
                for signal in signals
            ),
            source_health={},
        )

        previous = self.repo.latest_evaluation(
            conn,
            canonical_job_id,
        )

        if (
            previous is not None
            and not should_recalculate(
                previous_input_fingerprint=(
                    previous.input_fingerprint
                ),
                new_input_fingerprint=fingerprint,
            )
        ):
            self.repo.record_attempt(
                conn,
                attempt_id=f"attempt-{uuid4().hex}",
                canonical_job_id=canonical_job_id,
                status="SKIPPED_UNCHANGED",
                error_code=None,
                input_fingerprint=fingerprint,
                started_at=now,
                finished_at=now,
            )

            return None

        inputs = self._dimension_inputs(
            conn,
            canonical_job_id,
            stage,
            signals,
        )

        dimensions = score_dimensions(
            inputs
        )

        overall, confidence = aggregate_trust(
            dimensions
        )

        previous_classification = (
            previous.classification
            if previous is not None
            else None
        )

        decision = evaluate_policy(
            canonical_job_id=canonical_job_id,
            recruitment_stage=stage,
            overall_score=overall,
            confidence=confidence,
            dimensions=dimensions,
            signals=signals,
            evaluated_at=now,
            input_fingerprint=fingerprint,
            previous_classification=(
                previous_classification
            ),
        )

        decision = replace(
            decision,
            valid_until=(
                now + self.evaluation_ttl
            ),
        )

        self.repo.append_evaluation(
            conn,
            decision,
        )

        self.repo.record_attempt(
            conn,
            attempt_id=f"attempt-{uuid4().hex}",
            canonical_job_id=canonical_job_id,
            status="SUCCESS",
            error_code=None,
            input_fingerprint=fingerprint,
            started_at=now,
            finished_at=now,
        )

        return decision

    def shadow_evaluate_after_ingestion(
        self,
        canonical_job_ids,
        *,
        stage: RecruitmentStage = RecruitmentStage.DISCOVERY,
        now: datetime | None = None,
    ):
        if now is None:
            now = datetime.now(timezone.utc)

        results = []

        for canonical_job_id in sorted(
            set(canonical_job_ids)
        ):
            try:
                with self.db.transaction() as conn:
                    decision = self.evaluate_job(
                        conn,
                        canonical_job_id,
                        stage=stage,
                        now=now,
                    )

                    if decision is not None:
                        results.append(decision)

            except Exception as exc:
                # Shadow Mode MUST NOT break successful
                # ingestion. Failure is uncertainty,
                # never fraud evidence.
                try:
                    with self.db.transaction() as conn:
                        self.repo.ensure_schema(conn)

                        self.repo.record_attempt(
                            conn,
                            attempt_id=(
                                f"attempt-{uuid4().hex}"
                            ),
                            canonical_job_id=(
                                canonical_job_id
                            ),
                            status="FAILED",
                            error_code=(
                                type(exc).__name__
                            ),
                            input_fingerprint=None,
                            started_at=now,
                            finished_at=now,
                        )
                except Exception:
                    pass

        return results
