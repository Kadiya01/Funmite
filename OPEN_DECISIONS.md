# Open Decisions

Unresolved client decisions. Do not invent these rules. When a phase hits one
of these boundaries, record the context here and stop that branch unless the
decision does not block the phase.

## From the master specification (section 8)

- **Receipt branding/footer** — text, layout and branding on receipts.
- **Discount limits** — whether discounts are allowed and any ceiling; which
  role may apply discounts.
- **Receipt numbering format** — exact prefix/format of receipt numbers.
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
- **Receipt barcode content** — Artifact `05` schema-freeze checklist asks to confirm
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
- **Customer without phone** — the approved schema makes `customers.phone` nullable;
  Artifact `01` notes blank/unknown phones must not create duplicate-key problems.
  Phase 03 implemented a customer without a phone (nullable, no uniqueness), matching
  the approved schema. Confirmation pending.
- **Customer-record management permission** — the use-case permission matrix
  does not list creating/editing customer records. During Phase 02 this
  defaulted to Admin-only (`manage_customers`) since the cashier can still
  select an existing customer during a sale. Phase 03 shipped with this
  default (Admin-only). Confirm whether the cashier may create customer
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
- **Multi-item exchange rules** — Phase 06 validates each line independently (the
  product was sold on this sale, the quantity does not exceed the remaining
  un-exchanged quantity, no duplicate return lines, no duplicate replacement
  lines). Whether a single exchange must involve exactly one return/replacement or
  can span multiple mixed lines with mixed settlement (some customer pays, some
  shop pays) is not yet confirmed.
- **Exchange receipt printing** — whether a separate exchange receipt or an addendum
  to the original sale receipt should be printed. Phase 06 does not print anything;
  confirm before production.
- **Admin 2-day override** — whether the Admin should be able to override the
  2-day exchange window. Phase 06 enforces the window with no override. Confirm
  whether the Admin may extend or bypass it.

## Added during Phase 05

- **Receipt number format** — the wireframe layout shows a receipt/transaction
  number but no exact prefix. Phase 05 implemented the candidate
  `FUN-<YYYYMMDD>-<NNN>` (e.g. `FUN-20260116-001`), a daily sequence computed
  with `SaleRepository.max_receipt_sequence`; the database `UNIQUE` constraint
  on `sales.receipt_no` is the final guard and a collision rolls the sale back.
  The prefix, date layout and digit count are all localized in
  `app/domain/services/sale_service.py` (`RECEIPT_PREFIX`,
  `RECEIPT_SEQUENCE_DIGITS`). Confirm before production.
- **Receipt branding / header / footer** — the receipt header (shop name,
  address, phone) and footer/tagline text come from the approved wireframe and
  are configurable defaults in `ReceiptBuilder` (`SHOP_NAME`, `SHOP_ADDRESS`,
  `SHOP_PHONE`, `RECEIPT_FOOTER`, `RECEIPT_TAGLINE`). Confirm the final text and
  layout before mass-printing.
- **Receipt barcode content** — the receipt barcode encodes the receipt number
  exactly (rendered as Code128). This matches the wireframe candidate; confirm
  whether any other identifier should be encoded.
- **Discount applied at the till** — Admin-only discount is confirmed
  (approved matrix: "Discount" is Admin-only). Phase 05 implemented `PERCENT`
  and `FIXED` with no ceiling beyond "cannot make the total negative". Any
  required maximums/per-user limits must be confirmed.
- **Payment reference field** — the technical architecture asks which reference
  number is recorded for POS/Transfer transactions. Phase 05 added an optional
  free-text "Reference" field stored on `payments.reference`. Confirm whether a
  reference should be mandatory for either method.
- **Cashier reprint rights** — UC-06 "Reprint Receipt" has no dedicated
  capability in the matrix, so Phase 05 gates reprint to Admin via the closest
  capability, `CAP_VIEW_REPORTS`. Confirm whether the Cashier may reprint.
- **Cashier creates walk-in customers** — the approved matrix does not list
  customer-record management for the Cashier, but a sale requires a customer.
  Phase 05 added `CustomerService.create_for_sale` (name required, phone
  optional) gated by the Cashier's own `CAP_MAKE_SALE`, while full customer
  management stays Admin-only. Confirm the cashier may register minimal
  customers at the till.
- **Low-stock note after a sale** — Phase 05 shows a low-stock note after a sale
  but scoped to the sale's own items only (the Cashier never sees the Admin-only
  full low-stock list). Confirm whether the cashier should see a shop-wide
  low-stock alert instead.
- **ESC/POS naira rendering** — PC437 (thermal printers) has no naira glyph, so
  the ESC/POS renderer prints `N` instead of `₦` on the paper receipt. Applies
  only to the printed copy; on-screen text keeps `₦`. A hardware/print decision
  (Phase 11) may override this.

## Added during Phase 04

- **Inventory management permission** — the permission matrix lists "Stock
  Adjustment" as Admin-only and UC-07 "Stock In" with Actor Admin, but it does
  not name a separate capability for *viewing* inventory or movement history.
  Phase 04 gates stock-in (`CAP_STOCK_IN`), adjustment (`CAP_STOCK_ADJUSTMENT`)
  and the movement-history/low-stock listings (`CAP_STOCK_ADJUSTMENT`) to
  Admin-only, and the Inventory/Dashboard screens are Admin-only in the
  sidebar. Confirm whether the Cashier should ever see the movement history.
- **Stock-in without a purchase record** — the Phase 04 stock-in adds quantity
  and logs a `STOCK_IN` movement without creating a purchase (purchases and
  suppliers are Phase 07). When Phase 07 records purchases, the purchase-linked
  stock increase is expected to flow through the same inventory service.
  Confirm if stock-in should be restricted to purchase-linked movements later.
- **Low-stock popup scope** — Phase 04 raises the popup after Admin stock
  operations. Phase 05 sales will trigger the same popup when a sale leaves a
  product at `quantity <= 3`; the popup already lives in a reusable widget for
  that purpose.

## Added during Phase 03

- **Barcode symbology/format** — products have no existing barcodes, so the
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
