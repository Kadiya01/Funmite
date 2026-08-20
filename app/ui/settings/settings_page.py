"""Settings page: backup, restore and database management (Admin only).

Phase 09 provides offline local backup and restore.  Backup files are
stored in the configured backup directory as ``funmite_YYYYMMDD_HHMMSS.db``.
A restore always creates a pre-restore safety backup first.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
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
        sync_worker=None,
    ) -> None:
        super().__init__(parent)
        self.session_factory = session_factory
        self.current_user = current_user
        self._backups = []
        self._settings = load_settings()
        self._sync_worker = sync_worker

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

        # -- Cloud Sync section ------------------------------------------------ #

        sync_group = QGroupBox("Cloud Synchronization")
        sync_layout = QVBoxLayout(sync_group)

        # Status row
        status_row = QHBoxLayout()
        self._sync_status_label = QLabel("Status:")
        self._sync_status_label.setStyleSheet(f"font-weight: bold; color: {C.FG};")
        status_row.addWidget(self._sync_status_label)

        self._sync_status_value = QLabel("Not configured")
        self._sync_status_value.setStyleSheet(f"color: {C.MUTED_FG};")
        status_row.addWidget(self._sync_status_value)
        status_row.addStretch()
        sync_layout.addLayout(status_row)

        # Device info row
        device_row = QHBoxLayout()
        device_row.addWidget(QLabel("Device ID:"))
        self._device_id_label = QLabel("—")
        self._device_id_label.setStyleSheet(f"color: {C.MUTED_FG}; font-family: monospace;")
        device_row.addWidget(self._device_id_label)
        device_row.addStretch()
        sync_layout.addLayout(device_row)

        # Pending items row
        pending_row = QHBoxLayout()
        pending_row.addWidget(QLabel("Pending:"))
        self._pending_label = QLabel("0 items")
        self._pending_label.setStyleSheet(f"color: {C.MUTED_FG};")
        pending_row.addWidget(self._pending_label)
        pending_row.addStretch()
        sync_layout.addLayout(pending_row)

        # Registration form (shown when not registered)
        self._reg_form = QWidget()
        reg_layout = QHBoxLayout(self._reg_form)
        reg_layout.setContentsMargins(0, 8, 0, 8)

        reg_layout.addWidget(QLabel("Cloud URL:"))
        self._cloud_url_input = QLineEdit()
        self._cloud_url_input.setPlaceholderText("https://your-cloud-server.com")
        self._cloud_url_input.setFixedWidth(300)
        reg_layout.addWidget(self._cloud_url_input)

        reg_layout.addWidget(QLabel("Device Name:"))
        self._device_name_input = QLineEdit()
        self._device_name_input.setPlaceholderText("e.g. Front Desk PC")
        self._device_name_input.setFixedWidth(200)
        reg_layout.addWidget(self._device_name_input)

        self._register_btn = QPushButton("Register Device")
        self._register_btn.setObjectName("btnPrimary")
        self._register_btn.clicked.connect(self._on_register_device)
        reg_layout.addWidget(self._register_btn)

        reg_layout.addStretch()
        sync_layout.addWidget(self._reg_form)

        # Sync Now button (shown when registered)
        sync_btn_row = QHBoxLayout()
        self._sync_now_btn = QPushButton("Sync Now")
        self._sync_now_btn.setObjectName("btnPrimary")
        self._sync_now_btn.clicked.connect(self._on_sync_now)
        sync_btn_row.addWidget(self._sync_now_btn)
        sync_btn_row.addStretch()
        sync_layout.addLayout(sync_btn_row)

        layout.addWidget(sync_group)

        # Initial load
        self.refresh()

    def refresh(self) -> None:
        """Reload the backup list and sync status."""
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

        self._refresh_sync_section()

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

    def _refresh_sync_section(self) -> None:
        """Update the cloud sync section with current status."""
        from app.sync.device_registration import is_registered, load_credentials
        from app.domain.services.device_service import DeviceIdentity
        from app.data.repositories.sync_repository import SyncQueueRepository

        device = DeviceIdentity(self._settings.data_dir)
        self._device_id_label.setText(device.device_id)

        if not self._settings.cloud_sync_enabled:
            self._sync_status_value.setText("Disabled (set FUNMITE_CLOUD_SYNC=1)")
            self._sync_status_value.setStyleSheet(f"color: {C.MUTED_FG};")
            self._reg_form.setVisible(False)
            self._sync_now_btn.setVisible(False)
            return

        if not is_registered(self._settings.data_dir):
            self._sync_status_value.setText("Not registered")
            self._sync_status_value.setStyleSheet(f"color: #F59E0B;")
            self._reg_form.setVisible(True)
            self._sync_now_btn.setVisible(False)
            self._pending_label.setText("—")
            return

        creds = load_credentials(self._settings.data_dir)
        self._reg_form.setVisible(False)
        self._sync_now_btn.setVisible(True)

        try:
            with session_scope(self.session_factory) as session:
                repo = SyncQueueRepository(session)
                pending = repo.get_pending(limit=10000)
                self._pending_label.setText(f"{len(pending)} items")
        except Exception:
            self._pending_label.setText("—")

        if self._sync_worker is not None:
            self._sync_status_value.setText("Active")
            self._sync_status_value.setStyleSheet(f"color: #10B981;")
        else:
            self._sync_status_value.setText("Registered (worker not running)")
            self._sync_status_value.setStyleSheet(f"color: #F59E0B;")

    def _on_register_device(self) -> None:
        """Register this device with the cloud sync service."""
        from app.sync.device_registration import register_device, is_registered

        url = self._cloud_url_input.text().strip()
        if not url:
            QMessageBox.warning(self, "Missing URL", "Please enter the cloud server URL.")
            return

        name = self._device_name_input.text().strip()
        if not name:
            QMessageBox.warning(self, "Missing Name", "Please enter a device name.")
            return

        self._register_btn.setEnabled(False)
        try:
            result = register_device(self._settings.data_dir, url, name)
            if result.success:
                QMessageBox.information(
                    self,
                    "Registration Complete",
                    f"Device registered successfully.\n\nDevice ID: {result.device_id}",
                )
                self._refresh_sync_section()
            else:
                QMessageBox.warning(
                    self,
                    "Registration Failed",
                    f"Failed to register device:\n{result.error}",
                )
        except Exception as exc:
            QMessageBox.critical(
                self,
                "Registration Error",
                f"An error occurred during registration:\n{exc}",
            )
        finally:
            self._register_btn.setEnabled(True)

    def _on_sync_now(self) -> None:
        """Trigger an immediate sync cycle."""
        if self._sync_worker is None:
            QMessageBox.warning(
                self,
                "Sync Unavailable",
                "Sync worker is not running. Restart the application.",
            )
            return

        self._sync_now_btn.setEnabled(False)
        self._sync_status_value.setText("Syncing…")
        self._sync_status_value.setStyleSheet(f"color: #3B82F6;")
        try:
            self._sync_worker.trigger_push()
            self._sync_worker.trigger_pull()
            QMessageBox.information(
                self,
                "Sync Started",
                "Push and pull cycles triggered. Check status shortly.",
            )
        except Exception as exc:
            QMessageBox.warning(
                self,
                "Sync Error",
                f"Failed to trigger sync:\n{exc}",
            )
        finally:
            self._sync_now_btn.setEnabled(True)
            self._refresh_sync_section()
