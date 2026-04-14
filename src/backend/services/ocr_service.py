import os, re, logging
from typing import Optional, Tuple
from PIL import Image
import pytesseract
from langdetect import detect, LangDetectException
from deep_translator import GoogleTranslator

logger = logging.getLogger(__name__)

SUPPORTED_CURRENCIES = {
    "MYR","USD","EUR","GBP","SGD","AUD","JPY","CNY","THB",
    "IDR","PHP","INR","KRW","HKD","TWD","VND","BDT","LKR",
}
CURRENCY_SYMBOLS = {
    "$":"USD","€":"EUR","£":"GBP","¥":"JPY",
    "RM":"MYR","Rs":"INR","₹":"INR","₩":"KRW",
    "฿":"THB","Rp":"IDR","₱":"PHP",
}


def extract_text_from_image(image_path: str) -> Tuple[str, float]:
    try:
        img = Image.open(image_path)
        w, h = img.size
        if w < 800:
            scale = 800 / w
            img = img.resize((int(w * scale), int(h * scale)), Image.LANCZOS)
        data = pytesseract.image_to_data(img, output_type=pytesseract.Output.DICT)
        text = pytesseract.image_to_string(img)
        confidences = [
            int(c) for c, t in zip(data["conf"], data["text"])
            if t.strip() and c != "-1"
        ]
        avg_conf = sum(confidences) / len(confidences) / 100 if confidences else 0.0
        return text.strip(), round(avg_conf, 3)
    except Exception as e:
        logger.error(f"OCR failed: {e}")
        return "", 0.0


def detect_language(text: str) -> str:
    if not text or len(text.strip()) < 20:
        return "en"
    try:
        return detect(text)
    except LangDetectException:
        return "en"


def translate_to_english(text: str, source_lang: str) -> Optional[str]:
    if source_lang == "en" or not text.strip():
        return None
    try:
        translator = GoogleTranslator(source=source_lang, target="en")
        chunks = [text[i:i+4500] for i in range(0, len(text), 4500)]
        translated = " ".join(translator.translate(chunk) for chunk in chunks)
        return translated.strip()
    except Exception as e:
        logger.warning(f"Translation failed ({source_lang}→en): {e}")
        return None


def extract_total_amount(text: str) -> Tuple[Optional[float], Optional[str]]:
    lines = text.upper().split("\n")
    total_keywords = ["TOTAL","GRAND TOTAL","AMOUNT DUE","AMOUNT PAID",
                      "NET TOTAL","PAYABLE","JUMLAH","TOTAL HARGA"]
    amount = None
    currency = None

    for line in lines:
        if not any(kw in line for kw in total_keywords):
            continue
        numbers = re.findall(r"[\d,]+\.?\d{0,2}", line)
        if numbers:
            try:
                amount = float(numbers[-1].replace(",", ""))
            except ValueError:
                pass
        for symbol, code in CURRENCY_SYMBOLS.items():
            if symbol.upper() in line:
                currency = code
                break
        for code in SUPPORTED_CURRENCIES:
            if code in line:
                currency = code
                break
        if amount:
            break

    if amount is None:
        all_numbers = re.findall(r"\b\d{1,6}[.,]\d{2}\b", text)
        if all_numbers:
            try:
                amount = max(float(n.replace(",", "")) for n in all_numbers)
            except ValueError:
                pass

    if currency is None:
        upper_text = text.upper()
        for code in SUPPORTED_CURRENCIES:
            if code in upper_text:
                currency = code
                break

    return amount, currency


def extract_merchant(text: str) -> Optional[str]:
    lines = [l.strip() for l in text.split("\n") if l.strip()]
    skip = re.compile(
        r"(receipt|invoice|tax|vat|gst|tel:|phone|www\.|http|@|receipt no|reg no)",
        re.IGNORECASE,
    )
    for line in lines[:6]:
        if len(line) > 3 and not skip.search(line) and not re.match(r"^\d+$", line):
            return line.title()
    return lines[0].title() if lines else None


def normalize_merchant(merchant: str) -> str:
    if not merchant:
        return ""
    name = re.sub(r"\b(sdn bhd|sdn|bhd|ltd|llc|inc|corp|co\.|pte)\b", "", merchant, flags=re.IGNORECASE)
    name = re.sub(r"[^a-zA-Z0-9\s]", " ", name)
    return re.sub(r"\s+", " ", name).strip().upper()


def extract_receipt_date(text: str):
    from datetime import datetime
    patterns = [
        r"\b(\d{1,2})[/-](\d{1,2})[/-](\d{2,4})\b",
        r"\b(\d{4})[/-](\d{1,2})[/-](\d{1,2})\b",
        r"\b(\d{1,2})\s+(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+(\d{2,4})\b",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            try:
                g = match.groups()
                year = int(g[2]) + 2000 if len(str(g[2])) == 2 else int(g[2])
                month = g[1]
                day = int(g[0])
                if isinstance(month, str) and not month.isdigit():
                    return datetime.strptime(f"{day} {month} {year}", "%d %b %Y")
                return datetime(year, int(month), day)
            except (ValueError, TypeError):
                continue
    return None