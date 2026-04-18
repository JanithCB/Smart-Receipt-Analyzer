# src/desktop/views.py

from asyncio import timeout
import logging
import math
from pathlib import Path
from typing import Any
from desktop.api_client import api as _api


from PySide6.QtCore import (
    QMimeData,
    QSize,
    Qt,
    QThreadPool,
    QTimer,
    QUrl,
    Signal,
    Slot,
)
from PySide6.QtGui import (
    QBrush,
    QColor,
    QDragEnterEvent,
    QDropEvent,
    QFont,
    QPainter,
    QPainterPath,
    QPen,
)
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QProgressBar,
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
)

from desktop.workers import (
    ApiWorker,
    UploadWorker,
    make_analytics_worker,
    make_ask_advisor_worker,
    make_auto_insights_worker,
    make_correct_category_worker,
    make_delete_receipt_worker,
    make_get_receipt_worker,
    make_insights_worker,
    make_list_receipts_worker,
    make_login_worker,
    make_register_worker,
    make_reprocess_receipt_worker,
    make_summary_worker,
    make_update_receipt_worker,
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
    ("This Week", "week"),
    ("This Month", "month"),
    ("This Year", "year"),
    ("All Time", "all"),
]

CATEGORY_COLORS: dict[str, str] = {
    "Groceries": "#34d399",
    "Dining": "#f97316",
    "Transport": "#60a5fa",
    "Utilities": "#a78bfa",
    "Healthcare": "#f472b6",
    "Shopping": "#facc15",
    "Entertainment": "#fb7185",
    "Education": "#38bdf8",
    "Travel": "#4ade80",
    "Finance": "#e879f9",
    "Other": "#94a3b8",
}


def _category_color(category: str) -> str:
    return CATEGORY_COLORS.get(category, "#6b7280")


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
    def __init__(self, title: str, accent: str = "#60a5fa", parent: QWidget | None = None) -> None:
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
        self._value.setStyleSheet(f"color: {accent}; font-size: 22px; font-weight: 700;")

        layout.addWidget(self._title)
        layout.addWidget(self._value)

    def set_value(self, value: str) -> None:
        self._value.setText(value)


class PieChartWidget(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._data: list[dict] = []
        self.setMinimumSize(260, 260)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

    def set_data(self, data: list[dict]) -> None:
        self._data = [d for d in data if float(d.get("amount", 0) or 0) > 0]
        self.update()

    def paintEvent(self, event: Any) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        w = self.width()
        h = self.height()
        side = min(w, h) - 20
        cx = w // 2
        cy = h // 2
        r_outer = side // 2
        r_inner = int(r_outer * 0.52)

        if not self._data:
            painter.setPen(QColor("#4b5563"))
            painter.drawText(0, 0, w, h, Qt.AlignmentFlag.AlignCenter, "No data")
            return

        total = sum(float(d.get("amount", 0) or 0) for d in self._data)
        if total == 0:
            return

        start_angle = 90 * 16

        for item in self._data:
            amount = float(item.get("amount", 0) or 0)
            span = int((amount / total) * 360 * 16)
            color = QColor(_category_color(item.get("category", "Other")))

            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(color))
            painter.drawPie(cx - r_outer, cy - r_outer, r_outer * 2, r_outer * 2, start_angle, span)
            start_angle += span

        painter.setBrush(QBrush(QColor("#14161f")))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(cx - r_inner, cy - r_inner, r_inner * 2, r_inner * 2)

        painter.setPen(QColor("#ffffff"))
        font = painter.font()
        font.setPointSize(10)
        font.setBold(True)
        painter.setFont(font)
        painter.drawText(
            cx - r_inner,
            cy - 12,
            r_inner * 2,
            24,
            Qt.AlignmentFlag.AlignCenter,
            "TOTAL",
        )

        font.setPointSize(9)
        font.setBold(False)
        painter.setFont(font)
        painter.setPen(QColor("#9ca3af"))
        total_text = f"{total:,.0f}"
        painter.drawText(
            cx - r_inner,
            cy + 2,
            r_inner * 2,
            20,
            Qt.AlignmentFlag.AlignCenter,
            total_text,
        )


class PieLegend(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(8, 8, 8, 8)
        self._layout.setSpacing(5)

    def set_data(self, data: list[dict]) -> None:
        while self._layout.count():
            child = self._layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

        for item in data[:10]:
            cat = item.get("category", "Other")
            amount = float(item.get("amount", 0) or 0)
            pct = float(item.get("percentage", 0) or 0)
            color = _category_color(cat)

            row = QHBoxLayout()
            row.setSpacing(8)

            dot = QFrame()
            dot.setFixedSize(12, 12)
            dot.setStyleSheet(f"background-color: {color}; border-radius: 6px;")
            row.addWidget(dot)

            name_lbl = QLabel(cat)
            name_lbl.setStyleSheet("color: #d1d5db; font-size: 12px;")
            name_lbl.setMinimumWidth(90)
            row.addWidget(name_lbl)

            row.addStretch()

            pct_lbl = QLabel(f"{pct:.1f}%")
            pct_lbl.setStyleSheet(f"color: {color}; font-size: 12px; font-weight: 600;")
            pct_lbl.setAlignment(Qt.AlignmentFlag.AlignRight)
            row.addWidget(pct_lbl)

            amt_lbl = QLabel(f"{amount:,.0f}")
            amt_lbl.setStyleSheet("color: #6b7280; font-size: 11px;")
            amt_lbl.setAlignment(Qt.AlignmentFlag.AlignRight)
            amt_lbl.setMinimumWidth(70)
            row.addWidget(amt_lbl)

            container = QWidget()
            container.setLayout(row)
            self._layout.addWidget(container)

        self._layout.addStretch()


class BarChartWidget(QWidget):
    def __init__(
        self,
        accent_color: str = "#3b82f6",
        use_category_colors: bool = False,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._items: list[dict] = []
        self._value_key = "amount"
        self._label_key = "category"
        self._accent = accent_color
        self._use_category_colors = use_category_colors
        self.setMinimumHeight(200)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

    def set_data(
        self,
        items: list[dict],
        value_key: str = "amount",
        label_key: str = "category",
    ) -> None:
        self._items = items[:12]
        self._value_key = value_key
        self._label_key = label_key
        self.update()

    def paintEvent(self, event: Any) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        w = self.width()
        h = self.height()

        pad_left = 58
        pad_right = 12
        pad_top = 16
        pad_bottom = 46

        chart_w = w - pad_left - pad_right
        chart_h = h - pad_top - pad_bottom

        if not self._items:
            painter.setPen(QColor("#4b5563"))
            painter.drawText(0, 0, w, h, Qt.AlignmentFlag.AlignCenter, "No data")
            return

        values = [float(item.get(self._value_key, 0) or 0) for item in self._items]
        max_val = max(values) if values else 1
        if max_val == 0:
            max_val = 1

        grid_steps = 4
        painter.setPen(QPen(QColor("#242630"), 1))
        font = painter.font()
        font.setPointSize(8)
        painter.setFont(font)

        for i in range(grid_steps + 1):
            y = pad_top + chart_h - int((i / grid_steps) * chart_h)
            painter.setPen(QPen(QColor("#242630"), 1))
            painter.drawLine(pad_left, y, pad_left + chart_w, y)

            grid_val = (max_val / grid_steps) * i
            painter.setPen(QColor("#6b7280"))
            label = f"{grid_val:,.0f}" if grid_val < 10000 else f"{grid_val / 1000:.0f}k"
            painter.drawText(
                0,
                y - 8,
                pad_left - 4,
                16,
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                label,
            )

        n = len(self._items)
        group_w = chart_w / n
        bar_w = max(8, int(group_w * 0.55))

        for i, item in enumerate(self._items):
            val = float(item.get(self._value_key, 0) or 0)
            bar_h = int((val / max_val) * chart_h)
            x = pad_left + int(i * group_w + (group_w - bar_w) / 2)
            y = pad_top + chart_h - bar_h

            if self._use_category_colors:
                color = QColor(_category_color(item.get(self._label_key, "Other")))
            else:
                color = QColor(self._accent)

            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(color))
            radius = min(4, bar_w // 3)
            rect_path = QPainterPath()
            rect_path.addRoundedRect(x, y, bar_w, bar_h, radius, radius)
            painter.drawPath(rect_path)

            if bar_h > 14:
                painter.setPen(QColor("#9ca3af"))
                val_font = painter.font()
                val_font.setPointSize(7)
                painter.setFont(val_font)
                val_text = f"{val:,.0f}" if val < 10000 else f"{val / 1000:.1f}k"
                painter.drawText(x - 4, y - 14, bar_w + 8, 12, Qt.AlignmentFlag.AlignHCenter, val_text)

            label_text = str(item.get(self._label_key, ""))[:10]
            painter.setPen(QColor("#6b7280"))
            lbl_font = painter.font()
            lbl_font.setPointSize(8)
            painter.setFont(lbl_font)
            painter.drawText(
                x - 10,
                pad_top + chart_h + 6,
                bar_w + 20,
                36,
                Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop,
                label_text,
            )


class SimpleBarChart(QWidget):
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
            color = _category_color(item.get(label_key, "Other")) if label_key == "category" else "#2563eb"

            col = QWidget()
            col_layout = QVBoxLayout(col)
            col_layout.setContentsMargins(0, 0, 0, 0)
            col_layout.setSpacing(4)
            col_layout.setAlignment(Qt.AlignmentFlag.AlignBottom | Qt.AlignmentFlag.AlignHCenter)

            bar = QFrame()
            bar.setFixedWidth(28)
            bar.setFixedHeight(bar_height)
            bar.setStyleSheet(f"background-color: {color}; border-radius: 4px;")

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


class LoginView(QWidget):
    login_success = Signal(dict)
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
        email = self._email.text().strip()
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


class RegisterView(QWidget):
    register_success = Signal(dict)
    switch_to_login = Signal()

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
        username = self._username.text().strip()
        email = self._email.text().strip()
        password = self._password.text()
        confirm = self._confirm.text()
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
    POLL_INTERVAL_MS = 2500
    POLL_MAX_ATTEMPTS = 20

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._queued_files: list[Path] = []
        self._polling: dict[int, dict[str, Any]] = {}
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
        for raw_path in paths:
            path = Path(raw_path)
            if path.suffix.lower() not in self.ALLOWED_EXTENSIONS:
                self._add_status_row(path.name, "Skipped — unsupported type", "#f87171")
                continue
            if path not in self._queued_files:
                self._queued_files.append(path)
                self._add_status_row(path.name, "Queued", "#6b7280")

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
                widget = item.widget()
                if widget.property("filename") == filename:
                    widget.setText(f"  {filename}  —  {status_text}")
                    widget.setStyleSheet(f"color: {color}; font-size: 12px; padding: 2px 0;")
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
        receipt_id = receipt.get("id") if isinstance(receipt, dict) else None

        if receipt_id is None:
            self._update_status_row(filename, "Uploaded ✓", "#4ade80")
            self.upload_complete.emit()
            return

        self._update_status_row(filename, "Processing…", "#facc15")

        timer = QTimer(self)
        timer.setSingleShot(False)
        self._polling[receipt_id] = {
            "filename": filename,
            "attempts": 0,
            "timer": timer,
            "in_flight": False,
        }

        timer.timeout.connect(lambda rid=receipt_id: self._poll_receipt(rid))
        timer.start(self.POLL_INTERVAL_MS)

    def _poll_receipt(self, receipt_id: int) -> None:
        poll_info = self._polling.get(receipt_id)
        if poll_info is None:
            return

        if poll_info.get("in_flight"):
            return

        poll_info["attempts"] += 1
        if poll_info["attempts"] > self.POLL_MAX_ATTEMPTS:
            self._stop_polling(receipt_id, timeout=True)
            return

        poll_info["in_flight"] = True

        worker = make_get_receipt_worker(receipt_id)
        worker.signals.result.connect(lambda data, rid=receipt_id: self._on_poll_result(rid, data))
        worker.signals.error.connect(lambda _err, rid=receipt_id: self._on_poll_error(rid))
        POOL.start(worker)

    @Slot(int, object)
    def _on_poll_result(self, receipt_id: int, data: Any) -> None:
        poll_info = self._polling.get(receipt_id)
        if poll_info is None:
            return

        poll_info["in_flight"] = False

        if not isinstance(data, dict):
            return

        status = (data.get("processing_status") or "").lower()
        filename = poll_info["filename"]

        if status == "done":
            merchant = data.get("merchant") or "Unknown merchant"
            amount = data.get("total_amount")
            amount_str = f"{float(amount):,.2f}" if amount is not None else "—"
            currency = data.get("currency") or "LKR"
            self._update_status_row(
                filename,
                f"Done ✓  {merchant}  {currency} {amount_str}",
                "#4ade80",
            )
            self._stop_polling(receipt_id)
            self.upload_complete.emit()
        elif status == "failed":
            self._update_status_row(filename, "Processing failed", "#f87171")
            self._stop_polling(receipt_id)
            self.upload_complete.emit()

    def _on_poll_error(self, receipt_id: int) -> None:
        poll_info = self._polling.get(receipt_id)
        if poll_info is not None:
            poll_info["in_flight"] = False

    def _stop_polling(self, receipt_id: int, timeout: bool = False) -> None:
        poll_info = self._polling.pop(receipt_id, None)
        if not poll_info:
            return

        timer = poll_info.get("timer")
        if timer is not None:
            timer.stop()
            timer.deleteLater()

        poll_info["in_flight"] = False

        if timeout:
            self._update_status_row(
                poll_info["filename"],
                "Uploaded (processing taking longer than expected)",
                "#fb923c",
            )
        self.upload_complete.emit()


def stop_all_polling(self) -> None:
    """Stop every active receipt polling timer.

    Call this on logout so that background QTimers do not continue making
    authenticated API calls after the JWT token has been cleared.
    """
    # Iterate over a snapshot because _stop_polling mutates self._polling
    for receipt_id in list(self._polling.keys()):
        self._stop_polling(receipt_id)

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
            "merchant": self._merchant.text().strip() or None,
            "total_amount": self._amount.value(),
            "currency": self._currency.currentText(),
            "category": self._category.currentText(),
            "notes": self._notes.toPlainText().strip() or None,
        }


class ReceiptsView(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._current_page = 1
        self._total_pages = 1
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
        total = payload.get("total", 0)
        page = payload.get("page", 1)
        pages = payload.get("pages") or payload.get("total_pages", 1)

        if isinstance(payload.get("pagination"), dict):
            pag = payload["pagination"]
            total = pag.get("total_items", total)
            page = pag.get("page", page)
            pages = pag.get("total_pages", pages)

        self._receipts_cache = receipts
        self._current_page = page
        self._total_pages = max(1, pages)

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

            cat = receipt.get("category") or "—"
            cat_item = QTableWidgetItem(cat)
            cat_item.setForeground(QColor(_category_color(cat)))
            self._table.setItem(row, 4, cat_item)

            proc_status = receipt.get("processing_status") or "—"
            status_item = QTableWidgetItem(proc_status)
            if proc_status == "done":
                status_item.setForeground(QColor("#4ade80"))
            elif proc_status == "failed":
                status_item.setForeground(QColor("#f87171"))
            elif proc_status in ("pending", "processing"):
                status_item.setForeground(QColor("#facc15"))
            self._table.setItem(row, 5, status_item)

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
# AnalyticsView — BUG 3 FIX: shows pending_count warning + proper charts
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

        self._pending_banner = QLabel("")
        self._pending_banner.setStyleSheet(
            "background-color: #2d2000; border: 1px solid #b45309; border-radius: 8px;"
            " color: #fcd34d; font-size: 12px; padding: 8px 14px;"
        )
        self._pending_banner.setWordWrap(True)
        self._pending_banner.hide()
        layout.addWidget(self._pending_banner)

        kpi_row = QHBoxLayout()
        kpi_row.setSpacing(12)
        self._kpi_total = KpiCard("Total Spend", accent="#34d399")
        self._kpi_count = KpiCard("Receipts", accent="#60a5fa")
        self._kpi_avg = KpiCard("Avg Amount", accent="#a78bfa")
        self._kpi_top_cat = KpiCard("Top Category", accent="#f97316")
        for kpi in (self._kpi_total, self._kpi_count, self._kpi_avg, self._kpi_top_cat):
            kpi_row.addWidget(kpi)
        layout.addLayout(kpi_row)

        layout.addWidget(_make_divider())

        cat_title = QLabel("Spending by Category")
        cat_title.setStyleSheet("font-size: 15px; font-weight: 600; color: #e5e7eb;")
        layout.addWidget(cat_title)

        cat_row = QHBoxLayout()
        cat_row.setSpacing(24)

        self._pie_chart = PieChartWidget()
        self._pie_chart.setFixedSize(260, 260)
        cat_row.addWidget(self._pie_chart)

        self._pie_legend = PieLegend()
        self._pie_legend.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        cat_row.addWidget(self._pie_legend)

        layout.addLayout(cat_row)

        layout.addWidget(_make_divider())

        trend_title = QLabel("Monthly Spend Trend")
        trend_title.setStyleSheet("font-size: 15px; font-weight: 600; color: #e5e7eb;")
        layout.addWidget(trend_title)

        self._trend_chart = BarChartWidget(accent_color="#60a5fa", use_category_colors=False)
        self._trend_chart.setMinimumHeight(220)
        layout.addWidget(self._trend_chart)

        layout.addWidget(_make_divider())

        merch_title = QLabel("Top Merchants")
        merch_title.setStyleSheet("font-size: 15px; font-weight: 600; color: #e5e7eb;")
        layout.addWidget(merch_title)

        self._merchant_chart = BarChartWidget(accent_color="#a78bfa", use_category_colors=False)
        self._merchant_chart.setMinimumHeight(220)
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
            self._status_label.setText("Unexpected analytics response.")
            return

        total = float(data.get("total_spend") or 0)
        count = int(data.get("receipt_count") or 0)
        avg = float(data.get("average_spend") or 0)
        top_cat = data.get("top_category") or "—"

        pending_count = int(data.get("pending_count") or 0)
        if pending_count > 0:
            s = "s" if pending_count != 1 else ""
            self._pending_banner.setText(
                f"⏳  {pending_count} receipt{s} still processing — "
                f"totals will update automatically once OCR finishes."
            )
            self._pending_banner.show()
        else:
            self._pending_banner.hide()

        currency = (
            data.get("currency")
            or data.get("base_currency")
            or data.get("display_currency")
            or "LKR"
        )

        self._kpi_total.set_value(f"{currency} {total:,.2f}")
        self._kpi_count.set_value(str(count))
        self._kpi_avg.set_value(f"{currency} {avg:,.2f}")
        self._kpi_top_cat.set_value(str(top_cat))

        breakdown = data.get("category_breakdown") or []
        self._pie_chart.set_data(breakdown)
        self._pie_legend.set_data(breakdown)

        trend = data.get("monthly_trend") or []
        self._trend_chart.set_data(trend, value_key="amount", label_key="period")

        merchants = data.get("top_merchants") or []
        self._merchant_chart.set_data(merchants, value_key="amount", label_key="merchant")

    @Slot(str)
    def _on_error(self, message: str) -> None:
        self._pending_banner.hide()
        self._status_label.setText(f"Error loading analytics: {message}")


# ──────────────────────────────────────────────────────────────────────────────
# InsightsView
# ──────────────────────────────────────────────────────────────────────────────


class InsightCard(QFrame):
    TYPE_COLORS = {
        "trend": ("#1e3a5f", "#60a5fa"),
        "alert": ("#3b1f1f", "#f87171"),
        "tip": ("#1a2e1a", "#4ade80"),
        "anomaly": ("#3b2a10", "#fb923c"),
    }
    DEFAULT_COLORS = ("#1f2330", "#9ca3af")

    def __init__(self, insight: dict, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("card")
        insight_type = str(insight.get("type", "tip")).lower()
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
            cat_label = QLabel(str(category))
            cat_label.setStyleSheet(
                f"color: {_category_color(str(category))}; font-size: 11px; background: transparent;"
            )
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

        title = QLabel(str(insight.get("title", "Insight")))
        title.setStyleSheet(
            "color: #ffffff; font-size: 14px; font-weight: 600; background: transparent;"
        )
        title.setWordWrap(True)
        layout.addWidget(title)

        message = QLabel(str(insight.get("message", "")))
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

        insights = data if isinstance(data, list) else []

        if not insights:
            empty = _make_muted_label("No insights available yet. Upload more receipts to get started.")
            empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
            empty.setStyleSheet("color: #6b7280; font-size: 13px; padding: 40px;")
            self._content_layout.addWidget(empty)
            return

        for insight in insights:
            if isinstance(insight, dict):
                self._content_layout.addWidget(InsightCard(insight))

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
            bg = "#1e3a5f"
            color = "#e2e8f0"
        else:
            bg = "#1f2330"
            color = "#d1d5db"

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
        self._thinking_bubble: _ChatBubble | None = None
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 28, 28, 28)
        layout.setSpacing(14)

        header_row = QHBoxLayout()
        header_row.addWidget(_make_section_title("Ask AI"))
        header_row.addStretch()

        self._period_combo = QComboBox()
        for label, value in PERIOD_OPTIONS:
            self._period_combo.addItem(label, userData=value)
        self._period_combo.setCurrentIndex(1)
        self._period_combo.setMinimumHeight(34)
        header_row.addWidget(self._period_combo)

        layout.addLayout(header_row)
        layout.addWidget(_make_muted_label("Ask questions about your spending and get grounded advice."))

        suggested_label = _make_muted_label("Suggested questions")
        layout.addWidget(suggested_label)

        suggestions_wrap = QWidget()
        suggestions_layout = QHBoxLayout(suggestions_wrap)
        suggestions_layout.setContentsMargins(0, 0, 0, 0)
        suggestions_layout.setSpacing(8)

        for question in SUGGESTED_QUESTIONS:
            btn = QPushButton(question)
            btn.setStyleSheet(
                "QPushButton { background-color: #1a1d27; border: 1px solid #2d3041;"
                " border-radius: 16px; padding: 6px 14px; font-size: 12px; color: #9ca3af; }"
                "QPushButton:hover { border-color: #3b82f6; color: #60a5fa; }"
            )
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
            btn.clicked.connect(lambda _checked=False, q=question: self._ask(q))
            suggestions_layout.addWidget(btn)

        suggestions_layout.addStretch()
        layout.addWidget(suggestions_wrap)

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

        self._status_label = _make_muted_label("")
        layout.addWidget(self._status_label)

    def _get_period(self) -> str:
        return self._period_combo.currentData() or "month"

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
        self._status_label.setText("")

        self._add_bubble(question, is_user=True)

        thinking = _ChatBubble("Thinking...", is_user=False)
        self._insert_chat_widget(thinking)
        self._thinking_bubble = thinking
        self._scroll_to_bottom()

        period = self._get_period()
        worker = make_ask_advisor_worker(question, period=period)
        worker.signals.result.connect(self._on_answer)
        worker.signals.error.connect(self._on_ask_error)
        POOL.start(worker)

    def _insert_chat_widget(self, widget: QWidget) -> None:
        stretch_item = self._chat_layout.itemAt(self._chat_layout.count() - 1)
        if stretch_item and stretch_item.spacerItem():
            self._chat_layout.removeItem(stretch_item)
        self._chat_layout.addWidget(widget)
        self._chat_layout.addStretch()

    def _add_bubble(self, text: str, is_user: bool) -> None:
        self._insert_chat_widget(_ChatBubble(text, is_user=is_user))

    def _remove_thinking_bubble(self) -> None:
        if self._thinking_bubble is not None:
            self._chat_layout.removeWidget(self._thinking_bubble)
            self._thinking_bubble.deleteLater()
            self._thinking_bubble = None

    @Slot(object)
    def _on_answer(self, data: Any) -> None:
        self._send_btn.setEnabled(True)
        self._remove_thinking_bubble()

        if isinstance(data, dict):
            answer = data.get("answer") or data.get("message") or "No answer was returned."
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
        self._status_label.setText("")
        self._scroll_to_bottom()

    def _scroll_to_bottom(self) -> None:
        QTimer.singleShot(
            50,
            lambda: self._scroll.verticalScrollBar().setValue(
                self._scroll.verticalScrollBar().maximum()
            ),
        )


# ──────────────────────────────────────────────────────────────────────────────
# Main application shell
# ──────────────────────────────────────────────────────────────────────────────


class MainView(QWidget):
    logout_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._build_ui()

    def _build_ui(self) -> None:
        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        sidebar = QFrame()
        sidebar.setFixedWidth(220)
        sidebar.setStyleSheet(
            "QFrame { background-color: #11131a; border-right: 1px solid #242630; }"
        )
        side_layout = QVBoxLayout(sidebar)
        side_layout.setContentsMargins(18, 22, 18, 18)
        side_layout.setSpacing(10)

        brand = QLabel("Vispend AI")
        brand.setStyleSheet("font-size: 20px; font-weight: 700; color: #ffffff;")
        side_layout.addWidget(brand)

        subtitle = QLabel("Smart receipt manager")
        subtitle.setStyleSheet("font-size: 12px; color: #6b7280;")
        side_layout.addWidget(subtitle)
        side_layout.addSpacing(12)

        self._nav_buttons: dict[str, QPushButton] = {}
        nav_items = [
            ("upload", "Upload"),
            ("receipts", "Receipts"),
            ("analytics", "Analytics"),
            ("insights", "Insights"),
            ("ask", "Ask AI"),
        ]

        for key, label in nav_items:
            btn = QPushButton(label)
            btn.setCheckable(True)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setMinimumHeight(40)
            btn.setStyleSheet(
                "QPushButton { text-align: left; padding: 0 14px; border-radius: 8px; "
                "background-color: transparent; color: #cbd5e1; border: 1px solid transparent; }"
                "QPushButton:hover { background-color: #1a1d27; border-color: #2d3041; }"
                "QPushButton:checked { background-color: #1d3557; color: #ffffff; border-color: #3b82f6; }"
            )
            btn.clicked.connect(lambda _checked=False, name=key: self._set_page(name))
            side_layout.addWidget(btn)
            self._nav_buttons[key] = btn

        side_layout.addStretch()

        logout_btn = QPushButton("Sign out")
        logout_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        logout_btn.setMinimumHeight(38)
        logout_btn.setStyleSheet(
            "QPushButton { text-align: left; padding: 0 14px; border-radius: 8px; "
            "background-color: #2a1a1a; color: #fca5a5; border: 1px solid #7f1d1d; }"
            "QPushButton:hover { background-color: #3a1f1f; }"
        )
        logout_btn.clicked.connect(self.logout_requested.emit)
        side_layout.addWidget(logout_btn)

        root.addWidget(sidebar)

        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(0)

        self._stack = QStackedWidget()
        self.upload_view = UploadView()
        self.receipts_view = ReceiptsView()
        self.analytics_view = AnalyticsView()
        self.insights_view = InsightsView()
        self.ask_view = AskView()

        self._stack.addWidget(self.upload_view)
        self._stack.addWidget(self.receipts_view)
        self._stack.addWidget(self.analytics_view)
        self._stack.addWidget(self.insights_view)
        self._stack.addWidget(self.ask_view)

        content_layout.addWidget(self._stack)
        root.addWidget(content)

        self.upload_view.upload_complete.connect(self.receipts_view.refresh)
        self.upload_view.upload_complete.connect(self.analytics_view.refresh)
        self.upload_view.upload_complete.connect(self.insights_view.refresh)

        self._set_page("upload")

    def _set_page(self, name: str) -> None:
        page_map = {
            "upload": 0,
            "receipts": 1,
            "analytics": 2,
            "insights": 3,
            "ask": 4,
        }
        index = page_map.get(name, 0)
        self._stack.setCurrentIndex(index)

        for key, btn in self._nav_buttons.items():
            btn.setChecked(key == name)

        if name == "receipts":
            self.receipts_view.refresh()
        elif name == "analytics":
            self.analytics_view.refresh()
        elif name == "insights":
            self.insights_view.refresh()


# ──────────────────────────────────────────────────────────────────────────────
# Root app container
# ──────────────────────────────────────────────────────────────────────────────


class AppView(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._user_payload: dict[str, Any] | None = None
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self._stack = QStackedWidget()

        self.login_view = LoginView()
        self.register_view = RegisterView()
        self.main_view = MainView()

        self._stack.addWidget(self.login_view)
        self._stack.addWidget(self.register_view)
        self._stack.addWidget(self.main_view)

        layout.addWidget(self._stack)

        self.login_view.switch_to_register.connect(self._show_register)
        self.register_view.switch_to_login.connect(self._show_login)
        self.login_view.login_success.connect(self._on_auth_success)
        self.register_view.register_success.connect(self._on_auth_success)
        self.main_view.logout_requested.connect(self._logout)

        self._show_login()

    def _show_login(self) -> None:
        self._stack.setCurrentWidget(self.login_view)

    def _show_register(self) -> None:
        self._stack.setCurrentWidget(self.register_view)

    @Slot(object)
    def _on_auth_success(self, payload: Any) -> None:
        self._user_payload = payload if isinstance(payload, dict) else None
        self._stack.setCurrentWidget(self.main_view)
        self.main_view.receipts_view.refresh()
        self.main_view.analytics_view.refresh()
        self.main_view.insights_view.refresh()

    def _logout(self) -> None:
        _api.clear_token()
        self._user_payload = None
        self._show_login()


