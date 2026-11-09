import asyncio
import json
import logging
import queue
import threading
import uuid
from typing import Any, Dict, List, Optional
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.db import (
    FinancialProfile,
    InvestmentAnalysisHistory,
    Transaction,
    User,
    Wallet,
    get_accessible_wallets,
    get_db,
    SessionLocal,
)
from app.services.fire_engine import is_investment_wallet
from app.services.market_rates_service import convert_to_idr, fetch_live_market_rates
from app.investment_ai.market_data import get_market_quote
from app.investment_ai.sharia_reference import load_sharia_reference
from app.investment_ai.orchestrator import (
    AnalysisStopped,
    chat_with_investment_agent,
    register_stop_event,
    run_investment_swarm_pipeline,
    run_recommendation_pipeline,
    trigger_stop_event,
    unregister_stop_event,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/investment", tags=["Investment Research & Multi-Agent Swarm"])


class RunInvestmentSwarmRequest(BaseModel):
    market: str
    symbol: Optional[str] = ""
    analysis_type: Optional[str] = Field("analyze", pattern="^(analyze|recommend)$")
    horizon: Optional[str] = "ALL"  # ALL | SHORT | MEDIUM | LONG
    locale: Optional[str] = "id"


class StopInvestmentTaskRequest(BaseModel):
    task_id: str


class InvestmentChatRequest(BaseModel):
    symbol: Optional[str] = ""
    market: Optional[str] = "ihsg"
    message: str = ""
    mode: Optional[str] = "standard"  # standard | deep_validation
    locale: Optional[str] = "id"
    history: List[Dict[str, str]] = []
    analysis_context: Dict[str, Any] = {}


def _build_user_profile_context(user: User, db: Session) -> Dict[str, Any]:
    profile = db.query(FinancialProfile).filter(FinancialProfile.user_id == user.id).first()
    wallets = get_accessible_wallets(db, user.id, min_role="VIEWER")
    rates = fetch_live_market_rates()

    liquid_cash = sum(
        max(0.0, convert_to_idr(w.balance, getattr(w, "currency", "IDR") or "IDR", rates))
        for w in wallets
        if not is_investment_wallet(w.name, w.type, getattr(w, "asset_class", None))
        and not any(k in (w.type or "").upper() for k in ("CREDIT", "KREDIT", "PAYLATER", "LOAN", "UTANG", "HUTANG", "CC"))
    )

    invest_val = sum(
        max(0.0, convert_to_idr(w.balance, getattr(w, "currency", "IDR") or "IDR", rates))
        for w in wallets
        if is_investment_wallet(w.name, w.type, getattr(w, "asset_class", None))
    )

    monthly_exp = profile.monthly_living_expense if profile and profile.monthly_living_expense else 8_000_000.0
    risk_tol = profile.risk_tolerance if profile and profile.risk_tolerance else "MODERATE"
    sharia_pref = bool(profile.sharia_preference) if profile else False

    # Compute actual monthly surplus from recent income transactions or profile
    thirty_days_ago = datetime.now(timezone.utc) - timedelta(days=30)
    recent_incomes = (
        db.query(Transaction)
        .filter(
            Transaction.user_id == user.id,
            Transaction.type == "INCOME",
            Transaction.transaction_date >= thirty_days_ago,
        )
        .all()
    )
    income_val = sum(convert_to_idr(t.amount, getattr(t, "currency", "IDR") or "IDR", rates) for t in recent_incomes)
    if income_val <= 0 and profile and profile.monthly_income:
        income_val = float(profile.monthly_income)
    if income_val <= 0:
        income_val = monthly_exp * 1.25

    surplus_val = max(0.0, income_val - monthly_exp)

    return {
        "liquid_cash_balance": liquid_cash,
        "total_investment_balance": invest_val,
        "monthly_expenses": monthly_exp,
        "monthly_income": income_val,
        "monthly_surplus": surplus_val,
        "risk_tolerance": risk_tol,
        "sharia_preference": sharia_pref,
    }


@router.get("/quote")
def get_quote(
    market: str = Query(..., description="ihsg, crypto, us_stock, us_etf"),
    symbol: str = Query(..., description="Ticker/symbol e.g. BBCA, BTC, AAPL"),
    timeframe: str = Query("1D", description="1D, 1W, 1H"),
    current_user: User = Depends(get_current_user),
):
    """Fetches indicative market quote, price, and daily statistics."""
    try:
        quote = get_market_quote(market, symbol.strip().upper(), timeframe)
        return {
            "success": True,
            "market": market,
            "symbol": symbol.strip().upper(),
            "timeframe": timeframe,
            "quote": quote,
        }
    except Exception as e:
        logger.warning("Quote fetch error for %s (%s): %s", symbol, market, e)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Gagal mengambil quote pasar: {str(e)}",
        )


@router.get("/sharia-stocks")
def list_sharia_stocks(
    query: Optional[str] = Query(None, description="Search ticker or name"),
    current_user: User = Depends(get_current_user),
):
    """Returns the verified ISSI / DES sharia reference list from official BEI reference."""
    try:
        ref = load_sharia_reference()
        issuers = ref.get("issuers", [])
        if query:
            q = query.strip().upper()
            issuers = [
                i for i in issuers
                if q in (i.get("ticker") or "") or q in (i.get("name") or "").upper()
            ]
        return {
            "total": len(issuers),
            "source_name": ref.get("source_name"),
            "source_as_of": ref.get("source_as_of"),
            "valid_until": ref.get("valid_until"),
            "counts": ref.get("counts"),
            "issuers": issuers[:150],
        }
    except Exception as e:
        logger.error("Failed to load sharia reference: %s", e)
        return {"total": 0, "issuers": [], "error": str(e)}


@router.post("/stop")
def stop_task(
    req: StopInvestmentTaskRequest,
    current_user: User = Depends(get_current_user),
):
    """Signals an active analysis pipeline to terminate gracefully."""
    stopped = trigger_stop_event(req.task_id)
    return {"success": True, "stopped": stopped, "task_id": req.task_id}


@router.post("/chat")
def chat_with_agent(
    req: InvestmentChatRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Answers user inquiries or performs deep validation audits on the investment findings."""
    user_prof = _build_user_profile_context(current_user, db)
    ans = chat_with_investment_agent(
        history=req.history,
        analysis_context=req.analysis_context,
        user_message=req.message,
        mode=req.mode or "standard",
        locale=req.locale or "id",
        user_profile=user_prof,
    )
    return {"success": True, **ans}


@router.get("/history")
def list_history(
    market: Optional[str] = None,
    limit: int = 20,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Returns recent multi-agent investment research runs for the user."""
    query = db.query(InvestmentAnalysisHistory).filter(InvestmentAnalysisHistory.user_id == current_user.id)
    if market:
        query = query.filter(InvestmentAnalysisHistory.market == market)
    records = query.order_by(InvestmentAnalysisHistory.created_at.desc()).limit(limit).all()

    return [
        {
            "id": r.id,
            "run_id": r.run_id,
            "market": r.market,
            "symbol": r.symbol,
            "analysis_type": r.analysis_type,
            "investment_horizon": r.investment_horizon,
            "decision": r.decision,
            "confidence": r.confidence,
            "symbols_scanned": r.symbols_scanned,
            "status": r.status,
            "report_preview": r.report_preview,
            "exa_news_count": r.exa_news_count,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r in records
    ]


@router.get("/history/{history_id}")
def get_history_detail(
    history_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Returns full details including analyst reports and investment recommendation for a past run."""
    record = (
        db.query(InvestmentAnalysisHistory)
        .filter(
            InvestmentAnalysisHistory.id == history_id,
            InvestmentAnalysisHistory.user_id == current_user.id,
        )
        .first()
    )
    if not record:
        raise HTTPException(status_code=404, detail="Riwayat riset tidak ditemukan.")

    result_data = {}
    try:
        result_data = json.loads(record.result_json) if record.result_json else {}
    except Exception:
        pass

    return {
        "id": record.id,
        "run_id": record.run_id,
        "market": record.market,
        "symbol": record.symbol,
        "analysis_type": record.analysis_type,
        "investment_horizon": record.investment_horizon,
        "decision": record.decision,
        "confidence": record.confidence,
        "symbols_scanned": record.symbols_scanned,
        "status": record.status,
        "created_at": record.created_at.isoformat() if record.created_at else None,
        "result": result_data,
    }


@router.delete("/history/{history_id}")
def delete_history_detail(
    history_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Deletes a past investment research record."""
    record = (
        db.query(InvestmentAnalysisHistory)
        .filter(
            InvestmentAnalysisHistory.id == history_id,
            InvestmentAnalysisHistory.user_id == current_user.id,
        )
        .first()
    )
    if not record:
        raise HTTPException(status_code=404, detail="Riwayat tidak ditemukan.")
    db.delete(record)
    db.commit()
    return {"success": True, "deleted_id": history_id}


@router.post("/run")
def run_investment_swarm(
    req: RunInvestmentSwarmRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Launches multi-agent investment research and streams SSE events.
    Supports:
    - analysis_type="analyze": Deep single-asset investment research
    - analysis_type="recommend": Multi-asset market opportunity scanner
    Persists final result to InvestmentAnalysisHistory on completion.
    """
    market = req.market.strip().lower()
    analysis_type = (req.analysis_type or "analyze").strip().lower()
    symbol = (req.symbol or "").strip().upper()
    horizon = (req.horizon or "ALL").strip().upper()
    task_id = str(uuid.uuid4())
    stop_event = register_stop_event(task_id)

    user_profile = _build_user_profile_context(current_user, db)
    user_id = current_user.id

    def event_stream():
        msg_queue: queue.Queue = queue.Queue()

        def queue_emit(event: Dict[str, Any]):
            msg_queue.put(event)

        def worker():
            try:
                if analysis_type == "recommend":
                    final_res = run_recommendation_pipeline(
                        market=market,
                        event_callback=queue_emit,
                        stop_event=stop_event,
                        locale=req.locale or "id",
                        user_profile=user_profile,
                    )
                else:
                    final_res = run_investment_swarm_pipeline(
                        market=market,
                        symbol=symbol,
                        user_profile=user_profile,
                        event_callback=queue_emit,
                        stop_event=stop_event,
                        locale=req.locale or "id",
                    )

                # Persist to DB on success
                with SessionLocal() as worker_db:
                    rec = final_res.get("investment_recommendation") or {}
                    news_list = final_res.get("news_sources") or []
                    symbols_scanned = final_res.get("symbols_scanned", 1 if analysis_type == "analyze" else 0)
                    preview_text = final_res.get("report") if analysis_type == "recommend" else rec.get("executive_thesis", "")

                    history_row = InvestmentAnalysisHistory(
                        id=str(uuid.uuid4()),
                        user_id=user_id,
                        run_id=task_id,
                        market=market,
                        analysis_type=analysis_type,
                        investment_horizon=horizon,
                        symbol=symbol,
                        status="completed",
                        decision=rec.get("stance", "HOLD") if analysis_type == "analyze" else None,
                        confidence=float(rec.get("confidence_pct", 0)) if rec.get("confidence_pct") is not None else None,
                        symbols_scanned=symbols_scanned,
                        exa_news_count=final_res.get("exa_news_count", len(news_list)),
                        report_preview=(preview_text or "")[:500],
                        input_json=json.dumps(req.model_dump()),
                        result_json=json.dumps(final_res),
                    )
                    worker_db.add(history_row)
                    worker_db.commit()

            except AnalysisStopped as as_err:
                logger.info("Investment swarm task %s stopped: %s", task_id, as_err)
                queue_emit({
                    "type": "stopped",
                    "task_id": task_id,
                    "message": "Analisis dihentikan oleh pengguna.",
                })
            except Exception as exc:
                logger.error("Investment swarm task %s error: %s", task_id, exc)
                queue_emit({
                    "type": "error",
                    "task_id": task_id,
                    "error": str(exc),
                })
            finally:
                unregister_stop_event(task_id)
                queue_emit({"type": "_FINISHED_"})

        thread = threading.Thread(target=worker, daemon=True)
        thread.start()

        # Emit initial task ID
        init_evt = {
            "type": "task_init",
            "task_id": task_id,
            "market": market,
            "analysis_type": analysis_type,
            "symbol": symbol,
            "horizon": horizon,
        }
        yield f"data: {json.dumps(init_evt)}\n\n"

        while True:
            try:
                item = msg_queue.get(timeout=1.0)
                if item.get("type") == "_FINISHED_":
                    break
                yield f"data: {json.dumps(item)}\n\n"
            except queue.Empty:
                yield ": ping\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
