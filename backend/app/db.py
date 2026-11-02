import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Generator

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
    created_at = Column(DateTime, default=_utc_now, nullable=False)

    wallets = relationship("Wallet", back_populates="user", cascade="all, delete-orphan")
    categories = relationship("Category", back_populates="user", cascade="all, delete-orphan")
    transactions = relationship("Transaction", back_populates="user", cascade="all, delete-orphan")
    budgets = relationship("Budget", back_populates="user", cascade="all, delete-orphan")
    bot_links = relationship("BotLink", back_populates="user", cascade="all, delete-orphan")
    financial_profile = relationship("FinancialProfile", uselist=False, back_populates="user", cascade="all, delete-orphan")
    cfp_chats = relationship("CFPChatMessage", back_populates="user", cascade="all, delete-orphan")


class Wallet(Base):
    __tablename__ = "wallets"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String(100), nullable=False)  # e.g., "Bank BCA", "GoPay", "Cash Dompet"
    type = Column(String(32), default="BANK", nullable=False)  # BANK, EWALLET, CASH, INVESTMENT, CREDIT
    balance = Column(Float, default=0.0, nullable=False)
    currency = Column(String(8), default="IDR", nullable=False)
    color = Column(String(32), default="#3b82f6", nullable=False)
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


class Budget(Base):
    __tablename__ = "budgets"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    category_id = Column(String(36), ForeignKey("categories.id", ondelete="CASCADE"), nullable=False, index=True)
    limit_amount = Column(Float, nullable=False)
    period = Column(String(20), default="MONTHLY", nullable=False)
    created_at = Column(DateTime, default=_utc_now, nullable=False)

    user = relationship("User", back_populates="budgets")
    category = relationship("Category", back_populates="budgets")


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
    ("financial_profiles", "monthly_income"): text("ALTER TABLE financial_profiles ADD COLUMN monthly_income FLOAT DEFAULT 0"),
    ("financial_profiles", "monthly_debt_payment"): text("ALTER TABLE financial_profiles ADD COLUMN monthly_debt_payment FLOAT DEFAULT 0"),
    ("financial_profiles", "marital_status"): text("ALTER TABLE financial_profiles ADD COLUMN marital_status VARCHAR(24) DEFAULT 'SINGLE'"),
    ("financial_profiles", "dependents_count"): text("ALTER TABLE financial_profiles ADD COLUMN dependents_count INTEGER DEFAULT 0"),
    ("financial_profiles", "sharia_preference"): text("ALTER TABLE financial_profiles ADD COLUMN sharia_preference BOOLEAN DEFAULT FALSE"),
    ("financial_profiles", "memory_notes"): text("ALTER TABLE financial_profiles ADD COLUMN memory_notes TEXT"),
    ("financial_profiles", "confirmed_profile_fields"): text("ALTER TABLE financial_profiles ADD COLUMN confirmed_profile_fields TEXT DEFAULT '[]'"),
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
                )
                db.add(admin_user)
                db.flush()

                # Starter wallets for admin
                db.add(Wallet(user_id=admin_user.id, name="Cash Dompet", type="CASH", balance=500000.0, color="#10b981", is_default=True))
                db.add(Wallet(user_id=admin_user.id, name="Bank BCA", type="BANK", balance=15000000.0, color="#3b82f6", is_default=False))
                db.add(Wallet(user_id=admin_user.id, name="GoPay", type="EWALLET", balance=750000.0, color="#06b6d4", is_default=False))

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

