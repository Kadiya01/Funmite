"""Application shell smoke tests (Qt)."""

from __future__ import annotations

from PySide6.QtWidgets import QApplication, QPushButton

from app import __version__
from app.data.models import ROLE_ADMIN, ROLE_CASHIER
from app.domain.session import CurrentUser
from app.main import APP_TITLE, MainWindow
from app.ui.customers import CustomersPage
from app.ui.dashboard import DashboardPage
from app.ui.expenses import ExpensesPage
from app.ui.inventory import InventoryPage
from app.ui.pos import PosPage
from app.ui.products import ProductsPage
from app.ui.purchases import PurchasesPage
from app.ui.reports.reports_page import ReportsPage
from app.ui.settings.settings_page import SettingsPage
from app.ui.suppliers import SuppliersPage


def test_main_window_creates(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    assert window.windowTitle() == APP_TITLE
    assert window.isVisible() is False
    assert f"version {__version__}" in window.statusBar().currentMessage()


def test_main_window_shows_current_user_and_logout(qtbot):
    user = CurrentUser(
        user_id=1,
        username="jamilu",
        full_name="Jamilu",
        role=ROLE_ADMIN,
    )
    window = MainWindow(current_user=user)
    qtbot.addWidget(window)

    status = window.statusBar().currentMessage()
    assert "Admin: Jamilu" in status
    assert f"version {__version__}" in status

    buttons = [b for b in window.findChildren(QPushButton) if b.text() == "Log out"]
    assert len(buttons) == 1

    with qtbot.waitSignal(window.logout_requested, timeout=1000):
        buttons[0].click()


def test_main_window_without_user_has_no_logout(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    buttons = [b for b in window.findChildren(QPushButton) if b.text() == "Log out"]
    assert buttons == []


def test_application_singleton(qtbot):
    assert QApplication.instance() is not None


def _admin_user() -> CurrentUser:
    return CurrentUser(
        user_id=1,
        username="jamilu",
        full_name="Jamilu",
        role=ROLE_ADMIN,
    )


def _cashier_user() -> CurrentUser:
    return CurrentUser(
        user_id=2,
        username="kasuwa",
        full_name="Kasuwa",
        role=ROLE_CASHIER,
    )


def test_admin_window_shows_admin_navigation(qtbot, session_factory):
    window = MainWindow(current_user=_admin_user(), session_factory=session_factory)
    qtbot.addWidget(window)

    nav_items = [window.nav.item(i).text() for i in range(window.nav.count())]
    assert nav_items == [
        "Dashboard", "POS", "Products", "Inventory", "Customers",
        "Purchases", "Suppliers", "Expenses", "Reports", "Settings",
    ]
    assert window.stack.count() == 10
    assert isinstance(window.stack.widget(0), DashboardPage)
    assert isinstance(window.stack.widget(1), PosPage)
    assert isinstance(window.stack.widget(2), ProductsPage)
    assert isinstance(window.stack.widget(3), InventoryPage)
    assert isinstance(window.stack.widget(4), CustomersPage)
    assert isinstance(window.stack.widget(5), PurchasesPage)
    assert isinstance(window.stack.widget(6), SuppliersPage)
    assert isinstance(window.stack.widget(7), ExpensesPage)
    assert isinstance(window.stack.widget(8), ReportsPage)
    assert isinstance(window.stack.widget(9), SettingsPage)


def test_dashboard_view_stock_switches_to_inventory(qtbot, session_factory):
    window = MainWindow(current_user=_admin_user(), session_factory=session_factory)
    qtbot.addWidget(window)

    dashboard = window.stack.widget(0)
    assert isinstance(dashboard, DashboardPage)
    dashboard.view_stock_requested.emit()
    assert window.stack.currentIndex() == 3
    window.stack.setCurrentIndex(0)


def test_cashier_window_shows_only_pos(qtbot, session_factory):
    window = MainWindow(current_user=_cashier_user(), session_factory=session_factory)
    qtbot.addWidget(window)

    nav_items = [window.nav.item(i).text() for i in range(window.nav.count())]
    assert nav_items == ["POS"]
    assert window.stack.count() == 1
    assert isinstance(window.stack.widget(0), PosPage)


def test_app_controller_passes_session_factory_to_window(qtbot, session_factory, monkeypatch):
    from app.main import AppController

    app = QApplication.instance()
    controller = AppController(app, session_factory)
    monkeypatch.setattr(QApplication, "exec", lambda self: 0)

    controller._show(_admin_user())

    window = controller._window
    assert window is not None
    assert window.session_factory is session_factory
    assert window.stack.count() == 10
    window.close()
