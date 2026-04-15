# src/desktop/main.py

import logging
import sys
from pathlib import Path

src_dir = Path(__file__).resolve().parents[1]
if str(src_dir) not in sys.path:
    sys.path.insert(0, str(src_dir))

from PySide6.QtCore import Qt, Slot
from PySide6.QtGui import QFont, QFontDatabase, QIcon
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QSizePolicy,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from desktop.api_client import api
from desktop.views import (
    AnalyticsView,
    AskView,
    InsightsView,
    LoginView,
    RegisterView,
    ReceiptsView,
    UploadView,
)

logger = logging.getLogger(__name__)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
    datefmt="%H:%M:%S",
)

APP_STYLESHEET = """
/* ─── Global ─────────────────────────────────────────────── */
* {
    font-family: "Segoe UI", "Inter", "Helvetica Neue", Arial, sans-serif;
    font-size: 13px;
    color: #e2e2e2;
    outline: none;
}

QMainWindow, QWidget#central_widget {
    background-color: #111318;
}

/* ─── Sidebar ─────────────────────────────────────────────── */
QWidget#sidebar {
    background-color: #16181f;
    border-right: 1px solid #242630;
    min-width: 220px;
    max-width: 220px;
}

QLabel#app_title {
    font-size: 15px;
    font-weight: 600;
    color: #ffffff;
    padding: 0px 4px;
    letter-spacing: 0.5px;
}

QLabel#app_subtitle {
    font-size: 11px;
    color: #6b7280;
    padding: 0px 4px;
}

/* ─── Nav buttons ─────────────────────────────────────────── */
QPushButton#nav_btn {
    background-color: transparent;
    border: none;
    border-radius: 8px;
    padding: 10px 14px;
    text-align: left;
    color: #9ca3af;
    font-size: 13px;
    font-weight: 400;
}

QPushButton#nav_btn:hover {
    background-color: #1f2330;
    color: #e2e2e2;
}

QPushButton#nav_btn[active="true"] {
    background-color: #1e2a3a;
    color: #60a5fa;
    font-weight: 500;
}

QPushButton#nav_btn[active="true"]:hover {
    background-color: #1e2a3a;
}

/* ─── Logout button ───────────────────────────────────────── */
QPushButton#logout_btn {
    background-color: transparent;
    border: 1px solid #2d3041;
    border-radius: 8px;
    padding: 8px 14px;
    color: #6b7280;
    font-size: 12px;
    text-align: left;
}

QPushButton#logout_btn:hover {
    background-color: #2a1a1a;
    border-color: #7f1d1d;
    color: #fca5a5;
}

/* ─── Content area ────────────────────────────────────────── */
QWidget#content_area {
    background-color: #111318;
}

QStackedWidget {
    background-color: #111318;
    border: none;
}

/* ─── User info bar ───────────────────────────────────────── */
QLabel#user_label {
    font-size: 12px;
    color: #6b7280;
    padding: 2px 4px;
}

QFrame#sidebar_divider {
    background-color: #242630;
    min-height: 1px;
    max-height: 1px;
    border: none;
}

/* ─── Scrollbars ──────────────────────────────────────────── */
QScrollBar:vertical {
    background: #111318;
    width: 6px;
    margin: 0;
    border-radius: 3px;
}
QScrollBar::handle:vertical {
    background: #2d3041;
    border-radius: 3px;
    min-height: 30px;
}
QScrollBar::handle:vertical:hover {
    background: #3d4155;
}
QScrollBar::add-line:vertical,
QScrollBar::sub-line:vertical {
    height: 0;
    background: none;
}

QScrollBar:horizontal {
    background: #111318;
    height: 6px;
    border-radius: 3px;
}
QScrollBar::handle:horizontal {
    background: #2d3041;
    border-radius: 3px;
    min-width: 30px;
}
QScrollBar::handle:horizontal:hover {
    background: #3d4155;
}
QScrollBar::add-line:horizontal,
QScrollBar::sub-line:horizontal {
    width: 0;
    background: none;
}

/* ─── Inputs ──────────────────────────────────────────────── */
QLineEdit, QTextEdit, QPlainTextEdit {
    background-color: #1a1d27;
    border: 1px solid #2d3041;
    border-radius: 8px;
    padding: 8px 12px;
    color: #e2e2e2;
    selection-background-color: #1e3a5f;
}
QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus {
    border-color: #3b82f6;
    background-color: #1c2032;
}
QLineEdit::placeholder {
    color: #4b5563;
}

/* ─── Buttons (general) ───────────────────────────────────── */
QPushButton {
    background-color: #1f2330;
    border: 1px solid #2d3041;
    border-radius: 8px;
    padding: 8px 18px;
    color: #e2e2e2;
    font-size: 13px;
}
QPushButton:hover {
    background-color: #252b3d;
    border-color: #3b82f6;
}
QPushButton:pressed {
    background-color: #1a2035;
}
QPushButton:disabled {
    color: #4b5563;
    border-color: #1f2330;
    background-color: #16181f;
}

QPushButton#primary_btn {
    background-color: #2563eb;
    border: none;
    color: #ffffff;
    font-weight: 500;
}
QPushButton#primary_btn:hover {
    background-color: #1d4fd8;
}
QPushButton#primary_btn:pressed {
    background-color: #1e40af;
}
QPushButton#primary_btn:disabled {
    background-color: #1e2a4a;
    color: #6b7280;
}

/* ─── Tables ──────────────────────────────────────────────── */
QTableWidget {
    background-color: #16181f;
    border: 1px solid #242630;
    border-radius: 8px;
    gridline-color: #1f2330;
    alternate-background-color: #1a1d27;
}
QTableWidget::item {
    padding: 8px 10px;
    border: none;
    color: #d1d5db;
}
QTableWidget::item:selected {
    background-color: #1e3a5f;
    color: #ffffff;
}
QHeaderView::section {
    background-color: #1f2330;
    color: #9ca3af;
    font-size: 12px;
    font-weight: 500;
    padding: 8px 10px;
    border: none;
    border-bottom: 1px solid #2d3041;
}

/* ─── ComboBox ────────────────────────────────────────────── */
QComboBox {
    background-color: #1a1d27;
    border: 1px solid #2d3041;
    border-radius: 8px;
    padding: 7px 12px;
    color: #e2e2e2;
    min-width: 120px;
}
QComboBox:hover {
    border-color: #3b82f6;
}
QComboBox::drop-down {
    border: none;
    padding-right: 8px;
}
QComboBox QAbstractItemView {
    background-color: #1a1d27;
    border: 1px solid #2d3041;
    border-radius: 8px;
    color: #e2e2e2;
    selection-background-color: #1e3a5f;
    outline: none;
}

/* ─── Label variants ──────────────────────────────────────── */
QLabel {
    background: transparent;
    border: none;
}
QLabel#section_title {
    font-size: 16px;
    font-weight: 600;
    color: #ffffff;
    padding-bottom: 4px;
}
QLabel#muted {
    color: #6b7280;
    font-size: 12px;
}
QLabel#kpi_value {
    font-size: 22px;
    font-weight: 600;
    color: #ffffff;
}
QLabel#kpi_label {
    font-size: 11px;
    color: #6b7280;
    text-transform: uppercase;
    letter-spacing: 0.5px;
}

/* ─── Cards ───────────────────────────────────────────────── */
QFrame#card {
    background-color: #16181f;
    border: 1px solid #242630;
    border-radius: 12px;
    padding: 16px;
}

/* ─── Progress bar ────────────────────────────────────────── */
QProgressBar {
    background-color: #1f2330;
    border: 1px solid #2d3041;
    border-radius: 4px;
    height: 6px;
    text-align: center;
    color: transparent;
}
QProgressBar::chunk {
    background-color: #2563eb;
    border-radius: 4px;
}

/* ─── Tooltip ─────────────────────────────────────────────── */
QToolTip {
    background-color: #1a1d27;
    color: #e2e2e2;
    border: 1px solid #2d3041;
    border-radius: 6px;
    padding: 4px 8px;
    font-size: 12px;
}
"""


NAV_ITEMS = [
    ("Upload",     "UploadView"),
    ("Receipts",   "ReceiptsView"),
    ("Analytics",  "AnalyticsView"),
    ("Insights",   "InsightsView"),
    ("Ask AI",     "AskView"),
]


class SidebarDivider(QFrame):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("sidebar_divider")
        self.setFixedHeight(1)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Vispend AI")
        self.resize(1260, 800)
        self.setMinimumSize(960, 620)

        self._nav_buttons: list[QPushButton] = []
        self._current_user: dict = {}

        central = QWidget()
        central.setObjectName("central_widget")
        self.setCentralWidget(central)

        self._root_stack = QStackedWidget()

        root_layout = QVBoxLayout(central)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)
        root_layout.addWidget(self._root_stack)

        self._build_auth_screen()
        self._build_app_shell()

        self._root_stack.setCurrentIndex(0)

    # ──────────────────────────────────────────────────────────
    # Auth screen
    # ──────────────────────────────────────────────────────────

    def _build_auth_screen(self) -> None:
        self._auth_container = QStackedWidget()

        self._login_view = LoginView()
        self._register_view = RegisterView()

        self._auth_container.addWidget(self._login_view)
        self._auth_container.addWidget(self._register_view)
        self._auth_container.setCurrentIndex(0)

        self._login_view.login_success.connect(self._on_login_success)
        self._login_view.switch_to_register.connect(self._show_register)
        self._register_view.register_success.connect(self._on_login_success)
        self._register_view.switch_to_login.connect(self._show_login)

        self._root_stack.addWidget(self._auth_container)

    def _show_login(self) -> None:
        self._auth_container.setCurrentWidget(self._login_view)

    def _show_register(self) -> None:
        self._auth_container.setCurrentWidget(self._register_view)

    # ──────────────────────────────────────────────────────────
    # App shell
    # ──────────────────────────────────────────────────────────

    def _build_app_shell(self) -> None:
        shell = QWidget()
        shell.setObjectName("central_widget")
        shell_layout = QHBoxLayout(shell)
        shell_layout.setContentsMargins(0, 0, 0, 0)
        shell_layout.setSpacing(0)

        self._sidebar = self._build_sidebar()
        shell_layout.addWidget(self._sidebar)

        self._content_stack = QStackedWidget()
        self._content_stack.setObjectName("content_area")

        self._upload_view    = UploadView()
        self._receipts_view  = ReceiptsView()
        self._analytics_view = AnalyticsView()
        self._insights_view  = InsightsView()
        self._ask_view       = AskView()

        for view in (
            self._upload_view,
            self._receipts_view,
            self._analytics_view,
            self._insights_view,
            self._ask_view,
        ):
            self._content_stack.addWidget(view)

        shell_layout.addWidget(self._content_stack, stretch=1)

        self._root_stack.addWidget(shell)

        self._upload_view.upload_complete.connect(self._on_upload_complete)

    def _build_sidebar(self) -> QWidget:
        sidebar = QWidget()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(220)

        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(12, 20, 12, 16)
        layout.setSpacing(0)

        title_label = QLabel("Vispend AI")
        title_label.setObjectName("app_title")
        subtitle_label = QLabel("Receipt Manager")
        subtitle_label.setObjectName("app_subtitle")

        layout.addWidget(title_label)
        layout.addWidget(subtitle_label)
        layout.addSpacing(20)
        layout.addWidget(SidebarDivider())
        layout.addSpacing(12)

        for index, (label, _) in enumerate(NAV_ITEMS):
            btn = QPushButton(label)
            btn.setObjectName("nav_btn")
            btn.setProperty("active", "false")
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.clicked.connect(lambda checked, i=index: self._navigate(i))
            layout.addWidget(btn)
            layout.addSpacing(2)
            self._nav_buttons.append(btn)

        layout.addStretch()
        layout.addWidget(SidebarDivider())
        layout.addSpacing(12)

        self._user_label = QLabel("")
        self._user_label.setObjectName("user_label")
        self._user_label.setWordWrap(True)
        layout.addWidget(self._user_label)
        layout.addSpacing(8)

        logout_btn = QPushButton("Sign out")
        logout_btn.setObjectName("logout_btn")
        logout_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        logout_btn.clicked.connect(self._on_logout)
        layout.addWidget(logout_btn)

        return sidebar

    # ──────────────────────────────────────────────────────────
    # Navigation
    # ──────────────────────────────────────────────────────────

    def _navigate(self, index: int) -> None:
        self._content_stack.setCurrentIndex(index)
        for i, btn in enumerate(self._nav_buttons):
            btn.setProperty("active", "true" if i == index else "false")
            btn.style().unpolish(btn)
            btn.style().polish(btn)

        self._on_view_activated(index)

    def _on_view_activated(self, index: int) -> None:
        view = self._content_stack.widget(index)
        if hasattr(view, "refresh"):
            try:
                view.refresh()
            except Exception as exc:
                logger.warning("View refresh error at index %d: %s", index, exc)

    # ──────────────────────────────────────────────────────────
    # Auth handlers
    # ──────────────────────────────────────────────────────────

    @Slot(dict)
    def _on_login_success(self, payload: dict) -> None:
        self._current_user = payload

        user_info = payload.get("user", {})
        display_name = (
            user_info.get("full_name")
            or user_info.get("username")
            or user_info.get("email")
            or "User"
        )
        self._user_label.setText(display_name)

        self._root_stack.setCurrentIndex(1)
        self._navigate(0)
        logger.info("User signed in: %s", display_name)

    @Slot()
    def _on_logout(self) -> None:
        api.clear_token()
        self._current_user = {}
        self._user_label.setText("")

        for i, btn in enumerate(self._nav_buttons):
            btn.setProperty("active", "false")
            btn.style().unpolish(btn)
            btn.style().polish(btn)

        self._show_login()
        self._root_stack.setCurrentIndex(0)
        logger.info("User signed out")

    # ──────────────────────────────────────────────────────────
    # Cross-view signals
    # ──────────────────────────────────────────────────────────

    @Slot()
    def _on_upload_complete(self) -> None:
        if hasattr(self._receipts_view, "refresh"):
            self._receipts_view.refresh()


def main() -> None:
    app = QApplication(sys.argv)
    app.setApplicationName("Vispend AI")
    app.setApplicationVersion("1.0.0")
    app.setOrganizationName("Vispend")
    app.setStyle("Fusion")
    app.setStyleSheet(APP_STYLESHEET)

    window = MainWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()