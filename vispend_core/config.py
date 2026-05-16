# vispend_core/config.py
import os
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")
REC_RAW_DIR = os.path.join(DATA_DIR, "receipts_raw")
UPLOAD_DIR = os.path.join(DATA_DIR, "uploads")

OUTPUT_DIR = os.path.join(BASE_DIR, "outputs")
OCR_OUTPUT_DIR = os.path.join(OUTPUT_DIR, "ocr")
ANALYTICS_OUTPUT_DIR = os.path.join(OUTPUT_DIR, "analytics")

for path in [REC_RAW_DIR, UPLOAD_DIR, OCR_OUTPUT_DIR, ANALYTICS_OUTPUT_DIR]:
    os.makedirs(path, exist_ok=True)

OCR_SPACE_API_KEY = os.getenv("OCR_SPACE_API_KEY", "").strip()
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "").strip()
GROQ_MODEL = os.getenv("GROQ_MODEL", "meta-llama/llama-4-scout-17b-16e-instruct").strip()
TESSERACT_CMD = os.getenv("TESSERACT_CMD", "").strip()

CURRENCY_TO_USD = {
    "MYR": 0.24,
    "RM": 0.24,
    "SGD": 0.74,
    "LKR": 0.0055,
    "USD": 1.0,
    "GBP": 1.27,
    "EUR": 1.08,
    "INR": 0.012,
}

SUPPORTED_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff", ".webp"}