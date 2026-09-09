"""Settings page: backup, restore and database management (Admin only).

Phase 09 provides offline local backup and restore.  Backup files are
stored in the configured backup directory as ``funmite_YYYYMMDD_HHMMSS.db``.
A restore always creates a pre-restore safety backup first.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
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
    QFrame,
)

from app.config import load_settings
from app.data.db import session_scope
from app.data.models import PAYMENT_POS
from app.domain.services.backup_service import BackupService
from app.domain.session import CurrentUser
from app.printing.escpos import EscPosRenderer
from app.printing.printer import (
    PrinterConfigStore,
    PrinterUnavailableError,
    PrinterWriteFailureError,
    WindowsPrinter,
)
from app.printing.receipt import ReceiptData, ReceiptLine
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

        title = QLabel("Settings", self)
        title.setStyleSheet(f"font-size: {F.SIZE_2XL}; font-weight: {F.WEIGHT_BOLD}; color: {C.FG};")
        layout.addWidget(title)

        subtitle = QLabel("Backup, restore, and system configuration", self)
        subtitle.setStyleSheet(f"font-size: {F.SIZE_SM}; color: {C.MUTED_FG}; margin-bottom: 8px;")
        layout.addWidget(subtitle)

        # -- Backup & Restore section --------------------------------------- #

        backup_group = QGroupBox("BACKUP & RESTORE")
        backup_layout = QVBoxLayout(backup_group)
        backup_layout.setSpacing(16)

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

        # Danger zone
        danger_zone = QFrame()
        danger_zone.setStyleSheet(f"""
            QFrame {{
                border: 1px solid {C.DESTRUCTIVE_LIGHT};
                border-radius: {S.RADIUS_SM};
                background-color: #FEF2F2;
            }}
        """)
        danger_layout = QHBoxLayout(danger_zone)
        danger_layout.setContentsMargins(16, 16, 16, 16)
        
        restore_info = QLabel(
            "Restore database from selected backup. This will overwrite current data. "
            "A safety backup is created automatically."
        )
        restore_info.setStyleSheet(f"color: {C.DESTRUCTIVE}; font-weight: {F.WEIGHT_MEDIUM};")
        restore_info.setWordWrap(True)
        danger_layout.addWidget(restore_info, 1)

        self.restore_button = QPushButton("Restore from Backup")
        self.restore_button.setObjectName("btnDanger")
        self.restore_button.clicked.connect(self._on_restore)
        danger_layout.addWidget(self.restore_button)
        
        backup_layout.addWidget(danger_zone)
        layout.addWidget(backup_group, 1)

        # -- Receipt printing section ------------------------------------------ #

        printing_group = QGroupBox("RECEIPT PRINTING")
        printing_layout = QVBoxLayout(printing_group)
        printing_layout.setSpacing(12)

        printing_info = QLabel(
            "Choose the Windows thermal printer that prints receipts after each sale. "
            "If left empty, receipts are not printed (Reprint stays available)."
        )
        printing_info.setWordWrap(True)
        printing_info.setStyleSheet(f"color: {C.MUTED_FG};")
        printing_layout.addWidget(printing_info)

        printer_row = QHBoxLayout()
        printer_row.addWidget(QLabel("Printer name:"))
        self.printer_name_input = QComboBox()
        self.printer_name_input.setEditable(True)
        self.printer_name_input.setPlaceholderText(
            "e.g. Xprinter XP-370B"
        )
        self.printer_name_input.setInsertPolicy(
            QComboBox.InsertPolicy.NoInsert
        )
        self.printer_name_input.setCurrentText("")
        printer_row.addWidget(self.printer_name_input, 1)
        printing_layout.addLayout(printer_row)

        self.printer_hint_label = QLabel("")
        self.printer_hint_label.setStyleSheet(f"color: {C.MUTED_FG};")
        printing_layout.addWidget(self.printer_hint_label)

        printer_buttons = QHBoxLayout()
        self.save_printer_button = QPushButton("Save Printer")
        self.save_printer_button.setObjectName("btnPrimary")
        self.save_printer_button.clicked.connect(self._on_save_printer)
        printer_buttons.addWidget(self.save_printer_button)
        self.test_print_button = QPushButton("Test Print")
        self.test_print_button.setObjectName("btnPrimary")
        self.test_print_button.clicked.connect(self._on_test_print)
        printer_buttons.addWidget(self.test_print_button)
        self.clear_printer_button = QPushButton("Clear (no printing)")
        self.clear_printer_button.setObjectName("btnSecondary")
        self.clear_printer_button.clicked.connect(self._on_clear_printer)
        printer_buttons.addWidget(self.clear_printer_button)
        printer_buttons.addStretch()
        printing_layout.addLayout(printer_buttons)

        layout.addWidget(printing_group)

        # -- Cloud Sync section ------------------------------------------------ #

        sync_group = QGroupBox("CLOUD SYNC & DEVICE")
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
        self._load_printer_config()

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

    def _load_printer_config(self) -> None:
        """Populate the printer selector from persisted and installed printers."""
        store = PrinterConfigStore(self._settings.data_dir)
        saved = store.load()
        env_name = (self._settings.printer_name or "").strip()
        selected = saved or env_name

        installed = self._installed_printer_names()
        self.printer_name_input.blockSignals(True)
        self.printer_name_input.clear()
        self.printer_name_input.addItems(installed)
        self.printer_name_input.setCurrentText(selected if selected else "")
        self.printer_name_input.blockSignals(False)

        if env_name and not saved:
            self.printer_hint_label.setText(
                f"Using environment printer: {env_name}"
            )
        elif not installed and env_name:
            self.printer_hint_label.setText(
                f"Using environment printer: {env_name} (no installed printers detected)"
            )
        elif not installed:
            self.printer_hint_label.setText(
                "No installed printers detected by Windows."
            )
        else:
            self.printer_hint_label.setText("")

    def _installed_printer_names(self) -> list[str]:
        """Return the display names of installed Windows printers, if available."""
        try:
            import win32print
        except ImportError:
            return []
        try:
            flags = (
                win32print.PRINTER_ENUM_LOCAL
                | win32print.PRINTER_ENUM_CONNECTIONS
            )
            return sorted(
                {entry[2] for entry in win32print.EnumPrinters(flags)}
            )
        except Exception:  # noqa: BLE001
            return []

    def _on_save_printer(self) -> None:
        """Persist the Settings-UI printer name (primary configuration)."""
        store = PrinterConfigStore(self._settings.data_dir)
        store.save(self.printer_name_input.currentText().strip())
        self._load_printer_config()
        QMessageBox.information(
            self,
            "Printer Saved",
            "The receipt printer has been saved.",
        )

    def _on_clear_printer(self) -> None:
        """Clear the configured printer; falls back to the environment name."""
        store = PrinterConfigStore(self._settings.data_dir)
        store.clear()
        self.printer_name_input.setCurrentText("")
        self._load_printer_config()
        QMessageBox.information(
            self,
            "Printer Cleared",
            "No printer is configured. Receipts will not be printed after sales.",
        )

    def _on_test_print(self) -> None:
        """Send a sample receipt to the selected printer (no sale required)."""
        name = self.printer_name_input.currentText().strip()
        if not name:
            QMessageBox.warning(
                self,
                "No Printer",
                "Enter or pick a printer name, then Save Printer, then Test Print.",
            )
            return

        receipt = ReceiptData(
            receipt_no="TEST-PRINT",
            sale_date=datetime.now(),
            cashier_name=self.current_user.full_name,
            customer_name="Walk-in",
            lines=[
                ReceiptLine(
                    name="Test Product",
                    quantity=1,
                    unit_price=Decimal("500"),
                    total=Decimal("500"),
                )
            ],
            subtotal=Decimal("500"),
            discount_type=None,
            discount_value=Decimal("0"),
            discount_amount=Decimal("0"),
            total=Decimal("500"),
            payment_method=PAYMENT_POS,
            payment_label="BANK POS",
            amount_paid=Decimal("500"),
            barcode="TEST-PRINT",
        )

        try:
            WindowsPrinter(name, renderer=EscPosRenderer()).print_receipt(receipt)
        except PrinterUnavailableError as exc:
            QMessageBox.warning(
                self,
                "Printer Unavailable",
                f"Could not reach '{name}':\n{exc}",
            )
            return
        except PrinterWriteFailureError as exc:
            QMessageBox.warning(
                self,
                "Print Failed",
                f"Writing to '{name}' failed:\n{exc}",
            )
            return
        QMessageBox.information(
            self,
            "Test Print Sent",
            f"A test receipt was sent to '{name}'.",
        )

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
            self._sync_status_value.setStyleSheet(f"color: {C.WARNING};")
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
            self._sync_status_value.setStyleSheet(f"color: {C.SUCCESS};")
        else:
            self._sync_status_value.setText("Registered (worker not running)")
            self._sync_status_value.setStyleSheet(f"color: {C.WARNING};")

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
        self._sync_status_value.setStyleSheet(f"color: {C.INFO};")
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
