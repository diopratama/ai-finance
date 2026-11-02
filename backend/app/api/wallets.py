from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db import Wallet, Transaction, User, get_db
from app.auth import get_current_user

router = APIRouter(prefix="/wallets", tags=["Wallets"])


class CreateWalletRequest(BaseModel):
    name: str
    type: str = "BANK"  # CASH, BANK, EWALLET, INVESTMENT, CREDIT
    balance: float = 0.0
    currency: str = "IDR"
    color: str = "#3b82f6"
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
def list_wallets(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    wallets = db.query(Wallet).filter(Wallet.user_id == current_user.id, Wallet.is_archived == False).all()
    total_balance = sum(w.balance for w in wallets)
    return {
        "total_balance": round(total_balance, 2),
        "currency": current_user.base_currency,
        "wallets": [
            {
                "id": w.id,
                "name": w.name,
                "type": w.type,
                "balance": w.balance,
                "currency": w.currency,
                "color": w.color,
                "is_default": w.is_default,
                "created_at": w.created_at.isoformat(),
            }
            for w in wallets
        ],
    }


@router.post("")
def create_wallet(req: CreateWalletRequest, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if req.is_default:
        # unset previous default
        db.query(Wallet).filter(Wallet.user_id == current_user.id).update({"is_default": False})

    wallet = Wallet(
        user_id=current_user.id,
        name=req.name,
        type=req.type.upper(),
        balance=req.balance,
        currency=req.currency.upper(),
        color=req.color,
        is_default=req.is_default,
    )
    db.add(wallet)
    db.commit()
    db.refresh(wallet)
    return wallet


@router.put("/{wallet_id}")
def update_wallet(wallet_id: str, req: UpdateWalletRequest, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    wallet = db.query(Wallet).filter(Wallet.id == wallet_id, Wallet.user_id == current_user.id).first()
    if not wallet:
        raise HTTPException(status_code=404, detail="Wallet not found")

    if req.is_default:
        db.query(Wallet).filter(Wallet.user_id == current_user.id).update({"is_default": False})

    for field, val in req.model_dump(exclude_unset=True).items():
        setattr(wallet, field, val)

    db.commit()
    db.refresh(wallet)
    return wallet


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

