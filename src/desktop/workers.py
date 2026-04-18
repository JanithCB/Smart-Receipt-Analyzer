# src/desktop/workers.py

import logging
from pathlib import Path
from typing import Any, Callable

from PySide6.QtCore import QObject, QRunnable, QThread, Signal, Slot

from desktop.api_client import APIError, api

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────────────────────
# Base signal carrier
# ──────────────────────────────────────────────────────────────────────────────

class WorkerSignals(QObject):
    finished = Signal()
    error = Signal(str)
    result = Signal(object)
    progress = Signal(int)


# ──────────────────────────────────────────────────────────────────────────────
# Generic API worker
# ──────────────────────────────────────────────────────────────────────────────

class ApiWorker(QRunnable):
    """
    Run a callable off the UI thread.
    """

    def __init__(self, fn: Callable[[], Any]) -> None:
        super().__init__()
        self._fn = fn
        self.signals = WorkerSignals()
        self.setAutoDelete(True)

    @Slot()
    def run(self) -> None:
        try:
            result = self._fn()
            self.signals.result.emit(result)
        except APIError as exc:
            logger.warning("ApiWorker APIError: %s", exc)
            self.signals.error.emit(str(exc))
        except Exception as exc:
            logger.exception("ApiWorker unexpected error: %s", exc)
            self.signals.error.emit(f"Unexpected error: {exc}")
        finally:
            self.signals.finished.emit()


# ──────────────────────────────────────────────────────────────────────────────
# Upload worker
# ──────────────────────────────────────────────────────────────────────────────

class UploadWorkerSignals(QObject):
    finished = Signal()
    error = Signal(str, str)          # filename, message
    file_done = Signal(str, object)   # filename, receipt dict
    progress = Signal(int, int)       # completed, total


class UploadWorker(QRunnable):
    """
    Upload files sequentially, one at a time.
    """

    def __init__(self, file_paths: list[str | Path]) -> None:
        super().__init__()
        self._file_paths = [Path(p) for p in file_paths]
        self.signals = UploadWorkerSignals()
        self.setAutoDelete(True)

    @Slot()
    def run(self) -> None:
        total = len(self._file_paths)
        completed = 0

        for file_path in self._file_paths:
            try:
                receipt = api.upload_receipt(file_path)
                self.signals.file_done.emit(file_path.name, receipt)
            except APIError as exc:
                logger.warning("Upload failed for %s: %s", file_path.name, exc)
                self.signals.error.emit(file_path.name, str(exc))
            except Exception as exc:
                logger.exception("Unexpected upload error for %s: %s", file_path.name, exc)
                self.signals.error.emit(file_path.name, f"Unexpected error: {exc}")
            finally:
                completed += 1
                self.signals.progress.emit(completed, total)

        self.signals.finished.emit()


# ──────────────────────────────────────────────────────────────────────────────
# Health check worker
# ──────────────────────────────────────────────────────────────────────────────

class HealthCheckWorker(QThread):
    healthy = Signal(dict)
    unreachable = Signal(str)

    def run(self) -> None:
        try:
            result = api.health_check()
            self.healthy.emit(result if isinstance(result, dict) else {})
        except APIError as exc:
            self.unreachable.emit(str(exc))
        except Exception as exc:
            self.unreachable.emit(f"Health check failed: {exc}")


# ──────────────────────────────────────────────────────────────────────────────
# Convenience factory functions
# ──────────────────────────────────────────────────────────────────────────────

def make_login_worker(email: str, password: str) -> ApiWorker:
    return ApiWorker(lambda: api.login(email, password))


def make_register_worker(
    email: str,
    username: str,
    password: str,
    full_name: str | None = None,
) -> ApiWorker:
    return ApiWorker(lambda: api.register(email, username, password, full_name))


def make_get_me_worker() -> ApiWorker:
    return ApiWorker(api.get_me)


def make_update_me_worker(
    full_name: str | None = None,
    email: str | None = None,
    username: str | None = None,
    password: str | None = None,
) -> ApiWorker:
    return ApiWorker(
        lambda: api.update_me(
            full_name=full_name,
            email=email,
            username=username,
            password=password,
        )
    )


def make_list_receipts_worker(
    page: int = 1,
    page_size: int = 20,
    category: str | None = None,
    status: str | None = None,
    search: str | None = None,
    needs_review: bool | None = None,
) -> ApiWorker:
    return ApiWorker(
        lambda: api.list_receipts(
            page=page,
            page_size=page_size,
            category=category,
            status=status,
            search=search,
            needs_review=needs_review,
        )
    )


def make_get_receipt_worker(receipt_id: int) -> ApiWorker:
    return ApiWorker(lambda: api.get_receipt(receipt_id))


def make_update_receipt_worker(
    receipt_id: int,
    merchant: str | None = None,
    total_amount: float | None = None,
    currency: str | None = None,
    category: str | None = None,
    subcategory: str | None = None,
    notes: str | None = None,
    receipt_date: str | None = None,
) -> ApiWorker:
    return ApiWorker(
        lambda: api.update_receipt(
            receipt_id,
            merchant=merchant,
            total_amount=total_amount,
            currency=currency,
            category=category,
            subcategory=subcategory,
            notes=notes,
            receipt_date=receipt_date,
        )
    )


def make_delete_receipt_worker(receipt_id: int) -> ApiWorker:
    return ApiWorker(lambda: api.delete_receipt(receipt_id))


def make_reprocess_receipt_worker(receipt_id: int) -> ApiWorker:
    return ApiWorker(lambda: api.reprocess_receipt(receipt_id))


def make_correct_category_worker(
    receipt_id: int,
    category: str,
    subcategory: str | None = None,
) -> ApiWorker:
    return ApiWorker(lambda: api.correct_category(receipt_id, category, subcategory))


def make_analytics_worker(period: str = "month") -> ApiWorker:
    return ApiWorker(lambda: api.get_analytics(period))


def make_summary_worker(period: str = "month") -> ApiWorker:
    return ApiWorker(lambda: api.get_summary(period))


def make_recent_receipts_worker(limit: int = 10) -> ApiWorker:
    return ApiWorker(lambda: api.get_recent(limit))


def make_insights_worker(period: str = "month") -> ApiWorker:
    return ApiWorker(lambda: api.get_insights(period))


def make_auto_insights_worker(period: str = "month") -> ApiWorker:
    return ApiWorker(lambda: api.get_auto_insights(period))


def make_ask_advisor_worker(question: str, period: str = "month") -> ApiWorker:
    return ApiWorker(lambda: api.ask_advisor(question=question, period=period))


# ──────────────────────────────────────────────────────────────────────────────
# Backward-compatible aliases
# views.py currently imports these names without underscores.
# Keep both styles so we don't need to touch views.py right now.
# ──────────────────────────────────────────────────────────────────────────────

makeloginworker = make_login_worker
makeregisterworker = make_register_worker
makegetmeworker = make_get_me_worker
makeupdatemeworker = make_update_me_worker

makelistreceiptsworker = make_list_receipts_worker
makegetreceiptworker = make_get_receipt_worker
makeupdatereceiptworker = make_update_receipt_worker
makedeletereceiptworker = make_delete_receipt_worker
makereprocessreceiptworker = make_reprocess_receipt_worker
makecorrectcategoryworker = make_correct_category_worker

makeanalyticsworker = make_analytics_worker
makesummaryworker = make_summary_worker
makerecentreceiptsworker = make_recent_receipts_worker

makeinsightsworker = make_insights_worker
makeautoinsightsworker = make_auto_insights_worker
makeaskadvisorworker = make_ask_advisor_worker