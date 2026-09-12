"""Cloud server smoke tests (Phase 2 - M1).

Verifies the runnable FastAPI application: ``create_app()`` builds a real
app, startup initializes the cloud schema and session factory, and the
``/api/sync/*`` routes are reachable through the intended test interface
(FastAPI TestClient) exactly as the launcher serves them.
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.sync.cloud_api import app, create_app, set_cloud_session_factory


def _route_paths(container) -> set[str]:
    """Collect mounted route paths, including routes nested in included routers."""
    paths: set[str] = set()
    for route in getattr(container, "routes", []):
        if getattr(route, "path", None) is not None:
            paths.add(route.path)
        inner = getattr(route, "original_router", None)
        if inner is not None:
            paths |= _route_paths(inner)
    return paths


# ------------------------------------------------------------------
# Module-level application
# ------------------------------------------------------------------


def test_module_level_app_is_a_fastapi_application():
    assert isinstance(app, FastAPI)
    paths = _route_paths(app)
    assert "/api/sync/devices/register" in paths
    assert "/api/sync/push" in paths
    assert "/api/sync/pull" in paths
    assert "/api/sync/status" in paths


# ------------------------------------------------------------------
# create_app() through the TestClient lifecycle
# ------------------------------------------------------------------


def test_status_requires_authentication():
    try:
        with TestClient(create_app("sqlite:///:memory:")) as client:
            rejected = client.get(
                "/api/sync/status",
                headers={"X-Device-ID": "bogus", "X-API-Key": "bogus"},
            )
            assert rejected.status_code == 401
            assert "Invalid device credentials" in rejected.json()["detail"]
    finally:
        set_cloud_session_factory(None)


def test_register_then_status_round_trip():
    try:
        with TestClient(create_app("sqlite:///:memory:")) as client:
            registered = client.post(
                "/api/sync/devices/register",
                json={"device_name": "Smoke Test PC"},
            )
            assert registered.status_code == 200
            body = registered.json()
            assert body["device_id"]
            assert body["api_key"]

            status = client.get(
                "/api/sync/status",
                headers={
                    "X-Device-ID": body["device_id"],
                    "X-API-Key": body["api_key"],
                },
            )
            assert status.status_code == 200
            assert status.json()["device_id"] == body["device_id"]
    finally:
        set_cloud_session_factory(None)


def test_create_app_uses_provided_engine():
    from app.sync.cloud_db import create_cloud_engine, create_cloud_session_factory

    engine = create_cloud_engine("sqlite:///:memory:")
    sf = create_cloud_session_factory(engine)
    try:
        with TestClient(
            create_app(engine=engine, cloud_db_url="sqlite:///unused.db")
        ) as client:
            registered = client.post(
                "/api/sync/devices/register",
                json={"device_name": "Engine PC"},
            )
            assert registered.status_code == 200
            assert sf() is not None
    finally:
        engine.dispose()
        set_cloud_session_factory(None)