import os, shutil, logging
from datetime import datetime
from sqlalchemy.orm import Session
from ..models import Receipt
from .ocr_service import (
    extract_text_from_image, detect_language, translate_to_english,
    extract_total_amount, extract_merchant, normalize_merchant, extract_receipt_date,
)
from .categorization_service import categorize_receipt

logger = logging.getLogger(__name__)
UPLOAD_DIR = os.getenv("UPLOAD_DIR", "./uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)


def save_upload_file(file_obj, filename: str) -> str:
    safe_name = f"{datetime.utcnow().strftime('%Y%m%d%H%M%S%f')}_{filename}"
    dest = os.path.join(UPLOAD_DIR, safe_name)
    with open(dest, "wb") as f:
        shutil.copyfileobj(file_obj, f)
    return dest


def process_receipt(db: Session, receipt_id: int, user_id: int):
    receipt = db.query(Receipt).filter(Receipt.id == receipt_id).first()
    if not receipt:
        return
    try:
        receipt.processing_status = "processing"
        db.commit()

        raw_text, ocr_confidence = extract_text_from_image(receipt.file_path)
        receipt.raw_ocr_text = raw_text
        receipt.ocr_confidence = ocr_confidence

        lang = detect_language(raw_text)
        receipt.detected_language = lang

        translated = translate_to_english(raw_text, lang)
        receipt.translated_text = translated

        work_text = translated or raw_text

        merchant = extract_merchant(work_text)
        receipt.merchant = merchant
        receipt.merchant_normalized = normalize_merchant(merchant or "")

        amount, currency = extract_total_amount(work_text)
        receipt.total_amount = amount
        receipt.currency = currency or "USD"
        receipt.receipt_date = extract_receipt_date(work_text)

        category, subcategory, confidence, source, needs_review = categorize_receipt(
            db=db, user_id=user_id,
            merchant=merchant, merchant_normalized=receipt.merchant_normalized,
            ocr_text=raw_text, translated_text=translated,
        )
        receipt.category = category
        receipt.subcategory = subcategory
        receipt.category_confidence = confidence
        receipt.category_source = source
        receipt.needs_review = needs_review
        receipt.processing_status = "done"
        receipt.processing_error = None

    except Exception as e:
        logger.exception(f"Processing failed for receipt {receipt_id}: {e}")
        receipt.processing_status = "failed"
        receipt.processing_error = str(e)
    finally:
        db.commit()
        db.refresh(receipt)