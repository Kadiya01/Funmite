"""Apply pulled cloud mutations to the local SQLite database.

When the local device pulls changes from the cloud, each mutation must be
applied to the local database.  This module handles the mapping from cloud
payloads (keyed by sync_uuid) to local entities (keyed by integer id).

Key rules:
    - Users are NEVER synced.  User references in payloads are stored as
      display names only.
    - Foreign-key references in cloud payloads use sync_uuids.  We resolve
      them to local integer IDs before inserting.
    - Append-only entities (sales, payments, etc.) are inserted if the
      sync_uuid does not exist locally; skipped if it does (idempotent).
    - Reference entities (categories, products, customers, suppliers) are
      upserted: inserted if new, updated if the cloud version is newer.
"""

from __future__ import annotations

import logging
from datetime import datetime

from sqlalchemy.orm import Session

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
)
from app.sync.schemas import PulledMutation

log = logging.getLogger(__name__)

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

REFERENCE_TYPES = frozenset({"category", "product", "customer", "supplier"})
APPEND_ONLY_TYPES = frozenset({
    "sale", "sale_item", "payment", "inventory_log",
    "purchase", "purchase_item", "expense",
    "exchange", "exchange_item",
})

_CLOUD_ONLY_FIELDS = frozenset({
    "device_id", "cashier_name", "recorded_by_name",
    "created_by_name", "user_name", "approved_by_name",
})

# User FK fields that are never synced (users table is excluded from sync).
# When a payload from the cloud is missing one of these, default to user 1 (admin).
_USER_FK_DEFAULTS: dict[str, int] = {
    "sale": {"cashier_id": 1},
    "payment": {"recorded_by": 1},
    "inventory_log": {"user_id": 1},
    "purchase": {"created_by": 1},
    "expense": {"created_by": 1},
    "exchange": {"approved_by": 1},
}

_FK_MAPPINGS: dict[str, list[tuple[str, str, type]]] = {
    "product": [
        ("category_sync_uuid", "category_id", Category),
    ],
    "sale": [
        ("customer_sync_uuid", "customer_id", Customer),
    ],
    "sale_item": [
        ("sale_sync_uuid", "sale_id", Sale),
        ("product_sync_uuid", "product_id", Product),
    ],
    "payment": [
        ("sale_sync_uuid", "sale_id", Sale),
    ],
    "inventory_log": [
        ("product_sync_uuid", "product_id", Product),
    ],
    "purchase": [
        ("supplier_sync_uuid", "supplier_id", Supplier),
    ],
    "purchase_item": [
        ("purchase_sync_uuid", "purchase_id", Purchase),
        ("product_sync_uuid", "product_id", Product),
    ],
    "exchange": [
        ("original_sale_sync_uuid", "original_sale_id", Sale),
        ("customer_sync_uuid", "customer_id", Customer),
    ],
    "exchange_item": [
        ("exchange_sync_uuid", "exchange_id", Exchange),
        ("original_product_sync_uuid", "original_product_id", Product),
        ("replacement_product_sync_uuid", "replacement_product_id", Product),
    ],
}


def apply_mutations(session: Session, mutations: list[PulledMutation]) -> dict:
    applied = 0
    skipped = 0
    conflicts = 0

    for mut in mutations:
        result = _apply_one(session, mut)
        if result == "applied":
            applied += 1
        elif result == "skipped":
            skipped += 1
        elif result == "conflict":
            conflicts += 1

    session.flush()
    return {"applied": applied, "skipped": skipped, "conflicts": conflicts}


def _apply_one(session: Session, mut: PulledMutation) -> str:
    model_cls = _LOCAL_MODEL_MAP.get(mut.entity_type)
    if model_cls is None:
        return "skipped"

    if mut.operation == "DELETE":
        return _apply_delete(session, model_cls, mut)

    if mut.entity_type in APPEND_ONLY_TYPES:
        return _apply_append_only(session, model_cls, mut)

    if mut.entity_type in REFERENCE_TYPES:
        return _apply_reference(session, model_cls, mut)

    return "skipped"


def _apply_delete(session, model_cls, mut: PulledMutation) -> str:
    existing = session.query(model_cls).filter_by(sync_uuid=mut.sync_uuid).first()
    if existing is not None:
        session.delete(existing)
        return "applied"
    return "skipped"


def _apply_append_only(session, model_cls, mut: PulledMutation) -> str:
    existing = session.query(model_cls).filter_by(sync_uuid=mut.sync_uuid).first()
    if existing is not None:
        return "skipped"

    local_data = _prepare_local_data(session, mut.entity_type, mut.payload)
    if local_data is None:
        return "skipped"

    local_data["sync_uuid"] = mut.sync_uuid
    entity = model_cls(**local_data)
    session.add(entity)
    session.flush()
    return "applied"


def _apply_reference(session, model_cls, mut: PulledMutation) -> str:
    existing = session.query(model_cls).filter_by(sync_uuid=mut.sync_uuid).first()

    local_data = _prepare_local_data(session, mut.entity_type, mut.payload)
    if local_data is None:
        return "skipped"

    local_data["sync_uuid"] = mut.sync_uuid

    if existing is None:
        entity = model_cls(**local_data)
        session.add(entity)
        session.flush()
        return "applied"

    cloud_version = mut.version
    local_version = getattr(existing, "version", 0)
    if cloud_version > local_version:
        for key, value in local_data.items():
            if key == "sync_uuid":
                continue
            if hasattr(existing, key):
                setattr(existing, key, value)
        session.flush()
        return "applied"

    return "conflict" if cloud_version < local_version else "skipped"


def _prepare_local_data(session: Session, entity_type: str, payload: dict) -> dict:
    data = dict(payload)

    for field in _CLOUD_ONLY_FIELDS:
        data.pop(field, None)

    fk_mappings = _FK_MAPPINGS.get(entity_type, [])
    for cloud_field, local_field, lookup_model in fk_mappings:
        uuid_val = data.pop(cloud_field, None)
        if uuid_val is not None:
            referenced = session.query(lookup_model).filter_by(sync_uuid=uuid_val).first()
            if referenced is not None:
                data[local_field] = referenced.id
            else:
                log.warning(
                    "Cannot resolve FK: %s -> %s (not found locally)",
                    local_field, uuid_val,
                )

    user_fk_defaults = _USER_FK_DEFAULTS.get(entity_type, {})
    for field, default_val in user_fk_defaults.items():
        if field not in data or data[field] is None:
            data[field] = default_val

    _coerce_datetime_strings(session, entity_type, data)

    return data


def _coerce_datetime_strings(session: Session, entity_type: str, data: dict) -> None:
    """Convert string datetime values to actual datetime objects for SQLite."""
    from sqlalchemy import inspect as sa_inspect
    model_cls = _LOCAL_MODEL_MAP.get(entity_type)
    if model_cls is None:
        return
    mapper = sa_inspect(model_cls)
    datetime_cols = {
        c.key for c in mapper.column_attrs
        if hasattr(c.columns[0].type, "python_type")
        and c.columns[0].type.python_type is datetime
    }
    for key in datetime_cols:
        val = data.get(key)
        if isinstance(val, str):
            try:
                data[key] = datetime.fromisoformat(val)
            except (ValueError, TypeError):
                pass

    return data
