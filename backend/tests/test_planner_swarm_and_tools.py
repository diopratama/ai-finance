import json
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base, InvestmentAnalysisHistory, User
from app.services.planner_skills_loader import build_planner_system_prompt, route_planner_skills
from app.services.planner_tools import (
    _infer_market_from_symbol,
    build_recent_swarm_analyses_context,
    execute_planner_tool,
)
from app.services.router_service import RouterService


def _make_memory_session():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    return Session


def test_build_recent_swarm_analyses_context_limits_to_5_and_isolates_user():
    Session = _make_memory_session()
    db = Session()
    try:
        db.add(User(id="user_a", email="a@test.com", password_hash="x", full_name="User A"))
        db.add(User(id="user_b", email="b@test.com", password_hash="x", full_name="User B"))
        db.commit()

        base_time = datetime(2026, 11, 10, 10, 0, tzinfo=timezone.utc)
        for i in range(6):
            db.add(
                InvestmentAnalysisHistory(
                    user_id="user_a",
                    run_id=f"run_a_{i}",
                    market="us_stock" if i < 5 else "ihsg",
                    analysis_type="recommend" if i == 5 else "analyze",
                    investment_horizon="LONG",
                    symbol="" if i == 5 else f"SYM{i}",
                    status="completed",
                    decision="ACCUMULATE",
                    confidence=82.0,
                    result_json=json.dumps(
                        {
                            "current_price": 150.0 + i,
                            "candles": [{"close": 100.0}] * 200,
                            "fundamental_metrics": {"dcf_fair_value": 180.0, "piotroski_f_score": 8},
                            "long_term_metrics": {"cagr_3y_pct": 14.5, "max_drawdown_pct": -18.2},
                            "recommendation": {
                                "stance": "ACCUMULATE",
                                "confidence_pct": 82,
                                "investment_zones": {
                                    "accumulation_zone": {"low": 140.0, "high": 152.0},
                                    "fair_value_target": {"target": 180.0, "margin_of_safety_pct": 16.7},
                                    "thesis_invalidation": {"trigger_summary": "ROIC turun di bawah 8%"},
                                },
                            },
                            "top_candidates": [
                                {
                                    "symbol": "BBCA.JK",
                                    "score": 88.5,
                                    "fundamental_score": 56.0,
                                    "cycle_score": 32.5,
                                    "stance": "ACCUMULATE",
                                }
                            ],
                        }
                    ),
                    created_at=base_time + timedelta(hours=i),
                )
            )

        # Pending row (must be ignored)
        db.add(
            InvestmentAnalysisHistory(
                user_id="user_a",
                run_id="run_pending",
                market="crypto",
                analysis_type="analyze",
                symbol="ETH/USDT",
                status="running",
                result_json="{}",
                created_at=base_time + timedelta(hours=10),
            )
        )
        # Other user's row (must be isolated)
        db.add(
            InvestmentAnalysisHistory(
                user_id="user_b",
                run_id="run_b_0",
                market="us_stock",
                analysis_type="analyze",
                symbol="SECRET_OTHER",
                status="completed",
                result_json="{}",
                created_at=base_time + timedelta(hours=11),
            )
        )
        db.commit()

        ctx = build_recent_swarm_analyses_context(db, "user_a", limit=5)
        assert ctx["count"] == 5
        assert "SECRET_OTHER" not in ctx["summary_text"]
        assert "run_pending" not in ctx["summary_text"]
        assert "run_a_0" not in ctx["summary_text"]  # oldest of 6 excluded
        assert "run_a_5" in ctx["summary_text"]
        assert "BBCA.JK" in ctx["summary_text"]
        assert "DCF=180.0" in ctx["summary_text"]
        assert "candles" not in ctx["summary_text"]
    finally:
        db.close()


def test_execute_planner_tool_fetch_asset_and_search_internet():
    assert _infer_market_from_symbol("BBCA", "auto") == ("ihsg", "BBCA.JK")
    assert _infer_market_from_symbol("BTC", "auto") == ("crypto", "BTC/USDT")
    assert _infer_market_from_symbol("VOO", "auto") == ("us_etf", "VOO")
    assert _infer_market_from_symbol("NVDA", "auto") == ("us_stock", "NVDA")

    with (
        patch("app.services.planner_tools.get_market_quote", return_value={"price": 135.0, "change_pct": 1.2, "currency": "USD", "provider": "TwelveData", "indicators": {"rsi": 48.0, "sma200": 110.0}}),
        patch("app.services.planner_tools.fetch_long_term_market_metrics", return_value={"cagr_3y_pct": 42.0, "max_drawdown_pct": -35.0, "cycle_position": "HEALTHY_PULLBACK"}),
        patch("app.services.planner_tools.get_fundamental_context", return_value={"available": True, "text": "NVDA ROIC=60%", "raw": {"dcf_fair_value": 150.0}, "sharia": None}),
        patch("app.services.planner_tools.calculate_investment_zones", return_value={"accumulation_zone": {"low": 120.0, "high": 135.0}}),
    ):
        status_msg, res_json = execute_planner_tool(
            "fetch_asset_market_and_fundamentals",
            {"symbol": "NVDA", "market": "auto"},
            user_id="user_a",
        )
        assert "NVDA" in status_msg
        parsed = json.loads(res_json)
        assert parsed["market"] == "us_stock"
        assert parsed["quote"]["price"] == 135.0
        assert parsed["long_term_metrics"]["cagr_3y_pct"] == 42.0
        assert parsed["investment_zones"]["accumulation_zone"]["low"] == 120.0

    with (
        patch("app.services.planner_tools.search_internet", return_value=[{"title": "BI Rate Terbaru", "url": "https://example.com", "snippet": "6.00%"}]),
        patch("app.services.planner_tools.format_search_results_for_prompt", return_value="BI Rate 6.00%"),
    ):
        status_msg, text = execute_planner_tool("search_internet_live", {"query": "BI rate hari ini"})
        assert "BI rate" in status_msg
        assert "6.00%" in text


def test_execute_planner_tool_get_analysis_detail_ownership_check():
    Session = _make_memory_session()
    db = Session()
    try:
        db.add(User(id="user_a", email="a@test.com", password_hash="x", full_name="User A"))
        db.add(
            InvestmentAnalysisHistory(
                user_id="user_a",
                run_id="run_xyz",
                market="ihsg_syariah",
                analysis_type="analyze",
                symbol="TLKM.JK",
                status="completed",
                decision="BUY_ON_DIP",
                confidence=78.0,
                result_json=json.dumps({"candles_1d": [1, 2, 3], "agent_reports": {"fundamental": "Solid FCF"}}),
            )
        )
        db.commit()
    finally:
        db.close()

    with patch("app.services.planner_tools.SessionLocal", Session):
        _, ok_raw = execute_planner_tool("get_investment_analysis_detail", {"run_id": "run_xyz"}, user_id="user_a")
        ok_data = json.loads(ok_raw)
        assert ok_data["symbol"] == "TLKM.JK"
        assert "candles_1d" not in ok_data["result"]
        assert ok_data["result"]["agent_reports"]["fundamental"] == "Solid FCF"

        _, denied_raw = execute_planner_tool("get_investment_analysis_detail", {"run_id": "run_xyz"}, user_id="user_b")
        denied = json.loads(denied_raw)
        assert "error" in denied


def test_build_planner_system_prompt_includes_recent_swarm_analyses():
    routing = route_planner_skills("gimana hasil analisis swarm BBCA saya kemarin?")
    assert "investment_allocation" in routing["skill_ids"]
    prompt = build_planner_system_prompt(
        {
            "recent_analyses_count": 2,
            "recent_swarm_analyses_text": "• [run_id=r1] BBCA.JK ACCUMULATE",
        },
        routing,
    )
    assert "[RECENT SWARM INVESTMENT ANALYSES (LATEST 2 OF 5)]" in prompt
    assert "BBCA.JK ACCUMULATE" in prompt
    assert "fetch_asset_market_and_fundamentals" in prompt


@pytest.mark.asyncio
async def test_router_service_tool_calling_loop_and_fallback():
    rs = RouterService()
    rs.base_url = "http://mock-router/v1"
    rs.api_key = "test-key"

    # 1. Tool call then final answer
    first_resp = MagicMock()
    first_resp.status_code = 200
    first_resp.json.return_value = {
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "content": "",
                    "tool_calls": [
                        {
                            "id": "call_1",
                            "type": "function",
                            "function": {
                                "name": "fetch_asset_market_and_fundamentals",
                                "arguments": json.dumps({"symbol": "AAPL", "market": "us_stock"}),
                            },
                        }
                    ],
                }
            }
        ]
    }

    second_resp = MagicMock()
    second_resp.status_code = 200
    second_resp.json.return_value = {
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "content": "Valuasi AAPL menarik untuk akumulasi bertahap.",
                }
            }
        ]
    }

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(side_effect=[first_resp, second_resp])
    mock_cm = AsyncMock()
    mock_cm.__aenter__.return_value = mock_client
    mock_cm.__aexit__.return_value = False

    with (
        patch("app.services.router_service.httpx.AsyncClient", return_value=mock_cm),
        patch("app.services.router_service.execute_planner_tool", return_value=("Mengambil data AAPL...", '{"price": 225.0}')),
    ):
        events = []
        async for ev in rs.generate_planner_response_stream(
            [{"role": "user", "content": "Cek saham AAPL sekarang"}],
            {},
            user_id="user_a",
            emit_status=True,
        ):
            events.append(ev)

    assert any(isinstance(e, dict) and "AAPL" in e.get("status", "") for e in events)
    assert any(isinstance(e, dict) and "akumulasi bertahap" in e.get("chunk", "") for e in events)

