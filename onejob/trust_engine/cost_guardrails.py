from __future__ import annotations

from dataclasses import dataclass

PRE_REVENUE_ESSENTIAL_CAP_IDR = 100_000
REVENUE_COST_CAP_RATIO = 0.20
TARGET_GROSS_MARGIN_RATIO = 0.80
AI_SPIKE_MULTIPLIER = 2.0
COST_PER_SUCCESS_WORSENING_MULTIPLIER = 1.25


@dataclass(frozen=True)
class BudgetSnapshot:
    realized_revenue_30d: int
    recurring_paid_spend_monthly: int
    essential_emergency_spend_monthly: int
    tech_ai_infra_spend_30d: int
    ai_spend_30d: int
    previous_ai_spend_30d: int = 0
    successful_applications_30d: int = 0
    previous_cost_per_success_idr: float | None = None


@dataclass(frozen=True)
class PaidDependencyRequest:
    name: str
    incremental_cost_30d_idr: int
    measurable_value: bool
    fallback_available: bool
    monetization_justification: str
    kill_switch_available: bool


@dataclass(frozen=True)
class CostGuardrailDecision:
    allowed: bool
    reasons: tuple[str, ...]
    monthly_cap_idr: int
    cost_ratio: float | None
    gross_margin_ratio: float | None
    circuit_breaker: bool


def _validate_non_negative(snapshot: BudgetSnapshot) -> None:
    values = (
        snapshot.realized_revenue_30d,
        snapshot.recurring_paid_spend_monthly,
        snapshot.essential_emergency_spend_monthly,
        snapshot.tech_ai_infra_spend_30d,
        snapshot.ai_spend_30d,
        snapshot.previous_ai_spend_30d,
        snapshot.successful_applications_30d,
    )
    if any(value < 0 for value in values):
        raise ValueError("cost and revenue values must be non-negative")


def evaluate_budget(snapshot: BudgetSnapshot) -> CostGuardrailDecision:
    _validate_non_negative(snapshot)
    reasons: list[str] = []
    breaker = False

    if snapshot.realized_revenue_30d <= 0:
        cap = PRE_REVENUE_ESSENTIAL_CAP_IDR
        if snapshot.recurring_paid_spend_monthly > 0:
            reasons.append("PRE_REVENUE_RECURRING_PAID_SPEND")
        if (
            snapshot.essential_emergency_spend_monthly
            > PRE_REVENUE_ESSENTIAL_CAP_IDR
        ):
            reasons.append("PRE_REVENUE_ESSENTIAL_CAP_EXCEEDED")
        return CostGuardrailDecision(
            allowed=not reasons,
            reasons=tuple(reasons),
            monthly_cap_idr=cap,
            cost_ratio=None,
            gross_margin_ratio=None,
            circuit_breaker=False,
        )

    cap = int(snapshot.realized_revenue_30d * REVENUE_COST_CAP_RATIO)
    ratio = snapshot.tech_ai_infra_spend_30d / snapshot.realized_revenue_30d
    gross_margin = 1.0 - ratio

    if ratio > REVENUE_COST_CAP_RATIO:
        reasons.append("REVENUE_COST_CAP_EXCEEDED")
        breaker = True

    if (
        snapshot.previous_ai_spend_30d > 0
        and snapshot.ai_spend_30d
        > snapshot.previous_ai_spend_30d * AI_SPIKE_MULTIPLIER
    ):
        reasons.append("AI_COST_SPIKE")
        breaker = True

    if (
        snapshot.successful_applications_30d > 0
        and snapshot.previous_cost_per_success_idr is not None
    ):
        current_cost_per_success = (
            snapshot.tech_ai_infra_spend_30d
            / snapshot.successful_applications_30d
        )
        if (
            current_cost_per_success
            > snapshot.previous_cost_per_success_idr
            * COST_PER_SUCCESS_WORSENING_MULTIPLIER
        ):
            reasons.append("COST_PER_SUCCESS_WORSENED")
            breaker = True

    return CostGuardrailDecision(
        allowed=not reasons,
        reasons=tuple(reasons),
        monthly_cap_idr=cap,
        cost_ratio=round(ratio, 6),
        gross_margin_ratio=round(gross_margin, 6),
        circuit_breaker=breaker,
    )


def evaluate_paid_dependency(
    snapshot: BudgetSnapshot,
    request: PaidDependencyRequest,
) -> CostGuardrailDecision:
    reasons: list[str] = []

    if not request.measurable_value:
        reasons.append("MEASURABLE_VALUE_REQUIRED")
    if not request.fallback_available:
        reasons.append("FALLBACK_REQUIRED")
    if not request.monetization_justification.strip():
        reasons.append("MONETIZATION_JUSTIFICATION_REQUIRED")
    if not request.kill_switch_available:
        reasons.append("KILL_SWITCH_REQUIRED")

    projected = BudgetSnapshot(
        realized_revenue_30d=snapshot.realized_revenue_30d,
        recurring_paid_spend_monthly=snapshot.recurring_paid_spend_monthly,
        essential_emergency_spend_monthly=snapshot.essential_emergency_spend_monthly,
        tech_ai_infra_spend_30d=(
            snapshot.tech_ai_infra_spend_30d
            + request.incremental_cost_30d_idr
        ),
        ai_spend_30d=snapshot.ai_spend_30d,
        previous_ai_spend_30d=snapshot.previous_ai_spend_30d,
        successful_applications_30d=snapshot.successful_applications_30d,
        previous_cost_per_success_idr=snapshot.previous_cost_per_success_idr,
    )

    budget = evaluate_budget(projected)
    reasons.extend(budget.reasons)

    return CostGuardrailDecision(
        allowed=not reasons,
        reasons=tuple(dict.fromkeys(reasons)),
        monthly_cap_idr=budget.monthly_cap_idr,
        cost_ratio=budget.cost_ratio,
        gross_margin_ratio=budget.gross_margin_ratio,
        circuit_breaker=budget.circuit_breaker,
    )
