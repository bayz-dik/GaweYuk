from datetime import datetime, timezone

import pytest

from onejob.career_intent.commands import (
    CareerIntentCommandService,
    CreateCareerIntentVersionCommand,
    NewIntentStatement,
)
from onejob.career_targets.commands import (
    CreateSavedCareerTargetCommand,
    SetTargetLifecycleCommand,
    TargetCommandService,
)
from onejob.career_targets.compatibility import TargetCompatibilityService
from onejob.career_targets.models import (
    RoutingMethod,
    TargetCompatibilityRecord,
    TargetCompatibilityStatus,
)
from onejob.career_targets.routing import (
    ROUTER_V1_WEIGHTS,
    RoutingConfig,
    TargetRoutingService,
)
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
        id="job-1",
        title="Warehouse Operator",
        company="PT Logistik",
        location="Bekasi",
        description="Operate forklift in warehouse logistics.",
        normalized_title="warehouse operator",
        normalized_company="pt logistik",
        normalized_location="bekasi",
        skills=["forklift"],
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

    def make_target(self, *, display_name, role_focus, domain_focus, keywords, scope, key):
        created = self.targets.create_target(
            CreateSavedCareerTargetCommand(
                actor_id="user-1", twin_id="twin-1", idempotency_key=key,
                display_name=display_name, role_focus=role_focus,
                domain_focus=domain_focus, explicit_keywords=keywords,
                scope_definition=scope, overrides=[],
            ),
            actor=owner(), now=AT,
        )
        # mark VALID compatibility against active intent
        self.compat.assess(
            intent_version_id=self.intent_version,
            target_version_id=created.target_version_id,
            at=AT,
        )
        return created


@pytest.fixture
def env(tmp_path):
    return Env(tmp_path)


def test_config_has_versioned_thresholds():
    config = RoutingConfig(
        router_version="target-router-v1",
        minimum_threshold=0.60,
        ambiguity_margin=0.10,
        weights=ROUTER_V1_WEIGHTS,
    )
    assert config.router_version == "target-router-v1"
    assert config.minimum_threshold == 0.60
    assert config.ambiguity_margin == 0.10


def test_clear_winner_auto_routes(env):
    env.make_target(
        display_name="Warehouse", role_focus=["warehouse operator"],
        domain_focus=["logistics"], keywords=["forklift"],
        scope={"location": "bekasi"}, key="t1",
    )
    env.make_target(
        display_name="Accountant", role_focus=["accountant"],
        domain_focus=["finance"], keywords=["tax"],
        scope={"location": "jakarta"}, key="t2",
    )
    decision = env.router.route(
        twin_id="twin-1", intent_version_id=env.intent_version, job=job()
    )
    assert decision.method is RoutingMethod.AUTO_ROUTED
    assert decision.selected_target_version_id is not None


def test_close_top_scores_abstain_as_ambiguous(env):
    env.make_target(
        display_name="Warehouse A", role_focus=["warehouse operator"],
        domain_focus=["logistics"], keywords=["forklift"],
        scope={"location": "bekasi"}, key="t1",
    )
    env.make_target(
        display_name="Warehouse B", role_focus=["warehouse operator"],
        domain_focus=["logistics"], keywords=["forklift"],
        scope={"location": "bekasi"}, key="t2",
    )
    decision = env.router.route(
        twin_id="twin-1", intent_version_id=env.intent_version, job=job()
    )
    assert decision.method is RoutingMethod.AMBIGUOUS
    assert decision.selected_target_version_id is None


def test_low_scores_become_unscoped(env):
    env.make_target(
        display_name="Chef", role_focus=["chef"],
        domain_focus=["culinary"], keywords=["cooking"],
        scope={"location": "surabaya"}, key="t1",
    )
    decision = env.router.route(
        twin_id="twin-1", intent_version_id=env.intent_version, job=job()
    )
    assert decision.method is RoutingMethod.UNSCOPED
    assert decision.selected_target_version_id is None


def test_paused_target_excluded_from_auto_routing(env):
    created = env.make_target(
        display_name="Warehouse", role_focus=["warehouse operator"],
        domain_focus=["logistics"], keywords=["forklift"],
        scope={"location": "bekasi"}, key="t1",
    )
    env.targets.set_lifecycle(
        SetTargetLifecycleCommand(
            actor_id="user-1", twin_id="twin-1", target_id=created.target_id,
            idempotency_key="lc-1", action="PAUSE",
        ),
        actor=owner(), now=AT,
    )
    decision = env.router.route(
        twin_id="twin-1", intent_version_id=env.intent_version, job=job()
    )
    assert decision.method is RoutingMethod.UNSCOPED


def test_stale_compatibility_excluded(env):
    env.make_target(
        display_name="Warehouse", role_focus=["warehouse operator"],
        domain_focus=["logistics"], keywords=["forklift"],
        scope={"location": "bekasi"}, key="t1",
    )
    # route against a different (newer) intent version id → compat is stale
    decision = env.router.route(
        twin_id="twin-1", intent_version_id="intent_version-999", job=job()
    )
    assert decision.method is RoutingMethod.UNSCOPED


def test_deterministic_same_input_same_result(env):
    env.make_target(
        display_name="Warehouse", role_focus=["warehouse operator"],
        domain_focus=["logistics"], keywords=["forklift"],
        scope={"location": "bekasi"}, key="t1",
    )
    d1 = env.router.route(twin_id="twin-1", intent_version_id=env.intent_version, job=job())
    d2 = env.router.route(twin_id="twin-1", intent_version_id=env.intent_version, job=job())
    assert d1.method == d2.method
    assert d1.selected_target_version_id == d2.selected_target_version_id
    assert d1.router_version == d2.router_version == "target-router-v1"


def test_user_selected_wins_over_higher_auto_score(env):
    t_a = env.make_target(
        display_name="Warehouse A", role_focus=["chef"],
        domain_focus=["culinary"], keywords=["cooking"],
        scope={"location": "surabaya"}, key="t1",
    )
    t_b = env.make_target(
        display_name="Warehouse B", role_focus=["warehouse operator"],
        domain_focus=["logistics"], keywords=["forklift"],
        scope={"location": "bekasi"}, key="t2",
    )
    decision = env.router.route(
        twin_id="twin-1", intent_version_id=env.intent_version, job=job(),
        selected_target_id=t_a.target_id,
    )
    assert decision.method is RoutingMethod.USER_SELECTED
    assert decision.selected_target_version_id == t_a.target_version_id
    # alternatives include the other routable target
    assert t_b.target_version_id in {a.target_version_id for a in decision.alternatives}


def test_user_selected_unsatisfiable_target_is_rejected(env):
    from onejob.career_targets.routing import TargetNotRoutable

    # Build an unsatisfiable target and try to select it explicitly.
    created = env.targets.create_target(
        CreateSavedCareerTargetCommand(
            actor_id="user-1", twin_id="twin-1", idempotency_key="tu",
            display_name="Bad", role_focus=["x"], domain_focus=["y"],
            explicit_keywords=[], scope_definition={},
            overrides=[],
        ),
        actor=owner(), now=AT,
    )
    # Persist an UNSATISFIABLE compatibility for the active intent.
    from onejob.career_targets.repositories import SavedCareerTargetRepository

    with env.db.transaction() as conn:
        SavedCareerTargetRepository().save_compatibility(
            conn,
            record=TargetCompatibilityRecord(
                compatibility_id="cmp-bad",
                target_id=created.target_id,
                target_version_id=created.target_version_id,
                against_intent_version_id=env.intent_version,
                status=TargetCompatibilityStatus.UNSATISFIABLE,
                reasons=["impossible"],
                checked_at=AT,
                validator_version="target-compat-v1",
            ),
        )
    with pytest.raises(TargetNotRoutable):
        env.router.route(
            twin_id="twin-1", intent_version_id=env.intent_version, job=job(),
            selected_target_id=created.target_id,
        )
