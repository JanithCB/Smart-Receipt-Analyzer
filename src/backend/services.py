# src/backend/services.py

import json
import logging
import os
import re
import uuid
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from fastapi import HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from backend.database import SessionLocal
from backend.models import CategoryFeedback, Receipt

logger = logging.getLogger(__name__)

ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tif", ".tiff", ".pdf"}
ALLOWED_MIME_TYPES = {
    "image/jpeg",
    "image/png",
    "image/webp",
    "image/bmp",
    "image/tiff",
    "application/pdf",
}

CATEGORY_RULES: dict[str, dict[str, list[str]]] = {
    "Groceries": {
        "General": ["supermarket", "grocery", "mart", "food city", "keells", "cargills", "arpico"],
    },
    "Dining": {
        "Restaurant": ["restaurant", "cafe", "coffee", "kfc", "mcdonald", "pizza", "burger", "bakery"],
    },
    "Transport": {
        "Fuel": ["fuel", "petrol", "diesel", "ceypetco", "ioc", "shell", "petron"],
        "Ride": ["uber", "pickme", "taxi", "bus", "train"],
    },
    "Utilities": {
        "Bills": ["electricity", "water", "internet", "dialog", "mobitel", "hutch", "airtel"],
    },
    "Healthcare": {
        "Medical": ["pharmacy", "hospital", "clinic", "medical", "health"],
    },
    "Shopping": {
        "Retail": ["store", "fashion", "clothing", "mall", "shop"],
    },
    "Entertainment": {
        "Leisure": ["cinema", "movie", "netflix", "spotify", "game"],
    },
    "Education": {
        "Learning": ["book", "course", "tuition", "school", "education"],
    },
    "Travel": {
        "Trip": ["hotel", "booking", "flight", "airline", "travel"],
    },
    "Finance": {
        "Banking": ["bank", "loan", "finance", "insurance"],
    },
    "Other": {
        "Uncategorized": [],
    },
}

TOTAL_LABEL_PATTERNS = [
    r"grand\s*total",
    r"take[\s-]*out\s*total",
    r"total\s*(?:rm|lkr|rs|usd|eur|gbp|inr)?\s*(?:incl(?:\.|usive)?\s*gst|inc(?:\.|usive)?\s*gst)?",
    r"total\s*amount",
    r"total\s*payable",
    r"amount\s*due",
    r"amount\s*paid",
    r"net\s*amount",
    r"net\s*total",
    r"balance\s*due",
    r"sub[\s-]*total",
    r"\bsubtotal\b",
    r"\bpayable\b",
    r"\bto\s*pay\b",
    r"\bcash\b",
    r"\btotal\b",
]

CURRENCY_PREFIX_PATTERN = r"(?:rs(?:\.|/)?|lkr|usd|eur|gbp|inr|rm|myr|\$|€|£|₹)?"
AMOUNT_PATTERN = r"([0-9]{1,3}(?:[,\s][0-9]{3})*(?:\.[0-9]{1,2})?|[0-9]+(?:\.[0-9]{1,2})?)"

BAD_NUMBER_CONTEXT = [
    "tel",
    "phone",
    "mobile",
    "invoice",
    "invoice no",
    "receipt no",
    "receipt#",
    "ref",
    "reference",
    "vat",
    "tin",
    "tax id",
    "card",
    "approval",
    "auth",
    "trace",
    "batch",
]

DATE_PATTERNS = [
    r"\b(\d{4}[-/]\d{1,2}[-/]\d{1,2})\b",
    r"\b(\d{1,2}[-/]\d{1,2}[-/]\d{2,4})\b",
    r"\b(\d{1,2}\s+[A-Za-z]{3,9}\s+\d{2,4})\b",
    r"\b([A-Za-z]{3,9}\s+\d{1,2},\s+\d{4})\b",
]

DATE_FORMATS = (
    "%Y-%m-%d",
    "%Y/%m/%d",
    "%d/%m/%Y",
    "%d-%m-%Y",
    "%d/%m/%y",
    "%d-%m-%y",
    "%m/%d/%Y",
    "%m-%d-%Y",
    "%m/%d/%y",
    "%m-%d-%y",
    "%d %B %Y",
    "%d %b %Y",
    "%B %d, %Y",
    "%b %d, %Y",
)


def get_uploads_dir() -> Path:
    return Path(os.getenv("UPLOADS_DIR", "uploads"))


def get_max_upload_size() -> int:
    return int(os.getenv("MAX_UPLOAD_SIZE_MB", "15")) * 1024 * 1024


def get_max_reasonable_receipt_amount() -> float:
    return float(os.getenv("MAX_REASONABLE_RECEIPT_AMOUNT", "1000000"))


# -------------------------------------------------------------------
# File and upload helpers
# -------------------------------------------------------------------

def validate_upload(file: UploadFile) -> None:
    filename = file.filename or ""
    extension = Path(filename).suffix.lower()
    content_type = (file.content_type or "").lower()

    if extension not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Unsupported file type. Allowed: JPEG, PNG, WEBP, BMP, TIFF, PDF.",
        )

    if content_type and content_type not in ALLOWED_MIME_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Unsupported MIME type for uploaded file.",
        )


async def save_upload_file(file: UploadFile, uploads_dir: Path) -> tuple[Path, str | None]:
    uploads_dir.mkdir(parents=True, exist_ok=True)

    original_name = file.filename or "receipt"
    suffix = Path(original_name).suffix.lower()
    safe_name = f"{uuid.uuid4().hex}{suffix}"
    destination = uploads_dir / safe_name

    max_upload_size = get_max_upload_size()
    size = 0

    try:
        with destination.open("wb") as buffer:
            while True:
                chunk = await file.read(1024 * 1024)
                if not chunk:
                    break

                size += len(chunk)
                if size > max_upload_size:
                    try:
                        destination.unlink(missing_ok=True)
                    except Exception:
                        pass
                    raise HTTPException(
                        status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                        detail=f"File too large. Maximum allowed size is {max_upload_size // (1024 * 1024)} MB.",
                    )

                buffer.write(chunk)

        return destination, file.content_type
    finally:
        try:
            await file.close()
        except Exception:
            pass


# -------------------------------------------------------------------
# OCR helpers
# -------------------------------------------------------------------

def _configure_tesseract() -> None:
    try:
        import pytesseract
    except Exception:
        return

    tesseract_cmd = os.getenv("TESSERACT_CMD")
    if tesseract_cmd:
        pytesseract.pytesseract.tesseract_cmd = tesseract_cmd


def extract_text_from_file(file_path: str | Path) -> str:
    path = Path(file_path)
    suffix = path.suffix.lower()

    if suffix == ".pdf":
        return extract_text_from_pdf(path)

    return extract_text_from_image(path)


def extract_text_from_image(image_path: Path) -> str:
    try:
        from PIL import Image, ImageFilter, ImageOps
        import pytesseract
    except Exception as exc:
        logger.warning("Image OCR dependencies unavailable: %s", exc)
        return ""

    try:
        _configure_tesseract()
        image = Image.open(image_path)
        image = ImageOps.exif_transpose(image)
        if image.mode not in ("L", "RGB"):
            image = image.convert("RGB")

        grayscale = ImageOps.grayscale(image)
        processed = grayscale.filter(ImageFilter.SHARPEN)
        text = pytesseract.image_to_string(processed, config="--psm 6")

        if not text.strip():
            text = pytesseract.image_to_string(image, config="--psm 6")

        return clean_ocr_text(text)
    except Exception as exc:
        logger.exception("Failed OCR on image %s: %s", image_path, exc)
        return ""


def extract_text_from_pdf(pdf_path: Path) -> str:
    try:
        from pdf2image import convert_from_path
        import pytesseract
    except Exception as exc:
        logger.warning("PDF OCR dependencies unavailable: %s", exc)
        return ""

    try:
        _configure_tesseract()
        pages = convert_from_path(str(pdf_path), dpi=180, first_page=1, last_page=3)
        texts: list[str] = []
        for page in pages:
            texts.append(pytesseract.image_to_string(page, config="--psm 6"))
        return clean_ocr_text("\n".join(texts))
    except Exception as exc:
        logger.exception("Failed OCR on PDF %s: %s", pdf_path, exc)
        return ""


# -------------------------------------------------------------------
# Text parsing helpers
# -------------------------------------------------------------------

def clean_ocr_text(text: str) -> str:
    if not text:
        return ""

    cleaned = text.replace("\x0c", " ")
    cleaned = cleaned.replace("\r", "\n")
    cleaned = re.sub(r"[ \t]+", " ", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()


def normalize_merchant(value: str) -> str:
    normalized = (value or "").strip().lower()
    normalized = re.sub(r"[^a-z0-9\s&]", "", normalized)
    normalized = re.sub(r"\s+", " ", normalized)
    return normalized


def parse_json_blob(text: str) -> dict[str, Any] | None:
    if not text:
        return None

    try:
        return json.loads(text)
    except Exception:
        pass

    match = re.search(r"\{.*\}", text, flags=re.DOTALL)
    if not match:
        return None

    try:
        return json.loads(match.group(0))
    except Exception:
        return None


def parse_date(text: str) -> datetime | None:
    if not text:
        return None

    for pattern in DATE_PATTERNS:
        for match in re.finditer(pattern, text, flags=re.IGNORECASE):
            raw = match.group(1).strip()
            for fmt in DATE_FORMATS:
                try:
                    return datetime.strptime(raw, fmt)
                except ValueError:
                    continue

    return None


def _number_has_bad_context(line: str, match_start: int) -> bool:
    prefix = line[max(0, match_start - 24):match_start].lower()
    return any(token in prefix for token in BAD_NUMBER_CONTEXT)


def _normalize_amount_str(raw: str) -> str | None:
    if not raw:
        return None

    value = raw.replace(" ", "").replace(",", "")
    if value.count(".") > 1:
        return None

    try:
        normalized = Decimal(value)
    except (InvalidOperation, ValueError):
        return None

    if normalized <= 0:
        return None

    return str(normalized)


def _parse_decimal_amount(raw: str) -> float | None:
    normalized = _normalize_amount_str(raw)
    if normalized is None:
        return None

    try:
        amount = float(Decimal(normalized))
    except (InvalidOperation, ValueError):
        return None

    if amount <= 0:
        return None

    max_reasonable_amount = get_max_reasonable_receipt_amount()
    if amount > max_reasonable_amount:
        return None

    return round(amount, 2)


def _extract_amount_candidates(line: str) -> list[float]:
    candidates: list[float] = []

    for match in re.finditer(
        rf"{CURRENCY_PREFIX_PATTERN}\s*{AMOUNT_PATTERN}",
        line,
        flags=re.IGNORECASE,
    ):
        if _number_has_bad_context(line, match.start(1)):
            continue

        amount = _parse_decimal_amount(match.group(1))
        if amount is not None:
            candidates.append(amount)

    return candidates


def parse_total_amount(text: str) -> float | None:
    if not text:
        return None

    lines = [line.strip() for line in text.splitlines() if line.strip()]

    scored_candidates: list[tuple[int, float]] = []

    for line in lines:
        lower = line.lower()

        for label in TOTAL_LABEL_PATTERNS:
            if re.search(label, lower, flags=re.IGNORECASE):
                for amount in _extract_amount_candidates(line):
                    score = 100
                    if "grand total" in lower:
                        score += 20
                    if "takeout total" in lower or "take out total" in lower:
                        score += 15
                    if "subtotal" in lower or "sub total" in lower:
                        score -= 20
                    scored_candidates.append((score, amount))

    if scored_candidates:
        scored_candidates.sort(key=lambda item: (item[0], item[1]), reverse=True)
        return scored_candidates[0][1]

    fallback_candidates: list[float] = []
    for line in lines:
        lower = line.lower()
        if any(token in lower for token in BAD_NUMBER_CONTEXT):
            continue
        fallback_candidates.extend(_extract_amount_candidates(line))

    if not fallback_candidates:
        return None

    return max(fallback_candidates)


def parse_merchant(text: str) -> str | None:
    if not text:
        return None

    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not lines:
        return None

    ignored_prefixes = (
        "invoice",
        "receipt",
        "tax",
        "vat",
        "tel",
        "phone",
        "date",
        "time",
        "table",
        "cashier",
    )

    for line in lines[:8]:
        lowered = line.lower()
        if any(lowered.startswith(prefix) for prefix in ignored_prefixes):
            continue
        if re.search(r"\d{3,}", line):
            continue
        if len(line) < 2:
            continue
        return line[:120]

    return lines[0][:120] if lines else None


def apply_category_feedback(db: Session, merchant: str | None) -> tuple[str | None, str | None]:
    if not merchant:
        return None, None

    normalized = normalize_merchant(merchant)
    if not normalized:
        return None, None

    latest_feedback = (
        db.query(CategoryFeedback)
        .filter(CategoryFeedback.merchant_normalized == normalized)
        .order_by(CategoryFeedback.created_at.desc())
        .first()
    )

    if not latest_feedback:
        return None, None

    return latest_feedback.user_corrected_category, latest_feedback.user_corrected_subcategory


def categorize_receipt(merchant: str | None, text: str | None = None) -> tuple[str, str]:
    merchant_norm = normalize_merchant(merchant or "")
    text_norm = (text or "").lower()

    for category, subcats in CATEGORY_RULES.items():
        for subcategory, keywords in subcats.items():
            if any(keyword in merchant_norm or keyword in text_norm for keyword in keywords):
                return category, subcategory

    return "Other", "Uncategorized"


# -------------------------------------------------------------------
# Background receipt processing
# -------------------------------------------------------------------

def process_receipt_background(receipt_id: int) -> None:
    db = SessionLocal()

    try:
        receipt = db.query(Receipt).filter(Receipt.id == receipt_id).first()
        if not receipt:
            logger.warning("Receipt %s not found for background processing", receipt_id)
            return

        receipt.processing_status = "processing"
        db.add(receipt)
        db.commit()
        db.refresh(receipt)

        extracted_text = extract_text_from_file(receipt.file_path)
        merchant = parse_merchant(extracted_text)
        total_amount = parse_total_amount(extracted_text)
        receipt_date = parse_date(extracted_text)

        category = None
        subcategory = None
        category_source = "rule_based"

        corrected_category, corrected_subcategory = apply_category_feedback(db, merchant)
        if corrected_category:
            category = corrected_category
            subcategory = corrected_subcategory
            category_source = "user_correction"
        else:
            category, subcategory = categorize_receipt(merchant, extracted_text)

        receipt.ocr_text = extracted_text or None
        receipt.merchant = merchant
        receipt.total_amount = total_amount
        receipt.receipt_date = receipt_date
        receipt.category = category
        receipt.subcategory = subcategory
        receipt.category_source = category_source
        receipt.currency = receipt.currency or "LKR"

        has_meaningful_result = any(
            [
                bool(extracted_text and extracted_text.strip()),
                merchant is not None,
                total_amount is not None,
                receipt_date is not None,
            ]
        )

        receipt.needs_review = total_amount is None

        if total_amount is not None:
            receipt.processing_status = "done"
        elif has_meaningful_result:
            receipt.processing_status = "failed"
        else:
            receipt.processing_status = "failed"

        db.add(receipt)
        db.commit()
        db.refresh(receipt)

        logger.info(
            "Processed receipt %s | status=%s merchant=%s amount=%s date=%s category=%s",
            receipt.id,
            receipt.processing_status,
            receipt.merchant,
            receipt.total_amount,
            receipt.receipt_date,
            receipt.category,
        )

    except Exception as exc:
        logger.exception("Receipt processing failed for %s: %s", receipt_id, exc)
        try:
            db.rollback()
            receipt = db.query(Receipt).filter(Receipt.id == receipt_id).first()
            if receipt:
                receipt.processing_status = "failed"
                receipt.needs_review = True
                db.add(receipt)
                db.commit()
        except Exception:
            logger.exception("Failed to mark receipt %s as failed after exception", receipt_id)
    finally:
        db.close()


# -------------------------------------------------------------------
# Insights and advisor helpers
# -------------------------------------------------------------------

def generate_insights(summary: dict[str, Any]) -> list[dict[str, Any]]:
    insights: list[dict[str, Any]] = []

    total_spend = float(summary.get("total_spend", 0) or 0)
    receipt_count = int(summary.get("receipt_count", 0) or 0)
    average_spend = float(summary.get("average_spend", 0) or 0)
    top_category = summary.get("top_category")
    anomalies = summary.get("anomalies", [])

    if receipt_count == 0:
        insights.append(
            {
                "id": "empty-state",
                "type": "tip",
                "title": "No receipts yet",
                "message": "Upload receipts to start tracking spending patterns and receive insights.",
                "severity": "info",
            }
        )
        return insights

    if top_category:
        insights.append(
            {
                "id": "top-category",
                "type": "trend",
                "title": "Top spending category",
                "message": f"Your highest spending category is {top_category}.",
                "severity": "info",
                "category": top_category,
            }
        )

    if average_spend > 0:
        insights.append(
            {
                "id": "avg-spend",
                "type": "tip",
                "title": "Average receipt value",
                "message": f"Your average receipt amount is {average_spend:.2f}.",
                "severity": "info",
                "amount": average_spend,
            }
        )

    if total_spend > 0 and receipt_count >= 5:
        insights.append(
            {
                "id": "activity-level",
                "type": "trend",
                "title": "Spending activity",
                "message": f"You logged {receipt_count} receipts with a total spend of {total_spend:.2f}.",
                "severity": "info",
                "amount": total_spend,
            }
        )

    for index, anomaly in enumerate(anomalies[:2], start=1):
        insights.append(
            {
                "id": f"anomaly-{index}",
                "type": "anomaly",
                "title": "Unusual spending detected",
                "message": anomaly.get("message", "An unusual spending pattern was detected."),
                "severity": "warning",
                "category": anomaly.get("category"),
                "amount": anomaly.get("amount"),
                "metadata": anomaly.get("metadata"),
            }
        )

    return insights[:6]


def generate_auto_insights(summary: dict[str, Any]) -> list[dict[str, Any]]:
    insights = generate_insights(summary)
    category_breakdown = summary.get("category_breakdown", [])

    if category_breakdown:
        first = category_breakdown[0]
        percentage = float(first.get("percentage", 0) or 0)
        if percentage >= 40:
            insights.append(
                {
                    "id": "concentration-risk",
                    "type": "alert",
                    "title": "Spending is concentrated",
                    "message": f"{first.get('category', 'One category')} accounts for {percentage:.1f}% of your spending.",
                    "severity": "warning",
                    "category": first.get("category"),
                    "amount": first.get("amount"),
                }
            )

    return insights[:6]


def answer_advisor_question(question: str, summary: dict[str, Any]) -> dict[str, Any]:
    question_lower = question.lower()
    total_spend = float(summary.get("total_spend", 0) or 0)
    top_category = summary.get("top_category")
    average_spend = float(summary.get("average_spend", 0) or 0)
    anomalies = summary.get("anomalies", [])
    breakdown = summary.get("category_breakdown", [])

    sources = ["Local analytics summary", "Rule-based advisor fallback"]
    insights = generate_auto_insights(summary)

    if total_spend == 0:
        return {
            "answer": "I do not have enough spending data yet. Upload more receipts so I can give advice based on your actual patterns.",
            "sources": sources,
            "insights": insights,
        }

    if "food" in question_lower or "grocery" in question_lower or "dining" in question_lower:
        food_categories = {"Groceries", "Dining"}
        food_total = sum(float(item.get("amount", 0) or 0) for item in breakdown if item.get("category") in food_categories)
        answer = (
            f"You can reduce food spending by separating groceries from dining, setting a weekly cap, "
            f"and reviewing repeated small purchases. Your current combined food-related spend is about {food_total:.2f}."
        )
        return {"answer": answer, "sources": sources, "insights": insights}

    if "category" in question_lower or "spend most" in question_lower:
        answer = (
            f"Your top spending category is {top_category or 'not available yet'}. "
            f"Your total spend is {total_spend:.2f}, and your average receipt amount is {average_spend:.2f}."
        )
        return {"answer": answer, "sources": sources, "insights": insights}

    if "anomal" in question_lower or "unusual" in question_lower:
        if anomalies:
            answer = "I detected unusual spending patterns. " + " ".join(a.get("message", "") for a in anomalies[:3]).strip()
        else:
            answer = "I did not detect any strong spending anomalies in the selected period."
        return {"answer": answer, "sources": sources, "insights": insights}

    answer = (
        f"Based on your current receipts, your total spend is {total_spend:.2f}"
        f"{f', with {top_category} as your top category' if top_category else ''}. "
        "A practical next step is to review the top category, reduce repeated discretionary purchases, "
        "and compare high-value receipts against your monthly budget."
    )
    return {"answer": answer, "sources": sources, "insights": insights}


# -------------------------------------------------------------------
# Shared utility helpers
# -------------------------------------------------------------------

def safe_float(value: Any) -> float | None:
    try:
        if value is None or value == "":
            return None
        return float(value)
    except (TypeError, ValueError):
        return None