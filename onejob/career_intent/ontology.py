from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal

from onejob.career_intent.models import (
    IntentCardinality,
    IntentMergePolicy,
    IntentOperator,
    IntentStrength,
    IntentValueType,
    StrictnessDirection,
    UnknownPolicy,
)


ONTOLOGY_VERSION = "career-intent-v1"


@dataclass(frozen=True)
class IntentPredicateDefinition:
    predicate: str
    value_type: IntentValueType
    cardinality: IntentCardinality
    allowed_strengths: tuple[IntentStrength, ...]
    allowed_operators: tuple[IntentOperator, ...]
    merge_policy: IntentMergePolicy
    strictness_direction: StrictnessDirection = StrictnessDirection.NONE
    temporal_allowed: bool = True
    unknown_policy_allowed: bool = False
    ontology_version: str = ONTOLOGY_VERSION

    @property
    def operator(self) -> IntentOperator:
        """Primary (first) allowed operator for this predicate."""
        return self.allowed_operators[0]


_ALL_STRENGTHS = (
    IntentStrength.HARD_CONSTRAINT,
    IntentStrength.STRONG_PREFERENCE,
    IntentStrength.SOFT_PREFERENCE,
)


def _def(
    predicate: str,
    value_type: IntentValueType,
    cardinality: IntentCardinality,
    allowed_operators: tuple[IntentOperator, ...],
    merge_policy: IntentMergePolicy,
    *,
    allowed_strengths: tuple[IntentStrength, ...] = _ALL_STRENGTHS,
    strictness_direction: StrictnessDirection = StrictnessDirection.NONE,
    temporal_allowed: bool = True,
    unknown_policy_allowed: bool = False,
) -> IntentPredicateDefinition:
    return IntentPredicateDefinition(
        predicate=predicate,
        value_type=value_type,
        cardinality=cardinality,
        allowed_strengths=allowed_strengths,
        allowed_operators=allowed_operators,
        merge_policy=merge_policy,
        strictness_direction=strictness_direction,
        temporal_allowed=temporal_allowed,
        unknown_policy_allowed=unknown_policy_allowed,
    )


_REGISTRY: dict[str, IntentPredicateDefinition] = {
    "COMPENSATION.MIN_SALARY": _def(
        "COMPENSATION.MIN_SALARY",
        IntentValueType.MONEY,
        IntentCardinality.ONE,
        (IntentOperator.GTE,),
        IntentMergePolicy.MAX,
        strictness_direction=StrictnessDirection.HIGHER_IS_STRICTER,
        unknown_policy_allowed=True,
    ),
    "COMPENSATION.MAX_SALARY": _def(
        "COMPENSATION.MAX_SALARY",
        IntentValueType.MONEY,
        IntentCardinality.ONE,
        (IntentOperator.LTE,),
        IntentMergePolicy.MIN,
        strictness_direction=StrictnessDirection.LOWER_IS_STRICTER,
        unknown_policy_allowed=True,
    ),
    "COMMUTE.MAX_KM": _def(
        "COMMUTE.MAX_KM",
        IntentValueType.DISTANCE,
        IntentCardinality.ONE,
        (IntentOperator.LTE,),
        IntentMergePolicy.MIN,
        strictness_direction=StrictnessDirection.LOWER_IS_STRICTER,
        unknown_policy_allowed=True,
    ),
    "LOCATION.PREFERRED": _def(
        "LOCATION.PREFERRED",
        IntentValueType.LOCATION_REF_OR_TEXT,
        IntentCardinality.MANY,
        (IntentOperator.IN,),
        IntentMergePolicy.SET,
    ),
    "WORK_MODE.ALLOWED": _def(
        "WORK_MODE.ALLOWED",
        IntentValueType.ENUM,
        IntentCardinality.MANY,
        (IntentOperator.IN,),
        IntentMergePolicy.SET,
    ),
    "EMPLOYMENT_TYPE.PREFERRED": _def(
        "EMPLOYMENT_TYPE.PREFERRED",
        IntentValueType.ENUM,
        IntentCardinality.MANY,
        (IntentOperator.IN,),
        IntentMergePolicy.SET,
    ),
    "SHIFT.AVOID_NIGHT": _def(
        "SHIFT.AVOID_NIGHT",
        IntentValueType.BOOLEAN,
        IntentCardinality.ONE,
        (IntentOperator.EQ,),
        IntentMergePolicy.REPLACE,
        unknown_policy_allowed=True,
    ),
    "ROLE.PREFERRED": _def(
        "ROLE.PREFERRED",
        IntentValueType.TEXT,
        IntentCardinality.MANY,
        (IntentOperator.IN,),
        IntentMergePolicy.SET,
    ),
    "AVAILABILITY.START_DATE": _def(
        "AVAILABILITY.START_DATE",
        IntentValueType.DATE,
        IntentCardinality.ONE,
        (IntentOperator.LTE, IntentOperator.GTE, IntentOperator.EQ),
        IntentMergePolicy.REPLACE,
    ),
}


def get_intent_predicate_definition(
    predicate: str,
) -> IntentPredicateDefinition:
    """Return the typed definition for a predicate.

    Fails closed with ``KeyError`` for unknown predicates so no arbitrary
    expression can enter the intent model.
    """
    return _REGISTRY[predicate]


def is_known_predicate(predicate: str) -> bool:
    return predicate in _REGISTRY


StrictnessResult = Literal["TIGHTER", "EQUAL", "WEAKER", "UNKNOWN"]


def compare_strictness(
    predicate: str,
    old_value: object,
    new_value: object,
) -> StrictnessResult:
    """Compare semantic strictness of two values for a scalar predicate.

    Returns ``EQUAL`` when values are equal, otherwise interprets numeric
    direction according to the ontology's ``strictness_direction``. For
    predicates without a scalar direction, non-equal values are ``UNKNOWN``.
    """
    definition = get_intent_predicate_definition(predicate)

    if old_value == new_value:
        return "EQUAL"

    direction = definition.strictness_direction
    if direction is StrictnessDirection.NONE:
        return "UNKNOWN"

    try:
        old_num = float(old_value)  # type: ignore[arg-type]
        new_num = float(new_value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return "UNKNOWN"

    if direction is StrictnessDirection.HIGHER_IS_STRICTER:
        return "TIGHTER" if new_num > old_num else "WEAKER"
    # LOWER_IS_STRICTER
    return "TIGHTER" if new_num < old_num else "WEAKER"


TemporalState = Literal["FUTURE", "ACTIVE", "EXPIRED"]


def temporal_state(statement, at: datetime) -> TemporalState:
    """Evaluate a statement's temporal state at the exact timestamp.

    - ``effective_from > at`` → FUTURE
    - ``expires_at <= at`` → EXPIRED
    - otherwise → ACTIVE
    """
    effective_from = getattr(statement, "effective_from", None)
    expires_at = getattr(statement, "expires_at", None)

    if effective_from is not None and effective_from > at:
        return "FUTURE"
    if expires_at is not None and expires_at <= at:
        return "EXPIRED"
    return "ACTIVE"
