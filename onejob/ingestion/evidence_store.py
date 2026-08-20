from __future__ import annotations

import hashlib
import json
import sqlite3
from typing import Any

from onejob.ingestion.consensus import (
    ConsensusValue,
    resolve_field_consensus,
)
from onejob.ingestion.models import RawJobObservation


MATERIAL_FIELDS = (
    "title",
    "company_name",
    "location_text",
    "description",
    "salary_min",
    "salary_max",
    "currency",
    "employment_type",
    "contact_email",
)


SOURCE_CONFIDENCE = {
    "company_career": 0.98,
    "ats": 0.95,
    "government": 0.95,
    "university": 0.90,
    "agency": 0.85,
    "job_portal": 0.78,
    "event": 0.75,
    "open_web": 0.60,
    "user_supplied": 0.50,
}


def _json(value: Any) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
    )


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def _source_confidence(
    observation: RawJobObservation,
) -> float:
    source_type = observation.source_type

    key = (
        source_type.value
        if hasattr(source_type, "value")
        else str(source_type)
    )

    return SOURCE_CONFIDENCE.get(key, 0.50)


def _family_id(
    observation: RawJobObservation,
) -> str:
    # Satu listing upstream = satu evidence family.
    # Observation baru dari listing yang sama supersede
    # observation lamanya untuk current consensus.
    return (
        f"{observation.source_key}:"
        f"{observation.external_id}"
    )


class EvidenceConsensusStore:
    def record_observation(
        self,
        conn: sqlite3.Connection,
        canonical_job_id: str,
        observation: RawJobObservation,
    ) -> dict[str, ConsensusValue]:
        results: dict[str, ConsensusValue] = {}

        family_id = _family_id(observation)
        confidence = _source_confidence(observation)

        for field_name in MATERIAL_FIELDS:
            value = getattr(
                observation,
                field_name,
                None,
            )

            if value is None or value == "":
                continue

            value_json = _json(value)

            evidence_id = _sha256(
                f"{observation.observation_id}|"
                f"{field_name}"
            )

            previous_family_evidence = conn.execute(
                """
                SELECT 1
                FROM field_evidence
                WHERE canonical_job_id = ?
                  AND field_name = ?
                  AND evidence_family_id = ?
                LIMIT 1
                """,
                (
                    canonical_job_id,
                    field_name,
                    family_id,
                ),
            ).fetchone()

            independence_status = (
                "RELATED"
                if previous_family_evidence
                else "INDEPENDENT"
            )

            conn.execute(
                """
                INSERT OR IGNORE INTO field_evidence (
                    evidence_id,
                    canonical_job_id,
                    observation_id,
                    field_name,
                    value_json,
                    value_fingerprint,
                    evidence_family_id,
                    independence_status,
                    observed_at,
                    confidence
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    evidence_id,
                    canonical_job_id,
                    observation.observation_id,
                    field_name,
                    value_json,
                    _sha256(value_json),
                    family_id,
                    independence_status,
                    observation.observed_at.isoformat(),
                    confidence,
                ),
            )

            results[field_name] = self.resolve_field(
                conn,
                canonical_job_id,
                field_name,
            )

        return results

    def resolve_field(
        self,
        conn: sqlite3.Connection,
        canonical_job_id: str,
        field_name: str,
    ) -> ConsensusValue:
        rows = conn.execute(
            """
            SELECT
                evidence_id,
                value_json,
                evidence_family_id,
                confidence,
                observed_at
            FROM field_evidence
            WHERE canonical_job_id = ?
              AND field_name = ?
            ORDER BY observed_at DESC, rowid DESC
            """,
            (
                canonical_job_id,
                field_name,
            ),
        ).fetchall()

        # Hanya evidence terbaru per upstream listing
        # yang ikut voting current consensus.
        active_evidence = []
        seen_families = set()

        for row in rows:
            family_id = row[2]

            if family_id in seen_families:
                continue

            seen_families.add(family_id)

            active_evidence.append(
                {
                    "evidence_id": row[0],
                    "value": json.loads(row[1]),
                    "evidence_family_id": family_id,
                    "confidence": float(row[3]),
                }
            )

        consensus = resolve_field_consensus(
            field_name,
            active_evidence,
        )

        conn.execute(
            """
            INSERT INTO field_consensus (
                canonical_job_id,
                field_name,
                selected_value_json,
                confidence,
                primary_evidence_ids_json,
                conflicting_evidence_ids_json,
                resolution_reason
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(canonical_job_id, field_name)
            DO UPDATE SET
                selected_value_json =
                    excluded.selected_value_json,
                confidence =
                    excluded.confidence,
                primary_evidence_ids_json =
                    excluded.primary_evidence_ids_json,
                conflicting_evidence_ids_json =
                    excluded.conflicting_evidence_ids_json,
                resolution_reason =
                    excluded.resolution_reason
            """,
            (
                canonical_job_id,
                field_name,
                _json(consensus.selected_value),
                consensus.confidence,
                _json(consensus.primary_evidence_ids),
                _json(consensus.conflicting_evidence_ids),
                consensus.resolution_reason,
            ),
        )

        return consensus
