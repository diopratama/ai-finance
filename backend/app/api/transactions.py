from datetime import datetime, timezone
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import desc

from app.db import (
    Budget,
    Transaction,
    Wallet,
    Category,
    User,
    get_db,
    get_accessible_wallets,
    get_accessible_wallet_by_id,
    get_wallet_role,
)
from app.auth import get_current_user

router = APIRouter(prefix="/transactions", tags=["Transactions"])


class CreateTransactionRequest(BaseModel):
    wallet_id: Optional[str] = None
    category_id: Optional[str] = None
    budget_id: Optional[str] = None
    type: str = "EXPENSE"  # EXPENSE, INCOME, TRANSFER
    amount: float
    currency: str = "IDR"
    description: str
    merchant: Optional[str] = None
    raw_source: str = "WEB"
    raw_input: Optional[str] = None
    transaction_date: Optional[datetime] = None


@router.get("")
def list_transactions(
    wallet_id: Optional[str] = None,
    category_id: Optional[str] = None,
    budget_id: Optional[str] = None,
    type: Optional[str] = None,
    search: Optional[str] = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    acc_wallets = get_accessible_wallets(db, current_user.id, min_role="VIEWER")
    acc_wallet_ids = [w.id for w in acc_wallets]

    query = db.query(Transaction).filter(
        (Transaction.user_id == current_user.id) | (Transaction.wallet_id.in_(acc_wallet_ids))
    )

    if wallet_id:
        query = query.filter(Transaction.wallet_id == wallet_id)
    if category_id:
        query = query.filter(Transaction.category_id == category_id)
    if budget_id:
        query = query.filter(Transaction.budget_id == budget_id)
    if type:
        query = query.filter(Transaction.type == type.upper())
    if search:
        query = query.filter(
            (Transaction.description.ilike(f"%{search}%")) | (Transaction.merchant.ilike(f"%{search}%"))
        )

    total_count = query.count()
    transactions = query.order_by(desc(Transaction.transaction_date)).offset(offset).limit(limit).all()

    wallet_map = {w.id: w for w in acc_wallets}
    items = []
    for tx in transactions:
        to_wallet_info = None
        if tx.to_wallet_id:
            tw = wallet_map.get(tx.to_wallet_id) or db.query(Wallet).filter(Wallet.id == tx.to_wallet_id).first()
            if tw:
                to_wallet_info = {"id": tw.id, "name": tw.name, "color": tw.color}

        items.append({
            "id": tx.id,
            "type": tx.type,
            "amount": tx.amount,
            "currency": tx.currency,
            "amount_in_base": tx.amount_in_base,
            "description": tx.description,
            "merchant": tx.merchant,
            "wallet": {"id": tx.wallet.id, "name": tx.wallet.name, "color": tx.wallet.color} if tx.wallet else None,
            "to_wallet": to_wallet_info,
            "category": {"id": tx.category.id, "name": tx.category.name, "icon": tx.category.icon, "color": tx.category.color} if tx.category else None,
            "budget": (
                {
                    "id": tx.budget.id,
                    "name": tx.budget.name or (tx.budget.category.name if tx.budget.category else "Pos Anggaran"),
                    "group_type": tx.budget.group_type,
                }
                if tx.budget
                else None
            ),
            "created_by": {
                "id": tx.user.id,
                "name": tx.user.full_name or tx.user.email,
                "email": tx.user.email,
            } if tx.user else None,
            "is_own": tx.user_id == current_user.id,
            "raw_source": tx.raw_source,
            "transaction_date": tx.transaction_date.isoformat(),
        })

    return {
        "total": total_count,
        "limit": limit,
        "offset": offset,
        "items": items,
    }


@router.post("")
def create_transaction(
    req: CreateTransactionRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    linked_budget = None
    if req.budget_id:
        linked_budget = db.query(Budget).filter(
            Budget.id == req.budget_id,
            Budget.user_id == current_user.id,
        ).first()
        if not linked_budget:
            raise HTTPException(status_code=404, detail="Pos anggaran tidak ditemukan")

    resolved_wallet_id = req.wallet_id or (linked_budget.wallet_id if linked_budget else None)
    wallet = None
    if resolved_wallet_id:
        w_res = get_accessible_wallet_by_id(db, current_user.id, resolved_wallet_id, min_role="EDITOR")
        if not w_res:
            raise HTTPException(status_code=403, detail="Anda tidak memiliki izin Editor untuk mencatat transaksi di dompet ini")
        wallet, _ = w_res

    if not wallet:
        wallet = (
            db.query(Wallet)
            .filter(Wallet.user_id == current_user.id, Wallet.is_archived == False)
            .order_by(Wallet.is_default.desc(), Wallet.created_at.asc())
            .first()
        )
    if not wallet:
        raise HTTPException(status_code=404, detail="Dompet tidak ditemukan")

    tx_type = req.type.upper()
    if tx_type == "EXPENSE":
        wallet.balance -= req.amount
    elif tx_type == "INCOME":
        wallet.balance += req.amount

    resolved_category_id = req.category_id or (linked_budget.category_id if linked_budget else None)

    tx = Transaction(
        user_id=current_user.id,
        wallet_id=wallet.id,
        category_id=resolved_category_id,
        budget_id=linked_budget.id if linked_budget else None,
        type=tx_type,
        amount=req.amount,
        currency=req.currency.upper(),
        amount_in_base=req.amount,
        description=req.description,
        merchant=req.merchant,
        raw_source=req.raw_source,
        raw_input=req.raw_input,
        transaction_date=req.transaction_date or datetime.now(timezone.utc),
    )
    db.add(tx)
    db.commit()
    db.refresh(tx)
    return {
        "id": tx.id,
        "type": tx.type,
        "amount": tx.amount,
        "currency": tx.currency,
        "description": tx.description,
        "wallet_id": tx.wallet_id,
        "category_id": tx.category_id,
        "budget_id": tx.budget_id,
        "transaction_date": tx.transaction_date.isoformat(),
    }


@router.delete("/{tx_id}")
def delete_transaction(tx_id: str, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    tx = db.query(Transaction).filter(Transaction.id == tx_id).first()
    if not tx:
        raise HTTPException(status_code=404, detail="Transaction not found")

    is_creator = tx.user_id == current_user.id
    is_wallet_owner = tx.wallet and tx.wallet.user_id == current_user.id

    if not is_creator and not is_wallet_owner:
        raise HTTPException(status_code=403, detail="Anda tidak memiliki izin untuk menghapus transaksi ini")

    if tx.wallet:
        if tx.type == "EXPENSE":
            tx.wallet.balance += tx.amount
        elif tx.type == "INCOME":
            tx.wallet.balance -= tx.amount
        elif tx.type == "TRANSFER":
            tx.wallet.balance += tx.amount
            if tx.to_wallet_id:
                dest_w = db.query(Wallet).filter(Wallet.id == tx.to_wallet_id).first()
                if dest_w:
                    dest_w.balance -= tx.amount

    db.delete(tx)
    db.commit()
    return {"message": "Transaction deleted successfully"}


@router.get("/summary")
def get_transaction_summary(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Computes total income, total expense, net savings, and category distribution."""
    acc_wallets = get_accessible_wallets(db, current_user.id, min_role="VIEWER")
    acc_wallet_ids = [w.id for w in acc_wallets]

    transactions = (
        db.query(Transaction)
        .filter((Transaction.user_id == current_user.id) | (Transaction.wallet_id.in_(acc_wallet_ids)))
        .all()
    )

    total_income = sum(t.amount_in_base for t in transactions if t.type == "INCOME")
    total_expense = sum(t.amount_in_base for t in transactions if t.type == "EXPENSE")
    net_savings = total_income - total_expense

    cat_map = {}
    for t in transactions:
        if t.type == "EXPENSE":
            cat_name = t.category.name if t.category else "Lain-lain"
            cat_color = t.category.color if t.category else "#64748b"
            if cat_name not in cat_map:
                cat_map[cat_name] = {"name": cat_name, "color": cat_color, "total": 0.0}
            cat_map[cat_name]["total"] += t.amount_in_base

    return {
        "total_income": round(total_income, 2),
        "total_expense": round(total_expense, 2),
        "net_savings": round(net_savings, 2),
        "categories": list(cat_map.values()),
    }
