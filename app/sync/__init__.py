"""Sync layer — cloud synchronization for the Funmite POS.

Provides:
    - Cloud database models and engine (``cloud_models``, ``cloud_db``)
    - Sync API client for push/pull (``client``)
    - Background sync worker (``worker``)
    - Apply pulled mutations to local DB (``apply``)
    - Pydantic schemas for the wire protocol (``schemas``)
"""

from __future__ import annotations
