from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db import Budget, Category, Transaction, User, get_db
from app.auth import get_current_user

router = APIRouter(prefix="/budgets", tags=["Budgets & Categories"])


class CreateBudgetRequest(BaseModel):
    category_id: str
    limit_amount: float
    period: str = "MONTHLY"


@router.get("/categories")
def list_categories(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Lists system and user-specific categories."""
    categories = db.query(Category).filter(
        (Category.is_system == True) | (Category.user_id == current_user.id)
    ).all()
    return [
        {
            "id": c.id,
            "name": c.name,
            "icon": c.icon,
            "color": c.color,
            "type": c.type,
            "is_system": c.is_system,
        }
        for c in categories
    ]


@router.get("")
def list_budgets(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    budgets = db.query(Budget).filter(Budget.user_id == current_user.id).all()

    # Calculate actual spending per category
    results = []
    for b in budgets:
        spent = db.query(Transaction).filter(
            Transaction.user_id == current_user.id,
            Transaction.category_id == b.category_id,
            Transaction.type == "EXPENSE",
        ).all()
        spent_amount = sum(t.amount_in_base for t in spent)
        percent_used = min(100.0, round((spent_amount / b.limit_amount) * 100, 1)) if b.limit_amount > 0 else 0.0

        results.append({
            "id": b.id,
            "category": {
                "id": b.category.id,
                "name": b.category.name,
                "icon": b.category.icon,
                "color": b.category.color,
            } if b.category else None,
            "limit_amount": b.limit_amount,
            "spent_amount": round(spent_amount, 2),
            "remaining_amount": round(max(0, b.limit_amount - spent_amount), 2),
            "percent_used": percent_used,
            "is_over_budget": spent_amount > b.limit_amount,
            "period": b.period,
        })

    return results


@router.post("")
def create_budget(req: CreateBudgetRequest, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    category = db.query(Category).filter(Category.id == req.category_id).first()
    if not category:
        raise HTTPException(status_code=404, detail="Category not found")

    existing = db.query(Budget).filter(
        Budget.user_id == current_user.id,
        Budget.category_id == req.category_id,
    ).first()
    if existing:
        existing.limit_amount = req.limit_amount
        db.commit()
        db.refresh(existing)
        return existing

    budget = Budget(
        user_id=current_user.id,
        category_id=req.category_id,
        limit_amount=req.limit_amount,
        period=req.period.upper(),
    )
    db.add(budget)
    db.commit()
    db.refresh(budget)
    return budget


@router.delete("/{budget_id}")
def delete_budget(budget_id: str, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    budget = db.query(Budget).filter(Budget.id == budget_id, Budget.user_id == current_user.id).first()
    if not budget:
        raise HTTPException(status_code=404, detail="Budget not found")
    db.delete(budget)
    db.commit()
    return {"message": "Budget deleted successfully"}

