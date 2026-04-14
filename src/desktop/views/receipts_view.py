# src/desktop/views/receipts_view.py
"""Receipts View — paginated list, search, filter, review & correct"""
from PySide6.QtWidgets import (          # Fix 1: PyQt6 → PySide6
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QLineEdit,
    QComboBox, QTableWidget, QTableWidgetItem, QHeaderView, QFrame,
    QMessageBox, QDialog, QFormLayout, QDialogButtonBox,
    QSizePolicy, QAbstractItemView
)
from PySide6.QtCore import Qt, Signal, QTimer, QThreadPool  # Fix 1 + added QThreadPool
from PySide6.QtGui import QFont, QColor
from ..workers import (
    ListReceiptsWorker, DeleteReceiptWorker,
    ReprocessReceiptWorker, UpdateReceiptWorker
)


CATEGORIES = [
    "All", "Groceries", "Dining", "Transport", "Shopping",
    "Health & Medical", "Entertainment", "Utilities & Bills",
    "Education", "Travel & Accommodation", "Financial Services", "Other",
]

STATUS_COLORS = {
    "done":       "#437a22",
    "processing": "#d19900",
    "pending":    "#006494",
    "failed":     "#a12c7b",
}


class ReceiptsView(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._page       = 1
        self._page_size  = 20
        self._total      = 0
        self._worker     = None
        self._receipts   = []
        self._pool       = QThreadPool.globalInstance()
        self._search_timer = QTimer()
        self._search_timer.setSingleShot(True)
        self._search_timer.timeout.connect(self._load_receipts)
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(12)

        # Header
        header_row = QHBoxLayout()
        title = QLabel("Receipts")
        title.setObjectName("viewTitle")
        title.setFont(QFont("Segoe UI", 16, QFont.Weight.Bold))
        header_row.addWidget(title)
        header_row.addStretch()
        self.btn_refresh = QPushButton("⟳ Refresh")
        self.btn_refresh.setObjectName("ghostBtn")
        self.btn_refresh.clicked.connect(self.refresh)
        header_row.addWidget(self.btn_refresh)
        layout.addLayout(header_row)

        # Filters
        filter_row = QHBoxLayout()
        self.search_box = QLineEdit()
        self.search_box.setObjectName("inputField")
        self.search_box.setPlaceholderText("Search merchant or text…")
        self.search_box.textChanged.connect(lambda: self._search_timer.start(400))
        filter_row.addWidget(self.search_box, 3)

        self.cat_filter = QComboBox()
        self.cat_filter.setObjectName("comboField")
        self.cat_filter.addItems(CATEGORIES)
        self.cat_filter.currentTextChanged.connect(self._on_filter_change)
        filter_row.addWidget(self.cat_filter, 2)

        self.status_filter = QComboBox()
        self.status_filter.setObjectName("comboField")
        self.status_filter.addItems(["All Status", "done", "processing", "pending", "failed"])
        self.status_filter.currentTextChanged.connect(self._on_filter_change)
        filter_row.addWidget(self.status_filter, 2)

        self.review_filter = QComboBox()
        self.review_filter.setObjectName("comboField")
        self.review_filter.addItems(["All Reviews", "Needs Review", "Verified"])
        self.review_filter.currentTextChanged.connect(self._on_filter_change)
        filter_row.addWidget(self.review_filter, 2)
        layout.addLayout(filter_row)

        # Table
        self.table = QTableWidget()
        self.table.setObjectName("receiptsTable")
        self.table.setColumnCount(7)
        self.table.setHorizontalHeaderLabels([
            "Date", "Merchant", "Category", "Amount", "Currency", "Status", "Actions"
        ])
        self.table.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.ResizeMode.Stretch
        )
        self.table.horizontalHeader().setSectionResizeMode(
            2, QHeaderView.ResizeMode.ResizeToContents
        )
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.setAlternatingRowColors(True)
        layout.addWidget(self.table)

        # Pagination
        page_row = QHBoxLayout()
        self.lbl_total = QLabel("")
        self.lbl_total.setObjectName("pageInfo")
        page_row.addWidget(self.lbl_total)
        page_row.addStretch()

        self.btn_prev = QPushButton("← Prev")
        self.btn_prev.setObjectName("ghostBtn")
        self.btn_prev.setEnabled(False)
        self.btn_prev.clicked.connect(self._prev_page)

        self.lbl_page = QLabel("Page 1")
        self.lbl_page.setObjectName("pageInfo")

        self.btn_next = QPushButton("Next →")
        self.btn_next.setObjectName("ghostBtn")
        self.btn_next.setEnabled(False)
        self.btn_next.clicked.connect(self._next_page)

        page_row.addWidget(self.btn_prev)
        page_row.addWidget(self.lbl_page)
        page_row.addWidget(self.btn_next)
        layout.addLayout(page_row)

    def refresh(self):
        self._page = 1
        self._load_receipts()

    def _on_filter_change(self):
        self._page = 1
        self._load_receipts()

    def _load_receipts(self):
        category = self.cat_filter.currentText()
        status   = self.status_filter.currentText()
        review   = self.review_filter.currentText()
        search   = self.search_box.text().strip()

        self._worker = ListReceiptsWorker(
            page=self._page,
            page_size=self._page_size,
            category=None if category == "All" else category,
            status=None   if status   == "All Status" else status,
            needs_review=(
                True  if review == "Needs Review" else
                False if review == "Verified"     else None
            ),
            search=search or None,
        )
        # Fix 2: QRunnable uses pool.start(), not worker.start()
        self._worker.signals.finished.connect(self._on_data)
        self._worker.signals.error.connect(self._on_error)
        self._pool.start(self._worker)

    def _on_data(self, data: dict):
        self._total    = data.get("total", 0)
        self._receipts = data.get("items", [])
        self._render_table(self._receipts)

        total_pages = max(1, -(-self._total // self._page_size))
        self.lbl_total.setText(f"{self._total} receipt(s) found")
        self.lbl_page.setText(f"Page {self._page} / {total_pages}")
        self.btn_prev.setEnabled(self._page > 1)
        self.btn_next.setEnabled(self._page < total_pages)

    def _render_table(self, receipts: list):
        self.table.setRowCount(len(receipts))
        for row, r in enumerate(receipts):
            date_str     = (r.get("receipt_date") or r.get("created_at") or "")[:10]
            merchant     = r.get("merchant")          or "Unknown"
            category     = r.get("category")          or "Other"
            amount       = r.get("total_amount")
            currency     = r.get("currency")          or ""
            status       = r.get("processing_status") or ""
            needs_review = r.get("needs_review", False)
            receipt_id   = r.get("id")
            amount_str   = f"{amount:.2f}" if amount is not None else "—"

            for col, text in enumerate(
                [date_str, merchant, category, amount_str, currency, status]
            ):
                item = QTableWidgetItem(text)
                item.setTextAlignment(
                    Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft
                )
                if col == 5:
                    item.setForeground(QColor(STATUS_COLORS.get(status, "#7a7974")))
                if needs_review and col == 2:
                    item.setBackground(QColor("#e9e0c6"))
                self.table.setItem(row, col, item)

            # Actions
            action_widget = QWidget()
            al = QHBoxLayout(action_widget)
            al.setContentsMargins(4, 2, 4, 2)
            al.setSpacing(4)

            btn_edit = QPushButton("Edit")
            btn_edit.setObjectName("tableActionBtn")
            btn_edit.setFixedHeight(26)
            btn_edit.clicked.connect(
                lambda _, rid=receipt_id: self._edit_receipt(rid)
            )

            btn_del = QPushButton("Delete")
            btn_del.setObjectName("tableActionBtnDanger")
            btn_del.setFixedHeight(26)
            btn_del.clicked.connect(
                lambda _, rid=receipt_id: self._delete_receipt(rid)
            )

            al.addWidget(btn_edit)
            al.addWidget(btn_del)
            self.table.setCellWidget(row, 6, action_widget)

    def _edit_receipt(self, receipt_id: int):
        receipt = next(
            (r for r in self._receipts if r.get("id") == receipt_id), None
        )
        if not receipt:
            return
        dialog = EditReceiptDialog(receipt, self)
        if dialog.exec():
            self._load_receipts()

    def _delete_receipt(self, receipt_id: int):
        reply = QMessageBox.question(
            self, "Delete Receipt",
            "Are you sure you want to delete this receipt?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            w = DeleteReceiptWorker(receipt_id)
            # Fix 2: pool.start() not w.start()
            w.signals.finished.connect(lambda _: self._load_receipts())
            w.signals.error.connect(
                lambda e: QMessageBox.warning(self, "Error", e)
            )
            self._pool.start(w)

    def _prev_page(self):
        if self._page > 1:
            self._page -= 1
            self._load_receipts()

    def _next_page(self):
        if self._page < -(-self._total // self._page_size):
            self._page += 1
            self._load_receipts()

    def _on_error(self, message: str):
        self.lbl_total.setText(f"Error: {message}")


class EditReceiptDialog(QDialog):
    def __init__(self, receipt: dict, parent=None):
        super().__init__(parent)
        self.receipt = receipt
        self._worker = None
        self._pool   = QThreadPool.globalInstance()
        self.setWindowTitle(f"Edit Receipt #{receipt.get('id')}")
        self.setMinimumWidth(420)
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        form   = QFormLayout()
        form.setSpacing(10)

        self.merchant_edit = QLineEdit(self.receipt.get("merchant") or "")
        self.merchant_edit.setObjectName("inputField")
        form.addRow("Merchant:", self.merchant_edit)

        amt = self.receipt.get("total_amount")
        self.amount_edit = QLineEdit(str(amt) if amt is not None else "")
        self.amount_edit.setObjectName("inputField")
        form.addRow("Total Amount:", self.amount_edit)

        self.currency_edit = QLineEdit(self.receipt.get("currency") or "")
        self.currency_edit.setObjectName("inputField")
        form.addRow("Currency:", self.currency_edit)

        self.category_combo = QComboBox()
        self.category_combo.setObjectName("comboField")
        cats = CATEGORIES[1:]
        self.category_combo.addItems(cats)
        current_cat = self.receipt.get("category") or "Other"
        if current_cat in cats:
            self.category_combo.setCurrentText(current_cat)
        form.addRow("Category:", self.category_combo)

        self.notes_edit = QLineEdit(self.receipt.get("notes") or "")
        self.notes_edit.setObjectName("inputField")
        form.addRow("Notes:", self.notes_edit)

        layout.addLayout(form)

        conf   = self.receipt.get("category_confidence")
        source = self.receipt.get("category_source") or ""
        if conf is not None:
            badge = QLabel(f"AI confidence: {conf*100:.0f}%  |  Source: {source}")
            badge.setObjectName("confBadge")
            layout.addWidget(badge)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save |
            QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self.status_label = QLabel("")
        self.status_label.setObjectName("statusLabel")
        layout.addWidget(self.status_label)

    def _save(self):
        receipt_id = self.receipt.get("id")
        new_cat    = self.category_combo.currentText()
        old_cat    = self.receipt.get("category") or "Other"

        kwargs = {
            "merchant": self.merchant_edit.text().strip() or None,
            "notes":    self.notes_edit.text().strip()    or None,
        }
        try:
            kwargs["total_amount"] = float(self.amount_edit.text())
        except (ValueError, TypeError):
            pass

        curr = self.currency_edit.text().strip().upper()
        if curr:
            kwargs["currency"] = curr
        if new_cat != old_cat:
            kwargs["category"] = new_cat

        self.status_label.setText("Saving…")
        self._worker = UpdateReceiptWorker(receipt_id, **kwargs)
        # Fix 2: pool.start() not worker.start()
        self._worker.signals.finished.connect(lambda _: self.accept())
        self._worker.signals.error.connect(
            lambda e: self.status_label.setText(f"Error: {e}")
        )
        self._pool.start(self._worker)