"""Sale service tests (Phase 05).

Covers the complete atomic sale: customer requirement, cart validation,
pricing, approved discount behavior, POS/Transfer-only payments (cash/credit
rejected), sale items, payment records, stock deduction through the shared
inventory writer, inventory movement logging, receipt numbering, duplicate
handling, insufficient-stock rollback, authorization and offline operation.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.data.db import session_scope
from app.data.models import (
    DISCOUNT_FIXED,
    DISCOUNT_PERCENT,
    PAYMENT_POS,
    PAYMENT_TRANSFER,
    InventoryLog,
    Payment,
    ROLE_ADMIN,
    ROLE_CASHIER,
    Sale,
    SaleItem,
)
from app.domain.errors import AuthorizationError, NotFoundError, ValidationError
from app.domain.services.inventory_service import REFERENCE_SALE
from app.domain.services.sale_service import RECEIPT_PREFIX, SALE_ITEM_REASON, SaleService
from app.domain.session import CurrentUser
from tests.factories import make_category, make_customer, make_product, make_user


def _admin(session):
    return make_user(session, role=ROLE_ADMIN)


def _cashier(session):
    return make_user(session, role=ROLE_CASHIER)


def _product(session, *, name="Ladies Gown", quantity=10, selling_price="35000", cost_price="20000"):
    return make_product(
        session,
        make_category(session),
        name=name,
        quantity=quantity,
        selling_price=Decimal(selling_price),
        cost_price=Decimal(cost_price),
    )


def _customer(session, name="Amina Yusuf"):
    return make_customer(session, name=name)


def _items(*entries):
    return [{"product_id": product_id, "quantity": quantity} for product_id, quantity in entries]


def _count(session, model) -> int:
    return int(session.scalar(select(func.count()).select_from(model)) or 0)


def _complete(session_factory, user, customer, items, payment_method=PAYMENT_POS, **kwargs):
    with session_scope(session_factory) as session:
        return SaleService(session).complete_sale(
            user,
            customer_id=customer.id,
            items=items,
            payment_method=payment_method,
            **kwargs,
        )


def _sale_items(session_factory, sale_id: int) -> list[SaleItem]:
    with session_factory() as session:
        return session.scalars(
            select(SaleItem).where(SaleItem.sale_id == sale_id).order_by(SaleItem.id)
        ).all()


def _payments(session_factory, sale_id: int) -> list[Payment]:
    with session_factory() as session:
        return session.scalars(
            select(Payment).where(Payment.sale_id == sale_id).order_by(Payment.id)
        ).all()


# --- customer requirement -------------------------------------------------- #


def test_customer_required_for_every_sale(session_factory, session):
    admin = _admin(session)
    product = _product(session)
    session.commit()

    with pytest.raises(NotFoundError):
        with session_scope(session_factory) as session:
            SaleService(session).complete_sale(
                admin, customer_id=None, items=_items((product.id, 1)), payment_method=PAYMENT_POS
            )


def test_unknown_customer_rejected(session_factory, session):
    admin = _admin(session)
    product = _product(session)
    session.commit()

    with pytest.raises(NotFoundError, match="Customer not found"):
        with session_scope(session_factory) as session:
            SaleService(session).complete_sale(
                admin, customer_id=99999, items=_items((product.id, 1)), payment_method=PAYMENT_POS
            )


# --- cart validation ------------------------------------------------------- #


def test_sale_requires_at_least_one_item(session_factory, session):
    admin = _admin(session)
    customer = _customer(session)
    session.commit()

    with pytest.raises(ValidationError, match="at least one item"):
        with session_scope(session_factory) as session:
            SaleService(session).complete_sale(
                admin, customer_id=customer.id, items=[], payment_method=PAYMENT_POS
            )


@pytest.mark.parametrize("quantity", [0, -1, "0", "-3", "1.5", "abc", None])
def test_quantity_must_be_a_positive_whole_number(session_factory, session, quantity):
    admin = _admin(session)
    customer = _customer(session)
    product = _product(session)
    session.commit()

    with pytest.raises(ValidationError):
        with session_scope(session_factory) as session:
            SaleService(session).complete_sale(
                admin,
                customer_id=customer.id,
                items=[{"product_id": product.id, "quantity": quantity}],
                payment_method=PAYMENT_POS,
            )


def test_missing_product_rejected(session_factory, session):
    admin = _admin(session)
    customer = _customer(session)
    session.commit()

    with pytest.raises(NotFoundError, match="Product not found"):
        with session_scope(session_factory) as session:
            SaleService(session).complete_sale(
                admin, customer_id=customer.id, items=_items((99999, 1)), payment_method=PAYMENT_POS
            )


def test_inactive_product_rejected(session_factory, session):
    admin = _admin(session)
    customer = _customer(session)
    product = _product(session, name="Old Gown")
    product.is_active = False
    session.commit()

    with pytest.raises(ValidationError, match="not active"):
        with session_scope(session_factory) as session:
            SaleService(session).complete_sale(
                admin, customer_id=customer.id, items=_items((product.id, 1)), payment_method=PAYMENT_POS
            )


def test_duplicate_cart_line_rejected(session_factory, session):
    admin = _admin(session)
    customer = _customer(session)
    product = _product(session)
    session.commit()

    with pytest.raises(ValidationError, match="more than once"):
        with session_scope(session_factory) as session:
            SaleService(session).complete_sale(
                admin,
                customer_id=customer.id,
                items=_items((product.id, 1), (product.id, 2)),
                payment_method=PAYMENT_POS,
            )


# --- pricing --------------------------------------------------------------- #


def test_price_calculation_and_sale_headers(session_factory, session):
    admin = _admin(session)
    customer = _customer(session)
    gown = _product(session, name="Ladies Gown", selling_price="35000", cost_price="20000")
    top = _product(session, name="Top", selling_price="10000", cost_price="5000")
    session.commit()

    sale = _complete(
        session_factory,
        admin,
        customer,
        _items((gown.id, 1), (top.id, 2)),
        payment_method=PAYMENT_POS,
    )
    sale_id = sale.id

    with session_factory() as check:
        header = check.get(Sale, sale_id)
        assert header is not None
        assert header.receipt_no.startswith(f"{RECEIPT_PREFIX}-{datetime.now():%Y%m%d}-")
        assert header.customer_id == customer.id
        assert header.cashier_id == admin.id
        assert header.payment_method == PAYMENT_POS
        assert header.subtotal == Decimal("55000")
        assert header.discount_type is None
        assert header.discount_value == Decimal("0")
        assert header.discount_amount == Decimal("0")
        assert header.total == Decimal("55000")
        assert header.amount_paid == Decimal("55000")

    lines = _sale_items(session_factory, sale_id)
    assert len(lines) == 2
    by_name = {item.product_id: item for item in lines}
    gown_line = by_name[gown.id]
    assert gown_line.quantity == 1
    assert gown_line.unit_price == Decimal("35000")
    assert gown_line.cost_price == Decimal("20000")
    assert gown_line.line_total == Decimal("35000")
    top_line = by_name[top.id]
    assert top_line.quantity == 2
    assert top_line.line_total == Decimal("20000")


# --- discount (approved behavior only) ------------------------------------- #


def test_admin_percent_discount(session_factory, session):
    admin = _admin(session)
    customer = _customer(session)
    product = _product(session, selling_price="10000")
    session.commit()

    sale = _complete(
        session_factory,
        admin,
        customer,
        _items((product.id, 2)),
        payment_method=PAYMENT_POS,
        discount={"type": DISCOUNT_PERCENT, "value": 10},
    )
    assert sale.discount_type == DISCOUNT_PERCENT
    assert sale.discount_value == Decimal("10")
    assert sale.discount_amount == Decimal("2000")
    assert sale.total == Decimal("18000")
    assert sale.amount_paid == Decimal("18000")


def test_admin_fixed_discount(session_factory, session):
    admin = _admin(session)
    customer = _customer(session)
    product = _product(session, selling_price="10000")
    session.commit()

    sale = _complete(
        session_factory,
        admin,
        customer,
        _items((product.id, 2)),
        payment_method=PAYMENT_TRANSFER,
        discount={"type": DISCOUNT_FIXED, "value": 5000},
    )
    assert sale.discount_amount == Decimal("5000")
    assert sale.total == Decimal("15000")
    assert sale.amount_paid == Decimal("15000")


def test_discount_cannot_make_total_negative(session_factory, session):
    admin = _admin(session)
    customer = _customer(session)
    product = _product(session, selling_price="10000")
    session.commit()

    with pytest.raises(ValidationError, match="more than the sale total"):
        _complete(
            session_factory,
            admin,
            customer,
            _items((product.id, 1)),
            payment_method=PAYMENT_POS,
            discount={"type": DISCOUNT_FIXED, "value": 15000},
        )


def test_percent_discount_above_100_makes_total_negative(session_factory, session):
    admin = _admin(session)
    customer = _customer(session)
    product = _product(session, selling_price="10000")
    session.commit()

    with pytest.raises(ValidationError, match="more than the sale total"):
        _complete(
            session_factory,
            admin,
            customer,
            _items((product.id, 1)),
            payment_method=PAYMENT_POS,
            discount={"type": DISCOUNT_PERCENT, "value": 150},
        )


def test_invalid_discount_type_rejected(session_factory, session):
    admin = _admin(session)
    customer = _customer(session)
    product = _product(session)
    session.commit()

    with pytest.raises(ValidationError, match="not supported"):
        _complete(
            session_factory,
            admin,
            customer,
            _items((product.id, 1)),
            payment_method=PAYMENT_POS,
            discount={"type": "BOGO", "value": 5},
        )


def test_cashier_discount_blocked(session_factory, session):
    cashier = _cashier(session)
    customer = _customer(session)
    product = _product(session)
    session.commit()

    with pytest.raises(AuthorizationError):
        _complete(
            session_factory,
            cashier,
            customer,
            _items((product.id, 1)),
            payment_method=PAYMENT_POS,
            discount={"type": DISCOUNT_PERCENT, "value": 10},
        )


# --- payments -------------------------------------------------------------- #


def test_bank_pos_payment_recorded(session_factory, session):
    admin = _admin(session)
    customer = _customer(session)
    product = _product(session, selling_price="2500")
    session.commit()

    sale = _complete(session_factory, admin, customer, _items((product.id, 2)), payment_method=PAYMENT_POS)
    payments = _payments(session_factory, sale.id)
    assert len(payments) == 1
    payment = payments[0]
    assert payment.payment_method == PAYMENT_POS
    assert payment.amount == Decimal("5000")
    assert payment.sale_id == sale.id
    assert payment.recorded_by == admin.id
    assert payment.reference is None


def test_bank_transfer_payment_recorded_with_reference(session_factory, session):
    admin = _admin(session)
    customer = _customer(session)
    product = _product(session)
    session.commit()

    sale = _complete(
        session_factory,
        admin,
        customer,
        _items((product.id, 1)),
        payment_method=PAYMENT_TRANSFER,
        reference="TRF-12345",
    )
    payments = _payments(session_factory, sale.id)
    assert len(payments) == 1
    assert payments[0].payment_method == PAYMENT_TRANSFER
    assert payments[0].reference == "TRF-12345"


@pytest.mark.parametrize("method", ["CASH", "CREDIT", "cheque", "POS CASH", "", None, "  cash  "])
def test_cash_credit_and_unsupported_payments_rejected(session_factory, session, method):
    admin = _admin(session)
    customer = _customer(session)
    product = _product(session)
    session.commit()

    with pytest.raises(ValidationError, match="not supported"):
        with session_scope(session_factory) as session:
            SaleService(session).complete_sale(
                admin, customer_id=customer.id, items=_items((product.id, 1)), payment_method=method
            )


# --- stock deduction + inventory movement ---------------------------------- #


def test_stock_deducted_and_inventory_movement_logged(session_factory, session):
    admin = _admin(session)
    customer = _customer(session)
    product = _product(session, quantity=5)
    session.commit()

    sale = _complete(session_factory, admin, customer, _items((product.id, 2)), payment_method=PAYMENT_POS)

    with session_factory() as check:
        fresh = check.get(type(product), product.id)
        assert fresh.quantity == 3

        logs = check.scalars(
            select(InventoryLog).where(InventoryLog.product_id == product.id).order_by(InventoryLog.id)
        ).all()
        assert len(logs) == 1
        movement = logs[0]
        assert movement.change_quantity == -2
        assert movement.previous_quantity == 5
        assert movement.new_quantity == 3
        assert movement.reason == SALE_ITEM_REASON
        assert movement.reference_type == REFERENCE_SALE
        assert movement.reference_id == sale.id
        assert movement.user_id == admin.id


def test_sale_by_cashier_writes_cashier_on_every_record(session_factory, session):
    cashier = _cashier(session)
    customer = _customer(session)
    product = _product(session, quantity=4)
    session.commit()

    sale = _complete(session_factory, cashier, customer, _items((product.id, 1)), payment_method=PAYMENT_POS)

    with session_factory() as check:
        header = check.get(Sale, sale.id)
        assert header.cashier_id == cashier.id
        payments = _payments(session_factory, sale.id)
        assert payments[0].recorded_by == cashier.id
        log = check.scalar(select(InventoryLog).where(InventoryLog.reference_id == sale.id))
        assert log.user_id == cashier.id


def test_sale_completes_with_current_user_snapshot(session_factory, session):
    admin = _admin(session)
    customer = _customer(session)
    product = _product(session, quantity=4)
    session.commit()
    current = CurrentUser(
        user_id=admin.id, username=admin.username, full_name=admin.full_name, role=ROLE_ADMIN
    )

    sale = _complete(session_factory, current, customer, _items((product.id, 1)), payment_method=PAYMENT_POS)

    with session_factory() as check:
        header = check.get(Sale, sale.id)
        assert header.cashier_id == admin.id
        assert check.scalar(select(InventoryLog).where(InventoryLog.reference_id == sale.id)).user_id == admin.id


# --- receipt numbers ------------------------------------------------------- #


def test_receipt_numbers_are_unique_and_sequential(session_factory, session):
    admin = _admin(session)
    customer = _customer(session)
    product = _product(session, quantity=10)
    session.commit()

    first = _complete(session_factory, admin, customer, _items((product.id, 1)), payment_method=PAYMENT_POS)
    second = _complete(session_factory, admin, customer, _items((product.id, 1)), payment_method=PAYMENT_POS)

    assert first.receipt_no != second.receipt_no
    assert int(second.receipt_no.rsplit("-", 1)[1]) == int(first.receipt_no.rsplit("-", 1)[1]) + 1


def test_receipt_number_uses_sale_date_prefix(session_factory, session):
    admin = _admin(session)
    customer = _customer(session)
    product = _product(session)
    session.commit()
    yesterday = datetime.now() - timedelta(days=1)

    with session_scope(session_factory) as session:
        sale = SaleService(session).complete_sale(
            admin,
            customer_id=customer.id,
            items=_items((product.id, 1)),
            payment_method=PAYMENT_POS,
            sale_date=yesterday,
        )
        assert sale.receipt_no == f"{RECEIPT_PREFIX}-{yesterday:%Y%m%d}-001"


def test_duplicate_receipt_number_rolls_back_entire_sale(session_factory, session, monkeypatch):
    admin = _admin(session)
    customer = _customer(session)
    product = _product(session, quantity=10)
    session.commit()

    first = _complete(session_factory, admin, customer, _items((product.id, 1)), payment_method=PAYMENT_POS)

    def _same(*_args, **_kwargs):
        return first.receipt_no

    with pytest.raises(IntegrityError):
        with session_scope(session_factory) as session:
            service = SaleService(session)
            monkeypatch.setattr(service, "next_receipt_no", _same)
            service.complete_sale(
                admin, customer_id=customer.id, items=_items((product.id, 1)), payment_method=PAYMENT_POS
            )

    with session_factory() as check:
        assert _count(check, Sale) == 1
        assert _count(check, Payment) == 1
        assert _count(check, InventoryLog) == 1
        assert check.get(type(product), product.id).quantity == 9


# --- atomic rollback / insufficient stock ---------------------------------- #


def test_insufficient_stock_rejected_and_everything_rolled_back(session_factory, session):
    admin = _admin(session)
    customer = _customer(session)
    first_product = _product(session, name="Gown", quantity=5)
    scarce = _product(session, name="Scarce Top", quantity=1)
    session.commit()

    with pytest.raises(ValidationError, match="Insufficient stock.*Scarce Top"):
        _complete(
            session_factory,
            admin,
            customer,
            _items((first_product.id, 2), (scarce.id, 2)),
            payment_method=PAYMENT_POS,
        )

    with session_factory() as check:
        assert _count(check, Sale) == 0
        assert _count(check, SaleItem) == 0
        assert _count(check, Payment) == 0
        assert _count(check, InventoryLog) == 0
        assert check.get(type(first_product), first_product.id).quantity == 5
        assert check.get(type(scarce), scarce.id).quantity == 1


def test_no_payment_row_when_discount_covers_entire_total(session_factory, session):
    admin = _admin(session)
    customer = _customer(session)
    product = _product(session, selling_price="10000")
    session.commit()

    sale = _complete(
        session_factory,
        admin,
        customer,
        _items((product.id, 1)),
        payment_method=PAYMENT_POS,
        discount={"type": DISCOUNT_FIXED, "value": 10000},
    )
    assert sale.total == Decimal("0")
    assert sale.amount_paid == Decimal("0")
    assert _payments(session_factory, sale.id) == []
    with session_factory() as check:
        assert check.get(type(product), product.id).quantity == 9


# --- authorization --------------------------------------------------------- #


def test_cashier_can_complete_a_sale(session_factory, session):
    cashier = _cashier(session)
    customer = _customer(session)
    product = _product(session, quantity=3)
    session.commit()

    sale = _complete(session_factory, cashier, customer, _items((product.id, 1)), payment_method=PAYMENT_POS)
    assert sale.total == Decimal("35000")


def test_unauthenticated_user_cannot_sell(session_factory, session):
    customer = _customer(session)
    product = _product(session)
    session.commit()

    with pytest.raises(AuthorizationError):
        with session_scope(session_factory) as session:
            SaleService(session).complete_sale(
                None, customer_id=customer.id, items=_items((product.id, 1)), payment_method=PAYMENT_POS
            )


# --- offline operation ----------------------------------------------------- #


def test_complete_sale_works_fully_offline(session_factory, session):
    admin = _admin(session)
    customer = _customer(session)
    product = _product(session, quantity=2)
    session.commit()

    sale = _complete(session_factory, admin, customer, _items((product.id, 2)), payment_method=PAYMENT_TRANSFER)

    with session_factory() as check:
        header = check.get(Sale, sale.id)
        assert header.total == Decimal("70000")
        assert check.get(type(product), product.id).quantity == 0
        assert _count(check, Sale) == 1
        assert _count(check, SaleItem) == 1
        assert _count(check, Payment) == 1
        assert _count(check, InventoryLog) == 1
