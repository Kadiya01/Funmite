"""Relationship tests: the full entity graph navigates correctly."""

from __future__ import annotations

from sqlalchemy import func, select

from app.data.models import ROLE_CASHIER, InventoryLog, Payment, Product, Sale, SaleItem
from tests.factories import (
    make_category,
    make_customer,
    make_product,
    make_sale,
    make_user,
)


def _count(session, model) -> int:
    return int(session.scalar(select(func.count()).select_from(model)) or 0)


def test_sale_graph_navigates_both_directions(session):
    category = make_category(session)
    product = make_product(session, category, quantity=10)
    customer = make_customer(session)
    cashier = make_user(session, role=ROLE_CASHIER)
    sale = make_sale(session, customer, cashier, items=[(product, 2)])

    sale = session.get(Sale, sale.id)
    assert sale.customer is customer
    assert sale.cashier is cashier
    assert len(sale.items) == 1
    assert sale.items[0].product_id == product.id
    assert sale.items[0].quantity == 2
    assert len(sale.payments) == 1
    assert sale.payments[0].payment_method == "POS"

    assert customer.sales[0] is sale
    assert cashier.sales[0] is sale
    assert product.sale_items[0].sale_id == sale.id

    item = session.get(SaleItem, sale.items[0].id)
    assert item.sale is sale
    assert item.product is product


def test_product_category_relationship(session):
    category = make_category(session)
    product = make_product(session, category)
    assert product.category is category
    assert category.products[0] is product


def test_inventory_log_relationship(session):
    category = make_category(session)
    product = make_product(session, category, quantity=5)
    customer = make_customer(session)
    cashier = make_user(session)
    make_sale(session, customer, cashier, items=[(product, 1)])

    logs = session.scalars(select(InventoryLog).order_by(InventoryLog.id)).all()
    assert len(logs) == 1
    log = logs[0]
    assert log.product is product
    assert log.user is cashier
    assert log.previous_quantity == 5
    assert log.new_quantity == 4
    assert log.change_quantity == -1


def test_product_stock_decreases_with_sale(session):
    category = make_category(session)
    product = make_product(session, category, quantity=5)
    customer = make_customer(session)
    cashier = make_user(session)
    make_sale(session, customer, cashier, items=[(product, 2)])
    fresh = session.get(Product, product.id)
    assert fresh.quantity == 3


def test_payment_recorded_for_sale(session):
    customer = make_customer(session)
    cashier = make_user(session)
    category = make_category(session)
    product = make_product(session, category, selling_price="2500")
    sale = make_sale(session, customer, cashier, items=[(product, 3)])
    payment = session.scalar(select(Payment).where(Payment.sale_id == sale.id))
    assert payment is not None
    assert payment.amount == sale.total
