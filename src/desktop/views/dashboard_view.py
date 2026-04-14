# src/desktop/views/dashboard_view.py
from PySide6.QtCore import Qt, Signal, QThreadPool
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QTextEdit, QLineEdit,
    QFileDialog, QMessageBox, QFrame, QGridLayout, QTableWidget, QTableWidgetItem,
    QProgressBar, QListWidget, QListWidgetItem
)
from PySide6.QtCharts import (
    QChart, QChartView, QLineSeries, QValueAxis,
    QBarSeries, QBarSet, QBarCategoryAxis
)
from PySide6.QtGui import QPainter
from desktop.workers import ApiWorker


class SummaryCard(QFrame):
    def __init__(self, title, value="0"):
        super().__init__()
        self.setObjectName("summaryCard")
        layout = QVBoxLayout(self)
        self.title_lbl = QLabel(title)
        self.title_lbl.setStyleSheet("color:#6b7280; font-size:12px;")
        self.value_lbl = QLabel(value)
        self.value_lbl.setStyleSheet("font-size:26px; font-weight:700;")
        layout.addWidget(self.title_lbl)
        layout.addWidget(self.value_lbl)

    def set_value(self, text: str):
        self.value_lbl.setText(text)


class DashboardView(QWidget):
    logout_requested = Signal()

    def __init__(self, api_client, user: dict):
        super().__init__()
        self.api  = api_client
        # Fix 1: user is full token payload {"access_token":..., "user":{...}}
        # unwrap safely so user["email"] works correctly
        self.user = user.get("user", user) if isinstance(user, dict) else {}
        self.pool = QThreadPool.globalInstance()
        self.setWindowTitle("Vispend AI Dashboard")
        self.resize(1400, 900)
        self._build()
        self.refresh_all()

    def _build(self):
        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        sidebar = QFrame()
        sidebar.setFixedWidth(200)
        sidebar.setStyleSheet("background:#0f172a; color:white;")
        side_layout = QVBoxLayout(sidebar)
        side_layout.setContentsMargins(20, 20, 20, 20)
        side_layout.setSpacing(18)
        side_layout.addWidget(QLabel("<b>Vispend AI</b>"))
        side_layout.addWidget(QLabel("Dashboard"))
        side_layout.addWidget(QLabel("Receipts"))
        side_layout.addWidget(QLabel("AI Insights"))
        side_layout.addStretch()

        main = QFrame()
        main_layout = QVBoxLayout(main)
        main_layout.setContentsMargins(20, 20, 20, 20)
        main_layout.setSpacing(16)

        topbar = QHBoxLayout()
        title   = QLabel("Financial Overview")
        title.setStyleSheet("font-size:24px; font-weight:700;")
        # Fix 1: safe .get() on unwrapped user dict
        user_lbl    = QLabel(self.user.get("email", ""))
        logout_btn  = QPushButton("Logout")
        logout_btn.clicked.connect(self.logout_requested.emit)
        topbar.addWidget(title)
        topbar.addStretch()
        topbar.addWidget(user_lbl)
        topbar.addWidget(logout_btn)

        cards = QHBoxLayout()
        self.card_total    = SummaryCard("Total Spend (This Month)", "0")
        self.card_receipts = SummaryCard("Total Receipts", "0")
        self.card_category = SummaryCard("Top Category", "-")
        cards.addWidget(self.card_total)
        cards.addWidget(self.card_receipts)
        cards.addWidget(self.card_category)

        chart_grid = QGridLayout()
        self.trend_chart    = QChartView()
        self.trend_chart.setRenderHint(QPainter.RenderHint.Antialiasing)     # Fix 2: PySide6 enum
        self.category_chart = QChartView()
        self.category_chart.setRenderHint(QPainter.RenderHint.Antialiasing)  # Fix 2
        chart_grid.addWidget(self._boxed("Spending Trend",      self.trend_chart),    0, 0)
        chart_grid.addWidget(self._boxed("Category Breakdown",  self.category_chart), 0, 1)

        lower_grid = QGridLayout()
        self.insights_list = QListWidget()
        self.ask_input     = QLineEdit()
        self.ask_input.setPlaceholderText("Ask the AI, e.g. How can I reduce food spending?")
        self.ask_btn    = QPushButton("Ask")
        self.ask_btn.clicked.connect(self.ask_ai)
        self.ask_output = QTextEdit()
        self.ask_output.setReadOnly(True)

        ask_wrap = QVBoxLayout()
        ask_wrap.addWidget(self.ask_input)
        ask_wrap.addWidget(self.ask_btn)
        ask_wrap.addWidget(self.ask_output)
        ask_box = QFrame()
        ask_box.setLayout(ask_wrap)

        lower_grid.addWidget(self._boxed("AI Insights", self.insights_list), 0, 0)
        lower_grid.addWidget(self._boxed("AI Guide",    ask_box),            0, 1)

        upload_row = QHBoxLayout()
        self.upload_btn = QPushButton("Upload Receipts")
        self.upload_btn.clicked.connect(self.upload_receipts)
        self.refresh_btn = QPushButton("Refresh")
        self.refresh_btn.clicked.connect(self.refresh_all)
        self.progress = QProgressBar()
        self.progress.setValue(0)
        self.progress.setMaximum(100)
        upload_row.addWidget(self.upload_btn)
        upload_row.addWidget(self.refresh_btn)
        upload_row.addWidget(self.progress)

        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(
            ["Date", "Merchant", "Category", "Total", "Currency"]
        )
        self.table.horizontalHeader().setStretchLastSection(True)

        main_layout.addLayout(topbar)
        main_layout.addLayout(cards)
        main_layout.addLayout(chart_grid)
        main_layout.addLayout(lower_grid)
        main_layout.addLayout(upload_row)
        main_layout.addWidget(self._boxed("Recent Receipts", self.table))

        root.addWidget(sidebar)
        root.addWidget(main)

        self.setStyleSheet("""
            QWidget { background:#f8fafc; color:#111827; font-family:'Segoe UI'; }
            QFrame { background:white; border:1px solid #e5e7eb; border-radius:12px; }
            QPushButton {
                background:#0f766e; color:white; border:none; border-radius:8px;
                padding:10px 14px; font-weight:600;
            }
            QPushButton:hover { background:#115e59; }
            QLineEdit, QTextEdit, QListWidget, QTableWidget {
                background:white; border:1px solid #d1d5db;
                border-radius:8px; padding:8px;
            }
        """)

    def _boxed(self, title: str, widget) -> QFrame:
        box    = QFrame()
        layout = QVBoxLayout(box)
        lbl    = QLabel(title)
        lbl.setStyleSheet("font-weight:700; font-size:16px;")
        layout.addWidget(lbl)
        layout.addWidget(widget)
        return box

    def run_async(self, fn, on_success):
        worker = ApiWorker(fn)
        worker.signals.finished.connect(on_success)
        worker.signals.error.connect(self.show_error)
        self.pool.start(worker)

    def refresh_all(self):
        self.progress.setValue(10)
        self.run_async(self.api.get_summary,      self._update_summary)
        self.run_async(self.api.get_recent,        self._update_recent)
        self.run_async(self.api.get_auto_insights, self._update_insights)

    def _update_summary(self, data):
        self.card_total.set_value(f"{data.get('total_spend', 0):,.2f}")
        self.card_receipts.set_value(str(data.get("total_receipts", 0)))
        top_cat = data.get("top_category", "-")
        amt     = data.get("top_category_amount", 0)
        self.card_category.set_value(f"{top_cat} ({amt:,.2f})")
        self._render_trend_chart(data.get("monthly_trend", []))
        self._render_category_chart(data.get("category_breakdown", []))
        self.progress.setValue(70)

    def _update_recent(self, data):
        items = data.get("items", [])
        self.table.setRowCount(len(items))
        for row, item in enumerate(items):
            self.table.setItem(row, 0, QTableWidgetItem(item.get("date")     or ""))
            self.table.setItem(row, 1, QTableWidgetItem(item.get("merchant") or ""))
            self.table.setItem(row, 2, QTableWidgetItem(item.get("category") or ""))
            self.table.setItem(row, 3, QTableWidgetItem(f"{item.get('total', 0):,.2f}"))
            self.table.setItem(row, 4, QTableWidgetItem(item.get("currency") or ""))
        self.progress.setValue(90)

    def _update_insights(self, data):
        self.insights_list.clear()
        for item in data.get("items", []):
            q  = item.get("question", "")
            a  = item.get("answer",   "")
            self.insights_list.addItem(QListWidgetItem(f"Q: {q}\n\n{a}"))
        self.progress.setValue(100)

    def _render_trend_chart(self, trend: list):
        series = QLineSeries()
        for idx, point in enumerate(trend, start=1):
            series.append(idx, float(point.get("total", 0)))

        chart = QChart()
        chart.addSeries(series)
        chart.setTitle("Monthly Spend Trend")
        chart.legend().hide()

        axis_x = QValueAxis()
        axis_x.setRange(1, max(12, len(trend)))
        axis_x.setLabelFormat("%d")
        axis_x.setTitleText("Month")
        axis_y = QValueAxis()
        axis_y.setTitleText("Spend")

        chart.addAxis(axis_x, Qt.AlignmentFlag.AlignBottom)  # Fix 2: PySide6 enum
        chart.addAxis(axis_y, Qt.AlignmentFlag.AlignLeft)    # Fix 2
        series.attachAxis(axis_x)
        series.attachAxis(axis_y)
        self.trend_chart.setChart(chart)

    def _render_category_chart(self, breakdown: list):
        chart      = QChart()
        series     = QBarSeries()
        barset     = QBarSet("Amount")
        categories = []

        for item in breakdown[:8]:
            categories.append(item.get("category", "Other"))
            barset.append(float(item.get("total", 0)))

        series.append(barset)
        chart.addSeries(series)
        chart.setTitle("Spend by Category")

        axis_x = QBarCategoryAxis()
        axis_x.append(categories)
        axis_y = QValueAxis()

        chart.addAxis(axis_x, Qt.AlignmentFlag.AlignBottom)  # Fix 2
        chart.addAxis(axis_y, Qt.AlignmentFlag.AlignLeft)    # Fix 2
        series.attachAxis(axis_x)
        series.attachAxis(axis_y)
        chart.legend().setVisible(False)
        self.category_chart.setChart(chart)

    def ask_ai(self):
        question = self.ask_input.text().strip()
        if not question:
            QMessageBox.warning(self, "Missing Question", "Enter a question.")
            return
        self.ask_btn.setEnabled(False)
        worker = ApiWorker(self.api.ask_advisor, question)
        worker.signals.finished.connect(self._on_ai_answer)
        worker.signals.error.connect(self._on_ai_error)
        self.pool.start(worker)

    def _on_ai_answer(self, data):
        self.ask_btn.setEnabled(True)
        text    = data.get("answer", "")
        sources = ", ".join(data.get("sources", []))
        self.ask_output.setPlainText(f"{text}\n\nSources: {sources}")

    def _on_ai_error(self, message):
        self.ask_btn.setEnabled(True)
        self.show_error(message)

    def upload_receipts(self):
        paths, _ = QFileDialog.getOpenFileNames(
            self, "Select Receipt Images", "",
            "Images (*.png *.jpg *.jpeg *.bmp *.webp)"
        )
        if not paths:
            return
        self.upload_btn.setEnabled(False)
        self.progress.setValue(5)
        worker = ApiWorker(self.api.upload_receipts, paths)
        worker.signals.finished.connect(self._on_upload_success)
        worker.signals.error.connect(self._on_upload_error)
        self.pool.start(worker)

    def _on_upload_success(self, data):
        self.upload_btn.setEnabled(True)
        self.progress.setValue(100)
        results = data.get("results", [])
        errors  = data.get("errors",  [])
        QMessageBox.information(
            self, "Upload Complete",
            f"✓ {len(results)} uploaded.  ✗ {len(errors)} failed."
        )
        self.refresh_all()

    def _on_upload_error(self, message):
        self.upload_btn.setEnabled(True)
        self.show_error(message)

    def show_error(self, message: str):
        QMessageBox.critical(self, "Error", message)