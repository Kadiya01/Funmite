"""Phase 2 / M3 — the decisive real-shop two-PC workflow gate.

SKIPPED unless ``FUNMITE_TEST_PG_URL`` points at a reachable PostgreSQL.

This is the gate that decides whether M3 is done. It is not a deployment
smoke test — it drives the real shop workflow end to end:

    catalog setup on PC-A  ->  push / pull to converge both PCs
    both PCs sell while "offline"
    reconnect -> both push + pull
    verify inventory, movements, receipts, and convergence on BOTH PCs
    verify backup independence from the cloud
    verify cloud/connection failure resilience (server down, retry later)

Everything runs through the REAL stack: a real uvicorn subprocess served by
``app.sync.cloud_api:app`` against PostgreSQL, real ``SyncClient`` /
``SyncWorker``, real ``register_device()``, real ``SaleService`` and real
``BackupService``. No TestClient stubs.
"""

from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path

import httpx
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.config import Settings
from app.data.db import create_db_engine, create_session_factory, session_scope
from app.data.migrations import runner
from app.data.models import (
    ROLE_ADMIN,
    Category,
    Customer,
    InventoryLog,
    Payment,
    Product,
    Sale,
    SyncQueueItem,
    User,
)
from app.domain.services.auth_service import hash_password
from app.domain.services.backup_service import BackupService
from app.domain.services.device_service import DeviceIdentity
from app.domain.services.sale_service import SaleService
from app.domain.services.sync_service import SyncService
from app.domain.session import CurrentUser
from app.sync.client import SyncClient
from app.sync.cloud_db import create_cloud_engine, create_cloud_session_factory, init_cloud_schema
from app.sync.device_registration import register_device
from app.sync.worker import SyncWorker

PG_URL = os.environ.get("FUNMITE_TEST_PG_URL")
PROJECT_ROOT = Path(__file__).resolve().parents[1]

pytestmark = pytest.mark.skipif(
    not PG_URL,
    reason="FUNMITE_TEST_PG_URL not set; requires a real PostgreSQL server",
)


class CloudServer:
    """A real uvicorn subprocess serving the cloud sync API against PostgreSQL."""

    def __init__(self, pg_url: str) -> None:
        self.pg_url = pg_url
        self.port = self._free_port()
        self.base_url = f"http://127.0.0.1:{self.port}"
        self.proc: subprocess.Popen | None = None

    @staticmethod
    def _free_port() -> int:
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            return s.getsockname()[1]

    def start(self) -> None:
        env = dict(os.environ, FUNMITE_CLOUD_DB_URL=self.pg_url, PYTHONPATH=".")
        self.proc = subprocess.Popen(
            [
                sys.executable, "-m", "uvicorn",
                "app.sync.cloud_api:app",
                "--host", "127.0.0.1", "--port", str(self.port),
                "--log-level", "warning",
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            cwd=str(PROJECT_ROOT),
            env=env,
        )
        deadline = time.monotonic() + 60
        while time.monotonic() < deadline:
            try:
                if httpx.get(f"{self.base_url}/openapi.json", timeout=2).status_code == 200:
                    return
            except httpx.HTTPError:
                time.sleep(0.5)
        self.stop()
        raise AssertionError("Cloud server subprocess failed to start")

    def stop(self) -> None:
        if self.proc is not None:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self.proc.kill()
            self.proc = None


@pytest.fixture(scope="module")
def cloud_server():
    srv = CloudServer(PG_URL)
    srv.start()
    yield srv
    srv.stop()


def _truncate_cloud(pg_url: str) -> None:
    from sqlalchemy import inspect as sa_inspect
    from sqlalchemy import text

    eng = create_cloud_engine(pg_url)
    init_cloud_schema(eng)
    with eng.begin() as conn:
        names = sa_inspect(eng).get_table_names()
        conn.execute(
            text(
                "TRUNCATE TABLE " + ", ".join(f'"{t}"' for t in names)
                + " RESTART IDENTITY CASCADE"
            )
        )
    eng.dispose()


@pytest.fixture()
def clean_cloud(cloud_server):
    _truncate_cloud(PG_URL)
    yield


def _local_datadir(tmp_path: Path, name: str) -> Path:
    data_dir = tmp_path / name
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir


def _bootstrap_local(data_dir: Path, name: str):
    engine = create_db_engine(data_dir / f"{name}.db")
    runner.upgrade(engine)
    return create_session_factory(engine), engine


def _seed_admin(sf) -> CurrentUser:
    with sf() as s:
        admin = User(
            username="admin", full_name="Administrator",
            role=ROLE_ADMIN, password_hash=hash_password("admin123"),
        )
        s.add(admin)
        s.commit()
        admin_id = admin.id
    return CurrentUser(
        user_id=admin_id, username="admin",
        full_name="Administrator", role=ROLE_ADMIN,
    )


def _seed_catalog(sf) -> None:
    import uuid as _uuid

    with sf() as s:
        cat = Category(name="Apparel", sync_uuid="cat-001")
        s.add(cat)
        s.flush()
        cat_id = cat.id
        sync = SyncService(s)
        sync.enqueue_create("category", cat.id, {
            "sync_uuid": "cat-001", "name": cat.name, "version": 1,
        })

        prod = Product(
            product_code="PROD-0001", name="Ankara Gown",
            category_id=cat_id, cost_price=Decimal("8000"),
            selling_price=Decimal("12000"), quantity=15,
            minimum_stock=3, barcode="BC-0000000001",
            is_active=True, sync_uuid="prod-001",
        )
        s.add(prod)
        s.flush()
        sync.enqueue_create("product", prod.id, {
            "sync_uuid": "prod-001",
            "product_code": prod.product_code, "name": prod.name,
            "category_id": prod.category_id, "brand": prod.brand,
            "size": prod.size, "color": prod.color,
            "cost_price": str(prod.cost_price),
            "selling_price": str(prod.selling_price),
            "quantity": prod.quantity, "minimum_stock": prod.minimum_stock,
            "barcode": prod.barcode, "is_active": prod.is_active,
            "version": 1,
        })

        customer = Customer(
            customer_code=f"CUST-{_uuid.uuid4().hex[:8].upper()}",
            name="Walk-in Customer", phone=None, sync_uuid="cus-001",
        )
        s.add(customer)
        s.flush()
        sync.enqueue_create("customer", customer.id, {
            "sync_uuid": "cus-001",
            "customer_code": customer.customer_code,
            "name": customer.name, "phone": customer.phone, "version": 1,
        })
        s.commit()


def _make_worker(data_dir: Path, local_sf, name: str) -> SyncWorker:
    settings = Settings(
        data_dir=data_dir, log_dir=data_dir / "logs",
        backup_dir=data_dir / "backups",
        cloud_sync_enabled=True,
        sync_push_interval=30, sync_pull_interval=60,
    )
    return SyncWorker(
        local_session_factory=local_sf,
        cloud_session_factory=local_sf,
        settings=settings,
    )


def _product_local_id(sf, sync_uuid: str) -> int:
    with sf() as s:
        return s.query(Product).filter(Product.sync_uuid == sync_uuid).first().id


def _customer_local_id(sf, sync_uuid: str) -> int:
    with sf() as s:
        return s.query(Customer).filter(Customer.sync_uuid == sync_uuid).first().id


def _local_sales(sf) -> list[Sale]:
    with sf() as s:
        return list(s.query(Sale).all())


def _local_qty(sf, sync_uuid: str) -> int:
    with sf() as s:
        return s.query(Product).filter(Product.sync_uuid == sync_uuid).first().quantity


def _cloud_counts(pg_url: str) -> dict:
    from app.sync.cloud_models import CloudPayment, CloudSale
    sf = create_cloud_session_factory(create_cloud_engine(pg_url))
    with sf() as s:
        sales = s.query(CloudSale).count()
        receipts = (
            s.query(CloudSale.receipt_no).distinct().count()
        )
        payments = s.query(CloudPayment).count()
    return {"sales": sales, "receipts": receipts, "payments": payments}


def _setup_pc(tmp_path: Path, name: str, cloud_url: str, device_label: str):
    data_dir = _local_datadir(tmp_path, name)
    sf, _eng = _bootstrap_local(data_dir, name)
    reg = register_device(data_dir, cloud_url, device_label)
    assert reg.success, reg.error
    admin = _seed_admin(sf)
    _seed_catalog(sf)
    return data_dir, sf, admin


class TestTwoPcShopWorkflow:
    def test_offline_sales_reconnect_and_converge(
        self, cloud_server, clean_cloud, tmp_path
    ):
        a_dir, sf_a, admin_a = _setup_pc(tmp_path, "pc_a", cloud_server.base_url, "PC-A")
        b_dir, sf_b, admin_b = _setup_pc(tmp_path, "pc_b", cloud_server.base_url, "PC-B")

        # Converge the catalog first: PC-A pushes, PC-B pulls.
        _make_worker(a_dir, sf_a, "PC-A").trigger_push()
        _make_worker(b_dir, sf_b, "PC-B").trigger_pull()

        with sf_b() as s:
            assert s.query(Product).filter(Product.sync_uuid == "prod-001").first().quantity == 15
            assert s.query(Customer).filter(Customer.sync_uuid == "cus-001").first() is not None

        # ---- OFFLINE: both PCs sell one unit without any syncing ----
        prod_a = _product_local_id(sf_a, "prod-001")
        cus_a = _customer_local_id(sf_a, "cus-001")
        with session_scope(sf_a) as s:
            sale_a = SaleService(s, DeviceIdentity(a_dir)).complete_sale(
                admin_a,
                customer_id=cus_a,
                items=[{"product_id": prod_a, "quantity": 1}],
                payment_method="POS",
            )

        prod_b = _product_local_id(sf_b, "prod-001")
        cus_b = _customer_local_id(sf_b, "cus-001")
        with session_scope(sf_b) as s:
            sale_b = SaleService(s, DeviceIdentity(b_dir)).complete_sale(
                admin_b,
                customer_id=cus_b,
                items=[{"product_id": prod_b, "quantity": 1}],
                payment_method="POS",
            )

        # Both PCs have now sold offline: each thinks stock is 14.
        assert _local_qty(sf_a, "prod-001") == 14
        assert _local_qty(sf_b, "prod-001") == 14

        # ---- RECONNECT: both push, both pull, then pull again ----
        wa = _make_worker(a_dir, sf_a, "PC-A")
        wb = _make_worker(b_dir, sf_b, "PC-B")
        wa.trigger_push()
        wb.trigger_push()
        wa.trigger_pull()
        wb.trigger_pull()
        wa.trigger_pull()
        wb.trigger_pull()

        # ---- Receipts: device-prefixed, each PC sees the other's ----
        a_sales = _local_sales(sf_a)
        b_sales = _local_sales(sf_b)
        assert len(a_sales) == 2
        assert len(b_sales) == 2
        a_receipts = {s.receipt_no for s in a_sales}
        b_receipts = {s.receipt_no for s in b_sales}
        assert sale_a.receipt_no in b_receipts
        assert sale_b.receipt_no in a_receipts
        assert a_receipts == b_receipts
        for r in a_receipts:
            assert r[:3] != "FUN-", r  # real device prefixes, not the fallback
            assert "-" in r and r.split("-")[1].isdigit()
        assert len(a_receipts & b_receipts) == 2

        # ---- Inventory convergence: true on-hand is 15 - 2 = 13 on BOTH ----
        assert _local_qty(sf_a, "prod-001") == 13
        assert _local_qty(sf_b, "prod-001") == 13

        # ---- Movements: both movement logs present on each PC ----
        for sf in (sf_a, sf_b):
            with sf() as s:
                logs = list(
                    s.query(InventoryLog).filter(InventoryLog.reason == "Sale").all()
                )
                assert len(logs) == 2, f"expected 2 movements, got {len(logs)}"
                assert sum(l.change_quantity for l in logs) == -2
                assert {l.reason for l in logs} == {"Sale"}

        # ---- Payments: both sale payments on both PCs ----
        for sf in (sf_a, sf_b):
            with sf() as s:
                assert s.query(Payment).count() == 2

        # ---- Cloud aggregation ----
        counts = _cloud_counts(PG_URL)
        assert counts["sales"] == 2
        assert counts["receipts"] == 2
        assert counts["payments"] == 2

        # ---- Backup independence from the cloud ----
        a_db = a_dir / "pc_a.db"
        with session_scope(sf_a) as s:
            result = BackupService(
                s, db_path=a_db, backup_dir=a_dir / "backups"
            ).create_backup(admin_a)
        assert result.success, result.error
        backup_path = Path(result.backup_path)
        with sf_a() as s:
            assert BackupService(
                s, db_path=a_db, backup_dir=a_dir / "backups"
            ).validate_backup(admin_a, backup_path) is True

        restored_engine = create_engine(f"sqlite:///{backup_path.as_posix()}")
        restored_sf = sessionmaker(bind=restored_engine)
        with restored_sf() as s:
            assert s.query(Sale).count() == 2
            assert s.query(Product).filter(Product.sync_uuid == "prod-001").first().quantity == 13
            assert {x.receipt_no for x in s.query(Sale).all()} == a_receipts
        restored_engine.dispose()

    def test_cloud_down_pos_still_sells_and_sync_retries(self, tmp_path):
        srv = CloudServer(PG_URL)
        srv.start()
        try:
            _truncate_cloud(PG_URL)
            a_dir = _local_datadir(tmp_path, "pc_c")
            sf, _ = _bootstrap_local(a_dir, "pc_c")
            reg = register_device(a_dir, srv.base_url, "PC-C")
            assert reg.success, reg.error
            admin = _seed_admin(sf)
            _seed_catalog(sf)

            prod_id = _product_local_id(sf, "prod-001")
            cus_id = _customer_local_id(sf, "cus-001")

            # ---- Cloud goes fully DOWN ----
            srv.stop()

            # POS still sells (offline-first guarantee).
            with session_scope(sf) as s:
                sale_c = SaleService(s, DeviceIdentity(a_dir)).complete_sale(
                    admin,
                    customer_id=cus_id,
                    items=[{"product_id": prod_id, "quantity": 1}],
                    payment_method="POS",
                )
            assert sale_c.receipt_no

            worker = _make_worker(a_dir, sf, "PC-C")

            # Direct HTTP push against the dead server fails gracefully.
            from app.sync.schemas import Mutation

            dead = SyncClient("http://127.0.0.1:1", "any-device", "any-key", timeout=2)
            assert dead.push([Mutation(
                entity_type="sale", operation="CREATE",
                sync_uuid="x", payload={}, device_id="any-device",
            )]) is None

            # Worker push while down: reports the error, queue stays PENDING.
            worker.trigger_push()
            assert worker.status["last_error"]
            with sf() as s:
                pending = s.query(SyncQueueItem).filter_by(status="PENDING").count()
                assert pending >= 1

            # ---- Cloud returns; the same worker retries and succeeds ----
            srv.start()
            worker.trigger_push()
            assert worker.status["last_error"] is None, worker.status

            counts = _cloud_counts(PG_URL)
            assert counts["sales"] == 1
            assert counts["receipts"] == 1
        finally:
            srv.stop()