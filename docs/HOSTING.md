# Funmite Cloud Sync — Hosting Runbook (Phase 2 M3 hosting)

This runbook deploys the cloud sync service so POS PCs reach it over HTTPS.
Architecture (unchanged): **PC-A / PC-B → HTTPS FastAPI → managed PostgreSQL**.

The single implementation is `app/sync/cloud_api.py`. The app needs no
credentials from this repository: every secret is supplied by the hosting
provider as an environment variable. This repository contains **no**
database URLs, passwords, API keys, or `.env` files.

## What you deploy

| Artifact | Purpose |
|---|---|
| `Procfile` | Render `web` start command. |
| `render.yaml` | Blueprint for the web service; the managed PostgreSQL is **external (Neon)** and its connection string is supplied as a provider secret. |
| `app/sync/cloud_api.py` | The FastAPI app (module-level `app` = uvicorn target). |
| `app/sync/cloud_db.py` | Engine bootstrap; `init_cloud_schema` = idempotent `create_all`. |
| `/healthz` | Provider health check: `200` only when the DB answers. |

## 1. Provision (Neon + Render)

Two resources across two providers:

1. **Managed PostgreSQL on Neon** — create a project; Neon returns a
   connection string of the form
   `postgresql://user:pass@host/dbname?sslmode=require`. The `sslmode=require`
   is important: Neon only accepts TLS. `psycopg2` honours it from the URL, so
   no code change is needed.
2. **Web service on Render** — blueprints from `render.yaml`: one web service
   running `python -m uvicorn app.sync.cloud_api:app --host 0.0.0.0 --port
   $PORT --workers 1`, build command `pip install -r requirements.txt`.

The blueprint does **not** create a database and does not hold the connection
string. In the Render dashboard (Environment → Secrets) set
`FUNMITE_CLOUD_DB_URL` to the Neon connection string (an external resource
managed by Neon; back it up per Neon's snapshot policy, never via this repo).

## 2. Environment variables (secrets live in the provider)

| Variable | Set to | Notes |
|---|---|---|
| `FUNMITE_CLOUD_DB_URL` | Neon connection string (incl. `?sslmode=require`) | The app's primary variable. Set it as a **secret in the provider** (Render Environment → Secrets). The blueprint declares it `sync: false`, so your value is never overwritten by deploys. |
| `DATABASE_URL` | *(optional fallback)* | Used only if `FUNMITE_CLOUD_DB_URL` is unset. |
| `PYTHONUNBUFFERED` | `true` | Flush logs in production. |
| `FUNMITE_LOG_LEVEL` | `INFO` | Optional. |

Never store these in the repo. If a provider requires a specific variable name,
map it in the provider console (secrets section) — the code reads
`FUNMITE_CLOUD_DB_URL` first, then `DATABASE_URL`.

## 3. HTTPS

- Terminate TLS at the hosting edge. Render issues and renews certificates
  automatically for the service's default `onrender.com` URL, and for a
  custom domain once you add and verify it.
- POS PCs in the field configure the **`https://`** service URL in
  Settings → Sync. Never populate that field with `http://` from a browser or
  curl unless you are on Render's internal network.
- If the provider's URL is `http`-only (rare dev hosts), the POS client still
  works, but treat it as test-only.

## 4. Startup / schema behavior

On every first request and restart the app runs `init_cloud_schema`
(`create_all`, idempotent) against the managed database, then installs its
session factory. Consequences:

- The schema exists automatically on first boot — no manual SQL migration step
  at deploy time. Schema *evolution* (future migrations) is still a
  controlled, explicit task; `create_all` never alters existing tables.
- The app is stateless across processes; a single web worker is plenty for a
  two-PC shop. If you ever scale workers, each process re-runs idempotent
  `create_all` — safe.

## 5. Health / observability

- `GET /healthz` → `200 {"status":"ok","database":"up"}` (DB reachable) or
  `503`. Point the provider health check here (Render: default 5s interval /
  3 retries). The service restarts automatically on repeated failure.
- `GET /api/sync/status` (auth: `X-Device-ID`, `X-API-Key`) reports a device's
  dead-letters and last sync state — use it to confirm devices are talking.
- App logs go to stdout; the provider aggregates them (Render dashboard).

## 6. Point the PCs at it

1. On **PC-A** and **PC-B**: Settings → Sync → registration with the service's
   HTTPS URL. Each PC stores its own `sync_credentials.json` (device id +
   api_key) locally. Those files are **machine secrets** — never copy them
   between PCs or commit them.
2. Ensure the POS worker is enabled (Settings → Sync enabled). Push every 30s,
   pull every 60s; offline periods keep the queue local, and sync catches up on
   reconnect.

## 7. Post-deploy gates (hosted)

These prove the flip-to-live, against the **hosted** URL:

1. `GET https://<service>/healthz` → 200 (service up **and** DB connected).
2. Register **PC-A** then **PC-B** (two distinct devices).
3. PC-A pushes its catalog; PC-B pulls it.
4. Offline sale on each PC → reconnect → both converge (movements drain,
   inventory true on-hand matches, device-prefixed receipts unique).
5. Stop the cloud service → PCs still complete sales offline; restart the
   service → the pending queue drains (push retries succeed).
6. Full regression suite (`800 passed, 6 skipped`) stays green; SQLite and
   real-PG infrastructure tests are reported separately (PG gates skip when
   `FUNMITE_TEST_PG_URL` is unset).

## 8. Rollback

- **Code:** Render keeps prior deploys; `autoDeploy` is on, so revert to the
  last green commit by redeploying it.
- **Data:** the managed database is externally managed — snapshot/backup per
  provider policy. Nothing in this repo can lose it, and the POS PCs never
  lose local data (offline-first).

## Out of scope (M4)

Owner web dashboard / read-only remote UI is a **separate milestone (M4)** and
is intentionally not built here. This runbook delivers only the sync backend
that PCs talk to.