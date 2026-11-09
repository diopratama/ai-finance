import json
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr
from sqlalchemy.orm import Session

from app.db import (
    FinancialProfile,
    Wallet,
    Transaction,
    User,
    WalletMember,
    get_db,
    get_accessible_wallets,
    get_accessible_wallet_by_id,
    get_wallet_role,
)
from app.auth import get_current_user
from app.api.budgets import compute_monthly_allocation_data, get_current_month_key
from app.services.fire_engine import (
    ASSET_CLASS_LABELS,
    evaluate_investment_portfolio,
    infer_wallet_asset_class,
    is_investment_wallet,
)
from app.services.market_rates_service import (
    convert_to_idr,
    fetch_live_market_rates,
    format_currency_with_base,
    normalize_currency_unit,
)

router = APIRouter(prefix="/wallets", tags=["Wallets"])


class CreateWalletRequest(BaseModel):
    name: str
    type: str = "BANK"  # Any preset or custom free-text type e.g. BANK, EWALLET, KANTONG DIGITAL, BANK SYARIAH
    asset_class: Optional[str] = None  # Optional explicit class: EQUITY, BOND, MONEY_MARKET, GOLD, CRYPTO
    balance: float = 0.0
    currency: str = "IDR"
    color: str = "#f0b000"
    is_default: bool = False


class UpdateWalletRequest(BaseModel):
    name: Optional[str] = None
    type: Optional[str] = None
    asset_class: Optional[str] = None
    balance: Optional[float] = None
    currency: Optional[str] = None
    color: Optional[str] = None
    is_default: Optional[bool] = None
    is_archived: Optional[bool] = None


class TransferRequest(BaseModel):
    from_wallet_id: str
    to_wallet_id: str
    amount: float
    description: Optional[str] = "Transfer antar-wallet"


class AddWalletMemberRequest(BaseModel):
    email: EmailStr
    role: str = "EDITOR"  # "EDITOR" | "VIEWER"


class UpdateWalletMemberRequest(BaseModel):
    role: str  # "EDITOR" | "VIEWER"


class UpdatePortfolioStrategyRequest(BaseModel):
    strategy: str
    custom_allocations: Optional[Dict[str, float]] = None


def _build_user_portfolio_review(user: User, wallets: List[Wallet], db: Session) -> dict:
    profile = db.query(FinancialProfile).filter(FinancialProfile.user_id == user.id).first()
    risk_tolerance = (profile.risk_tolerance if profile and profile.risk_tolerance else "MODERATE").upper()
    sharia_pref = bool(profile.sharia_preference) if profile else False
    monthly_exp = (profile.monthly_living_expense if profile and (profile.monthly_living_expense or 0) > 0 else 8_000_000.0)
    is_married = ((profile.marital_status if profile else "SINGLE") or "SINGLE").upper() == "MARRIED"
    deps = int(profile.dependents_count or 0) if profile else 0
    strategy = getattr(profile, "portfolio_strategy", None) if profile else None
    custom_raw = getattr(profile, "custom_allocations_json", None) if profile else None
    custom_alloc = None
    if custom_raw:
        try:
            custom_alloc = json.loads(custom_raw)
        except Exception:
            custom_alloc = None

    liquid_cash = sum(
        max(0.0, convert_to_idr(w.balance, w.currency))
        for w in wallets
        if not is_investment_wallet(w.name, w.type, getattr(w, "asset_class", None))
        and not any(k in (w.type or "").upper() for k in ("CREDIT", "KREDIT", "PAYLATER", "LOAN", "UTANG", "HUTANG", "CC"))
    )

    return evaluate_investment_portfolio(
        wallets=wallets,
        risk_tolerance=risk_tolerance,
        sharia_preference=sharia_pref,
        liquid_cash_balance=liquid_cash,
        monthly_expenses=monthly_exp,
        is_married=is_married,
        dependents_count=deps,
        strategy=strategy,
        custom_allocations=custom_alloc,
    )


@router.get("/portfolio-review")
def get_portfolio_review(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    wallets = get_accessible_wallets(db, current_user.id, min_role="VIEWER")
    return _build_user_portfolio_review(current_user, wallets, db)


@router.put("/portfolio-strategy")
def update_portfolio_strategy(
    req: UpdatePortfolioStrategyRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    profile = db.query(FinancialProfile).filter(FinancialProfile.user_id == current_user.id).first()
    if not profile:
        profile = FinancialProfile(user_id=current_user.id)
        db.add(profile)
    profile.portfolio_strategy = (req.strategy or "AUTO_RISK").strip().upper()
    if req.custom_allocations is not None:
        profile.custom_allocations_json = json.dumps(req.custom_allocations)
    db.commit()
    db.refresh(profile)

    wallets = get_accessible_wallets(db, current_user.id, min_role="VIEWER")
    review = _build_user_portfolio_review(current_user, wallets, db)
    return {
        "success": True,
        "portfolio_strategy": profile.portfolio_strategy,
        "custom_allocations": json.loads(profile.custom_allocations_json) if profile.custom_allocations_json else {},
        "portfolio_review": review,
    }


@router.get("")
def list_wallets(
    month: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    wallets = get_accessible_wallets(db, current_user.id, min_role="VIEWER")
    market_rates = fetch_live_market_rates()

    personal_balance = sum(convert_to_idr(w.balance, w.currency) for w in wallets if w.user_id == current_user.id)
    shared_balance = sum(convert_to_idr(w.balance, w.currency) for w in wallets if w.user_id != current_user.id)
    total_balance = personal_balance + shared_balance

    alloc = compute_monthly_allocation_data(current_user, db, month or get_current_month_key())
    alloc_by_wallet = {wa["wallet_id"]: wa for wa in alloc.get("wallet_allocations", [])}

    serialized_wallets = []
    for w in wallets:
        role = get_wallet_role(db, w, current_user.id) or "VIEWER"
        members = [
            {
                "user_id": m.user_id,
                "name": m.user.full_name or m.user.email if m.user else "User",
                "email": m.user.email if m.user else "",
                "role": m.role,
                "created_at": m.created_at.isoformat(),
            }
            for m in w.members
        ]
        is_shared = (w.user_id != current_user.id) or (len(members) > 0)
        owner_info = (
            {
                "id": w.user.id,
                "name": w.user.full_name or w.user.email,
                "email": w.user.email,
            }
            if w.user
            else None
        )

        explicit_ac = getattr(w, "asset_class", None)
        resolved_ac = infer_wallet_asset_class(w.name, w.type, explicit_ac)
        is_inv = resolved_ac is not None
        norm_currency = normalize_currency_unit(w.currency)
        base_val = convert_to_idr(w.balance, norm_currency)
        fmt_info = format_currency_with_base(w.balance, norm_currency)

        serialized_wallets.append({
            "id": w.id,
            "name": w.name,
            "type": w.type,
            "asset_class": explicit_ac or resolved_ac,
            "asset_class_label": ASSET_CLASS_LABELS.get(resolved_ac, None) if resolved_ac else None,
            "is_investment": is_inv,
            "balance": round(w.balance, 2),
            "currency": norm_currency,
            "balance_in_base": round(base_val, 2),
            "formatted_native": fmt_info["native"],
            "formatted_base": fmt_info["formatted_idr"],
            "color": w.color,
            "is_default": w.is_default,
            "is_shared": is_shared,
            "access_role": role,
            "owner": owner_info,
            "members": members,
            "created_at": w.created_at.isoformat(),
            "allocated_budget": alloc_by_wallet.get(w.id, {}).get("total_monthly_budget", 0.0),
            "remaining_commitment": alloc_by_wallet.get(w.id, {}).get("remaining_commitment", 0.0),
            "sinking_fund_held": alloc_by_wallet.get(w.id, {}).get("sinking_fund_held", 0.0),
            "free_balance": alloc_by_wallet.get(w.id, {}).get("free_unallocated_balance", round(max(0.0, base_val), 2)),
            "shortfall_amount": alloc_by_wallet.get(w.id, {}).get("shortfall_amount", 0.0),
            "funding_status": alloc_by_wallet.get(w.id, {}).get("status", "IDLE"),
            "assigned_items_count": alloc_by_wallet.get(w.id, {}).get("items_count", 0),
        })

    portfolio_review = _build_user_portfolio_review(current_user, wallets, db)

    return {
        "total_balance": round(total_balance, 2),
        "personal_balance": round(personal_balance, 2),
        "shared_balance": round(shared_balance, 2),
        "investment_balance": portfolio_review["total_investment_balance"],
        "currency": current_user.base_currency,
        "month_key": alloc["month_key"],
        "wallets": serialized_wallets,
        "portfolio_review": portfolio_review,
        "market_rates": market_rates,
    }


@router.post("")
def create_wallet(req: CreateWalletRequest, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    clean_name = req.name.strip()
    if not clean_name:
        raise HTTPException(status_code=400, detail="Nama dompet tidak boleh kosong")
    clean_type = (req.type or "BANK").strip().upper()[:64] or "BANK"
    clean_ac = req.asset_class.strip().upper() if req.asset_class and req.asset_class.strip() else None
    if clean_ac and clean_ac not in ASSET_CLASS_LABELS:
        clean_ac = None

    if req.is_default:
        db.query(Wallet).filter(Wallet.user_id == current_user.id).update({"is_default": False})

    wallet = Wallet(
        user_id=current_user.id,
        name=clean_name[:100],
        type=clean_type,
        asset_class=clean_ac,
        balance=req.balance,
        currency=normalize_currency_unit(req.currency),
        color=req.color or "#f0b000",
        is_default=req.is_default,
    )
    db.add(wallet)
    db.commit()
    db.refresh(wallet)
    resolved_ac = infer_wallet_asset_class(wallet.name, wallet.type, wallet.asset_class)
    return {
        "id": wallet.id,
        "name": wallet.name,
        "type": wallet.type,
        "asset_class": wallet.asset_class or resolved_ac,
        "asset_class_label": ASSET_CLASS_LABELS.get(resolved_ac) if resolved_ac else None,
        "is_investment": resolved_ac is not None,
        "balance": round(wallet.balance, 2),
        "currency": wallet.currency,
        "color": wallet.color,
        "is_default": wallet.is_default,
        "access_role": "OWNER",
        "is_shared": False,
        "created_at": wallet.created_at.isoformat(),
    }


@router.put("/{wallet_id}")
def update_wallet(wallet_id: str, req: UpdateWalletRequest, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    wallet_res = get_accessible_wallet_by_id(db, current_user.id, wallet_id, min_role="OWNER")
    if not wallet_res:
        raise HTTPException(status_code=403, detail="Hanya pemilik dompet yang dapat mengubah informasi dompet")
    wallet, _ = wallet_res

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
    if "asset_class" in updates:
        raw_ac = (updates["asset_class"] or "").strip().upper()
        wallet.asset_class = raw_ac if raw_ac in ASSET_CLASS_LABELS else None
    if "balance" in updates and updates["balance"] is not None:
        wallet.balance = float(updates["balance"])
    if "currency" in updates and updates["currency"] is not None:
        wallet.currency = normalize_currency_unit(updates["currency"])
    if "color" in updates and updates["color"] is not None:
        wallet.color = updates["color"]
    if "is_default" in updates and updates["is_default"] is not None:
        wallet.is_default = bool(updates["is_default"])
    if "is_archived" in updates and updates["is_archived"] is not None:
        wallet.is_archived = bool(updates["is_archived"])

    db.commit()
    db.refresh(wallet)
    resolved_ac = infer_wallet_asset_class(wallet.name, wallet.type, wallet.asset_class)
    return {
        "id": wallet.id,
        "name": wallet.name,
        "type": wallet.type,
        "asset_class": wallet.asset_class or resolved_ac,
        "asset_class_label": ASSET_CLASS_LABELS.get(resolved_ac) if resolved_ac else None,
        "is_investment": resolved_ac is not None,
        "balance": round(wallet.balance, 2),
        "currency": wallet.currency,
        "color": wallet.color,
        "is_default": wallet.is_default,
        "access_role": "OWNER",
        "created_at": wallet.created_at.isoformat(),
    }


@router.delete("/{wallet_id}")
def delete_wallet(wallet_id: str, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    wallet_res = get_accessible_wallet_by_id(db, current_user.id, wallet_id, min_role="OWNER")
    if not wallet_res:
        raise HTTPException(status_code=403, detail="Hanya pemilik dompet yang dapat mengarsipkan dompet ini")
    wallet, _ = wallet_res

    wallet.is_archived = True
    db.commit()
    return {"message": "Dompet berhasil diarsipkan"}


@router.post("/transfer")
def transfer_between_wallets(req: TransferRequest, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if req.amount <= 0:
        raise HTTPException(status_code=400, detail="Nominal transfer harus lebih besar dari 0")

    from_res = get_accessible_wallet_by_id(db, current_user.id, req.from_wallet_id, min_role="EDITOR")
    to_res = get_accessible_wallet_by_id(db, current_user.id, req.to_wallet_id, min_role="EDITOR")

    if not from_res or not to_res:
        raise HTTPException(status_code=403, detail="Anda harus memiliki hak akses minimal Editor pada kedua dompet")

    from_w, _ = from_res
    to_w, _ = to_res

    if from_w.id == to_w.id:
        raise HTTPException(status_code=400, detail="Dompet sumber dan tujuan tidak boleh sama")

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
    return {"message": "Transfer berhasil dilakukan", "tx_id": tx.id}


# ==================== WALLET MEMBERS (SHARING) ====================


@router.post("/{wallet_id}/members")
def add_wallet_member(
    wallet_id: str,
    req: AddWalletMemberRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Invites a user by registered email to share this wallet with EDITOR or VIEWER role."""
    wallet_res = get_accessible_wallet_by_id(db, current_user.id, wallet_id, min_role="OWNER")
    if not wallet_res:
        raise HTTPException(status_code=403, detail="Hanya pemilik dompet yang dapat mengundang anggota")
    wallet, _ = wallet_res

    clean_email = req.email.strip().lower()
    if clean_email == current_user.email.strip().lower():
        raise HTTPException(status_code=400, detail="Anda adalah pemilik dompet ini")

    target_user = db.query(User).filter(User.email == clean_email).first()
    if not target_user:
        raise HTTPException(
            status_code=404,
            detail=f"Pengguna dengan email {clean_email} belum terdaftar di sistem. Minta pengguna mendaftar terlebih dahulu.",
        )

    clean_role = req.role.strip().upper()
    if clean_role not in ["EDITOR", "VIEWER"]:
        clean_role = "EDITOR"

    existing_member = db.query(WalletMember).filter(
        WalletMember.wallet_id == wallet.id,
        WalletMember.user_id == target_user.id,
    ).first()

    if existing_member:
        existing_member.role = clean_role
        db.commit()
        return {
            "message": f"Hak akses {target_user.full_name or target_user.email} diperbarui menjadi {clean_role}",
            "member": {
                "user_id": target_user.id,
                "name": target_user.full_name or target_user.email,
                "email": target_user.email,
                "role": existing_member.role,
            },
        }

    new_member = WalletMember(
        wallet_id=wallet.id,
        user_id=target_user.id,
        role=clean_role,
        invited_by_id=current_user.id,
    )
    db.add(new_member)
    db.commit()
    return {
        "message": f"Berhasil menambahkan {target_user.full_name or target_user.email} sebagai {clean_role}",
        "member": {
            "user_id": target_user.id,
            "name": target_user.full_name or target_user.email,
            "email": target_user.email,
            "role": new_member.role,
        },
    }


@router.put("/{wallet_id}/members/{member_user_id}")
def update_wallet_member_role(
    wallet_id: str,
    member_user_id: str,
    req: UpdateWalletMemberRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Updates the role (EDITOR / VIEWER) of an existing member. Only wallet OWNER can perform this."""
    wallet_res = get_accessible_wallet_by_id(db, current_user.id, wallet_id, min_role="OWNER")
    if not wallet_res:
        raise HTTPException(status_code=403, detail="Hanya pemilik dompet yang dapat mengubah hak akses anggota")

    clean_role = req.role.strip().upper()
    if clean_role not in ["EDITOR", "VIEWER"]:
        raise HTTPException(status_code=400, detail="Role harus berupa EDITOR atau VIEWER")

    member = db.query(WalletMember).filter(
        WalletMember.wallet_id == wallet_id,
        WalletMember.user_id == member_user_id,
    ).first()
    if not member:
        raise HTTPException(status_code=404, detail="Anggota tidak ditemukan pada dompet ini")

    member.role = clean_role
    db.commit()
    return {"message": "Hak akses berhasil diperbarui", "role": clean_role}


@router.delete("/{wallet_id}/members/{member_user_id}")
def remove_wallet_member(
    wallet_id: str,
    member_user_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Removes a member from the shared wallet. Can be done by OWNER or member themselves."""
    wallet = db.query(Wallet).filter(Wallet.id == wallet_id, Wallet.is_archived == False).first()
    if not wallet:
        raise HTTPException(status_code=404, detail="Dompet tidak ditemukan")

    is_owner = wallet.user_id == current_user.id
    is_self = member_user_id == current_user.id

    if not is_owner and not is_self:
        raise HTTPException(status_code=403, detail="Anda tidak memiliki izin untuk menghapus anggota ini")

    member = db.query(WalletMember).filter(
        WalletMember.wallet_id == wallet_id,
        WalletMember.user_id == member_user_id,
    ).first()
    if not member:
        raise HTTPException(status_code=404, detail="Anggota tidak ditemukan pada dompet ini")

    db.delete(member)
    db.commit()
    msg = "Anda berhasil keluar dari dompet bersama" if is_self else "Anggota berhasil dihapus dari dompet"
    return {"message": msg}
