from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr
from sqlalchemy.orm import Session
from typing import Optional

from app.db import User, Wallet, FinancialProfile, get_db
from app.security import hash_password, verify_password, create_access_token
from app.auth import get_current_user

router = APIRouter(prefix="/auth", tags=["Authentication"])


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str
    full_name: Optional[str] = None
    base_currency: str = "IDR"


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class AuthResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: dict


@router.post("/register", response_model=AuthResponse)
def register(req: RegisterRequest, db: Session = Depends(get_db)):
    email = req.email.lower().strip()
    existing = db.query(User).filter(User.email == email).first()
    if existing:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Email already registered")

    user = User(
        email=email,
        password_hash=hash_password(req.password),
        full_name=req.full_name or email.split("@")[0],
        base_currency=req.base_currency.upper(),
        role="user",
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
        },
    }


@router.post("/login", response_model=AuthResponse)
def login(req: LoginRequest, db: Session = Depends(get_db)):
    email = req.email.lower().strip()
    user = db.query(User).filter(User.email == email).first()
    if not user or not verify_password(req.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password")

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
        },
    }


@router.get("/me")
def get_me(current_user: User = Depends(get_current_user)):
    return {
        "id": current_user.id,
        "email": current_user.email,
        "full_name": current_user.full_name,
        "base_currency": current_user.base_currency,
        "role": current_user.role,
        "created_at": current_user.created_at.isoformat(),
    }

