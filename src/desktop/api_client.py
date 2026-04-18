# src/desktop/api_client.py

import logging
import os
from pathlib import Path
from typing import Any

import requests
from requests import Response, Session

logger = logging.getLogger(__name__)

DEFAULT_BASE_URL = "http://127.0.0.1:8000"
DEFAULT_TIMEOUT = int(os.getenv("API_TIMEOUT_SECONDS", "30"))
UPLOAD_TIMEOUT = int(os.getenv("API_UPLOAD_TIMEOUT_SECONDS", "180"))
PROCESSING_TIMEOUT = int(os.getenv("API_PROCESSING_TIMEOUT_SECONDS", "180"))


class APIError(Exception):
    def __init__(self, message: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code

    def __str__(self) -> str:
        if self.status_code is not None:
            return f"[{self.status_code}] {super().__str__()}"
        return str(super().__str__())


class APIClient:
    def __init__(self) -> None:
        self._base_url = os.getenv("API_BASE_URL", DEFAULT_BASE_URL).rstrip("/")
        self._session = Session()
        self._session.headers.update({"Accept": "application/json"})

    # ──────────────────────────────────────────────────────────
    # Token management
    # ──────────────────────────────────────────────────────────

    def set_token(self, token: str) -> None:
        self._session.headers["Authorization"] = f"Bearer {token}"

    def clear_token(self) -> None:
        self._session.headers.pop("Authorization", None)

    def has_token(self) -> bool:
        return "Authorization" in self._session.headers

    # ──────────────────────────────────────────────────────────
    # Internal helpers
    # ──────────────────────────────────────────────────────────

    def _url(self, path: str) -> str:
        return f"{self._base_url}/{path.lstrip('/')}"

    def _parse_response(self, response: Response) -> Any:
        try:
            payload = response.json()
        except Exception:
            payload = None

        if response.ok:
            return payload

        detail = None
        if isinstance(payload, dict):
            detail = payload.get("detail") or payload.get("message")

        if not detail:
            detail = response.text[:300] if response.text else response.reason

        if response.status_code == 401:
            self.clear_token()

        raise APIError(
            message=detail or "An unexpected error occurred.",
            status_code=response.status_code,
        )

    def _handle_request_exception(self, exc: Exception) -> None:
        if isinstance(exc, requests.exceptions.ConnectionError):
            raise APIError("Cannot connect to the backend. Make sure the server is running.")
        if isinstance(exc, requests.exceptions.Timeout):
            raise APIError("Request timed out. The server took too long to respond.")
        if isinstance(exc, requests.exceptions.RequestException):
            raise APIError(f"Request failed: {exc}")
        raise APIError(f"Unexpected request error: {exc}")

    def _get(
        self,
        path: str,
        params: dict[str, Any] | None = None,
        timeout: int = DEFAULT_TIMEOUT,
    ) -> Any:
        try:
            response = self._session.get(self._url(path), params=params, timeout=timeout)
        except Exception as exc:
            self._handle_request_exception(exc)
        return self._parse_response(response)

    def _post(
        self,
        path: str,
        json: Any = None,
        data: Any = None,
        files: Any = None,
        params: dict[str, Any] | None = None,
        timeout: int = DEFAULT_TIMEOUT,
    ) -> Any:
        try:
            response = self._session.post(
                self._url(path),
                json=json,
                data=data,
                files=files,
                params=params,
                timeout=timeout,
            )
        except Exception as exc:
            self._handle_request_exception(exc)
        return self._parse_response(response)

    def _put(
        self,
        path: str,
        json: Any = None,
        timeout: int = DEFAULT_TIMEOUT,
    ) -> Any:
        try:
            response = self._session.put(self._url(path), json=json, timeout=timeout)
        except Exception as exc:
            self._handle_request_exception(exc)
        return self._parse_response(response)

    def _delete(self, path: str, timeout: int = DEFAULT_TIMEOUT) -> Any:
        try:
            response = self._session.delete(self._url(path), timeout=timeout)
        except Exception as exc:
            self._handle_request_exception(exc)
        return self._parse_response(response)

    # ──────────────────────────────────────────────────────────
    # Health
    # ──────────────────────────────────────────────────────────

    def health_check(self) -> dict:
        result = self._get("/health", timeout=5)
        return result if isinstance(result, dict) else {}

    # ──────────────────────────────────────────────────────────
    # Auth
    # ──────────────────────────────────────────────────────────

    def register(
        self,
        email: str,
        username: str,
        password: str,
        full_name: str | None = None,
    ) -> dict:
        payload: dict[str, Any] = {
            "email": email,
            "username": username,
            "password": password,
        }
        if full_name:
            payload["full_name"] = full_name

        result = self._post("/auth/register", json=payload)
        if isinstance(result, dict) and result.get("access_token"):
            self.set_token(result["access_token"])
        return result if isinstance(result, dict) else {}

    def login(self, email: str, password: str) -> dict:
        result = self._post("/auth/login", json={"email": email, "password": password})
        if isinstance(result, dict) and result.get("access_token"):
            self.set_token(result["access_token"])
        return result if isinstance(result, dict) else {}

    def get_me(self) -> dict:
        result = self._get("/auth/me")
        return result if isinstance(result, dict) else {}

    def update_me(
        self,
        full_name: str | None = None,
        email: str | None = None,
        username: str | None = None,
        password: str | None = None,
    ) -> dict:
        payload: dict[str, Any] = {}
        if full_name is not None:
            payload["full_name"] = full_name
        if email is not None:
            payload["email"] = email
        if username is not None:
            payload["username"] = username
        if password is not None:
            payload["password"] = password
        result = self._put("/auth/me", json=payload)
        return result if isinstance(result, dict) else {}

    # ──────────────────────────────────────────────────────────
    # Receipts
    # ──────────────────────────────────────────────────────────

    def upload_receipt(self, file_path: str | Path) -> dict:
        path = Path(file_path)
        if not path.exists():
            raise APIError(f"File not found: {path}")

        mime_map = {
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".png": "image/png",
            ".webp": "image/webp",
            ".bmp": "image/bmp",
            ".tif": "image/tiff",
            ".tiff": "image/tiff",
            ".pdf": "application/pdf",
        }
        mime_type = mime_map.get(path.suffix.lower(), "application/octet-stream")

        with path.open("rb") as fh:
            files = {"file": (path.name, fh, mime_type)}
            result = self._post("/receipts/upload", files=files, timeout=UPLOAD_TIMEOUT)

        return result if isinstance(result, dict) else {}

    def list_receipts(
        self,
        page: int = 1,
        page_size: int = 20,
        category: str | None = None,
        status: str | None = None,
        search: str | None = None,
        needs_review: bool | None = None,
    ) -> dict:
        params: dict[str, Any] = {"page": page, "page_size": page_size}
        if category:
            params["category"] = category
        if status:
            params["status"] = status
        if search:
            params["search"] = search
        if needs_review is not None:
            params["needs_review"] = needs_review

        result = self._get("/receipts", params=params, timeout=PROCESSING_TIMEOUT)
        return result if isinstance(result, dict) else {}

    def get_receipt(self, receipt_id: int) -> dict:
        result = self._get(f"/receipts/{receipt_id}", timeout=PROCESSING_TIMEOUT)
        return result if isinstance(result, dict) else {}

    def update_receipt(
        self,
        receipt_id: int,
        merchant: str | None = None,
        total_amount: float | None = None,
        currency: str | None = None,
        category: str | None = None,
        subcategory: str | None = None,
        notes: str | None = None,
        receipt_date: str | None = None,
    ) -> dict:
        payload: dict[str, Any] = {}
        if merchant is not None:
            payload["merchant"] = merchant
        if total_amount is not None:
            payload["total_amount"] = total_amount
        if currency is not None:
            payload["currency"] = currency
        if category is not None:
            payload["category"] = category
        if subcategory is not None:
            payload["subcategory"] = subcategory
        if notes is not None:
            payload["notes"] = notes
        if receipt_date is not None:
            payload["receipt_date"] = receipt_date

        result = self._put(f"/receipts/{receipt_id}", json=payload, timeout=PROCESSING_TIMEOUT)
        return result if isinstance(result, dict) else {}

    def delete_receipt(self, receipt_id: int) -> dict | None:
        result = self._delete(f"/receipts/{receipt_id}")
        return result if isinstance(result, dict) or result is None else None

    def reprocess_receipt(self, receipt_id: int) -> dict:
        result = self._post(f"/receipts/{receipt_id}/reprocess", timeout=PROCESSING_TIMEOUT)
        return result if isinstance(result, dict) else {}

    def correct_category(
        self,
        receipt_id: int,
        category: str,
        subcategory: str | None = None,
    ) -> dict:
        payload: dict[str, Any] = {"category": category}
        if subcategory is not None:
            payload["subcategory"] = subcategory
        result = self._post(f"/receipts/{receipt_id}/correct-category", json=payload)
        return result if isinstance(result, dict) else {}

    # ──────────────────────────────────────────────────────────
    # Analytics
    # ──────────────────────────────────────────────────────────

    def get_analytics(self, period: str = "month") -> dict:
        result = self._get("/analytics", params={"period": period})
        return result if isinstance(result, dict) else {}

    def get_summary(self, period: str = "month") -> dict:
        result = self._get("/analytics/summary", params={"period": period})
        return result if isinstance(result, dict) else {}

    def get_recent(self, limit: int = 10) -> list:
        result = self._get("/analytics/recent", params={"limit": limit})
        return result if isinstance(result, list) else []

    # ──────────────────────────────────────────────────────────
    # Advisor
    # ──────────────────────────────────────────────────────────

    def get_insights(self, period: str = "month") -> list:
        result = self._get("/advisor/insights", params={"period": period})
        return result if isinstance(result, list) else []

    def get_auto_insights(self, period: str = "month") -> list:
        result = self._get("/advisor/insights/auto", params={"period": period})
        return result if isinstance(result, list) else []

    def ask_advisor(self, question: str, period: str = "month") -> dict:
        result = self._post(
            "/advisor/ask",
            json={"question": question},
            params={"period": period},
            timeout=PROCESSING_TIMEOUT,
        )
        return result if isinstance(result, dict) else {}


api = APIClient()