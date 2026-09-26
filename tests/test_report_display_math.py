"""Phase 4 regression: user-facing totals/chart math is Decimal-exact.

The display layers aggregate monetary values with Decimal and only convert to
``float`` at the chart boundary. These tests pin that behaviour so float
accumulation cannot silently regress totals like 0.10 + 0.20 != 0.30.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from app.ui.reports.my_sales_page import _sales_total
from app.ui.reports.reports_page import _daily_sales_series


@dataclass
class ChartRow:
    sale_date: date
    total: Decimal


@dataclass
class SalesRow:
    total: Decimal


def test_daily_sales_series_accumulates_exact_decimals():
    rows = [
        ChartRow(date(2026, 9, 1), Decimal("100.10")),
        ChartRow(date(2026, 9, 1), Decimal("0.90")),
        ChartRow(date(2026, 9, 2), Decimal("5.25")),
    ]
    series = _daily_sales_series(rows)
    assert len(series) == 2
    assert series[0] == ("Sep 01", 101.0)
    assert series[1] == ("Sep 02", 5.25)


def test_daily_sales_series_preserves_first_seen_order():
    rows = [
        ChartRow(date(2026, 9, 3), Decimal("1.00")),
        ChartRow(date(2026, 9, 1), Decimal("2.00")),
    ]
    series = _daily_sales_series(rows)
    assert [day for day, _ in series] == ["Sep 03", "Sep 01"]


def test_sales_total_is_decimal_exact():
    rows = [SalesRow(Decimal("0.1")), SalesRow(Decimal("0.2"))]
    assert _sales_total(rows) == Decimal("0.3")


def test_sales_total_of_empty_report_is_zero():
    assert _sales_total([]) == Decimal("0")