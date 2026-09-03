"""Repositories for ``sync_queue`` and ``sync_state`` tables.

These repositories handle the offline-first sync outbox: every local
mutation creates a ``sync_queue`` entry, and a background worker pushes
PENDING entries to the cloud API.  ``sync_state`` tracks the cursor for
inbound sync.
"""

from __future__ import annotations

import json
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.data.models import (
    SYNC_STATUS_FAILED,
    SYNC_STATUS_PENDING,
    SYNC_STATUS_SYNCED,
    SYNC_STATUS_SYNCING,
    SyncQueueItem,
    SyncState,
)


class SyncQueueRepository:
    """CRUD helpers for the sync outbox queue."""

    def __init__(self, session: Session) -> None:
        self.session = session

    # ------------------------------------------------------------------
    # Enqueue
    # ------------------------------------------------------------------

    def enqueue(
        self,
        *,
        entity_type: str,
        entity_id: int,
        operation: str,
        payload: dict,
        device_id: str | None = None,
    ) -> SyncQueueItem:
        """Create a new PENDING sync entry."""
        item = SyncQueueItem(
            entity_type=entity_type,
            entity_id=entity_id,
            operation=operation,
            payload=json.dumps(payload, default=str),
            status=SYNC_STATUS_PENDING,
            device_id=device_id,
        )
        self.session.add(item)
        return item

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def get_pending(self, *, limit: int = 50) -> list[SyncQueueItem]:
        """Return the oldest PENDING entries (FIFO order)."""
        stmt = (
            select(SyncQueueItem)
            .where(SyncQueueItem.status == SYNC_STATUS_PENDING)
            .order_by(SyncQueueItem.created_at)
            .limit(limit)
        )
        return list(self.session.scalars(stmt))

    def get_by_id(self, record_id: int) -> SyncQueueItem | None:
        return self.session.get(SyncQueueItem, record_id)

    def list_failed(self) -> list[SyncQueueItem]:
        return list(
            self.session.scalars(
                select(SyncQueueItem)
                .where(SyncQueueItem.status == SYNC_STATUS_FAILED)
                .order_by(SyncQueueItem.created_at)
            )
        )

    def list_synced(self, *, limit: int = 100) -> list[SyncQueueItem]:
        return list(
            self.session.scalars(
                select(SyncQueueItem)
                .where(SyncQueueItem.status == SYNC_STATUS_SYNCED)
                .order_by(SyncQueueItem.synced_at.desc())
                .limit(limit)
            )
        )

    # ------------------------------------------------------------------
    # Status transitions
    # ------------------------------------------------------------------

    def mark_syncing(self, item: SyncQueueItem) -> None:
        item.status = SYNC_STATUS_SYNCING
        item.attempt_count += 1
        item.last_attempt = datetime.now()

    def mark_synced(self, item: SyncQueueItem) -> None:
        item.status = SYNC_STATUS_SYNCED
        item.synced_at = datetime.now()

    def mark_failed(self, item: SyncQueueItem) -> None:
        item.status = SYNC_STATUS_FAILED
        item.last_attempt = datetime.now()

    def reset_failed(self, item: SyncQueueItem) -> None:
        """Reset a FAILED item back to PENDING for retry."""
        item.status = SYNC_STATUS_PENDING
        item.attempt_count = 0

    def clear_synced(self) -> int:
        """Delete all SYNCED entries. Returns count deleted."""
        count = self.session.query(SyncQueueItem).filter(
            SyncQueueItem.status == SYNC_STATUS_SYNCED
        ).delete()
        return count

    def count_pending(self) -> int:
        return int(
            self.session.query(SyncQueueItem)
            .filter(SyncQueueItem.status == SYNC_STATUS_PENDING)
            .count()
        )

    def count_all(self) -> int:
        return int(self.session.query(SyncQueueItem).count())


class SyncStateRepository:
    """Manages the sync cursor per device (last-synced timestamp)."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def get_by_device(self, device_id: str) -> SyncState | None:
        stmt = select(SyncState).where(SyncState.device_id == device_id)
        return self.session.scalar(stmt)

    def set_last_sync(self, device_id: str, timestamp: datetime) -> SyncState:
        state = self.get_by_device(device_id)
        if state is None:
            state = SyncState(
                device_id=device_id,
                last_sync_at=timestamp,
            )
            self.session.add(state)
        else:
            state.last_sync_at = timestamp
        return state

    def increment_version(self, device_id: str) -> SyncState:
        state = self.get_by_device(device_id)
        if state is None:
            state = SyncState(
                device_id=device_id,
                last_sync_at=datetime.now(),
                sync_version=1,
            )
            self.session.add(state)
        else:
            state.sync_version += 1
        return state

    def list_all(self) -> list[SyncState]:
        return list(self.session.scalars(select(SyncState)))
