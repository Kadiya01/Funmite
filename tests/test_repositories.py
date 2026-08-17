"""Repository tests: lookups, search, low stock and date filtering."""

from __future__ import annotations

from datetime import datetime, timedelta

from app.data.repositories.category_repository import CategoryRepository
from app.data.repositories.customer_repository import CustomerRepository
from app.data.repositories.inventory_repository import InventoryLogRepository
from app.data.repositories.product_repository import ProductRepository
from app.data.repositories.sale_repository import SaleRepository
from app.data.repositories.user_repository import UserRepository
from tests.factories import (
    make_category,
    make_customer,
    make_product,
    make_recent_sale,
    make_user,
)


def test_user_lookup_by_username(session):
    user = make_user(session, username="cashier01")
    repo = UserRepository(session)
    assert repo.get_by_username("cashier01") is user
    assert repo.get_by_username("missing") is None
    assert user in repo.list_active()


def test_category_lookup_by_name(session):
    category = make_category(session, name="Fashion")
    repo = CategoryRepository(session)
    assert repo.get_by_name("Fashion") is category


def test_product_lookup_by_barcode_and_code(session):
    category = make_category(session)
    product = make_product(session, category)
    repo = ProductRepository(session)
    assert repo.get_by_barcode(product.barcode) is product
    assert repo.get_by_product_code(product.product_code) is product
    assert repo.get_by_barcode("DOES-NOT-EXIST") is None


def test_product_search_matches_name_code_and_barcode(session):
    category = make_category(session)
    gown = make_product(session, category, name="Ladies Gown")
    top = make_product(session, category, name="Plain Top")
    repo = ProductRepository(session)

    assert gown in repo.search("gown")
    assert top not in repo.search("gown")
    assert gown in repo.search(gown.barcode)
    assert gown in repo.search(gown.product_code)


def test_product_search_is_case_insensitive(session):
    category = make_category(session)
    product = make_product(session, category, name="LADIES GOWN")
    repo = ProductRepository(session)
    assert product in repo.search("ladies gown")


def test_low_stock_list_uses_confirmed_threshold(session):
    category = make_category(session)
    low = make_product(session, category, quantity=3)
    critical = make_product(session, category, quantity=0)
    ok = make_product(session, category, quantity=4)
    repo = ProductRepository(session)
    result = repo.list_low_stock()
    assert low in result
    assert critical in result
    assert ok not in result


def test_customer_lookup_and_search(session):
    customer = make_customer(session, name="Amina Yusuf")
    repo = CustomerRepository(session)
    assert repo.get_by_customer_code(customer.customer_code) is customer
    assert customer in repo.search("amina")


def test_sale_repository_lookups(session):
    customer = make_customer(session)
    cashier = make_user(session)
    category = make_category(session)
    product = make_product(session, category)
    sale = make_recent_sale(session, customer, cashier, days_old=1, items=[(product, 1)])

    repo = SaleRepository(session)
    assert repo.get_by_receipt_no(sale.receipt_no) is sale
    assert sale in repo.list_between(
        datetime.now() - timedelta(days=2), datetime.now() + timedelta(days=1)
    )
    assert sale in repo.list_by_cashier(cashier.id)
    assert sale not in repo.list_between(
        datetime.now() - timedelta(days=10), datetime.now() - timedelta(days=5)
    )


def test_inventory_log_repository(session):
    category = make_category(session)
    product = make_product(session, category)
    customer = make_customer(session)
    cashier = make_user(session)
    make_recent_sale(session, customer, cashier, days_old=0, items=[(product, 2)])

    repo = InventoryLogRepository(session)
    logs = repo.list_by_product(product.id)
    assert len(logs) == 1
    assert logs[0].change_quantity == -2
    recent = repo.list_between(
        datetime.now() - timedelta(days=1), datetime.now() + timedelta(days=1)
    )
    assert logs[0] in recent
