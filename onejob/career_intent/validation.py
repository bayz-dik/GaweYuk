from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any

from onejob.career_intent.models import (
    IntentStatementRecord,
    IntentStrength,
    UnknownPolicy,
)
from onejob.career_intent.ontology import (
    get_intent_predicate_definition,
    is_known_predicate,
    temporal_state,
)


VALIDATOR_VERSION = "career-intent-validator-v1"


class UnknownIntentPredicate(ValueError):
    pass


class InvalidTemporalRange(ValueError):
    pass


class InvalidIntentStatement(ValueError):
    pass


class IntentValidationStatus(str, Enum):
    VALID = "VALID"
    VALID_WITH_TENSIONS = "VALID_WITH_TENSIONS"
    UNSATISFIABLE = "UNSATISFIABLE"


@dataclass(frozen=True)
class IntentTension:
    predicates: tuple[str, ...]
    reason: str


@dataclass(frozen=True)
class IntentValidationResult:
    status: str
    active_statements: list[IntentStatementRecord] = field(default_factory=list)
    hard_conflicts: list[IntentTension] = field(default_factory=list)
    tensions: list[IntentTension] = field(default_factory=list)
    validator_version: str = VALIDATOR_VERSION


def validate_statement(statement: IntentStatementRecord) -> None:
    """Validate a single statement against the typed ontology.

    Fails closed on unknown predicates, disallowed operators/strengths,
    unsupported unknown policies, and invalid temporal ranges.
    """
    if not is_known_predicate(statement.predicate):
        raise UnknownIntentPredicate(statement.predicate)

    definition = get_intent_predicate_definition(statement.predicate)

    if statement.operator not in definition.allowed_operators:
        raise InvalidIntentStatement(
            f"operator {statement.operator.value} not allowed for "
            f"{statement.predicate}"
        )

    if statement.strength not in definition.allowed_strengths:
        raise InvalidIntentStatement(
            f"strength {statement.strength.value} not allowed for "
            f"{statement.predicate}"
        )

    if statement.unknown_policy is not None and not definition.unknown_policy_allowed:
        raise InvalidIntentStatement(
            f"unknown_policy not allowed for {statement.predicate}"
        )

    if (
        statement.effective_from is not None
        and statement.expires_at is not None
        and statement.expires_at <= statement.effective_from
    ):
        raise InvalidTemporalRange(
            f"expires_at must be after effective_from for {statement.predicate}"
        )

    if (
        statement.unknown_policy is not None
        and not definition.temporal_allowed
        and (statement.effective_from or statement.expires_at)
    ):
        raise InvalidIntentStatement(
            f"temporal scope not allowed for {statement.predicate}"
        )


def _as_number(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def validate_intent_statements(
    statements: list[IntentStatementRecord],
    at: datetime,
) -> IntentValidationResult:
    """Validate a set of statements for internal consistency at ``at``.

    FUTURE/EXPIRED statements are excluded from the active evaluated set but
    validated individually. Detects impossible HARD salary bounds and records
    HARD-vs-SOFT/STRONG tensions without deleting any statement.
    """
    for statement in statements:
        validate_statement(statement)

    active = [s for s in statements if temporal_state(s, at) == "ACTIVE"]

    hard_conflicts: list[IntentTension] = []
    tensions: list[IntentTension] = []

    # Salary bound analysis: MIN_SALARY (GTE) vs MAX_SALARY (LTE).
    min_salary_hard: float | None = None
    max_salary_hard: float | None = None
    min_salary_any: list[tuple[IntentStrength, float]] = []
    max_salary_any: list[tuple[IntentStrength, float]] = []

    for s in active:
        num = _as_number(s.value)
        if num is None:
            continue
        if s.predicate == "COMPENSATION.MIN_SALARY":
            min_salary_any.append((s.strength, num))
            if s.strength is IntentStrength.HARD_CONSTRAINT:
                min_salary_hard = (
                    num if min_salary_hard is None else max(min_salary_hard, num)
                )
        elif s.predicate == "COMPENSATION.MAX_SALARY":
            max_salary_any.append((s.strength, num))
            if s.strength is IntentStrength.HARD_CONSTRAINT:
                max_salary_hard = (
                    num if max_salary_hard is None else min(max_salary_hard, num)
                )

    # HARD vs HARD impossible salary range.
    if (
        min_salary_hard is not None
        and max_salary_hard is not None
        and min_salary_hard > max_salary_hard
    ):
        hard_conflicts.append(
            IntentTension(
                predicates=(
                    "COMPENSATION.MIN_SALARY",
                    "COMPENSATION.MAX_SALARY",
                ),
                reason=(
                    f"HARD min salary {min_salary_hard:.0f} exceeds HARD max "
                    f"salary {max_salary_hard:.0f}"
                ),
            )
        )

    # HARD vs non-HARD tension on the same salary bound impossibility.
    if not hard_conflicts:
        for strength, min_v in min_salary_any:
            for strength2, max_v in max_salary_any:
                if min_v > max_v:
                    involved = {strength, strength2}
                    if IntentStrength.HARD_CONSTRAINT in involved and involved != {
                        IntentStrength.HARD_CONSTRAINT
                    }:
                        tensions.append(
                            IntentTension(
                                predicates=(
                                    "COMPENSATION.MIN_SALARY",
                                    "COMPENSATION.MAX_SALARY",
                                ),
                                reason=(
                                    "HARD salary bound conflicts with a weaker "
                                    "preference bound"
                                ),
                            )
                        )
                    elif IntentStrength.HARD_CONSTRAINT not in involved:
                        tensions.append(
                            IntentTension(
                                predicates=(
                                    "COMPENSATION.MIN_SALARY",
                                    "COMPENSATION.MAX_SALARY",
                                ),
                                reason="soft/strong salary preference tension",
                            )
                        )

    if hard_conflicts:
        status = IntentValidationStatus.UNSATISFIABLE.value
    elif tensions:
        status = IntentValidationStatus.VALID_WITH_TENSIONS.value
    else:
        status = IntentValidationStatus.VALID.value

    return IntentValidationResult(
        status=status,
        active_statements=active,
        hard_conflicts=hard_conflicts,
        tensions=tensions,
    )
