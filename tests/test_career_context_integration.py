from datetime import datetime, timezone

import pytest

from onejob.career_context.models import ResolvedScope
from onejob.career_context.service import (
    CareerContextService,
    ResolvedContextOutcome,
    resolved_context_fingerprint,
)
from onejob.career_intent.commands import (
    CareerIntentCommandService,
    CreateCareerIntentVersionCommand,
    NewIntentStatement,
)
from onejob.career_targets.commands import (
    CreateSavedCareerTargetCommand,
    TargetCommandService,
)
from onejob.career_targets.compatibility import TargetCompatibilityService
from onejob.career_targets.routing import TargetRoutingService
from onejob.career_twin.ontology import ONTOLOGY_VERSION
from onejob.career_twin.repositories import CareerTwinRepository
from onejob.models import CanonicalJob
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


def job(**overrides):
    data = dict(
        id="job-1", title="Warehouse Operator", company="PT Logistik",
        location="Bekasi", description="Operate forklift in warehouse logistics.",
        normalized_title="warehouse operator", normalized_company="pt logistik",
        normalized_location="bekasi", skills=["forklift"], salary_min=7_000_000,
    )
    data.update(overrides)
    return CanonicalJob(**data)


class Env:
    def __init__(self, tmp_path):
        self.db = Database(tmp_path / "gaweyuk.db")
        self.db.initialize()
        with self.db.transaction() as conn:
            CareerTwinRepository().ensure_twin(conn, "twin-1", "user-1", ONTOLOGY_VERSION)
        self.ids = SequentialIds()
        self.intent = CareerIntentCommandService(self.db, id_factory=self.ids)
        self.targets = TargetCommandService(self.db, id_factory=self.ids)
        self.compat = TargetCompatibilityService(self.db, id_factory=self.ids)
        self.router = TargetRoutingService(self.db, id_factory=self.ids)
        self.service = CareerContextService(
            self.db, id_factory=self.ids,
            intent_service=self.intent, target_service=self.targets,
            compatibility_service=self.compat, routing_service=self.router,
        )
        self.intent_version = self.intent.create_version(
            CreateCareerIntentVersionCommand(
                actor_id="user-1", twin_id="twin-1", idempotency_key="i1",
                expected_active_version_id=None,
                statements=[
                    NewIntentStatement(
                        predicate="COMPENSATION.MIN_SALARY", operator="GTE",
                        value=6_000_000, strength="HARD_CONSTRAINT", value_type="MONEY",
                        unknown_policy="REQUIRE_VERIFICATION",
                    )
                ],
            ),
            actor=owner(), now=AT,
        ).intent_version_id

    def make_target(self, key="t1"):
        created = self.targets.create_target(
            CreateSavedCareerTargetCommand(
                actor_id="user-1", twin_id="twin-1", idempotency_key=key,
                display_name="Warehouse", role_focus=["warehouse operator"],
                domain_focus=["logistics"], explicit_keywords=["forklift"],
                scope_definition={"location": "bekasi"}, overrides=[],
            ),
            actor=owner(), now=AT,
        )
        self.compat.assess(
            intent_version_id=self.intent_version,
            target_version_id=created.target_version_id, at=AT,
        )
        return created


@pytest.fixture
def env(tmp_path):
    return Env(tmp_path)


def test_targeted_materialization_records_provenance(env):
    target = env.make_target()
    outcome = env.service.resolve(
        twin_id="twin-1", job=job(), evaluated_at=AT,
        selected_target_id=target.target_id,
    )
    view = env.service.materialize(outcome)

    assert view.scope is ResolvedScope.TARGETED
    assert view.intent_version_id == env.intent_version
    assert view.target_version_id == target.target_version_id
    assert view.routing_decision_id is not None
    assert view.resolver_version
    assert view.input_fingerprint
    assert view.evaluated_at == AT


def test_unscoped_resolution_creates_no_dummy_target(env):
    # no targets → UNSCOPED
    outcome = env.service.resolve(twin_id="twin-1", job=job(), evaluated_at=AT)
    view = env.service.materialize(outcome)
    assert view.scope is ResolvedScope.UNSCOPED
    assert view.target_version_id is None
    # global intent still resolves — HARD min salary present
    predicates = {s["predicate"] for s in view.resolved_statements}
    assert "COMPENSATION.MIN_SALARY" in predicates


def test_ambiguous_routing_does_not_materialize_primary(env):
    env.make_target(key="t1")
    env.make_target(key="t2")
    outcome = env.service.resolve(twin_id="twin-1", job=job(), evaluated_at=AT)
    assert outcome.requires_user_selection is True
    with pytest.raises(Exception):
        env.service.materialize(outcome)


def test_fingerprint_is_order_independent():
    a = resolved_context_fingerprint(
        {"intent_version_id": "iv1", "target_version_id": "tv1",
         "resolver_version": "r1", "job": {"a": 1, "b": 2},
         "temporal": ["s1"], "exceptions": []}
    )
    b = resolved_context_fingerprint(
        {"job": {"b": 2, "a": 1}, "target_version_id": "tv1",
         "intent_version_id": "iv1", "exceptions": [],
         "temporal": ["s1"], "resolver_version": "r1"}
    )
    assert a == b


def test_fingerprint_changes_with_intent_version():
    base = {"intent_version_id": "iv1", "target_version_id": "tv1",
            "resolver_version": "r1", "job": {}, "temporal": [], "exceptions": []}
    changed = dict(base, intent_version_id="iv2")
    assert resolved_context_fingerprint(base) != resolved_context_fingerprint(changed)


def test_fingerprint_changes_with_resolver_version():
    base = {"intent_version_id": "iv1", "target_version_id": "tv1",
            "resolver_version": "r1", "job": {}, "temporal": [], "exceptions": []}
    changed = dict(base, resolver_version="r2")
    assert resolved_context_fingerprint(base) != resolved_context_fingerprint(changed)


def test_same_inputs_reuse_snapshot(env):
    target = env.make_target()
    o1 = env.service.resolve(twin_id="twin-1", job=job(), evaluated_at=AT,
                             selected_target_id=target.target_id)
    v1 = env.service.materialize(o1)
    o2 = env.service.resolve(twin_id="twin-1", job=job(), evaluated_at=AT,
                             selected_target_id=target.target_id)
    v2 = env.service.materialize(o2)
    assert v1.resolved_view_id == v2.resolved_view_id


def test_past_snapshot_unchanged_after_new_intent(env):
    target = env.make_target()
    o1 = env.service.resolve(twin_id="twin-1", job=job(), evaluated_at=AT,
                             selected_target_id=target.target_id)
    v1 = env.service.materialize(o1)

    # activate a new intent version
    env.intent.create_version(
        CreateCareerIntentVersionCommand(
            actor_id="user-1", twin_id="twin-1", idempotency_key="i2",
            expected_active_version_id=env.intent_version,
            statements=[
                NewIntentStatement(
                    predicate="COMPENSATION.MIN_SALARY", operator="GTE",
                    value=8_000_000, strength="HARD_CONSTRAINT", value_type="MONEY",
                    unknown_policy="REQUIRE_VERIFICATION",
                )
            ],
        ),
        actor=owner(), now=AT,
    )

    from onejob.career_context.repositories import CareerContextRepository

    with env.db.connection() as conn:
        stored = CareerContextRepository().get_resolved_view(
            conn, v1.resolved_view_id, twin_id="twin-1"
        )
    assert stored.intent_version_id == env.intent_version
