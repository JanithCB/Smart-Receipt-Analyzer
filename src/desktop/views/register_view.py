# src/desktop/views/register_view.py
from PySide6.QtCore import Signal, QThreadPool
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QLineEdit,
    QPushButton, QMessageBox, QFrame
)
from desktop.workers import ApiWorker


class RegisterView(QWidget):
    register_success = Signal(dict)
    back_to_login    = Signal()

    def __init__(self, api_client):
        super().__init__()
        self.api  = api_client
        self.pool = QThreadPool.globalInstance()
        self.setWindowTitle("Vispend AI - Register")
        self.resize(460, 460)
        self._build()

    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(40, 40, 40, 40)
        root.setSpacing(14)

        card   = QFrame()
        layout = QVBoxLayout(card)
        layout.setSpacing(12)

        title = QLabel("Create Account")
        title.setStyleSheet("font-size: 22px; font-weight: 700;")

        self.full_name = QLineEdit()
        self.full_name.setPlaceholderText("Full Name (optional)")

        # username field — required by UserCreate schema
        self.username = QLineEdit()
        self.username.setPlaceholderText("Username (min 3 characters)")

        self.email = QLineEdit()
        self.email.setPlaceholderText("Email")

        self.password = QLineEdit()
        self.password.setPlaceholderText("Password (min 6 characters)")
        self.password.setEchoMode(QLineEdit.EchoMode.Password)

        self.confirm = QLineEdit()
        self.confirm.setPlaceholderText("Confirm Password")
        self.confirm.setEchoMode(QLineEdit.EchoMode.Password)

        self.create_btn = QPushButton("Create Account")
        self.create_btn.clicked.connect(self.handle_register)

        back_btn = QPushButton("Back to Login")
        back_btn.clicked.connect(self.back_to_login.emit)

        layout.addWidget(title)
        layout.addWidget(self.full_name)
        layout.addWidget(self.username)
        layout.addWidget(self.email)
        layout.addWidget(self.password)
        layout.addWidget(self.confirm)
        layout.addWidget(self.create_btn)
        layout.addWidget(back_btn)

        root.addStretch()
        root.addWidget(card)
        root.addStretch()

    def handle_register(self):
        full_name = self.full_name.text().strip()
        username  = self.username.text().strip()
        email     = self.email.text().strip()
        password  = self.password.text().strip()
        confirm   = self.confirm.text().strip()

        if not email or not username or not password:
            QMessageBox.warning(self, "Missing Fields", "Email, username and password are required.")
            return
        if len(username) < 3:
            QMessageBox.warning(self, "Username Too Short", "Username must be at least 3 characters.")
            return
        if len(password) < 6:
            QMessageBox.warning(self, "Password Too Short", "Password must be at least 6 characters.")
            return
        if password != confirm:
            QMessageBox.warning(self, "Password Mismatch", "Passwords do not match.")
            return

        self.create_btn.setEnabled(False)

        def register_then_login():
            # fixed: now passes all 4 required fields
            self.api.register(
                email=email,
                username=username,
                password=password,
                full_name=full_name,
            )
            return self.api.login(email, password)

        worker = ApiWorker(register_then_login)
        worker.signals.finished.connect(self._on_success)
        worker.signals.error.connect(self._on_error)
        self.pool.start(worker)

    def _on_success(self, payload):
        self.create_btn.setEnabled(True)
        self.register_success.emit(payload)

    def _on_error(self, message):
        self.create_btn.setEnabled(True)
        QMessageBox.critical(self, "Registration Failed", message)