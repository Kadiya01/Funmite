"""Schema and migration tests: table creation, idempotency, downgrade."""

from __future__ import annotations

from sqlalchemy import inspect

from app.data.migrations import runner

EXPECTED_TABLES = {
    "users",
    "categories",
    "products",
    "customers",
    "sales",
    "sale_items",
    "payments",
    "inventory_logs",
    "suppliers",
    "purchases",
    "purchase_items",
    "expenses",
    "exchanges",
    "exchange_items",
    "sync_queue",
    "sync_state",
}


def test_migrations_create_all_expected_tables(engine):
    tables = set(inspect(engine).get_table_names())
    assert EXPECTED_TABLES.issubset(tables)


def test_schema_version_table_is_tracked(engine):
    assert "schema_version" in set(inspect(engine).get_table_names())
    assert runner.current_version(engine) >= 1


def test_upgrade_is_idempotent(engine):
    before = runner.current_version(engine)
    assert runner.upgrade(engine) == before
    assert runner.current_version(engine) == before


def test_downgrade_to_zero_then_upgrade_again(engine):
    assert runner.current_version(engine) >= 1
    runner.downgrade(engine, target=0)
    assert runner.current_version(engine) == 0
    tables = set(inspect(engine).get_table_names())
    assert "products" not in tables

    runner.upgrade(engine)
    assert runner.current_version(engine) >= 1
    tables = set(inspect(engine).get_table_names())
    assert "products" in tables


def test_no_website_tables_exist(engine):
    tables = set(inspect(engine).get_table_names())
    forbidden = {"web_users", "web_orders", "cart_items", "blog_posts", "site_content"}
    assert not forbidden.intersection(tables)


def test_expected_indexes_exist(engine):
    inspector = inspect(engine)

    def index_names(table):
        return {entry["name"] for entry in inspector.get_indexes(table)}

    assert "idx_products_category" in index_names("products")
    assert "idx_sales_date" in index_names("sales")
    assert "idx_sales_cashier" in index_names("sales")
    assert "idx_sale_items_sale" in index_names("sale_items")
    assert "idx_inventory_product_date" in index_names("inventory_logs")
    assert "idx_sync_status" in index_names("sync_queue")
