import pytest
import threading
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient
from app.main import app
from app.services.market_rates_service import (
    convert_between_currencies,
    convert_to_idr,
    fetch_live_market_rates,
)
from app.services.router_service import router_service
from app.investment_ai.fundamental_data import (
    get_sharia_reference_status,
    evaluate_sharia_screen,
)
from app.investment_ai.orchestrator import (
    fetch_comprehensive_market_data,
    run_recommendation_pipeline,
    chat_with_investment_agent,
    calibrate_confidence,
)

client = TestClient(app)


def test_cross_currency_conversion():
    # IDR to USD
    usd_val = convert_between_currencies(160000.0, "IDR", "USD")
    assert 5.0 <= usd_val <= 15.0

    # USD to IDR
    idr_val = convert_between_currencies(10.0, "USD", "IDR")
    assert 100000.0 <= idr_val <= 200000.0

    # IDR to GRAM
    gram_val = convert_between_currencies(2600000.0, "IDR", "GRAM")
    assert 0.5 <= gram_val <= 2.0

    # GRAM to IDR
    idr_from_gold = convert_between_currencies(1.0, "GRAM", "IDR")
    assert idr_from_gold > 2000000.0

    # Same currency
    assert convert_between_currencies(500.0, "USD", "USD") == 500.0


def test_simulate_chat_requires_auth():
    # Unauthenticated request to /api/v1/webhooks/simulate-chat must be rejected (401)
    res = client.post(
        "/api/v1/webhooks/simulate-chat",
        json={"message": "beli kopi 25rb"},
    )
    assert res.status_code in (401, 403)


@pytest.mark.asyncio
async def test_router_service_no_fake_ai_slop_fallbacks():
    # Router service without base_url configured must raise RuntimeError, NOT return fake receipt
    with patch.object(router_service, "base_url", ""):
        with pytest.raises(RuntimeError) as exc_ocr:
            await router_service.parse_receipt_image(b"fake_image_bytes")
        assert "belum terkonfigurasi" in str(exc_ocr.value)

        with pytest.raises(RuntimeError) as exc_audio:
            await router_service.transcribe_audio_note(b"fake_audio_bytes")
        assert "belum terkonfigurasi" in str(exc_audio.value)


def test_sharia_reference_lookup_both_ihsg_and_syariah():
    # Conventional and Syariah market lookups for known ISSI stocks
    tlkm_status = get_sharia_reference_status("TLKM")
    assert tlkm_status.get("status") == "Ya"

    bbca_status = get_sharia_reference_status("BBCA")
    assert bbca_status.get("status") in ("Tidak", "NOT_IN_REFERENCE")

    screen = evaluate_sharia_screen({"ticker": "TLKM"})
    assert "status" in screen


def test_fetch_comprehensive_market_data_indicators():
    # Fetch real live data and indicators for a major bluechip
    data = fetch_comprehensive_market_data("ihsg", "TLKM")
    assert "symbol" in data
    assert "timeframes" in data
    tf_1d = data["timeframes"].get("1D") or {}
    assert "stats" in tf_1d
    stats = tf_1d["stats"]
    assert "rsi" in stats
    assert "macd" in stats
    assert "investment_zones" in stats
    assert "1H" not in data["timeframes"]

    # Confidence calibration
    close_price = tf_1d.get("price") or 3000.0
    conf = calibrate_confidence(
        close_price,
        {"rsi": 45.0, "macd": 2.5, "sma20": close_price * 0.95, "sma50": close_price * 0.90},
        "BUY",
        1.5,
    )
    assert conf is not None
    assert 0.6 <= conf <= 0.95


def test_run_recommendation_pipeline():
    # Run the screener recommendation pipeline for a small limit/market
    events = []
    def on_event(ev):
        events.append(ev)

    res = run_recommendation_pipeline("ihsg_syariah", event_callback=on_event, locale="id")
    assert res["type"] == "recommendation"
    assert res["status"] in ("completed", "insufficient_data")
    assert "ranked_candidates" in res
    assert len(res["ranked_candidates"]) > 0
    top = res["ranked_candidates"][0]
    assert "symbol" in top
    assert "score" in top
    assert "stance" in top


def test_chat_deep_validation_mode():
    # Test standard mode
    ctx = {
        "symbol": "TLKM",
        "market": "ihsg",
        "investment_recommendation": {
            "stance": "ACCUMULATE",
            "confidence_pct": 82,
            "executive_thesis": "Fundamental solid dengan dividen yield atraktif.",
        },
    }

    # Standard chat (graceful fallback or mocked reply)
    with patch("app.investment_ai.orchestrator.call_llm", return_value="Valuasi saat ini tergolong wajar (Fair Value)."):
        std_res = chat_with_investment_agent(
            history=[{"role": "user", "content": "Apakah valuasi saat ini aman?"}],
            analysis_context=ctx,
            user_message="Apakah valuasi saat ini aman?",
            mode="standard",
        )
        assert "reply" in std_res
        assert "Fair Value" in std_res["reply"]
        assert std_res["mode"] == "standard"
        assert std_res["validation_meta"] is None

        # Deep validation audit mode (triggers live re-fetch, discrepancy flags, and auditor verdict)
        deep_res = chat_with_investment_agent(
            history=[{"role": "user", "content": "Audit divergensi 1D vs 1W"}],
            analysis_context=ctx,
            user_message="Audit divergensi 1D vs 1W",
            mode="deep_validation",
        )
        assert "reply" in deep_res
        assert deep_res["mode"] == "deep_validation"
        meta = deep_res["validation_meta"]
        assert meta is not None
        assert "TLKM" in meta["validated_symbols"]
        assert "live_snapshots" in meta
        assert len(meta["live_snapshots"]) > 0
        snap = meta["live_snapshots"][0]
        assert snap.get("symbol") == "TLKM"
        assert "rsi_1d" in snap
        assert "rsi_1w" in snap
