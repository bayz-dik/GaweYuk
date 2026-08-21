from __future__ import annotations

import hashlib
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class EvidenceFamily:
    evidence_family_id: str
    origin_source_id: str | None
    origin_external_id: str | None
    lineage_kind: str
    created_at: datetime


@dataclass(frozen=True)
class JobSourceAppearance:
    appearance_id: str
    canonical_job_id: str
    source_id: str
    external_id: str
    source_url: str
    apply_url: str | None
    evidence_family_id: str
    first_seen_at: datetime
    last_seen_at: datetime
    latest_observation_id: str
    appearance_state: str


def derive_evidence_family_id(
    *,
    source_id: str,
    external_id: str,
    upstream_family_hint: str | None,
) -> str:
    """Return the evidence-family id for a source appearance.

    A mirror that knows its upstream origin (``upstream_family_hint``) inherits
    that family so syndicated copies do not inflate independent evidence
    counts. Otherwise the family is derived deterministically from the
    origin source + external id, so re-fetching the same listing reuses it.
    """
    if upstream_family_hint is not None:
        return upstream_family_hint
    raw = f"family|{source_id}|{external_id}".encode()
    return hashlib.sha256(raw).hexdigest()


def _dt(value: datetime) -> str:
    return value.isoformat()


class AppearanceRepository:
    """Persistence for evidence families and source appearances.

    Appearances are updated in place for ``last_seen``/latest observation
    pointer, but raw observations themselves are never rewritten.
    """

    def _ensure_family(
        self,
        conn: sqlite3.Connection,
        *,
        evidence_family_id: str,
        origin_source_id: str,
        origin_external_id: str,
        lineage_kind: str,
        created_at: datetime,
    ) -> None:
        conn.execute(
            """
            INSERT OR IGNORE INTO evidence_families (
                evidence_family_id, origin_source_id, origin_external_id,
                lineage_kind, created_at
            )
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                evidence_family_id,
                origin_source_id,
                origin_external_id,
                lineage_kind,
                _dt(created_at),
            ),
        )

    def upsert_seen(
        self,
        conn: sqlite3.Connection,
        *,
        canonical_job_id: str,
        source_id: str,
        external_id: str,
        source_url: str,
        apply_url: str | None,
        evidence_family_id: str,
        observation_id: str,
        seen_at: datetime,
        lineage_kind: str = "ORIGIN",
    ) -> JobSourceAppearance:
        self._ensure_family(
            conn,
            evidence_family_id=evidence_family_id,
            origin_source_id=source_id,
            origin_external_id=external_id,
            lineage_kind=lineage_kind,
            created_at=seen_at,
        )

        existing = conn.execute(
            """
            SELECT appearance_id, first_seen_at
            FROM job_source_appearances
            WHERE source_id = ? AND external_id = ?
            """,
            (source_id, external_id),
        ).fetchone()

        if existing is None:
            appearance_id = uuid.uuid4().hex
            conn.execute(
                """
                INSERT INTO job_source_appearances (
                    appearance_id, canonical_job_id, source_id, external_id,
                    source_url, apply_url, evidence_family_id, first_seen_at,
                    last_seen_at, latest_observation_id, appearance_state
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    appearance_id,
                    canonical_job_id,
                    source_id,
                    external_id,
                    source_url,
                    apply_url,
                    evidence_family_id,
                    _dt(seen_at),
                    _dt(seen_at),
                    observation_id,
                    "ACTIVE",
                ),
            )
            first_seen = seen_at
        else:
            appearance_id = existing[0]
            first_seen = datetime.fromisoformat(existing[1])
            conn.execute(
                """
                UPDATE job_source_appearances
                SET last_seen_at = ?, latest_observation_id = ?,
                    apply_url = ?, source_url = ?
                WHERE appearance_id = ?
                """,
                (
                    _dt(seen_at),
                    observation_id,
                    apply_url,
                    source_url,
                    appearance_id,
                ),
            )

        return JobSourceAppearance(
            appearance_id=appearance_id,
            canonical_job_id=canonical_job_id,
            source_id=source_id,
            external_id=external_id,
            source_url=source_url,
            apply_url=apply_url,
            evidence_family_id=evidence_family_id,
            first_seen_at=first_seen,
            last_seen_at=seen_at,
            latest_observation_id=observation_id,
            appearance_state="ACTIVE",
        )

    def list_for_job(
        self, conn: sqlite3.Connection, canonical_job_id: str
    ) -> list[JobSourceAppearance]:
        rows = conn.execute(
            """
            SELECT appearance_id, canonical_job_id, source_id, external_id,
                   source_url, apply_url, evidence_family_id, first_seen_at,
                   last_seen_at, latest_observation_id, appearance_state
            FROM job_source_appearances
            WHERE canonical_job_id = ?
            ORDER BY first_seen_at, appearance_id
            """,
            (canonical_job_id,),
        ).fetchall()
        return [
            JobSourceAppearance(
                appearance_id=row[0],
                canonical_job_id=row[1],
                source_id=row[2],
                external_id=row[3],
                source_url=row[4],
                apply_url=row[5],
                evidence_family_id=row[6],
                first_seen_at=datetime.fromisoformat(row[7]),
                last_seen_at=datetime.fromisoformat(row[8]),
                latest_observation_id=row[9],
                appearance_state=row[10],
            )
            for row in rows
        ]
