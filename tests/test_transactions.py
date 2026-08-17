"""Transaction tests: commit and rollback behave atomically."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.data.db import session_scope, transaction
from app.data.models import PAYMENT_POS, Category, Product, Sale, SaleItem, User
from tests.factories import make_category, make_customer, make_product, make_user


def _count(session, model) -> int:
    return int(session.scalar(select(func.count()).select_from(model)) or 0)


def test_session_scope_commits(session_factory):
    with session_scope(session_factory) as session:
        make_category(session)
    with session_factory() as check:
        assert _count(check, Category) == 1


def test_session_scope_rolls_back_on_error(session_factory):
    with pytest.raises(RuntimeError):
        with session_scope(session_factory) as session:
            make_category(session)
            raise RuntimeError("boom")
    with session_factory() as check:
        assert _count(check, Category) == 0


def test_transaction_helper_rolls_back(session_factory):
    with session_factory() as session:
        with pytest.raises(RuntimeError):
            with transaction(session):
                make_category(session)
                raise RuntimeError("boom")
    with session_factory() as check:
        assert _count(check, Category) == 0


def test_transaction_helper_commits(session_factory):
    with session_factory() as session:
        with transaction(session):
            make_category(session)
    with session_factory() as check:
        assert _count(check, Category) == 1


def test_multi_table_sale_rolls_back_completely(session_factory):
    """A failing sale leaves no partial rows and no stock change behind."""
    product_code = None
    with pytest.raises(IntegrityError):
        with session_scope(session_factory) as session:
            category = make_category(session)
            product = make_product(session, category, quantity=5)
            customer = make_customer(session)
            cashier = make_user(session)

            sale = Sale(
                receipt_no="R-ATOMIC",
                customer_id=customer.id,
                cashier_id=cashier.id,
                sale_date=datetime.now(),
                subtotal=Decimal("100"),
                total=Decimal("100"),
                payment_method=PAYMENT_POS,
                amount_paid=Decimal("100"),
            )
            session.add(sale)
            session.flush()

            product.quantity -= 1

            # This item violates the quantity > 0 check and must abort the sale.
            session.add(
                SaleItem(
                    sale_id=sale.id,
                    product_id=product.id,
                    quantity=0,
                    unit_price=Decimal("1"),
                    cost_price=Decimal("1"),
                    line_total=Decimal("0"),
                )
            )
            session.flush()

    with session_factory() as check:
        assert _count(check, Sale) == 0
        assert _count(check, SaleItem) == 0
        # The whole transaction rolled back: even the setup rows never persisted,
        # which proves the failed sale left nothing (including stock) behind.
        assert _count(check, Product) == 0


def test_foreign_key_rollback_keeps_database_clean(session_factory):
    with pytest.raises(IntegrityError):
        with session_scope(session_factory) as session:
            session.add(User(username="orphan", password_hash="h", role="CASHIER", full_name="X"))
            sale = Sale(
                receipt_no="R-FK",
                customer_id=12345,
                cashier_id=1,
                sale_date=datetime.now(),
                subtotal=Decimal("0"),
                total=Decimal("0"),
                payment_method=PAYMENT_POS,
                amount_paid=Decimal("0"),
            )
            session.add(sale)
            session.flush()
    with session_factory() as check:
        assert _count(check, Sale) == 0
