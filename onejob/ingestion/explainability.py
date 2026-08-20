from __future__ import annotations

import hashlib
import json
import sqlite3
from typing import Any

from onejob.ingestion.consensus import ConsensusValue


def _json(value: Any) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
    )


def _conflict_id(
    canonical_job_id: str,
    field_name: str,
) -> str:
    raw = (
        f"{canonical_job_id}|{field_name}"
    ).encode()

    return hashlib.sha256(raw).hexdigest()


class ConflictExplainabilityStore:
    def sync(
        self,
        conn: sqlite3.Connection,
        canonical_job_id: str,
        consensus_values: dict[str, ConsensusValue],
        observed_at: str,
    ) -> None:
        for field_name, consensus in consensus_values.items():
            conflict_id = _conflict_id(
                canonical_job_id,
                field_name,
            )

            has_conflict = bool(
                consensus.conflicting_evidence_ids
            )

            if has_conflict:
                conn.execute(
                    """
                    INSERT INTO field_conflict_records (
                        conflict_id,
                        canonical_job_id,
                        field_name,
                        status,
                        selected_value_json,
                        confidence,
                        primary_evidence_ids_json,
                        conflicting_evidence_ids_json,
                        resolution_reason,
                        detected_at,
                        updated_at,
                        resolved_at
                    )
                    VALUES (
                        ?, ?, ?, 'OPEN',
                        ?, ?, ?, ?, ?, ?, ?, NULL
                    )
                    ON CONFLICT(canonical_job_id, field_name)
                    DO UPDATE SET
                        status = 'OPEN',
                        selected_value_json =
                            excluded.selected_value_json,
                        confidence =
                            excluded.confidence,
                        primary_evidence_ids_json =
                            excluded.primary_evidence_ids_json,
                        conflicting_evidence_ids_json =
                            excluded.conflicting_evidence_ids_json,
                        resolution_reason =
                            excluded.resolution_reason,
                        updated_at =
                            excluded.updated_at,
                        resolved_at = NULL
                    """,
                    (
                        conflict_id,
                        canonical_job_id,
                        field_name,
                        _json(
                            consensus.selected_value
                        ),
                        consensus.confidence,
                        _json(
                            consensus.primary_evidence_ids
                        ),
                        _json(
                            consensus.conflicting_evidence_ids
                        ),
                        consensus.resolution_reason,
                        observed_at,
                        observed_at,
                    ),
                )

                continue

            existing = conn.execute(
                """
                SELECT conflict_id
                FROM field_conflict_records
                WHERE canonical_job_id = ?
                  AND field_name = ?
                """,
                (
                    canonical_job_id,
                    field_name,
                ),
            ).fetchone()

            if existing is not None:
                conn.execute(
                    """
                    UPDATE field_conflict_records
                    SET
                        status = 'RESOLVED',
                        selected_value_json = ?,
                        confidence = ?,
                        primary_evidence_ids_json = ?,
                        conflicting_evidence_ids_json = '[]',
                        resolution_reason = ?,
                        updated_at = ?,
                        resolved_at = ?
                    WHERE conflict_id = ?
                    """,
                    (
                        _json(
                            consensus.selected_value
                        ),
                        consensus.confidence,
                        _json(
                            consensus.primary_evidence_ids
                        ),
                        consensus.resolution_reason,
                        observed_at,
                        observed_at,
                        existing[0],
                    ),
                )

    @staticmethod
    def _evidence(
        conn: sqlite3.Connection,
        evidence_ids: list[str],
        role: str,
    ) -> list[dict[str, Any]]:
        if not evidence_ids:
            return []

        placeholders = ",".join(
            "?" for _ in evidence_ids
        )

        rows = conn.execute(
            f"""
            SELECT
                e.evidence_id,
                e.value_json,
                e.confidence,
                e.evidence_family_id,
                e.independence_status,
                e.observed_at,
                r.source_key,
                r.source_type,
                r.source_url
            FROM field_evidence AS e
            JOIN raw_job_observations AS r
              ON r.observation_id = e.observation_id
            WHERE e.evidence_id IN ({placeholders})
            """,
            evidence_ids,
        ).fetchall()

        by_id = {
            row[0]: {
                "evidence_id": row[0],
                "role": role,
                "value": json.loads(row[1]),
                "confidence": float(row[2]),
                "evidence_family_id": row[3],
                "independence_status": row[4],
                "observed_at": row[5],
                "source_key": row[6],
                "source_type": row[7],
                "source_url": row[8],
            }
            for row in rows
        }

        return [
            by_id[evidence_id]
            for evidence_id in evidence_ids
            if evidence_id in by_id
        ]

    def explain_field(
        self,
        conn: sqlite3.Connection,
        canonical_job_id: str,
        field_name: str,
    ) -> dict[str, Any]:
        consensus = conn.execute(
            """
            SELECT
                selected_value_json,
                confidence,
                primary_evidence_ids_json,
                conflicting_evidence_ids_json,
                resolution_reason
            FROM field_consensus
            WHERE canonical_job_id = ?
              AND field_name = ?
            """,
            (
                canonical_job_id,
                field_name,
            ),
        ).fetchone()

        if consensus is None:
            raise KeyError(
                f"no consensus for "
                f"{canonical_job_id}:{field_name}"
            )

        conflict = conn.execute(
            """
            SELECT
                status,
                detected_at,
                updated_at,
                resolved_at
            FROM field_conflict_records
            WHERE canonical_job_id = ?
              AND field_name = ?
            """,
            (
                canonical_job_id,
                field_name,
            ),
        ).fetchone()

        primary_ids = json.loads(
            consensus[2]
        )

        conflicting_ids = json.loads(
            consensus[3]
        )

        return {
            "canonical_job_id":
                canonical_job_id,
            "field_name":
                field_name,
            "status": (
                conflict[0]
                if conflict is not None
                else "NO_CONFLICT"
            ),
            "selected_value":
                json.loads(consensus[0]),
            "confidence":
                float(consensus[1]),
            "resolution_reason":
                consensus[4],
            "primary_evidence":
                self._evidence(
                    conn,
                    primary_ids,
                    "PRIMARY",
                ),
            "conflicting_evidence":
                self._evidence(
                    conn,
                    conflicting_ids,
                    "CONFLICTING",
                ),
            "detected_at": (
                conflict[1]
                if conflict is not None
                else None
            ),
            "updated_at": (
                conflict[2]
                if conflict is not None
                else None
            ),
            "resolved_at": (
                conflict[3]
                if conflict is not None
                else None
            ),
        }
