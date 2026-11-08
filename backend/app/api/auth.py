import random
from datetime import datetime, timedelta, timezone
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr
from sqlalchemy.orm import Session

from app.db import User, Wallet, FinancialProfile, get_db
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
