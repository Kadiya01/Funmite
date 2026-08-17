"""Exchange service tests (Phase 06).

Covers the approved two-day Admin exchange workflow: the exchange window,
Admin-only authorization, original-receipt validation, returned/replacement item
validation, price-difference calculation under the no-cash rule, atomic stock
restore + deduction through the shared inventory writer, audit/history,
original-sale preservation, rollback on insufficient replacement stock,
duplicate/over-exchange protection, multi-item exchanges and offline operation.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.data.db import session_scope
from app.data.models import (
    DIFFERENCE_CUSTOMER_PAYS,
    DIFFERENCE_NONE,
    EXCHANGE_COMPLETED,
    InventoryLog,
    PAYMENT_POS,
    PAYMENT_TRANSFER,
    ROLE_ADMIN,
    ROLE_CASHIER,
    Exchange,
    ExchangeItem,
    Payment,
    Sale,
)
from app.domain.errors import AuthorizationError, NotFoundError, ValidationError
from app.domain.services.exchange_service import (
    EXCHANGE_REPLACEMENT_REASON,
    EXCHANGE_RETURN_REASON,
    EXCHANGE_WINDOW_DAYS,
    ExchangeService,
)
from app.domain.services.inventory_service import REFERENCE_EXCHANGE
from app.domain.session import CurrentUser
from tests.factories import (
    make_category,
    make_customer,
    make_product,
    make_recent_sale,
    make_user,
)


def _admin(session):
    return make_user(session, role=ROLE_ADMIN)


def _cashier(session):
    return make_user(session, role=ROLE_CASHIER)


def _product(
    session,
    *,
    name="Ladies Gown",
    selling_price="35000",
    cost_price="20000",
    quantity=10,
):
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


def _lines(*entries):
    return [
        {
            "original_product_id": original_product_id,
            "original_quantity": original_quantity,
            "replacement_product_id": replacement_product_id,
            "replacement_quantity": replacement_quantity,
        }
        for original_product_id, original_quantity, replacement_product_id, replacement_quantity in entries
    ]


def _count(session, model) -> int:
    return int(session.scalar(select(func.count()).select_from(model)) or 0)


def _exchange(session_factory, user, receipt_no, items, payment_method=PAYMENT_POS, **kwargs):
    with session_scope(session_factory) as session:
        return ExchangeService(session).complete_exchange(
            user,
            receipt_no=receipt_no,
            items=items,
            payment_method=payment_method,
            **kwargs,
        )


def _movements(session, exchange_id: int) -> list[InventoryLog]:
    return list(
        session.scalars(
            select(InventoryLog)
            .where(InventoryLog.reference_type == REFERENCE_EXCHANGE)
            .where(InventoryLog.reference_id == exchange_id)
            .order_by(InventoryLog.id)
        )
    )


# --- authorization ---------------------------------------------------------- #


def test_admin_can_complete_an_exchange(session_factory, session):
    admin = _admin(session)
    customer = _customer(session)
    gown = _product(session, name="Gown")
    ankara = _product(session, name="Ankara", selling_price="40000")
    sale = make_recent_sale(session, customer, admin, days_old=1, items=[(gown, 1)])
    session.commit()

    exchange = _exchange(
        session_factory, admin, sale.receipt_no, _lines((gown.id, 1, ankara.id, 1))
    )
    assert exchange.status == EXCHANGE_COMPLETED
    assert exchange.approved_by == admin.id
    assert exchange.original_sale_id == sale.id
    assert exchange.customer_id == customer.id


def test_cashier_cannot_exchange(session_factory, session):
    cashier = _cashier(session)
    customer = _customer(session)
    gown = _product(session, name="Gown")
    ankara = _product(session, name="Ankara", selling_price="40000")
    sale = make_recent_sale(session, customer, cashier, days_old=1, items=[(gown, 1)])
    session.commit()

    with pytest.raises(AuthorizationError):
        _exchange(session_factory, cashier, sale.receipt_no, _lines((gown.id, 1, ankara.id, 1)))


def test_unauthenticated_user_cannot_exchange(session_factory, session):
    customer = _customer(session)
    admin = _admin(session)
    gown = _product(session, name="Gown")
    ankara = _product(session, name="Ankara", selling_price="40000")
    sale = make_recent_sale(session, customer, admin, days_old=1, items=[(gown, 1)])
    session.commit()

    with pytest.raises(AuthorizationError):
        _exchange(session_factory, None, sale.receipt_no, _lines((gown.id, 1, ankara.id, 1)))


# --- exchange window -------------------------------------------------------- #


def test_exchange_within_two_days_allowed(session_factory, session):
    admin = _admin(session)
    customer = _customer(session)
    gown = _product(session, name="Gown")
    ankara = _product(session, name="Ankara", selling_price="40000")
    sale = make_recent_sale(session, customer, admin, days_old=1, items=[(gown, 1)])
    session.commit()

    exchange = _exchange(
        session_factory, admin, sale.receipt_no, _lines((gown.id, 1, ankara.id, 1))
    )
    assert exchange.original_sale_id == sale.id


def test_exchange_exactly_two_days_old_allowed(session_factory, session):
    admin = _admin(session)
    customer = _customer(session)
    gown = _product(session, name="Gown")
    ankara = _product(session, name="Ankara", selling_price="40000")
    sale = make_recent_sale(session, customer, admin, days_old=2, items=[(gown, 1)])
    session.commit()

    exchange = _exchange(
        session_factory,
        admin,
        sale.receipt_no,
        _lines((gown.id, 1, ankara.id, 1)),
        exchange_date=sale.sale_date + timedelta(days=EXCHANGE_WINDOW_DAYS),
    )
    assert exchange.original_sale_id == sale.id


def test_exchange_after_two_days_rejected(session_factory, session):
    admin = _admin(session)
    customer = _customer(session)
    gown = _product(session, name="Gown")
    ankara = _product(session, name="Ankara", selling_price="40000")
    sale = make_recent_sale(session, customer, admin, days_old=3, items=[(gown, 1)])
    session.commit()

    with pytest.raises(ValidationError, match="window"):
        _exchange(session_factory, admin, sale.receipt_no, _lines((gown.id, 1, ankara.id, 1)))

    with session_factory() as check:
        assert _count(check, Exchange) == 0


def test_exchange_before_the_sale_rejected(session_factory, session):
    admin = _admin(session)
    customer = _customer(session)
    gown = _product(session, name="Gown")
    ankara = _product(session, name="Ankara", selling_price="40000")
    sale = make_recent_sale(session, customer, admin, days_old=1, items=[(gown, 1)])
    session.commit()

    with pytest.raises(ValidationError, match="before the original sale"):
        _exchange(
            session_factory,
            admin,
            sale.receipt_no,
            _lines((gown.id, 1, ankara.id, 1)),
            exchange_date=sale.sale_date - timedelta(days=1),
        )


# --- original receipt validation -------------------------------------------- #


def test_unknown_receipt_rejected(session_factory, session):
    admin = _admin(session)
    customer = _customer(session)
    gown = _product(session, name="Gown")
    ankara = _product(session, name="Ankara", selling_price="40000")
    session.commit()

    with pytest.raises(NotFoundError, match="No sale found"):
        _exchange(session_factory, admin, "FUN-NOT-REAL", _lines((gown.id, 1, ankara.id, 1)))


def test_blank_receipt_rejected(session_factory, session):
    admin = _admin(session)
    customer = _customer(session)
    gown = _product(session, name="Gown")
    ankara = _product(session, name="Ankara", selling_price="40000")
    session.commit()

    with pytest.raises(NotFoundError, match="No sale found"):
        _exchange(session_factory, admin, "   ", _lines((gown.id, 1, ankara.id, 1)))


def test_find_sale_returns_the_original_sale(session_factory, session):
    admin = _admin(session)
    customer = _customer(session)
    gown = _product(session, name="Gown")
    sale = make_recent_sale(session, customer, admin, days_old=1, items=[(gown, 1)])
    session.commit()

    with session_factory() as check:
        found = ExchangeService(check).find_sale(admin, sale.receipt_no)
        assert found.id == sale.id
        assert found.customer_id == customer.id


def test_find_sale_rejects_cashier(session_factory, session):
    cashier = _cashier(session)
    customer = _customer(session)
    gown = _product(session, name="Gown")
    sale = make_recent_sale(session, customer, cashier, days_old=1, items=[(gown, 1)])
    session.commit()

    with pytest.raises(AuthorizationError):
        with session_factory() as check:
            ExchangeService(check).find_sale(cashier, sale.receipt_no)


# --- returned item validation ----------------------------------------------- #


def test_returned_product_must_have_been_sold(session_factory, session):
    admin = _admin(session)
    customer = _customer(session)
    gown = _product(session, name="Gown")
    shirt = _product(session, name="Shirt", selling_price="8000")
    ankara = _product(session, name="Ankara", selling_price="40000")
    sale = make_recent_sale(session, customer, admin, days_old=1, items=[(gown, 1)])
    session.commit()

    with pytest.raises(ValidationError, match="was not sold"):
        _exchange(session_factory, admin, sale.receipt_no, _lines((shirt.id, 1, ankara.id, 1)))


def test_returned_quantity_cannot_exceed_sold(session_factory, session):
    admin = _admin(session)
    customer = _customer(session)
    gown = _product(session, name="Gown")
    ankara = _product(session, name="Ankara", selling_price="40000")
    sale = make_recent_sale(session, customer, admin, days_old=1, items=[(gown, 1)])
    session.commit()

    with pytest.raises(ValidationError, match="Only 1 of 'Gown'"):
        _exchange(session_factory, admin, sale.receipt_no, _lines((gown.id, 2, ankara.id, 2)))


def test_returned_quantity_must_be_positive(session_factory, session):
    admin = _admin(session)
    customer = _customer(session)
    gown = _product(session, name="Gown")
    ankara = _product(session, name="Ankara", selling_price="40000")
    sale = make_recent_sale(session, customer, admin, days_old=1, items=[(gown, 2)])
    session.commit()

    with pytest.raises(ValidationError):
        _exchange(session_factory, admin, sale.receipt_no, _lines((gown.id, 0, ankara.id, 1)))


def test_unknown_original_product_rejected(session_factory, session):
    admin = _admin(session)
    customer = _customer(session)
    gown = _product(session, name="Gown")
    ankara = _product(session, name="Ankara", selling_price="40000")
    sale = make_recent_sale(session, customer, admin, days_old=1, items=[(gown, 1)])
    session.commit()

    with pytest.raises(NotFoundError, match="Original product not found"):
        _exchange(session_factory, admin, sale.receipt_no, _lines((99999, 1, ankara.id, 1)))


def test_missing_line_keys_rejected(session_factory, session):
    admin = _admin(session)
    customer = _customer(session)
    gown = _product(session, name="Gown")
    sale = make_recent_sale(session, customer, admin, days_old=1, items=[(gown, 1)])
    session.commit()

    with pytest.raises(ValidationError, match="original and a replacement product"):
        _exchange(session_factory, admin, sale.receipt_no, [{"original_product_id": gown.id}])
    with pytest.raises(ValidationError, match="original and a replacement product"):
        _exchange(session_factory, admin, sale.receipt_no, [{}])


def test_empty_items_rejected(session_factory, session):
    admin = _admin(session)
    customer = _customer(session)
    gown = _product(session, name="Gown")
    sale = make_recent_sale(session, customer, admin, days_old=1, items=[(gown, 1)])
    session.commit()

    with pytest.raises(ValidationError, match="at least one item"):
        _exchange(session_factory, admin, sale.receipt_no, [])


def test_duplicate_returned_line_rejected(session_factory, session):
    admin = _admin(session)
    customer = _customer(session)
    gown = _product(session, name="Gown")
    ankara = _product(session, name="Ankara", selling_price="40000")
    buba = _product(session, name="Buba", selling_price="15000")
    sale = make_recent_sale(session, customer, admin, days_old=1, items=[(gown, 2)])
    session.commit()

    with pytest.raises(ValidationError, match="more than once as a returned item"):
        _exchange(
            session_factory,
            admin,
            sale.receipt_no,
            _lines((gown.id, 1, ankara.id, 1), (gown.id, 1, buba.id, 1)),
        )


# --- replacement item validation -------------------------------------------- #


def test_unknown_replacement_rejected(session_factory, session):
    admin = _admin(session)
    customer = _customer(session)
    gown = _product(session, name="Gown")
    sale = make_recent_sale(session, customer, admin, days_old=1, items=[(gown, 1)])
    session.commit()

    with pytest.raises(NotFoundError, match="Replacement product not found"):
        _exchange(session_factory, admin, sale.receipt_no, _lines((gown.id, 1, 99999, 1)))


def test_inactive_replacement_rejected(session_factory, session):
    admin = _admin(session)
    customer = _customer(session)
    gown = _product(session, name="Gown")
    ankara = _product(session, name="Ankara", selling_price="40000")
    ankara.is_active = False
    sale = make_recent_sale(session, customer, admin, days_old=1, items=[(gown, 1)])
    session.commit()

    with pytest.raises(ValidationError, match="not active"):
        _exchange(session_factory, admin, sale.receipt_no, _lines((gown.id, 1, ankara.id, 1)))


def test_duplicate_replacement_line_rejected(session_factory, session):
    admin = _admin(session)
    customer = _customer(session)
    gown = _product(session, name="Gown")
    top = _product(session, name="Top", selling_price="10000")
    ankara = _product(session, name="Ankara", selling_price="40000")
    sale = make_recent_sale(
        session, customer, admin, days_old=1, items=[(gown, 1), (top, 1)]
    )
    session.commit()

    with pytest.raises(ValidationError, match="more than once as a replacement"):
        _exchange(
            session_factory,
            admin,
            sale.receipt_no,
            _lines((gown.id, 1, ankara.id, 1), (top.id, 1, ankara.id, 2)),
        )


def test_replacement_quantity_must_be_positive(session_factory, session):
    admin = _admin(session)
    customer = _customer(session)
    gown = _product(session, name="Gown")
    ankara = _product(session, name="Ankara", selling_price="40000")
    sale = make_recent_sale(session, customer, admin, days_old=1, items=[(gown, 1)])
    session.commit()

    with pytest.raises(ValidationError):
        _exchange(session_factory, admin, sale.receipt_no, _lines((gown.id, 1, ankara.id, 0)))


# --- stock / inventory ------------------------------------------------------ #


def test_returned_item_restored_and_replacement_deducted(session_factory, session):
    admin = _admin(session)
    customer = _customer(session)
    gown = _product(session, name="Gown", quantity=10)
    ankara = _product(session, name="Ankara", selling_price="40000", quantity=6)
    sale = make_recent_sale(session, customer, admin, days_old=1, items=[(gown, 1)])
    session.commit()

    exchange = _exchange(
        session_factory, admin, sale.receipt_no, _lines((gown.id, 1, ankara.id, 2))
    )

    with session_factory() as check:
        assert check.get(type(gown), gown.id).quantity == 10  # 9 restored to 10
        assert check.get(type(ankara), ankara.id).quantity == 4  # 6 - 2

        movements = _movements(check, exchange.id)
        assert len(movements) == 2
        returned = next(m for m in movements if m.product_id == gown.id)
        deducted = next(m for m in movements if m.product_id == ankara.id)
        assert returned.change_quantity == 1
        assert returned.previous_quantity == 9
        assert returned.new_quantity == 10
        assert returned.reason == EXCHANGE_RETURN_REASON
        assert returned.reference_type == REFERENCE_EXCHANGE
        assert returned.reference_id == exchange.id
        assert returned.user_id == admin.id
        assert deducted.change_quantity == -2
        assert deducted.previous_quantity == 6
        assert deducted.new_quantity == 4
        assert deducted.reason == EXCHANGE_REPLACEMENT_REASON


def test_same_product_return_and_replacement_keeps_stock_flat(session_factory, session):
    admin = _admin(session)
    customer = _customer(session)
    gown = _product(session, name="Gown", quantity=10)
    sale = make_recent_sale(session, customer, admin, days_old=1, items=[(gown, 1)])
    session.commit()

    exchange = _exchange(session_factory, admin, sale.receipt_no, _lines((gown.id, 1, gown.id, 1)))

    with session_factory() as check:
        # Sale took 1 (10→9), exchange returns 1 (9→10) then takes 1 (10→9): net zero from sale.
        assert check.get(type(gown), gown.id).quantity == 9
        movements = _movements(check, exchange.id)
        assert len(movements) == 2
        assert {m.change_quantity for m in movements} == {1, -1}


def test_insufficient_replacement_stock_rolls_everything_back(session_factory, session):
    admin = _admin(session)
    customer = _customer(session)
    gown = _product(session, name="Gown", quantity=5)
    ankara = _product(session, name="Ankara", selling_price="40000", quantity=1)
    sale = make_recent_sale(session, customer, admin, days_old=1, items=[(gown, 1)])
    session.commit()

    with pytest.raises(ValidationError, match="Insufficient stock.*Ankara"):
        _exchange(session_factory, admin, sale.receipt_no, _lines((gown.id, 1, ankara.id, 2)))

    with session_factory() as check:
        assert _count(check, Exchange) == 0
        assert _count(check, ExchangeItem) == 0
        assert _count(check, InventoryLog) == 1  # only the original sale movement
        assert check.get(type(gown), gown.id).quantity == 4  # stock untouched by exchange
        assert check.get(type(ankara), ankara.id).quantity == 1


# --- price difference ------------------------------------------------------- #


def test_customer_pays_difference_recorded(session_factory, session):
    admin = _admin(session)
    customer = _customer(session)
    gown = _product(session, name="Gown", selling_price="35000")
    ankara = _product(session, name="Ankara", selling_price="40000")
    sale = make_recent_sale(session, customer, admin, days_old=1, items=[(gown, 1)])
    session.commit()

    exchange = _exchange(
        session_factory, admin, sale.receipt_no, _lines((gown.id, 1, ankara.id, 1))
    )
    assert exchange.difference_type == DIFFERENCE_CUSTOMER_PAYS
    assert exchange.difference_amount == Decimal("5000")
    assert exchange.payment_method == PAYMENT_POS


def test_no_difference_exchange_needs_no_payment(session_factory, session):
    admin = _admin(session)
    customer = _customer(session)
    gown = _product(session, name="Gown", selling_price="35000")
    ankara = _product(session, name="Ankara", selling_price="35000")
    sale = make_recent_sale(session, customer, admin, days_old=1, items=[(gown, 1)])
    session.commit()

    exchange = _exchange(
        session_factory, admin, sale.receipt_no, _lines((gown.id, 1, ankara.id, 1))
    )
    assert exchange.difference_type == DIFFERENCE_NONE
    assert exchange.difference_amount == Decimal("0")
    assert exchange.payment_method is None


def test_multiple_lines_difference_aggregates(session_factory, session):
    admin = _admin(session)
    customer = _customer(session)
    gown = _product(session, name="Gown", selling_price="35000")
    top = _product(session, name="Top", selling_price="10000")
    ankara = _product(session, name="Ankara", selling_price="40000")
    buba = _product(session, name="Buba", selling_price="15000")
    sale = make_recent_sale(
        session, customer, admin, days_old=1, items=[(gown, 1), (top, 2)]
    )
    session.commit()

    exchange = _exchange(
        session_factory,
        admin,
        sale.receipt_no,
        _lines((gown.id, 1, ankara.id, 1), (top.id, 1, buba.id, 1)),
    )
    # returned 35000 + 10000 = 45000; replacement 40000 + 15000 = 55000
    assert exchange.difference_amount == Decimal("10000")
    assert exchange.difference_type == DIFFERENCE_CUSTOMER_PAYS
    with session_factory() as check:
        assert _count(check, ExchangeItem) == 2


def test_historical_original_price_and_current_replacement_price(session_factory, session):
    admin = _admin(session)
    customer = _customer(session)
    gown = _product(session, name="Gown", selling_price="35000")
    ankara = _product(session, name="Ankara", selling_price="40000")
    sale = make_recent_sale(session, customer, admin, days_old=1, items=[(gown, 1)])
    session.commit()

    with session_factory() as change:
        gown = change.get(type(gown), gown.id)
        gown.selling_price = Decimal("50000")
        ankara = change.get(type(ankara), ankara.id)
        ankara.selling_price = Decimal("60000")
        change.commit()

    exchange = _exchange(
        session_factory, admin, sale.receipt_no, _lines((gown.id, 1, ankara.id, 1))
    )

    with session_factory() as check:
        item = check.scalar(select(ExchangeItem).where(ExchangeItem.exchange_id == exchange.id))
        assert item.original_price == Decimal("35000")  # historical, from the sale
        assert item.replacement_price == Decimal("60000")  # current selling price


def test_customer_owed_money_blocked_without_settlement(session_factory, session):
    admin = _admin(session)
    customer = _customer(session)
    gown = _product(session, name="Gown", selling_price="35000")
    ankara = _product(session, name="Ankara", selling_price="20000")
    sale = make_recent_sale(session, customer, admin, days_old=1, items=[(gown, 1)])
    session.commit()

    with pytest.raises(ValidationError, match="money back"):
        _exchange(session_factory, admin, sale.receipt_no, _lines((gown.id, 1, ankara.id, 1)))

    with session_factory() as check:
        assert _count(check, Exchange) == 0


def test_payment_method_required_when_customer_pays(session_factory, session):
    admin = _admin(session)
    customer = _customer(session)
    gown = _product(session, name="Gown", selling_price="35000")
    ankara = _product(session, name="Ankara", selling_price="40000")
    sale = make_recent_sale(session, customer, admin, days_old=1, items=[(gown, 1)])
    session.commit()

    with pytest.raises(ValidationError, match="not supported"):
        _exchange(
            session_factory, admin, sale.receipt_no, _lines((gown.id, 1, ankara.id, 1)),
            payment_method=None,
        )


@pytest.mark.parametrize("method", ["CASH", "CREDIT", "cash", "cheque", "POS CASH", ""])
def test_cash_and_unsupported_payment_methods_rejected(session_factory, session, method):
    admin = _admin(session)
    customer = _customer(session)
    gown = _product(session, name="Gown", selling_price="35000")
    ankara = _product(session, name="Ankara", selling_price="40000")
    sale = make_recent_sale(session, customer, admin, days_old=1, items=[(gown, 1)])
    session.commit()

    with pytest.raises(ValidationError, match="not supported"):
        _exchange(
            session_factory, admin, sale.receipt_no, _lines((gown.id, 1, ankara.id, 1)),
            payment_method=method,
        )


def test_transfer_payment_recorded_on_exchange_header(session_factory, session):
    admin = _admin(session)
    customer = _customer(session)
    gown = _product(session, name="Gown", selling_price="35000")
    ankara = _product(session, name="Ankara", selling_price="40000")
    sale = make_recent_sale(session, customer, admin, days_old=1, items=[(gown, 1)])
    session.commit()

    exchange = _exchange(
        session_factory,
        admin,
        sale.receipt_no,
        _lines((gown.id, 1, ankara.id, 1)),
        payment_method=PAYMENT_TRANSFER,
    )
    assert exchange.payment_method == PAYMENT_TRANSFER
    with session_factory() as check:
        assert _count(check, Payment) == 1  # only the original sale's payment


# --- audit / history / original-sale preservation --------------------------- #


def test_exchange_history_records_approved_by_and_snapshots(session_factory, session):
    admin = _admin(session)
    customer = _customer(session)
    gown = _product(session, name="Gown", selling_price="35000")
    ankara = _product(session, name="Ankara", selling_price="40000")
    sale = make_recent_sale(session, customer, admin, days_old=1, items=[(gown, 1)])
    session.commit()

    exchange = _exchange(
        session_factory, admin, sale.receipt_no, _lines((gown.id, 1, ankara.id, 1))
    )

    with session_factory() as check:
        header = check.get(Exchange, exchange.id)
        assert header.approved_by == admin.id
        assert header.customer_id == customer.id
        assert header.original_sale_id == sale.id
        item = check.scalar(select(ExchangeItem).where(ExchangeItem.exchange_id == exchange.id))
        assert item.original_product_id == gown.id
        assert item.replacement_product_id == ankara.id
        assert item.original_price == Decimal("35000")
        assert item.replacement_price == Decimal("40000")
        assert item.original_quantity == 1
        assert item.replacement_quantity == 1


def test_original_sale_never_modified_or_deleted(session_factory, session):
    admin = _admin(session)
    customer = _customer(session)
    gown = _product(session, name="Gown", selling_price="35000")
    ankara = _product(session, name="Ankara", selling_price="40000")
    sale = make_recent_sale(session, customer, admin, days_old=1, items=[(gown, 1)])
    sale_total = sale.total
    session.commit()

    exchange = _exchange(
        session_factory, admin, sale.receipt_no, _lines((gown.id, 1, ankara.id, 1))
    )

    with session_factory() as check:
        header = check.get(Sale, sale.id)
        assert header is not None
        assert header.total == sale_total
        assert header.cashier_id == admin.id
        assert header.payment_method == PAYMENT_POS
        assert _count(check, Sale) == 1
        assert _count(check, Exchange) == 1
        assert exchange.original_sale_id == sale.id


def test_duplicate_exchange_of_the_same_sale_blocked(session_factory, session):
    admin = _admin(session)
    customer = _customer(session)
    gown = _product(session, name="Gown", quantity=5)
    ankara = _product(session, name="Ankara", selling_price="40000", quantity=5)
    buba = _product(session, name="Buba", selling_price="40000", quantity=5)
    sale = make_recent_sale(session, customer, admin, days_old=1, items=[(gown, 1)])
    session.commit()

    first = _exchange(
        session_factory, admin, sale.receipt_no, _lines((gown.id, 1, ankara.id, 1))
    )
    assert first.original_sale_id == sale.id

    with pytest.raises(ValidationError, match="already"):
        _exchange(session_factory, admin, sale.receipt_no, _lines((gown.id, 1, buba.id, 1)))

    with session_factory() as check:
        assert _count(check, Exchange) == 1  # the second exchange rolled back


def test_partial_return_still_allowed_after_a_prior_exchange(session_factory, session):
    admin = _admin(session)
    customer = _customer(session)
    gown = _product(session, name="Gown", quantity=5)
    ankara = _product(session, name="Ankara", selling_price="40000", quantity=5)
    buba = _product(session, name="Buba", selling_price="40000", quantity=5)
    sale = make_recent_sale(session, customer, admin, days_old=1, items=[(gown, 3)])
    session.commit()

    _exchange(session_factory, admin, sale.receipt_no, _lines((gown.id, 2, ankara.id, 2)))

    second = _exchange(
        session_factory, admin, sale.receipt_no, _lines((gown.id, 1, buba.id, 1))
    )
    assert second.original_sale_id == sale.id
    with session_factory() as check:
        assert _count(check, Exchange) == 2


# --- offline / snapshots ---------------------------------------------------- #


def test_exchange_works_fully_offline(session_factory, session):
    admin = _admin(session)
    customer = _customer(session)
    gown = _product(session, name="Gown", quantity=4)
    ankara = _product(session, name="Ankara", selling_price="40000", quantity=4)
    sale = make_recent_sale(session, customer, admin, days_old=1, items=[(gown, 1)])
    session.commit()

    exchange = _exchange(
        session_factory, admin, sale.receipt_no, _lines((gown.id, 1, ankara.id, 1))
    )

    with session_factory() as check:
        assert check.get(Exchange, exchange.id) is not None
        assert check.get(type(gown), gown.id).quantity == 4
        assert check.get(type(ankara), ankara.id).quantity == 3
        assert _count(check, ExchangeItem) == 1
        assert len(_movements(check, exchange.id)) == 2


def test_exchange_with_current_user_snapshot(session_factory, session):
    admin = _admin(session)
    customer = _customer(session)
    gown = _product(session, name="Gown", quantity=4)
    ankara = _product(session, name="Ankara", selling_price="40000", quantity=4)
    sale = make_recent_sale(session, customer, admin, days_old=1, items=[(gown, 1)])
    session.commit()
    current = CurrentUser(
        user_id=admin.id, username=admin.username, full_name=admin.full_name, role=ROLE_ADMIN
    )

    exchange = _exchange(
        session_factory, current, sale.receipt_no, _lines((gown.id, 1, ankara.id, 1))
    )
    assert exchange.approved_by == admin.id
    with session_factory() as check:
        movement = check.scalar(
            select(InventoryLog).where(InventoryLog.reference_id == exchange.id).limit(1)
        )
        assert movement.user_id == admin.id
