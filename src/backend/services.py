# src/backend/services.py

import io
import logging
import os
import re
import shutil
import uuid
from collections import Counter
from datetime import datetime
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
MAX_UPLOAD_SIZE = int(os.getenv("MAX_UPLOAD_SIZE_MB", "15")) * 1024 * 1024
DEFAULT_UPLOADS_DIR = Path(os.getenv("UPLOADS_DIR", "uploads"))

CATEGORY_RULES: dict[str, dict[str, list[str]]] = {
    "Groceries": {
        "General": ["supermarket", "grocery", "mart", "food city", "keells", "cargills", "arpico"],
    },
    "Dining": {
        "Restaurant": ["restaurant", "cafe", "coffee", "kfc", "mcdonald", "pizza", "burger", "bakery"],
    },
    "Transport": {
        "Fuel": ["fuel", "petrol", "diesel", "ceypetco", "ioc", "shell"],
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


# -------------------------------------------------------------------
# File and upload helpers
# -------------------------------------------------------------------


def get_uploads_dir() -> Path:
    return DEFAULT_UPLOADS_DIR


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

    size = 0
    with destination.open("wb") as buffer:
        while True:
            chunk = await file.read(1024 * 1024)
            if not chunk:
                break
            size += len(chunk)
            if size > MAX_UPLOAD_SIZE:
                buffer.close()
                try:
                    destination.unlink(missing_ok=True)
                except Exception:
                    pass
                raise HTTPException(
                    status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                    detail=f"File too large. Maximum allowed size is {MAX_UPLOAD_SIZE // (1024 * 1024)} MB.",
                )
            buffer.write(chunk)

    await file.close()
    return destination, file.content_type


# -------------------------------------------------------------------
# OCR helpers
# -------------------------------------------------------------------


def extract_text_from_file(file_path: str | Path) -> str:
    path = Path(file_path)
    suffix = path.suffix.lower()

    if suffix == ".pdf":
        return extract_text_from_pdf(path)

    return extract_text_from_image(path)


def extract_text_from_image(image_path: Path) -> str:
    try:
        from PIL import Image
        import pytesseract
    except Exception as exc:
        logger.warning("Image OCR dependencies unavailable: %s", exc)
        return ""

    try:
        image = Image.open(image_path)
        text = pytesseract.image_to_string(image)
        return clean_ocr_text(text)
    except Exception as exc:
        logger.exception("Failed OCR on image %s: %s", image_path, exc)
        return ""


def extract_text_from_pdf(pdf_path: Path) -> str:
    """
    PDF OCR fallback behavior:
    - Try pdf2image + pytesseract if available.
    - If dependencies are missing, return empty text rather than crashing.
    """
    try:
        from pdf2image import convert_from_path
        import pytesseract
    except Exception as exc:
        logger.warning("PDF OCR dependencies unavailable: %s", exc)
        return ""

    try:
        pages = convert_from_path(str(pdf_path), dpi=200)
        texts: list[str] = []
        for page in pages[:5]:
            texts.append(pytesseract.image_to_string(page))
        return clean_ocr_text("\n".join(texts))
    except Exception as exc:
        logger.exception("Failed OCR on PDF %s: %s", pdf_path, exc)
        return ""


# -------------------------------------------------------------------
# Text parsing helpers
# -------------------------------------------------------------------


def clean_ocr_text(text: str) -> str:
    text = text.replace("\x0c", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def detect_language(text: str) -> str | None:
    if not text.strip():
        return None

    try:
        from langdetect import detect
        return detect(text)
    except Exception:
        return None


def translate_to_english(text: str, source_language: str | None) -> str:
    if not text.strip():
        return text

    if not source_language or source_language == "en":
        return text

    try:
        from deep_translator import GoogleTranslator
        translated = GoogleTranslator(source=source_language, target="en").translate(text)
        return translated or text
    except Exception:
        return text


def normalize_merchant(merchant: str) -> str:
    merchant = merchant.lower().strip()
    merchant = re.sub(r"[^a-z0-9\s]", "", merchant)
    merchant = re.sub(r"\s+", " ", merchant)
    return merchant


def parse_currency(text: str) -> str | None:
    currency_patterns = {
        "LKR": [r"\brs\.?\b", r"\blkr\b", r"රු"],
        "USD": [r"\busd\b", r"\$\s?\d"],
        "EUR": [r"\beur\b", r"€"],
        "GBP": [r"\bgbp\b", r"£"],
        "INR": [r"\binr\b", r"₹"],
    }

    lowered = text.lower()
    for code, patterns in currency_patterns.items():
        for pattern in patterns:
            if re.search(pattern, lowered, flags=re.IGNORECASE):
                return code
    return None


def parse_total_amount(text: str) -> float | None:
    patterns = [
        r"(?:total|grand total|amount due|net total)\s*[:\-]?\s*(?:rs\.?|lkr|usd|eur|gbp|inr|\$|€|£|₹)?\s*([0-9]+(?:[,\s][0-9]{3})*(?:\.[0-9]{1,2})?)",
        r"(?:balance due)\s*[:\-]?\s*(?:rs\.?|lkr|usd|eur|gbp|inr|\$|€|£|₹)?\s*([0-9]+(?:[,\s][0-9]{3})*(?:\.[0-9]{1,2})?)",
    ]

    candidates: list[float] = []
    for pattern in patterns:
        for match in re.finditer(pattern, text, flags=re.IGNORECASE):
            value = match.group(1).replace(",", "").replace(" ", "")
            try:
                candidates.append(float(value))
            except ValueError:
                continue

    if candidates:
        return max(candidates)

    fallback = re.findall(r"([0-9]+(?:,[0-9]{3})*(?:\.[0-9]{2})?)", text)
    numeric_values: list[float] = []
    for item in fallback:
        try:
            numeric_values.append(float(item.replace(",", "")))
        except ValueError:
            continue

    return max(numeric_values) if numeric_values else None


def parse_receipt_date(text: str) -> datetime | None:
    date_patterns = [
        r"(\d{4}[-/]\d{1,2}[-/]\d{1,2})",
        r"(\d{1,2}[-/]\d{1,2}[-/]\d{2,4})",
        r"(\d{1,2}\s+[A-Za-z]{3,9}\s+\d{2,4})",
        r"([A-Za-z]{3,9}\s+\d{1,2},\s+\d{4})",
    ]

    for pattern in date_patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if not match:
            continue

        raw = match.group(1).strip()
        for fmt in (
            "%Y-%m-%d",
            "%Y/%m/%d",
            "%d-%m-%Y",
            "%d/%m/%Y",
            "%d-%m-%y",
            "%d/%m/%y",
            "%d %B %Y",
            "%d %b %Y",
            "%B %d, %Y",
            "%b %d, %Y",
        ):
            try:
                return datetime.strptime(raw, fmt)
            except ValueError:
                continue

    return None


def parse_merchant(text: str, original_filename: str | None = None) -> str | None:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    ignored = {"invoice", "receipt", "tax invoice", "bill", "total", "amount", "cash"}

    for line in lines[:8]:
        lowered = line.lower()
        if len(line) < 3:
            continue
        if any(keyword == lowered for keyword in ignored):
            continue
        if re.search(r"\d{2,}", line):
            continue
        return line[:255]

    if original_filename:
        return Path(original_filename).stem.replace("_", " ").replace("-", " ").strip()[:255] or None

    return None


# -------------------------------------------------------------------
# Categorization helpers
# -------------------------------------------------------------------


def get_category_from_feedback(db: Session, user_id: int, merchant: str | None) -> dict[str, Any] | None:
    if not merchant:
        return None

    normalized = normalize_merchant(merchant)
    if not normalized:
        return None

    feedback_rows = (
        db.query(CategoryFeedback)
        .filter(
            CategoryFeedback.user_id == user_id,
            CategoryFeedback.merchant_normalized == normalized,
        )
        .order_by(CategoryFeedback.created_at.desc())
        .all()
    )

    if not feedback_rows:
        return None

    latest = feedback_rows[0]
    return {
        "category": latest.user_corrected_category,
        "subcategory": latest.user_corrected_subcategory,
        "confidence": 0.98,
        "source": "feedback",
        "needs_review": False,
    }


def categorize_by_rules(merchant: str | None, text: str) -> dict[str, Any]:
    combined = f"{merchant or ''} {text}".lower()

    for category, sub_map in CATEGORY_RULES.items():
        for subcategory, keywords in sub_map.items():
            for keyword in keywords:
                if keyword in combined:
                    return {
                        "category": category,
                        "subcategory": subcategory,
                        "confidence": 0.78,
                        "source": "rules",
                        "needs_review": False,
                    }

    return {
        "category": "Other",
        "subcategory": "Uncategorized",
        "confidence": 0.35,
        "source": "rules",
        "needs_review": True,
    }


def categorize_with_openai(merchant: str | None, text: str) -> dict[str, Any] | None:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return None

    try:
        from openai import OpenAI
    except Exception as exc:
        logger.warning("OpenAI SDK unavailable: %s", exc)
        return None

    categories = list(CATEGORY_RULES.keys())

    prompt = (
        "Classify this receipt into one of these categories: "
        f"{', '.join(categories)}.\n"
        "Return strict JSON with keys: category, subcategory, confidence.\n"
        f"Merchant: {merchant or 'Unknown'}\n"
        f"Text: {text[:2500]}"
    )

    try:
        client = OpenAI(api_key=api_key)
        response = client.chat.completions.create(
            model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
            messages=[
                {"role": "system", "content": "You classify receipt spending categories."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.1,
        )
        content = response.choices[0].message.content or ""
        category = next((c for c in categories if c.lower() in content.lower()), "Other")
        return {
            "category": category,
            "subcategory": None,
            "confidence": 0.7,
            "source": "openai",
            "needs_review": category == "Other",
        }
    except Exception as exc:
        logger.warning("OpenAI categorization failed: %s", exc)
        return None


def categorize_receipt(
    db: Session,
    user_id: int,
    merchant: str | None,
    text: str,
) -> dict[str, Any]:
    feedback_result = get_category_from_feedback(db, user_id, merchant)
    if feedback_result:
        return feedback_result

    rule_result = categorize_by_rules(merchant, text)
    if rule_result["confidence"] >= 0.75:
        return rule_result

    ai_result = categorize_with_openai(merchant, text)
    if ai_result:
        return ai_result

    return rule_result


# -------------------------------------------------------------------
# Receipt processing orchestration
# -------------------------------------------------------------------


def process_receipt(receipt_id: int, db: Session) -> Receipt:
    receipt = db.query(Receipt).filter(Receipt.id == receipt_id).first()
    if not receipt:
        raise ValueError(f"Receipt {receipt_id} not found")

    try:
        receipt.processing_status = "processing"
        db.add(receipt)
        db.commit()
        db.refresh(receipt)

        extracted_text = extract_text_from_file(receipt.file_path)
        language = detect_language(extracted_text)
        translated_text = translate_to_english(extracted_text, language)

        working_text = translated_text or extracted_text
        merchant = parse_merchant(working_text, receipt.original_filename)
        total_amount = parse_total_amount(working_text)
        currency = parse_currency(working_text)
        receipt_date = parse_receipt_date(working_text)

        category_result = categorize_receipt(
            db=db,
            user_id=receipt.user_id,
            merchant=merchant,
            text=working_text,
        )

        receipt.ocr_text = extracted_text or None
        receipt.translated_text = translated_text if translated_text != extracted_text else None
        receipt.language = language
        receipt.merchant = merchant
        receipt.total_amount = total_amount
        receipt.currency = currency
        receipt.receipt_date = receipt_date
        receipt.category = category_result["category"]
        receipt.subcategory = category_result.get("subcategory")
        receipt.confidence = category_result.get("confidence")
        receipt.category_source = category_result.get("source")
        receipt.needs_review = category_result.get("needs_review", False)
        receipt.processing_status = "done"
    except Exception as exc:
        logger.exception("Receipt processing failed for id=%s: %s", receipt_id, exc)
        receipt.processing_status = "failed"
        receipt.needs_review = True
    finally:
        db.add(receipt)
        db.commit()
        db.refresh(receipt)

    return receipt


def process_receipt_background(receipt_id: int) -> None:
    db = SessionLocal()
    try:
        process_receipt(receipt_id, db)
    except Exception as exc:
        logger.exception("Background receipt processing failed for id=%s: %s", receipt_id, exc)
    finally:
        db.close()


def save_category_feedback(
    db: Session,
    user_id: int,
    receipt_id: int | None,
    merchant: str,
    ai_predicted_category: str | None,
    user_corrected_category: str,
    ai_predicted_subcategory: str | None = None,
    user_corrected_subcategory: str | None = None,
) -> CategoryFeedback:
    feedback = CategoryFeedback(
        user_id=user_id,
        receipt_id=receipt_id,
        merchant=merchant,
        merchant_normalized=normalize_merchant(merchant),
        ai_predicted_category=ai_predicted_category,
        user_corrected_category=user_corrected_category,
        ai_predicted_subcategory=ai_predicted_subcategory,
        user_corrected_subcategory=user_corrected_subcategory,
    )
    db.add(feedback)
    db.commit()
    db.refresh(feedback)
    return feedback


# -------------------------------------------------------------------
# Advisor fallback logic
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