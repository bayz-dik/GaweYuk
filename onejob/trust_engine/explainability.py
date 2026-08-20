from __future__ import annotations

from datetime import datetime, timezone
import sqlite3

from .policy import DEFAULT_POLICY
from .recalculation import (
    is_evaluation_fresh,
)
from .repository import TrustRepository


class TrustExplainabilityService:
    def __init__(self, db):
        self.db = db
        self.repo = TrustRepository()

    def job_exists(
        self,
        canonical_job_id: str,
    ) -> bool:
        with self.db.transaction() as conn:
            table = conn.execute(
                """
                SELECT 1
                FROM sqlite_master
                WHERE type = 'table'
                  AND name = 'canonical_jobs'
                """
            ).fetchone()

            if table is None:
                return False

            row = conn.execute(
                """
                SELECT 1
                FROM canonical_jobs
                WHERE canonical_job_id = ?
                """,
                (canonical_job_id,),
            ).fetchone()

            return row is not None

    def latest_explanation(
        self,
        canonical_job_id: str,
        *,
        now: datetime | None = None,
    ) -> dict | None:
        if now is None:
            now = datetime.now(timezone.utc)

        with self.db.transaction() as conn:
            self.repo.ensure_schema(conn)

            decision = (
                self.repo.latest_evaluation(
                    conn,
                    canonical_job_id,
                )
            )

            if decision is None:
                return None

            active_signals = (
                self.repo.list_active_signals(
                    conn,
                    canonical_job_id,
                )
            )

        fresh = is_evaluation_fresh(
            evaluated_at=decision.evaluated_at,
            valid_until=decision.valid_until,
            now=now,
            evaluation_policy_version=(
                decision.policy_version
            ),
            current_policy_version=(
                DEFAULT_POLICY.version
            ),
        )

        dimensions = {}

        for dimension, score in sorted(
            decision.dimensions.items(),
            key=lambda item: item[0].value,
        ):
            dimensions[dimension.value] = {
                "state": score.state.value,
                "score": score.score,
                "confidence": score.confidence,
                "reason_codes": list(
                    score.reason_codes
                ),
                "evidence_refs": list(
                    score.evidence_refs
                ),
            }

        hard_gates = [
            {
                "signal_id": gate.signal_id,
                "gate_code": gate.gate_code,
                "level": gate.level.value,
                "effect": gate.effect.value,
                "override_policy":
                    gate.override_policy,
            }
            for gate in decision.hard_gates
        ]

        signals = [
            {
                "signal_id": signal.signal_id,
                "signal_type":
                    signal.signal_type,
                "level": signal.level.value,
                "status": signal.status.value,
                "confidence":
                    signal.confidence,
                "detection_method":
                    signal.detection_method.value,
                "context_stage":
                    signal.context_stage.value,
                "evidence_refs": list(
                    signal.evidence_refs
                ),
                "extractor_version":
                    signal.extractor_version,
                "first_seen_at":
                    signal.first_seen_at.isoformat(),
                "last_seen_at":
                    signal.last_seen_at.isoformat(),
            }
            for signal in active_signals
        ]

        return {
            "evaluation_id":
                decision.evaluation_id,
            "canonical_job_id":
                decision.canonical_job_id,
            "recruitment_stage":
                decision.recruitment_stage.value,
            "overall_score":
                decision.overall_score,
            "confidence":
                decision.confidence,
            "classification":
                decision.classification.value,
            "freshness": {
                "state": (
                    "FRESH"
                    if fresh
                    else "NEEDS_REFRESH"
                ),
                "evaluated_at":
                    decision.evaluated_at.isoformat(),
                "valid_until": (
                    decision.valid_until.isoformat()
                    if decision.valid_until
                    else None
                ),
            },
            "dimensions": dimensions,
            "hard_gates": hard_gates,
            "active_signals": signals,
            "risk_signal_ids": list(
                decision.risk_signal_ids
            ),
            "unknown_dimensions": [
                item.value
                for item
                in decision.unknown_dimensions
            ],
            "not_applicable_dimensions": [
                item.value
                for item
                in decision.not_applicable_dimensions
            ],
            "allowed_actions": list(
                decision.allowed_actions
            ),
            "blocked_actions": list(
                decision.blocked_actions
            ),
            "override_policy":
                decision.override_policy,
            "primary_reasons": list(
                decision.primary_reasons
            ),
            "evidence_refs": list(
                decision.evidence_refs
            ),
            "policy_version":
                decision.policy_version,
        }
