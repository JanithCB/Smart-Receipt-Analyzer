# src/desktop/main.py
"""
Desktop Application Entry Point
Manages: Auth state, main window, tab navigation, stylesheet
"""
import sys
import os

# Fix 1: PyQt6 → PySide6 throughout (was mixing both frameworks)
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout,
    QHBoxLayout, QLabel, QPushButton, QStackedWidget,
    QFrame, QSizePolicy, QStatusBar
)
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QFont, QIcon

from .views.login_view import LoginView
from .views.upload_view import UploadView
from .views.receipts_view import ReceiptsView
from .views.analytics_view import AnalyticsView
from .views.insights_view import InsightsView
from .views.ask_view import AskView
from .workers import HealthCheckWorker
from .api_client import api


APP_NAME    = "Receipt Analyzer"
APP_VERSION = "2.0"


STYLESHEET = """
* { font-family: 'Segoe UI', 'Inter', sans-serif; }

QMainWindow, QWidget#centralWidget {
    background-color: #f7f6f2;
    color: #28251d;
}

/* ── Sidebar ── */
QWidget#sidebar {
    background-color: #1c1b19;
    min-width: 200px;
    max-width: 200px;
}
QLabel#sidebarLogo {
    color: #f9f8f5;
    font-size: 15px;
    font-weight: 700;
    padding: 20px 16px 8px 16px;
}
QLabel#sidebarVersion {
    color: #5a5957;
    font-size: 11px;
    padding: 0 16px 16px 16px;
}
QPushButton#navBtn {
    background: transparent;
    color: #797876;
    border: none;
    border-radius: 6px;
    padding: 10px 16px;
    text-align: left;
    font-size: 13px;
}
QPushButton#navBtn:hover { background: #262523; color: #cdccca; }
QPushButton#navBtnActive {
    background: #313b3b;
    color: #4f98a3;
    border: none;
    border-radius: 6px;
    padding: 10px 16px;
    text-align: left;
    font-size: 13px;
    font-weight: 600;
}
QLabel#userLabel {
    color: #797876;
    font-size: 11px;
    padding: 4px 16px;
}
QPushButton#logoutBtn {
    background: transparent;
    color: #797876;
    border: none;
    padding: 8px 16px;
    text-align: left;
    font-size: 12px;
}
QPushButton#logoutBtn:hover { color: #dd6974; }

/* ── Cards & Frames ── */
QFrame#kpiCard, QFrame#chartCard, QFrame#insightCard {
    background: #f9f8f5;
    border: 1px solid rgba(40,37,29,0.10);
    border-radius: 10px;
}
QFrame#insightCard { padding: 4px; }

/* ── Login ── */
QFrame#loginCard {
    background: #f9f8f5;
    border: 1px solid rgba(40,37,29,0.12);
    border-radius: 14px;
}
QLabel#appTitle    { font-size: 20px; font-weight: 700; color: #28251d; }
QLabel#appSubtitle { font-size: 12px; color: #7a7974; }

/* ── Tabs on login ── */
QPushButton#tabActive {
    background: #01696f;
    color: white;
    border: none;
    border-radius: 6px;
    padding: 8px 20px;
    font-weight: 600;
}
QPushButton#tabInactive {
    background: #f3f0ec;
    color: #7a7974;
    border: none;
    border-radius: 6px;
    padding: 8px 20px;
}
QPushButton#tabInactive:hover { background: #edeae5; color: #28251d; }

/* ── Inputs ── */
QLineEdit#inputField, QComboBox#comboField {
    background: white;
    border: 1px solid #d4d1ca;
    border-radius: 6px;
    padding: 6px 10px;
    font-size: 13px;
    color: #28251d;
}
QLineEdit#inputField:focus, QComboBox#comboField:focus {
    border-color: #01696f;
}

/* ── Buttons ── */
QPushButton#primaryBtn {
    background: #01696f;
    color: white;
    border: none;
    border-radius: 7px;
    padding: 8px 20px;
    font-size: 13px;
    font-weight: 600;
}
QPushButton#primaryBtn:hover    { background: #0c4e54; }
QPushButton#primaryBtn:disabled { background: #bab9b4; }

QPushButton#secondaryBtn {
    background: #f3f0ec;
    color: #28251d;
    border: 1px solid #d4d1ca;
    border-radius: 7px;
    padding: 8px 16px;
    font-size: 13px;
}
QPushButton#secondaryBtn:hover { background: #edeae5; }

QPushButton#ghostBtn {
    background: transparent;
    color: #7a7974;
    border: 1px solid #dcd9d5;
    border-radius: 6px;
    padding: 6px 14px;
    font-size: 12px;
}
QPushButton#ghostBtn:hover { background: #f3f0ec; color: #28251d; }

QPushButton#tableActionBtn {
    background: #f3f0ec;
    color: #01696f;
    border: none;
    border-radius: 4px;
    padding: 2px 10px;
    font-size: 11px;
}
QPushButton#tableActionBtnDanger {
    background: #f3f0ec;
    color: #a12c7b;
    border: none;
    border-radius: 4px;
    padding: 2px 10px;
    font-size: 11px;
}
QPushButton#suggestedBtn {
    background: #f3f0ec;
    color: #7a7974;
    border: 1px solid #dcd9d5;
    border-radius: 14px;
    padding: 2px 12px;
    font-size: 11px;
}
QPushButton#suggestedBtn:hover { background: #cedcd8; color: #01696f; }

/* ── Table ── */
QTableWidget#receiptsTable {
    background: white;
    border: 1px solid #dcd9d5;
    border-radius: 8px;
    gridline-color: #f3f0ec;
    font-size: 12px;
}
QTableWidget#receiptsTable::item:selected {
    background: #cedcd8;
    color: #28251d;
}
QHeaderView::section {
    background: #f3f0ec;
    border: none;
    padding: 6px 10px;
    font-size: 12px;
    font-weight: 600;
    color: #7a7974;
}

/* ── Drop Zone ── */
QFrame#dropZone {
    background: #f9f8f5;
    border: 2px dashed #d4d1ca;
    border-radius: 12px;
}
QFrame#dropZoneActive {
    background: #cedcd8;
    border: 2px dashed #01696f;
    border-radius: 12px;
}

/* ── Chat Bubbles ── */
QFrame#userBubble QLabel#bubbleText {
    background: #01696f;
    color: white;
    border-radius: 12px;
    padding: 10px 14px;
    font-size: 13px;
}
QFrame#aiBubble QLabel#bubbleText {
    background: white;
    color: #28251d;
    border: 1px solid #dcd9d5;
    border-radius: 12px;
    padding: 10px 14px;
    font-size: 13px;
}

/* ── Labels ── */
QLabel#viewTitle      { font-size: 16px; font-weight: 700; color: #28251d; }
QLabel#viewSubtitle   { font-size: 13px; color: #7a7974; }
QLabel#sectionLabel   { font-size: 13px; font-weight: 600; color: #28251d; }
QLabel#statusLabel    { font-size: 12px; color: #7a7974; }
QLabel#placeholderText{ font-size: 13px; color: #bab9b4; }
QLabel#kpiTitle       { font-size: 11px; color: #7a7974; }
QLabel#pageInfo       { font-size: 12px; color: #7a7974; }
QLabel#insightTitle   { font-size: 11px; font-weight: 600; }
QLabel#insightDesc    { font-size: 13px; color: #28251d; }
QLabel#catLabel       { font-size: 13px; color: #28251d; }
QLabel#catAmount      { font-size: 12px; color: #7a7974; }
QLabel#rankLabel      { font-size: 12px; font-weight: 700; color: #7a7974; }
QLabel#categoryBadge  {
    background: #f3f0ec;
    color: #01696f;
    border-radius: 10px;
    padding: 2px 8px;
    font-size: 11px;
}
QLabel#confBadge { font-size: 11px; color: #7a7974; }
QLabel#dropHint  { font-size: 13px; color: #7a7974; }
QLabel#dropTypes { font-size: 11px; color: #bab9b4; }

/* ── Progress ── */
QProgressBar#uploadProgress {
    background: #f3f0ec;
    border-radius: 4px;
    border: none;
}
QProgressBar#uploadProgress::chunk {
    background: #01696f;
    border-radius: 4px;
}

/* ── Status bar ── */
QStatusBar { background: #f3f0ec; font-size: 11px; color: #7a7974; }
"""


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self._current_user = None
        self.setWindowTitle(f"{APP_NAME} {APP_VERSION}")
        self.setMinimumSize(1060, 680)
        self._setup_ui()
        self._check_server()

    def _setup_ui(self):
        central = QWidget()
        central.setObjectName("centralWidget")
        self.setCentralWidget(central)

        self._root_stack = QStackedWidget()
        root_layout = QVBoxLayout(central)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.addWidget(self._root_stack)

        # Page 0: Login
        self._login_view = LoginView()
        self._login_view.login_success.connect(self._on_login)
        self._root_stack.addWidget(self._login_view)

        # Page 1: Main app
        self._app_widget = self._build_app_widget()
        self._root_stack.addWidget(self._app_widget)

        self._root_stack.setCurrentIndex(0)
        self.statusBar().showMessage("Checking server…")

    def _build_app_widget(self) -> QWidget:
        widget = QWidget()
        layout = QHBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # ── Sidebar ──
        sidebar = QWidget()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(200)
        sidebar_layout = QVBoxLayout(sidebar)
        sidebar_layout.setContentsMargins(0, 0, 0, 0)
        sidebar_layout.setSpacing(2)

        logo = QLabel("🧾 Receipt Analyzer")
        logo.setObjectName("sidebarLogo")
        sidebar_layout.addWidget(logo)

        ver = QLabel(f"v{APP_VERSION}")
        ver.setObjectName("sidebarVersion")
        sidebar_layout.addWidget(ver)

        self._nav_buttons = []
        nav_items = [
            ("  Upload",    0),
            ("  Receipts",  1),
            ("  Analytics", 2),
            ("  Insights",  3),
            ("  Ask AI",    4),
        ]
        for label, index in nav_items:
            btn = QPushButton(label)
            btn.setObjectName("navBtn")
            btn.clicked.connect(lambda _, i=index: self._switch_tab(i))
            sidebar_layout.addWidget(btn)
            self._nav_buttons.append(btn)

        sidebar_layout.addStretch()

        self._user_label = QLabel("")
        self._user_label.setObjectName("userLabel")
        self._user_label.setWordWrap(True)
        sidebar_layout.addWidget(self._user_label)

        btn_logout = QPushButton("Sign Out")
        btn_logout.setObjectName("logoutBtn")
        btn_logout.clicked.connect(self._logout)
        sidebar_layout.addWidget(btn_logout)

        layout.addWidget(sidebar)

        # ── Content stack ──
        self._content_stack  = QStackedWidget()
        self._upload_view    = UploadView()
        self._receipts_view  = ReceiptsView()
        self._analytics_view = AnalyticsView()
        self._insights_view  = InsightsView()
        self._ask_view       = AskView()

        self._upload_view.upload_complete.connect(self._on_upload_complete)

        for view in (
            self._upload_view,
            self._receipts_view,
            self._analytics_view,
            self._insights_view,
            self._ask_view,
        ):
            self._content_stack.addWidget(view)

        layout.addWidget(self._content_stack, 1)
        return widget

    def _switch_tab(self, index: int):
        self._content_stack.setCurrentIndex(index)
        for i, btn in enumerate(self._nav_buttons):
            btn.setObjectName("navBtnActive" if i == index else "navBtn")
            btn.style().unpolish(btn)
            btn.style().polish(btn)

    def _on_login(self, data: dict):
        # Fix 2: payload is {"access_token": ..., "user": {...}}
        # extract user sub-dict safely
        user = data.get("user", {})
        if not isinstance(user, dict):
            user = {}
        self._current_user = user
        api.set_token(data["access_token"])

        name = user.get("full_name") or user.get("username") or "User"
        self._user_label.setText(f"Signed in as\n{name}")
        self._root_stack.setCurrentIndex(1)
        self._switch_tab(0)
        self.statusBar().showMessage(f"Welcome, {name}!", 4000)
        QTimer.singleShot(300, self._receipts_view.refresh)

    def _logout(self):
        api.logout()
        self._current_user = None
        self._root_stack.setCurrentIndex(0)
        self.statusBar().showMessage("Signed out.")

    def _on_upload_complete(self):
        self._receipts_view.refresh()
        self._switch_tab(1)
        self.statusBar().showMessage(
            "Upload complete — receipts are being processed.", 5000
        )

    def _check_server(self):
        worker = HealthCheckWorker()
        worker.finished.connect(self._on_health)
        worker.start()

    def _on_health(self, data: dict):
        if data.get("healthy"):
            self.statusBar().showMessage("✓ Server connected", 4000)
        else:
            self.statusBar().showMessage(
                "✗ Cannot reach server — check that the backend is running."
            )


def run():
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setStyleSheet(STYLESHEET)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    run()