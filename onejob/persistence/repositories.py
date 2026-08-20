from __future__ import annotations

import json
import sqlite3

from onejob.ingestion.models import RawJobObservation


class ObservationRepository:
    def insert(
        self,
        conn: sqlite3.Connection,
        observation: RawJobObservation,
    ) -> bool:
        conn.execute(
            """
            INSERT OR IGNORE INTO sources (
                source_key,
                source_type,
                collector_version
            )
            VALUES (?, ?, ?)
            """,
            (
                observation.source_key,
                observation.source_type.value,
                observation.collector_version,
            ),
        )

        cursor = conn.execute(
            """
            INSERT OR IGNORE INTO raw_job_observations (
                observation_id,
                source_key,
                source_type,
                collector_version,
                external_id,
                source_url,
                canonical_hint_url,
                observed_at,
                published_at,
                updated_at,
                expires_at,
                title,
                company_name,
                location_text,
                description,
                salary_min,
                salary_max,
                currency,
                employment_type,
                skills_json,
                contact_email,
                source_payload_hash,
                raw_payload_reference
            )
            VALUES (
                ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
            )
            """,
            (
                observation.observation_id,
                observation.source_key,
                observation.source_type.value,
                observation.collector_version,
                observation.external_id,
                observation.source_url,
                observation.canonical_hint_url,
                observation.observed_at.isoformat(),
                observation.published_at.isoformat()
                if observation.published_at else None,
                observation.updated_at.isoformat()
                if observation.updated_at else None,
                observation.expires_at.isoformat()
                if observation.expires_at else None,
                observation.title,
                observation.company_name,
                observation.location_text,
                observation.description,
                observation.salary_min,
                observation.salary_max,
                observation.currency,
                observation.employment_type,
                json.dumps(observation.skills),
                observation.contact_email,
                observation.source_payload_hash,
                observation.raw_payload_reference,
            ),
        )

        return cursor.rowcount == 1

    def list_by_source(
        self,
        conn: sqlite3.Connection,
        source_key: str,
    ) -> list[RawJobObservation]:
        rows = conn.execute(
            """
            SELECT *
            FROM raw_job_observations
            WHERE source_key = ?
            ORDER BY observed_at ASC
            """,
            (source_key,),
        ).fetchall()

        result = []

        for row in rows:
            data = dict(row)
            data["skills"] = json.loads(data.pop("skills_json"))
            result.append(RawJobObservation.model_validate(data))

        return result
