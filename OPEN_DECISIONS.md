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
- **Backup retention / destination** — how many backups to keep and where.
- **Selected cloud/hybrid package** — whether cloud/LAN sync is in scope.
- **LAN synchronization method** — exact protocol/mechanism if LAN sync is used.
- **Final report list** — the exact set of reports to deliver.

## From the technical architecture (section 18)

- Exact receipt number prefix/format (see above).
- Exact mechanism for settling exchange price differences under the no-cash
  rule (see above).
- Final product data volume and data-entry/import format.
- Whether the virtual Lagos branch is only a future concept or must appear in
  V1 reports.
- Exact cloud remote UI scope within the V1 agreement.
- Exact backup frequency and retention count.
- Which payment reference number is recorded for POS/Transfer transactions, if
  any.
- Whether product images are mandatory or optional.

## Added during development

(No new entries yet.)
