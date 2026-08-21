from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from onejob.career_intent.models import (
    IntentCardinality,
    IntentStatementRecord,
    IntentStrength,
)
from onejob.career_intent.ontology import (
    compare_strictness,
    get_intent_predicate_definition,
    temporal_state,
)
from onejob.career_targets.models import (
    OverrideOperation,
    TargetIntentOverrideRecord,
)
from onejob.career_twin.errors import CareerTwinError


RESOLVER_VERSION = "career-target-resolver-v1"


class HardConstraintExceptionRequired(CareerTwinError):
    pass


@dataclass(frozen=True)
class ResolvedEntry:
    predicate: str
    value: Any
    strength: str
    value_type: str
    unknown_policy: str | None
    effect: str
    source_statement_id: str | None
    override_id: str | None


@dataclass(frozen=True)
class ResolvedPolicyDraft:
    entries: dict[str, ResolvedEntry] = field(default_factory=dict)

    def value_for(self, predicate: str) -> Any:
        return self.entries[predicate].value

    def effect_for(self, predicate: str) -> str:
        return self.entries[predicate].effect

    def strength_for(self, predicate: str) -> str:
        return self.entries[predicate].strength

    def source_statement_for(self, predicate: str) -> str | None:
        return self.entries[predicate].source_statement_id

    def as_statements(self) -> list[ResolvedEntry]:
        return list(self.entries.values())


def _authority_is_user(exception_authority: dict | None) -> bool:
    if not exception_authority:
        return False
    return (
        exception_authority.get("actor_type") == "USER"
        and bool(exception_authority.get("is_owner"))
    )


def _strength_rank(strength: str) -> int:
    return {
        IntentStrength.SOFT_PREFERENCE.value: 1,
        IntentStrength.STRONG_PREFERENCE.value: 2,
        IntentStrength.HARD_CONSTRAINT.value: 3,
    }[strength]


def resolve_target_policy(
    *,
    intent_statements: list[IntentStatementRecord],
    target_overrides: list[TargetIntentOverrideRecord],
    at: datetime,
    exception_authority: dict | None,
) -> ResolvedPolicyDraft:
    """Deterministically resolve effective target policy.

    Layers the active Career Intent statements with typed target overrides,
    obeying ontology cardinality and merge semantics. Tightening an inherited
    HARD constraint is allowed; weakening/removing it or weakening its strength
    requires an authorized-user EXPLICIT_EXCEPTION. The resolver never mutates
    source records.
    """
    # Temporal filter on inherited statements.
    active_statements = [
        s for s in intent_statements if temporal_state(s, at) == "ACTIVE"
    ]

    entries: dict[str, ResolvedEntry] = {}
    for s in active_statements:
        entries[s.predicate] = ResolvedEntry(
            predicate=s.predicate,
            value=s.value,
            strength=s.strength.value,
            value_type=s.value_type,
            unknown_policy=(
                s.unknown_policy.value if s.unknown_policy is not None else None
            ),
            effect="INHERIT",
            source_statement_id=s.statement_id,
            override_id=None,
        )

    # Temporal filter on overrides.
    active_overrides = [
        o
        for o in target_overrides
        if temporal_state(o, at) == "ACTIVE"
    ]

    for override in active_overrides:
        predicate = override.predicate
        definition = get_intent_predicate_definition(predicate)
        inherited = entries.get(predicate)
        inherited_is_hard = (
            inherited is not None
            and inherited.strength == IntentStrength.HARD_CONSTRAINT.value
        )

        if definition.cardinality is IntentCardinality.MANY:
            entries[predicate] = _apply_many_override(
                definition, inherited, override
            )
            continue

        # Scalar predicate.
        entries[predicate] = _apply_scalar_override(
            predicate,
            inherited,
            inherited_is_hard,
            override,
            exception_authority,
        )

    return ResolvedPolicyDraft(entries=entries)


def _apply_many_override(definition, inherited, override) -> ResolvedEntry:
    current: list[Any] = list(inherited.value) if inherited is not None else []
    value_type = inherited.value_type if inherited else "LOCATION_REF_OR_TEXT"
    strength = (
        inherited.strength if inherited else IntentStrength.SOFT_PREFERENCE.value
    )
    op = override.operation

    if op is OverrideOperation.ADD:
        result = current + [
            v for v in _as_list(override.value) if v not in current
        ]
        effect = "ADDED"
    elif op is OverrideOperation.REMOVE:
        remove = set(_as_list(override.value))
        result = [v for v in current if v not in remove]
        effect = "REMOVED"
    elif op is OverrideOperation.CLEAR:
        result = []
        effect = "CLEARED"
    elif op is OverrideOperation.REPLACE:
        result = _as_list(override.value)
        effect = "REPLACED"
    else:  # INHERIT / EXPLICIT_EXCEPTION on set
        result = _as_list(override.value) if override.value is not None else current
        effect = "INHERIT"

    return ResolvedEntry(
        predicate=override.predicate,
        value=result,
        strength=override.strength.value if override.strength else strength,
        value_type=value_type,
        unknown_policy=inherited.unknown_policy if inherited else None,
        effect=effect,
        source_statement_id=override.overrides_statement_id
        or (inherited.source_statement_id if inherited else None),
        override_id=override.override_id,
    )


def _apply_scalar_override(
    predicate,
    inherited,
    inherited_is_hard,
    override,
    exception_authority,
) -> ResolvedEntry:
    op = override.operation

    inherited_value = inherited.value if inherited else None
    inherited_strength = (
        inherited.strength if inherited else IntentStrength.SOFT_PREFERENCE.value
    )
    value_type = inherited.value_type if inherited else "MONEY"
    unknown_policy = inherited.unknown_policy if inherited else None
    source_statement_id = (
        override.overrides_statement_id
        or (inherited.source_statement_id if inherited else None)
    )

    if op is OverrideOperation.EXPLICIT_EXCEPTION:
        if not _authority_is_user(exception_authority):
            raise HardConstraintExceptionRequired(
                f"explicit exception for {predicate} requires authorized user"
            )
        return ResolvedEntry(
            predicate=predicate,
            value=override.value,
            strength=override.strength.value
            if override.strength
            else inherited_strength,
            value_type=value_type,
            unknown_policy=unknown_policy,
            effect="WEAKENED_BY_EXPLICIT_EXCEPTION",
            source_statement_id=source_statement_id,
            override_id=override.override_id,
        )

    if op in (OverrideOperation.CLEAR, OverrideOperation.REMOVE):
        if inherited_is_hard:
            raise HardConstraintExceptionRequired(
                f"removing inherited HARD constraint {predicate} requires "
                "an explicit exception"
            )
        return ResolvedEntry(
            predicate=predicate,
            value=None,
            strength=inherited_strength,
            value_type=value_type,
            unknown_policy=unknown_policy,
            effect="CLEARED",
            source_statement_id=source_statement_id,
            override_id=override.override_id,
        )

    if op is OverrideOperation.REPLACE:
        new_strength = (
            override.strength.value if override.strength else inherited_strength
        )
        # Strength weakening of an inherited HARD requires explicit exception.
        if inherited_is_hard and override.strength is not None:
            if _strength_rank(new_strength) < _strength_rank(
                IntentStrength.HARD_CONSTRAINT.value
            ):
                raise HardConstraintExceptionRequired(
                    f"weakening inherited HARD strength on {predicate} requires "
                    "an explicit exception"
                )

        effect = "REPLACED"
        if inherited_is_hard and inherited_value is not None:
            direction = compare_strictness(
                predicate, inherited_value, override.value
            )
            if direction == "WEAKER":
                raise HardConstraintExceptionRequired(
                    f"weakening inherited HARD value on {predicate} requires "
                    "an explicit exception"
                )
            effect = "TIGHTENED" if direction == "TIGHTER" else "EQUAL"

        return ResolvedEntry(
            predicate=predicate,
            value=override.value,
            strength=new_strength,
            value_type=value_type,
            unknown_policy=unknown_policy,
            effect=effect,
            source_statement_id=source_statement_id,
            override_id=override.override_id,
        )

    if op is OverrideOperation.ADD:
        # ADD on a scalar behaves like REPLACE of value.
        return ResolvedEntry(
            predicate=predicate,
            value=override.value,
            strength=override.strength.value
            if override.strength
            else inherited_strength,
            value_type=value_type,
            unknown_policy=unknown_policy,
            effect="ADDED",
            source_statement_id=source_statement_id,
            override_id=override.override_id,
        )

    # INHERIT
    return ResolvedEntry(
        predicate=predicate,
        value=inherited_value,
        strength=inherited_strength,
        value_type=value_type,
        unknown_policy=unknown_policy,
        effect="INHERIT",
        source_statement_id=source_statement_id,
        override_id=override.override_id,
    )


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, (list, tuple)):
        return list(value)
    return [value]
