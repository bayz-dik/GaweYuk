from __future__ import annotations

import json
import sqlite3

from onejob.catalog.models import (
    PublicApplyDestination,
    PublicJob,
    PublicVerificationSummary,
)


class CatalogRepository:
    """Public catalog reads. PUBLISHABLE filtering happens in SQL.

    The join to ``job_publication_heads`` with ``state = 'PUBLISHABLE'`` is the
    enforcement boundary: non-publishable jobs are never fetched, so review,
    quarantine, and rejected jobs cannot leak through the public API.
    """

    _BASE_SELECT = """
        SELECT
            cj.canonical_job_id,
            cj.title,
            co.display_name AS company,
            cj.location,
            cj.employment_type,
            cj.salary_min,
            cj.salary_max,
            cj.currency,
            cj.lifecycle_state,
            h.updated_at AS catalog_published_at
        FROM job_publication_heads h
        JOIN canonical_jobs cj
            ON cj.canonical_job_id = h.canonical_job_id
        JOIN companies co
            ON co.company_id = cj.company_id
        WHERE h.state = 'PUBLISHABLE'
    """

    def list_publishable(self, conn: sqlite3.Connection) -> list[PublicJob]:
        rows = conn.execute(
            self._BASE_SELECT + " ORDER BY cj.last_seen_at DESC, cj.canonical_job_id"
        ).fetchall()
        return [self._row_to_public_job(conn, row) for row in rows]

    def get_publishable(
        self, conn: sqlite3.Connection, canonical_job_id: str
    ) -> PublicJob | None:
        row = conn.execute(
            self._BASE_SELECT + " AND h.canonical_job_id = ?",
            (canonical_job_id,),
        ).fetchone()
        if row is None:
            return None
        return self._row_to_public_job(conn, row)

    def _verification_summary(
        self, conn: sqlite3.Connection, canonical_job_id: str
    ) -> PublicVerificationSummary:
        head = conn.execute(
            """
            SELECT s.corroboration_json, s.evaluated_at
            FROM job_publication_heads h
            JOIN publication_decisions d ON d.decision_id = h.decision_id
            JOIN job_verification_snapshots s
                ON s.verification_id = d.verification_id
            WHERE h.canonical_job_id = ?
            """,
            (canonical_job_id,),
        ).fetchone()
        if head is None:
            return PublicVerificationSummary()
        corroboration = json.loads(head[0]) if head[0] else {}
        return PublicVerificationSummary(
            checked_at=head[1],
            appearance_count=int(corroboration.get("appearance_count", 0)),
            independent_evidence_family_count=int(
                corroboration.get("independent_family_count", 0)
            ),
        )

    def _apply_destination(
        self, conn: sqlite3.Connection, canonical_job_id: str
    ) -> PublicApplyDestination:
        # Destination status comes from the verification snapshot that
        # authorized the current publishable head. A safe domain is only
        # exposed for VERIFIED/ALLOWED_EXTERNAL; raw/unverified URLs are never
        # returned to the public.
        row = conn.execute(
            """
            SELECT s.destination_status
            FROM job_publication_heads h
            JOIN publication_decisions d ON d.decision_id = h.decision_id
            JOIN job_verification_snapshots s
                ON s.verification_id = d.verification_id
            WHERE h.canonical_job_id = ?
            """,
            (canonical_job_id,),
        ).fetchone()
        status = row[0] if row is not None else "UNKNOWN"

        domain = None
        if status in ("VERIFIED", "ALLOWED_EXTERNAL"):
            appearance = conn.execute(
                """
                SELECT apply_url FROM job_source_appearances
                WHERE canonical_job_id = ? AND apply_url IS NOT NULL
                ORDER BY last_seen_at DESC LIMIT 1
                """,
                (canonical_job_id,),
            ).fetchone()
            if appearance is not None and appearance[0]:
                from urllib.parse import urlsplit

                domain = urlsplit(appearance[0]).hostname

        return PublicApplyDestination(status=status, domain=domain)

    def _row_to_public_job(
        self, conn: sqlite3.Connection, row: sqlite3.Row
    ) -> PublicJob:
        return PublicJob(
            canonical_job_id=row[0],
            title=row[1],
            company=row[2],
            location=row[3],
            employment_type=row[4],
            salary_min=row[5],
            salary_max=row[6],
            currency=row[7],
            lifecycle=row[8],
            catalog_published_at=row[9],
            apply_destination=self._apply_destination(conn, row[0]),
            verification_summary=self._verification_summary(conn, row[0]),
        )
