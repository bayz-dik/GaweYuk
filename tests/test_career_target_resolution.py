from datetime import datetime, timezone

import pytest

from onejob.career_intent.models import (
    IntentOperator,
    IntentStatementRecord,
    IntentStrength,
)
from onejob.career_targets.models import OverrideOperation, TargetIntentOverrideRecord
from onejob.career_targets.resolver import (
    HardConstraintExceptionRequired,
    resolve_target_policy,
)


AT = datetime(2026, 8, 21, 12, tzinfo=timezone.utc)


def statement(predicate, operator, value, strength, value_type="MONEY", statement_id=None):
    return IntentStatementRecord(
        statement_id=statement_id or f"is-{predicate}",
        intent_version_id="iv-1",
        predicate=predicate,
        operator=IntentOperator(operator),
        value=value,
        value_type=value_type,
        strength=IntentStrength(strength),
        provenance={},
    )


def hard_min_salary(value):
    return statement("COMPENSATION.MIN_SALARY", "GTE", value, "HARD_CONSTRAINT")


def preferred_locations(values):
    return statement(
        "LOCATION.PREFERRED",
        "IN",
        list(values),
        "STRONG_PREFERENCE",
        value_type="LOCATION_REF_OR_TEXT",
        statement_id="is-loc",
    )


def override(predicate, operation, value=None, strength=None, authority=None, overrides_statement_id=None):
    return TargetIntentOverrideRecord(
        override_id=f"ov-{predicate}-{operation}",
        target_version_id="tv-1",
        predicate=predicate,
        operation=OverrideOperation(operation),
        value=value,
        strength=IntentStrength(strength) if strength else None,
        overrides_statement_id=overrides_statement_id,
        explicit_exception_authority=authority,
    )


def replace_override(predicate, value):
    return override(predicate, "REPLACE", value=value, overrides_statement_id=f"is-{predicate}")


def remove_override(predicate, value):
    return override(predicate, "REMOVE", value=value, overrides_statement_id="is-loc")


# ---------------------------------------------------------------------------
# Typed override merge
# ---------------------------------------------------------------------------


def test_many_value_remove_is_explicit_and_deterministic():
    resolved = resolve_target_policy(
        intent_statements=[preferred_locations(["Cikarang", "Bekasi", "Karawang"])],
        target_overrides=[remove_override("LOCATION.PREFERRED", "Karawang")],
        at=AT,
        exception_authority=None,
    )
    assert resolved.value_for("LOCATION.PREFERRED") == ["Cikarang", "Bekasi"]


def test_many_value_add_appends_deterministically():
    resolved = resolve_target_policy(
        intent_statements=[preferred_locations(["Cikarang"])],
        target_overrides=[override("LOCATION.PREFERRED", "ADD", value="Bekasi")],
        at=AT,
        exception_authority=None,
    )
    assert resolved.value_for("LOCATION.PREFERRED") == ["Cikarang", "Bekasi"]


def test_inherited_value_passes_through_when_no_override():
    resolved = resolve_target_policy(
        intent_statements=[hard_min_salary(6_000_000)],
        target_overrides=[],
        at=AT,
        exception_authority=None,
    )
    assert resolved.value_for("COMPENSATION.MIN_SALARY") == 6_000_000
    assert resolved.effect_for("COMPENSATION.MIN_SALARY") == "INHERIT"


def test_target_can_tighten_hard_min_salary_without_exception():
    resolved = resolve_target_policy(
        intent_statements=[hard_min_salary(6_000_000)],
        target_overrides=[replace_override("COMPENSATION.MIN_SALARY", 7_000_000)],
        at=AT,
        exception_authority=None,
    )
    assert resolved.value_for("COMPENSATION.MIN_SALARY") == 7_000_000
    assert resolved.effect_for("COMPENSATION.MIN_SALARY") == "TIGHTENED"


def test_target_cannot_weaken_hard_min_salary_with_plain_replace():
    with pytest.raises(HardConstraintExceptionRequired):
        resolve_target_policy(
            intent_statements=[hard_min_salary(6_000_000)],
            target_overrides=[replace_override("COMPENSATION.MIN_SALARY", 5_000_000)],
            at=AT,
            exception_authority=None,
        )


def test_plain_remove_of_hard_scalar_requires_exception():
    with pytest.raises(HardConstraintExceptionRequired):
        resolve_target_policy(
            intent_statements=[hard_min_salary(6_000_000)],
            target_overrides=[
                override("COMPENSATION.MIN_SALARY", "CLEAR", overrides_statement_id="is-COMPENSATION.MIN_SALARY")
            ],
            at=AT,
            exception_authority=None,
        )


# ---------------------------------------------------------------------------
# Explicit exception authority
# ---------------------------------------------------------------------------


def test_explicit_exception_by_user_weakens_hard_rule():
    resolved = resolve_target_policy(
        intent_statements=[hard_min_salary(6_000_000)],
        target_overrides=[
            override(
                "COMPENSATION.MIN_SALARY",
                "EXPLICIT_EXCEPTION",
                value=5_000_000,
                authority="USER",
                overrides_statement_id="is-COMPENSATION.MIN_SALARY",
            )
        ],
        at=AT,
        exception_authority={"actor_type": "USER", "is_owner": True},
    )
    assert resolved.value_for("COMPENSATION.MIN_SALARY") == 5_000_000
    assert resolved.effect_for("COMPENSATION.MIN_SALARY") == "WEAKENED_BY_EXPLICIT_EXCEPTION"
    # lineage retains overridden statement id
    assert resolved.source_statement_for("COMPENSATION.MIN_SALARY") == "is-COMPENSATION.MIN_SALARY"


def test_system_actor_cannot_authorize_explicit_exception():
    with pytest.raises(HardConstraintExceptionRequired):
        resolve_target_policy(
            intent_statements=[hard_min_salary(6_000_000)],
            target_overrides=[
                override(
                    "COMPENSATION.MIN_SALARY",
                    "EXPLICIT_EXCEPTION",
                    value=5_000_000,
                    authority="SYSTEM",
                    overrides_statement_id="is-COMPENSATION.MIN_SALARY",
                )
            ],
            at=AT,
            exception_authority={"actor_type": "SYSTEM", "is_owner": True},
        )


def test_ai_actor_cannot_authorize_explicit_exception():
    with pytest.raises(HardConstraintExceptionRequired):
        resolve_target_policy(
            intent_statements=[hard_min_salary(6_000_000)],
            target_overrides=[
                override(
                    "COMPENSATION.MIN_SALARY",
                    "EXPLICIT_EXCEPTION",
                    value=5_000_000,
                    authority="AI",
                    overrides_statement_id="is-COMPENSATION.MIN_SALARY",
                )
            ],
            at=AT,
            exception_authority={"actor_type": "AI", "is_owner": True},
        )


# ---------------------------------------------------------------------------
# Strength changes
# ---------------------------------------------------------------------------


def test_local_soft_to_strong_promotion_is_allowed_for_user():
    resolved = resolve_target_policy(
        intent_statements=[
            statement("SHIFT.AVOID_NIGHT", "EQ", True, "SOFT_PREFERENCE", value_type="BOOLEAN", statement_id="is-shift")
        ],
        target_overrides=[
            override(
                "SHIFT.AVOID_NIGHT",
                "REPLACE",
                value=True,
                strength="STRONG_PREFERENCE",
                overrides_statement_id="is-shift",
            )
        ],
        at=AT,
        exception_authority={"actor_type": "USER", "is_owner": True},
    )
    assert resolved.strength_for("SHIFT.AVOID_NIGHT") == "STRONG_PREFERENCE"


def test_inherited_hard_to_soft_requires_explicit_exception():
    with pytest.raises(HardConstraintExceptionRequired):
        resolve_target_policy(
            intent_statements=[hard_min_salary(6_000_000)],
            target_overrides=[
                override(
                    "COMPENSATION.MIN_SALARY",
                    "REPLACE",
                    value=6_000_000,
                    strength="SOFT_PREFERENCE",
                    overrides_statement_id="is-COMPENSATION.MIN_SALARY",
                )
            ],
            at=AT,
            exception_authority=None,
        )


def test_resolver_does_not_mutate_source_records():
    statements = [hard_min_salary(6_000_000)]
    resolve_target_policy(
        intent_statements=statements,
        target_overrides=[replace_override("COMPENSATION.MIN_SALARY", 7_000_000)],
        at=AT,
        exception_authority=None,
    )
    assert statements[0].value == 6_000_000
