"""Users / Cashiers management page (Admin only).

Admins view, search, create, edit, deactivate/reactivate and reset the
passwords of Cashier accounts. Only active Admins reach this screen (the
navigation is Admin-only) and every action is re-checked in the service layer.
Accounts are always Cashiers; Admin accounts are never created or modified here.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.data.db import session_scope
from app.data.repositories.user_repository import UserRepository
from app.domain.errors import NotFoundError, ValidationError
from app.domain.services.user_service import UserService
from app.domain.session import CurrentUser
from app.ui.theme import C, F, empty_state_message
from app.ui.users.user_form import UserFormDialog


class UsersPage(QWidget):
    """Admin Cashier-account management screen."""

    def __init__(self, session_factory, current_user: CurrentUser, parent=None) -> None:
        super().__init__(parent)
        self.session_factory = session_factory
        self.current_user = current_user
        self._users = []

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        title = QLabel("Users & Cashiers", self)
        title.setStyleSheet(f"font-size: {F.SIZE_2XL}; font-weight: {F.WEIGHT_BOLD}; color: {C.FG};")
        layout.addWidget(title)

        subtitle = QLabel("Manage Cashier accounts", self)
        subtitle.setStyleSheet(f"font-size: {F.SIZE_SM}; color: {C.MUTED_FG}; margin-bottom: 8px;")
        layout.addWidget(subtitle)

        toolbar = QHBoxLayout()
        self.add_button = QPushButton("+ Add Cashier")
        self.add_button.setObjectName("btnPrimary")
        self.edit_button = QPushButton("Edit")
        self.edit_button.setObjectName("btnSecondary")
        self.deactivate_button = QPushButton("Deactivate")
        self.deactivate_button.setObjectName("btnSecondary")
        self.reset_pw_button = QPushButton("Reset Password")
        self.reset_pw_button.setObjectName("btnSecondary")
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search by name or username...")
        self.search_input.setClearButtonEnabled(True)
        self.search_input.textChanged.connect(lambda _: self.refresh())
        toolbar.addWidget(self.add_button)
        toolbar.addWidget(self.edit_button)
        toolbar.addWidget(self.deactivate_button)
        toolbar.addWidget(self.reset_pw_button)
        toolbar.addWidget(QLabel("Search:"))
        toolbar.addWidget(self.search_input, 1)
        layout.addLayout(toolbar)

        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["Full Name", "Username", "Role", "Status"])
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.setShowGrid(False)
        self.table.verticalHeader().setDefaultSectionSize(40)
        self.table.setAlternatingRowColors(True)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.table.doubleClicked.connect(lambda _: self.edit_selected())
        layout.addWidget(self.table, 1)

        self.empty_label = QLabel("No users found.", self)
        self.empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_label.setStyleSheet(empty_state_message(""))
        self.empty_label.setVisible(False)
        layout.addWidget(self.empty_label)

        self.count_label = QLabel("")
        self.count_label.setStyleSheet(f"color: {C.MUTED_FG}; font-size: {F.SIZE_SM};")
        layout.addWidget(self.count_label)

        self.add_button.clicked.connect(self.add_user)
        self.edit_button.clicked.connect(self.edit_selected)
        self.deactivate_button.clicked.connect(self.toggle_deactivate)
        self.reset_pw_button.clicked.connect(self.reset_password)

        self.refresh()

    def refresh(self) -> None:
        query = self.search_input.text().strip()
        with session_scope(self.session_factory) as session:
            users = UserRepository(session).search(query, limit=200)
        self._users = users
        self.table.setRowCount(0)
        for user in users:
            row = self.table.rowCount()
            self.table.insertRow(row)
            values = [
                user.full_name,
                user.username,
                user.role.title(),
                "Inactive" if not user.is_active else "",
            ]
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                if not user.is_active:
                    item.setForeground(Qt.GlobalColor.gray)
                self.table.setItem(row, column, item)
            self.table.item(row, 0).setData(Qt.ItemDataRole.UserRole, user.id)
        active = sum(1 for u in users if u.is_active)
        self.count_label.setText(f"{len(users)} user(s) — {active} active")
        self.empty_label.setVisible(len(users) == 0)
        self.deactivate_button.setText("Deactivate" if self._has_selected_active() else "Reactivate")

    def _selected(self):
        by_id = {user.id: user for user in self._users}
        rows = {index.row() for index in self.table.selectionModel().selectedRows()}
        for row in sorted(rows):
            user_id = self.table.item(row, 0).data(Qt.ItemDataRole.UserRole)
            if user_id in by_id:
                yield by_id[user_id]

    def _has_selected_active(self) -> bool:
        for user in self._selected():
            if user.is_active:
                return True
        return False

    def add_user(self) -> None:
        dialog = UserFormDialog(save_handler=self._create_handler())
        if dialog.exec():
            self.refresh()

    def edit_selected(self) -> None:
        selected = list(self._selected())
        if not selected:
            QMessageBox.information(self, "No selection", "Select a user row first.")
            return
        user = selected[0]
        dialog = UserFormDialog(
            save_handler=self._update_handler(user.id),
            existing=user,
        )
        if dialog.exec():
            self.refresh()

    def toggle_deactivate(self) -> None:
        selected = list(self._selected())
        if not selected:
            QMessageBox.information(self, "No selection", "Select a user row first.")
            return
        user = selected[0]
        verb = "deactivate" if user.is_active else "reactivate"
        result = QMessageBox.question(
            self,
            f"{verb.capitalize()} cashier",
            f"Are you sure you want to {verb} '{user.full_name}'?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if result != QMessageBox.StandardButton.Yes:
            return
        try:
            self._deactivate_handler()(user.id)
        except ValidationError as exc:
            QMessageBox.warning(self, "Cannot deactivate", str(exc))
        self.refresh()

    def reset_password(self) -> None:
        selected = list(self._selected())
        if not selected:
            QMessageBox.information(self, "No selection", "Select a user row first.")
            return
        user = selected[0]
        text, ok = QInputDialog.getText(
            self,
            "Reset Password",
            f"Enter a new minimum-6-character password for '{user.full_name}':",
            QLineEdit.EchoMode.Password,
        )
        if not ok:
            return
        try:
            self._reset_password_handler()(user.id, text)
        except ValidationError as exc:
            QMessageBox.warning(self, "Cannot reset password", str(exc))
        self.refresh()

    def _create_handler(self):
        def handler(data: dict):
            with session_scope(self.session_factory) as session:
                return UserService(session).create(
                    self.current_user,
                    username=data["username"],
                    full_name=data["full_name"],
                    password=data["password"],
                )
        return handler

    def _update_handler(self, user_id: int):
        def handler(data: dict):
            with session_scope(self.session_factory) as session:
                return UserService(session).update(
                    self.current_user,
                    user_id,
                    full_name=data["full_name"],
                )
        return handler

    def _deactivate_handler(self):
        def handler(user_id: int) -> None:
            target = self._by_id(user_id)
            with session_scope(self.session_factory) as session:
                service = UserService(session)
                if target.is_active:
                    service.deactivate(self.current_user, user_id)
                else:
                    service.activate(self.current_user, user_id)
        return handler

    def _by_id(self, user_id: int):
        for user in self._users:
            if user.id == user_id:
                return user
        return None

    def _reset_password_handler(self):
        def handler(user_id: int, new_password: str) -> None:
            with session_scope(self.session_factory) as session:
                UserService(session).reset_password(
                    self.current_user, user_id, new_password
                )
        return handler
