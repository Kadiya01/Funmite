"""Background synchronization worker.

The worker runs in a daemon thread and periodically:
  1. Pushes pending local mutations to the cloud.
  2. Pulls remote mutations from the cloud.
  3. Applies pulled mutations to the local database.

It is designed to be started once at application launch and to never crash
the main UI thread.  All errors are caught and logged.
"""

from __future__ import annotations

import json
import logging
import threading
import time
from datetime import datetime
from typing import Callable

from sqlalchemy.orm import Session, sessionmaker

from app.config import Settings
from app.data.db import session_scope
from app.data.models import (
    Category,
    Customer,
    Exchange,
    ExchangeItem,
    Expense,
    InventoryLog,
    Payment,
    Product,
    Purchase,
    PurchaseItem,
    Sale,
    SaleItem,
    Supplier,
    SyncQueueItem,
    User,
)
from app.data.repositories.sync_repository import SyncQueueRepository, SyncStateRepository
from app.domain.services.device_service import DeviceIdentity
from app.sync.apply import apply_mutations
from app.sync.client import SyncClient
from app.sync.schemas import Mutation, PulledMutation

log = logging.getLogger(__name__)

# Entity type → local model for serialization.
_LOCAL_MODEL_MAP: dict[str, type] = {
    "category": Category,
    "product": Product,
    "customer": Customer,
    "supplier": Supplier,
    "sale": Sale,
    "sale_item": SaleItem,
    "payment": Payment,
    "inventory_log": InventoryLog,
    "purchase": Purchase,
    "purchase_item": PurchaseItem,
    "expense": Expense,
    "exchange": Exchange,
    "exchange_item": ExchangeItem,
}

# FK fields that need sync_uuid resolution during serialization.
_FK_SYNC_UUID_FIELDS: dict[str, list[tuple[str, str, type]]] = {
    "product": [("category_id", "category_sync_uuid", Category)],
    "sale": [("customer_id", "customer_sync_uuid", Customer)],
    "sale_item": [
        ("sale_id", "sale_sync_uuid", Sale),
        ("product_id", "product_sync_uuid", Product),
    ],
    "payment": [("sale_id", "sale_sync_uuid", Sale)],
    "inventory_log": [("product_id", "product_sync_uuid", Product)],
    "purchase": [("supplier_id", "supplier_sync_uuid", Supplier)],
    "purchase_item": [
        ("purchase_id", "purchase_sync_uuid", Purchase),
        ("product_id", "product_sync_uuid", Product),
    ],
    "exchange": [
        ("original_sale_id", "original_sale_sync_uuid", Sale),
        ("customer_id", "customer_sync_uuid", Customer),
    ],
    "exchange_item": [
        ("exchange_id", "exchange_sync_uuid", Exchange),
        ("original_product_id", "original_product_sync_uuid", Product),
        ("replacement_product_id", "replacement_product_sync_uuid", Product),
    ],
}

# Cloud-payload display-name fields (mapped from local user FK).
_USER_DISPLAY_FIELDS: dict[str, list[tuple[str, str, type]]] = {
    "sale": [("cashier_id", "cashier_name", User)],
    "payment": [("recorded_by", "recorded_by_name", User)],
    "inventory_log": [("user_id", "user_name", User)],
    "purchase": [("created_by", "created_by_name", User)],
    "expense": [("created_by", "created_by_name", User)],
    "exchange": [("approved_by", "approved_by_name", User)],
}


def resolve_push_payload(
    session, entity_type: str, payload: dict
) -> dict:
    """Translate local integer FKs to sync_uuid references and user display names.

    The business services enqueue payloads with local integer foreign keys
    (e.g. ``category_id``, ``customer_id``).  The cloud API expects
    ``*_sync_uuid`` references for entity FKs and ``*_name`` display strings
    for user FKs (users are never synced).

    This function mutates and returns a *new* dict — the original is not
    modified.
    """
    data = dict(payload)

    # 1. Resolve entity FKs: local_id → sync_uuid
    for local_field, cloud_field, model_cls in _FK_SYNC_UUID_FIELDS.get(entity_type, []):
        local_id = data.pop(local_field, None)
        if local_id is not None and local_id != 0:
            related = session.get(model_cls, local_id)
            if related is not None and related.sync_uuid:
                data[cloud_field] = related.sync_uuid
            else:
                log.warning(
                    "Cannot resolve %s=%s to sync_uuid for %s",
                    local_field, local_id, entity_type,
                )

    # 2. Resolve user FKs: local_id → display name
    for local_field, cloud_field, user_cls in _USER_DISPLAY_FIELDS.get(entity_type, []):
        local_id = data.pop(local_field, None)
        if local_id is not None:
            user = session.get(user_cls, local_id)
            if user is not None:
                data[cloud_field] = user.full_name or user.username
            else:
                data[cloud_field] = "Unknown"

    return data


class SyncWorker:
    """Background daemon thread that pushes and pulls sync data."""

    def __init__(
        self,
        local_session_factory: sessionmaker,
        cloud_session_factory: sessionmaker | None,
        settings: Settings,
        *,
        push_interval: float = 30.0,
        pull_interval: float = 60.0,
        on_sync_complete: Callable[[], None] | None = None,
    ) -> None:
        self._local_sf = local_session_factory
        self._cloud_sf = cloud_session_factory
        self._settings = settings
        self._push_interval = push_interval
        self._pull_interval = pull_interval
        self._on_sync_complete = on_sync_complete
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._syncing = False
        self._last_push_at: datetime | None = None
        self._last_pull_at: datetime | None = None
        self._last_error: str | None = None
        self._pushed_count = 0
        self._pulled_count = 0

    @property
    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    @property
    def is_syncing(self) -> bool:
        return self._syncing

    @property
    def status(self) -> dict:
        return {
            "running": self.is_running,
            "syncing": self._syncing,
            "last_push_at": self._last_push_at,
            "last_pull_at": self._last_pull_at,
            "last_error": self._last_error,
            "pushed_count": self._pushed_count,
            "pulled_count": self._pulled_count,
        }

    def start(self) -> None:
        """Start the background sync thread."""
        if self.is_running:
            return
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run_loop,
            name="sync-worker",
            daemon=True,
        )
        self._thread.start()
        log.info("Sync worker started")

    def stop(self) -> None:
        """Stop the background sync thread."""
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=10)
            self._thread = None
        log.info("Sync worker stopped")

    def trigger_push(self) -> None:
        """Execute a single push cycle immediately."""
        try:
            self._do_push()
        except Exception:
            log.exception("Manual push failed")

    def trigger_pull(self) -> None:
        """Execute a single pull cycle immediately."""
        try:
            self._do_pull()
        except Exception:
            log.exception("Manual pull failed")

    def _run_loop(self) -> None:
        last_push = 0.0
        last_pull = 0.0

        while not self._stop_event.is_set():
            now = time.monotonic()

            if now - last_push >= self._push_interval:
                try:
                    self._do_push()
                except Exception:
                    log.exception("Push cycle failed")
                last_push = now

            if now - last_pull >= self._pull_interval:
                try:
                    self._do_pull()
                except Exception:
                    log.exception("Pull cycle failed")
                last_pull = now

            self._stop_event.wait(timeout=5.0)

    # ------------------------------------------------------------------
    # Push
    # ------------------------------------------------------------------

    def _do_push(self) -> None:
        if self._cloud_sf is None:
            return

        device = DeviceIdentity(self._settings.data_dir)
        client = self._build_client(device.device_id)
        if client is None:
            return

        self._syncing = True
        try:
            pending_items: list = []
            mutations: list[Mutation] = []

            with session_scope(self._local_sf) as session:
                queue = SyncQueueRepository(session)
                pending_items = queue.get_pending(limit=100)
                if not pending_items:
                    return

                for item in pending_items:
                    queue.mark_syncing(item)
                    raw_payload = json.loads(item.payload)
                    sync_uuid = raw_payload.pop("sync_uuid", "")
                    version = raw_payload.pop("version", 1)

                    resolved_payload = resolve_push_payload(
                        session, item.entity_type, raw_payload,
                    )

                    mutation = Mutation(
                        entity_type=item.entity_type,
                        operation=item.operation,
                        sync_uuid=sync_uuid,
                        payload=resolved_payload,
                        version=version,
                        device_id=item.device_id or device.device_id,
                        created_at=item.created_at,
                    )
                    mutations.append(mutation)

            # Push outside the local transaction
            result = client.push(mutations)
            if result is None:
                self._reset_push_items()
                self._last_error = "Push request failed"
                return

            self._last_push_at = datetime.now()
            self._pushed_count += result.accepted
            self._last_error = None

            # Mark items as synced based on result
            with session_scope(self._local_sf) as session:
                queue = SyncQueueRepository(session)
                for i, item in enumerate(pending_items):
                    if i < result.accepted:
                        queue.mark_synced(item)
        finally:
            self._syncing = False

    def _reset_push_items(self) -> None:
        """Reset SYNCING items back to PENDING on network failure."""
        try:
            with session_scope(self._local_sf) as session:
                queue = SyncQueueRepository(session)
                syncing = list(
                    session.query(SyncQueueItem).filter(
                        SyncQueueItem.status == "SYNCING"
                    )
                )
                for item in syncing:
                    queue.reset_failed(item)
        except Exception:
            log.exception("Failed to reset push items")

    # ------------------------------------------------------------------
    # Pull
    # ------------------------------------------------------------------

    def _do_pull(self) -> None:
        if self._cloud_sf is None:
            return

        device = DeviceIdentity(self._settings.data_dir)
        client = self._build_client(device.device_id)
        if client is None:
            return

        self._syncing = True
        try:
            # Determine since timestamp
            with session_scope(self._local_sf) as session:
                state_repo = SyncStateRepository(session)
                state = state_repo.get_by_device(device.device_id)
                since = state.last_sync_at if state and state.last_sync_at else datetime.min

            result = client.pull(since=since)
            if result is None:
                self._last_error = "Pull request failed"
                return

            if not result.mutations:
                self._last_pull_at = datetime.now()
                return

            # Apply pulled mutations to local DB
            with session_scope(self._local_sf) as session:
                summary = apply_mutations(session, result.mutations)

                # Update sync state
                state_repo = SyncStateRepository(session)
                state_repo.set_last_sync(device.device_id, result.server_timestamp)

            self._last_pull_at = datetime.now()
            self._pulled_count += len(result.mutations)
            self._last_error = None
        finally:
            self._syncing = False

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _build_client(self, device_id: str) -> SyncClient | None:
        """Build a SyncClient from stored device credentials."""
        cred_path = self._settings.data_dir / "sync_credentials.json"
        if not cred_path.exists():
            log.warning("No sync credentials found; skipping sync")
            return None

        try:
            creds = json.loads(cred_path.read_text(encoding="utf-8"))
            return SyncClient(
                base_url=creds["cloud_url"],
                device_id=device_id,
                api_key=creds["api_key"],
            )
        except Exception:
            log.exception("Failed to build sync client")
            return None
