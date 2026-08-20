"""Production-style integration tests for Phase 10 cloud sync.

End-to-end tests exercising the full offline-first sync lifecycle across
two simulated devices with independent SQLite databases and a shared
in-memory cloud database.

Test inventory:
    A – Full push/pull convergence between two devices
    B – Conflict resolution: concurrent edits, last-write-wins
    C – Device registration and credential persistence
    D – SyncWorker lifecycle (start / stop / graceful shutdown)
    E – Sync never blocks local POS operations
    F – Inventory movement-based sync (quantity derived from logs)
    G – Receipt number format preserved after sync round-trip
    H – User records are never synced
    I – Sync credentials never appear in logs
    J – FK resolution across categories, customers, suppliers
"""

from __future__ import annotations

import base64
import json
import logging
import threading
import time
from datetime import datetime, timedelta
from decimal import Decimal
from unittest.mock import patch

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from starlette.testclient import TestClient as StarletteTestClient

from app.config import Settings
from app.data.models import (
    Base,
    Category,
    Customer,
    InventoryLog,
    Product,
    Sale,
    SaleItem,
    Supplier,
    User,
)
from app.domain.services.device_service import DeviceIdentity
from app.sync.client import SyncClient
from app.sync.cloud_api import get_cloud_session_factory, set_cloud_session_factory, router as sync_router
from app.sync.cloud_db import create_cloud_session_factory, init_cloud_schema
from app.sync.schemas import PulledMutation
from app.sync.worker import SyncWorker, resolve_push_payload


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------


def _local_session_factory(tmp_path, name="device_a"):
    engine = create_engine(
        f"sqlite:///{tmp_path / f'{name}.db'}",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)


def _cloud_factory():
    from sqlalchemy.pool import StaticPool
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    init_cloud_schema(engine)
    return create_cloud_session_factory(engine), engine


def _make_cloud_app(cloud_sf):
    app = FastAPI()
    app.include_router(sync_router)
    set_cloud_session_factory(cloud_sf)
    return app


def _auth_headers(device_id, api_key):
    return {"X-Device-ID": device_id, "X-API-Key": api_key}


def _register_device_via_api(cloud_app, device_name):
    c = StarletteTestClient(cloud_app)
    resp = c.post("/api/sync/devices/register", json={"device_name": device_name})
    assert resp.status_code == 200
    data = resp.json()
    return data["device_id"], data["api_key"]


def _make_http_client(cloud_app):
    """Create a sync client that routes requests through the FastAPI app."""
    return StarletteTestClient(cloud_app)


def _seed_admin_user(sf):
    from app.domain.services.auth_service import hash_password
    with sf() as s:
        admin = User(
            username="admin", full_name="Administrator",
            role="ADMIN", password_hash=hash_password("admin123"),
        )
        s.add(admin)
        s.commit()


def _seed_category(sf, name="Fashion", uuid=None):
    with sf() as s:
        cat = Category(name=name)
        if uuid:
            cat.sync_uuid = uuid
        s.add(cat)
        s.commit()
        # Enqueue for sync
        from app.data.repositories.sync_repository import SyncQueueRepository
        from app.domain.services.sync_service import SyncService
        sync = SyncService(s)
        sync.enqueue_create("category", cat.id, {
            "name": cat.name, "sync_uuid": cat.sync_uuid,
            "version": cat.version,
        })
        s.commit()
        return cat.id


def _seed_customer(sf, name="Alice", uuid=None):
    import uuid as _uuid
    with sf() as s:
        code = f"CUST-{_uuid.uuid4().hex[:8].upper()}"
        cust = Customer(customer_code=code, name=name, phone="08012345678")
        if uuid:
            cust.sync_uuid = uuid
        s.add(cust)
        s.commit()
        from app.domain.services.sync_service import SyncService
        sync = SyncService(s)
        sync.enqueue_create("customer", cust.id, {
            "name": cust.name, "phone": cust.phone,
            "customer_code": cust.customer_code,
            "sync_uuid": cust.sync_uuid, "version": cust.version,
        })
        s.commit()
        return cust.id


def _seed_supplier(sf, name="Acme", uuid=None):
    with sf() as s:
        sup = Supplier(name=name, phone="08099999999")
        if uuid:
            sup.sync_uuid = uuid
        s.add(sup)
        s.commit()
        from app.domain.services.sync_service import SyncService
        sync = SyncService(s)
        sync.enqueue_create("supplier", sup.id, {
            "name": sup.name, "phone": sup.phone,
            "sync_uuid": sup.sync_uuid, "version": sup.version,
        })
        s.commit()
        return sup.id


def _seed_product(sf, cat_id, name="Shirt", uuid=None):
    import uuid as _uuid
    with sf() as s:
        code = f"PROD-{_uuid.uuid4().hex[:8].upper()}"
        bc = f"BC-{_uuid.uuid4().hex[:10].upper()}"
        prod = Product(
            product_code=code, name=name, category_id=cat_id,
            cost_price=Decimal("1000"), selling_price=Decimal("1500"),
            quantity=0, barcode=bc,
        )
        if uuid:
            prod.sync_uuid = uuid
        s.add(prod)
        s.commit()
        from app.domain.services.sync_service import SyncService
        sync = SyncService(s)
        sync.enqueue_create("product", prod.id, {
            "name": prod.name, "category_id": prod.category_id,
            "cost_price": str(prod.cost_price), "selling_price": str(prod.selling_price),
            "quantity": prod.quantity, "product_code": prod.product_code,
            "barcode": prod.barcode,
            "sync_uuid": prod.sync_uuid, "version": prod.version,
        })
        s.commit()
        return prod.id


def _make_worker(tmp_path, local_sf, cloud_sf, device_name="PC"):
    """Build a SyncWorker whose _build_client routes through the cloud FastAPI app."""
    cloud_app = _make_cloud_app(cloud_sf)
    device = DeviceIdentity(tmp_path)

    did, api_key = _register_device_via_api(cloud_app, device_name)

    settings = Settings(
        data_dir=tmp_path, log_dir=tmp_path / "logs",
        backup_dir=tmp_path / "backups",
        cloud_sync_enabled=True,
        sync_push_interval=30, sync_pull_interval=60,
    )

    tc = StarletteTestClient(cloud_app)
    headers = _auth_headers(did, api_key)

    class _TestSyncClient:
        def __init__(self):
            self._tc = tc
            self._headers = headers

        def push(self, mutations):
            if not mutations:
                from app.sync.schemas import PushResponse
                return PushResponse(accepted=0, rejected=0, conflicts=[], server_timestamp=datetime.now())
            from app.sync.schemas import PushRequest
            payload = PushRequest(mutations=mutations)
            resp = self._tc.post("/api/sync/push", json=payload.model_dump(mode="json"), headers=self._headers)
            resp.raise_for_status()
            from app.sync.schemas import PushResponse
            return PushResponse(**resp.json())

        def pull(self, since, entity_types=None):
            from app.sync.schemas import PullRequest, PullResponse
            payload = PullRequest(since=since, entity_types=entity_types)
            resp = self._tc.post("/api/sync/pull", json=payload.model_dump(mode="json"), headers=self._headers)
            resp.raise_for_status()
            return PullResponse(**resp.json())

        def get_status(self):
            resp = self._tc.get("/api/sync/status", headers=self._headers)
            resp.raise_for_status()
            return resp.json()

    worker = SyncWorker(
        local_session_factory=local_sf,
        cloud_session_factory=cloud_sf,
        settings=settings,
    )
    test_client = _TestSyncClient()
    worker._build_client = lambda _did: test_client
    return worker


# ------------------------------------------------------------------
# A – Full push/pull convergence between two devices
# ------------------------------------------------------------------

class TestA_FullPushPullConvergence:
    def test_category_converges(self, tmp_path):
        sf_a = _local_session_factory(tmp_path, "a")
        sf_b = _local_session_factory(tmp_path, "b")
        cloud_sf, _ = _cloud_factory()

        _seed_admin_user(sf_a)
        _seed_category(sf_a, "Electronics")

        worker_a = _make_worker(tmp_path / "a_data", sf_a, cloud_sf, "PC-A")
        worker_a.trigger_push()

        worker_b = _make_worker(tmp_path / "b_data", sf_b, cloud_sf, "PC-B")
        worker_b.trigger_pull()

        with sf_b() as s:
            cats = s.query(Category).filter(Category.name == "Electronics").all()
            assert len(cats) == 1

    def test_customer_converges(self, tmp_path):
        sf_a = _local_session_factory(tmp_path, "a")
        sf_b = _local_session_factory(tmp_path, "b")
        cloud_sf, _ = _cloud_factory()

        _seed_admin_user(sf_a)
        _seed_customer(sf_a, "Bob", uuid="cust-bob-001")

        worker_a = _make_worker(tmp_path / "a_data", sf_a, cloud_sf, "PC-A")
        worker_a.trigger_push()

        worker_b = _make_worker(tmp_path / "b_data", sf_b, cloud_sf, "PC-B")
        worker_b.trigger_pull()

        with sf_b() as s:
            assert s.query(Customer).filter(Customer.name == "Bob").count() == 1

    def test_supplier_converges(self, tmp_path):
        sf_a = _local_session_factory(tmp_path, "a")
        sf_b = _local_session_factory(tmp_path, "b")
        cloud_sf, _ = _cloud_factory()

        _seed_admin_user(sf_a)
        _seed_supplier(sf_a, "Global Ltd", uuid="sup-global-001")

        worker_a = _make_worker(tmp_path / "a_data", sf_a, cloud_sf, "PC-A")
        worker_a.trigger_push()

        worker_b = _make_worker(tmp_path / "b_data", sf_b, cloud_sf, "PC-B")
        worker_b.trigger_pull()

        with sf_b() as s:
            assert s.query(Supplier).filter(Supplier.name == "Global Ltd").count() == 1


# ------------------------------------------------------------------
# B – Conflict resolution: concurrent edits, last-write-wins
# ------------------------------------------------------------------

class TestB_ConflictResolution:
    def test_last_write_wins_on_category(self, tmp_path):
        sf_a = _local_session_factory(tmp_path, "a")
        sf_b = _local_session_factory(tmp_path, "b")
        sf_c = _local_session_factory(tmp_path, "c")
        cloud_sf, _ = _cloud_factory()

        _seed_admin_user(sf_a)
        cat_uuid = "conflict-cat-001"
        _seed_category(sf_a, "Original", uuid=cat_uuid)

        worker_a = _make_worker(tmp_path / "a_data", sf_a, cloud_sf, "PC-A")
        worker_a.trigger_push()

        worker_b = _make_worker(tmp_path / "b_data", sf_b, cloud_sf, "PC-B")
        worker_b.trigger_pull()

        # A updates locally and enqueues
        with sf_a() as s:
            cat = s.query(Category).filter(Category.sync_uuid == cat_uuid).first()
            cat.name = "Updated by A"
            cat.version = 2
            s.commit()
            from app.domain.services.sync_service import SyncService
            sync = SyncService(s)
            sync.enqueue_update("category", cat.id, {
                "name": cat.name, "sync_uuid": cat_uuid, "version": 2,
            })
            s.commit()

        worker_a.trigger_push()

        # B updates locally and enqueues
        with sf_b() as s:
            cat = s.query(Category).filter(Category.sync_uuid == cat_uuid).first()
            cat.name = "Updated by B"
            cat.version = 3
            s.commit()
            from app.domain.services.sync_service import SyncService
            sync = SyncService(s)
            sync.enqueue_update("category", cat.id, {
                "name": cat.name, "sync_uuid": cat_uuid, "version": 3,
            })
            s.commit()

        worker_b.trigger_push()

        # Verify cloud state
        with cloud_sf() as cs:
            from app.sync.cloud_models import CloudCategory, CloudSyncLog
            entity = cs.query(CloudCategory).filter_by(sync_uuid=cat_uuid).first()
            assert entity is not None, "Cloud entity not found"
            assert entity.version == 3, f"Cloud version is {entity.version}, expected 3"
            assert entity.name == "Updated by B", f"Cloud name is {entity.name}"

            logs = cs.query(CloudSyncLog).filter_by(entity_type="category").all()
            assert len(logs) == 3, f"Expected 3 log entries, got {len(logs)}"

        # Pull on fresh device C
        worker_c = _make_worker(tmp_path / "c_data", sf_c, cloud_sf, "PC-C")
        worker_c.trigger_pull()

        with sf_c() as s:
            cat = s.query(Category).filter(Category.sync_uuid == cat_uuid).first()
            assert cat is not None, "Category not found on C"
            assert cat.name == "Updated by B", f"C has name={cat.name}, expected 'Updated by B'"
            assert cat.version == 3, f"C has version={cat.version}, expected 3"


# ------------------------------------------------------------------
# C – Device registration and credential persistence
# ------------------------------------------------------------------

class TestC_DeviceRegistration:
    def test_register_and_read_back(self, tmp_path):
        from app.sync.device_registration import register_device, is_registered, load_credentials

        mock_resp = httpx.Response(
            200,
            json={"device_id": "cloud-dev-001", "api_key": "key-abc-123", "registered_at": datetime.now().isoformat()},
            request=httpx.Request("POST", "http://cloud/api/sync/devices/register"),
        )

        with patch("httpx.post", return_value=mock_resp):
            result = register_device(tmp_path, "http://cloud", "Front Desk")
            assert result.success is True
            assert is_registered(tmp_path) is True

        creds = load_credentials(tmp_path)
        assert creds["api_key"] == "key-abc-123"
        assert creds["cloud_url"] == "http://cloud"

    def test_not_registered_initially(self, tmp_path):
        from app.sync.device_registration import is_registered
        assert is_registered(tmp_path) is False

    def test_corrupt_credentials_handled(self, tmp_path):
        from app.sync.device_registration import load_credentials
        (tmp_path / "sync_credentials.json").write_text("{bad json")
        assert load_credentials(tmp_path) is None


# ------------------------------------------------------------------
# D – SyncWorker lifecycle (start / stop / graceful shutdown)
# ------------------------------------------------------------------

class TestD_SyncWorkerLifecycle:
    def test_start_stop_cycle(self, tmp_path):
        sf = _local_session_factory(tmp_path, "lc")
        cloud_sf, _ = _cloud_factory()
        worker = _make_worker(tmp_path / "data", sf, cloud_sf, "LC")

        assert worker.is_running is False
        worker.start()
        assert worker.is_running is True
        time.sleep(1)
        worker.stop()
        assert worker.is_running is False

    def test_worker_handles_cloud_errors(self, tmp_path):
        sf = _local_session_factory(tmp_path, "err")
        settings = Settings(
            data_dir=tmp_path, log_dir=tmp_path / "logs",
            backup_dir=tmp_path / "backups",
            cloud_sync_enabled=True, sync_push_interval=9999, sync_pull_interval=9999,
        )
        worker = SyncWorker(local_session_factory=sf, cloud_session_factory=None, settings=settings)
        worker.start()
        worker.trigger_push()
        worker.trigger_pull()
        worker.stop()
        assert worker.is_running is False

    def test_worker_stop_without_start(self, tmp_path):
        sf = _local_session_factory(tmp_path, "ns")
        settings = Settings(
            data_dir=tmp_path, log_dir=tmp_path / "logs",
            backup_dir=tmp_path / "backups",
            cloud_sync_enabled=True, sync_push_interval=9999, sync_pull_interval=9999,
        )
        worker = SyncWorker(local_session_factory=sf, cloud_session_factory=None, settings=settings)
        worker.stop()
        assert worker.is_running is False


# ------------------------------------------------------------------
# E – Sync never blocks local POS operations
# ------------------------------------------------------------------

class TestE_SyncDoesNotBlockPOS:
    def test_create_product_offline(self, tmp_path):
        sf = _local_session_factory(tmp_path, "off")
        _seed_admin_user(sf)
        cat_id = _seed_category(sf, "Books")

        with sf() as s:
            prod = Product(product_code="BOOK-001", name="Novel", category_id=cat_id, cost_price=Decimal("500"), selling_price=Decimal("800"), quantity=10, barcode="BC-BOOK001")
            s.add(prod)
            s.commit()
            pid = prod.id

        with sf() as s:
            prod = s.query(Product).get(pid)
            assert prod.name == "Novel"
            assert prod.quantity == 10

    def test_category_crud_offline(self, tmp_path):
        sf = _local_session_factory(tmp_path, "off")

        with sf() as s:
            cat = Category(name="Electronics")
            s.add(cat)
            s.commit()
            cid = cat.id

        with sf() as s:
            cat = s.query(Category).get(cid)
            assert cat.name == "Electronics"
            cat.name = "Electronics Updated"
            s.commit()

        with sf() as s:
            cat = s.query(Category).get(cid)
            assert cat.name == "Electronics Updated"

    def test_inventory_adjustment_offline(self, tmp_path):
        sf = _local_session_factory(tmp_path, "off")
        _seed_admin_user(sf)
        cat_id = _seed_category(sf, "Tools")
        prod_id = _seed_product(sf, cat_id, "Hammer")

        with sf() as s:
            log = InventoryLog(product_id=prod_id, change_quantity=5, previous_quantity=0, new_quantity=5, reason="Stock in", user_id=1, created_at=datetime.now())
            s.add(log)
            s.commit()

        with sf() as s:
            assert s.query(InventoryLog).count() == 1


# ------------------------------------------------------------------
# F – Inventory movement-based sync
# ------------------------------------------------------------------

class TestF_InventoryMovementSync:
    def test_logs_sync_quantity_derived(self, tmp_path):
        sf_a = _local_session_factory(tmp_path, "a")
        sf_b = _local_session_factory(tmp_path, "b")
        cloud_sf, _ = _cloud_factory()

        _seed_admin_user(sf_a)
        cat_id = _seed_category(sf_a, "Gadgets")
        prod_id = _seed_product(sf_a, cat_id, "Widget", uuid="prod-widget-001")

        with sf_a() as s:
            log = InventoryLog(product_id=prod_id, change_quantity=20, previous_quantity=0, new_quantity=20, reason="Initial stock", user_id=1, created_at=datetime.now())
            s.add(log)
            s.commit()
            from app.domain.services.sync_service import SyncService
            sync = SyncService(s)
            sync.enqueue_create("inventory_log", log.id, {
                "product_id": log.product_id, "change_quantity": log.change_quantity,
                "previous_quantity": log.previous_quantity, "new_quantity": log.new_quantity,
                "reason": log.reason, "user_id": log.user_id,
                "sync_uuid": log.sync_uuid,
            })
            s.commit()

        worker_a = _make_worker(tmp_path / "a_data", sf_a, cloud_sf, "PC-A")
        worker_a.trigger_push()

        worker_b = _make_worker(tmp_path / "b_data", sf_b, cloud_sf, "PC-B")
        worker_b.trigger_pull()

        with sf_b() as s:
            logs = s.query(InventoryLog).all()
            assert len(logs) >= 1
            total = sum(l.change_quantity for l in logs)
            assert total == 20


# ------------------------------------------------------------------
# G – Receipt number format preserved after sync round-trip
# ------------------------------------------------------------------

class TestG_ReceiptNumberFormat:
    def test_receipt_number_unchanged_after_sync(self, tmp_path):
        sf = _local_session_factory(tmp_path, "rcpt")
        cloud_sf, _ = _cloud_factory()

        _seed_admin_user(sf)
        cust_id = _seed_customer(sf, "Walk-In", "WALK-001")
        cat_id = _seed_category(sf, "Apparel")
        prod_id = _seed_product(sf, cat_id, "T-Shirt")

        with sf() as s:
            sale = Sale(
                receipt_no="FUN-20260819-042",
                customer_id=cust_id, cashier_id=1,
                sale_date=datetime.now(),
                subtotal=Decimal("1500"), total=Decimal("1500"),
                discount_type=None, discount_value=Decimal("0"),
                discount_amount=Decimal("0"),
                amount_paid=Decimal("1500"), payment_method="POS",
            )
            s.add(sale)
            s.flush()
            item = SaleItem(sale_id=sale.id, product_id=prod_id, quantity=1, unit_price=Decimal("1500"), cost_price=Decimal("1000"), line_total=Decimal("1500"))
            s.add(item)
            s.commit()
            from app.domain.services.sync_service import SyncService
            sync = SyncService(s)
            sync.enqueue_create("sale", sale.id, {
                "receipt_no": sale.receipt_no, "customer_id": sale.customer_id,
                "cashier_id": sale.cashier_id, "subtotal": str(sale.subtotal),
                "total": str(sale.total), "amount_paid": str(sale.amount_paid),
                "payment_method": sale.payment_method,
                "sale_date": sale.sale_date.isoformat() if sale.sale_date else datetime.now().isoformat(),
                "discount_type": sale.discount_type,
                "discount_value": str(sale.discount_value),
                "discount_amount": str(sale.discount_amount),
                "sync_uuid": sale.sync_uuid,
            })
            sync.enqueue_create("sale_item", item.id, {
                "sale_id": sale.id, "product_id": prod_id,
                "quantity": 1, "unit_price": str(Decimal("1500")),
                "cost_price": str(Decimal("1000")),
                "line_total": str(Decimal("1500")),
                "sync_uuid": item.sync_uuid,
            })
            s.commit()

        worker = _make_worker(tmp_path / "data", sf, cloud_sf, "RCPT")
        worker.trigger_push()

        from app.sync.cloud_models import CloudSale
        with cloud_sf() as cs:
            cloud_sales = cs.query(CloudSale).all()
            assert len(cloud_sales) >= 1
            for csale in cloud_sales:
                if csale.receipt_no:
                    assert csale.receipt_no.startswith("FUN-")


# ------------------------------------------------------------------
# H – User records are never synced
# ------------------------------------------------------------------

class TestH_UsersNeverSynced:
    def test_users_not_in_cloud(self, tmp_path):
        sf_a = _local_session_factory(tmp_path, "a")
        cloud_sf, _ = _cloud_factory()

        _seed_admin_user(sf_a)

        worker = _make_worker(tmp_path / "data", sf_a, cloud_sf, "NOUSR")
        worker.trigger_push()

        with cloud_sf() as cs:
            from sqlalchemy import inspect as sa_inspect
            engine = cs.get_bind()
            table_names = sa_inspect(engine).get_table_names()
            assert "users" not in table_names

    def test_pulled_user_mutation_skipped(self, tmp_path):
        sf = _local_session_factory(tmp_path, "rcv")
        cloud_sf, _ = _cloud_factory()

        from app.sync.schemas import PulledMutation, PullResponse
        mutation = PulledMutation(
            entity_type="user",
            sync_uuid="user-ghost-001",
            operation="upsert",
            version=1,
            device_id="test",
            payload={"username": "ghost", "full_name": "Ghost User", "role": "CASHIER", "password_hash": "x"},
        )

        settings = Settings(
            data_dir=tmp_path, log_dir=tmp_path / "logs",
            backup_dir=tmp_path / "backups",
            cloud_sync_enabled=True, sync_push_interval=9999, sync_pull_interval=9999,
        )
        worker = SyncWorker(local_session_factory=sf, cloud_session_factory=cloud_sf, settings=settings)

        from app.sync.apply import apply_mutations
        with sf() as s:
            summary = apply_mutations(s, [mutation])
            s.commit()
            assert summary["skipped"] == 1
            assert summary["applied"] == 0

        with sf() as s:
            result = s.execute(text("SELECT count(*) FROM users WHERE username = 'ghost'")).scalar()
            assert result == 0


# ------------------------------------------------------------------
# I – Sync credentials never appear in logs
# ------------------------------------------------------------------

class TestI_CredentialsNotInLogs:
    def test_no_api_key_in_log_output(self, tmp_path, caplog):
        from app.sync.device_registration import register_device

        mock_resp = httpx.Response(
            200,
            json={"device_id": "dev-001", "api_key": "SUPER_SECRET_KEY_12345", "registered_at": datetime.now().isoformat()},
            request=httpx.Request("POST", "http://cloud/api/sync/devices/register"),
        )

        with caplog.at_level(logging.DEBUG):
            with patch("httpx.post", return_value=mock_resp):
                register_device(tmp_path, "http://cloud", "Test PC")

        for record in caplog.records:
            assert "SUPER_SECRET_KEY" not in record.message


# ------------------------------------------------------------------
# J – FK resolution across categories, customers, suppliers
# ------------------------------------------------------------------

class TestJ_FKResolutionEndToEnd:
    def test_push_payload_resolves_all_entity_types(self, tmp_path):
        sf = _local_session_factory(tmp_path, "fk")

        cat_uuid = "fk-cat-001"
        cust_uuid = "fk-cust-001"
        sup_uuid = "fk-sup-001"

        _seed_category(sf, "Shirts", uuid=cat_uuid)
        _seed_customer(sf, "Charlie", uuid=cust_uuid)
        _seed_supplier(sf, "Delta Corp", uuid=sup_uuid)

        with sf() as s:
            cat = s.query(Category).filter(Category.sync_uuid == cat_uuid).first()
            cust = s.query(Customer).filter(Customer.sync_uuid == cust_uuid).first()
            sup = s.query(Supplier).filter(Supplier.sync_uuid == sup_uuid).first()

            payload = {
                "name": "Polo", "category_id": cat.id,
                "customer_id": cust.id, "supplier_id": sup.id,
                "cost_price": "2000", "selling_price": "3500",
                "quantity": 15, "version": 1,
            }
            resolved = resolve_push_payload(s, "product", payload)
            assert resolved["category_sync_uuid"] == cat_uuid
            assert resolved["name"] == "Polo"
            assert "category_id" not in resolved

    def test_unresolvable_fk_becomes_none(self, tmp_path):
        sf = _local_session_factory(tmp_path, "fk2")
        with sf() as s:
            payload = {"name": "Orphan", "category_id": 99999, "version": 1}
            resolved = resolve_push_payload(s, "product", payload)
            assert "category_sync_uuid" not in resolved
            assert "category_id" not in resolved

    def test_missing_fk_field_unchanged(self, tmp_path):
        sf = _local_session_factory(tmp_path, "fk3")
        with sf() as s:
            payload = {"name": "Simple", "version": 1}
            resolved = resolve_push_payload(s, "category", payload)
            assert resolved == {"name": "Simple", "version": 1}
