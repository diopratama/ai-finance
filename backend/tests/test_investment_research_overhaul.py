"""Tests verifying the wealth-compounding & fundamental overhaul of Investment Research."""

import inspect
from pathlib import Path
from unittest.mock import patch

import pandas as pd

import app.investment_ai.fundamental_data as fd
import app.investment_ai.market_data as md
import app.investment_ai.orchestrator as orch
import app.investment_ai.quant_screener as qs


def test_statement_piotroski_and_altman_scores():
    # Build minimal 2-year financial statement DataFrames (newest column first)
    income = pd.DataFrame(
        {
            "2025": [120.0, 1000.0, 450.0, 180.0],
            "2024": [100.0, 880.0, 380.0, 150.0],
        },
        index=["Net Income", "Total Revenue", "Gross Profit", "EBIT"],
    )
    balance_sheet = pd.DataFrame(
        {
            "2025": [1000.0, 180.0, 350.0, 150.0, 100.0, 300.0, 400.0],
            "2024": [950.0, 220.0, 300.0, 160.0, 102.0, 320.0, 320.0],
        },
        index=[
            "Total Assets",
            "Long Term Debt",
            "Current Assets",
            "Current Liabilities",
            "Ordinary Shares Number",
            "Total Liabilities Net Minority Interest",
            "Retained Earnings",
        ],
    )
    cashflow = pd.DataFrame(
        {"2025": [150.0], "2024": [110.0]},
        index=["Operating Cash Flow"],
    )

    f_score = fd._compute_piotroski_f_score(income, balance_sheet, cashflow)
    assert f_score is not None
    assert f_score >= 8

    z_score = fd._compute_altman_z_score(income, balance_sheet, market_cap=2200.0)
    assert z_score is not None
    assert z_score > 3.0


def test_fmp_graceful_fallback_without_key(monkeypatch):
    monkeypatch.setattr(fd.settings, "FMP_API_KEY", "")
    res = fd.fetch_fmp_fundamentals("AAPL")
    assert res.get("available") is False


def test_crypto_dilution_and_no_binance_futures():
    assert not hasattr(fd, "_binance_futures")
    low_dil = fd._evaluate_token_dilution(market_cap=90e9, fdv=100e9, circ=90e6, max_sup=100e6)
    assert low_dil["mcap_to_fdv_ratio"] == 0.9
    assert str(low_dil["dilution_risk"]).startswith("LOW")

    high_dil = fd._evaluate_token_dilution(market_cap=200e6, fdv=2e9, circ=100e6, max_sup=1e9)
    assert high_dil["mcap_to_fdv_ratio"] == 0.1
    assert str(high_dil["dilution_risk"]).startswith("HIGH")


def test_investment_zones_and_timeframe_cleanup():
    assert "1H" not in md.TIMEFRAME_CONFIG
    assert "1D" in md.TIMEFRAME_CONFIG
    assert "1W" in md.TIMEFRAME_CONFIG

    zones = md.calculate_investment_zones(
        price=4000.0,
        stats={"support": 3800.0, "resistance": 4400.0, "sma50": 3950.0, "sma200": 3900.0, "rsi": 42.0},
        long_term_metrics={"sma200_day": 3900.0, "cagr_3y_pct": 12.0},
        fundamental_data={"dcf_fair_value": 5200.0, "piotroski_f_score": 8, "altman_z_score": 3.5, "debt_to_equity": 40.0},
        market="ihsg",
    )
    assert zones["accumulation_zone"]["ideal_low"] < zones["accumulation_zone"]["ideal_high"]
    assert zones["fair_value_target"]["fair_value"] == 5200.0
    assert zones["fair_value_target"]["valuation_status"] == "UNDERVALUED"
    assert "F-Score" in zones["thesis_invalidation"]["summary"] or "fundamental" in zones["thesis_invalidation"]["summary"].lower()


def test_quant_screener_excludes_memes_and_weights_fundamentals_65():
    for meme in ("PEPE/USDT", "DOGE/USDT", "SHIB/USDT", "FLOKI/USDT"):
        assert meme not in qs.DEFAULT_CRYPTO_FALLBACK

    src_us = inspect.getsource(qs.fetch_live_us_universe)
    assert "undervalued_large_caps" in src_us
    assert "scrIds=day_gainers" not in src_us

    with patch("urllib.request.urlopen", side_effect=OSError("offline")):
        us_syms = qs.fetch_live_us_universe()
        assert len(us_syms) > 0

    high_quality = qs.compute_screener_breakdown(
        price=100.0,
        change_pct=1.0,
        indicators={"sma20": 99.0, "sma50": 98.0, "sma200": 102.0, "rsi": 45.0, "macd": "bullish"},
        fundamentals={
            "roe": 0.24,
            "roic": 0.20,
            "piotroski_f_score": 8,
            "revenue_cagr_3y": 0.16,
            "margin_of_safety_pct": 22.0,
            "dividend_yield": 3.5,
            "debt_to_equity": 35.0,
        },
        market="us_stock",
    )
    weak_overextended = qs.compute_screener_breakdown(
        price=160.0,
        change_pct=5.0,
        indicators={"sma20": 140.0, "sma50": 125.0, "sma200": 100.0, "rsi": 79.0, "macd": "bullish"},
        fundamentals={
            "roe": -0.05,
            "piotroski_f_score": 2,
            "revenue_cagr_3y": -0.10,
            "margin_of_safety_pct": -35.0,
            "debt_to_equity": 300.0,
        },
        market="us_stock",
    )
    assert high_quality["fundamental_score"] > weak_overextended["fundamental_score"]
    assert high_quality["score"] > weak_overextended["score"]
    assert high_quality["fundamental_score"] <= 65.0
    assert high_quality["cycle_score"] <= 35.0


def test_dca_compounding_concentration_and_macro_helpers():
    sim = orch.compute_dca_compounding_simulation(
        market="ihsg_syariah",
        current_price=3500.0,
        long_term_metrics={"cagr_3y_pct": 12.0},
        fundamental_raw={"dividend_yield": 5.0},
        user_profile={"monthly_surplus": 10_000_000.0, "market_rates": {"usd_to_idr": 16000.0}},
    )
    assert sim["currency"] == "IDR"
    assert sim["default_monthly_dca"] == 3_000_000.0
    assert len(sim["horizons"]) == 3
    h1, h3, h5 = sim["horizons"]
    assert h1["years"] == 1 and h3["years"] == 3 and h5["years"] == 5
    assert h5["projected_value"] > h3["projected_value"] > h1["projected_value"] > h1["total_principal"]
    assert h5["estimated_annual_dividend"] > 0

    conc = orch.analyze_portfolio_concentration(
        market="crypto",
        symbol="BTC/USDT",
        fundamental_raw={"category": "Layer 1"},
        user_profile={
            "risk_tolerance": "MODERATE",
            "portfolio_evaluation": {
                "total_investment_balance": 100_000_000.0,
                "investment_wallets": [{"name": "Dompet Crypto BTC", "asset_class": "CRYPTO", "balance_in_base": 35_000_000.0}],
                "allocations_comparison": [{"asset_class": "CRYPTO", "asset_class_label": "Aset Kripto", "actual_pct": 35.0, "target_pct": 10.0}],
            },
        },
    )
    assert conc["concentration_status"] == "OVERWEIGHT_KELAS_ASET"
    assert "PERINGATAN KONSENTRASI" in conc["warning_message"]

    with patch.object(orch, "fetch_live_market_rates", return_value={"usd_to_idr": 16200.0, "gold_idr_per_gram": 1_550_000.0}):
        macro = orch.build_macro_regime_context("ihsg", user_profile={"market_rates": {"usd_to_idr": 16200.0, "gold_idr_per_gram": 1_550_000.0}})
        assert macro["usd_idr_rate"] == 16200.0
        assert macro["interest_rate_regime"]


def test_skills_and_prompts_free_of_legacy_trading_contracts():
    base = Path(__file__).resolve().parents[1] / "app" / "investment_ai"
    forbidden = ("buy_sl", "1.5R", "2.5R", "4.0R", "day_gainers", "generate_trade_signal")
    for sub in ("skills", "prompt"):
        for file_path in (base / sub).rglob("*"):
            if file_path.is_file():
                text = file_path.read_text(encoding="utf-8")
                for term in forbidden:
                    assert term not in text, f"Found legacy trading term '{term}' in {file_path}"
