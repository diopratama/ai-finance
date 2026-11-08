from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db import Wallet, Transaction, User, get_db
from app.auth import get_current_user
from app.api.budgets import compute_monthly_allocation_data, get_current_month_key

router = APIRouter(prefix="/wallets", tags=["Wallets"])


class CreateWalletRequest(BaseModel):
    name: str
    type: str = "BANK"  # Any preset or custom free-text type e.g. BANK, EWALLET, KANTONG DIGITAL, BANK SYARIAH
    balance: float = 0.0
    currency: str = "IDR"
    color: str = "#f0b000"
    is_default: bool = False


class UpdateWalletRequest(BaseModel):
    name: Optional[str] = None
    type: Optional[str] = None
    balance: Optional[float] = None
    color: Optional[str] = None
    is_default: Optional[bool] = None
    is_archived: Optional[bool] = None


class TransferRequest(BaseModel):
    from_wallet_id: str
    to_wallet_id: str
    amount: float
    description: Optional[str] = "Transfer antar-wallet"


@router.get("")
def list_wallets(
    month: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    wallets = (
        db.query(Wallet)
        .filter(Wallet.user_id == current_user.id, Wallet.is_archived == False)
        .order_by(Wallet.is_default.desc(), Wallet.created_at.asc())
        .all()
    )
    total_balance = sum(w.balance for w in wallets)

    alloc = compute_monthly_allocation_data(current_user, db, month or get_current_month_key())
    alloc_by_wallet = {wa["wallet_id"]: wa for wa in alloc["wallet_allocations"]}

    return {
        "total_balance": round(total_balance, 2),
        "currency": current_user.base_currency,
        "month_key": alloc["month_key"],
        "wallets": [
            {
                "id": w.id,
                "name": w.name,
                "type": w.type,
                "balance": round(w.balance, 2),
                "currency": w.currency,
                "color": w.color,
                "is_default": w.is_default,
                "created_at": w.created_at.isoformat(),
                "allocated_budget": alloc_by_wallet.get(w.id, {}).get("total_monthly_budget", 0.0),
                "remaining_commitment": alloc_by_wallet.get(w.id, {}).get("remaining_commitment", 0.0),
                "sinking_fund_held": alloc_by_wallet.get(w.id, {}).get("sinking_fund_held", 0.0),
                "free_balance": alloc_by_wallet.get(w.id, {}).get("free_unallocated_balance", round(max(0.0, w.balance), 2)),
                "shortfall_amount": alloc_by_wallet.get(w.id, {}).get("shortfall_amount", 0.0),
                "funding_status": alloc_by_wallet.get(w.id, {}).get("status", "IDLE"),
                "assigned_items_count": alloc_by_wallet.get(w.id, {}).get("items_count", 0),
            }
            for w in wallets
        ],
    }


@router.post("")
def create_wallet(req: CreateWalletRequest, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    clean_name = req.name.strip()
    if not clean_name:
        raise HTTPException(status_code=400, detail="Nama dompet tidak boleh kosong")
    clean_type = (req.type or "BANK").strip().upper()[:64] or "BANK"

    if req.is_default:
        db.query(Wallet).filter(Wallet.user_id == current_user.id).update({"is_default": False})

    wallet = Wallet(
        user_id=current_user.id,
        name=clean_name[:100],
        type=clean_type,
        balance=req.balance,
        currency=req.currency.strip().upper() or "IDR",
        color=req.color or "#f0b000",
        is_default=req.is_default,
    )
    db.add(wallet)
    db.commit()
    db.refresh(wallet)
    return {
        "id": wallet.id,
        "name": wallet.name,
        "type": wallet.type,
        "balance": round(wallet.balance, 2),
        "currency": wallet.currency,
        "color": wallet.color,
        "is_default": wallet.is_default,
        "created_at": wallet.created_at.isoformat(),
    }


@router.put("/{wallet_id}")
def update_wallet(wallet_id: str, req: UpdateWalletRequest, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    wallet = db.query(Wallet).filter(Wallet.id == wallet_id, Wallet.user_id == current_user.id).first()
    if not wallet:
        raise HTTPException(status_code=404, detail="Wallet not found")

    if req.is_default:
        db.query(Wallet).filter(Wallet.user_id == current_user.id).update({"is_default": False})

    updates = req.model_dump(exclude_unset=True)
    if "name" in updates and updates["name"] is not None:
        clean_name = updates["name"].strip()
        if clean_name:
            wallet.name = clean_name[:100]
    if "type" in updates and updates["type"] is not None:
        clean_type = updates["type"].strip().upper()[:64]
        if clean_type:
            wallet.type = clean_type
    if "balance" in updates and updates["balance"] is not None:
        wallet.balance = float(updates["balance"])
    if "color" in updates and updates["color"] is not None:
        wallet.color = updates["color"]
    if "is_default" in updates and updates["is_default"] is not None:
        wallet.is_default = bool(updates["is_default"])
    if "is_archived" in updates and updates["is_archived"] is not None:
        wallet.is_archived = bool(updates["is_archived"])

    db.commit()
    db.refresh(wallet)
    return {
        "id": wallet.id,
        "name": wallet.name,
        "type": wallet.type,
        "balance": round(wallet.balance, 2),
        "currency": wallet.currency,
        "color": wallet.color,
        "is_default": wallet.is_default,
        "created_at": wallet.created_at.isoformat(),
    }


@router.delete("/{wallet_id}")
def delete_wallet(wallet_id: str, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    wallet = db.query(Wallet).filter(Wallet.id == wallet_id, Wallet.user_id == current_user.id).first()
    if not wallet:
        raise HTTPException(status_code=404, detail="Wallet not found")

    wallet.is_archived = True
    db.commit()
    return {"message": "Wallet archived successfully"}


@router.post("/transfer")
def transfer_between_wallets(req: TransferRequest, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if req.amount <= 0:
        raise HTTPException(status_code=400, detail="Transfer amount must be positive")

    from_w = db.query(Wallet).filter(Wallet.id == req.from_wallet_id, Wallet.user_id == current_user.id).first()
    to_w = db.query(Wallet).filter(Wallet.id == req.to_wallet_id, Wallet.user_id == current_user.id).first()

    if not from_w or not to_w:
        raise HTTPException(status_code=404, detail="One or both wallets not found")

    from_w.balance -= req.amount
    to_w.balance += req.amount

    tx = Transaction(
        user_id=current_user.id,
        wallet_id=from_w.id,
        to_wallet_id=to_w.id,
        type="TRANSFER",
        amount=req.amount,
        currency=from_w.currency,
        amount_in_base=req.amount,
        description=req.description or f"Transfer dari {from_w.name} ke {to_w.name}",
        raw_source="WEB",
    )
    db.add(tx)
    db.commit()
    return {"message": "Transfer completed successfully", "tx_id": tx.id}
