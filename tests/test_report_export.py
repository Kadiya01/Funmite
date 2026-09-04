"""F5 — Reports Print/Export (CSV) tests.

Every report tab must provide a CSV export after viewing. These tests drive
the ReportsPage through the full Run cycle and verify the exported CSV files
contain the expected headers and raw (machine-readable) values.
"""

from __future__ import annotations

import csv
from decimal import Decimal

from app.data.models import PAYMENT_POS, ROLE_ADMIN
from app.domain.session import CurrentUser
from app.ui.reports.reports_page import ReportsPage
from tests.factories import (
    make_category,
    make_customer,
    make_product,
    make_sale,
    make_user,
)


def _current(user) -> CurrentUser:
    return CurrentUser(
        user_id=user.id,
        username=user.username,
        full_name=user.full_name,
        role=user.role,
    )


def _page(session_factory, user) -> ReportsPage:
    return ReportsPage(session_factory, _current(user))


def _read_csv(path):
    with open(path, newline="", encoding="utf-8-sig") as fh:
        return list(csv.reader(fh))


def _seed_sale(session) -> None:
    admin = make_user(session, role=ROLE_ADMIN)
    customer = make_customer(session, name="Amina Yusuf")
    product = make_product(
        session, make_category(session), name="Ladies Gown",
        selling_price=Decimal("35000"), quantity=10,
    )
    make_sale(
        session, customer, admin,
        items=[(product, 2)], payment_method=PAYMENT_POS,
    )
    session.commit()


def test_export_button_exists(qtbot, session_factory, session):
    page = _page(session_factory, make_user(session, role=ROLE_ADMIN))
    qtbot.addWidget(page)
    assert page.export_button.isEnabled()
    assert page.export_button.text() == "Export CSV"


def test_run_populates_export_data_for_all_tabs(qtbot, session_factory, session):
    _seed_sale(session)
    page = _page(session_factory, make_user(session, role=ROLE_ADMIN))
    qtbot.addWidget(page)
    page._run_all_tabs()

    assert len(page._report_data) == page.tabs.count() == 9
    for index in range(page.tabs.count()):
        headers, rows = page._report_data[index]
        assert headers
        assert isinstance(rows, list)


def test_sales_export_contains_raw_money_values(qtbot, session_factory, session, tmp_path):
    _seed_sale(session)
    page = _page(session_factory, make_user(session, role=ROLE_ADMIN))
    qtbot.addWidget(page)
    page._run_all_tabs()
    page.tabs.setCurrentIndex(page.sales_tab)

    out = tmp_path / "sales.csv"
    page._export_current(str(out))

    rows = _read_csv(out)
    assert rows[0] == [
        "Receipt", "Date", "Customer", "Cashier",
        "Subtotal", "Discount", "Total", "Method",
    ]
    assert len(rows) == 2
    _, date_cell, customer, cashier, subtotal, discount, total, method = rows[1]
    assert customer == "Amina Yusuf"
    assert method == "POS"
    assert subtotal == "70000.00"
    assert discount == "0.00"
    assert total == "70000.00"


def test_profit_export_lists_all_metrics(qtbot, session_factory, session, tmp_path):
    _seed_sale(session)
    page = _page(session_factory, make_user(session, role=ROLE_ADMIN))
    qtbot.addWidget(page)
    page._run_all_tabs()
    page.tabs.setCurrentIndex(page.profit_tab)

    out = tmp_path / "profit.csv"
    page._export_current(str(out))

    rows = _read_csv(out)
    assert rows[0] == ["Metric", "Amount"]
    metrics = [r[0] for r in rows[1:]]
    assert metrics == [
        "Total Sales", "COGS", "Gross Profit", "Expenses", "Net Profit",
    ]


def test_inventory_export_contains_product_rows(qtbot, session_factory, session, tmp_path):
    _seed_sale(session)
    page = _page(session_factory, make_user(session, role=ROLE_ADMIN))
    qtbot.addWidget(page)
    page._run_all_tabs()
    page.tabs.setCurrentIndex(page.inventory_tab)

    out = tmp_path / "inventory.csv"
    page._export_current(str(out))

    rows = _read_csv(out)
    assert rows[0] == [
        "Product", "Category", "Qty", "Cost", "Price", "Value", "Min", "Status",
    ]
    assert any(r[0] == "Ladies Gown" and r[2] == "8" for r in rows[1:])  # 10 - 2 sold


def test_empty_report_exports_headers_only(qtbot, session_factory, session, tmp_path):
    page = _page(session_factory, make_user(session, role=ROLE_ADMIN))
    qtbot.addWidget(page)
    page._run_all_tabs()
    page.tabs.setCurrentIndex(page.sales_tab)

    out = tmp_path / "empty.csv"
    page._export_current(str(out))

    rows = _read_csv(out)
    assert len(rows) == 1
    assert rows[0][0] == "Receipt"


def test_export_before_run_prompts_without_writing(qtbot, session_factory, session, tmp_path, monkeypatch):
    page = _page(session_factory, make_user(session, role=ROLE_ADMIN))
    qtbot.addWidget(page)

    messages = []
    monkeypatch.setattr(
        "app.ui.reports.reports_page.QMessageBox.information",
        lambda *a, **k: messages.append(a),
    )

    out = tmp_path / "never.csv"
    page._export_current(str(out))

    assert not out.exists()
    assert messages