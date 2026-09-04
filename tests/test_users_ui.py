"""Users page (F4) UI tests."""

from __future__ import annotations

from PySide6.QtCore import Qt

from app.data.db import session_scope
from app.data.models import ROLE_ADMIN, ROLE_CASHIER
from app.data.repositories.user_repository import UserRepository
from app.domain.services.user_service import UserService
from app.domain.session import CurrentUser
from app.ui.users import UsersPage
from tests.factories import make_user


def _admin_user(session) -> CurrentUser:
    user = make_user(session, username="admin", role=ROLE_ADMIN)
    session.commit()
    return CurrentUser(
        user_id=user.id,
        username=user.username,
        full_name=user.full_name,
        role=user.role,
    )


def _make_cashier(session_factory, current_user, **kwargs):
    with session_scope(session_factory) as session:
        user = UserService(session).create(
            current_user,
            username=kwargs.get("username", "kasuwa"),
            full_name=kwargs.get("full_name", "Amina Bello"),
            password="secret6",
        )
        return user.id


def test_page_lists_cashiers(qtbot, session_factory, session):
    current_user = _admin_user(session)

    with session_scope(session_factory) as s:
        UserService(s).create(
            current_user, username="kasuwa", full_name="Amina", password="secret6"
        )
        UserService(s).create(
            current_user, username="bala", full_name="Bala", password="secret6"
        )

    page = UsersPage(session_factory, current_user)
    qtbot.addWidget(page)

    assert page.table.rowCount() == 3  # admin + 2 cashiers
    assert page.count_label.text() == "3 user(s) — 3 active"


def test_search_filters_users(qtbot, session_factory, session):
    current_user = _admin_user(session)

    with session_scope(session_factory) as s:
        UserService(s).create(
            current_user, username="kasuwa", full_name="Amina", password="secret6"
        )
        UserService(s).create(
            current_user, username="bala", full_name="Bala", password="secret6"
        )

    page = UsersPage(session_factory, current_user)
    qtbot.addWidget(page)

    page.search_input.setText("amina")
    assert page.table.rowCount() == 1

    page.search_input.setText("kasuwa")
    assert page.table.rowCount() == 1


def test_create_handler_registers_cashier(session_factory, session):
    current_user = _admin_user(session)
    page = UsersPage(session_factory, current_user)
    page._create_handler()(
        {"username": "newcash", "full_name": "New Cashier", "password": "secret6"}
    )
    with session_factory() as check:
        users = UserRepository(check).search("newcash")
        assert len(users) == 1
        assert users[0].role == ROLE_CASHIER


def test_create_handler_does_not_allow_admin_role(qtbot, session_factory, session):
    current_user = _admin_user(session)
    page = UsersPage(session_factory, current_user)
    qtbot.addWidget(page)

    # The form has no role selector; the service always creates a Cashier.
    page._create_handler()(
        {"username": "casher2", "full_name": "Casher", "password": "secret6"}
    )
    with session_factory() as check:
        created = UserRepository(check).get_by_username("casher2")
        assert created.role == ROLE_CASHIER


def test_edit_handler_updates_full_name(session_factory, session):
    current_user = _admin_user(session)
    user_id = _make_cashier(session_factory, current_user, username="kasuwa", full_name="Old Name")
    page = UsersPage(session_factory, current_user)
    page._update_handler(user_id)({"full_name": "New Name", "password": "", "username": "kasuwa"})
    with session_factory() as check:
        assert UserRepository(check).get(user_id).full_name == "New Name"


def test_deactivate_handler_marks_inactive(qtbot, session_factory, session):
    current_user = _admin_user(session)
    user_id = _make_cashier(session_factory, current_user, username="kasuwa")
    page = UsersPage(session_factory, current_user)
    qtbot.addWidget(page)
    page.refresh()

    page.table.setCurrentCell(0, 0)
    page._deactivate_handler()(user_id)
    with session_factory() as check:
        assert UserRepository(check).get(user_id).is_active is False


def test_reset_password_handler(qtbot, session_factory, session):
    from app.security.passwords import verify_password

    current_user = _admin_user(session)
    user_id = _make_cashier(session_factory, current_user, username="kasuwa", full_name="Amina")
    page = UsersPage(session_factory, current_user)
    qtbot.addWidget(page)

    page._reset_password_handler()(user_id, "newpass1")
    with session_factory() as check:
        user = UserRepository(check).get(user_id)
        assert verify_password("newpass1", user.password_hash) is True
