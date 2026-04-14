# src/backend/services/ocr_pipeline.py
import os
import re
import json
import cv2
import tempfile
import requests
import numpy as np
from datetime import datetime
from groq import Groq

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
OUTPUT_DIR = os.path.join(PROJECT_ROOT, "outputs")
os.makedirs(OUTPUT_DIR, exist_ok=True)

OCR_SPACE_API_KEY = os.getenv("OCR_SPACE_API_KEY", "")
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")

def get_skew_angle(img):
    edges = cv2.Canny(img, 50, 150, apertureSize=3)
    lines = cv2.HoughLinesP(edges, 1, np.pi / 180, threshold=100, minLineLength=100, maxLineGap=10)
    if lines is None:
        return 0.0
    angles = [np.degrees(np.arctan2(l[0][3] - l[0][1], l[0][2] - l[0][0])) for l in lines]
    return float(np.median(angles))

def deskew(img):
    angle = get_skew_angle(img)
    if abs(angle) < 1.0:
        return img
    h, w = img.shape
    m = cv2.getRotationMatrix2D((w // 2, h // 2), angle, 1.0)
    return cv2.warpAffine(img, m, (w, h), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE)

def preprocess_receipt(img_path, target_width=800):
    img = cv2.imread(img_path)
    if img is None:
        raise ValueError(f"Could not read image: {img_path}")
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    h, w = gray.shape
    gray = cv2.resize(gray, (target_width, int(h * target_width / w)))
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    enhanced = clahe.apply(gray)
    denoised = cv2.GaussianBlur(enhanced, (3, 3), 0)
    thresh = cv2.adaptiveThreshold(
        denoised, 255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY, 11, 2
    )
    return deskew(thresh)

def run_ocr_space(image_path):
    if not OCR_SPACE_API_KEY:
        return {"ParsedResults": [{"ParsedText": ""}]}
    with open(image_path, "rb") as f:
        response = requests.post(
            "https://api.ocr.space/parse/image",
            files={"file": f},
            data={
                "apikey": OCR_SPACE_API_KEY,
                "language": "eng",
                "isOverlayRequired": False,
                "OCREngine": 2,
            },
            timeout=120,
        )
    response.raise_for_status()
    return response.json()

def extract_text_from_ocr_space(result):
    parsed = result.get("ParsedResults", [])
    return "\n".join([r.get("ParsedText", "") for r in parsed]).strip()

def _safe_float(value, default=0.0):
    try:
        if value is None or value == "":
            return default
        return float(str(value).replace(",", "").strip())
    except Exception:
        return default

def _normalize_date(value):
    if not value:
        return None
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%m/%d/%Y", "%d.%m.%Y"):
        try:
            return datetime.strptime(str(value).strip(), fmt).date().isoformat()
        except Exception:
            continue
    return None

def _regex_total(text):
    amounts = re.findall(r'(?<!\d)(?:\d{1,3}(?:,\d{3})*|\d+)\.\d{2}(?!\d)', text or "")
    if not amounts:
        return 0.0
    vals = [_safe_float(a) for a in amounts]
    return max(vals) if vals else 0.0

def _regex_date(text):
    patterns = [
        r'(\d{4}-\d{2}-\d{2})',
        r'(\d{2}/\d{2}/\d{4})',
        r'(\d{2}-\d{2}-\d{4})',
        r'(\d{2}\.\d{2}\.\d{4})',
    ]
    for p in patterns:
        m = re.search(p, text or "")
        if m:
            return _normalize_date(m.group(1))
    return None

def infer_category(merchant, text):
    combined = f"{merchant or ''} {text or ''}".lower()
    if any(k in combined for k in ["pharmacy", "clinic", "hospital", "medical"]):
        return "Healthcare"
    if any(k in combined for k in ["fuel", "petrol", "diesel", "shell", "ceypetco"]):
        return "Fuel"
    if any(k in combined for k in ["bus", "train", "uber", "pickme", "taxi", "transport"]):
        return "Transport"
    if any(k in combined for k in ["hardware", "tools", "paint", "screw"]):
        return "Hardware & Tools"
    if any(k in combined for k in ["supermarket", "grocery", "keells", "food city", "cargills"]):
        return "Grocery"
    if any(k in combined for k in ["cafe", "coffee", "restaurant", "bakery", "food", "pizza", "burger"]):
        return "Food & Beverage"
    if any(k in combined for k in ["fashion", "retail", "store", "mart", "shop"]):
        return "Retail"
    return "Other"

def extract_fields_with_groq(ocr_text):
    if not GROQ_API_KEY or not ocr_text.strip():
        return {}
    client = Groq(api_key=GROQ_API_KEY)
    prompt = f"""
You are a receipt data extraction assistant.
Return only valid JSON.
Fields:
merchant, date, time, currency, subtotal, tax, total, payment_method,
items (list of objects with name, qty, unit_price, total_price).
Use null when missing.

OCR TEXT:
{ocr_text}
"""
    response = client.chat.completions.create(
        model="meta-llama/llama-4-scout-17b-16e-instruct",
        messages=[{"role": "user", "content": prompt}],
        temperature=0,
        max_tokens=1000,
        response_format={"type": "json_object"},
    )
    raw = response.choices[0].message.content.strip()
    try:
        return json.loads(raw)
    except Exception:
        return {}

def process_receipt_image(image_path: str) -> dict:
    preprocessed = preprocess_receipt(image_path)
    with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as tmp:
        tmp_path = tmp.name
    cv2.imwrite(tmp_path, preprocessed)

    try:
        ocr_result = run_ocr_space(tmp_path)
        ocr_text = extract_text_from_ocr_space(ocr_result)
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)

    fields = extract_fields_with_groq(ocr_text)

    merchant = fields.get("merchant") or os.path.splitext(os.path.basename(image_path))[0]
    date_value = _normalize_date(fields.get("date")) or _regex_date(ocr_text)
    total = _safe_float(fields.get("total"), _regex_total(ocr_text))
    subtotal = _safe_float(fields.get("subtotal"), 0.0)
    tax = _safe_float(fields.get("tax"), 0.0)
    currency = (fields.get("currency") or "LKR").upper()
    payment_method = (fields.get("payment_method") or "UNKNOWN").upper()
    items = fields.get("items") or []
    category = infer_category(merchant, ocr_text)

    normalized_items = []
    for item in items:
        normalized_items.append({
            "name": str(item.get("name") or "Item").strip(),
            "quantity": _safe_float(item.get("qty"), 1.0),
            "unit_price": _safe_float(item.get("unit_price") or item.get("total_price"), 0.0),
            "category": category,
        })

    return {
        "date": date_value,
        "merchant": merchant,
        "total": total,
        "subtotal": subtotal,
        "tax": tax,
        "currency": currency,
        "payment_method": payment_method,
        "category": category,
        "raw_text": ocr_text,
        "items": normalized_items,
    }