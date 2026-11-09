import json
import random
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr
from sqlalchemy import desc
from sqlalchemy.orm import Session

from app.db import (
    AccountBackup,
    Budget,
    BudgetGroup,
    Category,
    CFPChatMessage,
    FinancialProfile,
    Transaction,
    User,
    Wallet,
    WalletMember,
    get_db,
)
from app.security import hash_password, verify_password, create_access_token
from app.auth import get_current_user
from app.services.email_service import send_verification_email

router = APIRouter(prefix="/auth", tags=["Authentication"])


class RegisterRequest(BaseModel):
    full_name: str
    email: EmailStr
    password: str
    base_currency: str = "IDR"


class RegisterResponse(BaseModel):
    status: str = "verification_required"
    email: str
    full_name: str
    message: str
    is_verified: bool = False


class VerifyEmailRequest(BaseModel):
    email: EmailStr
    code: str


class ResendVerificationRequest(BaseModel):
    email: EmailStr


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class AuthResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: dict


class ProfileResponse(BaseModel):
    id: str
    email: str
    full_name: str
    base_currency: str
    role: str
    is_verified: bool
    created_at: str


class UpdateProfileRequest(BaseModel):
    full_name: str
    email: EmailStr
    base_currency: Optional[str] = "IDR"


class ChangePasswordRequest(BaseModel):
    old_password: str
    new_password: str


@router.post("/register", response_model=RegisterResponse)
async def register(req: RegisterRequest, db: Session = Depends(get_db)):
    full_name = req.full_name.strip()
    if len(full_name) < 2:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Nama lengkap wajib diisi minimal 2 karakter.",
        )

    email = req.email.lower().strip()
    existing = db.query(User).filter(User.email == email).first()
    if existing:
        if existing.is_verified:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email sudah terdaftar. Silakan login ke akun Anda.",
            )
        else:
            # User previously registered but not verified yet. Refresh verification OTP code.
            otp_code = f"{random.randint(100000, 999999)}"
            existing.full_name = full_name
            existing.password_hash = hash_password(req.password)
            existing.verification_code = otp_code
            existing.verification_expires_at = datetime.now(timezone.utc) + timedelta(minutes=15)
            db.commit()
            await send_verification_email(email, full_name, otp_code)
            return {
                "status": "verification_required",
                "email": email,
                "full_name": full_name,
                "message": "Kode verifikasi telah dikirim ulang ke email Anda. Silakan cek inbox/spam.",
                "is_verified": False,
            }

    otp_code = f"{random.randint(100000, 999999)}"
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=15)

    user = User(
        email=email,
        password_hash=hash_password(req.password),
        full_name=full_name,
        base_currency=req.base_currency.upper(),
        role="user",
        is_verified=False,
        verification_code=otp_code,
        verification_expires_at=expires_at,
    )
    db.add(user)
    db.flush()

    # Automatically provision starter wallets
    db.add(Wallet(user_id=user.id, name="Cash Dompet", type="CASH", balance=0.0, color="#10b981", is_default=True))
    db.add(Wallet(user_id=user.id, name="Bank Utama", type="BANK", balance=0.0, color="#3b82f6", is_default=False))
    db.add(Wallet(user_id=user.id, name="E-Wallet", type="EWALLET", balance=0.0, color="#06b6d4", is_default=False))

    # Provision starter financial profile
    db.add(FinancialProfile(user_id=user.id))

    db.commit()

    # Send verification email via Resend API
    await send_verification_email(email, full_name, otp_code)

    return {
        "status": "verification_required",
        "email": email,
        "full_name": full_name,
        "message": "Pendaftaran berhasil! Kode verifikasi 6-digit telah dikirim ke email Anda.",
        "is_verified": False,
    }


@router.post("/verify-email", response_model=AuthResponse)
def verify_email(req: VerifyEmailRequest, db: Session = Depends(get_db)):
    email = req.email.lower().strip()
    user = db.query(User).filter(User.email == email).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Pengguna tidak ditemukan.")

    if user.is_verified:
        token = create_access_token({"sub": user.id, "email": user.email, "role": user.role})
        return {
            "access_token": token,
            "token_type": "bearer",
            "user": {
                "id": user.id,
                "email": user.email,
                "full_name": user.full_name,
                "base_currency": user.base_currency,
                "role": user.role,
                "is_verified": True,
            },
        }

    input_code = req.code.strip()
    if not user.verification_code or user.verification_code != input_code:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Kode verifikasi salah. Silakan periksa kembali email Anda.",
        )

    if user.verification_expires_at:
        now_utc = datetime.now(timezone.utc)
        expires_at = (
            user.verification_expires_at.replace(tzinfo=timezone.utc)
            if user.verification_expires_at.tzinfo is None
            else user.verification_expires_at
        )
        if expires_at < now_utc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Kode verifikasi telah kedaluwarsa. Silakan klik 'Kirim Ulang Kode'.",
            )

    user.is_verified = True
    user.verification_code = None
    user.verification_expires_at = None
    db.commit()
    db.refresh(user)

    token = create_access_token({"sub": user.id, "email": user.email, "role": user.role})
    return {
        "access_token": token,
        "token_type": "bearer",
        "user": {
            "id": user.id,
            "email": user.email,
            "full_name": user.full_name,
            "base_currency": user.base_currency,
            "role": user.role,
            "is_verified": True,
        },
    }


@router.post("/resend-verification")
async def resend_verification(req: ResendVerificationRequest, db: Session = Depends(get_db)):
    email = req.email.lower().strip()
    user = db.query(User).filter(User.email == email).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Pengguna tidak ditemukan.")

    if user.is_verified:
        return {"ok": True, "message": "Email akun ini sudah terverifikasi. Silakan login."}

    otp_code = f"{random.randint(100000, 999999)}"
    user.verification_code = otp_code
    user.verification_expires_at = datetime.now(timezone.utc) + timedelta(minutes=15)
    db.commit()

    await send_verification_email(email, user.full_name or email, otp_code)
    return {"ok": True, "message": "Kode verifikasi baru berhasil dikirim ke email Anda."}


@router.post("/login", response_model=AuthResponse)
def login(req: LoginRequest, db: Session = Depends(get_db)):
    email = req.email.lower().strip()
    user = db.query(User).filter(User.email == email).first()
    if not user or not verify_password(req.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Email atau kata sandi tidak valid.",
        )

    if not user.is_verified:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Email belum diverifikasi. Silakan masukkan kode verifikasi Anda.",
        )

    token = create_access_token({"sub": user.id, "email": user.email, "role": user.role})
    return {
        "access_token": token,
        "token_type": "bearer",
        "user": {
            "id": user.id,
            "email": user.email,
            "full_name": user.full_name,
            "base_currency": user.base_currency,
            "role": user.role,
            "is_verified": user.is_verified,
        },
    }


@router.get("/profile", response_model=ProfileResponse)
def get_profile(current_user: User = Depends(get_current_user)):
    return {
        "id": current_user.id,
        "email": current_user.email,
        "full_name": current_user.full_name or "",
        "base_currency": current_user.base_currency,
        "role": current_user.role,
        "is_verified": current_user.is_verified,
        "created_at": current_user.created_at.isoformat(),
    }


@router.put("/profile", response_model=ProfileResponse)
def update_profile(
    req: UpdateProfileRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    full_name = req.full_name.strip()
    if len(full_name) < 2:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Nama lengkap wajib diisi minimal 2 karakter.",
        )

    new_email = req.email.lower().strip()
    if new_email != current_user.email:
        existing = db.query(User).filter(User.email == new_email).first()
        if existing and existing.id != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Alamat email sudah digunakan oleh akun lain.",
            )
        current_user.email = new_email

    current_user.full_name = full_name
    if req.base_currency:
        current_user.base_currency = req.base_currency.upper().strip()

    db.commit()
    db.refresh(current_user)

    return {
        "id": current_user.id,
        "email": current_user.email,
        "full_name": current_user.full_name,
        "base_currency": current_user.base_currency,
        "role": current_user.role,
        "is_verified": current_user.is_verified,
        "created_at": current_user.created_at.isoformat(),
    }


@router.put("/change-password")
def change_password(
    req: ChangePasswordRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if not verify_password(req.old_password, current_user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Kata sandi saat ini tidak sesuai.",
        )

    if len(req.new_password) < 6:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Kata sandi baru minimal 6 karakter.",
        )

    current_user.password_hash = hash_password(req.new_password)
    db.commit()

    return {"ok": True, "message": "Kata sandi berhasil diperbarui."}


@router.get("/me")
def get_me(current_user: User = Depends(get_current_user)):
    return {
        "id": current_user.id,
        "email": current_user.email,
        "full_name": current_user.full_name,
        "base_currency": current_user.base_currency,
        "role": current_user.role,
        "is_verified": current_user.is_verified,
        "created_at": current_user.created_at.isoformat(),
    }


# ==================== BACKUP, RESET & RESTORE DATA ====================


class CreateBackupRequest(BaseModel):
    title: Optional[str] = "Backup Manual"


class ResetAccountDataRequest(BaseModel):
    password: str
    mode: str = "ZERO_WALLETS"  # "ZERO_WALLETS" | "FULL_ACCOUNT_RESET"
    wallet_ids: Optional[List[str]] = None
    clear_transactions: bool = False


class RestoreAccountDataRequest(BaseModel):
    password: str
    backup_id: Optional[str] = None
    backup_payload: Optional[Dict[str, Any]] = None


def _parse_iso_dt(val: Optional[str]) -> datetime:
    if not val:
        return datetime.now(timezone.utc)
    try:
        return datetime.fromisoformat(val.replace("Z", "+00:00"))
    except Exception:
        return datetime.now(timezone.utc)


def _build_backup_payload(user: User, db: Session) -> Dict[str, Any]:
    wallets = db.query(Wallet).filter(Wallet.user_id == user.id).all()
    wallet_ids = [w.id for w in wallets]
    members = (
        db.query(WalletMember).filter(WalletMember.wallet_id.in_(wallet_ids)).all()
        if wallet_ids
        else []
    )
    categories = db.query(Category).filter(Category.user_id == user.id, Category.is_system == False).all()
    budget_groups = db.query(BudgetGroup).filter(BudgetGroup.user_id == user.id).all()
    budgets = db.query(Budget).filter(Budget.user_id == user.id).all()
    transactions = db.query(Transaction).filter(Transaction.user_id == user.id).all()
    profile = db.query(FinancialProfile).filter(FinancialProfile.user_id == user.id).first()

    return {
        "schema_version": "1.0",
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "user": {
            "id": user.id,
            "email": user.email,
            "full_name": user.full_name,
            "base_currency": user.base_currency,
        },
        "wallets": [
            {
                "id": w.id,
                "name": w.name,
                "type": w.type,
                "asset_class": getattr(w, "asset_class", None),
                "balance": w.balance,
                "currency": w.currency,
                "color": w.color,
                "is_default": w.is_default,
                "is_archived": w.is_archived,
                "created_at": w.created_at.isoformat() if w.created_at else None,
            }
            for w in wallets
        ],
        "wallet_members": [
            {
                "id": m.id,
                "wallet_id": m.wallet_id,
                "user_id": m.user_id,
                "role": m.role,
                "invited_by_id": m.invited_by_id,
                "created_at": m.created_at.isoformat() if m.created_at else None,
            }
            for m in members
        ],
        "categories": [
            {
                "id": c.id,
                "name": c.name,
                "icon": c.icon,
                "color": c.color,
                "type": c.type,
                "is_system": False,
                "created_at": c.created_at.isoformat() if c.created_at else None,
            }
            for c in categories
        ],
        "budget_groups": [
            {
                "id": bg.id,
                "name": bg.name,
                "is_sinking_fund": bg.is_sinking_fund,
                "sort_order": bg.sort_order,
                "created_at": bg.created_at.isoformat() if bg.created_at else None,
            }
            for bg in budget_groups
        ],
        "budgets": [
            {
                "id": b.id,
                "category_id": b.category_id,
                "wallet_id": b.wallet_id,
                "name": b.name,
                "group_type": b.group_type,
                "remark": b.remark,
                "limit_amount": b.limit_amount,
                "period": b.period,
                "month_key": b.month_key,
                "is_sinking_fund": b.is_sinking_fund,
                "rollover_balance": b.rollover_balance,
                "funded_this_month": b.funded_this_month,
                "sort_order": b.sort_order,
                "created_at": b.created_at.isoformat() if b.created_at else None,
            }
            for b in budgets
        ],
        "transactions": [
            {
                "id": t.id,
                "wallet_id": t.wallet_id,
                "category_id": t.category_id,
                "budget_id": t.budget_id,
                "to_wallet_id": t.to_wallet_id,
                "type": t.type,
                "amount": t.amount,
                "currency": t.currency,
                "amount_in_base": t.amount_in_base,
                "description": t.description,
                "merchant": t.merchant,
                "raw_input": t.raw_input,
                "raw_source": t.raw_source,
                "receipt_metadata": t.receipt_metadata,
                "transaction_date": t.transaction_date.isoformat() if t.transaction_date else None,
                "created_at": t.created_at.isoformat() if t.created_at else None,
            }
            for t in transactions
        ],
        "financial_profile": (
            {
                "current_age": profile.current_age,
                "target_fire_age": profile.target_fire_age,
                "monthly_income": profile.monthly_income,
                "monthly_living_expense": profile.monthly_living_expense,
                "monthly_debt_payment": profile.monthly_debt_payment,
                "marital_status": profile.marital_status,
                "dependents_count": profile.dependents_count,
                "risk_tolerance": profile.risk_tolerance,
                "sharia_preference": profile.sharia_preference,
                "memory_notes": profile.memory_notes,
                "confirmed_profile_fields": profile.confirmed_profile_fields,
                "fire_target_amount": profile.fire_target_amount,
                "emergency_fund_target": profile.emergency_fund_target,
            }
            if profile
            else None
        ),
    }


def _create_account_snapshot(
    user: User,
    db: Session,
    title: str = "Backup Manual",
    backup_type: str = "MANUAL",
) -> AccountBackup:
    payload = _build_backup_payload(user, db)
    active_wallets = [w for w in payload["wallets"] if not w.get("is_archived")]
    total_bal = sum(float(w.get("balance", 0.0)) for w in active_wallets)

    summary = {
        "wallets_count": len(active_wallets),
        "total_balance": round(total_bal, 2),
        "transactions_count": len(payload["transactions"]),
        "budgets_count": len(payload["budgets"]),
    }

    backup = AccountBackup(
        user_id=user.id,
        title=title.strip()[:160] if title else "Backup Data",
        backup_type=backup_type,
        summary_json=json.dumps(summary),
        payload_json=json.dumps(payload),
    )
    db.add(backup)
    db.flush()

    # Keep at most 15 snapshots per user
    all_backups = (
        db.query(AccountBackup)
        .filter(AccountBackup.user_id == user.id)
        .order_by(desc(AccountBackup.created_at))
        .all()
    )
    if len(all_backups) > 15:
        for old_b in all_backups[15:]:
            db.delete(old_b)

    return backup


@router.get("/backups")
def list_account_backups(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    backups = (
        db.query(AccountBackup)
        .filter(AccountBackup.user_id == current_user.id)
        .order_by(desc(AccountBackup.created_at))
        .all()
    )
    items = []
    for b in backups:
        try:
            summary = json.loads(b.summary_json or "{}")
        except Exception:
            summary = {}
        items.append({
            "id": b.id,
            "title": b.title,
            "backup_type": b.backup_type,
            "summary": summary,
            "created_at": b.created_at.isoformat() if b.created_at else "",
        })
    return {"items": items}


@router.post("/backups")
def create_account_backup(
    req: CreateBackupRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    backup = _create_account_snapshot(
        user=current_user,
        db=db,
        title=req.title or "Backup Manual",
        backup_type="MANUAL",
    )
    db.commit()
    db.refresh(backup)
    summary = json.loads(backup.summary_json or "{}")
    payload = json.loads(backup.payload_json)
    return {
        "id": backup.id,
        "title": backup.title,
        "backup_type": backup.backup_type,
        "summary": summary,
        "created_at": backup.created_at.isoformat(),
        "backup_payload": payload,
    }


@router.get("/backups/{backup_id}/export")
def export_account_backup(
    backup_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    backup = (
        db.query(AccountBackup)
        .filter(AccountBackup.id == backup_id, AccountBackup.user_id == current_user.id)
        .first()
    )
    if not backup:
        raise HTTPException(status_code=404, detail="Data backup tidak ditemukan.")
    return json.loads(backup.payload_json)


@router.delete("/backups/{backup_id}")
def delete_account_backup(
    backup_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    backup = (
        db.query(AccountBackup)
        .filter(AccountBackup.id == backup_id, AccountBackup.user_id == current_user.id)
        .first()
    )
    if not backup:
        raise HTTPException(status_code=404, detail="Data backup tidak ditemukan.")
    db.delete(backup)
    db.commit()
    return {"ok": True, "message": "Snapshot backup berhasil dihapus."}


@router.post("/reset-data")
def reset_account_data(
    req: ResetAccountDataRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Resets wallet balances or performs full financial data reset after verifying user's password.
    Automatically creates an AUTO_PRE_RESET backup snapshot beforehand.
    """
    if not req.password or not verify_password(req.password, current_user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Kata sandi akun tidak sesuai. Proses reset dibatalkan.",
        )

    mode = (req.mode or "ZERO_WALLETS").strip().upper()
    if mode not in ("ZERO_WALLETS", "FULL_ACCOUNT_RESET"):
        raise HTTPException(status_code=400, detail="Mode reset tidak valid.")

    auto_title = (
        "Auto-Backup Sebelum Factory Reset"
        if mode == "FULL_ACCOUNT_RESET"
        else "Auto-Backup Sebelum Reset Saldo Dompet"
    )
    auto_backup = _create_account_snapshot(
        user=current_user,
        db=db,
        title=auto_title,
        backup_type="AUTO_PRE_RESET",
    )

    if mode == "ZERO_WALLETS":
        query = db.query(Wallet).filter(Wallet.user_id == current_user.id, Wallet.is_archived == False)
        if req.wallet_ids:
            query = query.filter(Wallet.id.in_(req.wallet_ids))
        target_wallets = query.all()
        target_ids = [w.id for w in target_wallets]

        for w in target_wallets:
            w.balance = 0.0

        deleted_tx_count = 0
        if req.clear_transactions and target_ids:
            deleted_tx_count = (
                db.query(Transaction)
                .filter(Transaction.user_id == current_user.id, Transaction.wallet_id.in_(target_ids))
                .delete(synchronize_session=False)
            )
            budgets = db.query(Budget).filter(Budget.user_id == current_user.id, Budget.wallet_id.in_(target_ids)).all()
            for b in budgets:
                b.funded_this_month = 0.0
                b.rollover_balance = 0.0

        db.commit()
        return {
            "ok": True,
            "mode": mode,
            "reset_wallets_count": len(target_wallets),
            "deleted_transactions_count": deleted_tx_count,
            "auto_backup_id": auto_backup.id,
            "message": f"Berhasil mereset saldo {len(target_wallets)} dompet menjadi Rp 0. Snapshot backup otomatis telah disimpan.",
        }

    # FULL_ACCOUNT_RESET: Wipe transactions, budgets, custom categories, AI chats, and reset wallets to starter
    db.query(Transaction).filter(Transaction.user_id == current_user.id).delete(synchronize_session=False)
    db.query(Budget).filter(Budget.user_id == current_user.id).delete(synchronize_session=False)
    db.query(BudgetGroup).filter(BudgetGroup.user_id == current_user.id).delete(synchronize_session=False)
    db.query(Category).filter(Category.user_id == current_user.id, Category.is_system == False).delete(synchronize_session=False)
    db.query(CFPChatMessage).filter(CFPChatMessage.user_id == current_user.id).delete(synchronize_session=False)

    user_wallets = db.query(Wallet).filter(Wallet.user_id == current_user.id).all()
    for uw in user_wallets:
        db.delete(uw)
    db.flush()

    # Re-provision clean starter wallets
    db.add(Wallet(user_id=current_user.id, name="Cash Dompet", type="CASH", balance=0.0, color="#10b981", is_default=True))
    db.add(Wallet(user_id=current_user.id, name="Bank Utama", type="BANK", balance=0.0, color="#3b82f6", is_default=False))
    db.add(Wallet(user_id=current_user.id, name="E-Wallet", type="EWALLET", balance=0.0, color="#06b6d4", is_default=False))

    profile = db.query(FinancialProfile).filter(FinancialProfile.user_id == current_user.id).first()
    if profile:
        profile.monthly_income = 0.0
        profile.monthly_living_expense = 10000000.0
        profile.monthly_debt_payment = 0.0
        profile.memory_notes = ""
        profile.confirmed_profile_fields = "[]"

    db.commit()
    return {
        "ok": True,
        "mode": mode,
        "auto_backup_id": auto_backup.id,
        "message": "Seluruh data finansial berhasil di-reset ke pengaturan awal (Rp 0). Snapshot backup otomatis telah disimpan.",
    }


@router.post("/restore-data")
def restore_account_data(
    req: RestoreAccountDataRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Restores wallets, balances, categories, budgets, transactions, and financial profile
    from either a saved AccountBackup ID or an uploaded JSON payload after verifying password.
    """
    if not req.password or not verify_password(req.password, current_user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Kata sandi akun tidak sesuai. Proses restore dibatalkan.",
        )

    payload: Optional[Dict[str, Any]] = None
    if req.backup_id:
        backup = (
            db.query(AccountBackup)
            .filter(AccountBackup.id == req.backup_id, AccountBackup.user_id == current_user.id)
            .first()
        )
        if not backup:
            raise HTTPException(status_code=404, detail="Snapshot backup tidak ditemukan.")
        payload = json.loads(backup.payload_json)
    elif req.backup_payload:
        payload = req.backup_payload

    if not payload or "wallets" not in payload:
        raise HTTPException(status_code=400, detail="Format data backup tidak valid atau kosong.")

    # Clear current user financial records before restoring snapshot
    db.query(Transaction).filter(Transaction.user_id == current_user.id).delete(synchronize_session=False)
    db.query(Budget).filter(Budget.user_id == current_user.id).delete(synchronize_session=False)
    db.query(BudgetGroup).filter(BudgetGroup.user_id == current_user.id).delete(synchronize_session=False)
    db.query(Category).filter(Category.user_id == current_user.id, Category.is_system == False).delete(synchronize_session=False)

    existing_wallets = db.query(Wallet).filter(Wallet.user_id == current_user.id).all()
    for ew in existing_wallets:
        db.delete(ew)
    db.flush()

    # 1. Restore custom categories
    system_cat_ids = {c.id for c in db.query(Category).filter(Category.is_system == True).all()}
    restored_cat_ids = set(system_cat_ids)
    for c_data in payload.get("categories", []):
        cid = c_data.get("id")
        if not cid or cid in restored_cat_ids:
            continue
        db.add(
            Category(
                id=cid,
                user_id=current_user.id,
                name=c_data.get("name", "Kategori"),
                icon=c_data.get("icon", "tag"),
                color=c_data.get("color", "#64748b"),
                type=c_data.get("type", "EXPENSE"),
                is_system=False,
                created_at=_parse_iso_dt(c_data.get("created_at")),
            )
        )
        restored_cat_ids.add(cid)
    db.flush()

    # 2. Restore wallets
    restored_wallet_ids = set()
    for w_data in payload.get("wallets", []):
        wid = w_data.get("id")
        if not wid:
            continue
        db.add(
            Wallet(
                id=wid,
                user_id=current_user.id,
                name=w_data.get("name", "Dompet"),
                type=w_data.get("type", "BANK"),
                asset_class=w_data.get("asset_class"),
                balance=float(w_data.get("balance", 0.0)),
                currency=w_data.get("currency", "IDR"),
                color=w_data.get("color", "#f0b000"),
                is_default=bool(w_data.get("is_default", False)),
                is_archived=bool(w_data.get("is_archived", False)),
                created_at=_parse_iso_dt(w_data.get("created_at")),
            )
        )
        restored_wallet_ids.add(wid)
    db.flush()

    # 3. Restore wallet members (only if member user still exists)
    for m_data in payload.get("wallet_members", []):
        wid = m_data.get("wallet_id")
        uid = m_data.get("user_id")
        if wid in restored_wallet_ids and uid:
            u_exists = db.query(User.id).filter(User.id == uid).first()
            if u_exists:
                db.add(
                    WalletMember(
                        id=m_data.get("id"),
                        wallet_id=wid,
                        user_id=uid,
                        role=m_data.get("role", "EDITOR"),
                        invited_by_id=current_user.id,
                        created_at=_parse_iso_dt(m_data.get("created_at")),
                    )
                )
    db.flush()

    # 4. Restore budget groups
    for bg_data in payload.get("budget_groups", []):
        db.add(
            BudgetGroup(
                id=bg_data.get("id"),
                user_id=current_user.id,
                name=bg_data.get("name", "NEED"),
                is_sinking_fund=bool(bg_data.get("is_sinking_fund", False)),
                sort_order=int(bg_data.get("sort_order", 0)),
                created_at=_parse_iso_dt(bg_data.get("created_at")),
            )
        )
    db.flush()

    # 5. Restore budgets
    restored_budget_ids = set()
    for b_data in payload.get("budgets", []):
        bid = b_data.get("id")
        if not bid:
            continue
        cid = b_data.get("category_id")
        wid = b_data.get("wallet_id")
        db.add(
            Budget(
                id=bid,
                user_id=current_user.id,
                category_id=cid if cid in restored_cat_ids else None,
                wallet_id=wid if wid in restored_wallet_ids else None,
                name=b_data.get("name"),
                group_type=b_data.get("group_type", "LIVING NEEDS"),
                remark=b_data.get("remark"),
                limit_amount=float(b_data.get("limit_amount", 0.0)),
                period=b_data.get("period", "MONTHLY"),
                month_key=b_data.get("month_key"),
                is_sinking_fund=bool(b_data.get("is_sinking_fund", False)),
                rollover_balance=float(b_data.get("rollover_balance", 0.0)),
                funded_this_month=float(b_data.get("funded_this_month", 0.0)),
                sort_order=int(b_data.get("sort_order", 0)),
                created_at=_parse_iso_dt(b_data.get("created_at")),
            )
        )
        restored_budget_ids.add(bid)
    db.flush()

    # 6. Restore transactions
    restored_tx_count = 0
    for t_data in payload.get("transactions", []):
        wid = t_data.get("wallet_id")
        if wid not in restored_wallet_ids:
            continue
        cid = t_data.get("category_id")
        bid = t_data.get("budget_id")
        to_wid = t_data.get("to_wallet_id")
        db.add(
            Transaction(
                id=t_data.get("id"),
                user_id=current_user.id,
                wallet_id=wid,
                category_id=cid if cid in restored_cat_ids else None,
                budget_id=bid if bid in restored_budget_ids else None,
                to_wallet_id=to_wid if to_wid in restored_wallet_ids else None,
                type=t_data.get("type", "EXPENSE"),
                amount=float(t_data.get("amount", 0.0)),
                currency=t_data.get("currency", "IDR"),
                amount_in_base=float(t_data.get("amount_in_base", t_data.get("amount", 0.0))),
                description=t_data.get("description", "Transaksi"),
                merchant=t_data.get("merchant"),
                raw_input=t_data.get("raw_input"),
                raw_source=t_data.get("raw_source", "WEB"),
                receipt_metadata=t_data.get("receipt_metadata"),
                transaction_date=_parse_iso_dt(t_data.get("transaction_date")),
                created_at=_parse_iso_dt(t_data.get("created_at")),
            )
        )
        restored_tx_count += 1

    # 7. Restore financial profile
    fp_data = payload.get("financial_profile")
    if fp_data and isinstance(fp_data, dict):
        profile = db.query(FinancialProfile).filter(FinancialProfile.user_id == current_user.id).first()
        if not profile:
            profile = FinancialProfile(user_id=current_user.id)
            db.add(profile)
        profile.current_age = int(fp_data.get("current_age", 28))
        profile.target_fire_age = int(fp_data.get("target_fire_age", 50))
        profile.monthly_income = float(fp_data.get("monthly_income", 0.0))
        profile.monthly_living_expense = float(fp_data.get("monthly_living_expense", 10000000.0))
        profile.monthly_debt_payment = float(fp_data.get("monthly_debt_payment", 0.0))
        profile.marital_status = fp_data.get("marital_status", "SINGLE")
        profile.dependents_count = int(fp_data.get("dependents_count", 0))
        profile.risk_tolerance = fp_data.get("risk_tolerance", "MODERATE")
        profile.sharia_preference = bool(fp_data.get("sharia_preference", False))
        profile.memory_notes = fp_data.get("memory_notes", "")
        profile.confirmed_profile_fields = fp_data.get("confirmed_profile_fields", "[]")

    db.commit()
    return {
        "ok": True,
        "restored_wallets_count": len(restored_wallet_ids),
        "restored_transactions_count": restored_tx_count,
        "restored_budgets_count": len(restored_budget_ids),
        "message": (
            f"Berhasil memulihkan {len(restored_wallet_ids)} dompet, "
            f"{len(restored_budget_ids)} pos anggaran, dan {restored_tx_count} transaksi."
        ),
    }
