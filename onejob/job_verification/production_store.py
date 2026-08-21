from __future__ import annotations

import sqlite3
from datetime import datetime

from onejob.company_identity.repository import CompanyIdentityRepository
from onejob.company_identity.resolver import CompanyIdentityResolver
from onejob.ingestion.identity import company_id_for
from onejob.job_verification.freshness import FreshnessState, assess_freshness
from onejob.job_verification.models import ApplyDestinationStatus
from onejob.trust_engine.models import RecruitmentStage
from onejob.trust_engine.repository import TrustRepository


class ProductionVerificationStore:
    """Gathers real persisted verification inputs for a canonical job.

    This is the production bridge consumed by ``JobVerificationService``. It
    reads persisted state (company identity graph, apply-destination assessment,
    freshness, and the latest Trust Engine evaluation) rather than fabricating
    values. It never recomputes trust; it references the existing Trust Engine
    decision, including its hard gates and evaluation identity.
    """

    def __init__(
        self,
        db,
        *,
        destination_status_by_job: dict[str, ApplyDestinationStatus] | None = None,
        closed_jobs: set[str] | None = None,
        now: datetime | None = None,
    ):
        self.db = db
        self.identity_repo = CompanyIdentityRepository()
        self.identity_resolver = CompanyIdentityResolver()
        self.trust_repo = TrustRepository()
        self._destination = destination_status_by_job or {}
        self._closed = closed_jobs or set()
        self._now = now

    def _job(self, conn: sqlite3.Connection, canonical_job_id: str):
        return conn.execute(
            "SELECT * FROM canonical_jobs WHERE canonical_job_id = ?",
            (canonical_job_id,),
        ).fetchone()

    def resolve_identity(self, canonical_job_id: str) -> str:
        with self.db.connection() as conn:
            job = self._job(conn, canonical_job_id)
            if job is None:
                return "UNKNOWN"
            company_id = job["company_id"]
            relationships = tuple(
                self.identity_repo.relationships_for_company(conn, company_id)
            )
        resolution = self.identity_resolver.resolve(
            company_id=company_id,
            claimed_name=job["title"],
            source_domain="",
            relationships=relationships,
        )
        return resolution.state.value

    def trust(self, canonical_job_id: str) -> str:
        decision = self._latest_trust(canonical_job_id)
        if decision is None:
            # No trust evaluation yet is uncertainty, never eligibility.
            return "REVIEW_REQUIRED"
        return decision.classification.value

    def trust_evaluation_id(self, canonical_job_id: str) -> str | None:
        decision = self._latest_trust(canonical_job_id)
        return decision.evaluation_id if decision is not None else None

    def hard_gate_hits(self, canonical_job_id: str) -> tuple[str, ...]:
        decision = self._latest_trust(canonical_job_id)
        if decision is None:
            return ()
        # Only non-overridable gates count as publication hard blocks.
        return tuple(
            gate.gate_code
            for gate in decision.hard_gates
            if gate.override_policy != "REQUIRES_CORROBORATION"
        )

    def destination(self, canonical_job_id: str) -> ApplyDestinationStatus:
        return self._destination.get(
            canonical_job_id, ApplyDestinationStatus.UNKNOWN
        )

    def evidence_refs(self, canonical_job_id: str) -> tuple[str, ...]:
        with self.db.connection() as conn:
            rows = conn.execute(
                "SELECT evidence_family_id FROM job_source_appearances "
                "WHERE canonical_job_id = ?",
                (canonical_job_id,),
            ).fetchall()
        return tuple(sorted({row[0] for row in rows}))

    def corroboration(self, canonical_job_id: str) -> dict:
        with self.db.connection() as conn:
            rows = conn.execute(
                "SELECT evidence_family_id FROM job_source_appearances "
                "WHERE canonical_job_id = ?",
                (canonical_job_id,),
            ).fetchall()
        families = {row[0] for row in rows}
        return {
            "appearance_count": len(rows),
            "independent_family_count": len(families),
        }

    def canonical_version_id(self, canonical_job_id: str) -> str | None:
        with self.db.connection() as conn:
            row = conn.execute(
                "SELECT version_id FROM job_versions WHERE canonical_job_id = ? "
                "ORDER BY version_number DESC LIMIT 1",
                (canonical_job_id,),
            ).fetchone()
        return row[0] if row is not None else None

    def freshness_state(self, canonical_job_id: str) -> str:
        if canonical_job_id in self._closed:
            return FreshnessState.CLOSED.value
        with self.db.connection() as conn:
            job = self._job(conn, canonical_job_id)
        if job is None:
            return FreshnessState.UNKNOWN.value
        if job["lifecycle_state"] == "CLOSED":
            return FreshnessState.CLOSED.value
        assessment = assess_freshness(
            last_authoritative_seen_at=datetime.fromisoformat(job["last_seen_at"]),
            evaluated_at=self._now or datetime.fromisoformat(job["last_seen_at"]),
        )
        return assessment.state.value

    def _latest_trust(self, canonical_job_id: str):
        with self.db.connection() as conn:
            if not self._trust_tables_exist(conn):
                return None
            return self.trust_repo.latest_evaluation(conn, canonical_job_id)

    @staticmethod
    def _trust_tables_exist(conn: sqlite3.Connection) -> bool:
        return (
            conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' "
                "AND name='trust_evaluations'"
            ).fetchone()
            is not None
        )
