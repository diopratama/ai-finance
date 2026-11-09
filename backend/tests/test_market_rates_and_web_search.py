import pytest
from app.services.market_rates_service import (
    fetch_live_market_rates,
    convert_to_idr,
    format_currency_with_base,
    normalize_currency_unit,
)
from app.services.web_search_service import (
    should_search_internet,
    search_internet,
    format_search_results_for_prompt,
)
from app.services.planner_skills_loader import build_planner_system_prompt, route_planner_skills
from app.services.nlu_parser import parse_indonesian_amount, parse_transaction_text


def test_market_rates_service_live_and_fallback():
    rates = fetch_live_market_rates(force_refresh=True)
    assert "usd_to_idr" in rates
    assert "gold_per_gram_idr" in rates
    assert "gold_antam_idr" in rates
    assert "gold_buyback_idr" in rates
    assert "gold_spot_idr" in rates
    assert rates["usd_to_idr"] > 10000
    assert rates["gold_per_gram_idr"] > 2000000
    assert rates["gold_buyback_idr"] > 1800000

    # Conversions
    assert convert_to_idr(100000, "IDR") == 100000.0
    usd_idr = convert_to_idr(10, "USD")
    assert usd_idr > 100000

    gold_idr = convert_to_idr(2.5, "GRAM")
    assert gold_idr > 5000000

    # Formatting
    fmt_usd = format_currency_with_base(50, "USD")
    assert "$50" in fmt_usd["native"]
    assert "≈ Rp" in fmt_usd["display"]

    fmt_gold = format_currency_with_base(1.5, "GRAM")
    assert "1.50 gram" in fmt_gold["native"]
    assert "≈ Rp" in fmt_gold["display"]


def test_web_search_intent_detection():
    assert should_search_internet("Berapa harga emas antam hari ini?") is True
    assert should_search_internet("Bagaimana prospek ORI / SBN ritel terbaru 2026?") is True
    assert should_search_internet("Berapa suku bunga BI rate saat ini?") is True
    assert should_search_internet("Kurs dollar hari ini berapa?") is True
    assert should_search_internet("Apa kabar IHSG?") is True

    # General / internal queries should NOT trigger web search
    assert should_search_internet("Halo apa kabar") is False
    assert should_search_internet("Bagaimana cara budgeting 50/30/20?") is False


def test_nlu_parser_gold_and_usd():
    # Gold grams
    amt, curr = parse_indonesian_amount("beli emas 2.5 gram di antam")
    assert amt == 2.5
    assert curr == "GRAM"

    amt2, curr2 = parse_indonesian_amount("nabung emas 10 gr")
    assert amt2 == 10.0
    assert curr2 == "GRAM"

    # USD
    amt3, curr3 = parse_indonesian_amount("topup 50 usd")
    assert amt3 == 50.0
    assert curr3 == "USD"

    amt4, curr4 = parse_indonesian_amount("belanja $25 di amazon")
    assert amt4 == 25.0
    assert curr4 == "USD"

    # Full parser text
    parsed = parse_transaction_text("beli emas antam 2 gram")
    assert parsed["amount"] == 2.0
    assert parsed["currency"] == "GRAM"


def test_format_search_results_and_system_prompt():
    sample = [
        {"title": "Harga Emas Hari Ini", "snippet": "Harga emas Antam hari ini Rp 2.539.000 per gram.", "url": "https://indogold.id"},
    ]
    txt = format_search_results_for_prompt(sample)
    assert "Harga Emas Hari Ini" in txt
    assert "Harga Beli Emas Antam" in txt
    assert "Nilai Tukar Kurs Dollar (USD/IDR)" in txt

    routing = route_planner_skills("Berapa harga emas antam dan kurs dollar hari ini?", [])
    prompt = build_planner_system_prompt({}, routing, web_search_context=txt)
    assert "Kurs & Harga Komoditas Pasar Terkini" in prompt
    assert "DATA TERKINI DARI INTERNET" in prompt
