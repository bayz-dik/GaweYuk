from onejob.trust_engine.cost_guardrails import (
    BudgetSnapshot,
    PaidDependencyRequest,
    evaluate_budget,
    evaluate_paid_dependency,
)

def test_pre_revenue_recurring_paid_spend_is_zero():
    result = evaluate_budget(
        BudgetSnapshot(
            realized_revenue_30d=0,
            recurring_paid_spend_monthly=1,
            essential_emergency_spend_monthly=0,
            tech_ai_infra_spend_30d=0,
            ai_spend_30d=0,
        )
    )
    assert not result.allowed
    assert "PRE_REVENUE_RECURRING_PAID_SPEND" in result.reasons

def test_pre_revenue_essential_emergency_within_100k_is_allowed():
    result = evaluate_budget(
        BudgetSnapshot(
            realized_revenue_30d=0,
            recurring_paid_spend_monthly=0,
            essential_emergency_spend_monthly=100_000,
            tech_ai_infra_spend_30d=0,
            ai_spend_30d=0,
        )
    )
    assert result.allowed
    assert result.monthly_cap_idr == 100_000

def test_pre_revenue_essential_emergency_over_100k_is_blocked():
    result = evaluate_budget(
        BudgetSnapshot(
            realized_revenue_30d=0,
            recurring_paid_spend_monthly=0,
            essential_emergency_spend_monthly=100_001,
            tech_ai_infra_spend_30d=0,
            ai_spend_30d=0,
        )
    )
    assert not result.allowed
    assert "PRE_REVENUE_ESSENTIAL_CAP_EXCEEDED" in result.reasons

def test_post_revenue_cost_cap_is_20_percent():
    result = evaluate_budget(
        BudgetSnapshot(
            realized_revenue_30d=1_000_000,
            recurring_paid_spend_monthly=0,
            essential_emergency_spend_monthly=0,
            tech_ai_infra_spend_30d=200_000,
            ai_spend_30d=50_000,
        )
    )
    assert result.allowed
    assert result.monthly_cap_idr == 200_000
    assert result.cost_ratio == 0.20
    assert result.gross_margin_ratio == 0.80

def test_post_revenue_over_20_percent_trips_circuit_breaker():
    result = evaluate_budget(
        BudgetSnapshot(
            realized_revenue_30d=1_000_000,
            recurring_paid_spend_monthly=0,
            essential_emergency_spend_monthly=0,
            tech_ai_infra_spend_30d=200_001,
            ai_spend_30d=50_000,
        )
    )
    assert not result.allowed
    assert result.circuit_breaker
    assert "REVENUE_COST_CAP_EXCEEDED" in result.reasons

def test_ai_spike_trips_circuit_breaker():
    result = evaluate_budget(
        BudgetSnapshot(
            realized_revenue_30d=2_000_000,
            recurring_paid_spend_monthly=0,
            essential_emergency_spend_monthly=0,
            tech_ai_infra_spend_30d=100_000,
            ai_spend_30d=90_000,
            previous_ai_spend_30d=40_000,
        )
    )
    assert not result.allowed
    assert result.circuit_breaker
    assert "AI_COST_SPIKE" in result.reasons

def test_cost_per_success_worsening_trips_circuit_breaker():
    result = evaluate_budget(
        BudgetSnapshot(
            realized_revenue_30d=2_000_000,
            recurring_paid_spend_monthly=0,
            essential_emergency_spend_monthly=0,
            tech_ai_infra_spend_30d=100_000,
            ai_spend_30d=20_000,
            successful_applications_30d=2,
            previous_cost_per_success_idr=30_000,
        )
    )
    assert not result.allowed
    assert result.circuit_breaker
    assert "COST_PER_SUCCESS_WORSENED" in result.reasons

def test_paid_dependency_requires_measurable_value_fallback_and_kill_switch():
    snapshot = BudgetSnapshot(
        realized_revenue_30d=1_000_000,
        recurring_paid_spend_monthly=0,
        essential_emergency_spend_monthly=0,
        tech_ai_infra_spend_30d=50_000,
        ai_spend_30d=10_000,
    )
    request = PaidDependencyRequest(
        name="paid-ai",
        incremental_cost_30d_idr=10_000,
        measurable_value=False,
        fallback_available=False,
        monetization_justification="",
        kill_switch_available=False,
    )
    result = evaluate_paid_dependency(snapshot, request)
    assert not result.allowed
    assert {
        "MEASURABLE_VALUE_REQUIRED",
        "FALLBACK_REQUIRED",
        "MONETIZATION_JUSTIFICATION_REQUIRED",
        "KILL_SWITCH_REQUIRED",
    } <= set(result.reasons)

def test_paid_dependency_within_budget_and_all_safeguards_is_allowed():
    snapshot = BudgetSnapshot(
        realized_revenue_30d=1_000_000,
        recurring_paid_spend_monthly=0,
        essential_emergency_spend_monthly=0,
        tech_ai_infra_spend_30d=100_000,
        ai_spend_30d=20_000,
    )
    request = PaidDependencyRequest(
        name="paid-ai",
        incremental_cost_30d_idr=20_000,
        measurable_value=True,
        fallback_available=True,
        monetization_justification="improves paid conversion",
        kill_switch_available=True,
    )
    result = evaluate_paid_dependency(snapshot, request)
    assert result.allowed

def test_cap_is_ceiling_not_spending_target():
    result = evaluate_budget(
        BudgetSnapshot(
            realized_revenue_30d=10_000_000,
            recurring_paid_spend_monthly=0,
            essential_emergency_spend_monthly=0,
            tech_ai_infra_spend_30d=50_000,
            ai_spend_30d=5_000,
        )
    )
    assert result.allowed
    assert result.monthly_cap_idr == 2_000_000
    assert result.cost_ratio == 0.005
