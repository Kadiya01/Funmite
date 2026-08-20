# Funmite POS — Client UAT Checklist

**Project:** Funmite Clothing & Beyond
**Version:** 1.2.0
**Date:** _______________
**Client Representative:** _______________
**Developer:** _______________

---

## Instructions

1. Perform each test scenario in order.
2. Record the actual result observed.
3. Mark PASS or FAIL.
4. Add comments if needed.
5. Initial and date each section after completion.
6. All FAIL items must be resolved before production deployment.

---

## Section A: Login & Access Control

| ID | Scenario | Expected Result | Actual Result | PASS/FAIL | Client Comment | Developer Comment |
|----|----------|-----------------|---------------|-----------|----------------|-------------------|
| A1 | Admin login with correct credentials | Dashboard loads | | | | |
| A2 | Cashier login with correct credentials | POS screen loads | | | | |
| A3 | Login with wrong password | Error: "Invalid username or password" | | | | |
| A4 | Login with unknown username | Error: "Invalid username or password" | | | | |
| A5 | Cashier tries to access Products screen | Screen not visible (Cashier only sees POS) | | | | |
| A6 | Cashier tries to access Inventory | Screen not visible | | | | |
| A7 | Cashier tries to access Reports | Screen not visible | | | | |
| A8 | Cashier tries to access Settings | Screen not visible | | | | |
| A9 | Logout returns to login dialog | Login dialog appears, app does not close | | | | |

**Section A Sign-off:** _______________ Date: _______________

---

## Section B: Product Management (Admin)

| ID | Scenario | Expected Result | Actual Result | PASS/FAIL | Client Comment | Developer Comment |
|----|----------|-----------------|---------------|-----------|----------------|-------------------|
| B1 | Add a new product with all fields | Product saved successfully | | | | |
| B2 | Product code auto-generated (PRD-XXXXXX) | Code appears in product list | | | | |
| B3 | Barcode auto-generated (13 digits) | Barcode appears on product | | | | |
| B4 | Edit product name | Name updated | | | | |
| B5 | Edit product prices | Prices updated | | | | |
| B6 | Deactivate a product | Product marked inactive | | | | |
| B7 | Reactivate a product | Product active again | | | | |
| B8 | Search products by name | Results filtered correctly | | | | |
| B9 | Search products by barcode | Product found | | | | |
| B10 | Filter products by category | Correct products shown | | | | |
| B11 | Add a new category | Category saved | | | | |
| B12 | Print barcode label | Label prints with product name and barcode | | | | |

**Section B Sign-off:** _______________ Date: _______________

---

## Section C: Customer Management (Admin)

| ID | Scenario | Expected Result | Actual Result | PASS/FAIL | Client Comment | Developer Comment |
|----|----------|-----------------|---------------|-----------|----------------|-------------------|
| C1 | Add a new customer | Customer saved | | | | |
| C2 | Customer code auto-generated (CUS-XXXXX) | Code appears | | | | |
| C3 | Edit customer details | Details updated | | | | |
| C4 | Search customers by name | Results filtered | | | | |
| C5 | Search customers by phone | Results filtered | | | | |

**Section C Sign-off:** _______________ Date: _______________

---

## Section D: POS Sales (Cashier)

| ID | Scenario | Expected Result | Actual Result | PASS/FAIL | Client Comment | Developer Comment |
|----|----------|-----------------|---------------|-----------|----------------|-------------------|
| D1 | Scan a barcode — product appears in cart | Product added to cart with correct details | | | | |
| D2 | Search product by name — select to add | Product added to cart | | | | |
| D3 | Change quantity in cart (spinner) | Quantity updated, subtotal recalculated | | | | |
| D4 | Remove item from cart | Item removed, totals updated | | | | |
| D5 | Select an existing customer | Customer selected | | | | |
| D6 | Create a walk-in customer | Customer created and selected | | | | |
| D7 | Complete a sale with Bank POS payment | Sale completes, receipt prints | | | | |
| D8 | Complete a sale with Bank Transfer payment | Sale completes, receipt prints | | | | |
| D9 | Receipt number follows FUN-YYYYMMDD-NNN | Correct format on receipt | | | | |
| D10 | Subtotal, total, and amount paid are correct | Math is correct | | | | |
| D11 | Stock decreases after sale | Product quantity reduced | | | | |
| D12 | Insufficient stock shows error | Error message, sale blocked | | | | |
| D13 | Low-stock warning shows after sale | Warning if product ≤ 3 | | | | |
| D14 | Admin can apply discount (PERCENT) | Discount applied, total reduced | | | | |
| D15 | Admin can apply discount (FIXED) | Discount applied, total reduced | | | | |
| D16 | Cashier cannot apply discount | Discount controls hidden | | | | |
| D17 | Duplicate product in cart is prevented | Error or quantity increment | | | | |
| D18 | Sale completes even if printer unavailable | Sale saved, no crash | | | | |

**Section D Sign-off:** _______________ Date: _______________

---

## Section E: Receipt Printing

| ID | Scenario | Expected Result | Actual Result | PASS/FAIL | Client Comment | Developer Comment |
|----|----------|-----------------|---------------|-----------|----------------|-------------------|
| E1 | Receipt prints with shop name | "Funmite Clothing & Beyond" on receipt | | | | |
| E2 | Receipt shows correct receipt number | FUN-YYYYMMDD-NNN format | | | | |
| E3 | Receipt shows product names | Product names visible | | | | |
| E4 | Receipt shows quantities and prices | Correct values | | | | |
| E5 | Receipt shows subtotal, discount, total | All amounts correct | | | | |
| E6 | Receipt shows payment method | POS or TRANSFER shown | | | | |
| E7 | Receipt barcode prints | Barcode visible at bottom | | | | |
| E8 | Receipt barcode is scannable | Scanner reads barcode correctly | | | | |
| E9 | Naira formatting is acceptable | N sign or equivalent visible | | | | |
| E10 | Receipt is not clipped | Full receipt visible | | | | |
| E11 | Paper feeds correctly | No jams, clean cut | | | | |
| E12 | Multiple consecutive receipts print | All print correctly | | | | |
| E13 | Admin can reprint a receipt | Reprint works | | | | |

**Section E Sign-off:** _______________ Date: _______________

---

## Section F: Inventory Management (Admin)

| ID | Scenario | Expected Result | Actual Result | PASS/FAIL | Client Comment | Developer Comment |
|----|----------|-----------------|---------------|-----------|----------------|-------------------|
| F1 | View current stock levels | All products shown with quantities | | | | |
| F2 | Stock-in (add quantity) | Quantity increased | | | | |
| F3 | Stock adjustment with reason | Quantity changed, reason recorded | | | | |
| F4 | View inventory movement history | Movement log visible | | | | |
| F5 | Low-stock products highlighted | Products ≤ 3 highlighted | | | | |
| F6 | Negative stock is prevented | Error message | | | | |

**Section F Sign-off:** _______________ Date: _______________

---

## Section G: Purchases & Suppliers (Admin)

| ID | Scenario | Expected Result | Actual Result | PASS/FAIL | Client Comment | Developer Comment |
|----|----------|-----------------|---------------|-----------|----------------|-------------------|
| G1 | Add a new supplier | Supplier saved | | | | |
| G2 | Edit supplier details | Details updated | | | | |
| G3 | Create a purchase with a supplier | Purchase recorded | | | | |
| G4 | Add multiple products to purchase | All products added | | | | |
| G5 | Stock increases after purchase | Quantities increased | | | | |
| G6 | Product cost_price updates | Cost reflects latest purchase | | | | |
| G7 | Purchase balance = total_cost - amount_paid | Balance correct | | | | |

**Section G Sign-off:** _______________ Date: _______________

---

## Section H: Expenses (Admin)

| ID | Scenario | Expected Result | Actual Result | PASS/FAIL | Client Comment | Developer Comment |
|----|----------|-----------------|---------------|-----------|----------------|-------------------|
| H1 | Record a new expense | Expense saved | | | | |
| H2 | Expense has category, amount, description | All fields saved | | | | |
| H3 | Edit an expense | Details updated | | | | |
| H4 | Filter expenses by category | Correct expenses shown | | | | |

**Section H Sign-off:** _______________ Date: _______________

---

## Section I: Exchanges (Admin)

| ID | Scenario | Expected Result | Actual Result | PASS/FAIL | Client Comment | Developer Comment |
|----|----------|-----------------|---------------|-----------|----------------|-------------------|
| I1 | Find a sale by receipt number | Sale found | | | | |
| I2 | Select items to return | Items selected | | | | |
| I3 | Select replacement products | Products added | | | | |
| I4 | Difference amount is calculated correctly | Amount correct | | | | |
| I5 | Exchange completes (stock changes applied) | Returned items back in stock, replacements deducted | | | | |
| I6 | Exchange within 2-day window works | Exchange allowed | | | | |
| I7 | Exchange after 2 days is blocked | Error message | | | | |

**Section I Sign-off:** _______________ Date: _______________

---

## Section J: Reports (Admin)

| ID | Scenario | Expected Result | Actual Result | PASS/FAIL | Client Comment | Developer Comment |
|----|----------|-----------------|---------------|-----------|----------------|-------------------|
| J1 | Sales report shows correct data | Sales listed correctly | | | | |
| J2 | Profit report shows breakdown | Total Sales, COGS, Gross Profit, Expenses, Net Profit | | | | |
| J3 | Inventory report shows stock and values | Quantities and values correct | | | | |
| J4 | Payments report shows POS and Transfer totals | Totals correct | | | | |
| J5 | Purchases report shows supplier purchases | Purchases listed | | | | |
| J6 | Expenses report shows recorded expenses | Expenses listed | | | | |
| J7 | Product sales report shows per-product breakdown | Per-product data correct | | | | |
| J8 | Cashier sales report shows per-cashier totals | Totals correct | | | | |
| J9 | End of day report shows today's summary | Summary correct | | | | |
| J10 | Date range filters work correctly | Correct date filtering | | | | |

**Section J Sign-off:** _______________ Date: _______________

---

## Section K: Dashboard (Admin)

| ID | Scenario | Expected Result | Actual Result | PASS/FAIL | Client Comment | Developer Comment |
|----|----------|-----------------|---------------|-----------|----------------|-------------------|
| K1 | Today's sales total is correct | Matches sales report | | | | |
| K2 | Today's gross profit is correct | Matches profit report | | | | |
| K3 | Today's net profit is correct | Matches profit report | | | | |
| K4 | Transaction count is correct | Matches sales count | | | | |
| K5 | POS Total and Transfer Total are correct | Matches payments report | | | | |
| K6 | Low-stock indicator shows products below threshold | Products ≤ 3 shown | | | | |

**Section K Sign-off:** _______________ Date: _______________

---

## Section L: Backup & Restore (Admin)

| ID | Scenario | Expected Result | Actual Result | PASS/FAIL | Client Comment | Developer Comment |
|----|----------|-----------------|---------------|-----------|----------------|-------------------|
| L1 | Create a backup from Settings | Backup file created | | | | |
| L2 | Backup file appears in list with correct size | File listed correctly | | | | |
| L3 | Create multiple backups — all have unique filenames | No overwrites | | | | |
| L4 | Backup is a valid SQLite database | Integrity check passes | | | | |
| L5 | Restore a backup | Database restored, pre-restore backup created | | | | |
| L6 | Verify data after restore | Sales, products, customers match backup state | | | | |
| L7 | Application works after restore | No errors, login works | | | | |

**Section L Sign-off:** _______________ Date: _______________

---

## Section M: Cloud Synchronization (Admin)

| ID | Scenario | Expected Result | Actual Result | PASS/FAIL | Client Comment | Developer Comment |
|----|----------|-----------------|---------------|-----------|----------------|-------------------|
| M1 | Settings shows Cloud Sync section | Section visible | | | | |
| M2 | Device registration form is visible | Form displayed | | | | |
| M3 | Sync Now button triggers sync | Sync attempted | | | | |
| M4 | Sync status indicator shows in status bar | Indicator visible | | | | |
| M5 | Data created on PC-A syncs to PC-B | Data appears on PC-B | | | | |
| M6 | Data created on PC-B syncs to PC-A | Data appears on PC-A | | | | |

**Section M Sign-off:** _______________ Date: _______________

---

## Section N: Offline Operation

| ID | Scenario | Expected Result | Actual Result | PASS/FAIL | Client Comment | Developer Comment |
|----|----------|-----------------|---------------|-----------|----------------|-------------------|
| N1 | App works normally with internet disconnected | No errors, login works | | | | |
| N2 | Sales complete without internet | Sale saved locally | | | | |
| N3 | Reports work without internet | Reports show local data | | | | |
| N4 | Backup works without internet | Backup created | | | | |
| N5 | Inventory operations work without internet | Stock changes saved | | | | |
| N6 | Reconnect internet — pending sync occurs | Status shows synced | | | | |

**Section N Sign-off:** _______________ Date: _______________

---

## Summary

| Section | Total Tests | Pass | Fail | N/A |
|---------|-------------|------|------|-----|
| A. Login & Access | 9 | | | |
| B. Products | 12 | | | |
| C. Customers | 5 | | | |
| D. POS Sales | 18 | | | |
| E. Receipt Printing | 13 | | | |
| F. Inventory | 6 | | | |
| G. Purchases | 7 | | | |
| H. Expenses | 4 | | | |
| I. Exchanges | 7 | | | |
| J. Reports | 10 | | | |
| K. Dashboard | 6 | | | |
| L. Backup & Restore | 7 | | | |
| M. Cloud Sync | 6 | | | |
| N. Offline Operation | 6 | | | |
| **TOTAL** | **116** | | | |

---

## Final Sign-Off

- [ ] All critical tests passed
- [ ] All high-priority tests passed
- [ ] Known issues documented and accepted
- [ ] Ready for production deployment

**Client Representative:** _______________
**Signature:** _______________
**Date:** _______________

**Developer:** _______________
**Signature:** _______________
**Date:** _______________
