"""Low-stock popup tests (Phase 04)."""

from __future__ import annotations

from PySide6.QtWidgets import QMessageBox

from app.data.models import Product
from app.ui.widgets.low_stock_popup import (
    POPUP_TITLE,
    low_stock_summary,
    show_low_stock_alert,
)


def _product(name: str, quantity: int) -> Product:
    product = Product(
        id=1,
        product_code="PRD-000001",
        name=name,
        quantity=quantity,
        minimum_stock=3,
        barcode="1000000000001",
        is_active=True,
    )
    return product


def test_low_stock_summary_lists_products():
    products = [_product("Gown", 2), _product("Top", 3)]
    text = low_stock_summary(products)
    assert "Gown" in text and "2 left" in text
    assert "Top" in text and "3 left" in text


def test_low_stock_summary_empty():
    assert low_stock_summary([]) == ""


def test_show_low_stock_alert_returns_false_when_empty(qtbot, monkeypatch):
    def unexpected_exec(*_args):
        raise AssertionError("dialog should not open for an empty list")

    monkeypatch.setattr(QMessageBox, "exec", unexpected_exec)
    assert show_low_stock_alert(None, []) is False


def test_show_low_stock_alert_view_stock_action(qtbot, monkeypatch):
    products = [_product("Gown", 2)]

    def click_view_stock(message: QMessageBox):
        assert message.windowTitle() == POPUP_TITLE
        buttons = {button.text(): button for button in message.buttons()}
        buttons["View Stock"].click()
        return message.result()

    monkeypatch.setattr(QMessageBox, "exec", click_view_stock)
    assert show_low_stock_alert(None, products) is True


def test_show_low_stock_alert_dismiss_action(qtbot, monkeypatch):
    products = [_product("Gown", 2)]

    def click_dismiss(message: QMessageBox):
        buttons = {button.text(): button for button in message.buttons()}
        buttons["Dismiss"].click()
        return message.result()

    monkeypatch.setattr(QMessageBox, "exec", click_dismiss)
    assert show_low_stock_alert(None, products) is False
