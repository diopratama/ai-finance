import pytest
from app.services.web_search_service import call_exa_search, search_internet, should_search_internet
from app.services.fire_engine import (
    PORTFOLIO_STRATEGY_PRESETS,
    get_asset_allocation_recommendation,
    evaluate_investment_portfolio,
    normalize_custom_allocations,
    infer_wallet_asset_class,
    is_investment_wallet,
)
from app.investment_ai.sharia_reference import load_sharia_reference, get_issi_universe
from app.investment_ai.orchestrator import (
    normalize_market,
    agent_roles,
    _extract_json_block,
    parse_llm_response,
)


def test_search_internet_fallback_when_no_exa_key(monkeypatch):
    """Verifies that search_internet gracefully executes fallback multi-engine search when Exa is unavailable."""
    monkeypatch.setattr("app.config.settings.EXA_API_KEY", "")
    assert should_search_internet("Berapa harga emas hari ini?") is True
    # Should not raise exception and should return list
    results = search_internet("Saham BBCA IHSG", num_results=2)
    assert isinstance(results, list)


def test_portfolio_strategy_presets_and_custom_allocations():
    """Verifies strategy presets and custom target percentages in FIRE engine."""
    # Check presets existence
    assert "INDEX_ETF_CORE" in PORTFOLIO_STRATEGY_PRESETS
    assert "REAL_ASSET_PROPERTY" in PORTFOLIO_STRATEGY_PRESETS
    assert "HIGH_GROWTH_CRYPTO" in PORTFOLIO_STRATEGY_PRESETS
    assert "SHARIA_REAL_ASSET" in PORTFOLIO_STRATEGY_PRESETS
    assert "CUSTOM" in PORTFOLIO_STRATEGY_PRESETS

    # Test INDEX_ETF_CORE recommendation
    rec_etf = get_asset_allocation_recommendation("MODERATE", strategy="INDEX_ETF_CORE")
    assert rec_etf["strategy"] == "INDEX_ETF_CORE"
    classes = [item["asset_class"] for item in rec_etf["allocations"]]
    assert "INDEX_ETF" in classes

    # Test REAL_ASSET_PROPERTY recommendation
    rec_real = get_asset_allocation_recommendation("MODERATE", strategy="REAL_ASSET_PROPERTY")
    assert rec_real["strategy"] == "REAL_ASSET_PROPERTY"
    real_classes = [item["asset_class"] for item in rec_real["allocations"]]
    assert "REAL_ESTATE" in real_classes
    assert "LAND" in real_classes

    # Test CUSTOM weight normalization
    custom_raw = {"INDEX_ETF": 50, "GOLD": 30, "REAL_ESTATE": 20, "INVALID": 999}
    normalized = normalize_custom_allocations(custom_raw)
    assert "INDEX_ETF" in normalized
    assert "GOLD" in normalized
    assert "REAL_ESTATE" in normalized
    assert "INVALID" not in normalized

    rec_custom = get_asset_allocation_recommendation("MODERATE", strategy="CUSTOM", custom_allocations=custom_raw)
    assert rec_custom["strategy"] == "CUSTOM"
    assert len(rec_custom["allocations"]) == 3


def test_asset_class_inference_for_new_assets():
    """Verifies detection of Index/ETF, Productive Property, and Land."""
    assert infer_wallet_asset_class("Bibit Reksa Dana Indeks IDX30", "INVESTMENT") == "INDEX_ETF"
    assert infer_wallet_asset_class("Kost Eksklusif Dago", "INVESTMENT") == "REAL_ESTATE"
    assert infer_wallet_asset_class("Tanah Kavling Sentul", "INVESTMENT") == "LAND"
    assert infer_wallet_asset_class("Emas Antam Brankas", "INVESTMENT") == "GOLD"
    assert infer_wallet_asset_class("Binance BTC", "INVESTMENT") == "CRYPTO"
    assert is_investment_wallet("Tanah Kavling", "INVESTMENT") is True


def test_evaluate_investment_portfolio_with_strategy_and_real_assets():
    """Verifies portfolio evaluation with real asset illiquidity check and custom strategy."""
    sample_wallets = [
        {"id": "w1", "name": "Kost Bulanan", "type": "INVESTMENT", "balance": 700_000_000, "currency": "IDR", "asset_class": "REAL_ESTATE"},
        {"id": "w2", "name": "Tanah Kavling", "type": "INVESTMENT", "balance": 300_000_000, "currency": "IDR", "asset_class": "LAND"},
        {"id": "w3", "name": "Bibit IDX30", "type": "INVESTMENT", "balance": 100_000_000, "currency": "IDR", "asset_class": "INDEX_ETF"},
        {"id": "w4", "name": "BCA Operasional", "type": "BANK", "balance": 50_000_000, "currency": "IDR"},
    ]

    eval_res = evaluate_investment_portfolio(
        wallets=sample_wallets,
        risk_tolerance="MODERATE",
        liquid_cash_balance=50_000_000,
        strategy="REAL_ASSET_PROPERTY",
    )

    assert eval_res["has_investment_wallets"] is True
    assert eval_res["total_investment_balance"] == 1_100_000_000
    assert eval_res["portfolio_strategy"] == "REAL_ASSET_PROPERTY"

    # Should detect high concentration in illiquid real assets (1,000M / 1,100M > 90%)
    bp_keys = [bp["key"] for bp in eval_res["best_practices"]]
    assert "ILLIQUID_CONCENTRATION" in bp_keys


def test_sharia_reference_and_universe():
    """Verifies that the ISSI sharia universe loads properly from local reference."""
    ref = load_sharia_reference()
    assert ref["total"] > 0
    assert "counts" in ref
    universe = get_issi_universe()
    assert len(universe) > 0


def test_orchestrator_market_and_json_helpers():
    """Verifies orchestrator market normalization, roles, and JSON parser."""
    assert normalize_market("ihsg_syariah") == "ihsg"
    assert normalize_market("crypto") == "crypto"
    assert normalize_market("us_etf") == "us_etf"

    crypto_roles = agent_roles("crypto")
    assert "on_chain_analyst" in crypto_roles

    ihsg_roles = agent_roles("ihsg")
    assert "on_chain_analyst" not in ihsg_roles

    raw_json = '```json\n{"stance": "ACCUMULATE", "confidence_pct": 85}\n```'
    parsed = _extract_json_block(raw_json)
    assert parsed is not None
    assert parsed["stance"] == "ACCUMULATE"
    assert parsed["confidence_pct"] == 85

