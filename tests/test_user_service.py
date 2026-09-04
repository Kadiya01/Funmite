"""UserService (F4 User/Cashier management) tests.

Covers the Phase 12 F4 acceptance points:
create Cashier, duplicate-username rejection, edit, deactivate/reactivate,
reset password, inactive users cannot log in, unauthorized users cannot manage,
Admin cannot create another Admin, audit events, and historical references
survive deactivation.
"""

from __future__ import annotations

import pytest
from sqlalchemy import select

from app.data.models import ROLE_ADMIN, ROLE_CASHIER, AuditLog, Sale, User
from app.domain.errors import AuthorizationError, ValidationError
from app.domain.services.audit_service import (
    ACTION_USER_ACTIVATED,
    ACTION_USER_CREATED,
    ACTION_USER_DEACTIVATED,
    ACTION_USER_UPDATED,
    ACTION_PASSWORD_RESET,
)
from app.domain.services.auth_service import AuthService
from app.domain.services.user_service import MIN_PASSWORD_LENGTH, UserService
from app.domain.session import CurrentUser
from app.security.passwords import verify_password
from tests.factories import (
    make_category,
    make_customer,
    make_product,
    make_sale,
    make_user,
)


def _admin(session, username="admin") -> CurrentUser:
    user = make_user(session, username=username, role=ROLE_ADMIN)
    session.commit()
    return CurrentUser(
        user_id=user.id,
        username=user.username,
        full_name=user.full_name,
        role=user.role,
    )


def _cashier_actor(session) -> CurrentUser:
    user = make_user(session, username="costas", role=ROLE_CASHIER)
    session.commit()
    return CurrentUser(
        user_id=user.id,
        username=user.username,
        full_name=user.full_name,
        role=user.role,
    )


def _audit_actions(session) -> list[str]:
    return list(session.scalars(select(AuditLog.action)))


def _user(session, username: str) -> User:
    return session.scalar(select(User).where(User.username == username))


# --- create -------------------------------------------------------------- #


def test_create_cashier(session):
    actor = _admin(session)
    user = UserService(session).create(
        actor, username="kasuwa", full_name="Amina Bello", password="secret6"
    )
    assert user.role == ROLE_CASHIER
    assert user.is_active is True
    assert verify_password("secret6", user.password_hash) is True
    assert ACTION_USER_CREATED in _audit_actions(session)


def test_create_rejects_duplicate_username(session):
    actor = _admin(session)
    make_user(session, username="kasuwa", role=ROLE_CASHIER)
    session.commit()
    with pytest.raises(ValidationError):
        UserService(session).create(
            actor, username="kasuwa", full_name="X", password="secret6"
        )


def test_create_validates_fields(session):
    actor = _admin(session)
    with pytest.raises(ValidationError):
        UserService(session).create(actor, username="", full_name="X", password="secret6")
    with pytest.raises(ValidationError):
        UserService(session).create(actor, username="u", full_name="", password="secret6")
    with pytest.raises(ValidationError):
        UserService(session).create(actor, username="u", full_name="X", password="")
    with pytest.raises(ValidationError):
        UserService(session).create(
            actor, username="u", full_name="X", password="1234"
        )


def test_create_never_creates_admin(session):
    actor = _admin(session)
    user = UserService(session).create(
        actor, username="kasuwa", full_name="Amina", password="secret6"
    )
    assert user.role == ROLE_CASHIER


def test_unauthorized_cashier_cannot_create_user(session):
    actor = _cashier_actor(session)
    with pytest.raises(AuthorizationError):
        UserService(session).create(
            actor, username="kasuwa", full_name="Amina", password="secret6"
        )


# --- edit ---------------------------------------------------------------- #


def test_edit_cashier(session):
    actor = _admin(session)
    target = make_user(session, username="kasuwa", role=ROLE_CASHIER, full_name="Old")
    session.commit()
    updated = UserService(session).update(actor, target.id, full_name="New Name")
    assert updated.full_name == "New Name"
    assert ACTION_USER_UPDATED in _audit_actions(session)


def test_edit_cannot_touch_admin_account(session):
    actor = _admin(session)
    other_admin = make_user(session, username="admin2", role=ROLE_ADMIN)
    session.commit()
    with pytest.raises(ValidationError):
        UserService(session).update(actor, other_admin.id, full_name="X")


# --- deactivate / activate ---------------------------------------------- #


def test_deactivate_cashier(session):
    actor = _admin(session)
    target = make_user(session, username="kasuwa", role=ROLE_CASHIER)
    session.commit()
    UserService(session).deactivate(actor, target.id)
    assert _user(session, "kasuwa").is_active is False
    assert ACTION_USER_DEACTIVATED in _audit_actions(session)


def test_activate_cashier(session):
    actor = _admin(session)
    target = make_user(session, username="kasuwa", role=ROLE_CASHIER)
    target.is_active = False
    session.commit()
    UserService(session).activate(actor, target.id)
    assert _user(session, "kasuwa").is_active is True
    assert ACTION_USER_ACTIVATED in _audit_actions(session)


def test_cannot_deactivate_self(session):
    actor = _admin(session)
    with pytest.raises(ValidationError):
        UserService(session).deactivate(actor, actor.user_id)


def test_cannot_deactivate_admin_account(session):
    actor = _admin(session)
    other_admin = make_user(session, username="admin2", role=ROLE_ADMIN)
    session.commit()
    with pytest.raises(ValidationError):
        UserService(session).deactivate(actor, other_admin.id)


# --- reset password ------------------------------------------------------ #


def test_reset_password(session):
    actor = _admin(session)
    target = make_user(session, username="kasuwa", role=ROLE_CASHIER, password="oldpw")
    session.commit()
    UserService(session).reset_password(actor, target.id, "newpass1")
    fresh = _user(session, "kasuwa")
    assert verify_password("newpass1", fresh.password_hash) is True
    assert verify_password("oldpw", fresh.password_hash) is False
    assert ACTION_PASSWORD_RESET in _audit_actions(session)


def test_reset_password_rejects_short(session):
    actor = _admin(session)
    target = make_user(session, username="kasuwa", role=ROLE_CASHIER)
    session.commit()
    with pytest.raises(ValidationError):
        UserService(session).reset_password(actor, target.id, "123")


def test_reset_password_cannot_target_admin(session):
    actor = _admin(session)
    other_admin = make_user(session, username="admin2", role=ROLE_ADMIN)
    session.commit()
    with pytest.raises(ValidationError):
        UserService(session).reset_password(actor, other_admin.id, "newpass1")


# --- authentication of inactive user ------------------------------------ #


def test_inactive_cashier_cannot_log_in(session):
    from app.domain.errors import AuthenticationError

    make_user(session, username="kasuwa", role=ROLE_CASHIER, password="secret6")
    target = _user(session, "kasuwa")
    target.is_active = False
    session.commit()
    with pytest.raises(AuthenticationError):
        AuthService(session, iterations=10_000).authenticate("kasuwa", "secret6")


def test_reset_password_hash_exists_after_reset(session):
    actor = _admin(session)
    target = make_user(session, username="kasuwa", role=ROLE_CASHIER, password="oldpw")
    session.commit()
    UserService(session).reset_password(actor, target.id, "freshp1")
    _user(session, "kasuwa")
    new_hash = UserService(session).repo.get_by_username("kasuwa").password_hash
    assert "freshp1" not in new_hash
    assert new_hash.startswith("pbkdf2_sha256$")


# --- historical references survived ------------------------------------- #


def test_deactivating_cashier_preserves_historical_sales(session):
    actor = _admin(session)
    cashier = make_user(session, username="kasuwa", role=ROLE_CASHIER)
    customer = make_customer(session)
    product = make_product(session, category=make_category(session))
    sale = make_sale(session, customer, cashier, items=[(product, 2)])
    session.commit()

    sale_id = sale.id
    UserService(session).deactivate(actor, cashier.id)
    session.commit()

    reloaded = session.get(Sale, sale_id)
    assert reloaded is not None
    assert reloaded.cashier_id == cashier.id
    assert reloaded.cashier is not None
    assert reloaded.cashier.is_active is False
