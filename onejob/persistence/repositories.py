from __future__ import annotations

import json
import sqlite3

from onejob.ingestion.models import JobEvent, JobVersion, RawJobObservation


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


class JobHistoryRepository:
    def append_version(
        self,
        conn: sqlite3.Connection,
        version: JobVersion,
    ) -> None:
        conn.execute(
            """
            INSERT INTO job_versions (
                version_id,
                canonical_job_id,
                version_number,
                valid_from,
                valid_to,
                content_hash,
                changed_fields_json,
                field_snapshot_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                version.version_id,
                version.canonical_job_id,
                version.version_number,
                version.valid_from.isoformat(),
                version.valid_to.isoformat()
                if version.valid_to else None,
                version.content_hash,
                json.dumps(version.changed_fields),
                json.dumps(version.field_snapshot),
            ),
        )

    def latest_version(
        self,
        conn: sqlite3.Connection,
        canonical_job_id: str,
    ) -> JobVersion | None:
        row = conn.execute(
            """
            SELECT *
            FROM job_versions
            WHERE canonical_job_id = ?
            ORDER BY version_number DESC
            LIMIT 1
            """,
            (canonical_job_id,),
        ).fetchone()

        if row is None:
            return None

        return self._version_from_row(row)

    def close_previous_version(
        self,
        conn: sqlite3.Connection,
        canonical_job_id: str,
        valid_to,
    ) -> None:
        conn.execute(
            """
            UPDATE job_versions
            SET valid_to = ?
            WHERE canonical_job_id = ?
              AND valid_to IS NULL
            """,
            (
                valid_to.isoformat(),
                canonical_job_id,
            ),
        )

    def list_versions(
        self,
        conn: sqlite3.Connection,
        canonical_job_id: str,
    ) -> list[JobVersion]:
        rows = conn.execute(
            """
            SELECT *
            FROM job_versions
            WHERE canonical_job_id = ?
            ORDER BY version_number ASC
            """,
            (canonical_job_id,),
        ).fetchall()

        return [
            self._version_from_row(row)
            for row in rows
        ]

    def append_event(
        self,
        conn: sqlite3.Connection,
        event: JobEvent,
    ) -> None:
        conn.execute(
            """
            INSERT INTO job_events (
                event_id,
                canonical_job_id,
                event_type,
                occurred_at,
                payload_json
            )
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                event.event_id,
                event.canonical_job_id,
                event.event_type.value,
                event.occurred_at.isoformat(),
                json.dumps(event.payload),
            ),
        )

    def list_events(
        self,
        conn: sqlite3.Connection,
        canonical_job_id: str,
    ) -> list[JobEvent]:
        rows = conn.execute(
            """
            SELECT *
            FROM job_events
            WHERE canonical_job_id = ?
            ORDER BY occurred_at ASC
            """,
            (canonical_job_id,),
        ).fetchall()

        result = []

        for row in rows:
            data = dict(row)
            data["payload"] = json.loads(
                data.pop("payload_json")
            )
            result.append(JobEvent.model_validate(data))

        return result

    @staticmethod
    def _version_from_row(row) -> JobVersion:
        data = dict(row)

        data["changed_fields"] = json.loads(
            data.pop("changed_fields_json")
        )
        data["field_snapshot"] = json.loads(
            data.pop("field_snapshot_json")
        )

        return JobVersion.model_validate(data)
