from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field

from onejob.ingestion.identity import (
    company_id_for,
    job_identity_key,
)
from onejob.ingestion.lifecycle import (
    diff_material_fields,
    material_snapshot,
)
from onejob.persistence.repositories import ObservationRepository


def _normalize(value: str) -> str:
    return " ".join(value.casefold().split())


def _json(data) -> str:
    return json.dumps(
        data,
        sort_keys=True,
        separators=(",", ":"),
    )


def _stable_id(*parts: object) -> str:
    raw = "|".join(str(part) for part in parts).encode()
    return hashlib.sha256(raw).hexdigest()


@dataclass
class IngestionResult:
    new_count: int = 0
    unchanged_count: int = 0
    canonical_job_ids: list[str] = field(default_factory=list)


class IngestionPipeline:
    def __init__(self, db):
        self.db = db
        self.observations = ObservationRepository()

    def collect_one(self, collector, target) -> IngestionResult:
        batch = collector.collect(target)
        result = IngestionResult()

        with self.db.transaction() as conn:
            for observation in batch.observations:
                self.observations.insert(
                    conn,
                    observation,
                )

                normalized_company = _normalize(
                    observation.company_name
                )
                normalized_title = _normalize(
                    observation.title
                )
                normalized_location = _normalize(
                    observation.location_text
                )

                company_id = company_id_for(
                    observation.company_name
                )

                conn.execute(
                    """
                    INSERT OR IGNORE INTO companies (
                        company_id,
                        normalized_name,
                        display_name
                    )
                    VALUES (?, ?, ?)
                    """,
                    (
                        company_id,
                        normalized_company,
                        observation.company_name,
                    ),
                )

                canonical_job_id = job_identity_key(
                    company_id,
                    normalized_title,
                    normalized_location,
                )

                existing = conn.execute(
                    """
                    SELECT canonical_job_id
                    FROM canonical_jobs
                    WHERE canonical_job_id = ?
                    """,
                    (canonical_job_id,),
                ).fetchone()

                seen_at = observation.observed_at.isoformat()

                snapshot = material_snapshot(
                    observation.model_dump()
                )
                snapshot_json = _json(snapshot)
                content_hash = hashlib.sha256(
                    snapshot_json.encode()
                ).hexdigest()

                if existing is None:
                    conn.execute(
                        """
                        INSERT INTO canonical_jobs (
                            canonical_job_id,
                            company_id,
                            title,
                            normalized_title,
                            location,
                            normalized_location,
                            description,
                            salary_min,
                            salary_max,
                            currency,
                            employment_type,
                            contact_email,
                            lifecycle_state,
                            first_seen_at,
                            last_seen_at,
                            active_status_confidence
                        )
                        VALUES (
                            ?, ?, ?, ?, ?, ?, ?, ?,
                            ?, ?, ?, ?, ?, ?, ?, ?
                        )
                        """,
                        (
                            canonical_job_id,
                            company_id,
                            observation.title,
                            normalized_title,
                            observation.location_text,
                            normalized_location,
                            observation.description,
                            observation.salary_min,
                            observation.salary_max,
                            observation.currency,
                            observation.employment_type,
                            observation.contact_email,
                            "ACTIVE",
                            seen_at,
                            seen_at,
                            1.0,
                        ),
                    )

                    version_id = _stable_id(
                        canonical_job_id,
                        1,
                        content_hash,
                    )

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
                            version_id,
                            canonical_job_id,
                            1,
                            seen_at,
                            None,
                            content_hash,
                            _json([]),
                            snapshot_json,
                        ),
                    )

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
                            _stable_id(
                                canonical_job_id,
                                "JOB_DISCOVERED",
                                1,
                                content_hash,
                            ),
                            canonical_job_id,
                            "JOB_DISCOVERED",
                            seen_at,
                            _json({}),
                        ),
                    )

                    result.new_count += 1

                else:
                    latest = conn.execute(
                        """
                        SELECT
                            version_id,
                            version_number,
                            field_snapshot_json
                        FROM job_versions
                        WHERE canonical_job_id = ?
                        ORDER BY version_number DESC
                        LIMIT 1
                        """,
                        (canonical_job_id,),
                    ).fetchone()

                    old_snapshot = (
                        json.loads(latest[2])
                        if latest is not None
                        else {}
                    )

                    changed_fields = diff_material_fields(
                        old_snapshot,
                        snapshot,
                    )

                    if changed_fields:
                        conn.execute(
                            """
                            UPDATE canonical_jobs
                            SET
                                title = ?,
                                normalized_title = ?,
                                location = ?,
                                normalized_location = ?,
                                description = ?,
                                salary_min = ?,
                                salary_max = ?,
                                currency = ?,
                                employment_type = ?,
                                contact_email = ?,
                                last_seen_at = ?
                            WHERE canonical_job_id = ?
                            """,
                            (
                                observation.title,
                                normalized_title,
                                observation.location_text,
                                normalized_location,
                                observation.description,
                                observation.salary_min,
                                observation.salary_max,
                                observation.currency,
                                observation.employment_type,
                                observation.contact_email,
                                seen_at,
                                canonical_job_id,
                            ),
                        )

                        if latest is not None:
                            conn.execute(
                                """
                                UPDATE job_versions
                                SET valid_to = ?
                                WHERE version_id = ?
                                """,
                                (
                                    seen_at,
                                    latest[0],
                                ),
                            )

                        version_number = (
                            latest[1] + 1
                            if latest is not None
                            else 1
                        )

                        version_id = _stable_id(
                            canonical_job_id,
                            version_number,
                            content_hash,
                        )

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
                                version_id,
                                canonical_job_id,
                                version_number,
                                seen_at,
                                None,
                                content_hash,
                                _json(changed_fields),
                                snapshot_json,
                            ),
                        )

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
                                _stable_id(
                                    canonical_job_id,
                                    "JOB_CHANGED",
                                    version_number,
                                    content_hash,
                                ),
                                canonical_job_id,
                                "JOB_CHANGED",
                                seen_at,
                                _json(
                                    {
                                        "changed_fields":
                                            changed_fields
                                    }
                                ),
                            ),
                        )

                    else:
                        conn.execute(
                            """
                            UPDATE canonical_jobs
                            SET last_seen_at = ?
                            WHERE canonical_job_id = ?
                            """,
                            (
                                seen_at,
                                canonical_job_id,
                            ),
                        )

                        result.unchanged_count += 1

                conn.execute(
                    """
                    INSERT OR IGNORE INTO canonical_job_sources (
                        canonical_job_id,
                        observation_id,
                        source_key,
                        external_id
                    )
                    VALUES (?, ?, ?, ?)
                    """,
                    (
                        canonical_job_id,
                        observation.observation_id,
                        observation.source_key,
                        observation.external_id,
                    ),
                )

                if canonical_job_id not in result.canonical_job_ids:
                    result.canonical_job_ids.append(
                        canonical_job_id
                    )

            changed_count = max(
                0,
                len(batch.observations)
                - result.new_count
                - result.unchanged_count,
            )

            run_id = _stable_id(
                batch.source_key,
                batch.collector_version,
                batch.started_at.isoformat(),
                batch.finished_at.isoformat(),
            )

            conn.execute(
                """
                INSERT INTO collection_runs (
                    run_id,
                    source_key,
                    collector_version,
                    started_at,
                    finished_at,
                    status,
                    observations_count,
                    new_count,
                    changed_count,
                    unchanged_count,
                    closed_count,
                    warnings_count,
                    error_summary
                )
                VALUES (
                    ?, ?, ?, ?, ?, ?, ?,
                    ?, ?, ?, ?, ?, ?
                )
                """,
                (
                    run_id,
                    batch.source_key,
                    batch.collector_version,
                    batch.started_at.isoformat(),
                    batch.finished_at.isoformat(),
                    batch.status.value,
                    len(batch.observations),
                    result.new_count,
                    changed_count,
                    result.unchanged_count,
                    0,
                    len(batch.warnings),
                    getattr(batch, "error_summary", None),
                ),
            )

        return result

    def collect_many(self, collection_jobs):
        results = []

        for collector, target in collection_jobs:
            results.append(
                self.collect_one(
                    collector,
                    target,
                )
            )

        return results
