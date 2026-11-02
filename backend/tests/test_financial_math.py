import pytest
from app.services.fire_engine import (
    calculate_fire_metrics,
    calculate_financial_health_score,
    get_asset_allocation_recommendation,
)


def test_fire_metrics_rule_of_25():
    # 10 million IDR monthly expense -> 120 million annual -> 3 billion FIRE number
    metrics = calculate_fire_metrics(
        current_age=30,
        target_fire_age=50,
        monthly_expenses=10_000_000,
        current_net_worth=300_000_000,
        monthly_savings=5_000_000,
    )
    assert metrics["fire_number"] == 3_000_000_000.0
    assert metrics["annual_expenses"] == 120_000_000.0
    assert metrics["progress_percentage"] == 10.0
    assert metrics["years_to_target_age"] == 20


def test_financial_health_scoring():
    # Healthy user with 6 months emergency fund, >20% savings margin, and low debt
    score_data = calculate_financial_health_score(
        total_assets=100_000_000,
        total_debts=2_000_000,
        monthly_income=20_000_000,
        monthly_expenses=10_000_000,
        emergency_fund=60_000_000,
        is_married=False,
    )
    assert score_data["score"] >= 80
    assert score_data["status"] == "EXCELLENT"
    assert score_data["emergency_fund"]["is_sufficient"] is True


def test_asset_allocation_recommendations():
    cons = get_asset_allocation_recommendation("CONSERVATIVE")
    mod = get_asset_allocation_recommendation("MODERATE")
    agg = get_asset_allocation_recommendation("AGGRESSIVE")

    assert sum(a["percentage"] for a in cons["allocations"]) == 100
    assert sum(a["percentage"] for a in mod["allocations"]) == 100
    assert sum(a["percentage"] for a in agg["allocations"]) == 100

