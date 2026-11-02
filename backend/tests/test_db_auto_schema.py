import os
import pytest
from sqlalchemy import inspect, create_engine, text
from app.db import Base, init_db, _ensure_schema_columns, DEFAULT_CATEGORIES, SessionLocal, User, Category, Wallet


def test_db_auto_schema_creation(tmp_path):
    """Verifies that all tables and default seeds are automatically created."""
    init_db()
    db = SessionLocal()
    try:
        # Check system categories are populated
        system_cats = db.query(Category).filter(Category.is_system == True).all()
        assert len(system_cats) >= len(DEFAULT_CATEGORIES)

        # Check admin user was provisioned
        admin = db.query(User).filter(User.role == "admin").first()
        assert admin is not None
        assert admin.email == "admin@aifinance.com"

        # Check admin starter wallets
        wallets = db.query(Wallet).filter(Wallet.user_id == admin.id).all()
        assert len(wallets) >= 3
    finally:
        db.close()


def test_dynamic_column_addition():
    """Verifies dynamic column self-healing check runs without errors."""
    _ensure_schema_columns()

