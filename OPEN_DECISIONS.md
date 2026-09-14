# Open Decisions

Unresolved client decisions. Do not invent these rules. When a phase hits one
of these boundaries, record the context here and stop that branch unless the
decision does not block the phase.

## v1.3.0 confirmed batch (shop-use decisions)

The following were confirmed in a single batch before the v1.3.0 release:

- **Two-PC sync** -- RESOLVED: keep the existing dual-SQLite + cloud sync (Option A).
- **Exchange customer-owed (price-difference) refund** -- RESOLVED: settled as
  **store credit** tracked in the `customer_credits` ledger
  (source `EXCHANGE` adds, `SALE_PAYMENT` subtracts; amount always positive).
- **Store-credit spend** -- RESOLVED: a customer's store-credit balance is
  spendable at the till on the customer's next sale (`PAYMENT_CREDIT`); the
  balance can never go below zero.
- **Admin 2-day exchange override** -- RESOLVED: the Admin may override the
  2-day exchange window with a confirmation prompt and an audit record
  (`EXCHANGE_WINDOW_OVERRIDE`).
- **Cancel sale** -- RESOLVED: an Admin may reverse + void a finished sale
  (`CAP_CANCEL_SALE`). The sale is marked `CANCELLED` (never deleted), stock is
  restored with a matching `inventory_log`, and store credit paid on the sale
  is refunded to the customer's ledger.
- **Cashier end-of-day** -- RESOLVED: the cashier's EOD report shows only their
  own sales/COGS/payments for the day (expenses remain shop-wide),
  gated by `CAP_VIEW_OWN_SALES`.
- **Cashier reprint** -- RESOLVED: reprint is allowed for Admin **and** Cashier
  via the shared `CAP_REPRINT_RECEIPT`; cancelled sales can never be reprinted.
- **Multi-item exchange** -- RESOLVED: keep multi-item exchanges.
- **Printing the naira sign** -- RESOLVED: ESC/POS prints `NGN` (PC437 has no
  naira glyph); on-screen text keeps `₦`.
- **Backup retention** -- RESOLVED: backups are purged automatically after each
  backup (keep newest `FUNMITE_BACKUP_KEEP`, default 30; delete older than
  `FUNMITE_BACKUP_MAX_AGE_DAYS`, default 90 days; both rules must apply; 0
  disables a rule).
- **Release/versioning** -- RESOLVED: ship this batch as **v1.3.0** and rebuild
  the standalone `.exe`.

Still open after the batch (non-blocking): exact Excel CSV column headers for
the product import template, whether a payment reference is mandatory, and the
allowed set of expense categories.

## From the master specification (section 8)

- **Receipt branding/footer** -- RESOLVED: Wireframe candidate defaults implemented in `ReceiptBuilder`. Final text configurable in code constants; no functional blocker.
- **Discount limits** -- RESOLVED: Admin-only discount confirmed (approved matrix). Implemented in Phase 05. `PERCENT` and `FIXED` with no ceiling; cannot make total negative.
- **Receipt numbering format** -- RESOLVED: `FUN-YYYYMMDD-NNN` candidate implemented in Phase 05. Used in production. Prefix/digits localized in `sale_service.py`.
- **Product import columns** — exact columns and format for bulk import (awaiting
  the shop's actual Excel file; default CSV template implemented in Phase 03).
- **Exchange refund / price-difference behavior** — RESOLVED: store credit
  (see v1.3.0 confirmed batch).
- **Multi-item exchange rules** — RESOLVED: keep multi-item exchanges
  (see v1.3.0 confirmed batch).
- **Backup retention / destination** — RESOLVED: backups live in the configured
  backup directory (`FUNMITE_BACKUP_DIR`, default `<project_root>/backups/`).
  Auto-purge implemented in v1.3.0 (keep newest 30 / delete older than 90 days,
  env-tunable).
- **Selected cloud/hybrid package** — RESOLVED: Option A — Dual Independent
  SQLite + Cloud Sync. Each PC has its own local SQLite database; a sync
  outbox pattern pushes/pulls to cloud PostgreSQL. Phase 10 implemented this.
- **LAN synchronization method** — RESOLVED: Background `SyncWorker` thread
  with outbox pattern (push every 30s, pull every 60s). Manual trigger
  available via Settings UI. Phase 10 implemented this.
- **Deployment topology** — RESOLVED: Each PC runs independently with its
  own `funmite.db`. Cloud PostgreSQL serves as the central aggregation point
  for remote owner access. No LAN FastAPI — each PC is fully self-contained.
  Phase 10 implemented this.

## From the technical architecture (section 18)

- Exact receipt number prefix/format (see above).
- Exact mechanism for settling exchange price differences under the no-cash
  rule (see above) — RESOLVED: store credit (v1.3.0).
- Final product data volume and data-entry/import format.
- Whether the virtual Lagos branch is only a future concept or must appear in
  V1 reports.
- Exact cloud remote UI scope within the V1 agreement.
- Exact backup frequency and retention count — RESOLVED: manual trigger, with
  auto-purge of old backups after each new backup (keep newest 30 / older than
  90 days) implemented in v1.3.0.
- Which payment reference number is recorded for POS/Transfer transactions, if
  any.
- Whether product images are mandatory or optional.

## Added during development

- **Deployment topology** — RESOLVED: Each PC runs independently with its own
  `funmite.db`. Cloud PostgreSQL is the central aggregation point for remote
  owner access. No LAN FastAPI hosting — each PC is fully self-contained and
  offline-first. Phase 10 implemented this (Option A).
- **Receipt barcode content** -- RESOLVED: Encodes the receipt number exactly (e.g. `FUN-20260101-001`). Format: `FUN-YYYYMMDD-NNN`. Symbology: Code128. Rationale: human-readable, unique (DB constraint), standard retail practice. Implemented in Phase 05.
  whether the receipt barcode encodes the receipt number exactly. Candidate from the
  wireframes: the receipt barcode represents the receipt/transaction identifier.
- **Expenses scope** — Artifact `05` checklist asks whether expenses include all shop
  expenses or only selected categories. The approved schema has a free-text
  `expenses.category`; the allowed set is unconfirmed.
- **Supplier purchase `balance` semantics** — Artifact `05` checklist asks whether
  `purchases.balance` is a true payable or simply an informational purchase record.
  Since credit sales are prohibited, this must not imply supplier credit terms
  without confirmation.
- **Cloud remote access scope in V1** — RESOLVED: Cloud PostgreSQL is the central
  aggregation point. Remote owner access is read-only via cloud DB queries. No
  web UI — the cloud API provides push/pull endpoints for device sync. Phase 10
  implemented this.
- **Customer without phone** -- RESOLVED: `customers.phone` is nullable with no uniqueness constraint. Customers without phone numbers work correctly. Walk-in customers created by Cashier can omit phone. Implemented in Phase 03.
  Artifact `01` notes blank/unknown phones must not create duplicate-key problems.
  Phase 03 implemented a customer without a phone (nullable, no uniqueness), matching
  the approved schema. Confirmation pending.
- **Customer-record management permission** -- RESOLVED: Admin-only (`manage_customers`) confirmed and implemented. Cashier can create minimal walk-in customers at the till via `create_for_sale`.
  records.

## Added during Phase 10

- **Receipt number device prefix** -- RESOLVED: Implemented in Phase 2 (online
  sync). Receipt numbers now use `{DEVICE}-YYYYMMDD-NNN`, where `DEVICE` is the
  first 6 hex characters of the per-installation `data/device.id` UUID
  (uppercased). Each PC mints its own daily sequence, so no collisions across
  PCs. The cloud `sales.receipt_no` column carries a UNIQUE constraint as the
  final guard. Legacy `FUN-…` receipts remain readable for lookup/reprint.
- **Backup encryption** — the security rule says "Protect local backups" but no
  encryption mechanism is specified. Phase 09 stores plain SQLite files. Confirm
  whether backups should be encrypted or password-protected before production.
- **Backup file cleanup** — RESOLVED: automatic retention implemented in v1.3.0
  (keep newest `FUNMITE_BACKUP_KEEP` = 30, delete older than
  `FUNMITE_BACKUP_MAX_AGE_DAYS` = 90 days; both rules apply; 0 disables a rule).
- **Backup timestamp collision** — `test_multiple_backups_all_valid` is flaky
  because two backups created within the same second get identical filenames.
  The backup service uses microsecond precision; the collision window is ~1s.
  Documented as a known issue. Fix deferred.

## Added during M3 (two-PC online-sync gate)

- **Inventory convergence model** -- RESOLVED: version-LWW on
  `product.quantity` undercounts in the concurrent-offline case (both PCs
  record 15→14 while the true on-hand is 13). The receiving PC applies pulled
  `inventory_log.change_quantity` deltas to its own running `product.quantity`
  (floored at 0) instead of copying `previous/new_quantity` verbatim. `sync_uuid`
  skip makes the application idempotent. Implemented in `app/sync/apply.py`.
- **Client auth device id bug** (found by the M3 gate) -- RESOLVED: registration
  stored the local `DeviceIdentity.device_id` as the cloud device id, but the
  server authenticates against the cloud-assigned registry id, so every real
  HTTP push/pull returned 401. `save_credentials` now persists the cloud
  `device_id` returned by the register endpoint; `SyncWorker._build_client`
  uses it for the `X-Device-ID` header. Existing SQLite-shim integration tests
  never exercised the real HTTP path — the gate did.
- **Cloud-only columns leaking into local inserts** (found by the M3 gate) --
  RESOLVED: pulled payloads carry cloud-only fields (e.g. `CloudSaleItem.created_at`,
  which local `SaleItem` lacks) and were passed to the local model constructor,
  raising `TypeError`. `_prepare_local_data` now filters to columns that exist
  on the local model.
- **M3 gate evidence** -- `tests/test_shop_two_pc_workflow.py` runs both PCs as
  real offline SQLite stores against a live uvicorn + real PostgreSQL: both PCs
  sell offline, reconnect, push/pull, and converge (receipts, movements,
  payments, cloud counts, independent backups); a cloud-down PC still sells and
  its worker retries successfully on recovery. Skipped when `FUNMITE_TEST_PG_URL`
  is unset.

## Added during Phase 06

- **Customer-owed refund settlement** — RESOLVED: the customer-owed difference is
  refunded as store credit on the `customer_credits` ledger and is spendable at
  the till on the customer's next sale (v1.3.0).
- **Exchange receipt printing** — whether a separate exchange receipt or an addendum
  to the original sale receipt should be printed. Phase 06 does not print anything;
  confirm before production.
- **Admin 2-day override** — RESOLVED: the Admin may override the 2-day exchange
  window behind a confirmation prompt, and every override is audit-logged
  (`EXCHANGE_WINDOW_OVERRIDE`). Implemented in v1.3.0.

## Added during Phase 05

- **Payment reference field** — the technical architecture asks which reference
  number is recorded for POS/Transfer transactions. Phase 05 added an optional
  free-text "Reference" field stored on `payments.reference`. Confirm whether a
  reference should be mandatory for either method.
- **Cashier reprint rights** — RESOLVED: the Cashier may reprint receipts via the
  shared `CAP_REPRINT_RECEIPT` capability; Admin and Cashier can reprint, and a
  cancelled sale cannot be reprinted. Implemented in v1.3.0.
- **Cashier creates walk-in customers** -- RESOLVED: Cashier can create minimal walk-in customers at the till via `CustomerService.create_for_sale` (name required, phone optional) gated by `CAP_MAKE_SALE`. Full customer management stays Admin-only. Implemented in Phase 05.
  customers at the till.
- **Low-stock note after a sale** -- RESOLVED: Scoped to the sale own items only. Implemented in Phase 05.
- **ESC/POS naira rendering** — RESOLVED: PC437 (thermal printers) has no naira
  glyph, so the ESC/POS renderer and the paper receipt print `NGN` instead of
  `₦`. On-screen text keeps `₦`. Implemented in v1.3.0.

## Added during Phase 04

- **Inventory management permission** -- RESOLVED: Admin-only for stock operations and history viewing. Implemented in Phase 04.
- **Stock-in without a purchase record** -- RESOLVED: Both standalone stock-in (Phase 04) and purchase-linked stock-in (Phase 07) flow through the same `InventoryService.change_stock` writer with `reference_type=STOCK_IN`. All stock movements are auditable via `inventory_logs`. No restriction needed.
- **Low-stock popup scope** -- RESOLVED: Popup triggered after Admin stock operations AND after sales that leave a product at or below `LOW_STOCK_THRESHOLD`. Uses reusable `show_low_stock_alert` widget. Implemented in Phases 04-05.

## Added during Phase 03

- **Barcode symbology/format** -- RESOLVED: 13-digit numeric (12 + Luhn check). Symbology: Code128. No GS1/EAN needed (private shop). Uniqueness: counter + batch + DB constraint. Implemented in Phase 03.
  system generates one per product (confirmed). Phase 03 implemented a
  candidate format: a 13-digit numeric value (12-digit sequence + Luhn check
  digit) rendered as Code128, which a generic scanner reads back as plain
  digits. No GS1/EAN allocation exists; confirm the final symbology/format
  before labels are mass-printed.
- **Product import columns / format** — the exact import columns are
  unconfirmed. Phase 03 implemented a documented default CSV template
  (`Name,Category,Brand,Size,Color,Cost Price,Selling Price,Quantity,Minimum
  Stock,Product Code,Barcode`) with flexible header aliases. Confirm or
  replace before production data is imported.
- **Import vs existing records** — importing *updates* to existing products
  is intentionally NOT implemented in Phase 03 (duplicates are reported and
  skipped). Confirm whether an update mode is required.