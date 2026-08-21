from datetime import datetime, timezone

import pytest

from onejob.career_intent.commands import (
    CareerIntentCommandService,
    CreateCareerIntentVersionCommand,
    NewIntentStatement,
)
from onejob.career_targets.commands import (
    CreateSavedCareerTargetCommand,
    NewTargetOverride,
    TargetCommandService,
)
from onejob.career_targets.compatibility import TargetCompatibilityService
from onejob.career_targets.models import TargetCompatibilityStatus
from onejob.career_twin.ontology import ONTOLOGY_VERSION
from onejob.career_twin.repositories import CareerTwinRepository
from onejob.persistence.db import Database


AT = datetime(2026, 8, 21, 12, tzinfo=timezone.utc)


class SequentialIds:
    def __init__(self):
        self.counts = {}

    def __call__(self, kind: str) -> str:
        n = self.counts.get(kind, 0) + 1
        self.counts[kind] = n
        return f"{kind}-{n}"


def owner():
    return {"actor_id": "user-1", "twin_id": "twin-1", "is_owner": True, "actor_type": "USER"}


class Scenario:
    def __init__(self, tmp_path):
        self.db = Database(tmp_path / "gaweyuk.db")
        self.db.initialize()
        with self.db.transaction() as conn:
            CareerTwinRepository().ensure_twin(
                conn, "twin-1", "user-1", ONTOLOGY_VERSION
            )
        self.ids = SequentialIds()
        self.intent_service = CareerIntentCommandService(self.db, id_factory=self.ids)
        self.target_service = TargetCommandService(self.db, id_factory=self.ids)
        self.compatibility = TargetCompatibilityService(self.db, id_factory=self.ids)

    def create_intent(self, statements, expected=None, key=None):
        return self.intent_service.create_version(
            CreateCareerIntentVersionCommand(
                actor_id="user-1",
                twin_id="twin-1",
                idempotency_key=key or self.ids("k"),
                expected_active_version_id=expected,
                statements=statements,
            ),
            actor=owner(),
            now=AT,
        )

    def create_target(self, overrides=None):
        return self.target_service.create_target(
            CreateSavedCareerTargetCommand(
                actor_id="user-1",
                twin_id="twin-1",
                idempotency_key=self.ids("tk"),
                display_name="Target",
                role_focus=["operator"],
                domain_focus=["logistics"],
                explicit_keywords=[],
                scope_definition={},
                overrides=overrides or [],
            ),
            actor=owner(),
            now=AT,
        )

    def valid_pair(self):
        intent = self.create_intent(
            [
                NewIntentStatement(
                    predicate="COMPENSATION.MIN_SALARY",
                    operator="GTE",
                    value=6_000_000,
                    strength="HARD_CONSTRAINT",
                    value_type="MONEY",
                )
            ]
        )
        target = self.create_target(
            overrides=[
                NewTargetOverride(
                    predicate="COMPENSATION.MIN_SALARY",
                    operation="REPLACE",
                    value=7_000_000,
                    overrides_statement_id="intent_statement-1",
                )
            ]
        )
        return intent.intent_version_id, target.target_version_id

    def pair_requiring_explicit_exception(self):
        # Intent v1 min 6M, target tightens to 7M (valid). Then intent v2
        # raises global min to 8M so the target's 7M is now weaker than
        # inherited HARD → NEEDS_REVIEW.
        intent1 = self.create_intent(
            [
                NewIntentStatement(
                    predicate="COMPENSATION.MIN_SALARY",
                    operator="GTE",
                    value=6_000_000,
                    strength="HARD_CONSTRAINT",
                    value_type="MONEY",
                )
            ]
        )
        target = self.create_target(
            overrides=[
                NewTargetOverride(
                    predicate="COMPENSATION.MIN_SALARY",
                    operation="REPLACE",
                    value=7_000_000,
                    overrides_statement_id="intent_statement-1",
                )
            ]
        )
        intent2 = self.create_intent(
            [
                NewIntentStatement(
                    predicate="COMPENSATION.MIN_SALARY",
                    operator="GTE",
                    value=8_000_000,
                    strength="HARD_CONSTRAINT",
                    value_type="MONEY",
                )
            ],
            expected=intent1.intent_version_id,
        )
        return intent2.intent_version_id, target.target_version_id

    def unsatisfiable_pair(self):
        # Intent v2 sets both min and max HARD such that resolved target is
        # impossible.
        intent1 = self.create_intent(
            [
                NewIntentStatement(
                    predicate="COMPENSATION.MIN_SALARY",
                    operator="GTE",
                    value=6_000_000,
                    strength="HARD_CONSTRAINT",
                    value_type="MONEY",
                )
            ]
        )
        target = self.create_target(
            overrides=[
                NewTargetOverride(
                    predicate="COMPENSATION.MAX_SALARY",
                    operation="ADD",
                    value=5_000_000,
                    strength="HARD_CONSTRAINT",
                )
            ]
        )
        intent2 = self.create_intent(
            [
                NewIntentStatement(
                    predicate="COMPENSATION.MIN_SALARY",
                    operator="GTE",
                    value=6_000_000,
                    strength="HARD_CONSTRAINT",
                    value_type="MONEY",
                )
            ],
            expected=intent1.intent_version_id,
        )
        return intent2.intent_version_id, target.target_version_id

    def persist_compatibility_for_intent(self, intent_version_id):
        _, target_version_id = self.valid_pair()
        return self.compatibility.assess(
            intent_version_id=intent_version_id,
            target_version_id=target_version_id,
            at=AT,
        )


@pytest.fixture
def scenario(tmp_path):
    return Scenario(tmp_path)


def test_compatible_target_is_valid_for_exact_intent_version(scenario):
    intent_v1, target_v1 = scenario.valid_pair()
    result = scenario.compatibility.assess(
        intent_version_id=intent_v1,
        target_version_id=target_v1,
        at=AT,
    )
    assert result.status == TargetCompatibilityStatus.VALID
    assert result.against_intent_version_id == intent_v1
    assert result.validator_version


def test_new_global_hard_rule_can_put_target_into_needs_review(scenario):
    intent_v2, target_v1 = scenario.pair_requiring_explicit_exception()
    result = scenario.compatibility.assess(
        intent_version_id=intent_v2,
        target_version_id=target_v1,
        at=AT,
    )
    assert result.status == TargetCompatibilityStatus.NEEDS_REVIEW


def test_impossible_resolved_target_is_unsatisfiable(scenario):
    intent_v2, target_v1 = scenario.unsatisfiable_pair()
    result = scenario.compatibility.assess(
        intent_version_id=intent_v2,
        target_version_id=target_v1,
        at=AT,
    )
    assert result.status == TargetCompatibilityStatus.UNSATISFIABLE


def test_compatibility_assessment_for_old_intent_is_stale(scenario):
    intent_v1, target_v1 = scenario.valid_pair()
    old = scenario.compatibility.assess(
        intent_version_id=intent_v1,
        target_version_id=target_v1,
        at=AT,
    )
    assert scenario.compatibility.is_current(
        old, active_intent_version_id="intent_version-999"
    ) is False
    assert scenario.compatibility.is_current(
        old, active_intent_version_id=intent_v1
    ) is True


def test_activation_quarantines_dependent_target_without_repair(scenario):
    # active intent v1, valid target, then activate intent v2 (valid itself)
    # that makes the target need review; target version stays unchanged.
    intent_v2, target_v1 = scenario.pair_requiring_explicit_exception()

    results = scenario.compatibility.revalidate_for_active_intent(
        twin_id="twin-1",
        intent_version_id=intent_v2,
        at=AT,
    )
    statuses = {r.target_version_id: r.status for r in results}
    assert statuses[target_v1] == TargetCompatibilityStatus.NEEDS_REVIEW

    # target version row unchanged
    from onejob.career_targets.repositories import SavedCareerTargetRepository

    with scenario.db.connection() as conn:
        version = SavedCareerTargetRepository().get_version(conn, target_v1)
    assert version.version_number == 1
