import json
from typing import Dict, Any, List, Optional
from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import desc
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.api.budgets import compute_monthly_allocation_data, get_current_month_key
from app.db import (
    Budget,
    CFPChatMessage,
    Category,
    FinancialProfile,
    SessionLocal,
    Transaction,
    User,
    Wallet,
    get_db,
    get_accessible_wallets,
)
from app.services.fire_engine import (
    calculate_financial_health_score,
    calculate_fire_metrics,
    determine_emergency_target_months,
    evaluate_investment_portfolio,
    get_asset_allocation_recommendation,
)
from app.services.market_rates_service import (
    convert_to_idr,
    fetch_live_market_rates,
    format_currency_display_string,
)
from app.services.planner_skills_loader import (
    calculate_profile_completeness,
    extract_and_update_profile_memory,
    get_confirmed_fields_set,
    route_planner_skills,
    save_confirmed_fields_set,
)
from app.services.router_service import router_service

router = APIRouter(prefix="/planner", tags=["AI Financial Planner"])


class SendChatMessageRequest(BaseModel):
    message: str


class UpdatePersonalProfileRequest(BaseModel):
    monthly_income: Optional[float] = Field(default=None, ge=0)
    monthly_living_expense: Optional[float] = Field(default=None, ge=0)
    monthly_debt_payment: Optional[float] = Field(default=None, ge=0)
    marital_status: Optional[str] = None  # "SINGLE" | "MARRIED"
    dependents_count: Optional[int] = Field(default=None, ge=0, le=20)
    current_age: Optional[int] = Field(default=None, ge=17, le=90)
    target_fire_age: Optional[int] = Field(default=None, ge=20, le=95)
    risk_tolerance: Optional[str] = None  # "CONSERVATIVE" | "MODERATE" | "AGGRESSIVE"
    sharia_preference: Optional[bool] = None
    memory_notes: Optional[str] = None


def _fmt_idr(amount: float) -> str:
    return f"Rp {int(round(amount)):,}".replace(",", ".")


def _ensure_profile(user: User, db: Session) -> FinancialProfile:
    profile = db.query(FinancialProfile).filter(FinancialProfile.user_id == user.id).first()
    if not profile:
        profile = FinancialProfile(user_id=user.id)
        db.add(profile)
        db.commit()
        db.refresh(profile)
    return profile


def _serialize_personal_profile(profile: FinancialProfile, completeness: Dict[str, Any]) -> Dict[str, Any]:
    notes_list = [line.strip() for line in (profile.memory_notes or "").splitlines() if line.strip()]
    return {
        "current_age": profile.current_age,
        "target_fire_age": profile.target_fire_age,
        "monthly_income": profile.monthly_income or 0.0,
        "monthly_living_expense": profile.monthly_living_expense or 0.0,
        "monthly_debt_payment": profile.monthly_debt_payment or 0.0,
        "marital_status": (profile.marital_status or "SINGLE").upper(),
        "dependents_count": profile.dependents_count or 0,
        "risk_tolerance": (profile.risk_tolerance or "MODERATE").upper(),
        "sharia_preference": bool(profile.sharia_preference),
        "memory_notes": profile.memory_notes or "",
        "memory_notes_list": notes_list,
        "confirmed_fields": completeness["confirmed_fields"],
        "profile_completeness_pct": completeness["profile_completeness_pct"],
        "missing_profile_hints": completeness["missing_profile_hints"],
    }


def _is_credit_wallet_type(w_type: str) -> bool:
    t = (w_type or "").upper()
    return any(k in t for k in ("CREDIT", "KREDIT", "PAYLATER", "LOAN", "UTANG", "HUTANG", "PINJAMAN", "CC"))


def _is_illiquid_investment_type(w_type: str) -> bool:
    t = (w_type or "").upper()
    return any(k in t for k in ("INVEST", "SAHAM", "RDN", "REKSADANA", "CRYPTO", "PROPERTI", "EMAS", "SUKUK", "SBN"))


def build_planner_overview(user: User, db: Session) -> Dict[str, Any]:
    """Aggregates verified wallets, category spending, budgets, and personal profile into a rich planner snapshot."""
    profile = _ensure_profile(user, db)
    confirmed = get_confirmed_fields_set(profile)

    live_rates = fetch_live_market_rates()

    wallets = get_accessible_wallets(db, user.id, min_role="VIEWER")
    total_wallet_balance = sum(convert_to_idr(w.balance, w.currency, live_rates) for w in wallets)
    liquid_balance = sum(
        convert_to_idr(w.balance, w.currency, live_rates)
        for w in wallets
        if w.balance > 0
        and not _is_credit_wallet_type(w.type)
        and not _is_illiquid_investment_type(w.type)
        and (w.currency or "IDR").upper() != "GRAM"
    )
    credit_debt_balance = sum(
        abs(convert_to_idr(w.balance, w.currency, live_rates))
        for w in wallets
        if _is_credit_wallet_type(w.type) and w.balance < 0
    )

    transactions = db.query(Transaction).filter(Transaction.user_id == user.id).all()
    tx_income = sum(t.amount_in_base for t in transactions if t.type == "INCOME")
    tx_expense = sum(t.amount_in_base for t in transactions if t.type == "EXPENSE")

    # Category breakdown
    categories_map = {c.id: c.name for c in db.query(Category).all()}
    cat_totals: Dict[str, float] = {}
    for t in transactions:
        if t.type == "EXPENSE":
            cat_name = categories_map.get(t.category_id, "Lain-lain")
            cat_totals[cat_name] = cat_totals.get(cat_name, 0.0) + t.amount_in_base

    sorted_cats = sorted(cat_totals.items(), key=lambda x: x[1], reverse=True)
    category_spending_text = (
        "\n".join(f"  • {name}: {_fmt_idr(val)}" for name, val in sorted_cats[:6])
        if sorted_cats
        else "  • Belum ada transaksi pengeluaran tercatat"
    )

    # Monthly Wallet-Linked Budget Allocation & alerts
    alloc = compute_monthly_allocation_data(user, db, get_current_month_key())
    budget_lines: List[str] = []
    for grp in alloc["groups"]:
        if grp["items_count"] > 0:
            pct_str = f" ({grp['income_percentage']}% gaji)" if alloc["reference_income"] > 0 else ""
            budget_lines.append(
                f"  • Grup {grp['group_type']}: alokasi {_fmt_idr(grp['subtotal_budget'])}{pct_str}, "
                f"realisasi {_fmt_idr(grp['subtotal_spent'])}"
            )
            for it in grp["items"]:
                if it["is_over_budget"] or it["percent_used"] >= 80:
                    flag = "OVER-BUDGET!" if it["is_over_budget"] else "HAMPIR PENUH"
                    w_lbl = f" [{it['wallet']['name']}]" if it["wallet"] else ""
                    budget_lines.append(
                        f"    - {it['name']}{w_lbl}: {_fmt_idr(it['spent_amount'])} / {_fmt_idr(it['limit_amount'])} ({it['percent_used']}% — {flag})"
                    )
    for wa in alloc["wallet_allocations"]:
        if wa["status"] == "SHORTFALL":
            budget_lines.append(
                f"  • Kekurangan Saldo Dompet {wa['wallet_name']}: kurang {_fmt_idr(wa['shortfall_amount'])} dari komitmen {_fmt_idr(wa['remaining_commitment'])}"
            )
    budget_alerts_text = "\n".join(budget_lines) if budget_lines else "  • Belum ada batas anggaran bulanan yang diatur"

    wallets_breakdown_text = (
        "\n".join(
            f"  • {w.name} ({w.type}, {w.currency or 'IDR'}): {format_currency_display_string(w.balance, w.currency)}"
            for w in wallets
        )
        if wallets
        else "  • Belum ada dompet aktif"
    )

    live_market_rates_text = (
        f"  • Harga Beli Emas Antam (1 Gram Ritel Indonesia): {_fmt_idr(live_rates.get('gold_antam_idr', live_rates['gold_idr_per_gram']))} / gram\n"
        f"  • Harga Jual Kembali / Buyback Emas Antam: {_fmt_idr(live_rates.get('gold_buyback_idr', 2373000))} / gram\n"
        f"  • Harga Emas Spot Dunia (XAU): ${live_rates.get('gold_xau_usd', 4110):,.2f} / troy oz (≈ {_fmt_idr(live_rates.get('gold_spot_idr', 2390000))} / gram)\n"
        f"  • Kurs Nilai Tukar USD/IDR: {_fmt_idr(live_rates['usd_idr'])} per $1 USD\n"
        f"  • Sumber Data Live: {live_rates.get('source', 'Live Market API')}"
    )

    completeness = calculate_profile_completeness(profile, tx_income=tx_income, tx_expense=tx_expense)
    flags = completeness["flags"]

    # Effective income & expense with explicit confirmation transparency
    if (profile.monthly_income or 0.0) > 0:
        effective_income = profile.monthly_income
        income_label = "TERKONFIRMASI PROFIL"
    elif tx_income > 0:
        effective_income = tx_income
        income_label = "DARI TRANSAKSI PEMASUKAN TERDATA"
    else:
        effective_income = 15_000_000.0
        income_label = "BELUM DIKONFIRMASI USER — asumsi sementara Rp 15.000.000"

    if "monthly_living_expense" in confirmed and (profile.monthly_living_expense or 0.0) > 0:
        effective_expenses = profile.monthly_living_expense
        expense_label = "TERKONFIRMASI PROFIL"
    elif tx_expense >= 1_000_000:
        effective_expenses = tx_expense
        expense_label = "DARI TRANSAKSI PENGELUARAN TERDATA"
    else:
        effective_expenses = profile.monthly_living_expense if (profile.monthly_living_expense or 0.0) > 0 else 8_000_000.0
        expense_label = (
            "DARI TRANSAKSI + ESTIMASI DASAR"
            if tx_expense > 0
            else f"BELUM DIKONFIRMASI USER — asumsi sementara {_fmt_idr(effective_expenses)}"
        )

    monthly_debt = profile.monthly_debt_payment or 0.0
    is_married = (profile.marital_status or "SINGLE").upper() == "MARRIED"
    deps = profile.dependents_count or 0
    marital_text = "Menikah" if is_married else "Lajang"
    household_summary = f"{marital_text}, {deps} tanggungan"

    health = calculate_financial_health_score(
        total_assets=total_wallet_balance,
        total_debts=credit_debt_balance,
        monthly_income=effective_income,
        monthly_expenses=effective_expenses,
        emergency_fund=liquid_balance,
        is_married=is_married,
        dependents_count=deps,
        monthly_debt_payment=monthly_debt,
    )

    monthly_surplus = max(0.0, effective_income - effective_expenses - monthly_debt)
    fire_metrics = calculate_fire_metrics(
        current_age=profile.current_age or 28,
        target_fire_age=profile.target_fire_age or 50,
        monthly_expenses=effective_expenses,
        current_net_worth=total_wallet_balance,
        monthly_savings=monthly_surplus,
    )

    notes_lines = [f"  • {n}" for n in (profile.memory_notes or "").splitlines() if n.strip()]
    memory_notes_text = "\n".join(notes_lines) if notes_lines else "  • Belum ada catatan khusus dari obrolan"

    context = {
        "base_currency": user.base_currency,
        "net_worth_formatted": _fmt_idr(health["net_worth"]),
        "total_wallet_balance_formatted": _fmt_idr(total_wallet_balance),
        "liquid_balance_formatted": _fmt_idr(liquid_balance),
        "monthly_income_formatted": _fmt_idr(effective_income),
        "monthly_expenses_formatted": _fmt_idr(effective_expenses),
        "monthly_debt_formatted": _fmt_idr(monthly_debt),
        "dsr_percentage": health["debt_service_ratio_percentage"],
        "savings_margin_percentage": health["savings_margin_percentage"],
        "household_summary": household_summary,
        "emergency_fund_months": health["emergency_fund"]["months_covered"],
        "emergency_target_months": health["emergency_fund"]["target_months"],
        "emergency_fund_status": "Memadai" if health["emergency_fund"]["is_sufficient"] else "Perlu Ditingkatkan",
        "current_age": profile.current_age,
        "target_fire_age": profile.target_fire_age,
        "fire_target_formatted": _fmt_idr(fire_metrics["fire_number"]),
        "coast_fire_formatted": _fmt_idr(fire_metrics["coast_fire_number"]),
        "is_coast_fire_achieved": fire_metrics["is_coast_fire_achieved"],
        "risk_profile": (profile.risk_tolerance or "MODERATE").upper(),
        "sharia_preference": bool(profile.sharia_preference),
        "health_score": health["score"],
        "health_status": health["status"],
        "profile_completeness_pct": completeness["profile_completeness_pct"],
        "missing_profile_hints": completeness["missing_profile_hints"],
        # Prompt-only rich detail fields
        "wallets_breakdown_text": wallets_breakdown_text,
        "live_market_rates_text": live_market_rates_text,
        "category_spending_text": category_spending_text,
        "budget_alerts_text": budget_alerts_text,
        "memory_notes_text": memory_notes_text,
        "income_confirmation_label": income_label,
        "expense_confirmation_label": expense_label,
        "debt_confirmation_label": "TERKONFIRMASI USER" if flags["debt_ready"] else "BELUM DIKONFIRMASI USER — asumsi Rp 0",
        "household_confirmation_label": "TERKONFIRMASI USER" if flags["household_ready"] else "BELUM DIKONFIRMASI USER — asumsi sementara Lajang, 0 tanggungan",
        "risk_confirmation_label": "TERKONFIRMASI USER" if flags["risk_ready"] else "BELUM DIKONFIRMASI USER — default MODERATE",
        "age_confirmation_label": "TERKONFIRMASI USER" if flags["age_ready"] else "BELUM DIKONFIRMASI USER — default",
    }

    user_strategy = getattr(profile, "portfolio_strategy", None)
    custom_raw = getattr(profile, "custom_allocations_json", None)
    user_custom_alloc = None
    if custom_raw:
        try:
            user_custom_alloc = json.loads(custom_raw)
        except Exception:
            user_custom_alloc = None

    allocations = get_asset_allocation_recommendation(
        risk_tolerance=context["risk_profile"],
        sharia_preference=context["sharia_preference"],
        strategy=user_strategy,
        custom_allocations=user_custom_alloc,
    )
    portfolio_review = evaluate_investment_portfolio(
        wallets=wallets,
        risk_tolerance=context["risk_profile"],
        sharia_preference=context["sharia_preference"],
        liquid_cash_balance=liquid_balance,
        monthly_expenses=effective_expenses,
        is_married=is_married,
        dependents_count=deps,
        strategy=user_strategy,
        custom_allocations=user_custom_alloc,
    )
    personal_profile = _serialize_personal_profile(profile, completeness)

    return {
        "context": context,
        "allocations": allocations,
        "portfolio_review": portfolio_review,
        "personal_profile": personal_profile,
    }


@router.get("/health-score")
@router.get("/overview")
def get_health_score(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return build_planner_overview(current_user, db)


@router.put("/personal-profile")
def update_personal_profile(
    req: UpdatePersonalProfileRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Optional zero-friction profile update from the side panel."""
    profile = _ensure_profile(current_user, db)
    confirmed = get_confirmed_fields_set(profile)

    if req.monthly_income is not None:
        profile.monthly_income = req.monthly_income
        if req.monthly_income > 0:
            confirmed.add("monthly_income")

    if req.monthly_living_expense is not None:
        profile.monthly_living_expense = req.monthly_living_expense
        if req.monthly_living_expense > 0:
            profile.fire_target_amount = req.monthly_living_expense * 12 * 25
            confirmed.add("monthly_living_expense")

    if req.monthly_debt_payment is not None:
        profile.monthly_debt_payment = req.monthly_debt_payment
        confirmed.add("debt_obligation")

    if req.marital_status is not None:
        status_clean = req.marital_status.strip().upper()
        if status_clean in ("SINGLE", "MARRIED"):
            profile.marital_status = status_clean
            confirmed.add("marital_and_dependents")

    if req.dependents_count is not None:
        profile.dependents_count = req.dependents_count
        confirmed.add("marital_and_dependents")

    if req.current_age is not None:
        profile.current_age = req.current_age
        confirmed.add("age_and_retirement")

    if req.target_fire_age is not None:
        profile.target_fire_age = max(req.target_fire_age, (profile.current_age or 28) + 1)
        confirmed.add("age_and_retirement")

    if req.risk_tolerance is not None:
        risk_clean = req.risk_tolerance.strip().upper()
        if risk_clean in ("CONSERVATIVE", "MODERATE", "AGGRESSIVE"):
            profile.risk_tolerance = risk_clean
            confirmed.add("risk_profile")

    if req.sharia_preference is not None:
        profile.sharia_preference = req.sharia_preference

    if req.memory_notes is not None:
        profile.memory_notes = req.memory_notes.strip()

    # Keep emergency_fund_target in sync with household tier
    target_months = determine_emergency_target_months(
        is_married=(profile.marital_status or "SINGLE").upper() == "MARRIED",
        dependents_count=profile.dependents_count or 0,
    )
    profile.emergency_fund_target = (profile.monthly_living_expense or 8_000_000.0) * target_months

    save_confirmed_fields_set(profile, confirmed)
    db.commit()
    db.refresh(profile)

    return build_planner_overview(current_user, db)


@router.get("/history")
def get_chat_history(
    limit: int = 40,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    messages = (
        db.query(CFPChatMessage)
        .filter(CFPChatMessage.user_id == current_user.id)
        .order_by(CFPChatMessage.created_at.asc())
        .limit(limit)
        .all()
    )
    return [
        {
            "id": m.id,
            "role": m.role,
            "content": m.content,
            "created_at": m.created_at.isoformat(),
        }
        for m in messages
    ]


@router.delete("/history")
def clear_chat_history(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    deleted = db.query(CFPChatMessage).filter(CFPChatMessage.user_id == current_user.id).delete()
    db.commit()
    return {"cleared": True, "deleted_count": deleted}


@router.post("/chat")
async def chat_with_planner(
    req: SendChatMessageRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Streams conversational financial planning guidance with progressive profile auto-save & skill routing."""
    user_id = current_user.id
    profile = _ensure_profile(current_user, db)

    # 1. Progressive profiling: auto-capture facts mentioned in chat BEFORE building snapshot
    mem_result = extract_and_update_profile_memory(req.message, profile)
    if mem_result["updated"]:
        db.commit()
        db.refresh(profile)

    overview = build_planner_overview(current_user, db)
    financial_context = overview["context"]

    # 2. Persist user message
    user_msg = CFPChatMessage(user_id=user_id, role="user", content=req.message)
    db.add(user_msg)
    db.commit()

    # 3. Load recent conversation history (latest 12 messages in chronological order)
    history_records = (
        db.query(CFPChatMessage)
        .filter(CFPChatMessage.user_id == user_id)
        .order_by(desc(CFPChatMessage.created_at))
        .limit(12)
        .all()
    )
    history = [{"role": h.role, "content": h.content} for h in reversed(history_records)]

    # 4. Route to 1-2 relevant planner skills
    routing = route_planner_skills(req.message, history)

    meta_payload = {
        "active_skills": routing["skill_labels"],
        "skill_ids": routing["skill_ids"],
        "profile_updated": mem_result["updated"],
        "updated_fields": mem_result["updated_fields"],
        "profile_completeness_pct": financial_context["profile_completeness_pct"],
    }

    # Compact snapshot for DB storage
    stored_snapshot = {
        k: v
        for k, v in financial_context.items()
        if not k.endswith("_text")
    }
    stored_snapshot["active_skills"] = routing["skill_labels"]

    async def sse_event_generator():
        yield f"data: {json.dumps({'meta': meta_payload})}\n\n"

        collected_response: List[str] = []
        async for chunk in router_service.generate_planner_response_stream(
            conversation_history=history,
            financial_context=financial_context,
            routing=routing,
        ):
            collected_response.append(chunk)
            yield f"data: {json.dumps({'chunk': chunk})}\n\n"

        full_reply = "".join(collected_response)
        if full_reply:
            bg_db = SessionLocal()
            try:
                assistant_msg = CFPChatMessage(
                    user_id=user_id,
                    role="assistant",
                    content=full_reply,
                    metrics_snapshot=json.dumps(stored_snapshot),
                )
                bg_db.add(assistant_msg)
                bg_db.commit()
            finally:
                bg_db.close()
        yield "data: [DONE]\n\n"

    return StreamingResponse(sse_event_generator(), media_type="text/event-stream")


async def ask_planner_direct(user: User, message: str, db: Session) -> str:
    """Synchronous/direct conversational assistant for Telegram and WhatsApp bots."""
    profile = _ensure_profile(user, db)
    mem_result = extract_and_update_profile_memory(message, profile)
    if mem_result["updated"]:
        db.commit()
        db.refresh(profile)

    overview = build_planner_overview(user, db)
    financial_context = overview["context"]

    user_msg = CFPChatMessage(user_id=user.id, role="user", content=message)
    db.add(user_msg)
    db.commit()

    history_records = (
        db.query(CFPChatMessage)
        .filter(CFPChatMessage.user_id == user.id)
        .order_by(desc(CFPChatMessage.created_at))
        .limit(10)
        .all()
    )
    history = [{"role": h.role, "content": h.content} for h in reversed(history_records)]
    routing = route_planner_skills(message, history)

    reply = await router_service.generate_planner_response(
        conversation_history=history,
        financial_context=financial_context,
        routing=routing,
    )

    if reply:
        stored_snapshot = {
            k: v for k, v in financial_context.items() if not k.endswith("_text")
        }
        stored_snapshot["active_skills"] = routing["skill_labels"]
        assistant_msg = CFPChatMessage(
            user_id=user.id,
            role="assistant",
            content=reply,
            metrics_snapshot=json.dumps(stored_snapshot),
        )
        db.add(assistant_msg)
        db.commit()

    return reply


