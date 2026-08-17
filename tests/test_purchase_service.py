"""Purchase service tests (Phase 07)."""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.data.db import session_scope
from app.data.models import (
    InventoryLog,
    Product,
    Purchase,
    PurchaseItem,
)
from app.domain.errors import AuthorizationError, NotFoundError, ValidationError
from app.domain.services.inventory_service import REFERENCE_STOCK_IN
from app.domain.services.purchase_service import PurchaseLine, PurchaseService
from tests.factories import make_category, make_product, make_user


# ── helpers ──────────────────────────────────────────────────────────────── #

def _svc(session):
    return PurchaseService(session)


def _make_supplier(session, name: str = "Test Supplier"):
    from app.data.models import Supplier
    supplier = Supplier(name=name)
    session.add(supplier)
    session.flush()
    return supplier


# ── authorization ────────────────────────────────────────────────────────── #

class TestAuthorization:
    def test_admin_can_complete(self, session, session_factory):
        admin = make_user(session)
        cat = make_category(session)
        product = make_product(session, cat, cost_price=1000, quantity=0)
        supplier = _make_supplier(session)
        session.commit()
        with session_scope(session_factory) as s:
            purchase = _svc(s).complete_purchase(
                admin,
                supplier_id=supplier.id,
                items=[PurchaseLine(product_id=product.id, quantity=5, unit_cost=Decimal("1000"))],
                amount_paid=Decimal("5000"),
            )
            assert purchase.id is not None

    def test_cashier_cannot_complete(self, session, session_factory):
        cashier = make_user(session, role="CASHIER")
        cat = make_category(session)
        product = make_product(session, cat)
        supplier = _make_supplier(session)
        session.commit()
        with session_scope(session_factory) as s:
            with pytest.raises(AuthorizationError):
                _svc(s).complete_purchase(
                    cashier,
                    supplier_id=supplier.id,
                    items=[PurchaseLine(product_id=product.id, quantity=1, unit_cost=Decimal("1000"))],
                    amount_paid=Decimal("1000"),
                )

    def test_cashier_cannot_list(self, session, session_factory):
        cashier = make_user(session, role="CASHIER")
        session.commit()
        with session_scope(session_factory) as s:
            with pytest.raises(AuthorizationError):
                _svc(s).list_purchases(cashier)

    def test_unauthenticated_cannot_complete(self, session, session_factory):
        cat = make_category(session)
        product = make_product(session, cat)
        supplier = _make_supplier(session)
        session.commit()
        with session_scope(session_factory) as s:
            with pytest.raises(AuthorizationError):
                _svc(s).complete_purchase(
                    None,
                    supplier_id=supplier.id,
                    items=[PurchaseLine(product_id=product.id, quantity=1, unit_cost=Decimal("1000"))],
                    amount_paid=Decimal("1000"),
                )


# ── validation ───────────────────────────────────────────────────────────── #

class TestValidation:
    def test_empty_items_rejected(self, session, session_factory):
        admin = make_user(session)
        supplier = _make_supplier(session)
        session.commit()
        with session_scope(session_factory) as s:
            with pytest.raises(ValidationError, match="at least one item"):
                _svc(s).complete_purchase(
                    admin,
                    supplier_id=supplier.id,
                    items=[],
                    amount_paid=Decimal("0"),
                )

    def test_unknown_supplier_rejected(self, session, session_factory):
        admin = make_user(session)
        cat = make_category(session)
        product = make_product(session, cat)
        session.commit()
        with session_scope(session_factory) as s:
            with pytest.raises(NotFoundError, match="Supplier"):
                _svc(s).complete_purchase(
                    admin,
                    supplier_id=99999,
                    items=[PurchaseLine(product_id=product.id, quantity=1, unit_cost=Decimal("1000"))],
                    amount_paid=Decimal("1000"),
                )

    def test_unknown_product_rejected(self, session, session_factory):
        admin = make_user(session)
        supplier = _make_supplier(session)
        session.commit()
        with session_scope(session_factory) as s:
            with pytest.raises(NotFoundError, match="Product"):
                _svc(s).complete_purchase(
                    admin,
                    supplier_id=supplier.id,
                    items=[PurchaseLine(product_id=99999, quantity=1, unit_cost=Decimal("1000"))],
                    amount_paid=Decimal("1000"),
                )

    def test_inactive_product_rejected(self, session, session_factory):
        admin = make_user(session)
        cat = make_category(session)
        product = make_product(session, cat)
        product.is_active = False
        supplier = _make_supplier(session)
        session.commit()
        with session_scope(session_factory) as s:
            with pytest.raises(ValidationError, match="not active"):
                _svc(s).complete_purchase(
                    admin,
                    supplier_id=supplier.id,
                    items=[PurchaseLine(product_id=product.id, quantity=1, unit_cost=Decimal("1000"))],
                    amount_paid=Decimal("1000"),
                )

    def test_zero_quantity_rejected(self, session, session_factory):
        admin = make_user(session)
        cat = make_category(session)
        product = make_product(session, cat)
        supplier = _make_supplier(session)
        session.commit()
        with session_scope(session_factory) as s:
            with pytest.raises(ValidationError, match="quantity"):
                _svc(s).complete_purchase(
                    admin,
                    supplier_id=supplier.id,
                    items=[PurchaseLine(product_id=product.id, quantity=0, unit_cost=Decimal("1000"))],
                    amount_paid=Decimal("0"),
                )

    def test_negative_quantity_rejected(self, session, session_factory):
        admin = make_user(session)
        cat = make_category(session)
        product = make_product(session, cat)
        supplier = _make_supplier(session)
        session.commit()
        with session_scope(session_factory) as s:
            with pytest.raises(ValidationError, match="quantity"):
                _svc(s).complete_purchase(
                    admin,
                    supplier_id=supplier.id,
                    items=[PurchaseLine(product_id=product.id, quantity=-1, unit_cost=Decimal("1000"))],
                    amount_paid=Decimal("0"),
                )

    def test_duplicate_product_rejected(self, session, session_factory):
        admin = make_user(session)
        cat = make_category(session)
        product = make_product(session, cat)
        supplier = _make_supplier(session)
        session.commit()
        with session_scope(session_factory) as s:
            with pytest.raises(ValidationError, match="Duplicate"):
                _svc(s).complete_purchase(
                    admin,
                    supplier_id=supplier.id,
                    items=[
                        PurchaseLine(product_id=product.id, quantity=1, unit_cost=Decimal("1000")),
                        PurchaseLine(product_id=product.id, quantity=1, unit_cost=Decimal("1200")),
                    ],
                    amount_paid=Decimal("2200"),
                )

    def test_amount_paid_exceeds_total_rejected(self, session, session_factory):
        admin = make_user(session)
        cat = make_category(session)
        product = make_product(session, cat)
        supplier = _make_supplier(session)
        session.commit()
        with session_scope(session_factory) as s:
            with pytest.raises(ValidationError, match="cannot exceed"):
                _svc(s).complete_purchase(
                    admin,
                    supplier_id=supplier.id,
                    items=[PurchaseLine(product_id=product.id, quantity=1, unit_cost=Decimal("1000"))],
                    amount_paid=Decimal("2000"),
                )


# ── stock effects ────────────────────────────────────────────────────────── #

class TestStockEffects:
    def test_stock_increased(self, session, session_factory):
        admin = make_user(session)
        cat = make_category(session)
        product = make_product(session, cat, quantity=10)
        supplier = _make_supplier(session)
        session.commit()
        with session_scope(session_factory) as s:
            _svc(s).complete_purchase(
                admin,
                supplier_id=supplier.id,
                items=[PurchaseLine(product_id=product.id, quantity=5, unit_cost=Decimal("1000"))],
                amount_paid=Decimal("5000"),
            )
        with session_scope(session_factory) as check:
            p = check.get(Product, product.id)
            assert p.quantity == 15

    def test_inventory_log_created(self, session, session_factory):
        admin = make_user(session)
        cat = make_category(session)
        product = make_product(session, cat, quantity=0)
        supplier = _make_supplier(session)
        session.commit()
        with session_scope(session_factory) as s:
            _svc(s).complete_purchase(
                admin,
                supplier_id=supplier.id,
                items=[PurchaseLine(product_id=product.id, quantity=10, unit_cost=Decimal("500"))],
                amount_paid=Decimal("5000"),
            )
        with session_scope(session_factory) as check:
            logs = check.query(InventoryLog).filter(
                InventoryLog.product_id == product.id,
                InventoryLog.reference_type == REFERENCE_STOCK_IN,
            ).all()
            assert len(logs) == 1
            assert logs[0].change_quantity == 10
            assert logs[0].previous_quantity == 0
            assert logs[0].new_quantity == 10
            assert logs[0].reason == "Purchase stock received"

    def test_cost_price_updated(self, session, session_factory):
        admin = make_user(session)
        cat = make_category(session)
        product = make_product(session, cat, cost_price=Decimal("800"), quantity=0)
        supplier = _make_supplier(session)
        session.commit()
        with session_scope(session_factory) as s:
            _svc(s).complete_purchase(
                admin,
                supplier_id=supplier.id,
                items=[PurchaseLine(product_id=product.id, quantity=5, unit_cost=Decimal("1200"))],
                amount_paid=Decimal("6000"),
            )
        with session_scope(session_factory) as check:
            p = check.get(Product, product.id)
            assert p.cost_price == Decimal("1200")

    def test_multi_item_stock(self, session, session_factory):
        admin = make_user(session)
        cat = make_category(session)
        p1 = make_product(session, cat, name="Item A", quantity=0)
        p2 = make_product(session, cat, name="Item B", quantity=5)
        supplier = _make_supplier(session)
        session.commit()
        with session_scope(session_factory) as s:
            _svc(s).complete_purchase(
                admin,
                supplier_id=supplier.id,
                items=[
                    PurchaseLine(product_id=p1.id, quantity=10, unit_cost=Decimal("500")),
                    PurchaseLine(product_id=p2.id, quantity=3, unit_cost=Decimal("800")),
                ],
                amount_paid=Decimal("7400"),
            )
        with session_scope(session_factory) as check:
            assert check.get(Product, p1.id).quantity == 10
            assert check.get(Product, p2.id).quantity == 8


# ── purchase header / items ──────────────────────────────────────────────── #

class TestPurchaseHeader:
    def test_total_cost_calculated(self, session, session_factory):
        admin = make_user(session)
        cat = make_category(session)
        product = make_product(session, cat)
        supplier = _make_supplier(session)
        session.commit()
        with session_scope(session_factory) as s:
            purchase = _svc(s).complete_purchase(
                admin,
                supplier_id=supplier.id,
                items=[PurchaseLine(product_id=product.id, quantity=5, unit_cost=Decimal("1000"))],
                amount_paid=Decimal("5000"),
            )
            assert purchase.total_cost == Decimal("5000")
            assert purchase.amount_paid == Decimal("5000")
            assert purchase.balance == Decimal("0")

    def test_balance_calculated(self, session, session_factory):
        admin = make_user(session)
        cat = make_category(session)
        product = make_product(session, cat)
        supplier = _make_supplier(session)
        session.commit()
        with session_scope(session_factory) as s:
            purchase = _svc(s).complete_purchase(
                admin,
                supplier_id=supplier.id,
                items=[PurchaseLine(product_id=product.id, quantity=5, unit_cost=Decimal("1000"))],
                amount_paid=Decimal("3000"),
            )
            assert purchase.total_cost == Decimal("5000")
            assert purchase.amount_paid == Decimal("3000")
            assert purchase.balance == Decimal("2000")

    def test_purchase_items_created(self, session, session_factory):
        admin = make_user(session)
        cat = make_category(session)
        product = make_product(session, cat)
        supplier = _make_supplier(session)
        session.commit()
        with session_scope(session_factory) as s:
            purchase = _svc(s).complete_purchase(
                admin,
                supplier_id=supplier.id,
                items=[PurchaseLine(product_id=product.id, quantity=5, unit_cost=Decimal("1000"))],
                amount_paid=Decimal("5000"),
            )
            purchase_id = purchase.id
        with session_scope(session_factory) as check:
            items = check.query(PurchaseItem).filter(
                PurchaseItem.purchase_id == purchase_id
            ).all()
            assert len(items) == 1
            assert items[0].product_id == product.id
            assert items[0].quantity == 5
            assert items[0].unit_cost == Decimal("1000")
            assert items[0].line_total == Decimal("5000")

    def test_created_by_recorded(self, session, session_factory):
        admin = make_user(session)
        cat = make_category(session)
        product = make_product(session, cat)
        supplier = _make_supplier(session)
        session.commit()
        with session_scope(session_factory) as s:
            purchase = _svc(s).complete_purchase(
                admin,
                supplier_id=supplier.id,
                items=[PurchaseLine(product_id=product.id, quantity=1, unit_cost=Decimal("1000"))],
                amount_paid=Decimal("1000"),
            )
            assert purchase.created_by == admin.id


# ── list / get ───────────────────────────────────────────────────────────── #

class TestListPurchases:
    def test_list_empty(self, session, session_factory):
        admin = make_user(session)
        session.commit()
        with session_scope(session_factory) as s:
            assert _svc(s).list_purchases(admin) == []

    def test_list_returns_created(self, session, session_factory):
        admin = make_user(session)
        cat = make_category(session)
        product = make_product(session, cat)
        supplier = _make_supplier(session)
        session.commit()
        with session_scope(session_factory) as s:
            _svc(s).complete_purchase(
                admin,
                supplier_id=supplier.id,
                items=[PurchaseLine(product_id=product.id, quantity=1, unit_cost=Decimal("1000"))],
                amount_paid=Decimal("1000"),
            )
            result = _svc(s).list_purchases(admin)
            assert len(result) == 1

    def test_get_purchase(self, session, session_factory):
        admin = make_user(session)
        cat = make_category(session)
        product = make_product(session, cat)
        supplier = _make_supplier(session)
        session.commit()
        with session_scope(session_factory) as s:
            purchase = _svc(s).complete_purchase(
                admin,
                supplier_id=supplier.id,
                items=[PurchaseLine(product_id=product.id, quantity=1, unit_cost=Decimal("1000"))],
                amount_paid=Decimal("1000"),
            )
            purchase_id = purchase.id
        with session_scope(session_factory) as check:
            got = _svc(check).get_purchase(admin, purchase_id)
            assert got.total_cost == Decimal("1000")

    def test_get_not_found(self, session, session_factory):
        admin = make_user(session)
        session.commit()
        with session_scope(session_factory) as s:
            with pytest.raises(NotFoundError):
                _svc(s).get_purchase(admin, 99999)


# ── rollback ─────────────────────────────────────────────────────────────── #

class TestRollback:
    def test_invalid_item_rolls_back_stock(self, session, session_factory):
        admin = make_user(session)
        cat = make_category(session)
        p1 = make_product(session, cat, name="Good", quantity=0)
        p2 = make_product(session, cat, name="Bad", quantity=0)
        supplier = _make_supplier(session)
        session.commit()
        with session_scope(session_factory) as s:
            with pytest.raises(Exception):
                _svc(s).complete_purchase(
                    admin,
                    supplier_id=supplier.id,
                    items=[
                        PurchaseLine(product_id=p1.id, quantity=5, unit_cost=Decimal("1000")),
                        PurchaseLine(product_id=p2.id, quantity=0, unit_cost=Decimal("1000")),
                    ],
                    amount_paid=Decimal("10000"),
                )
        with session_scope(session_factory) as check:
            assert check.get(Product, p1.id).quantity == 0
            assert check.get(Product, p2.id).quantity == 0
