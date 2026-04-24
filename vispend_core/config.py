# vispend_core/config.py
import os
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = os.path.dirname(os.path.dirname(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
REC_RAW_DIR = os.path.join(DATA_DIR, "receipts_raw")
UPLOAD_DIR = os.path.join(DATA_DIR, "uploads")

OUTPUT_DIR = os.path.join(BASE_DIR, "outputs")
OCR_OUTPUT_DIR = os.path.join(OUTPUT_DIR, "ocr")
ANALYTICS_OUTPUT_DIR = os.path.join(OUTPUT_DIR, "analytics")

os.makedirs(REC_RAW_DIR, exist_ok=True)
os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(OCR_OUTPUT_DIR, exist_ok=True)
os.makedirs(ANALYTICS_OUTPUT_DIR, exist_ok=True)

OCR_SPACE_API_KEY = os.getenv("OCR_SPACE_API_KEY", "")
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GROQ_MODEL = os.getenv("GROQ_MODEL", "meta-llama/llama-4-scout-17b-16e-instruct")
TESSERACT_CMD = os.getenv("TESSERACT_CMD", "")

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