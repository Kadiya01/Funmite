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
        self.setStyleSheet(f"QDialog {{ background-color: {C.CARD}; }}")

        self.setWindowTitle("Funmite POS — Login")
        self.setModal(True)
        self.setMinimumWidth(800)
        self.setMinimumHeight(500)

        # Outer layout: Horizontal split
        outer = QHBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # --- Left Pane (Brand) ---
        left_pane = QFrame()
        left_pane.setStyleSheet(f"background-color: {C.PRIMARY_DARK};")
        left_layout = QVBoxLayout(left_pane)
        left_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        brand = QLabel()
        brand.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        from PySide6.QtGui import QPixmap
        from pathlib import Path
        logo_path = Path(__file__).parent.parent.parent / "assets" / "logo.png"
        
        if logo_path.exists():
            pixmap = QPixmap(str(logo_path))
            pixmap = pixmap.scaled(
                220, 140, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation
            )
            brand.setPixmap(pixmap)
        else:
            brand.setText(SHOP_TITLE)
            brand.setStyleSheet(f"""
                color: {C.ON_PRIMARY};
                font-size: 36px;
                font-weight: {F.WEIGHT_BOLD};
                padding: 0;
                background: transparent;
                letter-spacing: 4px;
            """)
        
        left_layout.addWidget(brand)
        left_layout.addSpacing(16)

        subtitle = QLabel(SHOP_SUBTITLE)
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        subtitle.setStyleSheet(f"""
            color: {C.SIDEBAR_FG};
            font-size: {F.SIZE_MD};
            font-weight: {F.WEIGHT_MEDIUM};
            background: transparent;
            letter-spacing: 2px;
        """)
        left_layout.addWidget(subtitle)

        # --- Right Pane (Form) ---
        right_pane = QFrame()
        right_pane.setStyleSheet(f"background-color: {C.CARD};")
        right_layout = QVBoxLayout(right_pane)
        right_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        right_layout.setContentsMargins(60, 40, 60, 40)
        
        # Form Container
        form_container = QFrame()
        form_container.setMaximumWidth(320)
        form_layout = QVBoxLayout(form_container)
        form_layout.setSpacing(0)
        form_layout.setContentsMargins(0, 0, 0, 0)
        
        form_title = QLabel("Welcome Back")
        form_title.setStyleSheet(f"""
            color: {C.PRIMARY};
            font-size: {F.SIZE_3XL};
            font-weight: {F.WEIGHT_BOLD};
            background: transparent;
            margin-bottom: 4px;
        """)
        form_layout.addWidget(form_title)
        
        form_subtitle = QLabel("Please sign in to continue")
        form_subtitle.setStyleSheet(f"""
            color: {C.MUTED_FG};
            font-size: {F.SIZE_MD};
            background: transparent;
            margin-bottom: 32px;
        """)
        form_layout.addWidget(form_subtitle)

        # --- Username ---
        username_label = QLabel("Username")
        username_label.setStyleSheet(f"""
            color: {C.FG_SECONDARY};
            font-size: {F.SIZE_SM};
            font-weight: {F.WEIGHT_MEDIUM};
            padding: 0 0 6px 0;
            background: transparent;
        """)
        form_layout.addWidget(username_label)

        self.username_input = QLineEdit()
        self.username_input.setPlaceholderText("Enter your username")
        self.username_input.setMinimumHeight(44)
        form_layout.addWidget(self.username_input)
        form_layout.addSpacing(20)

        # --- Password ---
        password_label = QLabel("Password")
        password_label.setStyleSheet(f"""
            color: {C.FG_SECONDARY};
            font-size: {F.SIZE_SM};
            font-weight: {F.WEIGHT_MEDIUM};
            padding: 0 0 6px 0;
            background: transparent;
        """)
        form_layout.addWidget(password_label)

        self.password_input = QLineEdit()
        self.password_input.setPlaceholderText("Enter your password")
        self.password_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.password_input.setMinimumHeight(44)
        form_layout.addWidget(self.password_input)
        form_layout.addSpacing(32)

        # --- Login Button ---
        self.login_button = QPushButton("Sign In")
        self.login_button.setObjectName("btnPrimary")
        self.login_button.setDefault(True)
        self.login_button.setMinimumHeight(44)
        self.login_button.setStyleSheet(f"""
            QPushButton {{
                background-color: {C.ACCENT};
                color: {C.ON_ACCENT};
                border: none;
                border-radius: {S.RADIUS_MD};
                font-size: {F.SIZE_MD};
                font-weight: {F.WEIGHT_SEMIBOLD};
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
        form_layout.addWidget(self.login_button)
        form_layout.addSpacing(16)

        # --- Error ---
        self.error_label = QLabel("")
        self.error_label.setStyleSheet(f"""
            color: {C.DESTRUCTIVE};
            background-color: {C.DESTRUCTIVE_LIGHT};
            border-radius: {S.RADIUS_SM};
            padding: 10px 12px;
            font-size: {F.SIZE_SM};
        """)
        self.error_label.setWordWrap(True)
        self.error_label.setVisible(False)
        form_layout.addWidget(self.error_label)
        form_layout.addSpacing(8)

        # --- Hint ---
        hint = QLabel(OFFLINE_HINT)
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hint.setStyleSheet(f"""
            color: {C.MUTED_FG};
            font-size: {F.SIZE_SM};
            background: transparent;
        """)
        form_layout.addWidget(hint)

        right_layout.addWidget(form_container)

        outer.addWidget(left_pane, 1)
        outer.addWidget(right_pane, 1)

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
