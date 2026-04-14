# src/desktop/api_client.py
import os
import requests
from typing import Optional


BASE_URL = os.getenv("API_BASE_URL", "http://127.0.0.1:8000")
TIMEOUT_DEFAULT = 120
TIMEOUT_UPLOAD  = 600
TIMEOUT_AI      = 300


class APIClient:
    def __init__(self, base_url: str = BASE_URL):
        self.base_url = base_url.rstrip("/")
        self.session  = requests.Session()
        self.token: Optional[str] = None

    def set_token(self, token: Optional[str]):
        self.token = token
        self.session.headers.pop("Authorization", None)
        if token:
            self.session.headers["Authorization"] = f"Bearer {token}"

    def logout(self):
        self.set_token(None)

    def _handle(self, response: requests.Response):
        if response.ok:
            return response.json()
        try:
            detail = response.json().get("detail", response.text)
        except Exception:
            detail = response.text
        raise RuntimeError(detail)

    # -- Auth ------------------------------------------------------------------

    # Fix #6: was missing username and full_name fields
    def register(self, email: str, username: str, password: str, full_name: str = ""):
        r = self.session.post(
            f"{self.base_url}/auth/register",
            json={
                "email":     email,
                "username":  username,   # was missing
                "password":  password,
                "full_name": full_name,  # was missing
            },
            timeout=TIMEOUT_DEFAULT,
        )
        data = self._handle(r)
        self.set_token(data["access_token"])
        return data

    def login(self, email: str, password: str):
        r = self.session.post(
            f"{self.base_url}/auth/login",
            json={"email": email, "password": password},
            timeout=TIMEOUT_DEFAULT,
        )
        data = self._handle(r)
        self.set_token(data["access_token"])
        return data

    def me(self):
        r = self.session.get(
            f"{self.base_url}/auth/me",
            timeout=TIMEOUT_DEFAULT,
        )
        return self._handle(r)

    # -- Analytics -------------------------------------------------------------

    def get_summary(self, period: str = "month", year=None, month=None):
        params = {"period": period}
        if year  is not None: params["year"]  = year
        if month is not None: params["month"] = month
        r = self.session.get(
            f"{self.base_url}/analytics/summary",
            params=params,
            timeout=TIMEOUT_DEFAULT,
        )
        return self._handle(r)

    def get_analytics(self, period: str = "month"):
        r = self.session.get(
            f"{self.base_url}/analytics",
            params={"period": period},
            timeout=TIMEOUT_DEFAULT,
        )
        return self._handle(r)

    def get_recent(self, limit: int = 20):
        r = self.session.get(
            f"{self.base_url}/analytics/recent",
            params={"limit": limit},
            timeout=TIMEOUT_DEFAULT,
        )
        return self._handle(r)

    # -- Receipts --------------------------------------------------------------

    def list_receipts(
        self,
        page: int = 1,
        page_size: int = 20,
        category: Optional[str] = None,
        status: Optional[str] = None,
        needs_review: Optional[bool] = None,
        search: Optional[str] = None,
    ):
        params = {"page": page, "page_size": page_size}
        if category     is not None: params["category"]     = category
        if status       is not None: params["status"]       = status
        if needs_review is not None: params["needs_review"] = needs_review
        if search       is not None: params["search"]       = search
        r = self.session.get(
            f"{self.base_url}/receipts",
            params=params,
            timeout=TIMEOUT_DEFAULT,
        )
        return self._handle(r)

    def get_receipt(self, receipt_id: int):
        r = self.session.get(
            f"{self.base_url}/receipts/{receipt_id}",
            timeout=TIMEOUT_DEFAULT,
        )
        return self._handle(r)

    def update_receipt(self, receipt_id: int, **kwargs):
        r = self.session.put(
            f"{self.base_url}/receipts/{receipt_id}",
            json=kwargs,
            timeout=TIMEOUT_DEFAULT,
        )
        return self._handle(r)

    def delete_receipt(self, receipt_id: int):
        r = self.session.delete(
            f"{self.base_url}/receipts/{receipt_id}",
            timeout=TIMEOUT_DEFAULT,
        )
        if r.status_code == 204:
            return {}
        return self._handle(r)

    def reprocess_receipt(self, receipt_id: int):
        r = self.session.post(
            f"{self.base_url}/receipts/{receipt_id}/reprocess",
            timeout=TIMEOUT_DEFAULT,
        )
        return self._handle(r)

    def correct_category(
        self,
        receipt_id: int,
        corrected_category: str,
        corrected_subcategory: Optional[str] = None,
    ):
        r = self.session.post(
            f"{self.base_url}/receipts/correct-category",
            json={
                "receipt_id":            receipt_id,
                "corrected_category":    corrected_category,
                "corrected_subcategory": corrected_subcategory,
            },
            timeout=TIMEOUT_DEFAULT,
        )
        return self._handle(r)

    def upload_receipt(self, path: str):
        with open(path, "rb") as f:
            r = self.session.post(
                f"{self.base_url}/receipts/upload",
                files={"file": (os.path.basename(path), f, "application/octet-stream")},
                timeout=TIMEOUT_UPLOAD,
            )
        return self._handle(r)

    def upload_receipts(self, paths: list):
        results = []
        errors  = []
        for path in paths:
            try:
                result = self.upload_receipt(path)
                results.append(result)
            except Exception as e:
                errors.append({"file": path, "error": str(e)})
        return {"results": results, "errors": errors}

    # -- AI Advisor ------------------------------------------------------------

    def get_insights(self):
        r = self.session.get(
            f"{self.base_url}/advisor/insights",
            timeout=TIMEOUT_AI,
        )
        return self._handle(r)

    def get_auto_insights(self):
        r = self.session.get(
            f"{self.base_url}/advisor/insights/auto",
            timeout=TIMEOUT_AI,
        )
        return self._handle(r)

    def ask_advisor(self, question: str):
        r = self.session.post(
            f"{self.base_url}/advisor/ask",
            json={"question": question},
            timeout=TIMEOUT_AI,
        )
        return self._handle(r)

    # -- Health ----------------------------------------------------------------

    def health_check(self):
        try:
            r = self.session.get(
                f"{self.base_url}/health",
                timeout=5,
            )
            return r.ok
        except Exception:
            return False


# Single shared instance used by all desktop views
api = APIClient()