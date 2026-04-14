# src/desktop/workers.py
from PySide6.QtCore import QObject, QRunnable, Signal, Slot, QThread
from desktop.api_client import api


class WorkerSignals(QObject):
    finished = Signal(object)
    error    = Signal(str)


class ApiWorker(QRunnable):
    """Generic worker — wraps any callable and runs it off the GUI thread."""
    def __init__(self, fn, *args, **kwargs):
        super().__init__()
        self.fn      = fn
        self.args    = args
        self.kwargs  = kwargs
        self.signals = WorkerSignals()

    @Slot()
    def run(self):
        try:
            result = self.fn(*self.args, **self.kwargs)
            self.signals.finished.emit(result)
        except Exception as e:
            self.signals.error.emit(str(e))


# ── Receipt list / detail / update / delete / reprocess ──────────────────────

class ListReceiptsWorker(QRunnable):
    def __init__(self, page=1, page_size=20, category=None,
                 status=None, needs_review=None, search=None):
        super().__init__()
        self.kwargs  = dict(page=page, page_size=page_size,
                            category=category, status=status,
                            needs_review=needs_review, search=search)
        self.signals = WorkerSignals()

    @Slot()
    def run(self):
        try:
            self.signals.finished.emit(api.list_receipts(**self.kwargs))
        except Exception as e:
            self.signals.error.emit(str(e))


class GetReceiptWorker(QRunnable):
    def __init__(self, receipt_id: int):
        super().__init__()
        self.receipt_id = receipt_id
        self.signals    = WorkerSignals()

    @Slot()
    def run(self):
        try:
            self.signals.finished.emit(api.get_receipt(self.receipt_id))
        except Exception as e:
            self.signals.error.emit(str(e))


class UpdateReceiptWorker(QRunnable):
    def __init__(self, receipt_id: int, **kwargs):
        super().__init__()
        self.receipt_id = receipt_id
        self.kwargs     = kwargs
        self.signals    = WorkerSignals()

    @Slot()
    def run(self):
        try:
            self.signals.finished.emit(
                api.update_receipt(self.receipt_id, **self.kwargs)
            )
        except Exception as e:
            self.signals.error.emit(str(e))


class DeleteReceiptWorker(QRunnable):
    def __init__(self, receipt_id: int):
        super().__init__()
        self.receipt_id = receipt_id
        self.signals    = WorkerSignals()

    @Slot()
    def run(self):
        try:
            self.signals.finished.emit(api.delete_receipt(self.receipt_id))
        except Exception as e:
            self.signals.error.emit(str(e))


class ReprocessReceiptWorker(QRunnable):
    def __init__(self, receipt_id: int):
        super().__init__()
        self.receipt_id = receipt_id
        self.signals    = WorkerSignals()

    @Slot()
    def run(self):
        try:
            self.signals.finished.emit(api.reprocess_receipt(self.receipt_id))
        except Exception as e:
            self.signals.error.emit(str(e))


class CorrectCategoryWorker(QRunnable):
    def __init__(self, receipt_id: int, category: str, subcategory: str = None):
        super().__init__()
        self.receipt_id  = receipt_id
        self.category    = category
        self.subcategory = subcategory
        self.signals     = WorkerSignals()

    @Slot()
    def run(self):
        try:
            self.signals.finished.emit(
                api.correct_category(self.receipt_id, self.category, self.subcategory)
            )
        except Exception as e:
            self.signals.error.emit(str(e))


# ── Upload ────────────────────────────────────────────────────────────────────

class UploadReceiptWorker(QRunnable):
    """Uploads a list of file paths one by one."""

    class Signals(QObject):
        file_done  = Signal(str, object)  # (path, result)
        file_error = Signal(str, str)     # (path, error)
        finished   = Signal(object)       # final summary dict
        error      = Signal(str)

    def __init__(self, paths: list):
        super().__init__()
        self.paths   = paths
        self.signals = UploadReceiptWorker.Signals()

    @Slot()
    def run(self):
        results = []
        errors  = []
        for path in self.paths:
            try:
                result = api.upload_receipt(path)
                results.append(result)
                self.signals.file_done.emit(path, result)
            except Exception as e:
                errors.append({"file": path, "error": str(e)})
                self.signals.file_error.emit(path, str(e))
        self.signals.finished.emit({"results": results, "errors": errors})


# ── Analytics ─────────────────────────────────────────────────────────────────

class GetSummaryWorker(QRunnable):
    def __init__(self, period="month", year=None, month=None):
        super().__init__()
        self.period  = period
        self.year    = year
        self.month   = month
        self.signals = WorkerSignals()

    @Slot()
    def run(self):
        try:
            self.signals.finished.emit(
                api.get_summary(self.period, self.year, self.month)
            )
        except Exception as e:
            self.signals.error.emit(str(e))


class GetRecentWorker(QRunnable):
    def __init__(self, limit=20):
        super().__init__()
        self.limit   = limit
        self.signals = WorkerSignals()

    @Slot()
    def run(self):
        try:
            self.signals.finished.emit(api.get_recent(self.limit))
        except Exception as e:
            self.signals.error.emit(str(e))


# ── AI Advisor ────────────────────────────────────────────────────────────────

class GetInsightsWorker(QRunnable):
    def __init__(self):
        super().__init__()
        self.signals = WorkerSignals()

    @Slot()
    def run(self):
        try:
            self.signals.finished.emit(api.get_insights())
        except Exception as e:
            self.signals.error.emit(str(e))


class GetAutoInsightsWorker(QRunnable):
    def __init__(self):
        super().__init__()
        self.signals = WorkerSignals()

    @Slot()
    def run(self):
        try:
            self.signals.finished.emit(api.get_auto_insights())
        except Exception as e:
            self.signals.error.emit(str(e))


class AskAdvisorWorker(QRunnable):
    def __init__(self, question: str):
        super().__init__()
        self.question = question
        self.signals  = WorkerSignals()

    @Slot()
    def run(self):
        try:
            self.signals.finished.emit(api.ask_advisor(self.question))
        except Exception as e:
            self.signals.error.emit(str(e))


# ── Health check ──────────────────────────────────────────────────────────────

class HealthCheckWorker(QThread):
    finished = Signal(dict)

    def run(self):
        try:
            ok = api.health_check()
            self.finished.emit({"healthy": ok})
        except Exception:
            self.finished.emit({"healthy": False})