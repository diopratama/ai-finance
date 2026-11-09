import json
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db import FinancialProfile, Transaction, User, Wallet, get_db, get_accessible_wallets
from app.services.fire_engine import (
    calculate_fire_metrics,
    evaluate_investment_portfolio,
    get_asset_allocation_recommendation,
    is_investment_wallet,
)
from app.services.planner_skills_loader import get_confirmed_fields_set, save_confirmed_fields_set
from app.services.market_rates_service import convert_to_idr, fetch_live_market_rates
from app.auth import get_current_user

router = APIRouter(prefix="/fire", tags=["FIRE & Financial Freedom"])


class UpdateFIREProfileRequest(BaseModel):
    current_age: int
    target_fire_age: int
    monthly_living_expense: float
    risk_tolerance: str = "MODERATE"


class CalculateFIRERequest(BaseModel):
    current_age: int
    target_fire_age: int
    monthly_expenses: float
    current_net_worth: float
    monthly_savings: float = 0.0
    annual_return_rate: float = 0.07


@router.get("/profile")
def get_fire_profile(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    profile = db.query(FinancialProfile).filter(FinancialProfile.user_id == current_user.id).first()
    if not profile:
        profile = FinancialProfile(user_id=current_user.id)
        db.add(profile)
        db.commit()
        db.refresh(profile)

    wallets = get_accessible_wallets(db, current_user.id, min_role="VIEWER")
    rates = fetch_live_market_rates()
    net_worth = sum(convert_to_idr(w.balance, getattr(w, "currency", "IDR") or "IDR", rates) for w in wallets)

    metrics = calculate_fire_metrics(
        current_age=profile.current_age,
        target_fire_age=profile.target_fire_age,
        monthly_expenses=profile.monthly_living_expense,
        current_net_worth=net_worth,
        monthly_savings=0.0,
    )
    sharia_pref = bool(getattr(profile, "sharia_preference", False))
    user_strategy = getattr(profile, "portfolio_strategy", None)
    custom_raw = getattr(profile, "custom_allocations_json", None)
    user_custom_alloc = None
    if custom_raw:
        try:
            user_custom_alloc = json.loads(custom_raw)
        except Exception:
            user_custom_alloc = None

    allocations = get_asset_allocation_recommendation(
        profile.risk_tolerance,
        sharia_preference=sharia_pref,
        strategy=user_strategy,
        custom_allocations=user_custom_alloc,
    )

    liquid_cash = sum(
        max(0.0, convert_to_idr(w.balance, getattr(w, "currency", "IDR") or "IDR", rates))
        for w in wallets
        if not is_investment_wallet(w.name, w.type, getattr(w, "asset_class", None))
        and not any(k in (w.type or "").upper() for k in ("CREDIT", "KREDIT", "PAYLATER", "LOAN", "UTANG", "HUTANG", "CC"))
    )
    portfolio_review = evaluate_investment_portfolio(
        wallets=wallets,
        risk_tolerance=profile.risk_tolerance or "MODERATE",
        sharia_preference=sharia_pref,
        liquid_cash_balance=liquid_cash,
        monthly_expenses=profile.monthly_living_expense or 8_000_000.0,
        is_married=((profile.marital_status or "SINGLE").upper() == "MARRIED"),
        dependents_count=int(profile.dependents_count or 0),
        strategy=user_strategy,
        custom_allocations=user_custom_alloc,
    )

    return {
        "profile": {
            "current_age": profile.current_age,
            "target_fire_age": profile.target_fire_age,
            "monthly_living_expense": profile.monthly_living_expense,
            "risk_tolerance": profile.risk_tolerance,
        },
        "metrics": metrics,
        "allocations": allocations,
        "portfolio_review": portfolio_review,
    }


@router.put("/profile")
def update_fire_profile(
    req: UpdateFIREProfileRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    profile = db.query(FinancialProfile).filter(FinancialProfile.user_id == current_user.id).first()
    if not profile:
        profile = FinancialProfile(user_id=current_user.id)
        db.add(profile)

    profile.current_age = req.current_age
    profile.target_fire_age = req.target_fire_age
    profile.monthly_living_expense = req.monthly_living_expense
    profile.risk_tolerance = req.risk_tolerance.upper()
    profile.fire_target_amount = req.monthly_living_expense * 12 * 25

    confirmed = get_confirmed_fields_set(profile)
    confirmed.update({"age_and_retirement", "monthly_living_expense", "risk_profile"})
    save_confirmed_fields_set(profile, confirmed)

    db.commit()
    db.refresh(profile)
    return profile


@router.post("/calculate")
def calculate_custom_fire(req: CalculateFIRERequest):
    """Calculates FIRE simulation on the fly with custom parameters."""
    metrics = calculate_fire_metrics(
        current_age=req.current_age,
        target_fire_age=req.target_fire_age,
        monthly_expenses=req.monthly_expenses,
        current_net_worth=req.current_net_worth,
        monthly_savings=req.monthly_savings,
        annual_return_rate=req.annual_return_rate,
    )
    return metrics

