# src/desktop/views/upload_view.py
"""Upload View — drag-and-drop + file picker, batch upload with progress"""
import os
from PySide6.QtWidgets import (          # Fix 1: PyQt6 → PySide6
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFileDialog, QProgressBar, QFrame, QSizePolicy,
    QListWidget, QListWidgetItem, QMessageBox
)
from PySide6.QtCore import Qt, Signal, QMimeData
from PySide6.QtGui import QDragEnterEvent, QDropEvent, QFont
from ..workers import UploadReceiptWorker


ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tiff", ".pdf"}


class DropZone(QFrame):
    files_dropped = Signal(list)          # Fix 1: pyqtSignal → Signal

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.setObjectName("dropZone")
        self.setMinimumHeight(180)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setSpacing(10)

        icon = QLabel("📂")
        icon.setFont(QFont("Segoe UI Emoji", 40))
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(icon)

        self.hint_label = QLabel("Drag & drop receipts here\nor click Browse to select files")
        self.hint_label.setObjectName("dropHint")
        self.hint_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.hint_label)

        types_label = QLabel("Supports: JPG · PNG · WEBP · BMP · TIFF · PDF")
        types_label.setObjectName("dropTypes")
        types_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(types_label)

    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
            self.setObjectName("dropZoneActive")
            self.style().unpolish(self)
            self.style().polish(self)

    def dragLeaveEvent(self, event):
        self.setObjectName("dropZone")
        self.style().unpolish(self)
        self.style().polish(self)

    def dropEvent(self, event: QDropEvent):
        self.setObjectName("dropZone")
        self.style().unpolish(self)
        self.style().polish(self)
        paths = []
        for url in event.mimeData().urls():
            path = url.toLocalFile()
            ext  = os.path.splitext(path)[1].lower()
            if ext in ALLOWED_EXTENSIONS:
                paths.append(path)
        if paths:
            self.files_dropped.emit(paths)
        event.acceptProposedAction()


class UploadView(QWidget):
    upload_complete = Signal()            # Fix 1: pyqtSignal → Signal

    def __init__(self, parent=None):
        super().__init__(parent)
        self._worker        = None
        self._pending_files: list = []
        self._done_count    = 0
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)

        header = QLabel("Upload Receipts")
        header.setObjectName("viewTitle")
        header.setFont(QFont("Segoe UI", 16, QFont.Weight.Bold))
        layout.addWidget(header)

        sub = QLabel(
            "Upload receipt images or PDFs — "
            "we'll extract the details automatically using OCR + AI."
        )
        sub.setObjectName("viewSubtitle")
        sub.setWordWrap(True)
        layout.addWidget(sub)

        self.drop_zone = DropZone()
        self.drop_zone.files_dropped.connect(self._add_files)
        layout.addWidget(self.drop_zone)

        btn_row = QHBoxLayout()
        self.btn_browse = QPushButton("Browse Files")
        self.btn_browse.setObjectName("secondaryBtn")
        self.btn_browse.setFixedHeight(38)
        self.btn_browse.clicked.connect(self._browse_files)
        btn_row.addWidget(self.btn_browse)
        btn_row.addStretch()
        layout.addLayout(btn_row)

        files_label = QLabel("Selected Files")
        files_label.setObjectName("sectionLabel")
        layout.addWidget(files_label)

        self.file_list = QListWidget()
        self.file_list.setObjectName("fileList")
        self.file_list.setFixedHeight(140)
        layout.addWidget(self.file_list)

        action_row = QHBoxLayout()
        self.btn_clear = QPushButton("Clear List")
        self.btn_clear.setObjectName("ghostBtn")
        self.btn_clear.clicked.connect(self._clear_files)

        self.btn_upload = QPushButton("Upload & Process")
        self.btn_upload.setObjectName("primaryBtn")
        self.btn_upload.setFixedHeight(42)
        self.btn_upload.setEnabled(False)
        self.btn_upload.clicked.connect(self._start_upload)

        action_row.addWidget(self.btn_clear)
        action_row.addStretch()
        action_row.addWidget(self.btn_upload)
        layout.addLayout(action_row)

        self.progress_bar = QProgressBar()
        self.progress_bar.setObjectName("uploadProgress")
        self.progress_bar.setFixedHeight(8)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setVisible(False)
        layout.addWidget(self.progress_bar)

        self.status_label = QLabel("")
        self.status_label.setObjectName("statusLabel")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.status_label)

        layout.addStretch()

    def _browse_files(self):
        paths, _ = QFileDialog.getOpenFileNames(
            self, "Select Receipt Files", "",
            "Receipt Files (*.jpg *.jpeg *.png *.webp *.bmp *.tiff *.pdf);;All Files (*)",
        )
        if paths:
            self._add_files(paths)

    def _add_files(self, paths: list):
        for path in paths:
            if path not in self._pending_files:
                self._pending_files.append(path)
                self.file_list.addItem(
                    QListWidgetItem(f"  📄  {os.path.basename(path)}")
                )
        self.btn_upload.setEnabled(len(self._pending_files) > 0)
        self.status_label.setText(
            f"{len(self._pending_files)} file(s) ready to upload."
        )

    def _clear_files(self):
        self._pending_files.clear()
        self.file_list.clear()
        self.btn_upload.setEnabled(False)
        self.status_label.setText("")

    def _start_upload(self):
        if not self._pending_files:
            return
        self._done_count = 0
        total = len(self._pending_files)
        self._set_loading(True)
        self.progress_bar.setMaximum(total)

        self._worker = UploadReceiptWorker(self._pending_files[:])

        # Fix 2: correct signal names from UploadReceiptWorker
        # was: self._worker.progress  (doesn't exist)
        # now: file_done → update progress, finished → done
        self._worker.signals.file_done.connect(
            lambda path, result: self._on_file_done(total)
        )
        self._worker.signals.file_error.connect(
            lambda path, err: self._on_file_done(total)
        )
        self._worker.signals.finished.connect(self._on_upload_done)
        self._worker.signals.error.connect(self._on_error)
        from PySide6.QtCore import QThreadPool
        QThreadPool.globalInstance().start(self._worker)

    def _on_file_done(self, total: int):
        self._done_count += 1
        self.progress_bar.setValue(self._done_count)
        self.status_label.setText(
            f"Uploading… {self._done_count}/{total}"
        )

    def _on_upload_done(self, data: dict):
        self._set_loading(False)
        ok_count  = len(data.get("results", []))
        err_count = len(data.get("errors",  []))
        msg = f"✅ {ok_count} receipt(s) uploaded successfully."
        if err_count:
            msg += f"\n⚠️ {err_count} file(s) failed."
        self.status_label.setText(msg)
        self._clear_files()
        if ok_count > 0:
            self.upload_complete.emit()

    def _on_error(self, message: str):
        self._set_loading(False)
        self.status_label.setStyleSheet("color: #a12c7b;")
        self.status_label.setText(f"Error: {message}")

    def _set_loading(self, loading: bool):
        self.btn_upload.setEnabled(not loading)
        self.btn_browse.setEnabled(not loading)
        self.btn_clear.setEnabled(not loading)
        self.progress_bar.setVisible(loading)
        if loading:
            self.progress_bar.setValue(0)
            self.status_label.setStyleSheet("color: #7a7974;")
            self.status_label.setText("Uploading…")
        else:
            self.status_label.setStyleSheet("")