from __future__ import annotations

from onejob.catalog.models import PublicJob, PublicVerificationSummary
from onejob.catalog.repository import CatalogRepository
from onejob.persistence.db import Database


class CatalogService:
    """Read boundary for the public catalog. Exposes publishable jobs only."""

    def __init__(self, db: Database, *, repository: CatalogRepository | None = None):
        self.db = db
        self.repo = repository or CatalogRepository()

    def list_jobs(self) -> list[PublicJob]:
        with self.db.connection() as conn:
            return self.repo.list_publishable(conn)

    def get_job(self, canonical_job_id: str) -> PublicJob | None:
        with self.db.connection() as conn:
            return self.repo.get_publishable(conn, canonical_job_id)

    def get_verification(
        self, canonical_job_id: str
    ) -> PublicVerificationSummary | None:
        job = self.get_job(canonical_job_id)
        if job is None:
            return None
        return job.verification_summary
