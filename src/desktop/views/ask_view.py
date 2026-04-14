"""Ask View — natural language Q&A with conversation history"""
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QLineEdit, QPushButton, QFrame, QScrollArea,
    QSizePolicy, QTextEdit
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont
from ..workers import AskWorker

SUGGESTED = [
    "What did I spend the most on?",
    "How much did I spend on dining this month?",
    "What are my top 3 merchants?",
    "How does this month compare to last month?",
    "How much did I spend on transport?",
]


class BubbleWidget(QFrame):
    def __init__(self, text: str, is_user: bool, parent=None):
        super().__init__(parent)
        self.setObjectName("userBubble" if is_user else "aiBubble")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        lbl = QLabel(text)
        lbl.setObjectName("bubbleText")
        lbl.setWordWrap(True)
        lbl.setMaximumWidth(520)
        lbl.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum)

        if is_user:
            layout.addStretch()
            layout.addWidget(lbl)
        else:
            layout.addWidget(lbl)
            layout.addStretch()


class AskView(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._worker = None
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(14)

        title = QLabel("Ask AI")
        title.setObjectName("viewTitle")
        title.setFont(QFont("Segoe UI", 16, QFont.Weight.Bold))
        layout.addWidget(title)

        sub = QLabel("Ask any question about your spending in plain language.")
        sub.setObjectName("viewSubtitle")
        layout.addWidget(sub)

        # Suggested questions
        sug_row = QHBoxLayout()
        sug_row.setSpacing(6)
        for q in SUGGESTED:
            btn = QPushButton(q)
            btn.setObjectName("suggestedBtn")
            btn.setFixedHeight(30)
            btn.clicked.connect(lambda _, text=q: self._send(text))
            sug_row.addWidget(btn)
        sug_row.addStretch()
        layout.addLayout(sug_row)

        # Conversation area
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setObjectName("chatScroll")

        self.chat_container = QWidget()
        self.chat_layout = QVBoxLayout(self.chat_container)
        self.chat_layout.setSpacing(10)
        self.chat_layout.setContentsMargins(0, 0, 0, 0)
        self.chat_layout.addStretch()

        scroll.setWidget(self.chat_container)
        layout.addWidget(scroll, 1)

        self._scroll = scroll

        # Input row
        input_row = QHBoxLayout()
        self.input_box = QLineEdit()
        self.input_box.setObjectName("inputField")
        self.input_box.setPlaceholderText("Ask something about your spending…")
        self.input_box.setFixedHeight(42)
        self.input_box.returnPressed.connect(self._on_send_clicked)
        input_row.addWidget(self.input_box, 1)

        self.btn_send = QPushButton("Ask →")
        self.btn_send.setObjectName("primaryBtn")
        self.btn_send.setFixedHeight(42)
        self.btn_send.setFixedWidth(90)
        self.btn_send.clicked.connect(self._on_send_clicked)
        input_row.addWidget(self.btn_send)
        layout.addLayout(input_row)

    def _on_send_clicked(self):
        text = self.input_box.text().strip()
        if text:
            self._send(text)

    def _send(self, question: str):
        self.input_box.clear()
        self._add_bubble(question, is_user=True)
        self.btn_send.setEnabled(False)
        self.btn_send.setText("…")

        self._worker = AskWorker(question)
        self._worker.finished.connect(self._on_answer)
        self._worker.error.connect(self._on_error)
        self._worker.start()

    def _on_answer(self, data: dict):
        self.btn_send.setEnabled(True)
        self.btn_send.setText("Ask →")
        self._add_bubble(data.get("answer", "No answer returned."), is_user=False)

    def _on_error(self, message: str):
        self.btn_send.setEnabled(True)
        self.btn_send.setText("Ask →")
        self._add_bubble(f"Error: {message}", is_user=False)

    def _add_bubble(self, text: str, is_user: bool):
        bubble = BubbleWidget(text, is_user)
        self.chat_layout.insertWidget(self.chat_layout.count() - 1, bubble)
        # Scroll to bottom
        from PyQt6.QtCore import QTimer
        QTimer.singleShot(50, lambda: self._scroll.verticalScrollBar().setValue(
            self._scroll.verticalScrollBar().maximum()
        ))