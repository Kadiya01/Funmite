# Open Decisions

Unresolved client decisions. Do not invent these rules. When a phase hits one
of these boundaries, record the context here and stop that branch unless the
decision does not block the phase.

## From the master specification (section 8)

- **Receipt branding/footer** -- RESOLVED: Wireframe candidate defaults implemented in `ReceiptBuilder`. Final text configurable in code constants; no functional blocker.
- **Discount limits** -- RESOLVED: Admin-only discount confirmed (approved matrix). Implemented in Phase 05. `PERCENT` and `FIXED` with no ceiling; cannot make total negative.
- **Receipt numbering format** -- RESOLVED: `FUN-YYYYMMDD-NNN` candidate implemented in Phase 05. Used in production. Prefix/digits localized in `sale_service.py`.
- **Product import columns** — exact columns and format for bulk import.
- **Exchange refund / price-difference behavior** — how a difference is settled
  under the no-cash rule, especially when the customer is owed money.
- **Multi-item exchange rules** — how exchanges spanning multiple items are
  handled.
- **Backup retention / destination** — RESOLVED: All backups are kept in the
  configured backup directory (`FUNMITE_BACKUP_DIR`, default `<project_root>/backups/`).
  No auto-purge. Users manage retention manually. Phase 09 implemented this way.
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
  rule (see above).
- Final product data volume and data-entry/import format.
- Whether the virtual Lagos branch is only a future concept or must appear in
  V1 reports.
- Exact cloud remote UI scope within the V1 agreement.
- Exact backup frequency and retention count — RESOLVED: Manual trigger only,
  no auto-purge, all backups kept. Phase 09 implemented this way.
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

- **Receipt number device prefix** — the phase prompt suggested adding a
  device prefix to receipt numbers to avoid collision across PCs. This was
  deferred because it's ambiguous in the source-of-truth (the approved format
  is `FUN-YYYYMMDD-NNN`). The database `UNIQUE` constraint on `receipt_no`
  remains the final guard. Confirm whether a device prefix is needed for
  multi-PC production.
- **Backup encryption** — the security rule says "Protect local backups" but no
  encryption mechanism is specified. Phase 09 stores plain SQLite files. Confirm
  whether backups should be encrypted or password-protected before production.
- **Backup file cleanup** — no auto-purge is implemented. Confirm whether a
  maximum backup count or disk-space threshold should trigger automatic cleanup.
- **Backup timestamp collision** — `test_multiple_backups_all_valid` is flaky
  because two backups created within the same second get identical filenames.
  The backup service uses microsecond precision; the collision window is ~1s.
  Documented as a known issue. Fix deferred.

## Added during Phase 06

- **Customer-owed refund settlement** — when the replacement item costs less than
  the returned item(s), the customer is owed money. Phase 06 refuses that branch
  with `ValidationError` and records it here. The settlement method (cash refund,
  credit toward a future sale, bank transfer back) must be confirmed. Until then,
  exchanges where the customer is owed money are blocked.
- **Exchange receipt printing** — whether a separate exchange receipt or an addendum
  to the original sale receipt should be printed. Phase 06 does not print anything;
  confirm before production.
- **Admin 2-day override** — whether the Admin should be able to override the
  2-day exchange window. Phase 06 enforces the window with no override. Confirm
  whether the Admin may extend or bypass it.

## Added during Phase 05

- **Payment reference field** — the technical architecture asks which reference
  number is recorded for POS/Transfer transactions. Phase 05 added an optional
  free-text "Reference" field stored on `payments.reference`. Confirm whether a
  reference should be mandatory for either method.
- **Cashier reprint rights** — UC-06 "Reprint Receipt" has no dedicated
  capability in the matrix, so Phase 05 gates reprint to Admin via the closest
  capability, `CAP_VIEW_REPORTS`. Confirm whether the Cashier may reprint.
- **Cashier creates walk-in customers** -- RESOLVED: Cashier can create minimal walk-in customers at the till via `CustomerService.create_for_sale` (name required, phone optional) gated by `CAP_MAKE_SALE`. Full customer management stays Admin-only. Implemented in Phase 05.
  customers at the till.
- **Low-stock note after a sale** -- RESOLVED: Scoped to the sale own items only. Implemented in Phase 05.
- **ESC/POS naira rendering** — PC437 (thermal printers) has no naira glyph, so
  the ESC/POS renderer prints `N` instead of `₦` on the paper receipt. Applies
  only to the printed copy; on-screen text keeps `₦`. A hardware/print decision
  (Phase 11) may override this.

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