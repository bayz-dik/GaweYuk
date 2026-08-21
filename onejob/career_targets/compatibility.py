from __future__ import annotations

from datetime import datetime
from typing import Protocol

from onejob.career_intent.repositories import CareerIntentRepository
from onejob.career_intent.validation import (
    IntentValidationStatus,
    validate_intent_statements,
)
from onejob.career_targets.models import (
    TargetCompatibilityRecord,
    TargetCompatibilityStatus,
)
from onejob.career_targets.repositories import SavedCareerTargetRepository
from onejob.career_targets.resolver import (
    HardConstraintExceptionRequired,
    resolve_target_policy,
)
from onejob.career_intent.models import (
    IntentOperator,
    IntentStatementRecord,
    IntentStrength,
    UnknownPolicy,
)
from onejob.persistence.db import Database


VALIDATOR_VERSION = "target-compat-v1"


class IdFactory(Protocol):
    def __call__(self, kind: str) -> str:
        ...


class TargetCompatibilityService:
    """Deterministic target-vs-intent compatibility assessment.

    An assessment resolves the exact target version against the exact intent
    version and classifies VALID / NEEDS_REVIEW / UNSATISFIABLE. It never
    mutates the target version.
    """

    def __init__(self, db: Database, *, id_factory: IdFactory):
        self.db = db
        self.id_factory = id_factory
        self.intents = CareerIntentRepository()
        self.targets = SavedCareerTargetRepository()

    def assess(
        self,
        *,
        intent_version_id: str,
        target_version_id: str,
        at: datetime,
        persist: bool = True,
    ) -> TargetCompatibilityRecord:
        with self.db.connection() as conn:
            intent_statements = self.intents.get_statements(conn, intent_version_id)
            overrides = self.targets.get_overrides(conn, target_version_id)
            target_version = self.targets.get_version(conn, target_version_id)

        status, reasons = self._classify(intent_statements, overrides, at)

        record = TargetCompatibilityRecord(
            compatibility_id=self.id_factory("compatibility"),
            target_id=target_version.target_id,
            target_version_id=target_version_id,
            against_intent_version_id=intent_version_id,
            status=status,
            reasons=reasons,
            checked_at=at,
            validator_version=VALIDATOR_VERSION,
        )

        if persist:
            with self.db.transaction() as conn:
                self.targets.save_compatibility(conn, record=record)

        return record

    def _classify(self, intent_statements, overrides, at):
        reasons: list[str] = []
        try:
            draft = resolve_target_policy(
                intent_statements=intent_statements,
                target_overrides=overrides,
                at=at,
                exception_authority=None,
            )
        except HardConstraintExceptionRequired as exc:
            return (
                TargetCompatibilityStatus.NEEDS_REVIEW,
                [f"requires explicit exception: {exc}"],
            )

        # Build resolved statements and run contradiction validation.
        resolved_statements = self._as_intent_statements(draft)
        validation = validate_intent_statements(resolved_statements, at=at)
        if validation.status == IntentValidationStatus.UNSATISFIABLE.value:
            return (
                TargetCompatibilityStatus.UNSATISFIABLE,
                [c.reason for c in validation.hard_conflicts],
            )

        return (TargetCompatibilityStatus.VALID, reasons or ["resolvable"])

    def _as_intent_statements(self, draft) -> list[IntentStatementRecord]:
        statements: list[IntentStatementRecord] = []
        for i, entry in enumerate(draft.as_statements()):
            try:
                operator = self._operator_for(entry)
            except KeyError:
                continue
            statements.append(
                IntentStatementRecord(
                    statement_id=f"resolved-{i}",
                    intent_version_id="__resolved__",
                    predicate=entry.predicate,
                    operator=operator,
                    value=entry.value,
                    value_type=entry.value_type,
                    strength=IntentStrength(entry.strength),
                    unknown_policy=(
                        UnknownPolicy(entry.unknown_policy)
                        if entry.unknown_policy
                        else None
                    ),
                    provenance={},
                )
            )
        return statements

    def _operator_for(self, entry) -> IntentOperator:
        from onejob.career_intent.ontology import get_intent_predicate_definition

        return get_intent_predicate_definition(entry.predicate).operator

    def is_current(
        self,
        record: TargetCompatibilityRecord,
        *,
        active_intent_version_id: str,
    ) -> bool:
        """A compatibility assessment is current only for the active intent."""
        return record.against_intent_version_id == active_intent_version_id

    def revalidate_for_active_intent(
        self,
        *,
        twin_id: str,
        intent_version_id: str,
        at: datetime,
    ) -> list[TargetCompatibilityRecord]:
        """Deterministically revalidate all of a twin's targets.

        Does not roll back the already-committed intent version. Each target's
        active version is assessed against the new active intent version.
        """
        with self.db.connection() as conn:
            targets = self.targets.list_for_twin(conn, twin_id)

        results: list[TargetCompatibilityRecord] = []
        for target in targets:
            if target.active_version_id is None:
                continue
            results.append(
                self.assess(
                    intent_version_id=intent_version_id,
                    target_version_id=target.active_version_id,
                    at=at,
                )
            )
        return results
