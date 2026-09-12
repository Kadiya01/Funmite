"""Deprecated placeholder (superseded by Phase 10C cloud sync).

The original LAN-service stub was superseded by the hybrid offline-first
cloud-sync topology.  The single cloud server implementation now lives in
``app.sync.cloud_api`` (``create_app`` / module-level ``app``); run it
with uvicorn or the ``scripts/run_cloud_server.bat`` launcher.

This module is retained only to avoid breaking stale imports and does
not implement a separate server.
"""
