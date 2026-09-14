"""Phase 2 / M3 — hosted two-PC validation gate.

SKIPPED unless ``FUNMITE_HOSTED_URL`` points at the PUBLIC HTTPS URL of the
deployed cloud sync service (e.g. ``https://funmite-cloud-sync.onrender.com``).

This is the M3 hosted gate: the same real-shop workflow the local PG gate
drives, but against the public managed service and the live cloud database of
the two PCs. No deployment smoke-test shortcuts:

    /healthz reachable (200) on the hosted service
    PC-A registers with the hosted service, seeds catalog, pushes
    PC-B registers, pulls, catalog converges
    both PCs sell while "offline"
    reconnect -> both push + pull
    verify inventory convergence, movements, receipts, and uniqueness on BOTH
    PCs, scoped to THIS run (unique product sync_uuid) so the test is
    re-runnable on a shared hosted database

All assertions are PC-side; the cloud PostgreSQL is never touched with
credentials. Device credentials stay in per-PC data dirs (never in git).
"""

from __future__ import annotations

import os
import uuid
from decimal import Decimal
from pathlib import Path

import httpx
import pytest

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
    SaleItem,
    User,
)
from app.domain.services.auth_service import hash_password
from app.domain.services.device_service import DeviceIdentity
from app.domain.services.sale_service import SaleService
from app.domain.services.sync_service import SyncService
from app.domain.session import CurrentUser
from app.sync.device_registration import register_device
from app.sync.worker import SyncWorker

HOSTED_URL = (os.environ.get("FUNMITE_HOSTED_URL") or "").rstrip("/")

pytestmark = pytest.mark.skipif(
    not HOSTED_URL,
    reason="FUNMITE_HOSTED_URL not set; requires the deployed cloud service",
)


def _local_datadir(tmp_path: Path, name: str) -> Path:
    data_dir = tmp_path / name
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir


def _bootstrap_local(data_dir: Path, name: str):
    engine = create_db_engine(data_dir / f"{name}.db")
    runner.upgrade(engine)
    return create_session_factory(engine)


def _seed_admin(sf) -> CurrentUser:
    with sf() as s:
        admin = User(
            username="admin", full_name="Administrator",
            role=ROLE_ADMIN, password_hash=hash_password("admin123"),
        )
        s.add(admin)
        s.commit()
        admin_id = admin.id
    return CurrentUser(user_id=admin_id, username="admin", full_name="Administrator", role=ROLE_ADMIN)


def _seed_catalog(sf, run: str) -> None:
    """Seed a catalog whose sync ids are unique per run (re-runnable on a shared cloud DB)."""
    cat_uuid = f"cat-{run}"
    prod_uuid = f"prod-{run}"
    cus_uuid = f"cus-{run}"

    with sf() as s:
        cat = Category(name=f"Apparel {run}", sync_uuid=cat_uuid)
        s.add(cat)
        s.flush()
        sync = SyncService(s)
        sync.enqueue_create("category", cat.id, {
            "sync_uuid": cat_uuid, "name": cat.name, "version": 1,
        })

        prod = Product(
            product_code=f"PROD-{run.upper()}", name=f"Ankara Gown {run}",
            category_id=cat.id, cost_price=Decimal("8000"),
            selling_price=Decimal("12000"), quantity=15,
            minimum_stock=3, barcode=f"BC-{run.upper()[:12].ljust(12, '0')}",
            is_active=True, sync_uuid=prod_uuid,
        )
        s.add(prod)
        s.flush()
        sync.enqueue_create("product", prod.id, {
            "sync_uuid": prod_uuid,
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
            customer_code=f"CUST-{run[:8].upper()}",
            name="Walk-in Customer", phone=None, sync_uuid=cus_uuid,
        )
        s.add(customer)
        s.flush()
        sync.enqueue_create("customer", customer.id, {
            "sync_uuid": cus_uuid,
            "customer_code": customer.customer_code,
            "name": customer.name, "phone": customer.phone, "version": 1,
        })
        s.commit()


def _make_worker(data_dir: Path, local_sf) -> SyncWorker:
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


def _local_qty(sf, prod_uuid: str) -> int:
    with sf() as s:
        return s.query(Product).filter(Product.sync_uuid == prod_uuid).first().quantity


def _run_sale_ids(sf, prod_uuid: str) -> set[int]:
    with sf() as s:
        prod = s.query(Product).filter(Product.sync_uuid == prod_uuid).first()
        if prod is None:
            return set()
        return {
            row[0] for row in s.query(SaleItem.sale_id).filter(SaleItem.product_id == prod.id).all()
        }


def _run_sales(sf, prod_uuid: str) -> list[Sale]:
    ids = _run_sale_ids(sf, prod_uuid)
    if not ids:
        return []
    with sf() as s:
        return list(s.query(Sale).filter(Sale.id.in_(ids)).all())


def _run_movements(sf, prod_uuid: str) -> list[InventoryLog]:
    with sf() as s:
        prod = s.query(Product).filter(Product.sync_uuid == prod_uuid).first()
        if prod is None:
            return []
        return list(
            s.query(InventoryLog).filter(
                InventoryLog.product_id == prod.id,
                InventoryLog.reason == "Sale",
            ).all()
        )


def _run_payments(sf, prod_uuid: str) -> list[Payment]:
    ids = _run_sale_ids(sf, prod_uuid)
    if not ids:
        return []
    with sf() as s:
        return list(s.query(Payment).filter(Payment.sale_id.in_(ids)).all())


class TestHostedTwoPcGate:
    def test_hosted_service_is_healthy(self):
        resp = httpx.get(f"{HOSTED_URL}/healthz", timeout=15)
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "ok"
        assert body["database"] == "up"

    def test_hosted_two_pc_offline_sales_converge(self, tmp_path):
        # /healthz must be up before we drive the workflow.
        assert httpx.get(f"{HOSTED_URL}/healthz", timeout=15).status_code == 200

        run = uuid.uuid4().hex[:10]

        # ---- PC-A: register, seed catalog, push ----
        a_dir = _local_datadir(tmp_path, "hosted_pc_a")
        sf_a = _bootstrap_local(a_dir, "hosted_pc_a")
        reg_a = register_device(a_dir, HOSTED_URL, f"Hosted PC-A {run}")
        assert reg_a.success, reg_a.error
        admin_a = _seed_admin(sf_a)
        _seed_catalog(sf_a, run)
        _make_worker(a_dir, sf_a).trigger_push()

        # ---- PC-B: register, pull catalog, verify convergence ----
        b_dir = _local_datadir(tmp_path, "hosted_pc_b")
        sf_b = _bootstrap_local(b_dir, "hosted_pc_b")
        reg_b = register_device(b_dir, HOSTED_URL, f"Hosted PC-B {run}")
        assert reg_b.success, reg_b.error
        admin_b = _seed_admin(sf_b)

        prod_uuid = f"prod-{run}"
        wb = _make_worker(b_dir, sf_b)
        for _ in range(3):
            wb.trigger_pull()
        assert _local_qty(sf_b, prod_uuid) == 15

        # ---- Both PCs sell OFFLINE (worker untouched; no sync yet) ----
        prod_a = _product(_sf=sf_a, prod_uuid=prod_uuid)
        cus_a = _customer(_sf=sf_a, run=run)
        prod_b = _product(_sf=sf_b, prod_uuid=prod_uuid)
        cus_b = _customer(_sf=sf_b, run=run)

        with session_scope(sf_a) as s:
            sale_a = SaleService(s, DeviceIdentity(a_dir)).complete_sale(
                admin_a, customer_id=cus_a, items=[{"product_id": prod_a, "quantity": 1}],
                payment_method="POS",
            )
        with session_scope(sf_b) as s:
            sale_b = SaleService(s, DeviceIdentity(b_dir)).complete_sale(
                admin_b, customer_id=cus_b, items=[{"product_id": prod_b, "quantity": 1}],
                payment_method="Transfer",
            )
        assert sale_a and sale_b

        # Both have 1 local sale and quantity 14 offline.
        assert _local_qty(sf_a, prod_uuid) == 14
        assert _local_qty(sf_b, prod_uuid) == 14

        # ---- RECONNECT: both push + pull ----
        wa = _make_worker(a_dir, sf_a)
        for worker in (wa, wb):
            worker.trigger_push()
            worker.trigger_pull()
        wa.trigger_pull()
        wb.trigger_pull()

        # ---- PC-side convergence for THIS run ----
        for sf in (sf_a, sf_b):
            sales = _run_sales(sf, prod_uuid)
            assert len(sales) == 2, f"expected 2 run sales, got {len(sales)}"
            receipts = {s.receipt_no for s in sales}
            assert len(receipts) == 2
            for r in receipts:
                assert r[:3] != "FUN-", r
                assert "-" in r and r.split("-")[1].isdigit()
            assert sale_a.receipt_no in receipts and sale_b.receipt_no in receipts
            assert _local_qty(sf, prod_uuid) == 13, "true on-hand must converge to 13"

            movements = _run_movements(sf, prod_uuid)
            assert len(movements) == 2
            assert sum(m.change_quantity for m in movements) == -2

            payments = _run_payments(sf, prod_uuid)
            assert len(payments) == 2
            assert {p.payment_method for p in payments} == {"POS", "TRANSFER"}

        # No dead workers: last error cleared after the final successful round.
        assert wa.status["last_error"] is None, wa.status
        assert wb.status["last_error"] is None, wb.status

        # Still healthy end-to-end.
        assert httpx.get(f"{HOSTED_URL}/healthz", timeout=15).status_code == 200


def _product(_sf, prod_uuid: str) -> int:
    with _sf() as s:
        return s.query(Product).filter(Product.sync_uuid == prod_uuid).first().id


def _customer(_sf, run: str) -> int:
    with _sf() as s:
        return s.query(Customer).filter(Customer.sync_uuid == f"cus-{run}").first().id