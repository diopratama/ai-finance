import os
import pytest
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker

import app.db as app_db
from app.db import Base, DEFAULT_CATEGORIES, User, Category, Wallet


def test_db_auto_schema_creation(tmp_path, monkeypatch):
    """Verifies that all tables and default seeds are automatically created."""
    db_file = tmp_path / "test_schema.db"
    test_engine = create_engine(f"sqlite:///{db_file}", connect_args={"check_same_thread": False})
    test_session = sessionmaker(bind=test_engine, autoflush=False, autocommit=False)

    monkeypatch.setattr(app_db, "engine", test_engine)
    monkeypatch.setattr(app_db, "SessionLocal", test_session)

    app_db.init_db()
    db = test_session()
    try:
        # Check system categories are populated
        system_cats = db.query(Category).filter(Category.is_system == True).all()
        assert len(system_cats) >= len(DEFAULT_CATEGORIES)

        # Check admin user was provisioned
        admin = db.query(User).filter(User.role == "admin").first()
        assert admin is not None
        assert admin.email in ["admin@aifinance.com", "dpratama.43@gmail.com"]

        # Check admin starter wallets
        wallets = db.query(Wallet).filter(Wallet.user_id == admin.id).all()
        assert len(wallets) >= 3
    finally:
        db.close()


def test_dynamic_column_addition(tmp_path, monkeypatch):
    """Verifies dynamic column self-healing check runs without errors."""
    db_file = tmp_path / "test_migration.db"
    test_engine = create_engine(f"sqlite:///{db_file}", connect_args={"check_same_thread": False})
    test_session = sessionmaker(bind=test_engine, autoflush=False, autocommit=False)

    monkeypatch.setattr(app_db, "engine", test_engine)
    monkeypatch.setattr(app_db, "SessionLocal", test_session)

    Base.metadata.create_all(bind=test_engine)
    app_db._ensure_schema_columns()

