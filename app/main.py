"""Application entry point.

Phase 00 provided the minimal shell; Phase 02 adds the login flow, the
current-user display and logout; Phase 03 adds the Admin-only Products and
Customers screens; Phase 04 adds the Dashboard (low-stock indicator) and
Inventory screens; Phase 05 adds the Cashier/Admin POS screen with the atomic
offline sale. The UI only talks to services; it never touches the database
directly.
"""

from __future__ import annotations

import sys

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QPushButton,
    QStackedWidget,
    QStatusBar,
    QVBoxLayout,
    QWidget,
)

from app import __version__
from app.config import load_settings
from app.data.db import create_session_factory, initialize_database, session_scope
from app.data.models import ROLE_ADMIN
from app.data.seed import ensure_seed_users
from app.domain.services.audit_service import ACTION_LOGOUT, AuditService
from app.domain.services.auth_service import AuthService
from app.domain.session import CurrentUser
from app.logging_config import setup_logging
from app.printing.printer import NullPrinter
from app.ui.customers import CustomersPage
from app.ui.dashboard import DashboardPage
from app.ui.expenses import ExpensesPage
from app.ui.inventory import InventoryPage
from app.ui.login import LoginDialog
from app.ui.pos import PosPage
from app.ui.products import ProductsPage
from app.ui.purchases import PurchasesPage
from app.ui.reports.reports_page import ReportsPage
from app.ui.settings.settings_page import SettingsPage
from app.ui.suppliers import SuppliersPage
from app.ui.theme import C, F, NAV_ICONS, S, generate_stylesheet

APP_TITLE = "Funmite POS"
NAV_WIDTH = 180


def _darken(hex_color: str, amount: int = 15) -> str:
    h = hex_color.lstrip("#")
    r, g, b = (int(h[i : i + 2], 16) for i in (0, 2, 4))
    return f"#{max(0, r - amount):02x}{max(0, g - amount):02x}{max(0, b - amount):02x}"


# Sidebar QSS
_SIDEBAR_QSS = f"""
QListWidget {{
    background-color: {C.SIDEBAR_BG};
    border: none;
    border-right: 1px solid {_darken(C.SIDEBAR_BG, 5)};
    outline: none;
    font-size: {F.SIZE_BASE};
    padding: 4px 0;
}}
QListWidget::item {{
    color: {C.SIDEBAR_FG};
    padding: 10px 16px 10px 20px;
    border: none;
    border-left: 3px solid transparent;
    min-height: 20px;
}}
QListWidget::item:selected {{
    background-color: {C.SIDEBAR_ACTIVE_BG};
    color: {C.SIDEBAR_ACTIVE_FG};
    border-left: 3px solid {C.SIDEBAR_ACCENT};
    font-weight: {F.WEIGHT_SEMIBOLD};
}}
QListWidget::item:hover:!selected {{
    background-color: {C.SIDEBAR_HOVER};
    color: {C.SIDEBAR_ACTIVE_FG};
}}
"""


class MainWindow(QMainWindow):
    """Application shell. Shows the signed-in user/role, a logout action and
    the screens the current role may use."""

    logout_requested = Signal()

    def __init__(
        self,
        current_user: CurrentUser | None = None,
        session_factory=None,
    ) -> None:
        super().__init__()
        self.current_user = current_user
        self.session_factory = session_factory
        self.setWindowTitle(APP_TITLE)
        self.setMinimumSize(960, 600)
        self.resize(1100, 700)

        if current_user is not None:
            self._build_navigation(current_user)
        else:
            central = QWidget(self)
            layout = QVBoxLayout(central)
            title = QLabel(APP_TITLE, central)
            title.setAlignment(Qt.AlignmentFlag.AlignCenter)
            title.setStyleSheet(
                f"font-size: {F.SIZE_3XL}; font-weight: {F.WEIGHT_BOLD}; "
                f"color: {C.PRIMARY}; padding: 40px;"
            )
            layout.addWidget(title)
            self.setCentralWidget(central)

        self._setup_status_bar()

    def _setup_status_bar(self) -> None:
        status_bar: QStatusBar = self.statusBar()
        status_bar.setFixedHeight(28)
        status = f"version {__version__}"
        if self.current_user is not None:
            status = f"{self.current_user.display_label}   |   {status}"
        status_bar.showMessage(status)

    def _build_navigation(self, current_user: CurrentUser) -> None:
        container = QWidget(self)
        layout = QHBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # --- Sidebar panel ---
        sidebar_panel = QWidget()
        sidebar_panel.setFixedWidth(NAV_WIDTH)
        sidebar_panel.setStyleSheet(f"background-color: {C.SIDEBAR_BG};")
        sidebar_layout = QVBoxLayout(sidebar_panel)
        sidebar_layout.setContentsMargins(0, 0, 0, 0)
        sidebar_layout.setSpacing(0)

        # Brand header
        brand = QLabel("FUNMITE")
        brand.setAlignment(Qt.AlignmentFlag.AlignCenter)
        brand.setStyleSheet(f"""
            color: {C.ON_PRIMARY};
            font-size: {F.SIZE_XL};
            font-weight: {F.WEIGHT_BOLD};
            padding: 14px 0 10px 0;
            letter-spacing: 3px;
            border-bottom: 1px solid {_darken(C.SIDEBAR_BG, -5)};
            background-color: {C.SIDEBAR_BG};
        """)
        sidebar_layout.addWidget(brand)

        # Subtitle
        subtitle = QLabel("CLOTHING & BEYOND")
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        subtitle.setStyleSheet(f"""
            color: {C.SIDEBAR_FG};
            font-size: {F.SIZE_XS};
            font-weight: {F.WEIGHT_MEDIUM};
            padding: 0 0 8px 0;
            letter-spacing: 1px;
            border-bottom: 1px solid {_darken(C.SIDEBAR_BG, -5)};
            background-color: {C.SIDEBAR_BG};
        """)
        sidebar_layout.addWidget(subtitle)

        # Navigation list
        self.nav = QListWidget()
        self.nav.setStyleSheet(_SIDEBAR_QSS)
        self.nav.setSpacing(0)
        sidebar_layout.addWidget(self.nav, 1)

        # User section at bottom
        user_frame = QFrame()
        user_frame.setStyleSheet(f"""
            QFrame {{
                background-color: {_darken(C.SIDEBAR_BG, -8)};
                border-top: 1px solid {_darken(C.SIDEBAR_BG, -5)};
                padding: 0;
            }}
        """)
        user_layout = QHBoxLayout(user_frame)
        user_layout.setContentsMargins(12, 10, 12, 10)

        user_icon = QLabel("\u25CF")
        user_icon.setStyleSheet(f"color: {C.ACCENT}; font-size: 14px; background: transparent;")
        user_layout.addWidget(user_icon)

        user_info = QLabel(current_user.display_label)
        user_info.setStyleSheet(f"""
            color: {C.SIDEBAR_FG};
            font-size: {F.SIZE_SM};
            font-weight: {F.WEIGHT_MEDIUM};
            background: transparent;
        """)
        user_layout.addWidget(user_info, 1)

        logout_btn = QPushButton("Log out")
        logout_btn.setFixedHeight(28)
        logout_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: transparent;
                color: {C.SIDEBAR_FG};
                border: 1px solid {_darken(C.SIDEBAR_BG, -10)};
                border-radius: 4px;
                font-size: {F.SIZE_SM};
                padding: 2px 10px;
            }}
            QPushButton:hover {{
                background-color: {C.DESTRUCTIVE};
                color: {C.ON_DESTRUCTIVE};
                border-color: {C.DESTRUCTIVE};
            }}
        """)
        logout_btn.clicked.connect(self.logout_requested.emit)
        user_layout.addWidget(logout_btn)

        sidebar_layout.addWidget(user_frame)

        layout.addWidget(sidebar_panel)

        # --- Page stack ---
        self.stack = QStackedWidget(container)
        layout.addWidget(self.stack, 1)

        if self.session_factory is None:
            self._add_placeholder(
                "Welcome",
                "Log in to load the POS screens.\n\n"
                "A database connection is required.",
            )
        elif current_user.role == ROLE_ADMIN:
            dashboard = DashboardPage(self.session_factory, current_user)
            dashboard.view_stock_requested.connect(
                lambda: self.nav.setCurrentRow(self._nav_row("Inventory"))
            )
            self._add_page("Dashboard", dashboard)

            pos = PosPage(self.session_factory, current_user, printer=NullPrinter())
            pos.add_product_requested.connect(
                lambda _barcode: self.nav.setCurrentRow(self._nav_row("Products"))
            )
            self._add_page("POS", pos)

            self._add_page("Products", ProductsPage(self.session_factory, current_user))
            self._add_page("Inventory", InventoryPage(self.session_factory, current_user))
            self._add_page("Customers", CustomersPage(self.session_factory, current_user))
            self._add_page("Purchases", PurchasesPage(self.session_factory, current_user))
            self._add_page("Suppliers", SuppliersPage(self.session_factory, current_user))
            self._add_page("Expenses", ExpensesPage(self.session_factory, current_user))
            self._add_page("Reports", ReportsPage(self.session_factory, current_user))
            self._add_page("Settings", SettingsPage(self.session_factory, current_user))
        else:
            self._add_page("POS", PosPage(self.session_factory, current_user, printer=NullPrinter()))

        self.nav.currentRowChanged.connect(self.stack.setCurrentIndex)
        self.nav.setCurrentRow(0)
        self.setCentralWidget(container)

    def _nav_row(self, label: str) -> int:
        for index in range(self.nav.count()):
            if self.nav.item(index).data(Qt.ItemDataRole.UserRole) == label:
                return index
        return 0

    def _add_page(self, label: str, page: QWidget) -> None:
        item = QListWidgetItem(label)
        item.setData(Qt.ItemDataRole.UserRole, label)
        item.setSizeHint(QListWidgetItem().sizeHint())
        self.nav.addItem(item)
        self.stack.addWidget(page)

    def _add_placeholder(self, label: str, message: str) -> None:
        item = QListWidgetItem(label)
        item.setData(Qt.ItemDataRole.UserRole, label)
        self.nav.addItem(item)
        placeholder = QWidget(self)
        layout = QVBoxLayout(placeholder)
        text = QLabel(message, placeholder)
        text.setAlignment(Qt.AlignmentFlag.AlignCenter)
        text.setWordWrap(True)
        text.setStyleSheet(
            f"font-size: {F.SIZE_LG}; color: {C.MUTED_FG}; padding: 60px;"
        )
        layout.addWidget(text)
        self.stack.addWidget(placeholder)


class AppController:
    """Drives the login -> main-window -> logout lifecycle."""

    def __init__(self, app: QApplication, session_factory) -> None:
        self.app = app
        self.session_factory = session_factory
        self._window: MainWindow | None = None
        self._relogin = False

    def _authenticator(self):
        def authenticate(username: str, password: str):
            with self.session_factory() as session:
                return AuthService(session).authenticate(username, password)

        return authenticate

    def start(self) -> int:
        self.app.setQuitOnLastWindowClosed(False)
        while True:
            current_user = self._prompt_login()
            if current_user is None:
                return 0
            self._relogin = False
            self._show(current_user)
            if not self._relogin:
                return 0

    def _prompt_login(self) -> CurrentUser | None:
        dialog = LoginDialog(authenticator=self._authenticator())
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return None
        return dialog.current_user

    def _show(self, current_user: CurrentUser) -> None:
        self._window = MainWindow(current_user=current_user, session_factory=self.session_factory)
        self._window.logout_requested.connect(self._on_logout)
        self._window.show()
        self.app.exec()

    def _on_logout(self) -> None:
        window = self._window
        if window is None or window.current_user is None:
            return
        self._relogin = True
        with self.session_factory() as session:
            AuditService(session).record(
                user_id=window.current_user.user_id,
                username=window.current_user.username,
                action=ACTION_LOGOUT,
            )
            session.commit()
        window.close()


def main() -> int:
    """Run the application and return its exit code."""
    settings = load_settings()
    setup_logging(settings)
    engine = initialize_database(settings)
    session_factory = create_session_factory(engine)

    with session_scope(session_factory) as session:
        ensure_seed_users(session)

    app = QApplication(sys.argv)

    # --- Apply global theme ---
    app.setStyleSheet(generate_stylesheet())
    default_font = QFont("Segoe UI", 9)
    default_font.setStyleStrategy(QFont.StyleStrategy.PreferAntialias)
    app.setFont(default_font)

    controller = AppController(app, session_factory)
    return controller.start()


if __name__ == "__main__":
    sys.exit(main())
