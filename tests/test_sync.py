"""Tests for Phase 10B — Sync foundation.

Covers:
  - Migration 003 (sync_uuid, version, device_id columns)
  - SyncQueueRepository (enqueue, queries, status transitions)
  - SyncStateRepository (last-sync cursor)
  - DeviceIdentity (file-based UUID persistence)
  - SyncService (enqueue logic, fire-and-forget)
  - Service-level sync integration
"""

from __future__ import annotations

import json
from datetime import datetime

import pytest
from sqlalchemy import inspect

from app.data.models import (
    SYNC_STATUS_FAILED,
    SYNC_STATUS_PENDING,
    SYNC_STATUS_SYNCED,
    SYNC_STATUS_SYNCING,
    Category,
    Customer,
    Product,
    ROLE_ADMIN,
    Supplier,
    SyncQueueItem,
    SyncState,
)
from app.data.repositories.sync_repository import (
    SyncQueueRepository,
    SyncStateRepository,
)
from app.domain.services.device_service import DeviceIdentity
from app.domain.services.sync_service import (
    ENTITY_CATEGORY,
    ENTITY_CUSTOMER,
    ENTITY_EXPENSE,
    ENTITY_PRODUCT,
    ENTITY_SALE,
    OP_CREATE,
    OP_DELETE,
    OP_UPDATE,
    SyncService,
)
from tests.factories import make_user


# ---------------------------------------------------------------------------
# Migration 003 — sync metadata columns
# ---------------------------------------------------------------------------

class TestSyncMetadataColumns:
    """Verify migration 003 added the correct columns."""

    def test_sync_uuid_on_products(self, engine):
        cols = {c["name"] for c in inspect(engine).get_columns("products")}
        assert "sync_uuid" in cols
        assert "version" in cols

    def test_sync_uuid_on_categories(self, engine):
        cols = {c["name"] for c in inspect(engine).get_columns("categories")}
        assert "sync_uuid" in cols
        assert "version" in cols

    def test_sync_uuid_on_customers(self, engine):
        cols = {c["name"] for c in inspect(engine).get_columns("customers")}
        assert "sync_uuid" in cols
        assert "version" in cols

    def test_sync_uuid_on_suppliers(self, engine):
        cols = {c["name"] for c in inspect(engine).get_columns("suppliers")}
        assert "sync_uuid" in cols
        assert "version" in cols

    def test_sync_uuid_on_sales(self, engine):
        cols = {c["name"] for c in inspect(engine).get_columns("sales")}
        assert "sync_uuid" in cols

    def test_sync_uuid_on_sale_items(self, engine):
        cols = {c["name"] for c in inspect(engine).get_columns("sale_items")}
        assert "sync_uuid" in cols

    def test_sync_uuid_on_payments(self, engine):
        cols = {c["name"] for c in inspect(engine).get_columns("payments")}
        assert "sync_uuid" in cols

    def test_sync_uuid_on_inventory_logs(self, engine):
        cols = {c["name"] for c in inspect(engine).get_columns("inventory_logs")}
        assert "sync_uuid" in cols

    def test_sync_uuid_on_purchases(self, engine):
        cols = {c["name"] for c in inspect(engine).get_columns("purchases")}
        assert "sync_uuid" in cols

    def test_sync_uuid_on_expenses(self, engine):
        cols = {c["name"] for c in inspect(engine).get_columns("expenses")}
        assert "sync_uuid" in cols

    def test_sync_uuid_on_exchanges(self, engine):
        cols = {c["name"] for c in inspect(engine).get_columns("exchanges")}
        assert "sync_uuid" in cols

    def test_device_id_on_sync_queue(self, engine):
        cols = {c["name"] for c in inspect(engine).get_columns("sync_queue")}
        assert "device_id" in cols

    def test_migration_version_is_3(self, engine):
        from app.data.migrations import runner
        assert runner.current_version(engine) == 3


# ---------------------------------------------------------------------------
# ORM model defaults
# ---------------------------------------------------------------------------

class TestSyncUuidDefaults:
    """ORM models auto-generate sync_uuid on creation."""

    def test_category_has_sync_uuid_and_version(self, session):
        cat = Category(name="Test Cat")
        session.add(cat)
        session.flush()
        assert cat.sync_uuid is not None
        assert cat.version == 1

    def test_product_has_sync_uuid_and_version(self, session):
        from tests.factories import make_category
        cat = make_category(session)
        product = Product(
            product_code="PRD-TEST",
            name="Test Product",
            category_id=cat.id,
            cost_price=100,
            selling_price=150,
            quantity=10,
            barcode="BAR-TEST-001",
        )
        session.add(product)
        session.flush()
        assert product.sync_uuid is not None
        assert product.version == 1

    def test_customer_has_sync_uuid_and_version(self, session):
        customer = Customer(
            customer_code="CUS-TEST",
            name="Test Customer",
        )
        session.add(customer)
        session.flush()
        assert customer.sync_uuid is not None
        assert customer.version == 1

    def test_supplier_has_sync_uuid_and_version(self, session):
        supplier = Supplier(name="Test Supplier")
        session.add(supplier)
        session.flush()
        assert supplier.sync_uuid is not None
        assert supplier.version == 1


# ---------------------------------------------------------------------------
# SyncQueueRepository
# ---------------------------------------------------------------------------

class TestSyncQueueRepository:
    """Sync queue CRUD and status transitions."""

    def test_enqueue_creates_pending_entry(self, session):
        repo = SyncQueueRepository(session)
        item = repo.enqueue(
            entity_type="product",
            entity_id=1,
            operation="CREATE",
            payload={"name": "Widget"},
            device_id="device-A",
        )
        session.flush()
        assert item.status == SYNC_STATUS_PENDING
        assert item.entity_type == "product"
        assert item.entity_id == 1
        assert item.operation == "CREATE"
        assert item.device_id == "device-A"
        parsed = json.loads(item.payload)
        assert parsed["name"] == "Widget"

    def test_get_pending_returns_fifo(self, session):
        repo = SyncQueueRepository(session)
        repo.enqueue(entity_type="product", entity_id=1, operation="CREATE", payload={})
        repo.enqueue(entity_type="product", entity_id=2, operation="UPDATE", payload={})
        session.flush()
        pending = repo.get_pending()
        assert len(pending) == 2
        assert pending[0].entity_id == 1
        assert pending[1].entity_id == 2

    def test_get_pending_respects_limit(self, session):
        repo = SyncQueueRepository(session)
        for i in range(10):
            repo.enqueue(entity_type="product", entity_id=i, operation="CREATE", payload={})
        session.flush()
        assert len(repo.get_pending(limit=3)) == 3

    def test_mark_syncing_updates_status(self, session):
        repo = SyncQueueRepository(session)
        item = repo.enqueue(entity_type="product", entity_id=1, operation="CREATE", payload={})
        session.flush()
        repo.mark_syncing(item)
        assert item.status == SYNC_STATUS_SYNCING
        assert item.attempt_count == 1
        assert item.last_attempt is not None

    def test_mark_synced_updates_status(self, session):
        repo = SyncQueueRepository(session)
        item = repo.enqueue(entity_type="product", entity_id=1, operation="CREATE", payload={})
        session.flush()
        repo.mark_synced(item)
        assert item.status == SYNC_STATUS_SYNCED
        assert item.synced_at is not None

    def test_mark_failed_updates_status(self, session):
        repo = SyncQueueRepository(session)
        item = repo.enqueue(entity_type="product", entity_id=1, operation="CREATE", payload={})
        session.flush()
        repo.mark_failed(item)
        assert item.status == SYNC_STATUS_FAILED

    def test_reset_failed_resets_to_pending(self, session):
        repo = SyncQueueRepository(session)
        item = repo.enqueue(entity_type="product", entity_id=1, operation="CREATE", payload={})
        session.flush()
        repo.mark_syncing(item)
        repo.mark_failed(item)
        repo.reset_failed(item)
        assert item.status == SYNC_STATUS_PENDING
        assert item.attempt_count == 0

    def test_clear_synced_removes_synced_entries(self, session):
        repo = SyncQueueRepository(session)
        item1 = repo.enqueue(entity_type="product", entity_id=1, operation="CREATE", payload={})
        item2 = repo.enqueue(entity_type="product", entity_id=2, operation="CREATE", payload={})
        session.flush()
        repo.mark_synced(item1)
        session.flush()
        count = repo.clear_synced()
        assert count == 1
        assert repo.get_by_id(item1.id) is None
        assert repo.get_by_id(item2.id) is not None

    def test_count_pending(self, session):
        repo = SyncQueueRepository(session)
        item1 = repo.enqueue(entity_type="product", entity_id=1, operation="CREATE", payload={})
        item2 = repo.enqueue(entity_type="product", entity_id=2, operation="CREATE", payload={})
        session.flush()
        assert repo.count_pending() == 2
        repo.mark_synced(item1)
        assert repo.count_pending() == 1

    def test_count_all(self, session):
        repo = SyncQueueRepository(session)
        repo.enqueue(entity_type="product", entity_id=1, operation="CREATE", payload={})
        repo.enqueue(entity_type="product", entity_id=2, operation="CREATE", payload={})
        session.flush()
        assert repo.count_all() == 2


# ---------------------------------------------------------------------------
# SyncStateRepository
# ---------------------------------------------------------------------------

class TestSyncStateRepository:
    """Sync cursor management."""

    def test_set_and_get_last_sync(self, session):
        repo = SyncStateRepository(session)
        now = datetime.now()
        repo.set_last_sync("device-A", now)
        session.flush()
        state = repo.get_by_device("device-A")
        assert state is not None
        assert state.last_sync_at == now

    def test_update_existing_last_sync(self, session):
        repo = SyncStateRepository(session)
        t1 = datetime(2026, 1, 1)
        t2 = datetime(2026, 6, 15)
        repo.set_last_sync("device-A", t1)
        session.flush()
        repo.set_last_sync("device-A", t2)
        session.flush()
        state = repo.get_by_device("device-A")
        assert state.last_sync_at == t2

    def test_get_missing_returns_none(self, session):
        repo = SyncStateRepository(session)
        assert repo.get_by_device("nonexistent") is None

    def test_list_all(self, session):
        repo = SyncStateRepository(session)
        repo.set_last_sync("device-A", datetime.now())
        repo.set_last_sync("device-B", datetime.now())
        session.flush()
        all_states = repo.list_all()
        assert len(all_states) == 2

    def test_increment_version(self, session):
        repo = SyncStateRepository(session)
        state = repo.increment_version("device-A")
        session.flush()
        assert state.sync_version == 1
        repo.increment_version("device-A")
        session.flush()
        state = repo.get_by_device("device-A")
        assert state.sync_version == 2


# ---------------------------------------------------------------------------
# DeviceIdentity
# ---------------------------------------------------------------------------

class TestDeviceIdentity:
    """File-based device UUID persistence."""

    def test_generates_new_uuid(self, tmp_path):
        device = DeviceIdentity(tmp_path)
        did = device.device_id
        assert len(did) == 36
        assert did.count("-") == 4

    def test_persists_and_reads_back(self, tmp_path):
        d1 = DeviceIdentity(tmp_path)
        first = d1.device_id
        d2 = DeviceIdentity(tmp_path)
        assert d2.device_id == first

    def test_reset_generates_new_id(self, tmp_path):
        d1 = DeviceIdentity(tmp_path)
        first = d1.device_id
        second = d1.reset()
        assert second != first
        assert d1.device_id == second


# ---------------------------------------------------------------------------
# SyncService
# ---------------------------------------------------------------------------

class TestSyncService:
    """Enqueue logic and fire-and-forget behavior."""

    def test_enqueue_create(self, session):
        svc = SyncService(session)
        svc.enqueue_create(ENTITY_PRODUCT, 42, {"name": "Widget"})
        session.flush()
        assert svc.has_pending()
        assert svc.pending_count() == 1

    def test_enqueue_update(self, session):
        svc = SyncService(session)
        svc.enqueue_update(ENTITY_CUSTOMER, 5, {"name": "Updated"})
        session.flush()
        items = SyncQueueRepository(session).get_pending()
        assert len(items) == 1
        assert items[0].operation == OP_UPDATE

    def test_enqueue_delete(self, session):
        svc = SyncService(session)
        svc.enqueue_delete(ENTITY_EXPENSE, 10, {"deleted": True})
        session.flush()
        items = SyncQueueRepository(session).get_pending()
        assert len(items) == 1
        assert items[0].operation == OP_DELETE

    def test_has_pending_false_when_empty(self, session):
        svc = SyncService(session)
        assert not svc.has_pending()
        assert svc.pending_count() == 0

    def test_total_count_includes_all_statuses(self, session):
        svc = SyncService(session)
        svc.enqueue_create(ENTITY_CATEGORY, 1, {"name": "A"})
        session.flush()
        items = SyncQueueRepository(session).get_pending()
        repo = SyncQueueRepository(session)
        repo.mark_synced(items[0])
        session.flush()
        assert svc.total_count() == 1
        assert svc.pending_count() == 0


# ---------------------------------------------------------------------------
# Service-level sync enqueue integration
# ---------------------------------------------------------------------------

class TestServiceSyncIntegration:
    """Verify that business services enqueue sync entries after mutations."""

    def _make_admin(self, session):
        return make_user(session, role=ROLE_ADMIN)

    def test_category_create_enqueues_sync(self, session):
        from app.domain.services.category_service import CategoryService
        admin = self._make_admin(session)
        svc = CategoryService(session)
        svc.create(admin, "Fashion")
        session.flush()
        pending = SyncQueueRepository(session).get_pending()
        sync_entries = [e for e in pending if e.entity_type == "category"]
        assert len(sync_entries) >= 1

    def test_category_rename_enqueues_sync(self, session):
        from app.domain.services.category_service import CategoryService
        admin = self._make_admin(session)
        svc = CategoryService(session)
        cat = svc.create(admin, "Fashion")
        session.flush()
        svc.rename(admin, cat.id, "Haute Couture")
        session.flush()
        pending = SyncQueueRepository(session).get_pending()
        sync_entries = [e for e in pending if e.entity_type == "category"]
        assert len(sync_entries) >= 2

    def test_customer_create_enqueues_sync(self, session):
        from app.domain.services.customer_service import CustomerService
        admin = self._make_admin(session)
        svc = CustomerService(session)
        svc.create(admin, name="Amina Yusuf")
        session.flush()
        pending = SyncQueueRepository(session).get_pending()
        sync_entries = [e for e in pending if e.entity_type == "customer"]
        assert len(sync_entries) >= 1

    def test_supplier_create_enqueues_sync(self, session):
        from app.domain.services.supplier_service import SupplierService
        admin = self._make_admin(session)
        svc = SupplierService(session)
        svc.create_supplier(admin, name="Acme Corp")
        session.flush()
        pending = SyncQueueRepository(session).get_pending()
        sync_entries = [e for e in pending if e.entity_type == "supplier"]
        assert len(sync_entries) >= 1

    def test_expense_create_enqueues_sync(self, session):
        from app.domain.services.expense_service import ExpenseService
        admin = self._make_admin(session)
        svc = ExpenseService(session)
        svc.create_expense(admin, category="Rent", amount=50000)
        session.flush()
        pending = SyncQueueRepository(session).get_pending()
        sync_entries = [e for e in pending if e.entity_type == "expense"]
        assert len(sync_entries) >= 1

    def test_product_create_enqueues_sync(self, session):
        from app.domain.services.product_service import ProductService
        from tests.factories import make_category
        admin = self._make_admin(session)
        cat = make_category(session)
        svc = ProductService(session)
        svc.create(
            admin, name="Gown", category=cat,
            cost_price=5000, selling_price=10000,
        )
        session.flush()
        pending = SyncQueueRepository(session).get_pending()
        sync_entries = [e for e in pending if e.entity_type == "product"]
        assert len(sync_entries) >= 1

    def test_sale_completes_enqueues_sync(self, session):
        from app.domain.services.sale_service import SaleService
        from tests.factories import make_category, make_customer, make_product
        admin = self._make_admin(session)
        cat = make_category(session)
        customer = make_customer(session)
        product = make_product(session, cat, quantity=20)
        session.flush()
        svc = SaleService(session)
        svc.complete_sale(
            admin,
            customer_id=customer.id,
            items=[{"product_id": product.id, "quantity": 2}],
            payment_method="TRANSFER",
        )
        session.flush()
        pending = SyncQueueRepository(session).get_pending()
        sync_types = {e.entity_type for e in pending}
        assert "sale" in sync_types
        assert "sale_item" in sync_types
        assert "payment" in sync_types
        assert "inventory_log" in sync_types
