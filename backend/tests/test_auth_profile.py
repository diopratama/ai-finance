import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from fastapi import HTTPException

from app.db import Base, User
from app.api.auth import (
    RegisterRequest,
    VerifyEmailRequest,
    LoginRequest,
    UpdateProfileRequest,
    ChangePasswordRequest,
    register,
    verify_email,
    login,
    update_profile,
    change_password,
)
from app.security import hash_password, verify_password


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


@pytest.mark.asyncio
async def test_register_mandatory_full_name_and_verification(db_session):
    # 1. Full name too short / empty
    with pytest.raises(HTTPException) as exc:
        await register(
            RegisterRequest(full_name=" ", email="dio@test.com", password="Password123!"),
            db=db_session,
        )
    assert exc.value.status_code == 400
    assert "Nama lengkap" in exc.value.detail

    # 2. Valid registration
    res = await register(
        RegisterRequest(full_name="Dio Pratama", email="dio@test.com", password="Password123!"),
        db=db_session,
    )
    assert res["status"] == "verification_required"
    assert res["is_verified"] is False
    assert res["email"] == "dio@test.com"

    user = db_session.query(User).filter(User.email == "dio@test.com").first()
    assert user is not None
    assert user.is_verified is False
    assert len(user.verification_code) == 6

    # 3. Login before verification should be blocked with 403
    with pytest.raises(HTTPException) as login_exc:
        login(LoginRequest(email="dio@test.com", password="Password123!"), db=db_session)
    assert login_exc.value.status_code == 403
    assert "Email belum diverifikasi" in login_exc.value.detail

    # 4. Verify with wrong code should fail
    with pytest.raises(HTTPException) as verify_exc:
        verify_email(VerifyEmailRequest(email="dio@test.com", code="000000"), db=db_session)
    assert verify_exc.value.status_code == 400

    # 5. Verify with correct code should succeed
    auth_res = verify_email(VerifyEmailRequest(email="dio@test.com", code=user.verification_code), db=db_session)
    assert auth_res["user"]["is_verified"] is True
    assert "access_token" in auth_res

    # 6. Now login succeeds
    login_res = login(LoginRequest(email="dio@test.com", password="Password123!"), db=db_session)
    assert login_res["user"]["is_verified"] is True


def test_update_profile_and_change_password(db_session):
    user = User(
        email="user@test.com",
        password_hash=hash_password("OldPassword123!"),
        full_name="Original Name",
        base_currency="IDR",
        role="user",
        is_verified=True,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)

    # 1. Update profile mandatory name
    with pytest.raises(HTTPException):
        update_profile(UpdateProfileRequest(full_name="A", email="user@test.com"), current_user=user, db=db_session)

    # 2. Update profile valid
    updated = update_profile(
        UpdateProfileRequest(full_name="Updated Name", email="newuser@test.com", base_currency="USD"),
        current_user=user,
        db=db_session,
    )
    assert updated["full_name"] == "Updated Name"
    assert updated["email"] == "newuser@test.com"
    assert updated["base_currency"] == "USD"

    # 3. Change password with wrong old password
    with pytest.raises(HTTPException) as cp_exc:
        change_password(
            ChangePasswordRequest(old_password="WrongPassword", new_password="NewPassword123!"),
            current_user=user,
            db=db_session,
        )
    assert cp_exc.value.status_code == 400

    # 4. Change password with correct old password
    res_cp = change_password(
        ChangePasswordRequest(old_password="OldPassword123!", new_password="NewPassword123!"),
        current_user=user,
        db=db_session,
    )
    assert res_cp["ok"] is True
    assert verify_password("NewPassword123!", user.password_hash) is True
