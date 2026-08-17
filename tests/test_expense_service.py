"""Expense service tests (Phase 07)."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

import pytest

from app.data.db import session_scope
from app.data.models import Expense
from app.domain.errors import AuthorizationError, NotFoundError, ValidationError
from app.domain.services.expense_service import ExpenseService
from tests.factories import make_user


# ── helpers ──────────────────────────────────────────────────────────────── #

def _svc(session):
    return ExpenseService(session)


# ── authorization ────────────────────────────────────────────────────────── #

class TestAuthorization:
    def test_admin_can_create(self, session, session_factory):
        admin = make_user(session)
        session.commit()
        with session_factory() as s:
            expense = _svc(s).create_expense(
                admin, category="Transport", amount=Decimal("5000"),
            )
            assert expense.id is not None

    def test_cashier_cannot_create(self, session, session_factory):
        cashier = make_user(session, role="CASHIER")
        session.commit()
        with session_factory() as s:
            with pytest.raises(AuthorizationError):
                _svc(s).create_expense(
                    cashier, category="Transport", amount=Decimal("5000"),
                )

    def test_cashier_cannot_list(self, session, session_factory):
        cashier = make_user(session, role="CASHIER")
        session.commit()
        with session_factory() as s:
            with pytest.raises(AuthorizationError):
                _svc(s).list_expenses(cashier)

    def test_unauthenticated_cannot_create(self, session, session_factory):
        with session_factory() as s:
            with pytest.raises(AuthorizationError):
                _svc(s).create_expense(
                    None, category="Transport", amount=Decimal("5000"),
                )


# ── create expense ───────────────────────────────────────────────────────── #

class TestCreateExpense:
    def test_create_with_all_fields(self, session, session_factory):
        admin = make_user(session)
        session.commit()
        dt = datetime(2026, 3, 15, 10, 0)
        with session_factory() as s:
            expense = _svc(s).create_expense(
                admin,
                category="Transport",
                amount=Decimal("5000"),
                description="Fuel for delivery",
                expense_date=dt,
            )
            assert expense.category == "Transport"
            assert expense.amount == Decimal("5000")
            assert expense.description == "Fuel for delivery"
            assert expense.expense_date == dt

    def test_create_minimal(self, session, session_factory):
        admin = make_user(session)
        session.commit()
        with session_factory() as s:
            expense = _svc(s).create_expense(
                admin, category="Rent", amount=Decimal("50000"),
            )
            assert expense.category == "Rent"
            assert expense.description is None

    def test_empty_category_rejected(self, session, session_factory):
        admin = make_user(session)
        session.commit()
        with session_factory() as s:
            with pytest.raises(ValidationError, match="category"):
                _svc(s).create_expense(admin, category="", amount=Decimal("5000"))

    def test_zero_amount_rejected(self, session, session_factory):
        admin = make_user(session)
        session.commit()
        with session_factory() as s:
            with pytest.raises(ValidationError, match="amount"):
                _svc(s).create_expense(admin, category="Test", amount=Decimal("0"))

    def test_negative_amount_rejected(self, session, session_factory):
        admin = make_user(session)
        session.commit()
        with session_factory() as s:
            with pytest.raises(ValidationError, match="amount"):
                _svc(s).create_expense(admin, category="Test", amount=Decimal("-100"))

    def test_created_by_recorded(self, session, session_factory):
        admin = make_user(session)
        session.commit()
        with session_scope(session_factory) as s:
            expense = _svc(s).create_expense(
                admin, category="Test", amount=Decimal("1000"),
            )
            assert expense.created_by == admin.id


# ── update expense ───────────────────────────────────────────────────────── #

class TestUpdateExpense:
    def test_update_category(self, session, session_factory):
        admin = make_user(session)
        session.commit()
        with session_factory() as s:
            expense = _svc(s).create_expense(
                admin, category="Old", amount=Decimal("1000"),
            )
            updated = _svc(s).update_expense(
                admin, expense.id, category="New",
            )
            assert updated.category == "New"

    def test_update_amount(self, session, session_factory):
        admin = make_user(session)
        session.commit()
        with session_factory() as s:
            expense = _svc(s).create_expense(
                admin, category="Test", amount=Decimal("1000"),
            )
            updated = _svc(s).update_expense(
                admin, expense.id, amount=Decimal("2000"),
            )
            assert updated.amount == Decimal("2000")

    def test_update_not_found(self, session, session_factory):
        admin = make_user(session)
        session.commit()
        with session_factory() as s:
            with pytest.raises(NotFoundError):
                _svc(s).update_expense(admin, 99999, category="X")

    def test_cannot_clear_category(self, session, session_factory):
        admin = make_user(session)
        session.commit()
        with session_factory() as s:
            expense = _svc(s).create_expense(
                admin, category="Test", amount=Decimal("1000"),
            )
            with pytest.raises(ValidationError, match="category"):
                _svc(s).update_expense(admin, expense.id, category="")


# ── list / get ───────────────────────────────────────────────────────────── #

class TestListExpenses:
    def test_list_empty(self, session, session_factory):
        admin = make_user(session)
        session.commit()
        with session_factory() as s:
            assert _svc(s).list_expenses(admin) == []

    def test_list_returns_created(self, session, session_factory):
        admin = make_user(session)
        session.commit()
        with session_factory() as s:
            _svc(s).create_expense(admin, category="A", amount=Decimal("1000"))
            _svc(s).create_expense(admin, category="B", amount=Decimal("2000"))
            result = _svc(s).list_expenses(admin)
            assert len(result) == 2

    def test_filter_by_category(self, session, session_factory):
        admin = make_user(session)
        session.commit()
        with session_factory() as s:
            _svc(s).create_expense(admin, category="Transport", amount=Decimal("1000"))
            _svc(s).create_expense(admin, category="Rent", amount=Decimal("5000"))
            result = _svc(s).list_expenses(admin, category="Transport")
            assert len(result) == 1
            assert result[0].category == "Transport"

    def test_get_expense(self, session, session_factory):
        admin = make_user(session)
        session.commit()
        with session_factory() as s:
            expense = _svc(s).create_expense(
                admin, category="Test", amount=Decimal("1000"),
            )
            got = _svc(s).get_expense(admin, expense.id)
            assert got.category == "Test"

    def test_get_not_found(self, session, session_factory):
        admin = make_user(session)
        session.commit()
        with session_factory() as s:
            with pytest.raises(NotFoundError):
                _svc(s).get_expense(admin, 99999)
