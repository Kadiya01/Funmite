# Funmite POS — User Acceptance Testing (UAT) Checklist

**Client:** Funmite Clothing & Beyond
**Version:** 1.1.0
**Tester:** _______________
**Date:** _______________

## Instructions

Check each item after testing. Record any issues in the Notes column.
Mark: PASS / FAIL / N/A

---

## 1. Login & Access Control

| # | Test | Result | Notes |
|---|------|--------|-------|
| 1.1 | Admin login with correct credentials | | |
| 1.2 | Cashier login with correct credentials | | |
| 1.3 | Wrong password shows error message | | |
| 1.4 | Unknown username shows error message | | |
| 1.5 | Cashier cannot see Admin screens (Products, Inventory, etc.) | | |
| 1.6 | Cashier only sees POS screen | | |
| 1.7 | Admin can access all screens | | |
| 1.8 | Logout returns to login dialog | | |

## 2. Product Management (Admin)

| # | Test | Result | Notes |
|---|------|--------|-------|
| 2.1 | Add a new product with all fields | | |
| 2.2 | Product code is auto-generated (PRD-XXXXXX) | | |
| 2.3 | Barcode is auto-generated (13 digits) | | |
| 2.4 | Edit product name and prices | | |
| 2.5 | Deactivate a product | | |
| 2.6 | Reactivate a product | | |
| 2.7 | Search products by name | | |
| 2.8 | Search products by barcode | | |
| 2.9 | Filter products by category | | |
| 2.10 | Add a new category | | |
| 2.11 | Print barcode label for a product | | |

## 3. Customer Management (Admin)

| # | Test | Result | Notes |
|---|------|--------|-------|
| 3.1 | Add a new customer | | |
| 3.2 | Customer code is auto-generated (CUS-XXXXX) | | |
| 3.3 | Edit customer details | | |
| 3.4 | Search customers by name | | |
| 3.5 | Search customers by phone | | |

## 4. POS Sales (Cashier)

| # | Test | Result | Notes |
|---|------|--------|-------|
| 4.1 | Scan a barcode — product appears in cart | | |
| 4.2 | Search product by name — select to add to cart | | |
| 4.3 | Change quantity in cart (spinner) | | |
| 4.4 | Remove item from cart | | |
| 4.5 | Select or create a walk-in customer | | |
| 4.6 | Complete a sale with Bank POS payment | | |
| 4.7 | Complete a sale with Bank Transfer payment | | |
| 4.8 | Receipt number follows `FUN-YYYYMMDD-NNN` format | | |
| 4.9 | Subtotal, total, and amount paid are correct | | |
| 4.10 | Stock decreases after sale | | |
| 4.11 | Insufficient stock shows error and prevents sale | | |
| 4.12 | Low-stock warning shows after sale if product is low | | |
| 4.13 | Admin can apply discount (PERCENT or FIXED) | | |
| 4.14 | Cashier cannot apply discount | | |
| 4.15 | Duplicate product in cart is prevented | | |
| 4.16 | Sale completes even if printer is unavailable | | |

## 5. Receipt Printing

| # | Test | Result | Notes |
|---|------|--------|-------|
| 5.1 | Receipt prints with shop name | | |
| 5.2 | Receipt shows correct receipt number | | |
| 5.3 | Receipt shows product names, quantities, prices | | |
| 5.4 | Receipt shows subtotal, discount, total | | |
| 5.5 | Receipt shows payment method | | |
| 5.6 | Receipt barcode scans correctly (receipt number) | | |
| 5.7 | Admin can reprint a receipt | | |

## 6. Inventory Management (Admin)

| # | Test | Result | Notes |
|---|------|--------|-------|
| 6.1 | View current stock levels | | |
| 6.2 | Stock-in (add quantity to a product) | | |
| 6.3 | Stock adjustment (with mandatory reason) | | |
| 6.4 | View inventory movement history | | |
| 6.5 | Low-stock products are highlighted | | |
| 6.6 | Negative stock is prevented | | |

## 7. Purchases & Suppliers (Admin)

| # | Test | Result | Notes |
|---|------|--------|-------|
| 7.1 | Add a new supplier | | |
| 7.2 | Edit supplier details | | |
| 7.3 | Create a purchase with a supplier | | |
| 7.4 | Add multiple products to purchase | | |
| 7.5 | Stock increases after purchase | | |
| 7.6 | Product cost_price updates to latest purchase cost | | |
| 7.7 | Purchase balance = total_cost - amount_paid | | |

## 8. Expenses (Admin)

| # | Test | Result | Notes |
|---|------|--------|-------|
| 8.1 | Record a new expense | | |
| 8.2 | Expense has category, amount, description | | |
| 8.3 | Edit an expense | | |
| 8.4 | Filter expenses by category | | |

## 9. Exchanges (Admin)

| # | Test | Result | Notes |
|---|------|--------|-------|
| 9.1 | Find a sale by receipt number | | |
| 9.2 | Select items to return | | |
| 9.3 | Select replacement products | | |
| 9.4 | Difference amount is calculated correctly | | |
| 9.5 | Exchange completes (stock changes applied) | | |
| 9.6 | Exchange within 2-day window works | | |
| 9.7 | Exchange after 2 days is blocked | | |

## 10. Reports (Admin)

| # | Test | Result | Notes |
|---|------|--------|-------|
| 10.1 | Sales report shows correct data | | |
| 10.2 | Profit report (Total Sales, COGS, Gross Profit, Expenses, Net Profit) | | |
| 10.3 | Inventory report shows current stock and values | | |
| 10.4 | Payments report shows POS and Transfer totals | | |
| 10.5 | Purchases report shows supplier purchases | | |
| 10.6 | Expenses report shows recorded expenses | | |
| 10.7 | Product sales report shows per-product breakdown | | |
| 10.8 | Cashier sales report shows per-cashier totals | | |
| 10.9 | End of day report shows today's summary | | |
| 10.10 | Date range filters work correctly | | |

## 11. Dashboard (Admin)

| # | Test | Result | Notes |
|---|------|--------|-------|
| 11.1 | Today's sales total is correct | | |
| 11.2 | Today's gross profit is correct | | |
| 11.3 | Today's net profit is correct | | |
| 11.4 | Transaction count is correct | | |
| 11.5 | POS Total and Transfer Total are correct | | |
| 11.6 | Low-stock indicator shows products below threshold | | |

## 12. Backup & Restore (Admin)

| # | Test | Result | Notes |
|---|------|--------|-------|
| 12.1 | Create a backup from Settings | | |
| 12.2 | Backup file appears in list with correct size | | |
| 12.3 | Create multiple backups — all have unique filenames | | |
| 12.4 | Backup is a valid SQLite database | | |

## 13. Cloud Synchronization (Admin)

| # | Test | Result | Notes |
|---|------|--------|-------|
| 13.1 | Settings shows Cloud Sync section | | |
| 13.2 | Device registration form is visible | | |
| 13.3 | Sync Now button triggers sync | | |
| 13.4 | Sync status indicator shows in status bar | | |
| 13.5 | Data created on PC-A syncs to PC-B | | |
| 13.6 | Data created on PC-B syncs to PC-A | | |

## 14. Offline Operation

| # | Test | Result | Notes |
|---|------|--------|-------|
| 14.1 | App works normally with internet disconnected | | |
| 14.2 | Sales complete without internet | | |
| 14.3 | Reports work without internet | | |
| 14.4 | Backup works without internet | | |
| 14.5 | Inventory operations work without internet | | |

---

## Summary

| Category | Total | Pass | Fail | N/A |
|----------|-------|------|------|-----|
| 1. Login & Access | 8 | | | |
| 2. Products | 11 | | | |
| 3. Customers | 5 | | | |
| 4. POS Sales | 16 | | | |
| 5. Receipt Printing | 7 | | | |
| 6. Inventory | 6 | | | |
| 7. Purchases | 7 | | | |
| 8. Expenses | 4 | | | |
| 9. Exchanges | 7 | | | |
| 10. Reports | 10 | | | |
| 11. Dashboard | 6 | | | |
| 12. Backup | 4 | | | |
| 13. Sync | 6 | | | |
| 14. Offline | 5 | | | |
| **TOTAL** | **92** | | | |

## Sign-Off

- [ ] All critical tests passed
- [ ] All high-priority tests passed
- [ ] Known issues documented and accepted
- [ ] Ready for production deployment

**Client Representative:** _______________
**Signature:** _______________
**Date:** _______________
