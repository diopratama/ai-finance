import json
from datetime import datetime, timezone
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import (
    Base,
    Budget,
    Category,
    FinancialProfile,
    Transaction,
    User,
    Wallet,
)
from app.security import hash_password
from app.services.fire_engine import (
    evaluate_investment_portfolio,
    infer_wallet_asset_class,
    is_investment_wallet,
)
from app.services.nlu_parser import parse_transaction_text
from app.api.transactions import get_transaction_summary
from app.api.webhooks import _process_user_transaction_message
from app.api.auth import (
    CreateBackupRequest,
    ResetAccountDataRequest,
    RestoreAccountDataRequest,
    create_account_backup,
    list_account_backups,
    reset_account_data,
    restore_account_data,
)


def _create_test_db():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    return SessionLocal()


def test_investment_portfolio_inference_and_evaluation():
    assert is_investment_wallet("Bibit Reksadana Saham", "INVESTMENT") is True
    assert infer_wallet_asset_class("Bibit Saham", "INVESTMENT") == "EQUITY"
    assert infer_wallet_asset_class("SBN Ritel ORI025", "INVESTMENT") == "BOND"
    assert infer_wallet_asset_class("Tabungan Emas Pegadaian", "INVESTMENT") == "GOLD"
    assert infer_wallet_asset_class("RDPU Pasar Uang", "INVESTMENT") == "MONEY_MARKET"
    assert infer_wallet_asset_class("Pluang Bitcoin", "INVESTMENT") == "CRYPTO"
    assert infer_wallet_asset_class("Kantong Utama", "BANK", "GOLD") == "GOLD"

    wallets = [
        {"id": "w1", "name": "Bibit Saham", "type": "INVESTMENT", "balance": 35_000_000.0, "asset_class": "EQUITY"},
        {"id": "w2", "name": "SBN ORI", "type": "INVESTMENT", "balance": 5_000_000.0, "asset_class": "BOND"},
        {"id": "w3", "name": "Antam Emas", "type": "INVESTMENT", "balance": 10_000_000.0, "asset_class": "GOLD"},
    ]
    rev = evaluate_investment_portfolio(
        wallets=wallets,
        risk_tolerance="MODERATE",
        sharia_preference=False,
        liquid_cash_balance=30_000_000.0,
        monthly_expenses=8_000_000.0,
        is_married=False,
        dependents_count=0,
    )
    assert rev["has_investment_wallets"] is True
    assert rev["investment_wallets_count"] == 3
    assert rev["total_investment_balance"] == 50_000_000.0
    assert rev["alignment_score"] > 0
    assert len(rev["allocations_comparison"]) >= 4
    assert len(rev["best_practices"]) >= 3
    assert len(rev["recommendations"]) >= 1


def test_monthly_transaction_reporting_summary():
    db = _create_test_db()
    user = User(
        email="report@test.com",
        password_hash=hash_password("secret123"),
        full_name="Report Tester",
        is_verified=True,
    )
    db.add(user)
    db.flush()

    w_bca = Wallet(user_id=user.id, name="BCA", type="BANK", balance=12_000_000.0, is_default=True)
    w_gopay = Wallet(user_id=user.id, name="GoPay", type="EWALLET", balance=500_000.0)
    cat_inc = Category(name="Gaji & Pendapatan", type="INCOME", is_system=True, color="#10b981")
    cat_food = Category(name="Makanan & Minuman", type="EXPENSE", is_system=True, color="#f97316")
    db.add_all([w_bca, w_gopay, cat_inc, cat_food])
    db.flush()

    # Previous month transaction (2026-10)
    db.add(
        Transaction(
            user_id=user.id,
            wallet_id=w_bca.id,
            category_id=cat_inc.id,
            type="INCOME",
            amount=10_000_000.0,
            amount_in_base=10_000_000.0,
            description="Gaji Oktober",
            transaction_date=datetime(2026, 10, 25, tzinfo=timezone.utc),
        )
    )
    db.add(
        Transaction(
            user_id=user.id,
            wallet_id=w_bca.id,
            category_id=cat_food.id,
            type="EXPENSE",
            amount=4_000_000.0,
            amount_in_base=4_000_000.0,
            description="Belanja Oktober",
            transaction_date=datetime(2026, 10, 26, tzinfo=timezone.utc),
        )
    )

    # Selected month transactions (2026-11)
    db.add(
        Transaction(
            user_id=user.id,
            wallet_id=w_bca.id,
            category_id=cat_inc.id,
            type="INCOME",
            amount=15_000_000.0,
            amount_in_base=15_000_000.0,
            description="Gaji November",
            transaction_date=datetime(2026, 11, 5, tzinfo=timezone.utc),
        )
    )
    db.add(
        Transaction(
            user_id=user.id,
            wallet_id=w_gopay.id,
            category_id=cat_food.id,
            type="EXPENSE",
            amount=3_000_000.0,
            amount_in_base=3_000_000.0,
            description="Kuliner November",
            transaction_date=datetime(2026, 11, 8, tzinfo=timezone.utc),
        )
    )
    db.commit()

    summary = get_transaction_summary(month="2026-11", current_user=user, db=db)
    m = summary["monthly"]
    assert m["month_key"] == "2026-11"
    assert m["income"] == 15_000_000.0
    assert m["expense"] == 3_000_000.0
    assert m["net_cashflow"] == 12_000_000.0
    assert m["savings_rate"] == 80.0
    assert m["prev_income"] == 10_000_000.0
    assert m["income_mom_pct"] == 50.0
    assert m["expense_mom_pct"] == -25.0
    assert len(summary["monthly_trend"]) == 6
    assert len(summary["expense_categories"]) == 1
    assert summary["expense_categories"][0]["name"] == "Makanan & Minuman"
    assert len(summary["wallet_breakdown"]) == 2


def test_bot_all_wallets_add_subtract_transfer_and_commands():
    db = _create_test_db()
    user = User(
        email="botuser@test.com",
        password_hash=hash_password("secret123"),
        full_name="Bot Tester",
        is_verified=True,
    )
    db.add(user)
    db.flush()

    w_bca = Wallet(user_id=user.id, name="BCA Utama", type="BANK", balance=10_000_000.0, is_default=True)
    w_bibit = Wallet(user_id=user.id, name="Bibit Saham", type="INVESTMENT", asset_class="EQUITY", balance=5_000_000.0)
    w_emas = Wallet(user_id=user.id, name="Tabungan Emas", type="INVESTMENT", asset_class="GOLD", balance=2_000_000.0)
    db.add_all([w_bca, w_bibit, w_emas])
    db.commit()

    # 1. Add funds to investment wallet
    r1 = _process_user_transaction_message(user, "tambah saldo Bibit Saham 1.5jt", "TELEGRAM", None, db)
    assert r1["success"] is True
    db.refresh(w_bibit)
    assert w_bibit.balance == 6_500_000.0

    # 2. Subtract funds from bank wallet
    r2 = _process_user_transaction_message(user, "kurangi saldo BCA Utama 500rb", "TELEGRAM", None, db)
    assert r2["success"] is True
    db.refresh(w_bca)
    assert w_bca.balance == 9_500_000.0

    # 3. Transfer without "dari" ("transfer BCA Utama ke Tabungan Emas 1jt")
    r3 = _process_user_transaction_message(user, "transfer BCA Utama ke Tabungan Emas 1jt", "TELEGRAM", None, db)
    assert r3["success"] is True
    db.refresh(w_bca)
    db.refresh(w_emas)
    assert w_bca.balance == 8_500_000.0
    assert w_emas.balance == 3_000_000.0

    # 4. Command /laporan and /portofolio
    r_lap = _process_user_transaction_message(user, "/laporan", "TELEGRAM", None, db)
    assert r_lap["success"] is True
    assert "Laporan Bulanan" in r_lap["message"]

    r_port = _process_user_transaction_message(user, "/portofolio", "TELEGRAM", None, db)
    assert r_port["success"] is True
    assert "Review Portofolio Investasi" in r_port["message"]


def test_account_backup_reset_and_restore_with_password():
    db = _create_test_db()
    user = User(
        email="backup@test.com",
        password_hash=hash_password("MyStrongPass99"),
        full_name="Backup Tester",
        is_verified=True,
    )
    db.add(user)
    db.flush()

    w1 = Wallet(user_id=user.id, name="Mandiri Payroll", type="BANK", balance=25_000_000.0, is_default=True)
    w2 = Wallet(user_id=user.id, name="SBN Ritel", type="INVESTMENT", asset_class="BOND", balance=15_000_000.0)
    db.add_all([w1, w2])
    db.flush()

    b1 = Budget(user_id=user.id, wallet_id=w1.id, name="KPR Rumah", group_type="LIVING NEEDS", limit_amount=5_000_000.0, month_key="2026-11")
    tx1 = Transaction(
        user_id=user.id,
        wallet_id=w1.id,
        type="INCOME",
        amount=25_000_000.0,
        amount_in_base=25_000_000.0,
        description="Gaji Masuk",
    )
    db.add_all([b1, tx1])
    db.commit()

    # 1. Manual backup
    manual_b = create_account_backup(CreateBackupRequest(title="Sebelum Uji Reset"), current_user=user, db=db)
    assert manual_b["summary"]["wallets_count"] == 2
    assert manual_b["summary"]["total_balance"] == 40_000_000.0

    # 2. Wrong password must fail with 401
    failed_wrong_pw = False
    try:
        reset_account_data(
            ResetAccountDataRequest(password="WrongPassword", mode="ZERO_WALLETS"),
            current_user=user,
            db=db,
        )
    except Exception as exc:
        failed_wrong_pw = getattr(exc, "status_code", None) == 401
    assert failed_wrong_pw is True

    # 3. ZERO_WALLETS reset with correct password
    res_zero = reset_account_data(
        ResetAccountDataRequest(password="MyStrongPass99", mode="ZERO_WALLETS", clear_transactions=False),
        current_user=user,
        db=db,
    )
    assert res_zero["ok"] is True
    db.refresh(w1)
    db.refresh(w2)
    assert w1.balance == 0.0
    assert w2.balance == 0.0

    # 4. FULL_ACCOUNT_RESET with correct password
    res_full = reset_account_data(
        ResetAccountDataRequest(password="MyStrongPass99", mode="FULL_ACCOUNT_RESET"),
        current_user=user,
        db=db,
    )
    assert res_full["ok"] is True
    remaining_tx = db.query(Transaction).filter(Transaction.user_id == user.id).count()
    assert remaining_tx == 0

    # 5. Restore from manual backup snapshot with password verification
    res_restore = restore_account_data(
        RestoreAccountDataRequest(password="MyStrongPass99", backup_id=manual_b["id"]),
        current_user=user,
        db=db,
    )
    assert res_restore["ok"] is True
    assert res_restore["restored_wallets_count"] == 2
    assert res_restore["restored_transactions_count"] == 1
    assert res_restore["restored_budgets_count"] == 1

    restored_wallets = db.query(Wallet).filter(Wallet.user_id == user.id).all()
    assert sum(w.balance for w in restored_wallets) == 40_000_000.0
