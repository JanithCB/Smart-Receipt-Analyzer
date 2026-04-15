# src/desktop/views.py

import logging
from pathlib import Path
from typing import Any

from PySide6.QtCore import (
    QMimeData,
    QSize,
    Qt,
    QThreadPool,
    QUrl,
    Signal,
    Slot,
)
from PySide6.QtGui import QDragEnterEvent, QDropEvent, QFont
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSpacerItem,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
    QFileDialog,
    QProgressBar,
    QCheckBox,
)

from desktop.workers import (
    ApiWorker,
    UploadWorker,
    make_analytics_worker,
    make_ask_advisor_worker,
    make_auto_insights_worker,
    make_delete_receipt_worker,
    make_insights_worker,
    make_list_receipts_worker,
    make_login_worker,
    make_register_worker,
    make_reprocess_receipt_worker,
    make_summary_worker,
    make_update_receipt_worker,
    make_correct_category_worker,
)

logger = logging.getLogger(__name__)

POOL = QThreadPool.globalInstance()

CATEGORIES = [
    "All",
    "Groceries",
    "Dining",
    "Transport",
    "Utilities",
    "Healthcare",
    "Shopping",
    "Entertainment",
    "Education",
    "Travel",
    "Finance",
    "Other",
]

CURRENCIES = ["LKR", "USD", "EUR", "GBP", "INR", "AUD", "CAD", "JPY"]

PERIOD_OPTIONS = [
    ("This Week",  "week"),
    ("This Month", "month"),
    ("This Year",  "year"),
    ("All Time",   "all"),
]


# ──────────────────────────────────────────────────────────────────────────────
# Shared helper widgets
# ──────────────────────────────────────────────────────────────────────────────


def _make_divider() -> QFrame:
    line = QFrame()
    line.setFrameShape(QFrame.Shape.HLine)
    line.setStyleSheet("background-color: #242630; border: none; max-height: 1px;")
    return line


def _make_card(parent: QWidget | None = None) -> QFrame:
    card = QFrame(parent)
    card.setObjectName("card")
    return card


def _make_section_title(text: str) -> QLabel:
    label = QLabel(text)
    label.setObjectName("section_title")
    return label


def _make_muted_label(text: str) -> QLabel:
    label = QLabel(text)
    label.setObjectName("muted")
    return label


def _make_primary_button(text: str) -> QPushButton:
    btn = QPushButton(text)
    btn.setObjectName("primary_btn")
    btn.setMinimumHeight(38)
    btn.setCursor(Qt.CursorShape.PointingHandCursor)
    return btn


class KpiCard(QFrame):
    def __init__(self, title: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("card")
        self.setMinimumWidth(160)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(6)

        self._title = QLabel(title.upper())
        self._title.setObjectName("kpi_label")

        self._value = QLabel("—")
        self._value.setObjectName("kpi_value")

        layout.addWidget(self._title)
        layout.addWidget(self._value)

    def set_value(self, value: str) -> None:
        self._value.setText(value)


class SimpleBarChart(QWidget):
    """
    A minimal canvas-free bar chart drawn with QFrame widgets.
    Uses proportional height bars inside a fixed container.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._layout = QHBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(8)
        self._layout.setAlignment(Qt.AlignmentFlag.AlignBottom | Qt.AlignmentFlag.AlignLeft)
        self.setMinimumHeight(140)

    def set_data(self, items: list[dict], value_key: str = "amount", label_key: str = "category") -> None:
        while self._layout.count():
            child = self._layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

        if not items:
            placeholder = _make_muted_label("No data available")
            placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self._layout.addWidget(placeholder)
            return

        max_value = max(float(item.get(value_key, 0) or 0) for item in items) or 1
        max_bar_height = 110

        for item in items[:10]:
            value = float(item.get(value_key, 0) or 0)
            label_text = str(item.get(label_key, ""))[:14]
            bar_height = max(4, int((value / max_value) * max_bar_height))

            col = QWidget()
            col_layout = QVBoxLayout(col)
            col_layout.setContentsMargins(0, 0, 0, 0)
            col_layout.setSpacing(4)
            col_layout.setAlignment(Qt.AlignmentFlag.AlignBottom | Qt.AlignmentFlag.AlignHCenter)

            bar = QFrame()
            bar.setFixedWidth(28)
            bar.setFixedHeight(bar_height)
            bar.setStyleSheet(
                "background-color: #2563eb; border-radius: 4px;"
            )

            amount_label = QLabel(f"{value:,.0f}")
            amount_label.setAlignment(Qt.AlignmentFlag.AlignHCenter)
            amount_label.setStyleSheet("font-size: 10px; color: #9ca3af;")

            name_label = QLabel(label_text)
            name_label.setAlignment(Qt.AlignmentFlag.AlignHCenter)
            name_label.setStyleSheet("font-size: 10px; color: #6b7280;")
            name_label.setWordWrap(True)
            name_label.setFixedWidth(60)

            col_layout.addWidget(amount_label)
            col_layout.addWidget(bar)
            col_layout.addWidget(name_label)

            self._layout.addWidget(col)

        self._layout.addStretch()


# ──────────────────────────────────────────────────────────────────────────────
# LoginView
# ──────────────────────────────────────────────────────────────────────────────


class LoginView(QWidget):
    login_success      = Signal(dict)
    switch_to_register = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._build_ui()

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setAlignment(Qt.AlignmentFlag.AlignCenter)

        card = _make_card()
        card.setFixedWidth(420)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(36, 36, 36, 36)
        layout.setSpacing(16)

        title = _make_section_title("Sign in to Vispend AI")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)

        sub = _make_muted_label("Manage your receipts and spending insights")
        sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(sub)
        layout.addSpacing(8)

        self._email = QLineEdit()
        self._email.setPlaceholderText("Email address")
        self._email.setMinimumHeight(40)
        layout.addWidget(self._email)

        self._password = QLineEdit()
        self._password.setPlaceholderText("Password")
        self._password.setEchoMode(QLineEdit.EchoMode.Password)
        self._password.setMinimumHeight(40)
        self._password.returnPressed.connect(self._on_login)
        layout.addWidget(self._password)

        self._error_label = QLabel("")
        self._error_label.setStyleSheet("color: #f87171; font-size: 12px;")
        self._error_label.setWordWrap(True)
        self._error_label.hide()
        layout.addWidget(self._error_label)

        self._login_btn = _make_primary_button("Sign in")
        self._login_btn.setMinimumHeight(42)
        self._login_btn.clicked.connect(self._on_login)
        layout.addWidget(self._login_btn)

        layout.addWidget(_make_divider())

        register_row = QHBoxLayout()
        register_row.setAlignment(Qt.AlignmentFlag.AlignCenter)
        register_row.addWidget(_make_muted_label("No account?"))
        register_btn = QPushButton("Create one")
        register_btn.setFlat(True)
        register_btn.setStyleSheet("color: #60a5fa; background: transparent; border: none; font-size: 13px;")
        register_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        register_btn.clicked.connect(self.switch_to_register)
        register_row.addWidget(register_btn)
        layout.addLayout(register_row)

        outer.addWidget(card)

    @Slot()
    def _on_login(self) -> None:
        email    = self._email.text().strip()
        password = self._password.text()
        self._error_label.hide()

        if not email or not password:
            self._show_error("Please enter your email and password.")
            return

        self._login_btn.setEnabled(False)
        self._login_btn.setText("Signing in...")

        worker = make_login_worker(email, password)
        worker.signals.result.connect(self._on_success)
        worker.signals.error.connect(self._on_error)
        POOL.start(worker)

    @Slot(object)
    def _on_success(self, payload: Any) -> None:
        self._login_btn.setEnabled(True)
        self._login_btn.setText("Sign in")
        self._password.clear()
        self.login_success.emit(payload)

    @Slot(str)
    def _on_error(self, message: str) -> None:
        self._login_btn.setEnabled(True)
        self._login_btn.setText("Sign in")
        self._show_error(message)

    def _show_error(self, message: str) -> None:
        self._error_label.setText(message)
        self._error_label.show()


# ──────────────────────────────────────────────────────────────────────────────
# RegisterView
# ──────────────────────────────────────────────────────────────────────────────


class RegisterView(QWidget):
    register_success = Signal(dict)
    switch_to_login  = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._build_ui()

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setAlignment(Qt.AlignmentFlag.AlignCenter)

        card = _make_card()
        card.setFixedWidth(440)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(36, 36, 36, 36)
        layout.setSpacing(14)

        title = _make_section_title("Create an account")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)
        layout.addSpacing(6)

        self._full_name = QLineEdit()
        self._full_name.setPlaceholderText("Full name")
        self._full_name.setMinimumHeight(40)
        layout.addWidget(self._full_name)

        self._username = QLineEdit()
        self._username.setPlaceholderText("Username")
        self._username.setMinimumHeight(40)
        layout.addWidget(self._username)

        self._email = QLineEdit()
        self._email.setPlaceholderText("Email address")
        self._email.setMinimumHeight(40)
        layout.addWidget(self._email)

        self._password = QLineEdit()
        self._password.setPlaceholderText("Password")
        self._password.setEchoMode(QLineEdit.EchoMode.Password)
        self._password.setMinimumHeight(40)
        layout.addWidget(self._password)

        self._confirm = QLineEdit()
        self._confirm.setPlaceholderText("Confirm password")
        self._confirm.setEchoMode(QLineEdit.EchoMode.Password)
        self._confirm.setMinimumHeight(40)
        self._confirm.returnPressed.connect(self._on_register)
        layout.addWidget(self._confirm)

        self._error_label = QLabel("")
        self._error_label.setStyleSheet("color: #f87171; font-size: 12px;")
        self._error_label.setWordWrap(True)
        self._error_label.hide()
        layout.addWidget(self._error_label)

        self._register_btn = _make_primary_button("Create account")
        self._register_btn.setMinimumHeight(42)
        self._register_btn.clicked.connect(self._on_register)
        layout.addWidget(self._register_btn)

        layout.addWidget(_make_divider())

        login_row = QHBoxLayout()
        login_row.setAlignment(Qt.AlignmentFlag.AlignCenter)
        login_row.addWidget(_make_muted_label("Already have an account?"))
        login_btn = QPushButton("Sign in")
        login_btn.setFlat(True)
        login_btn.setStyleSheet("color: #60a5fa; background: transparent; border: none; font-size: 13px;")
        login_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        login_btn.clicked.connect(self.switch_to_login)
        login_row.addWidget(login_btn)
        layout.addLayout(login_row)

        outer.addWidget(card)

    @Slot()
    def _on_register(self) -> None:
        full_name = self._full_name.text().strip()
        username  = self._username.text().strip()
        email     = self._email.text().strip()
        password  = self._password.text()
        confirm   = self._confirm.text()
        self._error_label.hide()

        if not username or not email or not password:
            self._show_error("Username, email, and password are required.")
            return
        if len(username) < 3:
            self._show_error("Username must be at least 3 characters.")
            return
        if len(password) < 6:
            self._show_error("Password must be at least 6 characters.")
            return
        if password != confirm:
            self._show_error("Passwords do not match.")
            return

        self._register_btn.setEnabled(False)
        self._register_btn.setText("Creating account...")

        worker = make_register_worker(email, username, password, full_name or None)
        worker.signals.result.connect(self._on_success)
        worker.signals.error.connect(self._on_error)
        POOL.start(worker)

    @Slot(object)
    def _on_success(self, payload: Any) -> None:
        self._register_btn.setEnabled(True)
        self._register_btn.setText("Create account")
        self._clear_fields()
        self.register_success.emit(payload)

    @Slot(str)
    def _on_error(self, message: str) -> None:
        self._register_btn.setEnabled(True)
        self._register_btn.setText("Create account")
        self._show_error(message)

    def _show_error(self, message: str) -> None:
        self._error_label.setText(message)
        self._error_label.show()

    def _clear_fields(self) -> None:
        self._password.clear()
        self._confirm.clear()


# ──────────────────────────────────────────────────────────────────────────────
# UploadView
# ──────────────────────────────────────────────────────────────────────────────


class _DropArea(QFrame):
    files_dropped = Signal(list)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.setMinimumHeight(160)
        self.setStyleSheet(
            "QFrame { background-color: #1a1d27; border: 2px dashed #2d3041; border-radius: 12px; }"
            "QFrame:hover { border-color: #3b82f6; }"
        )

        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setSpacing(8)

        icon_label = QLabel("Drop receipt files here")
        icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon_label.setStyleSheet("font-size: 14px; color: #6b7280; border: none;")
        layout.addWidget(icon_label)

        hint = QLabel("JPEG, PNG, WEBP, BMP, TIFF, PDF — up to 15 MB each")
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hint.setStyleSheet("font-size: 11px; color: #4b5563; border: none;")
        layout.addWidget(hint)

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
            self.setStyleSheet(
                "QFrame { background-color: #1e2a3a; border: 2px dashed #3b82f6; border-radius: 12px; }"
            )

    def dragLeaveEvent(self, event: Any) -> None:
        self.setStyleSheet(
            "QFrame { background-color: #1a1d27; border: 2px dashed #2d3041; border-radius: 12px; }"
            "QFrame:hover { border-color: #3b82f6; }"
        )

    def dropEvent(self, event: QDropEvent) -> None:
        self.setStyleSheet(
            "QFrame { background-color: #1a1d27; border: 2px dashed #2d3041; border-radius: 12px; }"
            "QFrame:hover { border-color: #3b82f6; }"
        )
        paths = [url.toLocalFile() for url in event.mimeData().urls() if url.isLocalFile()]
        if paths:
            self.files_dropped.emit(paths)


class UploadView(QWidget):
    upload_complete = Signal()

    ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tif", ".tiff", ".pdf"}

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._queued_files: list[Path] = []
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 28, 28, 28)
        layout.setSpacing(16)

        layout.addWidget(_make_section_title("Upload Receipts"))
        layout.addWidget(_make_muted_label("Drop files below or browse to add receipts to the queue."))

        self._drop_area = _DropArea()
        self._drop_area.files_dropped.connect(self._add_files)
        layout.addWidget(self._drop_area)

        btn_row = QHBoxLayout()
        browse_btn = QPushButton("Browse files")
        browse_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        browse_btn.clicked.connect(self._browse_files)
        btn_row.addWidget(browse_btn)

        self._clear_btn = QPushButton("Clear queue")
        self._clear_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._clear_btn.clicked.connect(self._clear_queue)
        btn_row.addWidget(self._clear_btn)
        btn_row.addStretch()

        self._upload_btn = _make_primary_button("Upload all")
        self._upload_btn.setEnabled(False)
        self._upload_btn.clicked.connect(self._start_upload)
        btn_row.addWidget(self._upload_btn)
        layout.addLayout(btn_row)

        self._queue_label = _make_muted_label("No files queued")
        layout.addWidget(self._queue_label)

        self._progress_bar = QProgressBar()
        self._progress_bar.setVisible(False)
        self._progress_bar.setMinimum(0)
        self._progress_bar.setTextVisible(False)
        layout.addWidget(self._progress_bar)

        self._status_list = QVBoxLayout()
        self._status_list.setSpacing(4)
        status_container = QWidget()
        status_container.setLayout(self._status_list)
        scroll = QScrollArea()
        scroll.setWidget(status_container)
        scroll.setWidgetResizable(True)
        scroll.setMaximumHeight(220)
        scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")
        layout.addWidget(scroll)
        layout.addStretch()

    def _add_files(self, paths: list[str]) -> None:
        added = 0
        for raw_path in paths:
            path = Path(raw_path)
            if path.suffix.lower() not in self.ALLOWED_EXTENSIONS:
                self._add_status_row(path.name, "Skipped — unsupported type", "#f87171")
                continue
            if path not in self._queued_files:
                self._queued_files.append(path)
                self._add_status_row(path.name, "Queued", "#6b7280")
                added += 1

        self._update_queue_label()
        self._upload_btn.setEnabled(bool(self._queued_files))

    def _add_status_row(self, filename: str, status_text: str, color: str) -> None:
        row = QLabel(f"  {filename}  —  {status_text}")
        row.setProperty("filename", filename)
        row.setStyleSheet(f"color: {color}; font-size: 12px; padding: 2px 0;")
        self._status_list.addWidget(row)

    def _update_status_row(self, filename: str, status_text: str, color: str) -> None:
        for i in range(self._status_list.count()):
            item = self._status_list.itemAt(i)
            if item and item.widget():
                w = item.widget()
                if w.property("filename") == filename:
                    w.setText(f"  {filename}  —  {status_text}")
                    w.setStyleSheet(f"color: {color}; font-size: 12px; padding: 2px 0;")
                    return

    def _update_queue_label(self) -> None:
        count = len(self._queued_files)
        self._queue_label.setText(f"{count} file{'s' if count != 1 else ''} queued" if count else "No files queued")

    def _clear_queue(self) -> None:
        self._queued_files.clear()
        while self._status_list.count():
            child = self._status_list.takeAt(0)
            if child.widget():
                child.widget().deleteLater()
        self._update_queue_label()
        self._upload_btn.setEnabled(False)

    @Slot()
    def _browse_files(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(
            self,
            "Select receipt files",
            "",
            "Receipt files (*.jpg *.jpeg *.png *.webp *.bmp *.tif *.tiff *.pdf)",
        )
        if paths:
            self._add_files(paths)

    @Slot()
    def _start_upload(self) -> None:
        if not self._queued_files:
            return

        self._upload_btn.setEnabled(False)
        self._progress_bar.setMaximum(len(self._queued_files))
        self._progress_bar.setValue(0)
        self._progress_bar.setVisible(True)

        worker = UploadWorker(list(self._queued_files))
        worker.signals.file_done.connect(self._on_file_done)
        worker.signals.error.connect(self._on_file_error)
        worker.signals.progress.connect(self._on_progress)
        worker.signals.finished.connect(self._on_all_done)
        POOL.start(worker)

    @Slot(str, object)
    def _on_file_done(self, filename: str, receipt: Any) -> None:
        self._update_status_row(filename, "Uploaded", "#4ade80")
        self.upload_complete.emit()

    @Slot(str, str)
    def _on_file_error(self, filename: str, message: str) -> None:
        self._update_status_row(filename, f"Failed: {message}", "#f87171")

    @Slot(int, int)
    def _on_progress(self, completed: int, total: int) -> None:
        self._progress_bar.setValue(completed)

    @Slot()
    def _on_all_done(self) -> None:
        self._queued_files.clear()
        self._update_queue_label()
        self._upload_btn.setEnabled(False)


# ──────────────────────────────────────────────────────────────────────────────
# Edit receipt dialog
# ──────────────────────────────────────────────────────────────────────────────


class EditReceiptDialog(QDialog):
    def __init__(self, receipt: dict, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._receipt = receipt
        self.setWindowTitle("Edit Receipt")
        self.setMinimumWidth(420)
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(14)

        form = QFormLayout()
        form.setSpacing(10)

        self._merchant = QLineEdit(self._receipt.get("merchant") or "")
        self._merchant.setPlaceholderText("Merchant name")
        self._merchant.setMinimumHeight(38)
        form.addRow("Merchant", self._merchant)

        self._amount = QDoubleSpinBox()
        self._amount.setMinimum(0.0)
        self._amount.setMaximum(9_999_999.99)
        self._amount.setDecimals(2)
        self._amount.setMinimumHeight(38)
        current_amount = self._receipt.get("total_amount") or 0.0
        try:
            self._amount.setValue(float(current_amount))
        except (TypeError, ValueError):
            self._amount.setValue(0.0)
        form.addRow("Amount", self._amount)

        self._currency = QComboBox()
        self._currency.addItems(CURRENCIES)
        current_currency = self._receipt.get("currency") or "LKR"
        if current_currency in CURRENCIES:
            self._currency.setCurrentText(current_currency)
        self._currency.setMinimumHeight(38)
        form.addRow("Currency", self._currency)

        self._category = QComboBox()
        category_options = CATEGORIES[1:]
        self._category.addItems(category_options)
        current_category = self._receipt.get("category") or "Other"
        if current_category in category_options:
            self._category.setCurrentText(current_category)
        self._category.setMinimumHeight(38)
        form.addRow("Category", self._category)

        self._notes = QTextEdit()
        self._notes.setPlainText(self._receipt.get("notes") or "")
        self._notes.setMaximumHeight(80)
        self._notes.setPlaceholderText("Optional notes...")
        form.addRow("Notes", self._notes)

        layout.addLayout(form)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def get_data(self) -> dict:
        return {
            "merchant":     self._merchant.text().strip() or None,
            "total_amount": self._amount.value(),
            "currency":     self._currency.currentText(),
            "category":     self._category.currentText(),
            "notes":        self._notes.toPlainText().strip() or None,
        }


# ──────────────────────────────────────────────────────────────────────────────
# ReceiptsView
# ──────────────────────────────────────────────────────────────────────────────


class ReceiptsView(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._current_page     = 1
        self._total_pages      = 1
        self._receipts_cache: list[dict] = []
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 28, 28, 28)
        layout.setSpacing(12)

        header_row = QHBoxLayout()
        header_row.addWidget(_make_section_title("Receipts"))
        header_row.addStretch()
        refresh_btn = QPushButton("Refresh")
        refresh_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        refresh_btn.clicked.connect(self.refresh)
        header_row.addWidget(refresh_btn)
        layout.addLayout(header_row)

        filter_row = QHBoxLayout()
        filter_row.setSpacing(10)

        self._search = QLineEdit()
        self._search.setPlaceholderText("Search receipts...")
        self._search.setMinimumHeight(36)
        self._search.setMinimumWidth(200)
        self._search.returnPressed.connect(self.refresh)
        filter_row.addWidget(self._search)

        self._category_filter = QComboBox()
        self._category_filter.addItems(CATEGORIES)
        self._category_filter.setMinimumHeight(36)
        self._category_filter.currentIndexChanged.connect(self._on_filter_changed)
        filter_row.addWidget(self._category_filter)

        self._status_filter = QComboBox()
        self._status_filter.addItems(["All status", "done", "processing", "failed", "pending"])
        self._status_filter.setMinimumHeight(36)
        self._status_filter.currentIndexChanged.connect(self._on_filter_changed)
        filter_row.addWidget(self._status_filter)

        self._review_filter = QCheckBox("Needs review")
        self._review_filter.stateChanged.connect(self._on_filter_changed)
        filter_row.addWidget(self._review_filter)

        filter_row.addStretch()
        layout.addLayout(filter_row)

        self._table = QTableWidget()
        self._table.setColumnCount(7)
        self._table.setHorizontalHeaderLabels(
            ["Date", "Merchant", "Amount", "Currency", "Category", "Status", "Actions"]
        )
        self._table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._table.setAlternatingRowColors(True)
        self._table.verticalHeader().setVisible(False)
        self._table.setShowGrid(False)
        layout.addWidget(self._table)

        pagination_row = QHBoxLayout()
        self._prev_btn = QPushButton("Previous")
        self._prev_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._prev_btn.clicked.connect(self._prev_page)
        pagination_row.addWidget(self._prev_btn)

        self._page_label = QLabel("Page 1")
        self._page_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        pagination_row.addWidget(self._page_label)

        self._next_btn = QPushButton("Next")
        self._next_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._next_btn.clicked.connect(self._next_page)
        pagination_row.addWidget(self._next_btn)
        pagination_row.addStretch()

        self._count_label = _make_muted_label("")
        pagination_row.addWidget(self._count_label)
        layout.addLayout(pagination_row)

        self._status_label = _make_muted_label("")
        layout.addWidget(self._status_label)

    def refresh(self) -> None:
        self._load_receipts(self._current_page)

    def _get_filters(self) -> dict:
        filters: dict[str, Any] = {}
        search = self._search.text().strip()
        if search:
            filters["search"] = search
        cat = self._category_filter.currentText()
        if cat != "All":
            filters["category"] = cat
        status = self._status_filter.currentText()
        if status != "All status":
            filters["status"] = status
        if self._review_filter.isChecked():
            filters["needs_review"] = True
        return filters

    def _load_receipts(self, page: int) -> None:
        filters = self._get_filters()
        self._status_label.setText("Loading...")
        worker = make_list_receipts_worker(page=page, **filters)
        worker.signals.result.connect(self._on_receipts_loaded)
        worker.signals.error.connect(self._on_load_error)
        POOL.start(worker)

    @Slot(object)
    def _on_receipts_loaded(self, payload: Any) -> None:
        self._status_label.setText("")
        if not isinstance(payload, dict):
            return

        receipts = payload.get("receipts") or payload.get("items") or []
        total    = payload.get("total", 0)
        page     = payload.get("page", 1)
        pages    = payload.get("pages") or payload.get("total_pages", 1)

        self._receipts_cache = receipts
        self._current_page   = page
        self._total_pages    = max(1, pages)

        self._populate_table(receipts)
        self._page_label.setText(f"Page {page} of {self._total_pages}")
        self._count_label.setText(f"{total} total receipts")
        self._prev_btn.setEnabled(page > 1)
        self._next_btn.setEnabled(page < self._total_pages)

    @Slot(str)
    def _on_load_error(self, message: str) -> None:
        self._status_label.setText(f"Error: {message}")

    def _populate_table(self, receipts: list[dict]) -> None:
        self._table.setRowCount(0)
        self._table.setRowCount(len(receipts))

        for row, receipt in enumerate(receipts):
            receipt_id = receipt.get("id", 0)

            date_val = receipt.get("receipt_date") or receipt.get("created_at") or ""
            if date_val and len(str(date_val)) > 10:
                date_val = str(date_val)[:10]

            self._table.setItem(row, 0, QTableWidgetItem(str(date_val)))
            self._table.setItem(row, 1, QTableWidgetItem(receipt.get("merchant") or "—"))
            amount = receipt.get("total_amount")
            amount_text = f"{float(amount):,.2f}" if amount is not None else "—"
            self._table.setItem(row, 2, QTableWidgetItem(amount_text))
            self._table.setItem(row, 3, QTableWidgetItem(receipt.get("currency") or "—"))
            self._table.setItem(row, 4, QTableWidgetItem(receipt.get("category") or "—"))
            self._table.setItem(row, 5, QTableWidgetItem(receipt.get("processing_status") or "—"))

            for col in range(6):
                item = self._table.item(row, col)
                if item:
                    item.setTextAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)

            action_widget = QWidget()
            action_layout = QHBoxLayout(action_widget)
            action_layout.setContentsMargins(4, 2, 4, 2)
            action_layout.setSpacing(6)

            edit_btn = QPushButton("Edit")
            edit_btn.setFixedHeight(28)
            edit_btn.setStyleSheet("font-size: 12px; padding: 2px 10px;")
            edit_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            edit_btn.clicked.connect(lambda _, rid=receipt_id: self._edit_receipt(rid))

            delete_btn = QPushButton("Delete")
            delete_btn.setFixedHeight(28)
            delete_btn.setStyleSheet(
                "font-size: 12px; padding: 2px 10px;"
                "background-color: #2a1a1a; border-color: #7f1d1d; color: #fca5a5;"
            )
            delete_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            delete_btn.clicked.connect(lambda _, rid=receipt_id: self._delete_receipt(rid))

            action_layout.addWidget(edit_btn)
            action_layout.addWidget(delete_btn)
            action_layout.addStretch()
            self._table.setCellWidget(row, 6, action_widget)
            self._table.setRowHeight(row, 42)

    def _edit_receipt(self, receipt_id: int) -> None:
        receipt = next((r for r in self._receipts_cache if r.get("id") == receipt_id), None)
        if receipt is None:
            return

        dialog = EditReceiptDialog(receipt, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            data = dialog.get_data()
            worker = make_update_receipt_worker(receipt_id, **data)
            worker.signals.result.connect(lambda _: self.refresh())
            worker.signals.error.connect(lambda msg: QMessageBox.warning(self, "Update failed", msg))
            POOL.start(worker)

    def _delete_receipt(self, receipt_id: int) -> None:
        reply = QMessageBox.question(
            self,
            "Delete receipt",
            "Are you sure you want to delete this receipt? This action cannot be undone.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        worker = make_delete_receipt_worker(receipt_id)
        worker.signals.result.connect(lambda _: self.refresh())
        worker.signals.error.connect(lambda msg: QMessageBox.warning(self, "Delete failed", msg))
        POOL.start(worker)

    def _on_filter_changed(self) -> None:
        self._current_page = 1
        self.refresh()

    def _prev_page(self) -> None:
        if self._current_page > 1:
            self._current_page -= 1
            self._load_receipts(self._current_page)

    def _next_page(self) -> None:
        if self._current_page < self._total_pages:
            self._current_page += 1
            self._load_receipts(self._current_page)


# ──────────────────────────────────────────────────────────────────────────────
# AnalyticsView
# ──────────────────────────────────────────────────────────────────────────────


class AnalyticsView(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._build_ui()

    def _build_ui(self) -> None:
        scroll_area = QScrollArea(self)
        scroll_area.setWidgetResizable(True)
        scroll_area.setStyleSheet("QScrollArea { border: none; }")

        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(28, 28, 28, 28)
        layout.setSpacing(20)

        header_row = QHBoxLayout()
        header_row.addWidget(_make_section_title("Analytics"))
        header_row.addStretch()

        self._period_combo = QComboBox()
        for label, value in PERIOD_OPTIONS:
            self._period_combo.addItem(label, userData=value)
        self._period_combo.setCurrentIndex(1)
        self._period_combo.setMinimumHeight(34)
        self._period_combo.currentIndexChanged.connect(self.refresh)
        header_row.addWidget(self._period_combo)
        layout.addLayout(header_row)

        kpi_row = QHBoxLayout()
        kpi_row.setSpacing(12)
        self._kpi_total    = KpiCard("Total Spend")
        self._kpi_count    = KpiCard("Receipts")
        self._kpi_avg      = KpiCard("Avg Amount")
        self._kpi_top_cat  = KpiCard("Top Category")
        for kpi in (self._kpi_total, self._kpi_count, self._kpi_avg, self._kpi_top_cat):
            kpi_row.addWidget(kpi)
        layout.addLayout(kpi_row)

        layout.addWidget(_make_divider())

        layout.addWidget(QLabel("Spending by Category"))

        self._category_chart = SimpleBarChart()
        layout.addWidget(self._category_chart)

        layout.addWidget(_make_divider())
        layout.addWidget(QLabel("Monthly Trend"))

        self._trend_chart = SimpleBarChart()
        layout.addWidget(self._trend_chart)

        layout.addWidget(_make_divider())
        layout.addWidget(QLabel("Top Merchants"))

        self._merchant_chart = SimpleBarChart()
        layout.addWidget(self._merchant_chart)

        self._status_label = _make_muted_label("")
        layout.addWidget(self._status_label)
        layout.addStretch()

        scroll_area.setWidget(container)

        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(0, 0, 0, 0)
        outer_layout.addWidget(scroll_area)

    def _get_period(self) -> str:
        return self._period_combo.currentData() or "month"

    def refresh(self) -> None:
        self._status_label.setText("Loading analytics...")
        period = self._get_period()
        worker = make_summary_worker(period)
        worker.signals.result.connect(self._on_summary_loaded)
        worker.signals.error.connect(self._on_error)
        POOL.start(worker)

    @Slot(object)
    def _on_summary_loaded(self, data: Any) -> None:
        self._status_label.setText("")
        if not isinstance(data, dict):
            return

        total    = float(data.get("total_spend") or 0)
        count    = int(data.get("receipt_count") or 0)
        avg      = float(data.get("average_spend") or 0)
        top_cat  = data.get("top_category") or "—"

        currency = "LKR"
        self._kpi_total.set_value(f"{currency} {total:,.2f}")
        self._kpi_count.set_value(str(count))
        self._kpi_avg.set_value(f"{currency} {avg:,.2f}")
        self._kpi_top_cat.set_value(str(top_cat))

        breakdown = data.get("category_breakdown") or []
        self._category_chart.set_data(breakdown, value_key="amount", label_key="category")

        trend = data.get("monthly_trend") or []
        self._trend_chart.set_data(trend, value_key="amount", label_key="period")

        merchants = data.get("top_merchants") or []
        self._merchant_chart.set_data(merchants, value_key="amount", label_key="merchant")

    @Slot(str)
    def _on_error(self, message: str) -> None:
        self._status_label.setText(f"Error loading analytics: {message}")


# ──────────────────────────────────────────────────────────────────────────────
# InsightsView
# ──────────────────────────────────────────────────────────────────────────────


class InsightCard(QFrame):
    TYPE_COLORS = {
        "trend":   ("#1e3a5f", "#60a5fa"),
        "alert":   ("#3b1f1f", "#f87171"),
        "tip":     ("#1a2e1a", "#4ade80"),
        "anomaly": ("#3b2a10", "#fb923c"),
    }
    DEFAULT_COLORS = ("#1f2330", "#9ca3af")

    def __init__(self, insight: dict, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("card")
        insight_type = insight.get("type", "tip")
        bg, accent = self.TYPE_COLORS.get(insight_type, self.DEFAULT_COLORS)

        self.setStyleSheet(
            f"QFrame#card {{ background-color: {bg}; border: 1px solid {accent}33;"
            f" border-radius: 10px; padding: 14px; }}"
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(6)

        header = QHBoxLayout()
        type_badge = QLabel(insight_type.upper())
        type_badge.setStyleSheet(
            f"color: {accent}; font-size: 10px; font-weight: 600;"
            " background: transparent; letter-spacing: 0.5px;"
        )
        header.addWidget(type_badge)

        category = insight.get("category")
        if category:
            cat_label = QLabel(category)
            cat_label.setStyleSheet("color: #6b7280; font-size: 11px; background: transparent;")
            header.addWidget(cat_label)

        header.addStretch()

        amount = insight.get("amount")
        if amount is not None:
            try:
                amount_label = QLabel(f"{float(amount):,.2f}")
                amount_label.setStyleSheet(
                    f"color: {accent}; font-size: 13px; font-weight: 600; background: transparent;"
                )
                header.addWidget(amount_label)
            except (TypeError, ValueError):
                pass

        layout.addLayout(header)

        title = QLabel(insight.get("title", "Insight"))
        title.setStyleSheet(
            "color: #ffffff; font-size: 14px; font-weight: 600; background: transparent;"
        )
        title.setWordWrap(True)
        layout.addWidget(title)

        message = QLabel(insight.get("message", ""))
        message.setStyleSheet("color: #d1d5db; font-size: 13px; background: transparent;")
        message.setWordWrap(True)
        layout.addWidget(message)


class InsightsView(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._build_ui()

    def _build_ui(self) -> None:
        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(28, 28, 28, 28)
        outer_layout.setSpacing(14)

        header_row = QHBoxLayout()
        header_row.addWidget(_make_section_title("Spending Insights"))
        header_row.addStretch()

        self._refresh_btn = QPushButton("Refresh")
        self._refresh_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._refresh_btn.clicked.connect(self.refresh)
        header_row.addWidget(self._refresh_btn)
        outer_layout.addLayout(header_row)

        outer_layout.addWidget(
            _make_muted_label("AI-generated insights based on your spending patterns.")
        )

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: none; }")
        outer_layout.addWidget(scroll)

        self._content_widget = QWidget()
        self._content_layout = QVBoxLayout(self._content_widget)
        self._content_layout.setContentsMargins(0, 0, 0, 0)
        self._content_layout.setSpacing(10)
        scroll.setWidget(self._content_widget)

        self._status_label = _make_muted_label("")
        outer_layout.addWidget(self._status_label)

    def refresh(self) -> None:
        self._refresh_btn.setEnabled(False)
        self._status_label.setText("Generating insights...")
        self._clear_cards()

        worker = make_auto_insights_worker()
        worker.signals.result.connect(self._on_insights_loaded)
        worker.signals.error.connect(self._on_error)
        POOL.start(worker)

    def _clear_cards(self) -> None:
        while self._content_layout.count():
            child = self._content_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

    @Slot(object)
    def _on_insights_loaded(self, data: Any) -> None:
        self._refresh_btn.setEnabled(True)
        self._status_label.setText("")
        self._clear_cards()

        if not data:
            empty = _make_muted_label("No insights available yet. Upload more receipts to get started.")
            empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
            empty.setStyleSheet("color: #6b7280; font-size: 13px; padding: 40px;")
            self._content_layout.addWidget(empty)
            return

        insights = data if isinstance(data, list) else []
        for insight in insights:
            if isinstance(insight, dict):
                card = InsightCard(insight)
                self._content_layout.addWidget(card)

        self._content_layout.addStretch()

    @Slot(str)
    def _on_error(self, message: str) -> None:
        self._refresh_btn.setEnabled(True)
        self._clear_cards()
        error_label = QLabel(f"Could not load insights: {message}")
        error_label.setStyleSheet("color: #f87171; font-size: 13px; padding: 20px;")
        error_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        error_label.setWordWrap(True)
        self._content_layout.addWidget(error_label)
        self._status_label.setText("")


# ──────────────────────────────────────────────────────────────────────────────
# AskView
# ──────────────────────────────────────────────────────────────────────────────


SUGGESTED_QUESTIONS = [
    "Where am I spending the most?",
    "How can I reduce my food expenses?",
    "Do I have any unusual spending?",
    "What is my average receipt amount?",
    "Which category grew the most this month?",
]


class _ChatBubble(QFrame):
    def __init__(self, text: str, is_user: bool, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        if is_user:
            bg      = "#1e3a5f"
            color   = "#e2e2e2"
            align   = Qt.AlignmentFlag.AlignRight
        else:
            bg      = "#1f2330"
            color   = "#d1d5db"
            align   = Qt.AlignmentFlag.AlignLeft

        self.setStyleSheet(
            f"QFrame {{ background-color: {bg}; border-radius: 10px; padding: 2px; }}"
        )
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)

        outer = QHBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        if is_user:
            outer.addStretch()

        label = QLabel(text)
        label.setWordWrap(True)
        label.setTextFormat(Qt.TextFormat.PlainText)
        label.setStyleSheet(
            f"color: {color}; font-size: 13px; background: transparent;"
            " padding: 10px 14px; border: none;"
        )
        label.setMaximumWidth(560)
        outer.addWidget(label)

        if not is_user:
            outer.addStretch()


class AskView(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 28, 28, 28)
        layout.setSpacing(14)

        layout.addWidget(_make_section_title("Ask AI"))
        layout.addWidget(_make_muted_label("Ask questions about your spending and get grounded advice."))

        suggested_label = _make_muted_label("Suggested questions")
        layout.addWidget(suggested_label)

        suggestions_row = QHBoxLayout()
        suggestions_row.setSpacing(8)
        for question in SUGGESTED_QUESTIONS:
            btn = QPushButton(question)
            btn.setStyleSheet(
                "QPushButton { background-color: #1a1d27; border: 1px solid #2d3041;"
                " border-radius: 16px; padding: 6px 14px; font-size: 12px; color: #9ca3af; }"
                "QPushButton:hover { border-color: #3b82f6; color: #60a5fa; }"
            )
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
            btn.clicked.connect(lambda checked, q=question: self._ask(q))
            suggestions_row.addWidget(btn)

        suggestions_row.addStretch()
        layout.addLayout(suggestions_row)

        layout.addWidget(_make_divider())

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")
        layout.addWidget(scroll, stretch=1)

        self._chat_container = QWidget()
        self._chat_container.setStyleSheet("background: transparent;")
        self._chat_layout = QVBoxLayout(self._chat_container)
        self._chat_layout.setContentsMargins(0, 0, 0, 0)
        self._chat_layout.setSpacing(10)
        self._chat_layout.addStretch()
        scroll.setWidget(self._chat_container)
        self._scroll = scroll

        input_row = QHBoxLayout()
        input_row.setSpacing(10)

        self._input = QLineEdit()
        self._input.setPlaceholderText("Type a question about your spending...")
        self._input.setMinimumHeight(42)
        self._input.returnPressed.connect(self._on_send)
        input_row.addWidget(self._input)

        self._send_btn = _make_primary_button("Send")
        self._send_btn.setFixedWidth(90)
        self._send_btn.setMinimumHeight(42)
        self._send_btn.clicked.connect(self._on_send)
        input_row.addWidget(self._send_btn)
        layout.addLayout(input_row)

    def _ask(self, question: str) -> None:
        self._input.setText(question)
        self._on_send()

    @Slot()
    def _on_send(self) -> None:
        question = self._input.text().strip()
        if not question:
            return

        self._input.clear()
        self._send_btn.setEnabled(False)
        self._add_bubble(question, is_user=True)

        thinking = _ChatBubble("Thinking...", is_user=False)
        self._chat_layout.addWidget(thinking)
        self._thinking_bubble = thinking
        self._scroll_to_bottom()

        worker = make_ask_advisor_worker(question)
        worker.signals.result.connect(self._on_answer)
        worker.signals.error.connect(self._on_ask_error)
        POOL.start(worker)

    def _add_bubble(self, text: str, is_user: bool) -> None:
        stretch_item = self._chat_layout.itemAt(self._chat_layout.count() - 1)
        if stretch_item and stretch_item.spacerItem():
            self._chat_layout.removeItem(stretch_item)

        bubble = _ChatBubble(text, is_user=is_user)
        self._chat_layout.addWidget(bubble)
        self._chat_layout.addStretch()

    def _remove_thinking_bubble(self) -> None:
        if hasattr(self, "_thinking_bubble") and self._thinking_bubble:
            self._thinking_bubble.deleteLater()
            self._thinking_bubble = None

    @Slot(object)
    def _on_answer(self, data: Any) -> None:
        self._send_btn.setEnabled(True)
        self._remove_thinking_bubble()

        if isinstance(data, dict):
            answer = data.get("answer") or "No answer was returned."
        elif isinstance(data, str):
            answer = data
        else:
            answer = "Received an unexpected response format."

        self._add_bubble(answer, is_user=False)
        self._scroll_to_bottom()

    @Slot(str)
    def _on_ask_error(self, message: str) -> None:
        self._send_btn.setEnabled(True)
        self._remove_thinking_bubble()
        self._add_bubble(f"Error: {message}", is_user=False)
        self._scroll_to_bottom()

    def _scroll_to_bottom(self) -> None:
        from PySide6.QtCore import QTimer
        QTimer.singleShot(50, lambda: self._scroll.verticalScrollBar().setValue(
            self._scroll.verticalScrollBar().maximum()
        ))