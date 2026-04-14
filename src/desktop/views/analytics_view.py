# src/desktop/views/analytics_view.py
"""Analytics View — charts, category breakdown, monthly trends, top merchants"""
from PySide6.QtWidgets import (          # Fix 1: PyQt6 → PySide6
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QComboBox, QFrame, QGridLayout, QScrollArea, QSizePolicy
)
from PySide6.QtCore import Qt, Signal, QThreadPool  # Fix 1 + QThreadPool
from PySide6.QtGui import QFont
from ..workers import AnalyticsWorker


class KPICard(QFrame):
    def __init__(self, title: str, value: str = "—",
                 color: str = "#01696f", parent=None):
        super().__init__(parent)
        self.setObjectName("kpiCard")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(4)

        self.lbl_title = QLabel(title)
        self.lbl_title.setObjectName("kpiTitle")

        self.lbl_value = QLabel(value)
        self.lbl_value.setObjectName("kpiValue")
        self.lbl_value.setFont(QFont("Segoe UI", 20, QFont.Weight.Bold))
        self.lbl_value.setStyleSheet(f"color: {color};")

        layout.addWidget(self.lbl_title)
        layout.addWidget(self.lbl_value)

    def update_value(self, value: str):
        self.lbl_value.setText(value)


class AnalyticsView(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._worker = None
        self._pool   = QThreadPool.globalInstance()  # Fix 2: pool for QRunnable
        self._setup_ui()

    def _setup_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        outer.addWidget(scroll)

        container = QWidget()
        scroll.setWidget(container)

        layout = QVBoxLayout(container)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(20)

        # Header
        header_row = QHBoxLayout()
        title = QLabel("Analytics")
        title.setObjectName("viewTitle")
        title.setFont(QFont("Segoe UI", 16, QFont.Weight.Bold))
        header_row.addWidget(title)
        header_row.addStretch()

        self.period_combo = QComboBox()
        self.period_combo.setObjectName("comboField")
        self.period_combo.addItems(
            ["week", "month", "3months", "6months", "year", "all"]
        )
        self.period_combo.setCurrentText("month")
        self.period_combo.currentTextChanged.connect(self.refresh)
        header_row.addWidget(QLabel("Period:"))
        header_row.addWidget(self.period_combo)

        self.btn_refresh = QPushButton("⟳")
        self.btn_refresh.setObjectName("ghostBtn")
        self.btn_refresh.setFixedWidth(36)
        self.btn_refresh.clicked.connect(self.refresh)
        header_row.addWidget(self.btn_refresh)
        layout.addLayout(header_row)

        # KPI row
        kpi_grid = QGridLayout()
        kpi_grid.setSpacing(12)
        self.kpi_total = KPICard("Total Spend",       "—", "#01696f")
        self.kpi_count = KPICard("Receipts",           "—", "#006494")
        self.kpi_avg   = KPICard("Avg per Receipt",   "—", "#964219")
        self.kpi_top   = KPICard("Top Category",       "—", "#7a39bb")
        kpi_grid.addWidget(self.kpi_total, 0, 0)
        kpi_grid.addWidget(self.kpi_count, 0, 1)
        kpi_grid.addWidget(self.kpi_avg,   0, 2)
        kpi_grid.addWidget(self.kpi_top,   0, 3)
        layout.addLayout(kpi_grid)

        # Category breakdown
        cat_title = QLabel("Spending by Category")
        cat_title.setObjectName("sectionLabel")
        cat_title.setFont(QFont("Segoe UI", 13, QFont.Weight.DemiBold))
        layout.addWidget(cat_title)

        self.cat_frame  = QFrame()
        self.cat_frame.setObjectName("chartCard")
        self.cat_layout = QVBoxLayout(self.cat_frame)
        self.cat_layout.setSpacing(8)
        self.cat_layout.setContentsMargins(16, 14, 16, 14)
        self.cat_placeholder = QLabel("Loading…")
        self.cat_placeholder.setObjectName("placeholderText")
        self.cat_layout.addWidget(self.cat_placeholder)
        layout.addWidget(self.cat_frame)

        # Monthly trends
        trend_title = QLabel("Monthly Trends")
        trend_title.setObjectName("sectionLabel")
        trend_title.setFont(QFont("Segoe UI", 13, QFont.Weight.DemiBold))
        layout.addWidget(trend_title)

        self.trend_frame  = QFrame()
        self.trend_frame.setObjectName("chartCard")
        self.trend_layout = QVBoxLayout(self.trend_frame)
        self.trend_layout.setContentsMargins(16, 14, 16, 14)
        self.trend_placeholder = QLabel("Loading…")
        self.trend_placeholder.setObjectName("placeholderText")
        self.trend_layout.addWidget(self.trend_placeholder)
        layout.addWidget(self.trend_frame)

        # Top merchants
        merch_title = QLabel("Top Merchants")
        merch_title.setObjectName("sectionLabel")
        merch_title.setFont(QFont("Segoe UI", 13, QFont.Weight.DemiBold))
        layout.addWidget(merch_title)

        self.merch_frame  = QFrame()
        self.merch_frame.setObjectName("chartCard")
        self.merch_layout = QVBoxLayout(self.merch_frame)
        self.merch_layout.setContentsMargins(16, 14, 16, 14)
        self.merch_placeholder = QLabel("Loading…")
        self.merch_placeholder.setObjectName("placeholderText")
        self.merch_layout.addWidget(self.merch_placeholder)
        layout.addWidget(self.merch_frame)

        layout.addStretch()

    def refresh(self):
        period       = self.period_combo.currentText()
        self._worker = AnalyticsWorker(period=period)
        # Fix 2: signals.finished / pool.start() — not worker.start()
        self._worker.signals.finished.connect(self._on_data)
        self._worker.signals.error.connect(self._on_error)
        self._pool.start(self._worker)

    def _on_data(self, data: dict):
        summary = data.get("summary", {})
        self.kpi_total.update_value(
            f"{summary.get('currency', '')} {summary.get('total_spend', 0):.2f}"
        )
        self.kpi_count.update_value(str(summary.get("total_receipts", 0)))
        self.kpi_avg.update_value(
            f"{summary.get('currency', '')}"
            f"{summary.get('avg_per_receipt', 0):.2f}"
        )
        self.kpi_top.update_value(summary.get("top_category") or "—")

        self._render_categories(data.get("category_breakdown", []))
        self._render_trends(data.get("monthly_trends",      []))
        self._render_merchants(data.get("top_merchants",    []))

    def _clear_layout(self, layout):
        while layout.count():
            item = layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    def _render_categories(self, items: list):
        self._clear_layout(self.cat_layout)
        if not items:
            self.cat_layout.addWidget(QLabel("No data yet."))
            return

        BAR_COLORS = [
            "#01696f", "#006494", "#7a39bb", "#964219",
            "#437a22", "#d19900", "#a12c7b", "#da7101",
        ]
        max_total = max(i["total"] for i in items) if items else 1

        for idx, item in enumerate(items[:10]):
            row = QHBoxLayout()
            row.setSpacing(10)

            name = QLabel(item["category"])
            name.setFixedWidth(160)
            name.setObjectName("catLabel")
            row.addWidget(name)

            bar_container = QFrame()
            bar_container.setFixedHeight(22)
            bar_container.setObjectName("barContainer")
            bar_inner = QFrame(bar_container)
            bar_inner.setObjectName("barFill")
            pct   = item["total"] / max_total
            color = BAR_COLORS[idx % len(BAR_COLORS)]
            bar_inner.setStyleSheet(
                f"background-color: {color}; border-radius: 4px;"
            )
            bar_inner.setFixedHeight(22)
            bar_inner.setFixedWidth(max(4, int(pct * 340)))
            row.addWidget(bar_container, 1)

            amount_lbl = QLabel(
                f"{item['total']:.2f}  ({item['percentage']:.1f}%)"
            )
            amount_lbl.setObjectName("catAmount")
            amount_lbl.setFixedWidth(130)
            row.addWidget(amount_lbl)

            wrapper = QWidget()
            wrapper.setLayout(row)
            self.cat_layout.addWidget(wrapper)

    def _render_trends(self, items: list):
        self._clear_layout(self.trend_layout)
        if not items:
            self.trend_layout.addWidget(QLabel("No trend data yet."))
            return

        max_val = max(i["total"] for i in items) or 1
        for item in items:
            row = QHBoxLayout()

            month_lbl = QLabel(item["month"])
            month_lbl.setFixedWidth(80)
            month_lbl.setObjectName("catLabel")
            row.addWidget(month_lbl)

            bar = QFrame()
            bar.setObjectName("barFill")
            width = max(4, int(item["total"] / max_val * 320))
            bar.setFixedSize(width, 18)
            bar.setStyleSheet("background-color: #01696f; border-radius: 4px;")
            row.addWidget(bar)
            row.addStretch()

            amt = QLabel(f"{item['total']:.2f}")
            amt.setObjectName("catAmount")
            row.addWidget(amt)

            wrapper = QWidget()
            wrapper.setLayout(row)
            self.trend_layout.addWidget(wrapper)

    def _render_merchants(self, items: list):
        self._clear_layout(self.merch_layout)
        if not items:
            self.merch_layout.addWidget(QLabel("No merchant data yet."))
            return

        for i, item in enumerate(items[:8]):
            row = QHBoxLayout()

            rank = QLabel(f"#{i+1}")
            rank.setFixedWidth(28)
            rank.setObjectName("rankLabel")
            row.addWidget(rank)

            name = QLabel(item["merchant"])
            name.setObjectName("catLabel")
            row.addWidget(name, 1)

            visits = QLabel(f"{item['count']} visit(s)")
            visits.setObjectName("catAmount")
            visits.setFixedWidth(80)
            row.addWidget(visits)

            total = QLabel(f"{item['total']:.2f}")
            total.setObjectName("catAmount")
            total.setFixedWidth(90)
            row.addWidget(total)

            wrapper = QWidget()
            wrapper.setLayout(row)
            self.merch_layout.addWidget(wrapper)

    def _on_error(self, message: str):
        self.kpi_total.update_value("Error")
        self.kpi_count.update_value("—")
        self.kpi_avg.update_value("—")
        self.kpi_top.update_value("—")