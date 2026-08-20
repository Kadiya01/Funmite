"""Cloud sync FastAPI routes.

This module implements the server-side sync API.  The cloud service
receives push requests from local devices, stores the data, and
serves pull requests.

Authentication is by ``X-Device-ID`` and ``X-API-Key`` headers.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.sync.cloud_db import create_cloud_session_factory, init_cloud_schema
from app.sync.cloud_models import (
    CloudCategory,
    CloudCustomer,
    CloudExchange,
    CloudExchangeItem,
    CloudExpense,
    CloudInventoryLog,
    CloudPayment,
    CloudProduct,
    CloudPurchase,
    CloudPurchaseItem,
    CloudSale,
    CloudSaleItem,
    CloudSupplier,
    CloudSyncLog,
    DeviceRegistry,
)
from app.sync.schemas import (
    ConflictDetail,
    DeviceRegisterRequest,
    DeviceRegisterResponse,
    Mutation,
    PullRequest,
    PullResponse,
    PulledMutation,
    PushRequest,
    PushResponse,
    SyncStatusResponse,
)

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/sync", tags=["sync"])

# ------------------------------------------------------------------
# Entity type → cloud model mapping
# ------------------------------------------------------------------

CLOUD_MODEL_MAP: dict[str, type] = {
    "category": CloudCategory,
    "product": CloudProduct,
    "customer": CloudCustomer,
    "supplier": CloudSupplier,
    "sale": CloudSale,
    "sale_item": CloudSaleItem,
    "payment": CloudPayment,
    "inventory_log": CloudInventoryLog,
    "purchase": CloudPurchase,
    "purchase_item": CloudPurchaseItem,
    "expense": CloudExpense,
    "exchange": CloudExchange,
    "exchange_item": CloudExchangeItem,
}

# Mutable reference entities that use version-based conflict detection.
REFERENCE_TYPES = frozenset({"category", "product", "customer", "supplier"})

# Append-only entities are always accepted.
APPEND_ONLY_TYPES = frozenset({
    "sale", "sale_item", "payment", "inventory_log",
    "purchase", "purchase_item", "expense",
    "exchange", "exchange_item",
})

# Columns to exclude from sync payloads (never sync these)
_EXCLUDE_COLUMNS = {"id"}


# ------------------------------------------------------------------
# Session dependency
# ------------------------------------------------------------------

_cloud_session_factory: sessionmaker | None = None


def get_cloud_session_factory() -> sessionmaker:
    return _cloud_session_factory  # type: ignore[return-value]


def set_cloud_session_factory(factory: sessionmaker) -> None:
    global _cloud_session_factory
    _cloud_session_factory = factory


def get_db():
    factory = get_cloud_session_factory()
    session = factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


# ------------------------------------------------------------------
# Auth dependency
# ------------------------------------------------------------------


def _authenticate(
    x_device_id: str = Header(...),
    x_api_key: str = Header(...),
    db: Session = Depends(get_db),
) -> DeviceRegistry:
    stmt = select(DeviceRegistry).where(
        DeviceRegistry.device_id == x_device_id,
        DeviceRegistry.api_key == x_api_key,
        DeviceRegistry.is_active == True,  # noqa: E712
    )
    device = db.scalar(stmt)
    if device is None:
        raise HTTPException(status_code=401, detail="Invalid device credentials")
    device.last_seen_at = datetime.now()
    db.flush()
    return device


# ------------------------------------------------------------------
# Device registration
# ------------------------------------------------------------------


@router.post("/devices/register", response_model=DeviceRegisterResponse)
def register_device(
    req: DeviceRegisterRequest,
    db: Session = Depends(get_db),
) -> DeviceRegisterResponse:
    import uuid as _uuid_mod

    device_id = str(_uuid_mod.uuid4())
    api_key = _uuid_mod.uuid4().hex

    device = DeviceRegistry(
        device_id=device_id,
        device_name=req.device_name,
        api_key=api_key,
        is_active=True,
        registered_at=datetime.now(),
    )
    db.add(device)
    db.flush()

    return DeviceRegisterResponse(
        device_id=device_id,
        api_key=api_key,
        registered_at=device.registered_at,
    )


# ------------------------------------------------------------------
# Push endpoint
# ------------------------------------------------------------------


@router.post("/push", response_model=PushResponse)
def push_mutations(
    req: PushRequest,
    device: DeviceRegistry = Depends(_authenticate),
    db: Session = Depends(get_db),
) -> PushResponse:
    accepted = 0
    rejected = 0
    conflicts: list[ConflictDetail] = []

    for mut in req.mutations:
        result = _apply_mutation(db, mut, device.device_id)
        if result == "accepted":
            accepted += 1
        elif result == "rejected":
            rejected += 1
        elif isinstance(result, ConflictDetail):
            conflicts.append(result)
            rejected += 1

    db.flush()
    now = datetime.now()

    return PushResponse(
        accepted=accepted,
        rejected=rejected,
        conflicts=conflicts,
        server_timestamp=now,
    )


def _apply_mutation(
    db: Session, mut: Mutation, device_id: str
) -> str | ConflictDetail:
    """Apply a single mutation to the cloud DB.

    Returns 'accepted', 'rejected', or a ConflictDetail.
    """
    model_cls = CLOUD_MODEL_MAP.get(mut.entity_type)
    if model_cls is None:
        return "rejected"

    # --- DELETE operations ---
    if mut.operation == "DELETE":
        existing = db.get(model_cls, mut.sync_uuid)
        if existing is not None:
            db.delete(existing)
            _log_sync_event(db, mut, device_id, True)
        return "accepted"

    # --- Append-only entities: always accept ---
    if mut.entity_type in APPEND_ONLY_TYPES:
        existing = db.get(model_cls, mut.sync_uuid)
        if existing is not None:
            # Idempotent: already exists, skip silently
            _log_sync_event(db, mut, device_id, True)
            return "accepted"

        _upsert_cloud_entity(db, model_cls, mut, device_id)
        _log_sync_event(db, mut, device_id, True)
        return "accepted"

    # --- Reference entities: version-based conflict detection ---
    existing = db.get(model_cls, mut.sync_uuid)
    if existing is None:
        _upsert_cloud_entity(db, model_cls, mut, device_id)
        _log_sync_event(db, mut, device_id, True)
        return "accepted"

    remote_version = getattr(existing, "version", 0)
    if mut.version > remote_version:
        _upsert_cloud_entity(db, model_cls, mut, device_id)
        _log_sync_event(db, mut, device_id, True)
        return "accepted"
    elif mut.version == remote_version:
        if mut.created_at is None:
            _log_sync_event(db, mut, device_id, True)
            return "accepted"
        remote_ts = getattr(existing, "updated_at", datetime.min) or datetime.min
        if mut.created_at >= remote_ts:
            _upsert_cloud_entity(db, model_cls, mut, device_id)
            _log_sync_event(db, mut, device_id, True)
            return "accepted"
        else:
            conflict = ConflictDetail(
                sync_uuid=mut.sync_uuid,
                entity_type=mut.entity_type,
                reason="same_version_older_timestamp",
                remote_version=remote_version,
            )
            _log_sync_event(db, mut, device_id, False, conflict.reason)
            return conflict
    else:
        conflict = ConflictDetail(
            sync_uuid=mut.sync_uuid,
            entity_type=mut.entity_type,
            reason="stale_version",
            remote_version=remote_version,
        )
        _log_sync_event(db, mut, device_id, False, conflict.reason)
        return conflict


def _upsert_cloud_entity(
    db: Session,
    model_cls: type,
    mut: Mutation,
    device_id: str,
) -> None:
    """Insert or update a cloud entity from a mutation payload."""
    payload = dict(mut.payload)
    # Ensure key fields are set from the mutation envelope
    payload["sync_uuid"] = mut.sync_uuid
    payload["device_id"] = device_id
    if hasattr(model_cls, "version"):
        payload["version"] = mut.version

    # Coerce string datetimes to actual datetime objects for SQLite
    payload = _coerce_datetime_fields(model_cls, payload)

    existing = db.get(model_cls, mut.sync_uuid)
    if existing is not None:
        for key, value in payload.items():
            if key in _EXCLUDE_COLUMNS:
                continue
            if hasattr(existing, key):
                setattr(existing, key, value)
    else:
        entity = model_cls(**{k: v for k, v in payload.items() if k not in _EXCLUDE_COLUMNS})
        db.add(entity)


def _coerce_datetime_fields(model_cls: type, payload: dict) -> dict:
    """Convert string datetime values in payload to actual datetime objects."""
    from sqlalchemy import inspect as sa_inspect
    mapper = sa_inspect(model_cls)
    datetime_cols = {
        c.key for c in mapper.column_attrs
        if hasattr(c.columns[0].type, "python_type")
        and c.columns[0].type.python_type is datetime
    }
    result = dict(payload)
    for key in datetime_cols:
        val = result.get(key)
        if isinstance(val, str):
            try:
                result[key] = datetime.fromisoformat(val)
            except (ValueError, TypeError):
                pass
    return result


def _log_sync_event(
    db: Session,
    mut: Mutation,
    device_id: str,
    accepted: bool,
    reason: str | None = None,
) -> None:
    entry = CloudSyncLog(
        entity_type=mut.entity_type,
        operation=mut.operation,
        sync_uuid=mut.sync_uuid,
        device_id=device_id,
        version=mut.version,
        accepted=accepted,
        conflict_reason=reason,
    )
    db.add(entry)


# ------------------------------------------------------------------
# Pull endpoint
# ------------------------------------------------------------------


@router.post("/pull", response_model=PullResponse)
def pull_mutations(
    req: PullRequest,
    device: DeviceRegistry = Depends(_authenticate),
    db: Session = Depends(get_db),
) -> PullResponse:
    entity_types = req.entity_types or list(CLOUD_MODEL_MAP.keys())
    limit = 200

    stmt = (
        select(CloudSyncLog)
        .where(
            CloudSyncLog.created_at > req.since,
            CloudSyncLog.accepted == True,  # noqa: E712
            CloudSyncLog.entity_type.in_(entity_types),
            CloudSyncLog.device_id != device.device_id,
        )
        .order_by(CloudSyncLog.created_at)
        .limit(limit + 1)
    )

    rows = list(db.scalars(stmt))
    has_more = len(rows) > limit
    rows = rows[:limit]

    mutations: list[PulledMutation] = []
    seen_uuids: set[str] = set()

    for log_entry in rows:
        if log_entry.sync_uuid in seen_uuids:
            continue
        seen_uuids.add(log_entry.sync_uuid)

        if log_entry.operation == "DELETE":
            mutations.append(
                PulledMutation(
                    entity_type=log_entry.entity_type,
                    operation=log_entry.operation,
                    sync_uuid=log_entry.sync_uuid,
                    payload={},
                    version=log_entry.version,
                    device_id=log_entry.device_id,
                    created_at=log_entry.created_at,
                )
            )
            continue

        model_cls = CLOUD_MODEL_MAP.get(log_entry.entity_type)
        if model_cls is None:
            continue

        entity = db.get(model_cls, log_entry.sync_uuid)
        if entity is None:
            continue

        payload = _entity_to_dict(entity)
        mutations.append(
            PulledMutation(
                entity_type=log_entry.entity_type,
                operation=log_entry.operation,
                sync_uuid=log_entry.sync_uuid,
                payload=payload,
                version=getattr(entity, "version", 1),
                device_id=log_entry.device_id,
                created_at=log_entry.created_at,
            )
        )

    return PullResponse(
        mutations=mutations,
        server_timestamp=datetime.now(),
        has_more=has_more,
    )


def _entity_to_dict(entity) -> dict:
    """Serialize a cloud model instance to a dict, excluding internal columns."""
    result = {}
    for col in entity.__table__.columns:
        if col.name in _EXCLUDE_COLUMNS:
            continue
        value = getattr(entity, col.name)
        if isinstance(value, datetime):
            value = value.isoformat()
        result[col.name] = value
    return result


# ------------------------------------------------------------------
# Status endpoint
# ------------------------------------------------------------------


@router.get("/status", response_model=SyncStatusResponse)
def sync_status(
    device: DeviceRegistry = Depends(_authenticate),
    db: Session = Depends(get_db),
) -> SyncStatusResponse:
    return SyncStatusResponse(
        device_id=device.device_id,
        last_push_at=device.last_seen_at,
        last_pull_at=device.last_seen_at,
    )
