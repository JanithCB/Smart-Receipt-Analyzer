# vispend_core/pipeline.py
import os
import json
import glob
import time
import pandas as pd

from .config import (
    REC_RAW_DIR,
    UPLOAD_DIR,
    ANALYTICS_OUTPUT_DIR,
    CURRENCY_TO_USD,
)
from .ocr_client import get_ocr_text
from .translation import translate_to_english
from .llm_extractor import extract_fields_with_groq

def convert_to_usd(amount, currency):
    if amount is None:
        return None
    try:
        amount = float(amount)
        rate = CURRENCY_TO_USD.get(str(currency).upper().strip())
        if rate is None:
            return None
        return round(amount * rate, 4)
    except (ValueError, TypeError):
        return None

def process_single_receipt(img_path: str, language_hint: str = "eng") -> dict:
    filename = os.path.basename(img_path)

    # 1. OCR
    ocr_text = get_ocr_text(img_path, language=language_hint)

    # 2. Translate to English (LLM will still see English)
    translated_text, detected_lang = translate_to_english(ocr_text)

    # 3. LLM structured extraction
    fields = extract_fields_with_groq(translated_text) if translated_text.strip() else {}

    currency = fields.get("currency")
    subtotal = fields.get("subtotal")
    tax = fields.get("tax")
    total = fields.get("total")

    return {
        "file": filename,
        "merchant": fields.get("merchant"),
        "date": fields.get("date"),
        "time": fields.get("time"),
        "currency": currency,
        "category": fields.get("category"),
        "subtotal_orig": subtotal,
        "tax_orig": tax,
        "total_orig": total,
        "subtotal_usd": convert_to_usd(subtotal, currency),
        "tax_usd": convert_to_usd(tax, currency),
        "total_usd": convert_to_usd(total, currency),
        "payment_method": fields.get("payment_method"),
        "items": json.dumps(fields.get("items", [])),
        "ocr_text_preview": ocr_text[:200],
        "ocr_lang": detected_lang,
    }

def process_batch_receipts(dir_path: str = REC_RAW_DIR, sleep_sec: float = 2.0) -> pd.DataFrame:
    img_paths = glob.glob(os.path.join(dir_path, "*"))
    results = []
    for i, img_path in enumerate(img_paths):
        print(f"Processing ({i+1}/{len(img_paths)}): {os.path.basename(img_path)}")
        try:
            result = process_single_receipt(img_path)
            results.append(result)
            time.sleep(sleep_sec)  # respect OCR.Space / Groq rate limits
        except Exception as e:
            print("Error:", e)
            results.append({"file": os.path.basename(img_path), "error": str(e)})
    df = pd.DataFrame(results)
    out_csv = os.path.join(ANALYTICS_OUTPUT_DIR, "ocr_batch_results.csv")
    df.to_csv(out_csv, index=False)
    print("Done! Processed", len(df), "receipts ->", out_csv)
    return df