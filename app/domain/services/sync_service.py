"""Synchronization service — enqueue local mutations for cloud push.

Every business service calls ``SyncService.enqueue`` after successfully
committing a local mutation.  This creates a ``sync_queue`` entry with
the full entity payload so a background worker can later push it to the
cloud API.

This service is *offline-first*: enqueue never blocks the caller and
never raises.  Network failures are handled by the background push
worker, not here.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from app.config import load_settings
from app.data.repositories.sync_repository import SyncQueueRepository
from app.domain.services.device_service import DeviceIdentity

log = logging.getLogger(__name__)

# ------------------------------------------------------------------
# Entity types that participate in sync
# ------------------------------------------------------------------
ENTITY_CATEGORY = "category"
ENTITY_PRODUCT = "product"
ENTITY_CUSTOMER = "customer"
ENTITY_SALE = "sale"
ENTITY_SALE_ITEM = "sale_item"
ENTITY_PAYMENT = "payment"
ENTITY_INVENTORY_LOG = "inventory_log"
ENTITY_SUPPLIER = "supplier"
ENTITY_PURCHASE = "purchase"
ENTITY_PURCHASE_ITEM = "purchase_item"
ENTITY_EXPENSE = "expense"
ENTITY_EXCHANGE = "exchange"
ENTITY_EXCHANGE_ITEM = "exchange_item"

# Mutable reference entities use version-based conflict detection.
REFERENCE_ENTITIES = frozenset({
    ENTITY_CATEGORY,
    ENTITY_PRODUCT,
    ENTITY_CUSTOMER,
    ENTITY_SUPPLIER,
})

# Append-only entities never conflict; they are always accepted.
APPEND_ONLY_ENTITIES = frozenset({
    ENTITY_SALE,
    ENTITY_SALE_ITEM,
    ENTITY_PAYMENT,
    ENTITY_INVENTORY_LOG,
    ENTITY_PURCHASE,
    ENTITY_PURCHASE_ITEM,
    ENTITY_EXPENSE,
    ENTITY_EXCHANGE,
    ENTITY_EXCHANGE_ITEM,
})

# ------------------------------------------------------------------
# Operation types
# ------------------------------------------------------------------
OP_CREATE = "CREATE"
OP_UPDATE = "UPDATE"
OP_DELETE = "DELETE"


class SyncService:
    """Facade for sync queue operations."""

    def __init__(
        self,
        session: Session,
        device: DeviceIdentity | None = None,
    ) -> None:
        self._session = session
        self._queue = SyncQueueRepository(session)
        self._device = device

    def _get_device(self) -> DeviceIdentity:
        if self._device is None:
            self._device = DeviceIdentity(load_settings().data_dir)
        return self._device

    # ------------------------------------------------------------------
    # Public API — called by business services after commit
    # ------------------------------------------------------------------

    def enqueue(
        self,
        entity_type: str,
        entity_id: int,
        operation: str,
        payload: dict[str, Any],
    ) -> None:
        """Create a PENDING sync entry for the given mutation.

        This method is fire-and-forget: it never raises and never blocks.
        """
        try:
            self._queue.enqueue(
                entity_type=entity_type,
                entity_id=entity_id,
                operation=operation,
                payload=payload,
                device_id=self._get_device().device_id,
            )
            log.debug(
                "Enqueued sync: %s %s %s",
                operation,
                entity_type,
                entity_id,
            )
        except Exception:
            log.exception("Failed to enqueue sync for %s/%s", entity_type, entity_id)

    def enqueue_create(self, entity_type: str, entity_id: int, payload: dict[str, Any]) -> None:
        self.enqueue(entity_type, entity_id, OP_CREATE, payload)

    def enqueue_update(self, entity_type: str, entity_id: int, payload: dict[str, Any]) -> None:
        self.enqueue(entity_type, entity_id, OP_UPDATE, payload)

    def enqueue_delete(self, entity_type: str, entity_id: int, payload: dict[str, Any]) -> None:
        self.enqueue(entity_type, entity_id, OP_DELETE, payload)

    # ------------------------------------------------------------------
    # Status queries
    # ------------------------------------------------------------------

    def pending_count(self) -> int:
        return self._queue.count_pending()

    def total_count(self) -> int:
        return self._queue.count_all()

    def has_pending(self) -> bool:
        return self.pending_count() > 0
