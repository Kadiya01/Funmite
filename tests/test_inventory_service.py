"""Inventory service tests (Phase 04).

Covers stock-in, adjustment, the shared movement writer, movement history,
low-stock detection, permissions and transactional integrity.
"""

from __future__ import annotations

import pytest
from sqlalchemy import select

from app.data.db import session_scope
from app.data.models import InventoryLog, LOW_STOCK_THRESHOLD, ROLE_ADMIN, ROLE_CASHIER
from app.data.repositories.inventory_repository import InventoryLogRepository
from app.domain.errors import AuthorizationError, NotFoundError, ValidationError
from app.domain.permissions import CAP_MAKE_SALE
from app.domain.services.inventory_service import (
    DEFAULT_STOCK_IN_REASON,
    REFERENCE_STOCK_ADJUSTMENT,
    REFERENCE_STOCK_IN,
    InventoryService,
)
from tests.factories import make_category, make_product, make_user


def _admin(session):
    return make_user(session, role=ROLE_ADMIN)


def _cashier(session):
    return make_user(session, role=ROLE_CASHIER)


def _product(session, *, quantity: int = 10, name: str = "Gown"):
    return make_product(session, make_category(session), name=name, quantity=quantity)


def _logs(session):
    return session.scalars(select(InventoryLog).order_by(InventoryLog.id)).all()


# --- stock-in ------------------------------------------------------------- #


def test_stock_in_increases_quantity_and_logs_movement(session_factory, session):
    admin = _admin(session)
    product = _product(session, quantity=5)
    session.commit()

    with session_scope(session_factory) as session:
        log = InventoryService(session).stock_in(admin, product.id, 7)

    with session_factory() as check:
        fresh = check.get(type(product), product.id)
        assert fresh.quantity == 12

    log_id = log.id
    with session_factory() as check:
        recorded = check.get(InventoryLog, log_id)
        assert recorded is not None
        assert recorded.product_id == product.id
        assert recorded.change_quantity == 7
        assert recorded.previous_quantity == 5
        assert recorded.new_quantity == 12
        assert recorded.reason == DEFAULT_STOCK_IN_REASON
        assert recorded.reference_type == REFERENCE_STOCK_IN
        assert recorded.reference_id is None
        assert recorded.user_id == admin.id
        assert recorded.created_at is not None


def test_stock_in_uses_supplied_reason(session_factory, session):
    admin = _admin(session)
    product = _product(session)
    session.commit()

    with session_scope(session_factory) as session:
        InventoryService(session).stock_in(admin, product.id, 2, reason="Delivery")

    with session_factory() as check:
        log = check.scalars(select(InventoryLog)).one()
        assert log.reason == "Delivery"


def test_stock_in_rejects_zero_or_negative_quantity(session_factory, session):
    admin = _admin(session)
    product = _product(session, quantity=5)
    session.commit()

    for bad in ("0", "-1", "1.5", "abc", ""):
        with session_scope(session_factory) as session:
            with pytest.raises(ValidationError):
                InventoryService(session).stock_in(admin, product.id, bad)

    with session_factory() as check:
        assert check.get(type(product), product.id).quantity == 5
        assert check.scalars(select(InventoryLog)).first() is None


def test_stock_in_requires_stock_in_permission(session_factory, session):
    cashier = _cashier(session)
    product = _product(session)
    session.commit()

    with session_scope(session_factory) as session:
        with pytest.raises(AuthorizationError):
            InventoryService(session).stock_in(cashier, product.id, 1)


def test_stock_in_missing_product_raises(session_factory, session):
    admin = _admin(session)
    session.commit()

    with session_scope(session_factory) as session:
        with pytest.raises(NotFoundError):
            InventoryService(session).stock_in(admin, 9999, 1)


# --- adjustment ----------------------------------------------------------- #


def test_adjust_sets_quantity_and_logs_movement(session_factory, session):
    admin = _admin(session)
    product = _product(session, quantity=8)
    session.commit()

    with session_scope(session_factory) as session:
        log = InventoryService(session).adjust(admin, product.id, 2, reason="Physical count")

    with session_factory() as check:
        fresh = check.get(type(product), product.id)
        assert fresh.quantity == 2

    log_id = log.id
    with session_factory() as check:
        recorded = check.get(InventoryLog, log_id)
        assert recorded.change_quantity == -6
        assert recorded.previous_quantity == 8
        assert recorded.new_quantity == 2
        assert recorded.reason == "Physical count"
        assert recorded.reference_type == REFERENCE_STOCK_ADJUSTMENT


def test_adjust_requires_reason(session_factory, session):
    admin = _admin(session)
    product = _product(session, quantity=8)
    session.commit()

    with session_scope(session_factory) as session:
        with pytest.raises(ValidationError):
            InventoryService(session).adjust(admin, product.id, 3, reason="   ")

    with session_factory() as check:
        assert check.get(type(product), product.id).quantity == 8


def test_adjust_cannot_go_below_zero(session_factory, session):
    admin = _admin(session)
    product = _product(session, quantity=3)
    session.commit()

    with session_scope(session_factory) as session:
        with pytest.raises(ValidationError):
            InventoryService(session).adjust(admin, product.id, -1, reason="Count")

    with session_factory() as check:
        assert check.get(type(product), product.id).quantity == 3
        assert check.scalars(select(InventoryLog)).first() is None


def test_adjust_to_same_quantity_is_recorded_as_noop(session_factory, session):
    admin = _admin(session)
    product = _product(session, quantity=4)
    session.commit()

    with session_scope(session_factory) as session:
        log = InventoryService(session).adjust(admin, product.id, 4, reason="Confirmed count")

    with session_factory() as check:
        recorded = check.get(InventoryLog, log.id)
        assert recorded.change_quantity == 0
        assert recorded.new_quantity == 4


def test_adjust_requires_stock_adjustment_permission(session_factory, session):
    cashier = _cashier(session)
    product = _product(session)
    session.commit()

    with session_scope(session_factory) as session:
        with pytest.raises(AuthorizationError):
            InventoryService(session).adjust(cashier, product.id, 1, reason="Count")


# --- shared movement writer (sale/exchange reuse) ------------------------- #


def test_change_stock_is_shared_and_reusable_by_sales(session_factory, session):
    cashier = _cashier(session)  # has CAP_MAKE_SALE, not stock management
    product = _product(session, quantity=5)
    session.commit()

    with session_scope(session_factory) as session:
        log = InventoryService(session).change_stock(
            cashier,
            product.id,
            -2,
            "Sold",
            reference_type="SALE",
            reference_id=101,
            capability=CAP_MAKE_SALE,
        )

    with session_factory() as check:
        assert check.get(type(product), product.id).quantity == 3
        recorded = check.get(InventoryLog, log.id)
        assert recorded.reference_type == "SALE"
        assert recorded.reference_id == 101
        assert recorded.change_quantity == -2


def test_change_stock_defaults_to_admin_stock_capability(session_factory, session):
    cashier = _cashier(session)
    product = _product(session, quantity=5)
    session.commit()

    with session_scope(session_factory) as session:
        with pytest.raises(AuthorizationError):
            InventoryService(session).change_stock(cashier, product.id, -2, "Sold")


def test_change_stock_refuses_negative_result(session_factory, session):
    admin = _admin(session)
    product = _product(session, quantity=3)
    session.commit()

    with session_scope(session_factory) as session:
        with pytest.raises(ValidationError):
            InventoryService(session).change_stock(admin, product.id, -5, "Sale")

    with session_factory() as check:
        assert check.get(type(product), product.id).quantity == 3
        assert check.scalars(select(InventoryLog)).first() is None


def test_change_stock_requires_reason(session_factory, session):
    admin = _admin(session)
    product = _product(session, quantity=3)
    session.commit()

    with session_scope(session_factory) as session:
        with pytest.raises(ValidationError):
            InventoryService(session).change_stock(admin, product.id, 1, "")


# --- queries -------------------------------------------------------------- #


def test_list_low_stock_uses_confirmed_threshold(session_factory, session):
    admin = _admin(session)
    category = make_category(session)
    critical = make_product(session, category, quantity=0)
    low = make_product(session, category, quantity=LOW_STOCK_THRESHOLD)
    ok = make_product(session, category, quantity=LOW_STOCK_THRESHOLD + 1)
    inactive = make_product(session, category, quantity=2)
    inactive.is_active = False
    session.commit()

    with session_scope(session_factory) as session:
        result = InventoryService(session).list_low_stock(admin)

    ids = {product.id for product in result}
    assert critical.id in ids
    assert low.id in ids
    assert ok.id not in ids
    assert inactive.id not in ids


def test_list_low_stock_is_admin_only(session_factory, session):
    cashier = _cashier(session)
    session.commit()

    with session_scope(session_factory) as session:
        with pytest.raises(AuthorizationError):
            InventoryService(session).list_low_stock(cashier)


def test_list_movements_returns_newest_first_and_filters(session_factory, session):
    admin = _admin(session)
    gown = _product(session, name="Gown", quantity=10)
    top = _product(session, name="Top", quantity=10)
    session.commit()

    with session_scope(session_factory) as session:
        InventoryService(session).stock_in(admin, gown.id, 1, reason="First")
        InventoryService(session).stock_in(admin, gown.id, 2, reason="Second")
        InventoryService(session).stock_in(admin, top.id, 3, reason="Top in")

    with session_scope(session_factory) as session:
        all_logs = InventoryService(session).list_movements(admin)

    assert len(all_logs) == 3
    assert [log.reason for log in all_logs] == ["Top in", "Second", "First"]

    with session_scope(session_factory) as session:
        gown_logs = InventoryService(session).list_movements(admin, product_id=gown.id)
    assert [log.reason for log in gown_logs] == ["Second", "First"]

    with session_scope(session_factory) as session:
        limited = InventoryService(session).list_movements(admin, limit=1)
    assert len(limited) == 1
    assert limited[0].reason == "Top in"


def test_list_movements_eager_loads_product_and_user(session_factory, session):
    admin = _admin(session)
    product = _product(session, name="Ankara", quantity=10)
    session.commit()

    with session_scope(session_factory) as session:
        InventoryService(session).stock_in(admin, product.id, 2)

    with session_scope(session_factory) as session:
        log = InventoryService(session).list_movements(admin)[0]
        assert log.product.name == "Ankara"
        assert log.user.full_name == admin.full_name


def test_list_movements_is_admin_only(session_factory, session):
    cashier = _cashier(session)
    session.commit()

    with session_scope(session_factory) as session:
        with pytest.raises(AuthorizationError):
            InventoryService(session).list_movements(cashier)


# --- audit trail integrity ------------------------------------------------- #


def test_every_stock_change_is_traceable(session_factory, session):
    admin = _admin(session)
    product = _product(session, quantity=5)
    session.commit()

    with session_scope(session_factory) as session:
        InventoryService(session).stock_in(admin, product.id, 5)
        InventoryService(session).adjust(admin, product.id, 4, reason="Count")

    with session_factory() as check:
        assert check.get(type(product), product.id).quantity == 4
        repo = InventoryLogRepository(check)
        logs = repo.list_by_product(product.id)
        assert [log.new_quantity for log in logs] == [10, 4]
        assert [log.change_quantity for log in logs] == [5, -6]
        assert logs[0].reason == DEFAULT_STOCK_IN_REASON
        assert logs[1].reason == "Count"


def test_failed_stock_change_persists_nothing(session_factory, session):
    admin = _admin(session)
    product = _product(session, quantity=2)
    session.commit()

    with pytest.raises(ValidationError):
        with session_scope(session_factory) as session:
            InventoryService(session).adjust(admin, product.id, -3, reason="Count")

    with session_factory() as check:
        assert check.get(type(product), product.id).quantity == 2
        assert check.scalars(select(InventoryLog)).first() is None
