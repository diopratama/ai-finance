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


_ID_MONTH_NAMES = {
    1: "Januari", 2: "Februari", 3: "Maret", 4: "April",
    5: "Mei", 6: "Juni", 7: "Juli", 8: "Agustus",
    9: "September", 10: "Oktober", 11: "November", 12: "Desember",
}

_ID_SHORT_MONTHS = {
    1: "Jan", 2: "Feb", 3: "Mar", 4: "Apr",
    5: "Mei", 6: "Jun", 7: "Jul", 8: "Agu",
    9: "Sep", 10: "Okt", 11: "Nov", 12: "Des",
}


def _format_month_label(month_key: str, short: bool = False) -> str:
    try:
        y_str, m_str = month_key.split("-")
        y, m = int(y_str), int(m_str)
        m_name = (_ID_SHORT_MONTHS if short else _ID_MONTH_NAMES).get(m, m_str)
        return f"{m_name} {str(y)[2:]}" if short else f"{m_name} {y}"
    except Exception:
        return month_key


def _shift_month_key(month_key: str, delta_months: int) -> str:
    try:
        y_str, m_str = month_key.split("-")
        y, m = int(y_str), int(m_str)
        total_m = (y * 12 + (m - 1)) + delta_months
        ny = total_m // 12
        nm = (total_m % 12) + 1
        return f"{ny:04d}-{nm:02d}"
    except Exception:
        return month_key


def _tx_month_key(tx: Transaction) -> str:
    if tx.transaction_date:
        return tx.transaction_date.strftime("%Y-%m")
    return datetime.now(timezone.utc).strftime("%Y-%m")


@router.get("")
def list_transactions(
    wallet_id: Optional[str] = None,
    category_id: Optional[str] = None,
    budget_id: Optional[str] = None,
    type: Optional[str] = None,
    month: Optional[str] = None,
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
    if search and isinstance(search, str):
        query = query.filter(
            (Transaction.description.ilike(f"%{search}%")) | (Transaction.merchant.ilike(f"%{search}%"))
        )

    month_str = month.strip() if isinstance(month, str) and month.strip() else None
    if month_str and len(month_str) == 7 and "-" in month_str:
        try:
            y_s, m_s = month_str.split("-")
            yr, mo = int(y_s), int(m_s)
            start_dt = datetime(yr, mo, 1)
            next_mk = _shift_month_key(month_str, 1)
            ny_s, nm_s = next_mk.split("-")
            end_dt = datetime(int(ny_s), int(nm_s), 1)
            query = query.filter(Transaction.transaction_date >= start_dt, Transaction.transaction_date < end_dt)
        except Exception:
            pass

    limit_num = limit if isinstance(limit, int) else 50
    offset_num = offset if isinstance(offset, int) else 0

    total_count = query.count()
    transactions = query.order_by(desc(Transaction.transaction_date)).offset(offset_num).limit(limit_num).all()

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
def get_transaction_summary(
    month: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Computes total & monthly income/expense, MoM comparison, 6-month cashflow trend, category & wallet breakdowns."""
    acc_wallets = get_accessible_wallets(db, current_user.id, min_role="VIEWER")
    acc_wallet_ids = [w.id for w in acc_wallets]
    wallet_map = {w.id: w for w in acc_wallets}

    transactions = (
        db.query(Transaction)
        .filter((Transaction.user_id == current_user.id) | (Transaction.wallet_id.in_(acc_wallet_ids)))
        .all()
    )

    total_income = sum(t.amount_in_base for t in transactions if t.type == "INCOME")
    total_expense = sum(t.amount_in_base for t in transactions if t.type == "EXPENSE")
    net_savings = total_income - total_expense

    month_str = month.strip() if isinstance(month, str) and month.strip() and len(month.strip()) == 7 else None
    target_mk = month_str or datetime.now(timezone.utc).strftime("%Y-%m")
    prev_mk = _shift_month_key(target_mk, -1)

    # Group transactions by month_key
    tx_by_month = {}
    for t in transactions:
        mk = _tx_month_key(t)
        tx_by_month.setdefault(mk, []).append(t)

    month_txs = tx_by_month.get(target_mk, [])
    prev_txs = tx_by_month.get(prev_mk, [])

    m_income = sum(t.amount_in_base for t in month_txs if t.type == "INCOME")
    m_expense = sum(t.amount_in_base for t in month_txs if t.type == "EXPENSE")
    m_transfer = sum(t.amount_in_base for t in month_txs if t.type == "TRANSFER")
    m_net = m_income - m_expense
    m_savings_rate = round((m_net / m_income) * 100, 1) if m_income > 0 else 0.0

    p_income = sum(t.amount_in_base for t in prev_txs if t.type == "INCOME")
    p_expense = sum(t.amount_in_base for t in prev_txs if t.type == "EXPENSE")

    income_mom_pct = round(((m_income - p_income) / p_income) * 100, 1) if p_income > 0 else (100.0 if m_income > 0 else 0.0)
    expense_mom_pct = round(((m_expense - p_expense) / p_expense) * 100, 1) if p_expense > 0 else (100.0 if m_expense > 0 else 0.0)

    # 6-month trend ending at target_mk
    monthly_trend = []
    for delta in range(-5, 1):
        mk = _shift_month_key(target_mk, delta)
        t_list = tx_by_month.get(mk, [])
        inc = sum(t.amount_in_base for t in t_list if t.type == "INCOME")
        exp = sum(t.amount_in_base for t in t_list if t.type == "EXPENSE")
        net_cf = inc - exp
        sr = round((net_cf / inc) * 100, 1) if inc > 0 else 0.0
        monthly_trend.append({
            "month_key": mk,
            "label": _format_month_label(mk, short=True),
            "full_label": _format_month_label(mk, short=False),
            "income": round(inc, 2),
            "expense": round(exp, 2),
            "net_cashflow": round(net_cf, 2),
            "savings_rate": sr,
            "tx_count": len(t_list),
        })

    # Category breakdown for target month (or all transactions if month_str was explicitly "ALL")
    active_scope_txs = month_txs
    exp_cat_map = {}
    inc_cat_map = {}
    for t in active_scope_txs:
        cat_name = t.category.name if t.category else ("Transfer" if t.type == "TRANSFER" else "Lain-lain")
        cat_color = t.category.color if t.category else "#64748b"
        if t.type == "EXPENSE":
            if cat_name not in exp_cat_map:
                exp_cat_map[cat_name] = {"name": cat_name, "color": cat_color, "total": 0.0, "count": 0}
            exp_cat_map[cat_name]["total"] += t.amount_in_base
            exp_cat_map[cat_name]["count"] += 1
        elif t.type == "INCOME":
            if cat_name not in inc_cat_map:
                inc_cat_map[cat_name] = {"name": cat_name, "color": cat_color or "#10b981", "total": 0.0, "count": 0}
            inc_cat_map[cat_name]["total"] += t.amount_in_base
            inc_cat_map[cat_name]["count"] += 1

    expense_categories = sorted(exp_cat_map.values(), key=lambda x: x["total"], reverse=True)
    for c in expense_categories:
        c["total"] = round(c["total"], 2)
        c["percentage"] = round((c["total"] / m_expense) * 100, 1) if m_expense > 0 else 0.0

    income_categories = sorted(inc_cat_map.values(), key=lambda x: x["total"], reverse=True)
    for c in income_categories:
        c["total"] = round(c["total"], 2)
        c["percentage"] = round((c["total"] / m_income) * 100, 1) if m_income > 0 else 0.0

    # All-time categories for legacy compatibility
    all_cat_map = {}
    for t in transactions:
        if t.type == "EXPENSE":
            cat_name = t.category.name if t.category else "Lain-lain"
            cat_color = t.category.color if t.category else "#64748b"
            if cat_name not in all_cat_map:
                all_cat_map[cat_name] = {"name": cat_name, "color": cat_color, "total": 0.0}
            all_cat_map[cat_name]["total"] += t.amount_in_base

    # Wallet breakdown for selected month
    w_stats = {}
    for w in acc_wallets:
        w_stats[w.id] = {
            "wallet_id": w.id,
            "wallet_name": w.name,
            "wallet_color": w.color,
            "wallet_type": w.type,
            "current_balance": round(w.balance, 2),
            "income": 0.0,
            "expense": 0.0,
            "transfer_in": 0.0,
            "transfer_out": 0.0,
            "tx_count": 0,
        }

    for t in active_scope_txs:
        if t.wallet_id in w_stats:
            if t.type == "INCOME":
                w_stats[t.wallet_id]["income"] += t.amount_in_base
                w_stats[t.wallet_id]["tx_count"] += 1
            elif t.type == "EXPENSE":
                w_stats[t.wallet_id]["expense"] += t.amount_in_base
                w_stats[t.wallet_id]["tx_count"] += 1
            elif t.type == "TRANSFER":
                w_stats[t.wallet_id]["transfer_out"] += t.amount_in_base
                w_stats[t.wallet_id]["tx_count"] += 1
        if t.type == "TRANSFER" and t.to_wallet_id and t.to_wallet_id in w_stats:
            w_stats[t.to_wallet_id]["transfer_in"] += t.amount_in_base
            w_stats[t.to_wallet_id]["tx_count"] += 1

    wallet_breakdown = []
    for ws in w_stats.values():
        ws["income"] = round(ws["income"], 2)
        ws["expense"] = round(ws["expense"], 2)
        ws["transfer_in"] = round(ws["transfer_in"], 2)
        ws["transfer_out"] = round(ws["transfer_out"], 2)
        ws["net_cashflow"] = round((ws["income"] + ws["transfer_in"]) - (ws["expense"] + ws["transfer_out"]), 2)
        wallet_breakdown.append(ws)
    wallet_breakdown.sort(key=lambda x: (x["income"] + x["expense"] + x["transfer_in"] + x["transfer_out"]), reverse=True)

    return {
        "total_income": round(total_income, 2),
        "total_expense": round(total_expense, 2),
        "net_savings": round(net_savings, 2),
        "categories": list(all_cat_map.values()),
        "month_key": target_mk,
        "month_label": _format_month_label(target_mk, short=False),
        "monthly": {
            "month_key": target_mk,
            "month_label": _format_month_label(target_mk, short=False),
            "income": round(m_income, 2),
            "expense": round(m_expense, 2),
            "transfer_volume": round(m_transfer, 2),
            "net_cashflow": round(m_net, 2),
            "savings_rate": m_savings_rate,
            "tx_count": len(month_txs),
            "prev_month_key": prev_mk,
            "prev_income": round(p_income, 2),
            "prev_expense": round(p_expense, 2),
            "income_mom_pct": income_mom_pct,
            "expense_mom_pct": expense_mom_pct,
        },
        "monthly_trend": monthly_trend,
        "expense_categories": expense_categories,
        "income_categories": income_categories,
        "wallet_breakdown": wallet_breakdown,
    }
