"""AI Insights View"""
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QFrame, QScrollArea, QSizePolicy
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont
from ..workers import InsightsWorker

INSIGHT_ICONS = {
    "trend":   ("", "#01696f"),
    "alert":   ("",  "#964219"),
    "tip":     ("", "#7a39bb"),
    "anomaly": ("", "#a12c7b"),
}


class InsightCard(QFrame):
    def __init__(self, insight: dict, parent=None):
        super().__init__(parent)
        self.setObjectName("insightCard")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(14)

        itype = insight.get("type", "tip")
        icon_char, color = INSIGHT_ICONS.get(itype, ("💡", "#7a39bb"))

        icon_lbl = QLabel(icon_char)
        icon_lbl.setFont(QFont("Segoe UI Emoji", 22))
        icon_lbl.setFixedWidth(36)
        icon_lbl.setAlignment(Qt.AlignmentFlag.AlignTop)
        layout.addWidget(icon_lbl)

        text_col = QVBoxLayout()
        text_col.setSpacing(4)

        title = QLabel(insight.get("title", ""))
        title.setObjectName("insightTitle")
        title.setFont(QFont("Segoe UI", 11, QFont.Weight.DemiBold))
        title.setStyleSheet(f"color: {color};")
        text_col.addWidget(title)

        desc = QLabel(insight.get("description", ""))
        desc.setObjectName("insightDesc")
        desc.setWordWrap(True)
        text_col.addWidget(desc)

        if insight.get("category"):
            cat_badge = QLabel(f"  {insight['category']}  ")
            cat_badge.setObjectName("categoryBadge")
            text_col.addWidget(cat_badge)

        layout.addLayout(text_col)


class InsightsView(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._worker = None
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

        self._layout = QVBoxLayout(container)
        self._layout.setContentsMargins(24, 24, 24, 24)
        self._layout.setSpacing(14)

        header_row = QHBoxLayout()
        title = QLabel("AI Insights")
        title.setObjectName("viewTitle")
        title.setFont(QFont("Segoe UI", 16, QFont.Weight.Bold))
        header_row.addWidget(title)
        header_row.addStretch()
        self.btn_refresh = QPushButton("⟳ Refresh")
        self.btn_refresh.setObjectName("ghostBtn")
        self.btn_refresh.clicked.connect(self.refresh)
        header_row.addWidget(self.btn_refresh)
        self._layout.addLayout(header_row)

        sub = QLabel("AI-generated spending insights based on your last 60 days of receipts.")
        sub.setObjectName("viewSubtitle")
        sub.setWordWrap(True)
        self._layout.addWidget(sub)

        self.cards_container = QWidget()
        self.cards_layout = QVBoxLayout(self.cards_container)
        self.cards_layout.setSpacing(10)
        self.cards_layout.setContentsMargins(0, 0, 0, 0)
        self._layout.addWidget(self.cards_container)

        self.status_lbl = QLabel("Click Refresh to load insights.")
        self.status_lbl.setObjectName("placeholderText")
        self.status_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._layout.addWidget(self.status_lbl)
        self._layout.addStretch()

    def refresh(self):
        self.status_lbl.setText("Generating insights…")
        self._clear_cards()
        self._worker = InsightsWorker()
        self._worker.finished.connect(self._on_data)
        self._worker.error.connect(self._on_error)
        self._worker.start()

    def _clear_cards(self):
        while self.cards_layout.count():
            item = self.cards_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    def _on_data(self, data: dict):
        self.status_lbl.setText("")
        self._clear_cards()
        insights = data.get("insights", [])
        if not insights:
            self.status_lbl.setText("No insights available yet. Upload more receipts.")
            return
        for insight in insights:
            card = InsightCard(insight)
            self.cards_layout.addWidget(card)

    def _on_error(self, message: str):
        self.status_lbl.setText(f"Error: {message}")