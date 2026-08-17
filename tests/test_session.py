"""Current-user / session handling tests."""

from __future__ import annotations

from app.data.models import ROLE_ADMIN, ROLE_CASHIER, User
from app.domain.permissions import CAP_DISCOUNT, CAP_MAKE_SALE
from app.domain.session import AuthSession, CurrentUser


def make_user(role: str, *, is_active: bool = True) -> User:
    return User(
        id=1,
        username="jamilu",
        password_hash="x",
        role=role,
        full_name="Jamilu",
        is_active=is_active,
    )


def test_auth_session_starts_and_exposes_current_user():
    session = AuthSession()
    assert session.is_authenticated is False
    assert session.user is None

    user = session.start(make_user(ROLE_ADMIN))
    assert session.is_authenticated is True
    assert session.user is user
    assert user.user_id == 1
    assert user.role == ROLE_ADMIN
    assert user.display_label == "Admin: Jamilu"


def test_auth_session_end_clears_user():
    session = AuthSession()
    session.start(make_user(ROLE_CASHIER))
    ended = session.end()
    assert ended is not None and ended.role == ROLE_CASHIER
    assert session.user is None
    assert session.is_authenticated is False


def test_current_user_can_checks_permissions():
    admin = CurrentUser(user_id=1, username="a", full_name="A", role=ROLE_ADMIN)
    cashier = CurrentUser(user_id=2, username="c", full_name="C", role=ROLE_CASHIER)
    assert admin.can(CAP_DISCOUNT) is True
    assert cashier.can(CAP_DISCOUNT) is False
    assert cashier.can(CAP_MAKE_SALE) is True


def test_display_label_falls_back_to_username():
    user = CurrentUser(user_id=1, username="ali", full_name="", role=ROLE_CASHIER)
    assert user.display_label == "Cashier: ali"
