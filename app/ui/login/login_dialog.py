"""Login dialog.

Collects a username and password, delegates authentication to the
``AuthService`` (never touches the database directly), and on success exposes
the signed-in user as ``current_user``. The password field is masked and the
dialog never logs or displays passwords.
"""

from __future__ import annotations

import logging
from collections.abc import Callable

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
)

from app.data.models import User
from app.domain.errors import AuthenticationError
from app.domain.session import AuthSession, CurrentUser
from app.ui.theme import C, F, S

logger = logging.getLogger(__name__)

SHOP_TITLE = "FUNMITE"
SHOP_SUBTITLE = "CLOTHING & BEYOND"
OFFLINE_HINT = "Offline mode supported"
GENERIC_ERROR = "Login failed. Please try again."

_DIALOG_QSS = f"""
QDialog {{
    background-color: {C.BG};
}}
"""


class LoginDialog(QDialog):
    """Modal login screen. Emits ``login_succeeded`` on valid credentials."""

    login_succeeded = Signal(object)

    def __init__(
        self,
        authenticator: Callable[[str, str], User],
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._authenticator = authenticator
        self.current_user: CurrentUser | None = None
        self.setStyleSheet(_DIALOG_QSS)

        self.setWindowTitle("Funmite POS — Login")
        self.setModal(True)
        self.setMinimumWidth(400)
        self.setMinimumHeight(480)

        # Outer centered layout
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # Card container
        card = QFrame()
        card.setMaximumWidth(360)
        card.setStyleSheet(f"""
            QFrame {{
                background-color: {C.CARD};
                border: 1px solid {C.BORDER};
                border-radius: {S.RADIUS_LG};
                padding: 32px 28px;
            }}
        """)
        card_layout = QVBoxLayout(card)
        card_layout.setSpacing(0)
        card_layout.setContentsMargins(0, 0, 0, 0)

        # --- Brand ---
        brand = QLabel(SHOP_TITLE)
        brand.setAlignment(Qt.AlignmentFlag.AlignCenter)
        brand.setStyleSheet(f"""
            color: {C.PRIMARY};
            font-size: 28px;
            font-weight: {F.WEIGHT_BOLD};
            padding: 0;
            background: transparent;
            letter-spacing: 4px;
        """)
        card_layout.addWidget(brand)

        subtitle = QLabel(SHOP_SUBTITLE)
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        subtitle.setStyleSheet(f"""
            color: {C.MUTED_FG};
            font-size: {F.SIZE_SM};
            font-weight: {F.WEIGHT_MEDIUM};
            padding: 2px 0 24px 0;
            background: transparent;
            letter-spacing: 2px;
        """)
        card_layout.addWidget(subtitle)

        # --- Divider ---
        divider = QFrame()
        divider.setFrameShape(QFrame.Shape.HLine)
        divider.setStyleSheet(f"background-color: {C.BORDER}; max-height: 1px; border: none;")
        card_layout.addWidget(divider)
        card_layout.addSpacing(24)

        # --- Username ---
        username_label = QLabel("Username")
        username_label.setStyleSheet(f"""
            color: {C.FG_SECONDARY};
            font-size: {F.SIZE_SM};
            font-weight: {F.WEIGHT_MEDIUM};
            padding: 0 0 4px 0;
            background: transparent;
        """)
        card_layout.addWidget(username_label)

        self.username_input = QLineEdit()
        self.username_input.setPlaceholderText("Enter username")
        self.username_input.setMinimumHeight(40)
        card_layout.addWidget(self.username_input)
        card_layout.addSpacing(16)

        # --- Password ---
        password_label = QLabel("Password")
        password_label.setStyleSheet(f"""
            color: {C.FG_SECONDARY};
            font-size: {F.SIZE_SM};
            font-weight: {F.WEIGHT_MEDIUM};
            padding: 0 0 4px 0;
            background: transparent;
        """)
        card_layout.addWidget(password_label)

        self.password_input = QLineEdit()
        self.password_input.setPlaceholderText("Enter password")
        self.password_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.password_input.setMinimumHeight(40)
        card_layout.addWidget(self.password_input)
        card_layout.addSpacing(24)

        # --- Login Button ---
        self.login_button = QPushButton("LOGIN")
        self.login_button.setObjectName("btnPrimary")
        self.login_button.setDefault(True)
        self.login_button.setMinimumHeight(44)
        self.login_button.setStyleSheet(f"""
            QPushButton {{
                background-color: {C.ACCENT};
                color: {C.ON_ACCENT};
                border: none;
                border-radius: {S.RADIUS_SM};
                padding: 10px 16px;
                font-size: {F.SIZE_MD};
                font-weight: {F.WEIGHT_SEMIBOLD};
                min-height: 22px;
                letter-spacing: 1px;
            }}
            QPushButton:hover {{
                background-color: {C.ACCENT_HOVER};
            }}
            QPushButton:pressed {{
                background-color: {_darken(C.ACCENT, 20)};
            }}
            QPushButton:disabled {{
                background-color: {C.MUTED};
                color: {C.MUTED_FG};
            }}
        """)
        card_layout.addWidget(self.login_button)
        card_layout.addSpacing(12)

        # --- Error ---
        self.error_label = QLabel("")
        self.error_label.setStyleSheet(f"""
            color: {C.DESTRUCTIVE};
            background-color: {C.DESTRUCTIVE_LIGHT};
            border-radius: {S.RADIUS_SM};
            padding: 8px 12px;
            font-size: {F.SIZE_SM};
        """)
        self.error_label.setWordWrap(True)
        self.error_label.setVisible(False)
        card_layout.addWidget(self.error_label)
        card_layout.addSpacing(8)

        # --- Hint ---
        hint = QLabel(OFFLINE_HINT)
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hint.setStyleSheet(f"""
            color: {C.MUTED_FG};
            font-size: {F.SIZE_XS};
            background: transparent;
        """)
        card_layout.addWidget(hint)

        outer.addWidget(card, alignment=Qt.AlignmentFlag.AlignCenter)

        # --- Connections ---
        self.login_button.clicked.connect(self._submit)
        self.username_input.returnPressed.connect(self._submit)
        self.password_input.returnPressed.connect(self._submit)

        self.username_input.setFocus()

    def _submit(self) -> None:
        username = self.username_input.text().strip()
        password = self.password_input.text()
        if not username or not password:
            self._show_error("Enter your username and password.")
            return

        try:
            user = self._authenticator(username, password)
        except AuthenticationError as exc:
            self._show_error(str(exc) or GENERIC_ERROR)
            return
        except Exception:
            logger.exception("Unexpected error during login for user %r", username)
            self._show_error(GENERIC_ERROR)
            return

        self.current_user = AuthSession().start(user)
        self.login_succeeded.emit(self.current_user)
        self.accept()

    def _show_error(self, message: str) -> None:
        self.error_label.setText(message)
        self.error_label.setVisible(True)
        self.password_input.clear()
        self.password_input.setFocus()


def _darken(hex_color: str, amount: int = 15) -> str:
    h = hex_color.lstrip("#")
    r, g, b = (int(h[i : i + 2], 16) for i in (0, 2, 4))
    return f"#{max(0, r - amount):02x}{max(0, g - amount):02x}{max(0, b - amount):02x}"
