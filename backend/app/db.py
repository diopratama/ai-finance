import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Generator, List, Optional

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    create_engine,
    inspect,
    text,
)
from sqlalchemy.orm import DeclarativeBase, Session, relationship, sessionmaker

from app.config import settings

logger = logging.getLogger(__name__)


def _utc_now():
    return datetime.now(timezone.utc)


def _normalize_db_url(url: str) -> str:
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+psycopg2://", 1)
    return url


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    email = Column(String(255), unique=True, index=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    full_name = Column(String(255), nullable=True)
    base_currency = Column(String(8), default="IDR", nullable=False)
    role = Column(String(20), default="user", nullable=False)  # "admin" | "user"
    is_verified = Column(Boolean, default=False, nullable=False)
    verification_code = Column(String(8), nullable=True, index=True)
    verification_expires_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=_utc_now, nullable=False)

    wallets = relationship("Wallet", back_populates="user", cascade="all, delete-orphan")
    categories = relationship("Category", back_populates="user", cascade="all, delete-orphan")
    transactions = relationship("Transaction", back_populates="user", cascade="all, delete-orphan")
    budgets = relationship("Budget", back_populates="user", cascade="all, delete-orphan")
    budget_groups = relationship("BudgetGroup", back_populates="user", cascade="all, delete-orphan")
    bot_links = relationship("BotLink", back_populates="user", cascade="all, delete-orphan")
    financial_profile = relationship("FinancialProfile", uselist=False, back_populates="user", cascade="all, delete-orphan")
    cfp_chats = relationship("CFPChatMessage", back_populates="user", cascade="all, delete-orphan")


class Wallet(Base):
    __tablename__ = "wallets"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String(100), nullable=False)  # e.g., "Mandiri", "Jago", "Danamon", "Cash Dompet"
    type = Column(String(64), default="BANK", nullable=False)  # Preset or custom type e.g. BANK, EWALLET, KANTONG DIGITAL, BANK SYARIAH
    balance = Column(Float, default=0.0, nullable=False)
    currency = Column(String(8), default="IDR", nullable=False)
    color = Column(String(32), default="#f0b000", nullable=False)
    is_default = Column(Boolean, default=False, nullable=False)
    is_archived = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, default=_utc_now, nullable=False)

    user = relationship("User", back_populates="wallets")
    transactions = relationship("Transaction", back_populates="wallet", foreign_keys="Transaction.wallet_id")


class Category(Base):
    __tablename__ = "categories"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True)
    name = Column(String(100), nullable=False)
    icon = Column(String(32), default="tag", nullable=False)
    color = Column(String(32), default="#64748b", nullable=False)
    type = Column(String(20), default="EXPENSE", nullable=False)  # "EXPENSE" | "INCOME"
    is_system = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, default=_utc_now, nullable=False)

    user = relationship("User", back_populates="categories")
    transactions = relationship("Transaction", back_populates="category")
    budgets = relationship("Budget", back_populates="category")


class Transaction(Base):
    __tablename__ = "transactions"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    wallet_id = Column(String(36), ForeignKey("wallets.id", ondelete="CASCADE"), nullable=False, index=True)
    category_id = Column(String(36), ForeignKey("categories.id", ondelete="SET NULL"), nullable=True, index=True)
    budget_id = Column(String(36), ForeignKey("budgets.id", ondelete="SET NULL"), nullable=True, index=True)
    to_wallet_id = Column(String(36), ForeignKey("wallets.id", ondelete="SET NULL"), nullable=True)  # For transfer

    type = Column(String(20), default="EXPENSE", nullable=False)  # EXPENSE, INCOME, TRANSFER
    amount = Column(Float, nullable=False)
    currency = Column(String(8), default="IDR", nullable=False)
    amount_in_base = Column(Float, nullable=False)  # Converted to user base currency
    description = Column(String(512), nullable=False)
    merchant = Column(String(128), nullable=True)
    raw_input = Column(Text, nullable=True)  # Original text message / transcript
    raw_source = Column(String(32), default="WEB", nullable=False)  # WEB, TELEGRAM, WHATSAPP, VOICE, RECEIPT
    receipt_metadata = Column(Text, nullable=True)  # JSON string of receipt items/confidence
    transaction_date = Column(DateTime, default=_utc_now, nullable=False, index=True)
    created_at = Column(DateTime, default=_utc_now, nullable=False)

    user = relationship("User", back_populates="transactions")
    wallet = relationship("Wallet", back_populates="transactions", foreign_keys=[wallet_id])
    category = relationship("Category", back_populates="transactions")
    budget = relationship("Budget", back_populates="transactions")


class Budget(Base):
    __tablename__ = "budgets"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    category_id = Column(String(36), ForeignKey("categories.id", ondelete="SET NULL"), nullable=True, index=True)
    wallet_id = Column(String(36), ForeignKey("wallets.id", ondelete="SET NULL"), nullable=True, index=True)
    name = Column(String(160), nullable=True)  # Specific item e.g. "KPR", "Sekolah Aa dan Ade", "Nabung Umrah"
    group_type = Column(String(64), default="LIVING NEEDS", nullable=False)  # e.g. LIVING NEEDS, LIFE STYLE, PREDICTABLE SAVING, or custom
    remark = Column(String(255), nullable=True)
    limit_amount = Column(Float, nullable=False)
    period = Column(String(20), default="MONTHLY", nullable=False)
    month_key = Column(String(7), nullable=True, index=True)  # Format "YYYY-MM"
    is_sinking_fund = Column(Boolean, default=False, nullable=False)
    rollover_balance = Column(Float, default=0.0, nullable=False)
    funded_this_month = Column(Float, default=0.0, nullable=False)
    sort_order = Column(Integer, default=0, nullable=False)
    created_at = Column(DateTime, default=_utc_now, nullable=False)

    user = relationship("User", back_populates="budgets")
    category = relationship("Category", back_populates="budgets")
    wallet = relationship("Wallet")
    transactions = relationship("Transaction", back_populates="budget")


class BudgetGroup(Base):
    __tablename__ = "budget_groups"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String(100), nullable=False)
    is_sinking_fund = Column(Boolean, default=False, nullable=False)
    sort_order = Column(Integer, default=0, nullable=False)
    created_at = Column(DateTime, default=_utc_now, nullable=False)

    user = relationship("User", back_populates="budget_groups")


class BotLink(Base):
    __tablename__ = "bot_links"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    platform = Column(String(20), nullable=False)  # "TELEGRAM" | "WHATSAPP"
    platform_user_id = Column(String(128), nullable=True, index=True)
    platform_username = Column(String(128), nullable=True)
    pairing_code = Column(String(16), nullable=True, index=True)
    pairing_expires_at = Column(DateTime, nullable=True)
    is_active = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, default=_utc_now, nullable=False)

    user = relationship("User", back_populates="bot_links")


class FinancialProfile(Base):
    __tablename__ = "financial_profiles"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True)
    current_age = Column(Integer, default=28, nullable=False)
    target_fire_age = Column(Integer, default=50, nullable=False)
    monthly_income = Column(Float, default=0.0, nullable=False)
    monthly_living_expense = Column(Float, default=10000000.0, nullable=False)
    monthly_debt_payment = Column(Float, default=0.0, nullable=False)
    marital_status = Column(String(24), default="SINGLE", nullable=False)  # SINGLE | MARRIED
    dependents_count = Column(Integer, default=0, nullable=False)
    risk_tolerance = Column(String(32), default="MODERATE", nullable=False)  # CONSERVATIVE, MODERATE, AGGRESSIVE
    sharia_preference = Column(Boolean, default=False, nullable=False)
    memory_notes = Column(Text, nullable=True)  # Newline/JSON bullet notes captured from chat
    confirmed_profile_fields = Column(Text, default="[]", nullable=False)  # JSON array of user-confirmed field keys
    fire_target_amount = Column(Float, default=3000000000.0, nullable=False)
    emergency_fund_target = Column(Float, default=60000000.0, nullable=False)
    created_at = Column(DateTime, default=_utc_now, nullable=False)

    user = relationship("User", back_populates="financial_profile")


class CFPChatMessage(Base):
    __tablename__ = "cfp_chat_messages"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    role = Column(String(20), nullable=False)  # "user" | "assistant" | "system"
    content = Column(Text, nullable=False)
    metrics_snapshot = Column(Text, nullable=True)  # JSON snapshot of finances at chat time
    created_at = Column(DateTime, default=_utc_now, nullable=False)

    user = relationship("User", back_populates="cfp_chats")


# Database engine with resilience for remote server IP
engine = create_engine(
    _normalize_db_url(settings.DATABASE_URL),
    pool_pre_ping=True,
    pool_recycle=1800,
    connect_args=(
        {"check_same_thread": False}
        if settings.DATABASE_URL.startswith("sqlite")
        else {"connect_timeout": 10}
    ),
)

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


# Dynamic Schema Migration Registry (Self-healing columns)
_SCHEMA_MIGRATIONS = {
    ("wallets", "is_archived"): text("ALTER TABLE wallets ADD COLUMN is_archived BOOLEAN DEFAULT FALSE"),
    ("transactions", "raw_receipt_url"): text("ALTER TABLE transactions ADD COLUMN raw_receipt_url VARCHAR(1024)"),
    ("transactions", "merchant"): text("ALTER TABLE transactions ADD COLUMN merchant VARCHAR(128)"),
    ("transactions", "budget_id"): text("ALTER TABLE transactions ADD COLUMN budget_id VARCHAR(36)"),
    ("budgets", "wallet_id"): text("ALTER TABLE budgets ADD COLUMN wallet_id VARCHAR(36)"),
    ("budgets", "name"): text("ALTER TABLE budgets ADD COLUMN name VARCHAR(160)"),
    ("budgets", "group_type"): text("ALTER TABLE budgets ADD COLUMN group_type VARCHAR(64) DEFAULT 'LIVING NEEDS'"),
    ("budgets", "remark"): text("ALTER TABLE budgets ADD COLUMN remark VARCHAR(255)"),
    ("budgets", "month_key"): text("ALTER TABLE budgets ADD COLUMN month_key VARCHAR(7)"),
    ("budgets", "is_sinking_fund"): text("ALTER TABLE budgets ADD COLUMN is_sinking_fund BOOLEAN DEFAULT FALSE"),
    ("budgets", "rollover_balance"): text("ALTER TABLE budgets ADD COLUMN rollover_balance FLOAT DEFAULT 0"),
    ("budgets", "funded_this_month"): text("ALTER TABLE budgets ADD COLUMN funded_this_month FLOAT DEFAULT 0"),
    ("budgets", "sort_order"): text("ALTER TABLE budgets ADD COLUMN sort_order INTEGER DEFAULT 0"),
    ("financial_profiles", "monthly_income"): text("ALTER TABLE financial_profiles ADD COLUMN monthly_income FLOAT DEFAULT 0"),
    ("financial_profiles", "monthly_debt_payment"): text("ALTER TABLE financial_profiles ADD COLUMN monthly_debt_payment FLOAT DEFAULT 0"),
    ("financial_profiles", "marital_status"): text("ALTER TABLE financial_profiles ADD COLUMN marital_status VARCHAR(24) DEFAULT 'SINGLE'"),
    ("financial_profiles", "dependents_count"): text("ALTER TABLE financial_profiles ADD COLUMN dependents_count INTEGER DEFAULT 0"),
    ("financial_profiles", "sharia_preference"): text("ALTER TABLE financial_profiles ADD COLUMN sharia_preference BOOLEAN DEFAULT FALSE"),
    ("financial_profiles", "memory_notes"): text("ALTER TABLE financial_profiles ADD COLUMN memory_notes TEXT"),
    ("financial_profiles", "confirmed_profile_fields"): text("ALTER TABLE financial_profiles ADD COLUMN confirmed_profile_fields TEXT DEFAULT '[]'"),
    ("users", "is_verified"): text("ALTER TABLE users ADD COLUMN is_verified BOOLEAN DEFAULT FALSE"),
    ("users", "verification_code"): text("ALTER TABLE users ADD COLUMN verification_code VARCHAR(8)"),
    ("users", "verification_expires_at"): text("ALTER TABLE users ADD COLUMN verification_expires_at TIMESTAMP"),
}


def _ensure_schema_columns() -> None:
    """Dynamically checks and alters tables if newly defined columns are absent."""
    try:
        inspector = inspect(engine)
        existing_tables = set(inspector.get_table_names())
        for (table_name, column_name), ddl_stmt in _SCHEMA_MIGRATIONS.items():
            if table_name not in existing_tables:
                continue
            existing_cols = {col["name"] for col in inspector.get_columns(table_name)}
            if column_name not in existing_cols:
                try:
                    with engine.begin() as conn:
                        conn.execute(ddl_stmt)
                    logger.info("Auto-migrated column: %s.%s", table_name, column_name)
                except Exception as err:
                    logger.debug("Column addition ignored or already applied: %s", err)

        # Relax NOT NULL on budgets.category_id and widen wallets.type on PostgreSQL
        if not settings.DATABASE_URL.startswith("sqlite"):
            if "users" in existing_tables:
                try:
                    with engine.begin() as conn:
                        conn.execute(text("UPDATE users SET is_verified = TRUE WHERE is_verified IS NULL OR (is_verified = FALSE AND verification_code IS NULL)"))
                except Exception as err:
                    logger.debug("users.is_verified legacy backfill skipped: %s", err)

            if "budgets" in existing_tables:
                try:
                    with engine.begin() as conn:
                        conn.execute(text("ALTER TABLE budgets ALTER COLUMN category_id DROP NOT NULL"))
                except Exception as err:
                    logger.debug("budgets.category_id nullable check skipped: %s", err)
            if "wallets" in existing_tables:
                try:
                    with engine.begin() as conn:
                        conn.execute(text("ALTER TABLE wallets ALTER COLUMN type TYPE VARCHAR(64)"))
                except Exception as err:
                    logger.debug("wallets.type widen skipped: %s", err)

        # Backfill legacy budget rows missing month_key or name
        if "budgets" in existing_tables:
            now_mk = _utc_now().strftime("%Y-%m")
            db = SessionLocal()
            try:
                legacy_rows = db.query(Budget).filter(
                    (Budget.month_key == None) | (Budget.name == None) | (Budget.group_type == None)
                ).all()
                if legacy_rows:
                    for b in legacy_rows:
                        if not b.month_key:
                            b.month_key = now_mk
                        if not b.group_type:
                            b.group_type = "LIVING NEEDS"
                        if not b.name:
                            b.name = b.category.name if b.category else "Pos Anggaran"
                        if b.is_sinking_fund is None:
                            b.is_sinking_fund = False
                        if b.rollover_balance is None:
                            b.rollover_balance = 0.0
                        if b.funded_this_month is None:
                            b.funded_this_month = 0.0
                        if b.sort_order is None:
                            b.sort_order = 0
                    db.commit()
            except Exception as err:
                logger.debug("Budget backfill notice: %s", err)
                db.rollback()
            finally:
                db.close()
    except Exception as e:
        logger.warning("Dynamic schema update notice: %s", e)


DEFAULT_CATEGORIES = [
    {"name": "Makanan & Minuman", "icon": "utensils", "color": "#ef4444", "type": "EXPENSE"},
    {"name": "Transportasi", "icon": "car", "color": "#f97316", "type": "EXPENSE"},
    {"name": "Belanja", "icon": "shopping-bag", "color": "#eab308", "type": "EXPENSE"},
    {"name": "Tagihan & Utilitas", "icon": "receipt", "color": "#06b6d4", "type": "EXPENSE"},
    {"name": "Hiburan & Rekreasi", "icon": "film", "color": "#8b5cf6", "type": "EXPENSE"},
    {"name": "Kesehatan", "icon": "heart-pulse", "color": "#ec4899", "type": "EXPENSE"},
    {"name": "Pendidikan", "icon": "graduation-cap", "color": "#3b82f6", "type": "EXPENSE"},
    {"name": "Investasi", "icon": "trending-up", "color": "#10b981", "type": "EXPENSE"},
    {"name": "Gaji & Pendapatan", "icon": "wallet", "color": "#22c55e", "type": "INCOME"},
    {"name": "Bonus & Freelance", "icon": "coins", "color": "#14b8a6", "type": "INCOME"},
    {"name": "Hasil Investasi / Dividen", "icon": "pie-chart", "color": "#6366f1", "type": "INCOME"},
    {"name": "Lain-lain", "icon": "more-horizontal", "color": "#64748b", "type": "EXPENSE"},
]

DEFAULT_BUDGET_GROUPS = [
    {"name": "LIVING NEEDS", "is_sinking_fund": False, "sort_order": 1},
    {"name": "LIFE STYLE", "is_sinking_fund": False, "sort_order": 2},
    {"name": "ZAKAT DAN SEDEKAH", "is_sinking_fund": False, "sort_order": 3},
    {"name": "PREDICTABLE SAVING", "is_sinking_fund": True, "sort_order": 4},
]


def ensure_user_default_groups(db: Session, user_id: str) -> List[BudgetGroup]:
    """Ensures a user has budget groups configured, seeding defaults if needed."""
    existing = (
        db.query(BudgetGroup)
        .filter(BudgetGroup.user_id == user_id)
        .order_by(BudgetGroup.sort_order.asc(), BudgetGroup.created_at.asc())
        .all()
    )
    if not existing:
        for g in DEFAULT_BUDGET_GROUPS:
            db.add(
                BudgetGroup(
                    user_id=user_id,
                    name=g["name"],
                    is_sinking_fund=g["is_sinking_fund"],
                    sort_order=g["sort_order"],
                )
            )
        db.flush()

        # Also pull any custom groups already used in user's existing budgets
        legacy_custom_types = [
            r[0].strip().upper()
            for r in db.query(Budget.group_type).filter(Budget.user_id == user_id).distinct().all()
            if r[0] and r[0].strip().upper() not in [dg["name"] for dg in DEFAULT_BUDGET_GROUPS]
        ]
        next_order = 5
        for ct in legacy_custom_types:
            db.add(
                BudgetGroup(
                    user_id=user_id,
                    name=ct,
                    is_sinking_fund=False,
                    sort_order=next_order,
                )
            )
            next_order += 1
        db.commit()

        existing = (
            db.query(BudgetGroup)
            .filter(BudgetGroup.user_id == user_id)
            .order_by(BudgetGroup.sort_order.asc(), BudgetGroup.created_at.asc())
            .all()
        )
    return existing


def ensure_default_seeds() -> None:
    """Seeds default categories, starter admin user and default starter wallets."""
    from app.security import hash_password

    db = SessionLocal()
    try:
        # 1. System Default Categories
        for cat in DEFAULT_CATEGORIES:
            existing = db.query(Category).filter(Category.name == cat["name"], Category.is_system == True).first()
            if not existing:
                db.add(
                    Category(
                        name=cat["name"],
                        icon=cat["icon"],
                        color=cat["color"],
                        type=cat["type"],
                        is_system=True,
                    )
                )

        # 2. Initial Admin Account (if configured)
        if settings.ADMIN_EMAIL and settings.ADMIN_PASSWORD:
            admin_email = settings.ADMIN_EMAIL.lower().strip()
            existing_admin = db.query(User).filter(User.email == admin_email).first()
            if not existing_admin:
                admin_user = User(
                    email=admin_email,
                    password_hash=hash_password(settings.ADMIN_PASSWORD),
                    full_name="Admin AI-Finance",
                    base_currency="IDR",
                    role="admin",
                    is_verified=True,
                )
                db.add(admin_user)
                db.flush()

                # Starter wallets for admin
                db.add(Wallet(user_id=admin_user.id, name="Cash Dompet", type="CASH", balance=500000.0, color="#10b981", is_default=True))
                db.add(Wallet(user_id=admin_user.id, name="Bank BCA", type="BANK", balance=15000000.0, color="#3b82f6", is_default=False))
                db.add(Wallet(user_id=admin_user.id, name="GoPay", type="EWALLET", balance=750000.0, color="#06b6d4", is_default=False))

                # Default groups for admin
                ensure_user_default_groups(db, admin_user.id)

                # Starter financial profile
                db.add(FinancialProfile(user_id=admin_user.id, current_age=28, target_fire_age=45, monthly_living_expense=8000000.0, fire_target_amount=2400000000.0))

        db.commit()
    except Exception as e:
        logger.warning("Error running seeds: %s", e)
        db.rollback()
    finally:
        db.close()


def init_db() -> None:
    """Initializes tables dynamically on any PostgreSQL or SQLite database."""
    Base.metadata.create_all(bind=engine)
    _ensure_schema_columns()
    ensure_default_seeds()
    logger.info("Database initialized successfully with auto-dynamic schema verification.")


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

