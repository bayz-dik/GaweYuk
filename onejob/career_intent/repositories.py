from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from typing import Any

from onejob.career_intent.models import (
    CareerIntentRecord,
    CareerIntentVersionRecord,
    IntentOperator,
    IntentStatementRecord,
    IntentStrength,
    UnknownPolicy,
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


class StaleIntentPointer(RuntimeError):
    pass


def _row_to_intent(row: sqlite3.Row) -> CareerIntentRecord:
    return CareerIntentRecord(
        intent_id=row["intent_id"],
        twin_id=row["twin_id"],
        active_version_id=row["active_version_id"],
        created_at=_parse_dt(row["created_at"]),
        created_by_actor_id=row["created_by_actor_id"],
    )


def _row_to_version(row: sqlite3.Row) -> CareerIntentVersionRecord:
    return CareerIntentVersionRecord(
        intent_version_id=row["intent_version_id"],
        intent_id=row["intent_id"],
        version_number=row["version_number"],
        supersedes_version_id=row["supersedes_version_id"],
        created_by_actor_id=row["created_by_actor_id"],
        created_at=_parse_dt(row["created_at"]),
        input_fingerprint=row["input_fingerprint"],
    )


def _row_to_statement(row: sqlite3.Row) -> IntentStatementRecord:
    return IntentStatementRecord(
        statement_id=row["statement_id"],
        intent_version_id=row["intent_version_id"],
        predicate=row["predicate"],
        operator=IntentOperator(row["operator"]),
        value=_loads(row["value_json"]),
        value_type=row["value_type"],
        strength=IntentStrength(row["strength"]),
        effective_from=_parse_dt(row["effective_from"]),
        expires_at=_parse_dt(row["expires_at"]),
        unknown_policy=(
            UnknownPolicy(row["unknown_policy"])
            if row["unknown_policy"] is not None
            else None
        ),
        provenance=_loads(row["provenance_json"]) or {},
    )


class CareerIntentRepository:
    """Caller-owned-connection persistence for Career Intent aggregates."""

    def create_intent(
        self,
        conn: sqlite3.Connection,
        *,
        twin_id: str,
        actor_id: str,
        intent_id: str,
    ) -> CareerIntentRecord:
        conn.execute(
            """
            INSERT INTO career_intents (
                intent_id,
                twin_id,
                active_version_id,
                created_at,
                created_by_actor_id
            )
            VALUES (?, ?, NULL, ?, ?)
            """,
            (
                intent_id,
                twin_id,
                datetime.now().isoformat(),
                actor_id,
            ),
        )
        return self.get(conn, intent_id)

    def get(
        self, conn: sqlite3.Connection, intent_id: str
    ) -> CareerIntentRecord | None:
        row = conn.execute(
            "SELECT * FROM career_intents WHERE intent_id = ?",
            (intent_id,),
        ).fetchone()
        return _row_to_intent(row) if row is not None else None

    def get_for_twin(
        self, conn: sqlite3.Connection, twin_id: str
    ) -> CareerIntentRecord | None:
        row = conn.execute(
            "SELECT * FROM career_intents WHERE twin_id = ?",
            (twin_id,),
        ).fetchone()
        return _row_to_intent(row) if row is not None else None

    def append_version(
        self,
        conn: sqlite3.Connection,
        *,
        version: CareerIntentVersionRecord,
        statements: list[IntentStatementRecord],
    ) -> None:
        conn.execute(
            """
            INSERT INTO career_intent_versions (
                intent_version_id,
                intent_id,
                version_number,
                supersedes_version_id,
                created_by_actor_id,
                created_at,
                input_fingerprint
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                version.intent_version_id,
                version.intent_id,
                version.version_number,
                version.supersedes_version_id,
                version.created_by_actor_id,
                _dt(version.created_at),
                version.input_fingerprint,
            ),
        )
        for statement in statements:
            conn.execute(
                """
                INSERT INTO career_intent_statements (
                    statement_id,
                    intent_version_id,
                    predicate,
                    operator,
                    value_json,
                    value_type,
                    strength,
                    effective_from,
                    expires_at,
                    unknown_policy,
                    provenance_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    statement.statement_id,
                    statement.intent_version_id,
                    statement.predicate,
                    statement.operator.value,
                    _dumps(statement.value),
                    statement.value_type,
                    statement.strength.value,
                    _dt(statement.effective_from),
                    _dt(statement.expires_at),
                    statement.unknown_policy.value
                    if statement.unknown_policy is not None
                    else None,
                    _dumps(statement.provenance),
                ),
            )

    def get_version(
        self, conn: sqlite3.Connection, intent_version_id: str
    ) -> CareerIntentVersionRecord | None:
        row = conn.execute(
            "SELECT * FROM career_intent_versions WHERE intent_version_id = ?",
            (intent_version_id,),
        ).fetchone()
        return _row_to_version(row) if row is not None else None

    def get_statements(
        self, conn: sqlite3.Connection, intent_version_id: str
    ) -> list[IntentStatementRecord]:
        rows = conn.execute(
            """
            SELECT * FROM career_intent_statements
            WHERE intent_version_id = ?
            ORDER BY statement_id
            """,
            (intent_version_id,),
        ).fetchall()
        return [_row_to_statement(row) for row in rows]

    def move_active_pointer(
        self,
        conn: sqlite3.Connection,
        intent_id: str,
        expected_active_version_id: str | None,
        new_active_version_id: str,
    ) -> None:
        if expected_active_version_id is None:
            cursor = conn.execute(
                """
                UPDATE career_intents
                SET active_version_id = ?
                WHERE intent_id = ?
                  AND active_version_id IS NULL
                """,
                (new_active_version_id, intent_id),
            )
        else:
            cursor = conn.execute(
                """
                UPDATE career_intents
                SET active_version_id = ?
                WHERE intent_id = ?
                  AND active_version_id = ?
                """,
                (
                    new_active_version_id,
                    intent_id,
                    expected_active_version_id,
                ),
            )
        if cursor.rowcount != 1:
            raise StaleIntentPointer(
                "stale intent active pointer for "
                f"{intent_id}: expected={expected_active_version_id!r}"
            )

    def latest_version_number(
        self, conn: sqlite3.Connection, intent_id: str
    ) -> int:
        row = conn.execute(
            """
            SELECT MAX(version_number) AS n
            FROM career_intent_versions
            WHERE intent_id = ?
            """,
            (intent_id,),
        ).fetchone()
        return row["n"] or 0

    # -- suggestions -----------------------------------------------------

    def insert_suggestion(
        self,
        conn: sqlite3.Connection,
        *,
        suggestion_id: str,
        intent_id: str,
        predicate: str,
        operator: str,
        proposed_value: Any,
        proposed_strength: str,
        evidence: list[Any],
        confidence: float | None,
        source: str,
        decision_state: str,
        created_at: datetime,
        fingerprint: str,
    ) -> None:
        conn.execute(
            """
            INSERT INTO career_intent_suggestions (
                suggestion_id,
                intent_id,
                predicate,
                proposed_value_json,
                proposed_strength,
                operator,
                evidence_json,
                confidence,
                source,
                decision_state,
                created_at,
                fingerprint
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                suggestion_id,
                intent_id,
                predicate,
                _dumps(proposed_value),
                proposed_strength,
                operator,
                _dumps(evidence),
                confidence,
                source,
                decision_state,
                _dt(created_at),
                fingerprint,
            ),
        )

    def get_suggestion(
        self, conn: sqlite3.Connection, suggestion_id: str
    ) -> dict[str, Any] | None:
        row = conn.execute(
            "SELECT * FROM career_intent_suggestions WHERE suggestion_id = ?",
            (suggestion_id,),
        ).fetchone()
        if row is None:
            return None
        return {
            "suggestion_id": row["suggestion_id"],
            "intent_id": row["intent_id"],
            "predicate": row["predicate"],
            "proposed_value": _loads(row["proposed_value_json"]),
            "proposed_strength": row["proposed_strength"],
            "operator": row["operator"],
            "evidence": _loads(row["evidence_json"]),
            "confidence": row["confidence"],
            "source": row["source"],
            "decision_state": row["decision_state"],
            "created_at": row["created_at"],
            "fingerprint": row["fingerprint"],
        }

    def set_suggestion_decision(
        self,
        conn: sqlite3.Connection,
        suggestion_id: str,
        decision_state: str,
    ) -> None:
        conn.execute(
            """
            UPDATE career_intent_suggestions
            SET decision_state = ?
            WHERE suggestion_id = ?
            """,
            (decision_state, suggestion_id),
        )

    def list_suggestions(
        self,
        conn: sqlite3.Connection,
        intent_id: str,
        *,
        decision_state: str | None = None,
    ) -> list[dict[str, Any]]:
        if decision_state is None:
            rows = conn.execute(
                """
                SELECT * FROM career_intent_suggestions
                WHERE intent_id = ?
                ORDER BY created_at, suggestion_id
                """,
                (intent_id,),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT * FROM career_intent_suggestions
                WHERE intent_id = ? AND decision_state = ?
                ORDER BY created_at, suggestion_id
                """,
                (intent_id, decision_state),
            ).fetchall()
        return [
            {
                "suggestion_id": row["suggestion_id"],
                "predicate": row["predicate"],
                "proposed_value": _loads(row["proposed_value_json"]),
                "proposed_strength": row["proposed_strength"],
                "source": row["source"],
                "decision_state": row["decision_state"],
            }
            for row in rows
        ]

    def insert_suppression(
        self,
        conn: sqlite3.Connection,
        *,
        suppression_id: str,
        intent_id: str,
        fingerprint: str,
        reason: str | None,
        created_at: datetime,
    ) -> None:
        conn.execute(
            """
            INSERT INTO career_intent_suppressions (
                suppression_id,
                intent_id,
                fingerprint,
                reason,
                created_at,
                lifted_at
            )
            VALUES (?, ?, ?, ?, ?, NULL)
            """,
            (
                suppression_id,
                intent_id,
                fingerprint,
                reason,
                _dt(created_at),
            ),
        )

    def active_suppression(
        self,
        conn: sqlite3.Connection,
        intent_id: str,
        fingerprint: str,
    ) -> bool:
        row = conn.execute(
            """
            SELECT 1 FROM career_intent_suppressions
            WHERE intent_id = ?
              AND fingerprint = ?
              AND lifted_at IS NULL
            LIMIT 1
            """,
            (intent_id, fingerprint),
        ).fetchone()
        return row is not None
