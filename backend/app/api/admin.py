import logging
from datetime import datetime, timedelta, timezone
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, Depends, Query, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import func, or_

from app.db import User, Wallet, Transaction, BotLink, get_db
from app.auth import get_admin_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin", tags=["Admin Management"])


class AdminStatsResponse(BaseModel):
    total_users: int
    verified_users: int
    unverified_users: int
    active_users_30d: int
    total_transactions: int
    total_system_wallets: int
    total_system_balance: float
    bot_connected_users: int


class AdminUserItem(BaseModel):
    id: str
    full_name: str
    email: str
    role: str
    is_verified: bool
    base_currency: str
    created_at: str
    wallet_count: int
    total_balance: float
    transaction_count: int
    has_bot_linked: bool


class AdminUsersResponse(BaseModel):
    total: int
    page: int
    limit: int
    users: List[AdminUserItem]


@router.get("/stats", response_model=AdminStatsResponse)
def get_admin_stats(
    admin_user: User = Depends(get_admin_user),
    db: Session = Depends(get_db),
):
    """Returns platform-wide aggregate statistics for administrator monitoring."""
    total_users = db.query(User).count()
    verified_users = db.query(User).filter(User.is_verified == True).count()
    unverified_users = total_users - verified_users

    # Active users in the last 30 days (users with transactions in past 30 days)
    thirty_days_ago = datetime.now(timezone.utc) - timedelta(days=30)
    active_users_30d = (
        db.query(Transaction.user_id)
        .filter(Transaction.transaction_date >= thirty_days_ago)
        .distinct()
        .count()
    )

    total_transactions = db.query(Transaction).count()
    total_system_wallets = db.query(Wallet).filter(Wallet.is_archived == False).count()
    total_system_balance = (
        db.query(func.coalesce(func.sum(Wallet.balance), 0.0))
        .filter(Wallet.is_archived == False)
        .scalar()
        or 0.0
    )

    bot_connected_users = (
        db.query(BotLink.user_id)
        .filter(BotLink.is_active == True)
        .distinct()
        .count()
    )

    return {
        "total_users": total_users,
        "verified_users": verified_users,
        "unverified_users": unverified_users,
        "active_users_30d": active_users_30d,
        "total_transactions": total_transactions,
        "total_system_wallets": total_system_wallets,
        "total_system_balance": round(total_system_balance, 2),
        "bot_connected_users": bot_connected_users,
    }


@router.get("/users", response_model=AdminUsersResponse)
def get_admin_users(
    search: Optional[str] = Query(None, description="Search by full name or email"),
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    admin_user: User = Depends(get_admin_user),
    db: Session = Depends(get_db),
):
    """Returns paginated list of registered users with wealth, activity, and verification status."""
    query = db.query(User)

    if search:
        search_pattern = f"%{search.strip().lower()}%"
        query = query.filter(
            or_(
                func.lower(User.full_name).ilike(search_pattern),
                func.lower(User.email).ilike(search_pattern),
            )
        )

    total = query.count()
    users = (
        query.order_by(User.created_at.desc())
        .offset((page - 1) * limit)
        .limit(limit)
        .all()
    )

    user_items = []
    for u in users:
        active_wallets = [w for w in u.wallets if not w.is_archived]
        total_balance = sum(w.balance for w in active_wallets)
        tx_count = len(u.transactions)
        has_bot = any(b.is_active for b in u.bot_links)

        user_items.append(
            AdminUserItem(
                id=u.id,
                full_name=u.full_name or "Tanpa Nama",
                email=u.email,
                role=u.role,
                is_verified=u.is_verified,
                base_currency=u.base_currency or "IDR",
                created_at=u.created_at.isoformat(),
                wallet_count=len(active_wallets),
                total_balance=round(total_balance, 2),
                transaction_count=tx_count,
                has_bot_linked=has_bot,
            )
        )

    return {
        "total": total,
        "page": page,
        "limit": limit,
        "users": user_items,
    }
