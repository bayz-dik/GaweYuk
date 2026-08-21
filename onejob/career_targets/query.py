from __future__ import annotations

from onejob.career_targets.repositories import SavedCareerTargetRepository
from onejob.career_intent.repositories import CareerIntentRepository
from onejob.persistence.db import Database


class CareerTargetQueryService:
    """Safe, allowlisted read models for Saved Career Targets."""

    def __init__(self, db: Database):
        self.db = db
        self.repo = SavedCareerTargetRepository()
        self.intents = CareerIntentRepository()

    def list_safe(self, *, twin_id: str) -> list[dict]:
        with self.db.connection() as conn:
            targets = self.repo.list_for_twin(conn, twin_id)
            result = []
            for target in targets:
                result.append(self._safe(conn, target, twin_id))
        return result

    def safe_view(self, *, twin_id: str, target_id: str) -> dict | None:
        with self.db.connection() as conn:
            target = self.repo.get_owned(conn, target_id=target_id, twin_id=twin_id)
            if target is None:
                return None
            return self._safe(conn, target, twin_id)

    def _safe(self, conn, target, twin_id) -> dict:
        display_name = None
        compatibility_status = None
        compatibility_reasons: list[str] = []
        if target.active_version_id is not None:
            version = self.repo.get_version(conn, target.active_version_id)
            display_name = version.display_name if version else None
            intent = self.intents.get_for_twin(conn, twin_id)
            if intent and intent.active_version_id:
                compat = self.repo.latest_compatibility(
                    conn,
                    target_version_id=target.active_version_id,
                    against_intent_version_id=intent.active_version_id,
                )
                if compat is not None:
                    compatibility_status = compat.status.value
                    compatibility_reasons = compat.reasons
        return {
            "target_id": target.target_id,
            "display_name": display_name,
            "active_version": target.active_version_id,
            "lifecycle": target.lifecycle.value,
            "compatibility_status": compatibility_status,
            "compatibility_reasons": compatibility_reasons,
        }
