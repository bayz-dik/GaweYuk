from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from typing import Any

from onejob.career_intent.models import IntentStrength
from onejob.career_targets.models import (
    OverrideOperation,
    SavedCareerTargetRecord,
    SavedCareerTargetVersionRecord,
    TargetCompatibilityRecord,
    TargetCompatibilityStatus,
    TargetIntentOverrideRecord,
    TargetLifecycle,
)


def _dumps(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def _loads(text: str | None) -> Any:
    if text is None:
        return None
    return json.loads(text)


def _dt(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


def _parse_dt(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value) if value is not None else None


class StaleTargetState(RuntimeError):
    pass


def _row_to_target(row: sqlite3.Row) -> SavedCareerTargetRecord:
    return SavedCareerTargetRecord(
        target_id=row["target_id"],
        twin_id=row["twin_id"],
        active_version_id=row["active_version_id"],
        lifecycle=TargetLifecycle(row["lifecycle"]),
        created_at=_parse_dt(row["created_at"]),
        created_by_actor_id=row["created_by_actor_id"],
    )


def _row_to_version(row: sqlite3.Row) -> SavedCareerTargetVersionRecord:
    return SavedCareerTargetVersionRecord(
        target_version_id=row["target_version_id"],
        target_id=row["target_id"],
        version_number=row["version_number"],
        supersedes_version_id=row["supersedes_version_id"],
        display_name=row["display_name"],
        role_focus=_loads(row["role_focus_json"]) or [],
        domain_focus=_loads(row["domain_focus_json"]) or [],
        explicit_keywords=_loads(row["explicit_keywords_json"]) or [],
        scope_definition=_loads(row["scope_definition_json"]) or {},
        created_at=_parse_dt(row["created_at"]),
        input_fingerprint=row["input_fingerprint"],
    )


def _row_to_override(row: sqlite3.Row) -> TargetIntentOverrideRecord:
    return TargetIntentOverrideRecord(
        override_id=row["override_id"],
        target_version_id=row["target_version_id"],
        predicate=row["predicate"],
        operation=OverrideOperation(row["operation"]),
        value=_loads(row["value_json"]),
        strength=(
            IntentStrength(row["strength"])
            if row["strength"] is not None
            else None
        ),
        effective_from=_parse_dt(row["effective_from"]),
        expires_at=_parse_dt(row["expires_at"]),
        overrides_statement_id=row["overrides_statement_id"],
        explicit_exception_authority=row["explicit_exception_authority"],
    )


def _row_to_compatibility(row: sqlite3.Row) -> TargetCompatibilityRecord:
    return TargetCompatibilityRecord(
        compatibility_id=row["compatibility_id"],
        target_id=row["target_id"],
        target_version_id=row["target_version_id"],
        against_intent_version_id=row["against_intent_version_id"],
        status=TargetCompatibilityStatus(row["status"]),
        reasons=_loads(row["reasons_json"]) or [],
        checked_at=_parse_dt(row["checked_at"]),
        validator_version=row["validator_version"],
    )


class SavedCareerTargetRepository:
    """Caller-owned-connection persistence for Saved Career Targets."""

    def create_target(
        self, conn: sqlite3.Connection, *, target: SavedCareerTargetRecord
    ) -> None:
        conn.execute(
            """
            INSERT INTO saved_career_targets (
                target_id,
                twin_id,
                active_version_id,
                lifecycle,
                created_at,
                created_by_actor_id
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                target.target_id,
                target.twin_id,
                target.active_version_id,
                target.lifecycle.value,
                _dt(target.created_at),
                target.created_by_actor_id,
            ),
        )

    def get(
        self, conn: sqlite3.Connection, target_id: str
    ) -> SavedCareerTargetRecord | None:
        row = conn.execute(
            "SELECT * FROM saved_career_targets WHERE target_id = ?",
            (target_id,),
        ).fetchone()
        return _row_to_target(row) if row is not None else None

    def get_owned(
        self, conn: sqlite3.Connection, *, target_id: str, twin_id: str
    ) -> SavedCareerTargetRecord | None:
        row = conn.execute(
            """
            SELECT * FROM saved_career_targets
            WHERE target_id = ? AND twin_id = ?
            """,
            (target_id, twin_id),
        ).fetchone()
        return _row_to_target(row) if row is not None else None

    def list_for_twin(
        self, conn: sqlite3.Connection, twin_id: str
    ) -> list[SavedCareerTargetRecord]:
        rows = conn.execute(
            """
            SELECT * FROM saved_career_targets
            WHERE twin_id = ?
            ORDER BY created_at, target_id
            """,
            (twin_id,),
        ).fetchall()
        return [_row_to_target(row) for row in rows]

    def append_version(
        self,
        conn: sqlite3.Connection,
        *,
        version: SavedCareerTargetVersionRecord,
        overrides: list[TargetIntentOverrideRecord],
    ) -> None:
        conn.execute(
            """
            INSERT INTO saved_career_target_versions (
                target_version_id,
                target_id,
                version_number,
                supersedes_version_id,
                display_name,
                role_focus_json,
                domain_focus_json,
                explicit_keywords_json,
                scope_definition_json,
                created_at,
                input_fingerprint
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                version.target_version_id,
                version.target_id,
                version.version_number,
                version.supersedes_version_id,
                version.display_name,
                _dumps(version.role_focus),
                _dumps(version.domain_focus),
                _dumps(version.explicit_keywords),
                _dumps(version.scope_definition),
                _dt(version.created_at),
                version.input_fingerprint,
            ),
        )
        for override in overrides:
            conn.execute(
                """
                INSERT INTO target_intent_overrides (
                    override_id,
                    target_version_id,
                    predicate,
                    operation,
                    value_json,
                    strength,
                    effective_from,
                    expires_at,
                    overrides_statement_id,
                    explicit_exception_authority
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    override.override_id,
                    override.target_version_id,
                    override.predicate,
                    override.operation.value,
                    _dumps(override.value),
                    override.strength.value
                    if override.strength is not None
                    else None,
                    _dt(override.effective_from),
                    _dt(override.expires_at),
                    override.overrides_statement_id,
                    override.explicit_exception_authority,
                ),
            )

    def get_version(
        self, conn: sqlite3.Connection, target_version_id: str
    ) -> SavedCareerTargetVersionRecord | None:
        row = conn.execute(
            """
            SELECT * FROM saved_career_target_versions
            WHERE target_version_id = ?
            """,
            (target_version_id,),
        ).fetchone()
        return _row_to_version(row) if row is not None else None

    def get_overrides(
        self, conn: sqlite3.Connection, target_version_id: str
    ) -> list[TargetIntentOverrideRecord]:
        rows = conn.execute(
            """
            SELECT * FROM target_intent_overrides
            WHERE target_version_id = ?
            ORDER BY override_id
            """,
            (target_version_id,),
        ).fetchall()
        return [_row_to_override(row) for row in rows]

    def latest_version_number(
        self, conn: sqlite3.Connection, target_id: str
    ) -> int:
        row = conn.execute(
            """
            SELECT MAX(version_number) AS n
            FROM saved_career_target_versions
            WHERE target_id = ?
            """,
            (target_id,),
        ).fetchone()
        return row["n"] or 0

    def move_active_pointer(
        self,
        conn: sqlite3.Connection,
        *,
        target_id: str,
        expected_active_version_id: str | None,
        new_active_version_id: str,
    ) -> None:
        if expected_active_version_id is None:
            cursor = conn.execute(
                """
                UPDATE saved_career_targets
                SET active_version_id = ?
                WHERE target_id = ? AND active_version_id IS NULL
                """,
                (new_active_version_id, target_id),
            )
        else:
            cursor = conn.execute(
                """
                UPDATE saved_career_targets
                SET active_version_id = ?
                WHERE target_id = ? AND active_version_id = ?
                """,
                (new_active_version_id, target_id, expected_active_version_id),
            )
        if cursor.rowcount != 1:
            raise StaleTargetState(
                "stale target active pointer for "
                f"{target_id}: expected={expected_active_version_id!r}"
            )

    def set_lifecycle(
        self,
        conn: sqlite3.Connection,
        *,
        target_id: str,
        expected_lifecycle: TargetLifecycle,
        new_lifecycle: TargetLifecycle,
    ) -> None:
        cursor = conn.execute(
            """
            UPDATE saved_career_targets
            SET lifecycle = ?
            WHERE target_id = ? AND lifecycle = ?
            """,
            (new_lifecycle.value, target_id, expected_lifecycle.value),
        )
        if cursor.rowcount != 1:
            raise StaleTargetState(
                "stale target lifecycle for "
                f"{target_id}: expected={expected_lifecycle.value}"
            )

    # -- compatibility ---------------------------------------------------

    def save_compatibility(
        self, conn: sqlite3.Connection, *, record: TargetCompatibilityRecord
    ) -> None:
        conn.execute(
            """
            INSERT INTO target_compatibility_assessments (
                compatibility_id,
                target_id,
                target_version_id,
                against_intent_version_id,
                status,
                reasons_json,
                checked_at,
                validator_version
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                record.compatibility_id,
                record.target_id,
                record.target_version_id,
                record.against_intent_version_id,
                record.status.value,
                _dumps(record.reasons),
                _dt(record.checked_at),
                record.validator_version,
            ),
        )

    def latest_compatibility(
        self,
        conn: sqlite3.Connection,
        *,
        target_version_id: str,
        against_intent_version_id: str,
    ) -> TargetCompatibilityRecord | None:
        row = conn.execute(
            """
            SELECT * FROM target_compatibility_assessments
            WHERE target_version_id = ?
              AND against_intent_version_id = ?
            ORDER BY checked_at DESC, compatibility_id DESC
            LIMIT 1
            """,
            (target_version_id, against_intent_version_id),
        ).fetchone()
        return _row_to_compatibility(row) if row is not None else None

    # -- routing / applicability ----------------------------------------

    def save_applicability(
        self,
        conn: sqlite3.Connection,
        *,
        assessment,
    ) -> None:
        conn.execute(
            """
            INSERT INTO target_applicability_assessments (
                assessment_id,
                twin_id,
                job_context_fingerprint,
                intent_version_id,
                target_version_id,
                eligibility,
                applicability_score,
                confidence_band,
                signals_json,
                reasons_json,
                router_version,
                created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                assessment.assessment_id,
                assessment.twin_id,
                assessment.job_context_fingerprint,
                assessment.intent_version_id,
                assessment.target_version_id,
                assessment.eligibility.value,
                assessment.applicability_score,
                assessment.confidence_band.value,
                _dumps([s.model_dump() for s in assessment.signals]),
                _dumps(assessment.reasons),
                assessment.router_version,
                _dt(assessment.created_at),
            ),
        )

    def save_routing_decision(
        self, conn: sqlite3.Connection, *, decision
    ) -> None:
        conn.execute(
            """
            INSERT INTO target_routing_decisions (
                routing_decision_id,
                twin_id,
                job_context_fingerprint,
                intent_version_id,
                method,
                selected_target_version_id,
                winner_score,
                winner_margin,
                router_version,
                reasons_json,
                alternatives_json,
                created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                decision.routing_decision_id,
                decision.twin_id,
                decision.job_context_fingerprint,
                decision.intent_version_id,
                decision.method.value,
                decision.selected_target_version_id,
                decision.winner_score,
                decision.winner_margin,
                decision.router_version,
                _dumps(decision.reasons),
                _dumps([a.model_dump() for a in decision.alternatives]),
                _dt(decision.created_at),
            ),
        )
