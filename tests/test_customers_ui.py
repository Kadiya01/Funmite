"""Customers page UI tests (Phase 03)."""

from __future__ import annotations

from app.data.db import session_scope
from app.data.models import ROLE_ADMIN
from app.domain.services.customer_service import CustomerService
from app.domain.session import CurrentUser
from app.ui.customers import CustomersPage
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


def _create_customer(session_factory, user: CurrentUser, **kwargs) -> None:
    with session_scope(session_factory) as session:
        CustomerService(session).create(
            user,
            name=kwargs.get("name", "Customer"),
            phone=kwargs.get("phone"),
            address=kwargs.get("address"),
        )


def test_page_lists_customers(qtbot, session_factory, session):
    current_user = _admin_user(session)
    _create_customer(session_factory, current_user, name="Amina", phone="08031234567")
    _create_customer(session_factory, current_user, name="Ali", phone="08039876543")

    page = CustomersPage(session_factory, current_user)
    qtbot.addWidget(page)

    assert page.table.rowCount() == 2
    assert page.count_label.text() == "2 customer(s)"


def test_search_filters_customers(qtbot, session_factory, session):
    current_user = _admin_user(session)
    _create_customer(session_factory, current_user, name="Amina", phone="08031234567")
    _create_customer(session_factory, current_user, name="Ali", phone="08039876543")

    page = CustomersPage(session_factory, current_user)
    qtbot.addWidget(page)

    page.search_input.setText("amina")
    assert page.table.rowCount() == 1

    page.search_input.setText("08039876543")
    assert page.table.rowCount() == 1


def test_create_handler_registers_customer(session_factory, session):
    current_user = _admin_user(session)
    page = CustomersPage(session_factory, current_user)
    page._create_handler()(
        {
            "name": "New Customer",
            "phone": "08031111111",
            "address": "Kano",
            "customer_code": "",
        }
    )
    with session_factory() as check:
        from app.data.repositories.customer_repository import CustomerRepository

        customers = CustomerRepository(check).search("New Customer")
        assert len(customers) == 1
        assert customers[0].customer_code.startswith("CUS-")
