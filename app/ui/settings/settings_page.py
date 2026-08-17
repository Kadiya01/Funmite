"""Settings page: backup, restore and database management (Admin only).

Phase 09 provides offline local backup and restore.  Backup files are
stored in the configured backup directory as ``funmite_YYYYMMDD_HHMMSS.db``.
A restore always creates a pre-restore safety backup first.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app.config import load_settings
from app.data.db import session_scope
from app.domain.services.backup_service import BackupService
from app.domain.session import CurrentUser
from app.ui.theme import C, F, S
from app.utils.formatting import format_file_size


def _format_size(size_bytes: int) -> str:
    """Format bytes into human-readable size."""
    return format_file_size(size_bytes)


def _format_datetime(dt) -> str:
    """Format a datetime for display."""
    return dt.strftime("%Y-%m-%d %H:%M:%S")


class SettingsPage(QWidget):
    """Admin settings screen with backup and restore functionality."""

    def __init__(
        self,
        session_factory,
        current_user: CurrentUser,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.session_factory = session_factory
        self.current_user = current_user
        self._backups = []
        self._settings = load_settings()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(16)

        # -- Backup section ------------------------------------------------- #

        backup_group = QGroupBox("Database Backup")
        backup_layout = QVBoxLayout(backup_group)

        backup_toolbar = QHBoxLayout()
        self.backup_button = QPushButton("Create Backup")
        self.backup_button.setObjectName("btnPrimary")
        self.backup_button.clicked.connect(self._on_backup)
        backup_toolbar.addWidget(self.backup_button)
        backup_toolbar.addStretch()
        backup_layout.addLayout(backup_toolbar)

        self.backup_table = QTableWidget(0, 3)
        self.backup_table.setHorizontalHeaderLabels(
            ["Filename", "Size", "Created"]
        )
        self.backup_table.setSelectionBehavior(
            QTableWidget.SelectionBehavior.SelectRows
        )
        self.backup_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.backup_table.setShowGrid(False)
        self.backup_table.verticalHeader().setVisible(False)
        self.backup_table.verticalHeader().setDefaultSectionSize(40)
        self.backup_table.setAlternatingRowColors(True)
        self.backup_table.setSelectionMode(
            QTableWidget.SelectionMode.SingleSelection
        )
        header = self.backup_table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        backup_layout.addWidget(self.backup_table, 1)

        self.backup_count_label = QLabel("No backups")
        self.backup_count_label.setStyleSheet(f"color: {C.MUTED_FG};")
        backup_layout.addWidget(self.backup_count_label)

        layout.addWidget(backup_group, 1)

        # -- Restore section ------------------------------------------------ #

        restore_group = QGroupBox("Database Restore")
        restore_layout = QVBoxLayout(restore_group)

        restore_toolbar = QHBoxLayout()
        self.restore_button = QPushButton("Restore from Backup...")
        self.restore_button.setObjectName("btnDanger")
        self.restore_button.clicked.connect(self._on_restore)
        restore_toolbar.addWidget(self.restore_button)
        restore_toolbar.addStretch()
        restore_layout.addLayout(restore_toolbar)

        restore_info = QLabel(
            "Select a backup from the list above, then click 'Restore from Backup' "
            "to restore the database. A safety backup of the current state will be "
            "created automatically before the restore."
        )
        restore_info.setWordWrap(True)
        restore_layout.addWidget(restore_info)

        layout.addWidget(restore_group)

        # Initial load
        self.refresh()

    def refresh(self) -> None:
        """Reload the backup list."""
        with session_scope(self.session_factory) as session:
            service = BackupService(
                session,
                db_path=self._settings.data_dir / "funmite.db",
                backup_dir=self._settings.backup_dir,
            )
            self._backups = service.list_backups(self.current_user)

        self.backup_table.setRowCount(len(self._backups))
        for row, backup in enumerate(self._backups):
            self.backup_table.setItem(row, 0, QTableWidgetItem(backup.filename))
            self.backup_table.setItem(
                row, 1, QTableWidgetItem(_format_size(backup.size_bytes))
            )
            self.backup_table.setItem(
                row, 2, QTableWidgetItem(_format_datetime(backup.created_at))
            )

        count = len(self._backups)
        if count == 0:
            self.backup_count_label.setText("No backups")
        elif count == 1:
            self.backup_count_label.setText("1 backup")
        else:
            self.backup_count_label.setText(f"{count} backups")

    def _on_backup(self) -> None:
        """Create a new backup."""
        self.backup_button.setEnabled(False)
        try:
            with session_scope(self.session_factory) as session:
                service = BackupService(
                    session,
                    db_path=self._settings.data_dir / "funmite.db",
                    backup_dir=self._settings.backup_dir,
                )
                result = service.create_backup(self.current_user)
                session.commit()

            if result.success:
                QMessageBox.information(
                    self,
                    "Backup Complete",
                    f"Backup created successfully:\n{result.filename}",
                )
                self.refresh()
            else:
                QMessageBox.warning(
                    self,
                    "Backup Failed",
                    f"Backup failed:\n{result.error}",
                )
        except Exception as exc:
            QMessageBox.critical(
                self,
                "Backup Error",
                f"An error occurred during backup:\n{exc}",
            )
        finally:
            self.backup_button.setEnabled(True)

    def _on_restore(self) -> None:
        """Restore from a selected backup."""
        # Get selected backup
        selected_rows = self.backup_table.selectionModel().selectedRows()
        if not selected_rows:
            QMessageBox.warning(
                self,
                "No Backup Selected",
                "Please select a backup from the list above to restore.",
            )
            return

        selected_row = selected_rows[0].row()
        if selected_row >= len(self._backups):
            return

        backup = self._backups[selected_row]
        backup_path = Path(backup.path)

        # Confirmation dialog
        reply = QMessageBox.warning(
            self,
            "Confirm Restore",
            f"Are you sure you want to restore from backup?\n\n"
            f"Backup: {backup.filename}\n"
            f"Created: {_format_datetime(backup.created_at)}\n\n"
            f"WARNING: This will replace the current database.\n"
            f"A safety backup of the current state will be created first.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        self.restore_button.setEnabled(False)
        try:
            with session_scope(self.session_factory) as session:
                service = BackupService(
                    session,
                    db_path=self._settings.data_dir / "funmite.db",
                    backup_dir=self._settings.backup_dir,
                )
                result = service.restore_backup(self.current_user, backup_path)
                session.commit()

            if result.success:
                QMessageBox.information(
                    self,
                    "Restore Complete",
                    f"Database restored successfully from:\n{backup.filename}\n\n"
                    f"A safety backup was saved as:\n"
                    f"{Path(result.pre_restore_backup).name}",
                )
                self.refresh()
            else:
                QMessageBox.warning(
                    self,
                    "Restore Failed",
                    f"Restore failed:\n{result.error}",
                )
        except Exception as exc:
            QMessageBox.critical(
                self,
                "Restore Error",
                f"An error occurred during restore:\n{exc}",
            )
        finally:
            self.restore_button.setEnabled(True)
