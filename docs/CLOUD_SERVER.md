# Funmite Cloud Sync Service (Phase 2 — M1)

The cloud sync server is the **online** half of the offline-first POS. Each PC
keeps its own local SQLite database and a background worker pushes/pulls
mutations through this service into a shared cloud database. This document
covers Phase 2 M1: the runnable FastAPI application.

## Status (truthful to the current milestone)

- **M1 done:** a real, runnable FastAPI application exists
  (`create_app()` / module-level `app` in `app/sync/cloud_api.py`), a Windows
  launcher exists, and an automated smoke test exercises the app through the
  FastAPI test interface.
- **Not done yet (later milestones):** the PostgreSQL driver (M2), provisioning
  of a managed PostgreSQL database and a public host (M3), and the two-PC field
  validation (M3). Today the service runs against the configured
  `FUNMITE_CLOUD_DB_URL`, which defaults to the development backend
  `sqlite:///cloud.db`. Switching to PostgreSQL later requires no code change —
  only the driver (M2) and the URL.

## The single implementation

`app/sync/cloud_api.py` is the one and only cloud-server implementation:

- `router` — the sync routes (`/api/sync/devices/register`, `/push`, `/pull`,
  `/status`).
- `create_app(cloud_db_url=None, *, engine=None)` — builds the FastAPI app. On
  startup it creates the cloud engine (from the URL, or the injected engine),
  initializes the cloud schema, and configures the session factory used by the
  routes.
- `app = create_app()` — module-level instance the launcher serves.

`app/api/server.py` is a deprecated stub and must not be used; it points
readers here.

## Starting it

Windows launcher:

```bat
set FUNMITE_CLOUD_DB_URL=sqlite:///cloud.db
scripts\run_cloud_server.bat
```

Equivalent direct command:

```bat
.venv\Scripts\python.exe -m uvicorn app.sync.cloud_api:app --host 127.0.0.1 --port 8000
```

The launcher defaults to `127.0.0.1:8000`; override with `FUNMITE_API_HOST` and
`FUNMITE_API_PORT`.

## Configuration

| Variable | Default | Meaning |
|---|---|---|
| `FUNMITE_CLOUD_DB_URL` | `sqlite:///cloud.db` | Cloud database URL. `postgresql://…` works once the driver exists (M2). |
| `FUNMITE_API_HOST` | `127.0.0.1` | uvicorn bind host. |
| `FUNMITE_API_PORT` | `8000` | uvicorn bind port. |

The URL is also used by POS clients through the same settings
(`app/config.py`). In production the server and the POS PCs share the same
`FUNMITE_CLOUD_DB_URL`.

## Endpoints

| Endpoint | Method | Notes |
|---|---|---|
| `/api/sync/devices/register` | POST | Register a device, returns `device_id` + `api_key`. |
| `/api/sync/push` | POST | Push local mutations (auth: `X-Device-ID`, `X-API-Key`). |
| `/api/sync/pull` | POST | Pull other devices' mutations since a timestamp. |
| `/api/sync/status` | GET | Device sync status (auth required). |

Interactive docs are available at `/docs` when the server is running.

## Smoke test

```bat
set PYTHONPATH=.
.venv\Scripts\python.exe -m pytest tests/test_cloud_server.py -q
```

`tests/test_cloud_server.py` proves the module-level app exists with the sync
routes, startup initializes the schema/factory through `TestClient`, the status
endpoint is reachable (rejects missing credentials with 401), and a full
register → status round-trip succeeds.

## Backend note

- `sqlite:///:memory:` and `sqlite:///cloud.db` are the development/test
  backends (see `app/sync/cloud_db.py`).
- Production uses PostgreSQL (M2/M3). No PostgreSQL driver is installed yet;
  that is deliberately deferred to M2.