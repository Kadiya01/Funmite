# UI/UX POLISH IMPLEMENTATION PLAN

## Overview
Polish and professionalize the Funmite POS UI/UX for client UAT. No functional changes.

## Audit Findings

### Critical Issues Found
1. _darken() duplicated 4 times -- theme.py, main.py, pos_page.py, login_dialog.py
2. No page titles on Customers, Suppliers, Expenses, Purchases
3. Hardcoded font-size: 20px in reports_page.py, my_sales_page.py
4. Hardcoded color literals in settings_page.py (#F59E0B, #10B981, #3B82F6)
5. No empty states on any table
6. Products page overrides entire global table stylesheet
7. Dashboard shadows violate no-excessive-shadows rule
8. Status bar format needs improvement
9. Reports summary shows tab name instead of actual totals

### Implementation Steps (18 steps)
See full plan in conversation context.
