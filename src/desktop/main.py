# src/desktop/main.py

import logging
import sys
from pathlib import Path

from dotenv import load_dotenv

# Must run before ANY import that reads os.getenv at module level
# (api_client.py creates the singleton `api = APIClient()` at import time).
load_dotenv(Path(__file__).resolve().parents[1] / ".env")

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
    format="%(asctime)s %(levelname)-8s %(name)s %(message)s",
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
"""


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self._current_user: dict = {}
        self._nav_buttons: list[QPushButton] = []
        self._build_ui()

    def _build_ui(self) -> None:
        self.setWindowTitle("Vispend AI")
        self.resize(1400, 900)
        self.setMinimumSize(1180, 760)

        central = QWidget()
        central.setObjectName("central_widget")
        root = QHBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self._root_stack = QStackedWidget()
        root.addWidget(self._root_stack)

        self._auth_stack = QStackedWidget()
        self._login_view = LoginView()
        self._register_view = RegisterView()
        self._auth_stack.addWidget(self._login_view)
        self._auth_stack.addWidget(self._register_view)

        app_shell = QWidget()
        shell_layout = QHBoxLayout(app_shell)
        shell_layout.setContentsMargins(0, 0, 0, 0)
        shell_layout.setSpacing(0)

        sidebar = self._build_sidebar()
        shell_layout.addWidget(sidebar)

        self._content_stack = QStackedWidget()
        self._content_stack.setObjectName("content_area")

        self._upload_view = UploadView()
        self._receipts_view = ReceiptsView()
        self._analytics_view = AnalyticsView()
        self._insights_view = InsightsView()
        self._ask_view = AskView()

        self._content_stack.addWidget(self._upload_view)
        self._content_stack.addWidget(self._receipts_view)
        self._content_stack.addWidget(self._analytics_view)
        self._content_stack.addWidget(self._insights_view)
        self._content_stack.addWidget(self._ask_view)

        shell_layout.addWidget(self._content_stack, 1)

        self._root_stack.addWidget(self._auth_stack)
        self._root_stack.addWidget(app_shell)

        self.setCentralWidget(central)

        self._login_view.login_success.connect(self._on_auth_success)
        self._login_view.show_register_requested.connect(self._show_register)
        self._register_view.register_success.connect(self._on_auth_success)
        self._register_view.show_login_requested.connect(self._show_login)
        self._upload_view.upload_complete.connect(self._on_upload_complete)

        self._show_login()
        self._root_stack.setCurrentIndex(0)

    def _build_sidebar(self) -> QWidget:
        sidebar = QWidget()
        sidebar.setObjectName("sidebar")
        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(16, 18, 16, 18)
        layout.setSpacing(14)

        title = QLabel("Vispend AI")
        title.setObjectName("app_title")

        subtitle = QLabel("Receipt intelligence")
        subtitle.setObjectName("app_subtitle")

        layout.addWidget(title)
        layout.addWidget(subtitle)

        divider_top = QFrame()
        divider_top.setObjectName("sidebar_divider")
        layout.addWidget(divider_top)

        self._user_label = QLabel("")
        self._user_label.setObjectName("user_label")
        self._user_label.setWordWrap(True)
        layout.addWidget(self._user_label)

        nav_items = [
            ("Upload", 0),
            ("Receipts", 1),
            ("Analytics", 2),
            ("Insights", 3),
            ("Ask AI", 4),
        ]

        for label, index in nav_items:
            btn = QPushButton(label)
            btn.setObjectName("nav_btn")
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setProperty("active", "false")
            btn.clicked.connect(lambda _checked=False, i=index: self._show_page(i))
            self._nav_buttons.append(btn)
            layout.addWidget(btn)

        layout.addStretch()

        divider_bottom = QFrame()
        divider_bottom.setObjectName("sidebar_divider")
        layout.addWidget(divider_bottom)

        logout_btn = QPushButton("Sign out")
        logout_btn.setObjectName("logout_btn")
        logout_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        logout_btn.clicked.connect(self._on_logout)
        layout.addWidget(logout_btn)

        return sidebar

    def _set_active_nav(self, index: int) -> None:
        for i, btn in enumerate(self._nav_buttons):
            btn.setProperty("active", "true" if i == index else "false")
            btn.style().unpolish(btn)
            btn.style().polish(btn)

    def _show_page(self, index: int) -> None:
        self._content_stack.setCurrentIndex(index)
        self._set_active_nav(index)

        current_widget = self._content_stack.currentWidget()
        if hasattr(current_widget, "refresh"):
            try:
                current_widget.refresh()
            except Exception as exc:
                logger.warning("Failed to refresh page %s: %s", index, exc)

    @Slot(dict)
    def _on_auth_success(self, user_payload: dict) -> None:
        self._current_user = user_payload or {}
        display_name = (
            self._current_user.get("username")
            or self._current_user.get("email")
            or "Signed in"
        )
        self._user_label.setText(display_name)
        self._root_stack.setCurrentIndex(1)
        self._show_page(0)
        logger.info("User signed in: %s", display_name)

    @Slot()
    def _show_register(self) -> None:
        self._auth_stack.setCurrentWidget(self._register_view)

    @Slot()
    def _show_login(self) -> None:
        self._auth_stack.setCurrentWidget(self._login_view)

    @Slot()
    def _on_logout(self) -> None:
        # FIX BUG-5: Stop any active receipt polling timers BEFORE clearing the
        # token. Without this, running QTimers keep calling GET /receipts/{id}
        # after sign-out (401s) and may survive into the next user's session.
        if hasattr(self._upload_view, "stop_all_polling"):
            self._upload_view.stop_all_polling()

        api.clear_token()
        self._current_user = {}
        self._user_label.setText("")

        for btn in self._nav_buttons:
            btn.setProperty("active", "false")
            btn.style().unpolish(btn)
            btn.style().polish(btn)

        self._show_login()
        self._root_stack.setCurrentIndex(0)
        logger.info("User signed out")

    @Slot()
    def _on_upload_complete(self) -> None:
        # FIX BUG-4: Refresh all data-dependent views when a receipt finishes
        # processing, not just the receipts list.
        for view in (self._receipts_view, self._analytics_view, self._insights_view):
            if hasattr(view, "refresh"):
                try:
                    view.refresh()
                except Exception as exc:
                    logger.warning("View refresh failed after upload: %s", exc)


def _load_fonts() -> None:
    candidate_fonts = [
        "assets/fonts/Inter-Regular.ttf",
        "assets/fonts/InterVariable.ttf",
        "assets/fonts/Inter-VariableFont_opsz,wght.ttf",
    ]
    for rel_path in candidate_fonts:
        path = src_dir / rel_path
        if path.exists():
            QFontDatabase.addApplicationFont(str(path))
            break


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("Vispend AI")
    app.setStyleSheet(APP_STYLESHEET)

    _load_fonts()

    default_font = QFont("Inter", 10)
    default_font.setHintingPreference(QFont.HintingPreference.PreferFullHinting)
    app.setFont(default_font)

    window = MainWindow()
    icon_path = src_dir / "assets" / "logo.png"
    if icon_path.exists():
        window.setWindowIcon(QIcon(str(icon_path)))
    window.show()

    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())