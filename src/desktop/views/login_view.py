# src/desktop/views/login_view.py
from PySide6.QtCore import Qt, Signal, QThreadPool
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QLineEdit,
    QPushButton, QMessageBox, QFrame
)
from desktop.workers import ApiWorker


class LoginView(QWidget):
    login_success = Signal(dict)
    open_register = Signal()

    def __init__(self, api_client):
        super().__init__()
        self.api  = api_client
        self.pool = QThreadPool.globalInstance()
        self.setWindowTitle("Vispend AI - Login")
        self.resize(440, 360)
        self._build()

    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(40, 40, 40, 40)
        root.setSpacing(14)

        card = QFrame()
        card.setObjectName("card")
        card_layout = QVBoxLayout(card)
        card_layout.setSpacing(12)

        title = QLabel("Vispend AI")
        title.setStyleSheet("font-size: 24px; font-weight: 700;")

        subtitle = QLabel("Login to view your receipts, charts, and AI insights.")
        subtitle.setWordWrap(True)

        self.email = QLineEdit()
        self.email.setPlaceholderText("Email")

        self.password = QLineEdit()
        self.password.setPlaceholderText("Password")
        self.password.setEchoMode(QLineEdit.EchoMode.Password)  # fixed

        self.login_btn = QPushButton("Login")
        self.login_btn.clicked.connect(self.handle_login)
        self.password.returnPressed.connect(self.handle_login)  # press Enter to login

        self.register_btn = QPushButton("Create new account")
        self.register_btn.clicked.connect(self.open_register.emit)

        card_layout.addWidget(title)
        card_layout.addWidget(subtitle)
        card_layout.addWidget(self.email)
        card_layout.addWidget(self.password)
        card_layout.addWidget(self.login_btn)
        card_layout.addWidget(self.register_btn)

        root.addStretch()
        root.addWidget(card)
        root.addStretch()

    def handle_login(self):
        email    = self.email.text().strip()
        password = self.password.text().strip()

        if not email or not password:
            QMessageBox.warning(self, "Missing Fields", "Enter email and password.")
            return

        self.login_btn.setEnabled(False)
        worker = ApiWorker(self.api.login, email, password)
        worker.signals.finished.connect(self._on_login_success)
        worker.signals.error.connect(self._on_error)
        self.pool.start(worker)

    def _on_login_success(self, payload):
        self.login_btn.setEnabled(True)
        self.login_success.emit(payload)   # fixed: emit full payload, not just payload["user"]

    def _on_error(self, message):
        self.login_btn.setEnabled(True)
        QMessageBox.critical(self, "Login Failed", message)