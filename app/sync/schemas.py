"""Pydantic request/response models for the sync API contract.

These schemas define the wire format between the local POS client and the
cloud sync service.  They are intentionally simple: a batch of mutations
for push, a list of mutations for pull.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


# ------------------------------------------------------------------
# Device registration
# ------------------------------------------------------------------


class DeviceRegisterRequest(BaseModel):
    device_name: str = Field(..., min_length=1, max_length=150)


class DeviceRegisterResponse(BaseModel):
    device_id: str
    api_key: str
    registered_at: datetime


# ------------------------------------------------------------------
# Push (local → cloud)
# ------------------------------------------------------------------


class Mutation(BaseModel):
    """One local mutation to push to the cloud."""

    entity_type: str
    operation: str  # CREATE, UPDATE, DELETE
    sync_uuid: str
    payload: dict[str, Any]
    version: int = 1
    device_id: str
    created_at: datetime | None = None


class PushRequest(BaseModel):
    mutations: list[Mutation] = Field(default_factory=list, max_length=500)


class ConflictDetail(BaseModel):
    sync_uuid: str
    entity_type: str
    reason: str
    remote_version: int


class PushResponse(BaseModel):
    accepted: int = 0
    rejected: int = 0
    conflicts: list[ConflictDetail] = Field(default_factory=list)
    server_timestamp: datetime


# ------------------------------------------------------------------
# Pull (cloud → local)
# ------------------------------------------------------------------


class PullRequest(BaseModel):
    since: datetime
    entity_types: list[str] | None = None


class PulledMutation(BaseModel):
    """One mutation returned from the cloud during pull."""

    entity_type: str
    operation: str
    sync_uuid: str
    payload: dict[str, Any]
    version: int = 1
    device_id: str
    created_at: datetime | None = None


class PullResponse(BaseModel):
    mutations: list[PulledMutation] = Field(default_factory=list)
    server_timestamp: datetime
    has_more: bool = False


# ------------------------------------------------------------------
# Status
# ------------------------------------------------------------------


class SyncStatusResponse(BaseModel):
    device_id: str
    last_push_at: datetime | None = None
    last_pull_at: datetime | None = None
    total_synced: int = 0
    total_conflicts: int = 0
