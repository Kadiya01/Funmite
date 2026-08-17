"""Comprehensive tests for Phase 10C — Cloud Synchronization.

Covers:
    - Cloud schema creation
    - Device registration
    - Push synchronization (CREATE, UPDATE, DELETE)
    - Pull synchronization (incremental)
    - Idempotency (duplicate push protection)
    - Conflict detection/resolution (version-based)
    - Two-device convergence (Admin PC + Cashier PC)
    - Offline operation followed by sync-on-reconnect
    - Append-only entity sync (sales, payments, expenses, etc.)
    - Reference entity sync (categories, products, customers, suppliers)
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from decimal import Decimal

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import sessionmaker as sf_maker

from app.config import Settings
from app.data.db import create_db_engine, create_session_factory
from app.data.migrations import runner
from app.data.models import (
    Category,
    Customer,
    Expense,
    InventoryLog,
    Payment,
    Product,
    Purchase,
    PurchaseItem,
    ROLE_ADMIN,
    Sale,
    SaleItem,
    Supplier,
)
from app.sync.apply import apply_mutations
from app.sync.cloud_api import get_db, get_cloud_session_factory, router, set_cloud_session_factory
from app.sync.cloud_db import create_cloud_engine, init_cloud_schema
from app.sync.cloud_models import CloudCategory, CloudProduct, CloudSale, CloudSyncLog, DeviceRegistry
from app.sync.schemas import PulledMutation
from app.sync.worker import SyncWorker


# ------------------------------------------------------------------
# Fixtures
# ------------------------------------------------------------------


@pytest.fixture
def cloud_engine():
    eng = create_cloud_engine("sqlite:///:memory:")
    init_cloud_schema(eng)
    yield eng
    eng.dispose()


@pytest.fixture
def cloud_sf(cloud_engine):
    return sf_maker(bind=cloud_engine, expire_on_commit=False)


@pytest.fixture
def cloud_app(cloud_engine):
    sf = sf_maker(bind=cloud_engine, expire_on_commit=False)
    set_cloud_session_factory(sf)
    app = FastAPI()
    app.include_router(router)

    def override_get_db():
        session = sf()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    app.dependency_overrides[get_db] = override_get_db
    yield app
    set_cloud_session_factory(None)


@pytest.fixture
def cloud_client(cloud_app):
    return TestClient(cloud_app)


def _local_sf_factory(db_path_or_url=":memory:"):
    from sqlalchemy.pool import StaticPool
    if db_path_or_url == ":memory:":
        engine = create_engine(
            "sqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
    else:
        engine = create_db_engine(db_path_or_url)
    runner.upgrade(engine)
    return create_session_factory(engine), engine


def _register_device(cloud_client: TestClient, name: str = "Test PC"):
    resp = cloud_client.post("/api/sync/devices/register", json={"device_name": name})
    assert resp.status_code == 200
    data = resp.json()
    return data["device_id"], data["api_key"]


def _auth_headers(device_id: str, api_key: str):
    return {"X-Device-ID": device_id, "X-API-Key": api_key}


# ------------------------------------------------------------------
# Cloud schema
# ------------------------------------------------------------------


class TestCloudSchema:
    def test_cloud_tables_created(self, cloud_engine):
        inspector = inspect(cloud_engine)
        tables = set(inspector.get_table_names())
        assert "categories" in tables
        assert "products" in tables
        assert "customers" in tables
        assert "suppliers" in tables
        assert "sales" in tables
        assert "sale_items" in tables
        assert "payments" in tables
        assert "inventory_logs" in tables
        assert "purchases" in tables
        assert "purchase_items" in tables
        assert "expenses" in tables
        assert "exchanges" in tables
        assert "exchange_items" in tables
        assert "device_registry" in tables
        assert "sync_log" in tables

    def test_cloud_category_has_sync_uuid_pk(self, cloud_engine):
        inspector = inspect(cloud_engine)
        pk = inspector.get_pk_constraint("categories")
        pk_cols = [c for c in pk["constrained_columns"]]
        assert "sync_uuid" in pk_cols

    def test_cloud_sync_log_has_all_columns(self, cloud_engine):
        inspector = inspect(cloud_engine)
        cols = {c["name"] for c in inspector.get_columns("sync_log")}
        assert "entity_type" in cols
        assert "operation" in cols
        assert "sync_uuid" in cols
        assert "device_id" in cols
        assert "accepted" in cols
        assert "conflict_reason" in cols


# ------------------------------------------------------------------
# Device registration
# ------------------------------------------------------------------


class TestDeviceRegistration:
    def test_register_returns_credentials(self, cloud_client):
        did, api_key = _register_device(cloud_client, "Admin PC")
        assert len(did) == 36
        assert len(api_key) == 32

    def test_register_stores_in_db(self, cloud_client, cloud_sf):
        did, api_key = _register_device(cloud_client, "Admin PC")
        with cloud_sf() as s:
            dev = s.query(DeviceRegistry).filter_by(device_id=did).first()
            assert dev is not None
            assert dev.device_name == "Admin PC"
            assert dev.api_key == api_key
            assert dev.is_active is True

    def test_register_multiple_devices(self, cloud_client):
        d1, _ = _register_device(cloud_client, "Admin PC")
        d2, _ = _register_device(cloud_client, "Cashier PC")
        assert d1 != d2


# ------------------------------------------------------------------
# Auth
# ------------------------------------------------------------------


class TestAuth:
    def test_valid_credentials_accepted(self, cloud_client):
        did, api_key = _register_device(cloud_client)
        resp = cloud_client.get("/api/sync/status", headers=_auth_headers(did, api_key))
        assert resp.status_code == 200

    def test_invalid_credentials_rejected(self, cloud_client):
        resp = cloud_client.get(
            "/api/sync/status",
            headers=_auth_headers("fake-id", "fake-key"),
        )
        assert resp.status_code == 401

    def test_push_without_auth_rejected(self, cloud_client):
        resp = cloud_client.post("/api/sync/push", json={"mutations": []})
        assert resp.status_code == 422


# ------------------------------------------------------------------
# Push synchronization
# ------------------------------------------------------------------


class TestPushSync:
    def test_push_category(self, cloud_client, cloud_sf):
        did, api_key = _register_device(cloud_client)
        headers = _auth_headers(did, api_key)

        resp = cloud_client.post(
            "/api/sync/push",
            json={
                "mutations": [
                    {
                        "entity_type": "category",
                        "operation": "CREATE",
                        "sync_uuid": "cat-001",
                        "payload": {"name": "Fashion", "version": 1},
                        "version": 1,
                        "device_id": did,
                    }
                ]
            },
            headers=headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["accepted"] == 1
        assert data["rejected"] == 0

        with cloud_sf() as s:
            cat = s.get(CloudCategory, "cat-001")
            assert cat is not None
            assert cat.name == "Fashion"
            assert cat.device_id == did

    def test_push_product(self, cloud_client, cloud_sf):
        did, api_key = _register_device(cloud_client)
        headers = _auth_headers(did, api_key)

        resp = cloud_client.post(
            "/api/sync/push",
            json={
                "mutations": [
                    {
                        "entity_type": "product",
                        "operation": "CREATE",
                        "sync_uuid": "prd-001",
                        "payload": {
                            "product_code": "PRD-001",
                            "name": "Gown",
                            "category_sync_uuid": "cat-001",
                            "cost_price": 5000,
                            "selling_price": 10000,
                            "quantity": 10,
                            "minimum_stock": 3,
                            "barcode": "1234567890123",
                            "is_active": True,
                            "version": 1,
                        },
                        "version": 1,
                        "device_id": did,
                    }
                ]
            },
            headers=headers,
        )
        assert resp.status_code == 200
        assert resp.json()["accepted"] == 1

    def test_push_sale(self, cloud_client, cloud_sf):
        did, api_key = _register_device(cloud_client)
        headers = _auth_headers(did, api_key)

        resp = cloud_client.post(
            "/api/sync/push",
            json={
                "mutations": [
                    {
                        "entity_type": "sale",
                        "operation": "CREATE",
                        "sync_uuid": "sale-001",
                        "payload": {
                            "receipt_no": "FUN-20260101-001",
                            "customer_sync_uuid": "cus-001",
                            "cashier_name": "Admin",
                            "sale_date": "2026-01-01T10:00:00",
                            "subtotal": 10000,
                            "total": 10000,
                            "payment_method": "POS",
                            "amount_paid": 10000,
                        },
                        "version": 1,
                        "device_id": did,
                    }
                ]
            },
            headers=headers,
        )
        assert resp.status_code == 200
        assert resp.json()["accepted"] == 1

        with cloud_sf() as s:
            sale = s.get(CloudSale, "sale-001")
            assert sale is not None
            assert sale.receipt_no == "FUN-20260101-001"

    def test_push_empty_batch(self, cloud_client):
        did, api_key = _register_device(cloud_client)
        resp = cloud_client.post(
            "/api/sync/push",
            json={"mutations": []},
            headers=_auth_headers(did, api_key),
        )
        assert resp.status_code == 200
        assert resp.json()["accepted"] == 0

    def test_push_multiple_entities(self, cloud_client, cloud_sf):
        did, api_key = _register_device(cloud_client)
        headers = _auth_headers(did, api_key)

        mutations = [
            {
                "entity_type": "category",
                "operation": "CREATE",
                "sync_uuid": f"cat-{i:03d}",
                "payload": {"name": f"Category {i}", "version": 1},
                "version": 1,
                "device_id": did,
            }
            for i in range(5)
        ]

        resp = cloud_client.post(
            "/api/sync/push",
            json={"mutations": mutations},
            headers=headers,
        )
        assert resp.json()["accepted"] == 5


# ------------------------------------------------------------------
# Idempotency
# ------------------------------------------------------------------


class TestIdempotency:
    def test_duplicate_push_is_idempotent(self, cloud_client, cloud_sf):
        did, api_key = _register_device(cloud_client)
        headers = _auth_headers(did, api_key)

        mutation = {
            "entity_type": "category",
            "operation": "CREATE",
            "sync_uuid": "cat-001",
            "payload": {"name": "Fashion", "version": 1},
            "version": 1,
            "device_id": did,
        }

        cloud_client.post("/api/sync/push", json={"mutations": [mutation]}, headers=headers)
        resp2 = cloud_client.post("/api/sync/push", json={"mutations": [mutation]}, headers=headers)
        assert resp2.json()["accepted"] == 1

        with cloud_sf() as s:
            count = s.query(CloudCategory).count()
            assert count == 1

    def test_append_only_duplicate_is_skipped(self, cloud_client, cloud_sf):
        did, api_key = _register_device(cloud_client)
        headers = _auth_headers(did, api_key)

        mutation = {
            "entity_type": "sale",
            "operation": "CREATE",
            "sync_uuid": "sale-001",
            "payload": {
                "receipt_no": "FUN-20260101-001",
                "customer_sync_uuid": "cus-001",
                "cashier_name": "Admin",
                "sale_date": "2026-01-01T10:00:00",
                "subtotal": 5000,
                "total": 5000,
                "payment_method": "POS",
                "amount_paid": 5000,
            },
            "version": 1,
            "device_id": did,
        }

        cloud_client.post("/api/sync/push", json={"mutations": [mutation]}, headers=headers)
        resp = cloud_client.post("/api/sync/push", json={"mutations": [mutation]}, headers=headers)
        assert resp.json()["accepted"] == 1

        with cloud_sf() as s:
            assert s.query(CloudSale).count() == 1


# ------------------------------------------------------------------
# Conflict detection/resolution
# ------------------------------------------------------------------


class TestConflictResolution:
    def test_higher_version_wins(self, cloud_client, cloud_sf):
        did_a, api_a = _register_device(cloud_client, "PC-A")
        did_b, api_b = _register_device(cloud_client, "PC-B")

        cloud_client.post(
            "/api/sync/push",
            json={
                "mutations": [{
                    "entity_type": "category",
                    "operation": "CREATE",
                    "sync_uuid": "cat-001",
                    "payload": {"name": "Fashion", "version": 1},
                    "version": 1,
                    "device_id": did_a,
                }]
            },
            headers=_auth_headers(did_a, api_a),
        )

        resp = cloud_client.post(
            "/api/sync/push",
            json={
                "mutations": [{
                    "entity_type": "category",
                    "operation": "UPDATE",
                    "sync_uuid": "cat-001",
                    "payload": {"name": "Haute Couture", "version": 2},
                    "version": 2,
                    "device_id": did_b,
                }]
            },
            headers=_auth_headers(did_b, api_b),
        )
        assert resp.json()["accepted"] == 1

        with cloud_sf() as s:
            cat = s.get(CloudCategory, "cat-001")
            assert cat.name == "Haute Couture"
            assert cat.version == 2

    def test_stale_version_rejected(self, cloud_client, cloud_sf):
        did_a, api_a = _register_device(cloud_client, "PC-A")
        did_b, api_b = _register_device(cloud_client, "PC-B")

        cloud_client.post(
            "/api/sync/push",
            json={"mutations": [{
                "entity_type": "category", "operation": "CREATE",
                "sync_uuid": "cat-001",
                "payload": {"name": "Fashion", "version": 1},
                "version": 1, "device_id": did_a,
            }]},
            headers=_auth_headers(did_a, api_a),
        )
        cloud_client.post(
            "/api/sync/push",
            json={"mutations": [{
                "entity_type": "category", "operation": "UPDATE",
                "sync_uuid": "cat-001",
                "payload": {"name": "Couture", "version": 2},
                "version": 2, "device_id": did_b,
            }]},
            headers=_auth_headers(did_b, api_b),
        )

        resp = cloud_client.post(
            "/api/sync/push",
            json={"mutations": [{
                "entity_type": "category", "operation": "UPDATE",
                "sync_uuid": "cat-001",
                "payload": {"name": "Old Fashion", "version": 1},
                "version": 1, "device_id": did_a,
            }]},
            headers=_auth_headers(did_a, api_a),
        )
        data = resp.json()
        assert data["rejected"] == 1
        assert len(data["conflicts"]) == 1
        assert data["conflicts"][0]["reason"] == "stale_version"

    def test_same_version_last_write_wins(self, cloud_client, cloud_sf):
        did_a, api_a = _register_device(cloud_client, "PC-A")
        did_b, api_b = _register_device(cloud_client, "PC-B")
        now = datetime.now()

        cloud_client.post(
            "/api/sync/push",
            json={"mutations": [{
                "entity_type": "category", "operation": "CREATE",
                "sync_uuid": "cat-001",
                "payload": {"name": "Fashion", "version": 1},
                "version": 1, "device_id": did_a,
                "created_at": now.isoformat(),
            }]},
            headers=_auth_headers(did_a, api_a),
        )

        resp = cloud_client.post(
            "/api/sync/push",
            json={"mutations": [{
                "entity_type": "category", "operation": "UPDATE",
                "sync_uuid": "cat-001",
                "payload": {"name": "Haute Couture", "version": 1},
                "version": 1, "device_id": did_b,
                "created_at": (now + timedelta(seconds=10)).isoformat(),
            }]},
            headers=_auth_headers(did_b, api_b),
        )
        assert resp.json()["accepted"] == 1

        with cloud_sf() as s:
            cat = s.get(CloudCategory, "cat-001")
            assert cat.name == "Haute Couture"

    def test_same_version_older_timestamp_rejected(self, cloud_client, cloud_sf):
        did_a, api_a = _register_device(cloud_client, "PC-A")
        did_b, api_b = _register_device(cloud_client, "PC-B")
        now = datetime.now()

        cloud_client.post(
            "/api/sync/push",
            json={"mutations": [{
                "entity_type": "category", "operation": "CREATE",
                "sync_uuid": "cat-001",
                "payload": {"name": "Fashion New", "version": 1},
                "version": 1, "device_id": did_a,
                "created_at": now.isoformat(),
            }]},
            headers=_auth_headers(did_a, api_a),
        )

        resp = cloud_client.post(
            "/api/sync/push",
            json={"mutations": [{
                "entity_type": "category", "operation": "UPDATE",
                "sync_uuid": "cat-001",
                "payload": {"name": "Old Fashion", "version": 1},
                "version": 1, "device_id": did_b,
                "created_at": (now - timedelta(seconds=10)).isoformat(),
            }]},
            headers=_auth_headers(did_b, api_b),
        )
        data = resp.json()
        assert data["rejected"] == 1
        assert data["conflicts"][0]["reason"] == "same_version_older_timestamp"


# ------------------------------------------------------------------
# Pull synchronization
# ------------------------------------------------------------------


class TestPullSync:
    def test_pull_returns_pushed_mutations(self, cloud_client, cloud_sf):
        did_a, api_a = _register_device(cloud_client, "PC-A")
        did_b, api_b = _register_device(cloud_client, "PC-B")

        cloud_client.post(
            "/api/sync/push",
            json={"mutations": [{
                "entity_type": "category", "operation": "CREATE",
                "sync_uuid": "cat-001",
                "payload": {"name": "Fashion", "version": 1},
                "version": 1, "device_id": did_a,
            }]},
            headers=_auth_headers(did_a, api_a),
        )

        resp = cloud_client.post(
            "/api/sync/pull",
            json={"since": (datetime.now() - timedelta(hours=1)).isoformat()},
            headers=_auth_headers(did_b, api_b),
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["mutations"]) == 1
        assert data["mutations"][0]["sync_uuid"] == "cat-001"

    def test_pull_excludes_own_mutations(self, cloud_client):
        did, api_key = _register_device(cloud_client)
        headers = _auth_headers(did, api_key)

        cloud_client.post(
            "/api/sync/push",
            json={"mutations": [{
                "entity_type": "category", "operation": "CREATE",
                "sync_uuid": "cat-001",
                "payload": {"name": "Fashion", "version": 1},
                "version": 1, "device_id": did,
            }]},
            headers=headers,
        )

        resp = cloud_client.post(
            "/api/sync/pull",
            json={"since": (datetime.now() - timedelta(hours=1)).isoformat()},
            headers=headers,
        )
        assert len(resp.json()["mutations"]) == 0

    def test_pull_with_entity_type_filter(self, cloud_client):
        did_a, api_a = _register_device(cloud_client, "PC-A")
        did_b, api_b = _register_device(cloud_client, "PC-B")

        cloud_client.post(
            "/api/sync/push",
            json={"mutations": [
                {
                    "entity_type": "category", "operation": "CREATE",
                    "sync_uuid": "cat-001",
                    "payload": {"name": "Fashion", "version": 1},
                    "version": 1, "device_id": did_a,
                },
                {
                    "entity_type": "product", "operation": "CREATE",
                    "sync_uuid": "prd-001",
                    "payload": {"name": "Gown", "product_code": "P001", "barcode": "B001", "version": 1},
                    "version": 1, "device_id": did_a,
                },
            ]},
            headers=_auth_headers(did_a, api_a),
        )

        resp = cloud_client.post(
            "/api/sync/pull",
            json={
                "since": (datetime.now() - timedelta(hours=1)).isoformat(),
                "entity_types": ["category"],
            },
            headers=_auth_headers(did_b, api_b),
        )
        mutations = resp.json()["mutations"]
        assert len(mutations) == 1
        assert mutations[0]["entity_type"] == "category"

    def test_pull_since_timestamp_filters(self, cloud_client):
        did_a, api_a = _register_device(cloud_client, "PC-A")
        did_b, api_b = _register_device(cloud_client, "PC-B")

        cloud_client.post(
            "/api/sync/push",
            json={"mutations": [{
                "entity_type": "category", "operation": "CREATE",
                "sync_uuid": "cat-001",
                "payload": {"name": "Fashion", "version": 1},
                "version": 1, "device_id": did_a,
            }]},
            headers=_auth_headers(did_a, api_a),
        )

        future = datetime.now() + timedelta(hours=1)
        resp = cloud_client.post(
            "/api/sync/pull",
            json={"since": future.isoformat()},
            headers=_auth_headers(did_b, api_b),
        )
        assert len(resp.json()["mutations"]) == 0


# ------------------------------------------------------------------
# Apply pulled mutations to local DB
# ------------------------------------------------------------------


class TestApplyMutations:
    def _make_session(self):
        engine = create_db_engine(":memory:")
        runner.upgrade(engine)
        sf = create_session_factory(engine)
        return sf()

    def test_apply_category(self):
        s = self._make_session()
        mutations = [PulledMutation(
            entity_type="category", operation="CREATE",
            sync_uuid="cat-001",
            payload={"name": "Fashion", "version": 1},
            version=1, device_id="device-a",
        )]
        result = apply_mutations(s, mutations)
        assert result["applied"] == 1
        s.flush()
        cat = s.query(Category).filter_by(sync_uuid="cat-001").first()
        assert cat is not None
        assert cat.name == "Fashion"
        s.close()

    def test_apply_product(self):
        s = self._make_session()
        mutations = [
            PulledMutation(
                entity_type="category", operation="CREATE",
                sync_uuid="cat-001",
                payload={"name": "Fashion", "version": 1},
                version=1, device_id="device-a",
            ),
            PulledMutation(
                entity_type="product", operation="CREATE",
                sync_uuid="prd-001",
                payload={
                    "product_code": "PRD-001", "name": "Gown",
                    "category_sync_uuid": "cat-001",
                    "cost_price": 5000, "selling_price": 10000,
                    "quantity": 10, "minimum_stock": 3,
                    "barcode": "1234567890123", "is_active": True, "version": 1,
                },
                version=1, device_id="device-a",
            ),
        ]
        result = apply_mutations(s, mutations)
        assert result["applied"] == 2
        s.flush()
        prd = s.query(Product).filter_by(sync_uuid="prd-001").first()
        assert prd is not None
        assert prd.name == "Gown"
        s.close()

    def test_apply_customer(self):
        s = self._make_session()
        mutations = [PulledMutation(
            entity_type="customer", operation="CREATE",
            sync_uuid="cus-001",
            payload={"customer_code": "CUS-001", "name": "Amina Yusuf", "phone": "08012345678", "version": 1},
            version=1, device_id="device-a",
        )]
        result = apply_mutations(s, mutations)
        assert result["applied"] == 1
        s.flush()
        cus = s.query(Customer).filter_by(sync_uuid="cus-001").first()
        assert cus is not None
        assert cus.name == "Amina Yusuf"
        s.close()

    def test_apply_supplier(self):
        s = self._make_session()
        mutations = [PulledMutation(
            entity_type="supplier", operation="CREATE",
            sync_uuid="sup-001",
            payload={"name": "Acme Corp", "version": 1},
            version=1, device_id="device-a",
        )]
        result = apply_mutations(s, mutations)
        assert result["applied"] == 1
        s.flush()
        sup = s.query(Supplier).filter_by(sync_uuid="sup-001").first()
        assert sup is not None
        s.close()

    def test_idempotent_apply(self):
        s = self._make_session()
        mutations = [PulledMutation(
            entity_type="category", operation="CREATE",
            sync_uuid="cat-001",
            payload={"name": "Fashion", "version": 1},
            version=1, device_id="device-a",
        )]
        apply_mutations(s, mutations)
        s.flush()
        result = apply_mutations(s, mutations)
        assert result["skipped"] == 1
        count = s.query(Category).filter_by(sync_uuid="cat-001").count()
        assert count == 1
        s.close()

    def test_reference_version_wins(self):
        s = self._make_session()
        apply_mutations(s, [PulledMutation(
            entity_type="category", operation="CREATE",
            sync_uuid="cat-001",
            payload={"name": "Fashion", "version": 1},
            version=1, device_id="device-a",
        )])
        s.flush()

        result = apply_mutations(s, [PulledMutation(
            entity_type="category", operation="UPDATE",
            sync_uuid="cat-001",
            payload={"name": "Haute Couture", "version": 2},
            version=2, device_id="device-b",
        )])
        assert result["applied"] == 1
        s.flush()
        cat = s.query(Category).filter_by(sync_uuid="cat-001").first()
        assert cat.name == "Haute Couture"
        s.close()

    def test_reference_stale_version_rejected(self):
        s = self._make_session()
        apply_mutations(s, [PulledMutation(
            entity_type="category", operation="CREATE",
            sync_uuid="cat-001",
            payload={"name": "Couture", "version": 2},
            version=2, device_id="device-b",
        )])
        s.flush()

        result = apply_mutations(s, [PulledMutation(
            entity_type="category", operation="UPDATE",
            sync_uuid="cat-001",
            payload={"name": "Old Fashion", "version": 1},
            version=1, device_id="device-a",
        )])
        assert result["conflicts"] == 1
        s.flush()
        cat = s.query(Category).filter_by(sync_uuid="cat-001").first()
        assert cat.name == "Couture"
        s.close()


# ------------------------------------------------------------------
# Two-device convergence
# ------------------------------------------------------------------


class TestTwoDeviceConvergence:
    def test_offline_operations_sync_on_reconnect(self, cloud_client, cloud_sf):
        """Critical scenario: both PCs offline, operate, reconnect, sync, converge."""
        local_sf_a, engine_a = _local_sf_factory()
        local_sf_b, engine_b = _local_sf_factory()

        did_a, api_a = _register_device(cloud_client, "Admin PC")
        did_b, api_b = _register_device(cloud_client, "Cashier PC")
        headers_a = _auth_headers(did_a, api_a)
        headers_b = _auth_headers(did_b, api_b)

        # Push initial shared data
        cloud_client.post(
            "/api/sync/push",
            json={"mutations": [
                {
                    "entity_type": "category", "operation": "CREATE",
                    "sync_uuid": "cat-gown",
                    "payload": {"name": "Gowns", "version": 1},
                    "version": 1, "device_id": did_a,
                },
                {
                    "entity_type": "product", "operation": "CREATE",
                    "sync_uuid": "prd-lace",
                    "payload": {
                        "product_code": "PRD-001", "name": "Lace Gown",
                        "category_sync_uuid": "cat-gown",
                        "cost_price": 5000, "selling_price": 12000,
                        "quantity": 15, "minimum_stock": 3,
                        "barcode": "BAR001", "is_active": True, "version": 1,
                    },
                    "version": 1, "device_id": did_a,
                },
                {
                    "entity_type": "customer", "operation": "CREATE",
                    "sync_uuid": "cus-fati",
                    "payload": {
                        "customer_code": "CUS-001", "name": "Fatima Bello",
                        "phone": "08011112222", "version": 1,
                    },
                    "version": 1, "device_id": did_a,
                },
            ]},
            headers=headers_a,
        )

        since = (datetime.now() - timedelta(hours=1)).isoformat()

        # Admin PC already has data locally (it was the source), seed it directly
        with local_sf_a() as s:
            cat = Category(name="Gowns", sync_uuid="cat-gown", version=1)
            s.add(cat)
            s.flush()
            s.add(Product(
                product_code="PRD-001", name="Lace Gown", sync_uuid="prd-lace",
                category_id=cat.id, cost_price=5000, selling_price=12000,
                quantity=15, minimum_stock=3, barcode="BAR001", is_active=True, version=1,
            ))
            s.add(Customer(
                customer_code="CUS-001", name="Fatima Bello", phone="08011112222",
                sync_uuid="cus-fati", version=1,
            ))
            s.commit()

        # Cashier PC pulls initial data from cloud
        resp_b = cloud_client.post("/api/sync/pull", json={"since": since}, headers=headers_b)

        with local_sf_b() as s:
            apply_mutations(s, [PulledMutation(**m) for m in resp_b.json()["mutations"]])
            s.commit()

        # Verify both have initial data
        with local_sf_a() as s:
            assert s.query(Category).filter_by(sync_uuid="cat-gown").first() is not None
            assert s.query(Product).filter_by(sync_uuid="prd-lace").first() is not None

        with local_sf_b() as s:
            assert s.query(Category).filter_by(sync_uuid="cat-gown").first() is not None
            assert s.query(Product).filter_by(sync_uuid="prd-lace").first() is not None

        # --- OFFLINE PERIOD ---
        # Admin creates new category + customer
        with local_sf_a() as s:
            s.add(Category(name="Ankara", sync_uuid="cat-ankara", version=1))
            s.add(Customer(customer_code="CUS-002", name="Amina Yusuf", phone="08022223333", sync_uuid="cus-amina", version=1))
            s.commit()

        # Cashier creates a new sale (requires valid local FK ids)
        with local_sf_b() as s:
            local_cus = s.query(Customer).filter_by(sync_uuid="cus-fati").first()
            local_prd = s.query(Product).filter_by(sync_uuid="prd-lace").first()
            s.add(Sale(
                receipt_no="PCB-20260817-001",
                customer_id=local_cus.id,
                cashier_id=1,
                sale_date=datetime.now(),
                subtotal=Decimal("12000"), total=Decimal("12000"),
                payment_method="POS", amount_paid=Decimal("12000"),
                sync_uuid="sale-offline-001",
            ))
            s.commit()

        # --- RECONNECT: BOTH PUSH ---
        cloud_client.post(
            "/api/sync/push",
            json={"mutations": [
                {
                    "entity_type": "category", "operation": "CREATE",
                    "sync_uuid": "cat-ankara",
                    "payload": {"name": "Ankara", "version": 1},
                    "version": 1, "device_id": did_a,
                },
                {
                    "entity_type": "customer", "operation": "CREATE",
                    "sync_uuid": "cus-amina",
                    "payload": {
                        "customer_code": "CUS-002", "name": "Amina Yusuf",
                        "phone": "08022223333", "version": 1,
                    },
                    "version": 1, "device_id": did_a,
                },
            ]},
            headers=headers_a,
        )

        cloud_client.post(
            "/api/sync/push",
            json={"mutations": [{
                "entity_type": "sale", "operation": "CREATE",
                "sync_uuid": "sale-offline-001",
                "payload": {
                    "receipt_no": "PCB-20260817-001",
                    "customer_sync_uuid": "cus-fati",
                    "cashier_name": "Cashier",
                    "sale_date": datetime.now().isoformat(),
                    "subtotal": 12000, "total": 12000,
                    "payment_method": "POS", "amount_paid": 12000,
                },
                "version": 1, "device_id": did_b,
            }]},
            headers=headers_b,
        )

        # --- BOTH PULL TO CONVERGE ---
        since2 = (datetime.now() - timedelta(hours=1)).isoformat()
        resp_a = cloud_client.post("/api/sync/pull", json={"since": since2}, headers=headers_a)
        resp_b = cloud_client.post("/api/sync/pull", json={"since": since2}, headers=headers_b)

        with local_sf_a() as s:
            apply_mutations(s, [PulledMutation(**m) for m in resp_a.json()["mutations"]])
            s.commit()

        with local_sf_b() as s:
            apply_mutations(s, [PulledMutation(**m) for m in resp_b.json()["mutations"]])
            s.commit()

        # --- VERIFY CONVERGENCE ---
        # Admin PC has the Cashier's sale
        with local_sf_a() as s:
            assert s.query(Sale).filter_by(sync_uuid="sale-offline-001").first() is not None

        # Cashier PC has Admin's new category and customer
        with local_sf_b() as s:
            assert s.query(Category).filter_by(sync_uuid="cat-ankara").first() is not None
            assert s.query(Customer).filter_by(sync_uuid="cus-amina").first() is not None

        # Both have original shared data
        for sf in [local_sf_a, local_sf_b]:
            with sf() as s:
                assert s.query(Category).filter_by(sync_uuid="cat-gown").first() is not None
                assert s.query(Product).filter_by(sync_uuid="prd-lace").first() is not None
                assert s.query(Customer).filter_by(sync_uuid="cus-fati").first() is not None

        engine_a.dispose()
        engine_b.dispose()

    def test_concurrent_same_entity_conflict_resolved(self, cloud_client, cloud_sf):
        did_a, api_a = _register_device(cloud_client, "Admin PC")
        did_b, api_b = _register_device(cloud_client, "Cashier PC")

        # Admin creates product at v1
        cloud_client.post(
            "/api/sync/push",
            json={"mutations": [{
                "entity_type": "product", "operation": "CREATE",
                "sync_uuid": "prd-gown",
                "payload": {
                    "product_code": "PRD-001", "name": "Lace Gown",
                    "cost_price": 5000, "selling_price": 12000,
                    "quantity": 10, "minimum_stock": 3,
                    "barcode": "BAR001", "is_active": True, "version": 1,
                },
                "version": 1, "device_id": did_a,
            }]},
            headers=_auth_headers(did_a, api_a),
        )

        # Both update at version 2
        resp_a = cloud_client.post(
            "/api/sync/push",
            json={"mutations": [{
                "entity_type": "product", "operation": "UPDATE",
                "sync_uuid": "prd-gown",
                "payload": {
                    "product_code": "PRD-001", "name": "Designer Lace Gown",
                    "cost_price": 5000, "selling_price": 15000,
                    "quantity": 10, "minimum_stock": 3,
                    "barcode": "BAR001", "is_active": True, "version": 2,
                },
                "version": 2, "device_id": did_a,
            }]},
            headers=_auth_headers(did_a, api_a),
        )
        assert resp_a.json()["accepted"] == 1

        resp_b = cloud_client.post(
            "/api/sync/push",
            json={"mutations": [{
                "entity_type": "product", "operation": "UPDATE",
                "sync_uuid": "prd-gown",
                "payload": {
                    "product_code": "PRD-001", "name": "Lace Gown",
                    "cost_price": 5000, "selling_price": 13000,
                    "quantity": 10, "minimum_stock": 3,
                    "barcode": "BAR001", "is_active": True, "version": 2,
                },
                "version": 2, "device_id": did_b,
            }]},
            headers=_auth_headers(did_b, api_b),
        )
        # Same version: one accepted (last-write-wins), one rejected
        result_b = resp_b.json()
        assert result_b["accepted"] + result_b["rejected"] == 1

        with cloud_sf() as s:
            prd = s.query(CloudProduct).filter_by(sync_uuid="prd-gown").first()
            assert prd is not None
            assert prd.version == 2


# ------------------------------------------------------------------
# DELETE operations
# ------------------------------------------------------------------


class TestDeleteSync:
    def test_delete_category(self, cloud_client, cloud_sf):
        did, api_key = _register_device(cloud_client)
        headers = _auth_headers(did, api_key)

        cloud_client.post(
            "/api/sync/push",
            json={"mutations": [{
                "entity_type": "category", "operation": "CREATE",
                "sync_uuid": "cat-001",
                "payload": {"name": "Temp", "version": 1},
                "version": 1, "device_id": did,
            }]},
            headers=headers,
        )

        resp = cloud_client.post(
            "/api/sync/push",
            json={"mutations": [{
                "entity_type": "category", "operation": "DELETE",
                "sync_uuid": "cat-001",
                "payload": {},
                "version": 2, "device_id": did,
            }]},
            headers=headers,
        )
        assert resp.json()["accepted"] == 1

        with cloud_sf() as s:
            cat = s.get(CloudCategory, "cat-001")
            assert cat is None


# ------------------------------------------------------------------
# Sync worker
# ------------------------------------------------------------------


class TestSyncWorker:
    def test_worker_start_stop(self):
        engine = create_db_engine(":memory:")
        runner.upgrade(engine)
        sf = create_session_factory(engine)
        worker = SyncWorker(sf, None, Settings(), push_interval=1, pull_interval=1)
        assert not worker.is_running
        worker.start()
        assert worker.is_running
        worker.stop()
        assert not worker.is_running
        engine.dispose()

    def test_worker_status(self):
        engine = create_db_engine(":memory:")
        runner.upgrade(engine)
        sf = create_session_factory(engine)
        worker = SyncWorker(sf, None, Settings())
        status = worker.status
        assert status["running"] is False
        assert status["syncing"] is False
        engine.dispose()


# ------------------------------------------------------------------
# Full round-trip
# ------------------------------------------------------------------


class TestFullRoundTrip:
    def test_push_then_pull_round_trip(self, cloud_client, cloud_sf):
        did_a, api_a = _register_device(cloud_client, "PC-A")
        did_b, api_b = _register_device(cloud_client, "PC-B")

        cloud_client.post(
            "/api/sync/push",
            json={"mutations": [{
                "entity_type": "category", "operation": "CREATE",
                "sync_uuid": "cat-roundtrip",
                "payload": {"name": "Roundtrip Cat", "version": 1},
                "version": 1, "device_id": did_a,
            }]},
            headers=_auth_headers(did_a, api_a),
        )

        resp = cloud_client.post(
            "/api/sync/pull",
            json={"since": (datetime.now() - timedelta(hours=1)).isoformat()},
            headers=_auth_headers(did_b, api_b),
        )
        pulled = resp.json()["mutations"]
        assert len(pulled) == 1
        assert pulled[0]["sync_uuid"] == "cat-roundtrip"
        assert pulled[0]["payload"]["name"] == "Roundtrip Cat"

    def test_push_all_entity_types(self, cloud_client, cloud_sf):
        did, api_key = _register_device(cloud_client)
        headers = _auth_headers(did, api_key)

        now_str = datetime.now().isoformat()
        entities = [
            ("category", "cat-001", {"name": "Test", "version": 1}),
            ("product", "prd-001", {
                "product_code": "P001", "name": "Test Prod",
                "cost_price": 100, "selling_price": 200,
                "quantity": 5, "minimum_stock": 3,
                "barcode": "BAR001", "is_active": True, "version": 1,
            }),
            ("customer", "cus-001", {"customer_code": "C001", "name": "Test", "version": 1}),
            ("supplier", "sup-001", {"name": "Test Supplier", "version": 1}),
            ("sale", "sale-001", {
                "receipt_no": "FUN-001", "customer_sync_uuid": "cus-001",
                "cashier_name": "Admin", "sale_date": now_str,
                "subtotal": 500, "total": 500, "payment_method": "POS", "amount_paid": 500,
            }),
            ("sale_item", "si-001", {
                "sale_sync_uuid": "sale-001", "product_sync_uuid": "prd-001",
                "quantity": 1, "unit_price": 500, "cost_price": 100, "line_total": 500,
            }),
            ("payment", "pay-001", {
                "sale_sync_uuid": "sale-001", "payment_method": "POS",
                "amount": 500, "payment_date": now_str, "recorded_by_name": "Admin",
            }),
            ("inventory_log", "ilog-001", {
                "product_sync_uuid": "prd-001", "change_quantity": -1,
                "previous_quantity": 5, "new_quantity": 4,
                "reason": "Sale", "user_name": "Admin",
            }),
            ("purchase", "purch-001", {
                "supplier_sync_uuid": "sup-001",
                "purchase_date": now_str, "total_cost": 1000,
                "amount_paid": 1000, "balance": 0, "created_by_name": "Admin",
            }),
            ("expense", "exp-001", {
                "category": "Rent", "amount": 50000,
                "expense_date": now_str, "created_by_name": "Admin",
            }),
        ]

        mutations = [
            {
                "entity_type": etype, "operation": "CREATE",
                "sync_uuid": uuid, "payload": payload,
                "version": 1, "device_id": did,
            }
            for etype, uuid, payload in entities
        ]

        resp = cloud_client.post(
            "/api/sync/push",
            json={"mutations": mutations},
            headers=headers,
        )
        assert resp.json()["accepted"] == len(entities)

    def test_sync_log_recorded(self, cloud_client, cloud_sf):
        did, api_key = _register_device(cloud_client)
        headers = _auth_headers(did, api_key)

        cloud_client.post(
            "/api/sync/push",
            json={"mutations": [{
                "entity_type": "category", "operation": "CREATE",
                "sync_uuid": "cat-001",
                "payload": {"name": "Test", "version": 1},
                "version": 1, "device_id": did,
            }]},
            headers=headers,
        )

        with cloud_sf() as s:
            logs = s.query(CloudSyncLog).all()
            assert len(logs) == 1
            assert logs[0].entity_type == "category"
            assert logs[0].operation == "CREATE"
            assert logs[0].accepted is True
