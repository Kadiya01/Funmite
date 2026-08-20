# PHASE 10 ARCHITECTURE

## Selected Architecture: Option A — Dual Independent SQLite + Cloud Sync

Each PC runs the full Funmite POS application with its own local SQLite
database. A sync engine on each PC enqueues local mutations to a sync outbox.
A background worker pushes pending changes to a cloud PostgreSQL database via
a secure REST API. The owner accesses business data remotely through the
cloud API.

```
COMPUTER 1 (Admin PC)              COMPUTER 2 (Cashier PC)
┌─────────────────────┐            ┌─────────────────────┐
│ Funmite POS         │            │ Funmite POS         │
│ funmite.db (SQLite) │            │ funmite.db (SQLite) │
│ Sync Engine         │            │ Sync Engine         │
│ Sync Worker         │            │ Sync Worker         │
└────────┬────────────┘            └────────┬────────────┘
         │                                  │
         │         LAN (optional)           │
         ├──────────────────────────────────┤
         │                                  │
         └──────────────┬───────────────────┘
                        │ HTTPS
                        ▼
              ┌─────────────────┐
              │  Cloud Service  │
              │  PostgreSQL/API │
              └────────┬────────┘
                       │ HTTPS
                       ▼
              ┌─────────────────┐
              │  Owner Phone/   │
              │  Laptop (read)  │
              └─────────────────┘
```

## Why Option A

1. **Offline-first preserved.** Each PC operates independently. No LAN or
   Internet dependency for local operations.
2. **Inventory correctness via movement-based sync.** Stock is derived from
   synced inventory movements, not from syncing absolute quantity values.
   Both PCs can sell the same product offline; the cloud applies all movements
   and derives the correct final stock.
3. **Receipt uniqueness via device prefix.** Receipt numbers are
   `{DEVICE}-{YYYYMMDD}-{NNN}`. Each PC generates its own sequence. No
   collisions possible.
4. **Append-only financial records.** Sales, payments, expenses, purchases,
   and exchanges are never overwritten — only created. Sync is idempotent
   on entity_type + entity_id.
5. **Conflict detection for mutable reference data.** Products, customers,
   categories use version columns for optimistic locking. Last-write-wins
   at the cloud level with conflict logging.
6. **Simple deployment.** No LAN server to maintain. No FastAPI service
   on one PC. Both PCs are equal peers.
7. **Kano-appropriate.** Two PCs in one room. Internet may be unreliable.
   The system handles this gracefully.

## Why Not Option B (Single Server)

Option B (Admin PC hosts database + API, Cashier connects via LAN) would
eliminate dual-DB conflicts but violates the confirmed offline-first
requirement: if the Admin PC or LAN fails, the Cashier PC cannot operate.
The client explicitly confirmed the shop must continue selling without
Internet/LAN. In a small boutique, "LAN failure" and "Admin PC off" are
real scenarios (power outage on one PC, cable unplugged, Windows update).

## Why Not Option C (LAN Sync + Cloud Sync)

Option C adds LAN synchronization on top of cloud synchronization. This
doubles the sync complexity (two sync protocols, two failure modes) for
minimal benefit. The cloud sync already handles the case where both PCs
operate offline and reconcile later. LAN sync would only matter if both
PCs needed real-time stock visibility — but the existing `minimum_stock`
threshold and the client's small inventory make occasional brief stock
discrepancies acceptable and self-correcting on next sync.

## Key Design Decisions

### Globally Unique Identifiers

Local `id INTEGER PRIMARY KEY` remains the primary key within each local
database. For cloud sync, each entity gets a `sync_uuid TEXT` column
(UUID v4) generated on first creation. The cloud database uses `sync_uuid`
as the unique identifier. The local `id` is never exposed to the cloud.

### Sync Outbox Pattern

After every local transaction that modifies synced data, a `sync_queue`
row is created with the entity type, local ID, operation (CREATE/UPDATE/
DELETE), and a JSON payload of the full row. The background sync worker
picks PENDING entries and pushes them to the cloud API.

### Movement-Based Inventory Sync

Stock quantity is NEVER synced directly. Instead, inventory movements
(sales, stock-in, exchanges, adjustments) are synced. The cloud database
derives stock by replaying movements. This prevents oversell: if both PCs
sell 5 units of a product with 10 in stock, the cloud sees two -5
movements and derives stock = 0, not -5 or 5.

### Conflict Strategy

| Entity Type | Strategy | Rationale |
|---|---|---|
| Sales, Payments, Expenses, Purchases, Exchanges, InventoryLogs | Append-only, no conflict | Financial records are never edited |
| Products | Version column, last-write-wins | Reference data, rare concurrent edits |
| Categories | Version column, last-write-wins | Reference data, very rare concurrent edits |
| Customers | Version column, last-write-wins | Reference data, possible concurrent edits |
| Suppliers | Version column, last-write-wins | Reference data, rare concurrent edits |
| Users | Local only, never synced | Credentials must not leave the PC |

### Sync States

```
PENDING → SYNCING → SYNCED
                  → FAILED → (retry) → SYNCING
                           → (max retries) → CONFLICT_MANUAL
```

### Idempotency

The cloud API uses `entity_type + sync_uuid` as the idempotency key.
Retrying the same sync request is safe — the cloud recognizes the
duplicate and returns success without creating a new record.

### Backup Compatibility

After restore, the sync_queue is cleared. The restored database is treated
as a fresh state. On next sync, the full current state is pushed to the
cloud, overwriting any previous cloud data for this device. This is safe
because the restored database represents the owner's intended state.

## Phase 10C — Cloud Synchronization API Layer

### Module Structure

```
app/sync/
├── __init__.py        # Package docstring
├── cloud_models.py    # Cloud SQLAlchemy models (sync_uuid as PK, no integer IDs)
├── cloud_db.py        # Engine creation, schema init, session factory
├── schemas.py         # Pydantic request/response models for wire format
├── cloud_api.py       # FastAPI router: /api/sync/devices/register, /push, /pull, /status
├── client.py          # SyncClient (httpx) — local POS → cloud HTTP calls
├── apply.py           # Apply pulled mutations to local SQLite (FK resolution, datetime coercion)
└── worker.py          # SyncWorker — background daemon thread, periodic push/pull
```

### Cloud Database

- **Schema:** mirrors all synced local entities using `sync_uuid` as primary key.
  Integer `id` is never exposed to cloud.
- **Idempotency:** `entity_type + sync_uuid` unique constraint on `cloud_sync_log`.
  Duplicate pushes are recognized and accepted silently.
- **Engine:** In-memory SQLite with `StaticPool` for tests; PostgreSQL for production.
  Controlled by `CLOUD_DB_URL` env var.

### API Endpoints

| Endpoint | Method | Auth | Description |
|---|---|---|---|
| `/api/sync/devices/register` | POST | None | Register new device, returns `device_id` + `api_key` |
| `/api/sync/push` | POST | `X-Device-ID` + `X-API-Key` | Push local mutations to cloud |
| `/api/sync/pull` | POST | `X-Device-ID` + `X-API-Key` | Pull mutations from other devices since timestamp |
| `/api/sync/status` | GET | `X-Device-ID` + `X-API-Key` | Device sync status |

### Push Logic

1. Append-only entities (sales, payments, expenses, etc.): always accepted if
   `sync_uuid` not seen before; idempotent skip if already present.
2. Reference entities (categories, products, customers, suppliers): version-based
   conflict detection. Higher version wins. Same version with no `created_at`
   is an idempotent no-op. Same version with newer timestamp wins (last-write-wins).
3. DELETE operations: remove entity from cloud if present.

### Pull Logic

- Returns mutations from `cloud_sync_log` where `created_at > since` and
  `device_id != requesting_device_id` (never return own mutations).
- Payload includes full entity state from cloud tables.
- Maximum 200 mutations per pull with `has_more` flag.

### Local Apply Logic

When pulling mutations from cloud and applying to local SQLite:
1. **FK resolution:** Cloud payloads use `*_sync_uuid` fields; resolved to local
   integer IDs by querying local database.
2. **User FK defaults:** Users are never synced. Required user FK fields
   (`cashier_id`, `recorded_by`, `created_by`, `approved_by`, `user_id`)
   default to user ID 1 (admin) when absent from payload.
3. **Datetime coercion:** ISO string timestamps from cloud are converted to
   Python `datetime` objects for SQLite compatibility.
4. **Cloud-only fields stripped:** `device_id`, `cashier_name`, `recorded_by_name`,
   etc. are removed before local insert.
5. **Idempotent inserts:** Append-only entities skip if `sync_uuid` already exists
   locally. Reference entities upsert with version check.

### Configuration

New settings in `app/config.py`:
- `cloud_sync_enabled: bool = False`
- `cloud_db_url: str = "sqlite:///cloud.db"`
- `sync_push_interval: int = 30` (seconds)
- `sync_pull_interval: int = 60` (seconds)

### Test Coverage

`tests/test_cloud_sync.py` — 39 tests covering:
- Cloud schema creation
- Device registration (credentials, DB persistence, multiple devices)
- Auth (valid/invalid credentials, no-auth rejection)
- Push sync (categories, products, sales with full payloads)
- Idempotent push (duplicate accepted, append-only duplicate skipped)
- Conflict resolution (higher version wins, same version last-write-wins,
  stale version rejected)
- Pull sync (incremental since timestamp, entity type filtering)
- Apply mutations locally (categories, products, customers, suppliers, sales)
- Two-device convergence with offline period + reconnect sync
- DELETE operations
- SyncWorker (push/pull cycle, error handling)
- Full round-trip (push → pull → apply → verify)
