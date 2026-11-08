import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from fastapi import HTTPException

from app.db import Base, User, Wallet, Transaction, BotLink
from app.services.nlu_parser import parse_transaction_text
from app.api.webhooks import _process_user_transaction_message
from app.api.admin import get_admin_stats, get_admin_users
from app.auth import get_admin_user
from app.security import hash_password


@pytest.fixture()
def db_session():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    TestingSession = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    db = TestingSession()
    try:
        yield db
    finally:
        db.close()


def test_nlu_topup_parses_as_income():
    res = parse_transaction_text("Topup saldo gopay 1jt", user_wallets=["GoPay", "Bank BCA"])
    assert res["type"] == "INCOME"
    assert res["amount"] == 1000000.0
    assert res["wallet_hint"] == "GoPay"

    res2 = parse_transaction_text("isi saldo gopay 100rb", user_wallets=["GoPay", "Bank BCA"])
    assert res2["type"] == "INCOME"
    assert res2["amount"] == 100000.0
    assert res2["wallet_hint"] == "GoPay"


def test_topup_balance_increases_wallet(db_session):
    user = User(
        email="test_topup@test.com",
        password_hash=hash_password("Password123!"),
        full_name="User Topup",
        base_currency="IDR",
        role="user",
        is_verified=True,
    )
    db_session.add(user)
    db_session.flush()

    wallet = Wallet(user_id=user.id, name="GoPay", type="EWALLET", balance=50000.0, is_default=True)
    db_session.add(wallet)
    db_session.commit()

    initial_balance = wallet.balance
    assert initial_balance == 50000.0

    # Process "topup saldo gopay 100rb"
    result = _process_user_transaction_message(
        user=user,
        raw_text="topup saldo gopay 100rb",
        source="TELEGRAM",
        receipt_meta=None,
        db=db_session,
    )

    assert result["success"] is True
    db_session.refresh(wallet)
    # Balance must have INCREASED by 100,000!
    assert wallet.balance == 150000.0
    assert "Top Up / Pemasukan" in result["message"]
    assert "150.000" in result["message"]


def test_admin_api_access_control(db_session):
    admin = User(
        email="admin@test.com",
        password_hash=hash_password("AdminPass123!"),
        full_name="Super Admin",
        role="admin",
        is_verified=True,
    )
    regular_user = User(
        email="regular@test.com",
        password_hash=hash_password("UserPass123!"),
        full_name="Regular User",
        role="user",
        is_verified=True,
    )
    db_session.add_all([admin, regular_user])
    db_session.commit()

    # Regular user must be forbidden
    with pytest.raises(HTTPException) as exc:
        get_admin_user(current_user=regular_user)
    assert exc.value.status_code == 403

    # Admin user is permitted
    allowed_admin = get_admin_user(current_user=admin)
    assert allowed_admin.id == admin.id

    # Test admin stats
    stats = get_admin_stats(admin_user=admin, db=db_session)
    assert stats["total_users"] == 2
    assert stats["verified_users"] == 2

    # Test admin users list
    user_list = get_admin_users(admin_user=admin, db=db_session)
    assert user_list["total"] == 2
    assert len(user_list["users"]) == 2

