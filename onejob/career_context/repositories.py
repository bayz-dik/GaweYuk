from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from typing import Any

from onejob.career_context.models import (
    ConstraintAssessment,
    ConstraintResult,
    ResolvedScope,
    ResolvedTargetViewRecord,
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


def _row_to_view(row: sqlite3.Row) -> ResolvedTargetViewRecord:
    return ResolvedTargetViewRecord(
        resolved_view_id=row["resolved_view_id"],
        twin_id=row["twin_id"],
        intent_version_id=row["intent_version_id"],
        target_version_id=row["target_version_id"],
        routing_decision_id=row["routing_decision_id"],
        scope=ResolvedScope(row["scope"]),
        resolved_statements=_loads(row["resolved_statements_json"]) or [],
        applied_overrides=_loads(row["applied_overrides_json"]) or [],
        explicit_exceptions=_loads(row["explicit_exceptions_json"]) or [],
        active_temporal_statements=(
            _loads(row["active_temporal_statements_json"]) or []
        ),
        tensions=_loads(row["tensions_json"]) or [],
        validation_status=row["validation_status"],
        resolver_version=row["resolver_version"],
        evaluated_at=_parse_dt(row["evaluated_at"]),
        input_fingerprint=row["input_fingerprint"],
    )


class CareerContextRepository:
    """Caller-owned-connection persistence for resolved views/assessments."""

    def get_or_create_resolved_view(
        self, conn: sqlite3.Connection, *, view: ResolvedTargetViewRecord
    ) -> ResolvedTargetViewRecord:
        existing = conn.execute(
            """
            SELECT * FROM resolved_target_views
            WHERE twin_id = ? AND input_fingerprint = ?
            """,
            (view.twin_id, view.input_fingerprint),
        ).fetchone()
        if existing is not None:
            # Content-addressed reuse: return the existing immutable snapshot.
            return _row_to_view(existing)

        conn.execute(
            """
            INSERT INTO resolved_target_views (
                resolved_view_id,
                twin_id,
                intent_version_id,
                target_version_id,
                routing_decision_id,
                scope,
                resolved_statements_json,
                applied_overrides_json,
                explicit_exceptions_json,
                active_temporal_statements_json,
                tensions_json,
                validation_status,
                resolver_version,
                evaluated_at,
                input_fingerprint
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                view.resolved_view_id,
                view.twin_id,
                view.intent_version_id,
                view.target_version_id,
                view.routing_decision_id,
                view.scope.value,
                _dumps(view.resolved_statements),
                _dumps(view.applied_overrides),
                _dumps(view.explicit_exceptions),
                _dumps(view.active_temporal_statements),
                _dumps(view.tensions),
                view.validation_status,
                view.resolver_version,
                _dt(view.evaluated_at),
                view.input_fingerprint,
            ),
        )
        return view

    def get_resolved_view(
        self, conn: sqlite3.Connection, resolved_view_id: str, *, twin_id: str
    ) -> ResolvedTargetViewRecord | None:
        row = conn.execute(
            """
            SELECT * FROM resolved_target_views
            WHERE resolved_view_id = ? AND twin_id = ?
            """,
            (resolved_view_id, twin_id),
        ).fetchone()
        return _row_to_view(row) if row is not None else None

    def append_constraint_assessment(
        self, conn: sqlite3.Connection, *, assessment: ConstraintAssessment
    ) -> None:
        conn.execute(
            """
            INSERT INTO constraint_assessments (
                assessment_id,
                resolved_view_id,
                statement_id,
                result,
                observed_value_json,
                evidence_status,
                unknown_reason,
                required_action,
                reasons_json,
                evaluator_version
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                assessment.assessment_id,
                assessment.resolved_view_id,
                assessment.statement_id,
                assessment.result.value,
                _dumps(assessment.observed_value),
                assessment.evidence_status,
                assessment.unknown_reason,
                assessment.required_action,
                _dumps(assessment.reasons),
                assessment.evaluator_version,
            ),
        )

    def list_constraint_assessments(
        self, conn: sqlite3.Connection, resolved_view_id: str
    ) -> list[ConstraintAssessment]:
        rows = conn.execute(
            """
            SELECT * FROM constraint_assessments
            WHERE resolved_view_id = ?
            ORDER BY assessment_id
            """,
            (resolved_view_id,),
        ).fetchall()
        return [
            ConstraintAssessment(
                assessment_id=row["assessment_id"],
                resolved_view_id=row["resolved_view_id"],
                statement_id=row["statement_id"],
                result=ConstraintResult(row["result"]),
                observed_value=_loads(row["observed_value_json"]),
                evidence_status=row["evidence_status"],
                unknown_reason=row["unknown_reason"],
                required_action=row["required_action"],
                reasons=_loads(row["reasons_json"]) or [],
                evaluator_version=row["evaluator_version"],
            )
            for row in rows
        ]
