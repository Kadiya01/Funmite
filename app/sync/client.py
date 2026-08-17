"""HTTP client for the local POS to push/pull mutations to/from the cloud.

This client is used by the background sync worker.  All methods are
synchronous and handle network errors gracefully (returning empty results
rather than raising, to preserve the offline-first guarantee).
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any

import httpx

from app.sync.schemas import (
    Mutation,
    PullRequest,
    PullResponse,
    PushRequest,
    PushResponse,
)

log = logging.getLogger(__name__)

DEFAULT_TIMEOUT = 15.0


class SyncClient:
    """HTTP client for the cloud sync API."""

    def __init__(
        self,
        base_url: str,
        device_id: str,
        api_key: str,
        timeout: float = DEFAULT_TIMEOUT,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._device_id = device_id
        self._api_key = api_key
        self._timeout = timeout

    @property
    def _headers(self) -> dict[str, str]:
        return {
            "X-Device-ID": self._device_id,
            "X-API-Key": self._api_key,
        }

    # ------------------------------------------------------------------
    # Push
    # ------------------------------------------------------------------

    def push(self, mutations: list[Mutation]) -> PushResponse | None:
        """Push a batch of mutations to the cloud.

        Returns the PushResponse on success, None on network error.
        """
        if not mutations:
            return PushResponse(
                accepted=0,
                rejected=0,
                conflicts=[],
                server_timestamp=datetime.now(),
            )

        try:
            with httpx.Client(timeout=self._timeout) as client:
                payload = PushRequest(mutations=mutations)
                resp = client.post(
                    f"{self._base_url}/api/sync/push",
                    json=payload.model_dump(mode="json"),
                    headers=self._headers,
                )
                resp.raise_for_status()
                return PushResponse(**resp.json())
        except Exception:
            log.exception("Push failed — will retry later")
            return None

    # ------------------------------------------------------------------
    # Pull
    # ------------------------------------------------------------------

    def pull(
        self,
        since: datetime,
        entity_types: list[str] | None = None,
    ) -> PullResponse | None:
        """Pull mutations from the cloud since a given timestamp.

        Returns the PullResponse on success, None on network error.
        """
        try:
            with httpx.Client(timeout=self._timeout) as client:
                payload = PullRequest(since=since, entity_types=entity_types)
                resp = client.post(
                    f"{self._base_url}/api/sync/pull",
                    json=payload.model_dump(mode="json"),
                    headers=self._headers,
                )
                resp.raise_for_status()
                return PullResponse(**resp.json())
        except Exception:
            log.exception("Pull failed — will retry later")
            return None

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    @staticmethod
    def register(base_url: str, device_name: str) -> dict[str, Any] | None:
        """Register a new device with the cloud service.

        Returns {"device_id", "api_key", "registered_at"} or None.
        """
        try:
            with httpx.Client(timeout=DEFAULT_TIMEOUT) as client:
                resp = client.post(
                    f"{base_url.rstrip('/')}/api/sync/devices/register",
                    json={"device_name": device_name},
                )
                resp.raise_for_status()
                return resp.json()
        except Exception:
            log.exception("Device registration failed")
            return None

    # ------------------------------------------------------------------
    # Status
    # ------------------------------------------------------------------

    def status(self) -> dict[str, Any] | None:
        """Get sync status from the cloud."""
        try:
            with httpx.Client(timeout=self._timeout) as client:
                resp = client.get(
                    f"{self._base_url}/api/sync/status",
                    headers=self._headers,
                )
                resp.raise_for_status()
                return resp.json()
        except Exception:
            log.exception("Status check failed")
            return None
