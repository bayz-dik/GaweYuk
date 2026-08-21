from __future__ import annotations

from onejob.career_intent.ontology import temporal_state
from onejob.career_intent.repositories import CareerIntentRepository
from onejob.persistence.db import Database


class CareerIntentQueryService:
    """Safe, allowlisted read models for Career Intent."""

    def __init__(self, db: Database):
        self.db = db
        self.repo = CareerIntentRepository()

    def active_version_id(self, twin_id: str) -> str | None:
        with self.db.connection() as conn:
            intent = self.repo.get_for_twin(conn, twin_id)
        return intent.active_version_id if intent else None

    def safe_view(self, *, twin_id: str) -> dict:
        from datetime import datetime, timezone

        now = datetime.now(timezone.utc)
        with self.db.connection() as conn:
            intent = self.repo.get_for_twin(conn, twin_id)
            if intent is None or intent.active_version_id is None:
                return {
                    "active_version": None,
                    "statements": [],
                    "pending_suggestions_count": 0,
                }
            statements = self.repo.get_statements(conn, intent.active_version_id)
            pending = self.repo.list_suggestions(
                conn, intent.intent_id, decision_state="PENDING"
            )

        return {
            "active_version": intent.active_version_id,
            "statements": [
                {
                    "predicate": s.predicate,
                    "operator": s.operator.value,
                    "value": s.value,
                    "strength": s.strength.value,
                    "temporal_status": temporal_state(s, now),
                }
                for s in statements
            ],
            "pending_suggestions_count": len(pending),
        }
