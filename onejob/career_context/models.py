from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ConstraintResult(str, Enum):
    SATISFIED = "SATISFIED"
    VIOLATED = "VIOLATED"
    UNKNOWN = "UNKNOWN"


class PolicyGateStatus(str, Enum):
    ELIGIBLE = "ELIGIBLE"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"
    BLOCKED = "BLOCKED"
    INVALID_CONTEXT = "INVALID_CONTEXT"


class ResolvedScope(str, Enum):
    TARGETED = "TARGETED"
    UNSCOPED = "UNSCOPED"


class ResolvedStatement(BaseModel):
    model_config = ConfigDict(frozen=True)

    predicate: str
    operator: str
    value: Any
    strength: str
    value_type: str
    unknown_policy: str | None = None
    source_statement_id: str | None = None
    effect: str = "INHERIT"
    provenance: dict[str, Any] = Field(default_factory=dict)


class ResolvedTargetViewRecord(BaseModel):
    model_config = ConfigDict(frozen=True)

    resolved_view_id: str
    twin_id: str
    intent_version_id: str
    target_version_id: str | None
    routing_decision_id: str | None
    scope: ResolvedScope
    resolved_statements: list[dict[str, Any]] = Field(default_factory=list)
    applied_overrides: list[dict[str, Any]] = Field(default_factory=list)
    explicit_exceptions: list[dict[str, Any]] = Field(default_factory=list)
    active_temporal_statements: list[dict[str, Any]] = Field(
        default_factory=list
    )
    tensions: list[dict[str, Any]] = Field(default_factory=list)
    validation_status: str
    resolver_version: str
    evaluated_at: datetime
    input_fingerprint: str


class ConstraintAssessment(BaseModel):
    model_config = ConfigDict(frozen=True)

    assessment_id: str
    resolved_view_id: str
    statement_id: str
    result: ConstraintResult
    observed_value: Any | None = None
    evidence_status: str
    unknown_reason: str | None = None
    required_action: str | None = None
    reasons: list[str] = Field(default_factory=list)
    evaluator_version: str


class PolicyGateResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    status: PolicyGateStatus
    hard_violations: list[str] = Field(default_factory=list)
    hard_unknowns: list[str] = Field(default_factory=list)
    strong_tradeoffs: list[str] = Field(default_factory=list)
    soft_signals: list[str] = Field(default_factory=list)
    reasons: list[str] = Field(default_factory=list)


class EvaluationContext(BaseModel):
    model_config = ConfigDict(frozen=True)

    career_twin_projection: dict[str, Any] = Field(default_factory=dict)
    resolved_target_view: ResolvedTargetViewRecord
    constraint_assessments: list[ConstraintAssessment] = Field(
        default_factory=list
    )
    hard_gate_status: PolicyGateStatus
    strong_preference_signals: list[str] = Field(default_factory=list)
    soft_preference_signals: list[str] = Field(default_factory=list)
    provenance: dict[str, Any] = Field(default_factory=dict)
    context_version: str = "career-context-v1"
