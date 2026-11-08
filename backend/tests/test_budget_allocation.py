from datetime import datetime, timezone
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base, Budget, Category, DEFAULT_CATEGORIES, FinancialProfile, Transaction, User, Wallet
from app.api.budgets import (
    CopyMonthRequest,
    CreateBudgetGroupRequest,
    CreateBudgetRequest,
    CreateCategoryRequest,
    DistributePaydayRequest,
    RecordBudgetActionRequest,
    RenameGroupRequest,
    UpdateBudgetGroupRequest,
    compute_monthly_allocation_data,
    copy_budgets_from_previous_month,
    create_budget,
    create_budget_group,
    create_custom_category,
    delete_budget_group,
    distribute_payday_allocations,
    get_budget_groups,
    get_current_month_key,
    record_budget_action,
    rename_budget_group,
    update_budget_group,
)
from app.api.wallets import CreateWalletRequest, create_wallet, list_wallets
from app.api.webhooks import _process_user_transaction_message


@pytest.fixture()
def db_session():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    TestingSession = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    db = TestingSession()
    try:
        for cat in DEFAULT_CATEGORIES:
            db.add(
                Category(
                    name=cat["name"],
                    icon=cat["icon"],
                    color=cat["color"],
                    type=cat["type"],
                    is_system=True,
                )
            )
        user = User(
            email="budget_tester@aifinance.com",
            password_hash="hashed",
            full_name="Dio Pratama",
            base_currency="IDR",
            role="user",
        )
        db.add(user)
        db.flush()
        db.add(
            FinancialProfile(
                user_id=user.id,
                monthly_income=62_250_000.0,
                monthly_living_expense=21_821_363.0,
            )
        )
        db.commit()
        yield db, user
    finally:
        db.close()


def test_custom_wallets_categories_and_group_types(db_session):
    db, user = db_session

    # Custom wallet name & custom free-text wallet type
    w_syariah = create_wallet(
        CreateWalletRequest(name="Jago Kantong Syariah", type="KANTONG SYARIAH", balance=1_500_000.0, color="#f0b000"),
        current_user=user,
        db=db,
    )
    assert w_syariah["name"] == "Jago Kantong Syariah"
    assert w_syariah["type"] == "KANTONG SYARIAH"

    # Custom user category
    custom_cat = create_custom_category(
        CreateCategoryRequest(name="Kebutuhan Anak", type="EXPENSE", color="#f0b000"),
        current_user=user,
        db=db,
    )
    assert custom_cat["name"] == "Kebutuhan Anak"
    assert custom_cat["is_system"] is False

    # Custom group TYPE
    mk = get_current_month_key()
    b = create_budget(
        CreateBudgetRequest(
            name="SPP Sekolah Anak",
            group_type="PENDIDIKAN KELUARGA",
            limit_amount=2_760_000.0,
            wallet_id=w_syariah["id"],
            category_id=custom_cat["id"],
            month_key=mk,
        ),
        current_user=user,
        db=db,
    )
    assert b["group_type"] == "PENDIDIKAN KELUARGA"
    assert b["wallet"]["name"] == "Jago Kantong Syariah"

    # Rename group TYPE
    renamed = rename_budget_group(
        RenameGroupRequest(old_group_type="PENDIDIKAN KELUARGA", new_group_type="EDUKASI ANAK", month_key=mk),
        current_user=user,
        db=db,
    )
    assert renamed["updated_count"] == 1
    alloc = compute_monthly_allocation_data(user, db, mk)
    assert any(g["group_type"] == "EDUKASI ANAK" for g in alloc["groups"])


def test_payday_distribution_and_sinking_fund_rollover(db_session):
    db, user = db_session
    mk = "2026-11"
    next_mk = "2026-12"

    payroll = create_wallet(CreateWalletRequest(name="Payroll BCA", type="BANK", balance=50_000_000.0, is_default=True), user, db)
    mandiri = create_wallet(CreateWalletRequest(name="Mandiri", type="BANK", balance=0.0), user, db)
    jago = create_wallet(CreateWalletRequest(name="Jago", type="KANTONG DIGITAL", balance=0.0), user, db)
    danamon = create_wallet(CreateWalletRequest(name="Danamon", type="BANK", balance=0.0), user, db)

    # Living Needs + Predictable Saving in Mandiri = Rp 10,000,000
    kpr = create_budget(
        CreateBudgetRequest(name="KPR", group_type="LIVING NEEDS", limit_amount=6_301_363.0, wallet_id=mandiri["id"], month_key=mk),
        user,
        db,
    )
    pelunasan_kpr = create_budget(
        CreateBudgetRequest(name="Pelunasan KPR", group_type="PREDICTABLE SAVING", limit_amount=3_698_637.0, wallet_id=mandiri["id"], month_key=mk),
        user,
        db,
    )
    umrah = create_budget(
        CreateBudgetRequest(name="Nabung Umrah", group_type="PREDICTABLE SAVING", limit_amount=2_000_000.0, wallet_id=jago["id"], month_key=mk),
        user,
        db,
    )
    bensin = create_budget(
        CreateBudgetRequest(name="Bensin Mobil + Motor", group_type="LIVING NEEDS", limit_amount=1_000_000.0, wallet_id=danamon["id"], month_key=mk),
        user,
        db,
    )

    assert pelunasan_kpr["is_sinking_fund"] is True
    assert umrah["is_sinking_fund"] is True

    # Before payday distribution: Mandiri needs 10,000,000, Jago needs 2,000,000, Danamon needs 1,000,000
    alloc_before = compute_monthly_allocation_data(user, db, mk)
    by_w = {wa["wallet_name"]: wa for wa in alloc_before["wallet_allocations"]}
    assert by_w["Mandiri"]["shortfall_amount"] == 10_000_000.0
    assert by_w["Mandiri"]["status"] == "SHORTFALL"
    assert by_w["Jago"]["shortfall_amount"] == 2_000_000.0
    assert by_w["Danamon"]["shortfall_amount"] == 1_000_000.0

    # Execute 1-click Payday Distribution from Payroll BCA
    dist_res = distribute_payday_allocations(
        DistributePaydayRequest(source_wallet_id=payroll["id"], month_key=mk, mode="SHORTFALL", auto_fund_sinking=True),
        user,
        db,
    )
    assert len(dist_res["transfers_executed"]) == 3
    by_w_after = {wa["wallet_name"]: wa for wa in dist_res["allocation"]["wallet_allocations"]}
    assert by_w_after["Mandiri"]["current_balance"] == 10_000_000.0
    assert by_w_after["Mandiri"]["status"] == "FUNDED"
    assert by_w_after["Payroll BCA"]["current_balance"] == 37_000_000.0

    # Pay KPR (6,301,363) via 1-click record action; Mandiri balance becomes 3,698,637 (earmarked for Pelunasan KPR!)
    tx_kpr = db.query(Budget).filter(Budget.id == kpr["id"]).first()
    record_res = record_budget_action(
        kpr["id"],
        RecordBudgetActionRequest(mode="EXPENSE", amount=6_301_363.0),
        user,
        db,
    )
    # Fix transaction date to match 2026-11 so monthly math aligns regardless of test wall-clock date
    latest_tx = db.query(Transaction).filter(Transaction.id == record_res["transaction_id"]).first()
    latest_tx.transaction_date = datetime(2026, 11, 10, tzinfo=timezone.utc)
    db.commit()

    # Copy template into December 2026 (2026-12):
    # - KPR resets to 0 spent
    # - Pelunasan KPR rolls over 3,698,637; Nabung Umrah rolls over 2,000,000!
    copied = copy_budgets_from_previous_month(
        CopyMonthRequest(target_month=next_mk, source_month=mk),
        user,
        db,
    )
    assert copied["copied_count"] == 4
    dec_groups = {g["group_type"]: g for g in copied["allocation"]["groups"]}
    dec_sinking_items = {it["name"]: it for it in dec_groups["PREDICTABLE SAVING"]["items"]}
    assert dec_sinking_items["Pelunasan KPR"]["rollover_balance"] == 3_698_637.0
    assert dec_sinking_items["Nabung Umrah"]["rollover_balance"] == 2_000_000.0

    # Check December shortfall on Mandiri: 3,698,637 already sitting in Mandiri, so December paycheck shortfall is 10,000,000!
    dec_by_w = {wa["wallet_name"]: wa for wa in copied["allocation"]["wallet_allocations"]}
    assert dec_by_w["Mandiri"]["shortfall_amount"] == 10_000_000.0


def test_chatbot_smart_fund_location_routing(db_session):
    db, user = db_session
    mk = get_current_month_key()

    create_wallet(CreateWalletRequest(name="Payroll Utama", type="BANK", balance=10_000_000.0, is_default=True), user, db)
    danamon = create_wallet(CreateWalletRequest(name="Danamon", type="BANK", balance=1_500_000.0), user, db)

    create_budget(
        CreateBudgetRequest(
            name="Bensin Mobil + Motor",
            group_type="LIVING NEEDS",
            limit_amount=1_000_000.0,
            wallet_id=danamon["id"],
            month_key=mk,
        ),
        user,
        db,
    )

    # User chats WITHOUT mentioning Danamon -> bot automatically routes to Danamon via matched budget's Fund Location!
    res = _process_user_transaction_message(
        user=user,
        raw_text="isi bensin 250rb",
        source="WHATSAPP",
        receipt_meta=None,
        db=db,
    )
    assert res["success"] is True
    assert res["wallet"]["name"] == "Danamon"
    assert res["wallet"]["balance"] == 1_250_000.0
    assert res["matched_budget"]["name"] == "Bensin Mobil + Motor"
    assert res["matched_budget"]["remaining_amount"] == 750_000.0


def test_budget_group_crud_and_reassign(db_session):
    db, user = db_session
    mk = get_current_month_key()

    # 1. Fetch initial groups (should auto-seed 4 defaults)
    initial_groups = get_budget_groups(current_user=user, db=db)
    assert len(initial_groups) == 4
    names = [g.name for g in initial_groups]
    assert "LIVING NEEDS" in names
    assert "PREDICTABLE SAVING" in names

    # 2. Create new custom group
    created = create_budget_group(
        CreateBudgetGroupRequest(name="DANA DARURAT", is_sinking_fund=True),
        current_user=user,
        db=db,
    )
    assert created.name == "DANA DARURAT"
    assert created.is_sinking_fund is True

    # Check allocation includes the new empty group
    alloc = compute_monthly_allocation_data(user, db, mk)
    grp_types = [g["group_type"] for g in alloc["groups"]]
    assert "DANA DARURAT" in grp_types

    # 3. Add an item under DANA DARURAT
    b_item = create_budget(
        CreateBudgetRequest(
            name="Tabungan Darurat 6 Bulan",
            group_type="DANA DARURAT",
            limit_amount=3_000_000.0,
            month_key=mk,
        ),
        current_user=user,
        db=db,
    )
    assert b_item["group_type"] == "DANA DARURAT"

    # 4. Update/Rename Group
    updated = update_budget_group(
        group_id=created.id,
        req=UpdateBudgetGroupRequest(name="DANA CADANGAN & DARURAT"),
        current_user=user,
        db=db,
    )
    assert updated.name == "DANA CADANGAN & DARURAT"
    # Verify budget item was automatically cascaded
    b_refreshed = db.query(Budget).filter(Budget.id == b_item["id"]).first()
    assert b_refreshed.group_type == "DANA CADANGAN & DARURAT"

    # 5. Delete group with reassign to LIVING NEEDS
    living_grp = next(g for g in initial_groups if g.name == "LIVING NEEDS")
    del_res = delete_budget_group(
        group_id=created.id,
        action="reassign",
        reassign_to_id=living_grp.id,
        current_user=user,
        db=db,
    )
    assert del_res["success"] is True
    assert del_res["items_affected"] == 1
    assert del_res["action_taken"] == "reassign"

    # Verify item moved to LIVING NEEDS
    b_reassigned = db.query(Budget).filter(Budget.id == b_item["id"]).first()
    assert b_reassigned.group_type == "LIVING NEEDS"


