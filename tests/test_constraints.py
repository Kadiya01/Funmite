"""Constraint tests: invalid values and duplicate keys are rejected.

Each test runs on its own fresh session. After an expected
``IntegrityError`` the session is left in a rolled-back state, which is fine
because the fixture provides a new session per test.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

import pytest
from sqlalchemy.exc import IntegrityError

from app.data.models import (
    PAYMENT_POS,
    ROLE_ADMIN,
    Category,
    Exchange,
    Payment,
    Product,
    Sale,
    SaleItem,
    User,
)
from tests.factories import make_category, make_customer, make_product, make_sale, make_user


def test_invalid_role_rejected(session):
    session.add(
        User(username="owner", password_hash="h", role="OWNER", full_name="Owner")
    )
    with pytest.raises(IntegrityError):
        session.flush()


def test_invalid_payment_method_rejected(session):
    customer = make_customer(session)
    cashier = make_user(session)
    session.add(
        Sale(
            receipt_no="R-CASH",
            customer_id=customer.id,
            cashier_id=cashier.id,
            sale_date=datetime.now(),
            subtotal=Decimal("0"),
            total=Decimal("0"),
            payment_method="CASH",
            amount_paid=Decimal("0"),
        )
    )
    with pytest.raises(IntegrityError):
        session.flush()


def test_product_negative_quantity_rejected(session):
    category = make_category(session)
    session.add(
        Product(
            product_code="P-NEGQTY",
            name="Bad",
            category_id=category.id,
            cost_price=Decimal("1"),
            selling_price=Decimal("2"),
            quantity=-1,
            barcode="BC-NEGQTY",
        )
    )
    with pytest.raises(IntegrityError):
        session.flush()


def test_product_negative_price_rejected(session):
    category = make_category(session)
    session.add(
        Product(
            product_code="P-NEGPRICE",
            name="Bad",
            category_id=category.id,
            cost_price=Decimal("-5"),
            selling_price=Decimal("2"),
            quantity=1,
            barcode="BC-NEGPRICE",
        )
    )
    with pytest.raises(IntegrityError):
        session.flush()


def test_sale_item_nonpositive_quantity_rejected(session):
    customer = make_customer(session)
    cashier = make_user(session)
    category = make_category(session)
    product = make_product(session, category)
    sale = make_sale(session, customer, cashier)
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
    with pytest.raises(IntegrityError):
        session.flush()


def test_payment_nonpositive_amount_rejected(session):
    customer = make_customer(session)
    cashier = make_user(session)
    sale = make_sale(session, customer, cashier)
    session.add(
        Payment(
            sale_id=sale.id,
            payment_method=PAYMENT_POS,
            amount=Decimal("0"),
            payment_date=datetime.now(),
            recorded_by=cashier.id,
        )
    )
    with pytest.raises(IntegrityError):
        session.flush()


def test_invalid_exchange_difference_type_rejected(session):
    customer = make_customer(session)
    cashier = make_user(session)
    sale = make_sale(session, customer, cashier)
    session.add(
        Exchange(
            original_sale_id=sale.id,
            customer_id=customer.id,
            approved_by=cashier.id,
            exchange_date=datetime.now(),
            difference_amount=Decimal("0"),
            difference_type="FREE",
            status="COMPLETED",
        )
    )
    with pytest.raises(IntegrityError):
        session.flush()


def test_duplicate_username_rejected(session):
    make_user(session, username="admin01")
    session.add(
        User(username="admin01", password_hash="h", role=ROLE_ADMIN, full_name="Dupe")
    )
    with pytest.raises(IntegrityError):
        session.flush()


def test_duplicate_category_name_rejected(session):
    make_category(session, name="Fashion")
    session.add(Category(name="Fashion"))
    with pytest.raises(IntegrityError):
        session.flush()


def test_duplicate_barcode_rejected(session):
    category = make_category(session)
    first = make_product(session, category)
    session.add(
        Product(
            product_code="P-DUPBAR",
            name="Dupe",
            category_id=category.id,
            cost_price=Decimal("1"),
            selling_price=Decimal("2"),
            quantity=1,
            barcode=first.barcode,
        )
    )
    with pytest.raises(IntegrityError):
        session.flush()


def test_duplicate_receipt_no_rejected(session):
    customer = make_customer(session)
    cashier = make_user(session)
    first = make_sale(session, customer, cashier)
    session.add(
        Sale(
            receipt_no=first.receipt_no,
            customer_id=customer.id,
            cashier_id=cashier.id,
            sale_date=datetime.now(),
            subtotal=Decimal("0"),
            total=Decimal("0"),
            payment_method=PAYMENT_POS,
            amount_paid=Decimal("0"),
        )
    )
    with pytest.raises(IntegrityError):
        session.flush()


def test_foreign_key_violation_rejected(session):
    cashier = make_user(session)
    session.add(
        Sale(
            receipt_no="R-NOCUSTOMER",
            customer_id=999999,
            cashier_id=cashier.id,
            sale_date=datetime.now(),
            subtotal=Decimal("0"),
            total=Decimal("0"),
            payment_method=PAYMENT_POS,
            amount_paid=Decimal("0"),
        )
    )
    with pytest.raises(IntegrityError):
        session.flush()
