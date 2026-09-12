"""Phase 2 M2 — real PostgreSQL compatibility gate.

These tests are SKIPPED unless ``FUNMITE_TEST_PG_URL`` points at a reachable
PostgreSQL database (e.g. ``postgresql://user:pass@127.0.0.1:5432/dbname``).
They prove the cloud engine, schema bootstrap, API round-trip, and the
``receipt_no`` uniqueness guard all behave correctly against an actual
PostgreSQL server — not merely by installing the driver.
"""

from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import inspect, select, text

from app.sync.cloud_api import create_app, set_cloud_session_factory
from app.sync.cloud_db import create_cloud_engine, init_cloud_schema
from app.sync.cloud_models import CloudSale, CloudSaleItem

PG_URL = os.environ.get("FUNMITE_TEST_PG_URL")

pytestmark = pytest.mark.skipif(
    not PG_URL,
    reason="FUNMITE_TEST_PG_URL not set; requires a real PostgreSQL server",
)


@pytest.fixture
def pg_engine():
    eng = create_cloud_engine(PG_URL)
    init_cloud_schema(eng)
    with eng.begin() as conn:
        tables = inspect(eng).get_table_names()
        truncate_sql = (
            "TRUNCATE TABLE "
            + ", ".join(f'"{t}"' for t in tables)
            + " RESTART IDENTITY CASCADE"
        )
        conn.execute(text(truncate_sql))
    yield eng
    eng.dispose()


@pytest.fixture
def pg_client(pg_engine):
    sf = __import__("sqlalchemy.orm", fromlist=["sessionmaker"]).sessionmaker(
        bind=pg_engine, expire_on_commit=False
    )
    set_cloud_session_factory(sf)
    app = create_app(engine=pg_engine)

    from app.sync.cloud_api import get_db

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
    with TestClient(app) as client:
        yield client
    set_cloud_session_factory(None)


def _register_device(client: TestClient, name: str = "PG Test PC"):
    resp = client.post("/api/sync/devices/register", json={"device_name": name})
    assert resp.status_code == 200
    data = resp.json()
    return data["device_id"], data["api_key"]


def _auth(device_id: str, api_key: str):
    return {"X-Device-ID": device_id, "X-API-Key": api_key}


def _sale_mutation(sync_uuid, receipt_no, device_id):
    return {
        "entity_type": "sale",
        "operation": "CREATE",
        "sync_uuid": sync_uuid,
        "payload": {
            "receipt_no": receipt_no,
            "customer_sync_uuid": "cus-001",
            "cashier_name": "Admin",
            "sale_date": "2026-01-01T10:00:00",
            "subtotal": 9450,
            "total": 9450,
            "payment_method": "POS",
            "amount_paid": 10000,
        },
        "version": 1,
        "device_id": device_id,
    }


class TestPostgresqlCloudSchema:
    def test_cloud_schema_builds_on_postgresql(self, pg_engine):
        tables = set(inspect(pg_engine).get_table_names())
        for expected in (
            "categories",
            "products",
            "customers",
            "suppliers",
            "sales",
            "sale_items",
            "payments",
            "inventory_logs",
            "purchases",
            "purchase_items",
            "expenses",
            "exchanges",
            "exchange_items",
            "sync_log",
            "device_registry",
        ):
            assert expected in tables, f"missing cloud table on PostgreSQL: {expected}"


class TestPostgresqlApiRoundTrip:
    def test_push_pull_round_trip_on_postgresql(self, pg_engine, pg_client):
        did_a, key_a = _register_device(pg_client, "PG PC-A")
        did_b, key_b = _register_device(pg_client, "PG PC-B")

        receipt = "DEV000-20260101-001"
        push = pg_client.post(
            "/api/sync/push",
            json={
                "mutations": [
                    _sale_mutation("sale-pg-001", receipt, did_a),
                    {
                        "entity_type": "sale_item",
                        "operation": "CREATE",
                        "sync_uuid": "sale-item-pg-001",
                        "payload": {
                            "sale_sync_uuid": "sale-pg-001",
                            "product_sync_uuid": "prod-001",
                            "quantity": 1,
                            "unit_price": 9450,
                            "cost_price": 7000,
                            "line_total": 9450,
                        },
                        "version": 1,
                        "device_id": did_a,
                    },
                ]
            },
            headers=_auth(did_a, key_a),
        )
        assert push.status_code == 200, push.text
        assert push.json()["accepted"] == 2

        pull = pg_client.post(
            "/api/sync/pull",
            json={"entity_types": ["sale", "sale_item"], "since": "2020-01-01T00:00:00"},
            headers=_auth(did_b, key_b),
        )
        assert pull.status_code == 200, pull.text
        pulled = pull.json()["mutations"]
        assert len(pulled) == 2
        sale_muts = [m for m in pulled if m["entity_type"] == "sale"]
        assert any(m["payload"]["receipt_no"] == receipt for m in sale_muts)

    def test_datetime_and_numeric_round_trip_on_postgresql(self, pg_engine, pg_client):
        from datetime import datetime
        from decimal import Decimal

        did_a, key_a = _register_device(pg_client, "PG PC-A")
        resp = pg_client.post(
            "/api/sync/push",
            json={
                "mutations": [
                    _sale_mutation("sale-pg-002", "DEV000-20260101-002", did_a)
                ]
            },
            headers=_auth(did_a, key_a),
        )
        assert resp.status_code == 200, resp.text

        sf = __import__("sqlalchemy.orm", fromlist=["sessionmaker"]).sessionmaker(
            bind=pg_engine, expire_on_commit=False
        )
        with sf() as s:
            sale = s.get(CloudSale, "sale-pg-002")
            assert sale is not None
            assert isinstance(sale.sale_date, datetime)
            assert sale.subtotal == Decimal("9450.00")
            assert sale.total == Decimal("9450.00")
            assert sale.receipt_no == "DEV000-20260101-002"

    def test_postgresql_enforces_unique_receipt_no(self, pg_engine, pg_client):
        did_a, key_a = _register_device(pg_client, "PG PC-A")
        ok = pg_client.post(
            "/api/sync/push",
            json={"mutations": [_sale_mutation("sale-pg-003", "DEV000-20260101-003", did_a)]},
            headers=_auth(did_a, key_a),
        )
        assert ok.status_code == 200, ok.text

        dup = pg_client.post(
            "/api/sync/push",
            json={"mutations": [_sale_mutation("sale-pg-004", "DEV000-20260101-003", did_a)]},
            headers=_auth(did_a, key_a),
        )
        assert dup.status_code == 409, dup.text
        assert "Duplicate receipt_no" in dup.json()["detail"]

        sf = __import__("sqlalchemy.orm", fromlist=["sessionmaker"]).sessionmaker(
            bind=pg_engine, expire_on_commit=False
        )
        with sf() as s:
            rows = s.execute(
                select(CloudSale).where(CloudSale.receipt_no == "DEV000-20260101-003")
            ).scalars().all()
            assert len(rows) == 1, "unique receipt_no guard failed on PostgreSQL"