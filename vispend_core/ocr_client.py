# vispend_core/ocr_client.py
import os
from typing import Any, Dict

import cv2
import requests

from .config import OCR_OUTPUT_DIR, OCR_SPACE_API_KEY
from .preprocessing import preprocess_receipt

OCR_SPACE_URL = "https://api.ocr.space/parse/image"


def _file_stem(path: str) -> str:
    return os.path.splitext(os.path.basename(path))[0]


def run_ocr_space(image_path: str, language: str = "eng") -> Dict[str, Any]:
    if not OCR_SPACE_API_KEY:
        raise ValueError("OCR_SPACE_API_KEY is missing. Add it to your .env file.")

    with open(image_path, "rb") as file_obj:
        response = requests.post(
            OCR_SPACE_URL,
            files={"file": file_obj},
            data={
                "apikey": OCR_SPACE_API_KEY,
                "language": language,
                "isOverlayRequired": False,
                "OCREngine": 2,
            },
            timeout=60,
        )

    response.raise_for_status()
    result = response.json()

    if result.get("IsErroredOnProcessing"):
        message = result.get("ErrorMessage") or result.get("ErrorDetails") or "OCR.Space processing failed."
        if isinstance(message, list):
            message = " | ".join(str(item) for item in message)
        raise ValueError(str(message))

    return result


def extract_text_from_ocr_space(result: Dict[str, Any]) -> str:
    parsed_results = result.get("ParsedResults", [])
    parts = []

    for item in parsed_results:
        text = item.get("ParsedText", "")
        if text and text.strip():
            parts.append(text.strip())

    return "\n".join(parts).strip()


def save_preprocessed_image(img_path: str) -> str:
    processed = preprocess_receipt(img_path)
    stem = _file_stem(img_path)
    prep_path = os.path.join(OCR_OUTPUT_DIR, f"{stem}_prep.png")

    ok = cv2.imwrite(prep_path, processed)
    if not ok:
        raise IOError(f"Failed to save preprocessed image: {prep_path}")

    return prep_path


def get_ocr_text(img_path: str, language: str = "eng", force: bool = False) -> str:
    stem = _file_stem(img_path)
    txt_path = os.path.join(OCR_OUTPUT_DIR, f"{stem}_ocr.txt")

    if os.path.exists(txt_path) and not force:
        with open(txt_path, "r", encoding="utf-8") as file_obj:
            return file_obj.read().strip()

    prep_path = save_preprocessed_image(img_path)
    result = run_ocr_space(prep_path, language=language)
    ocr_text = extract_text_from_ocr_space(result)

    with open(txt_path, "w", encoding="utf-8") as file_obj:
        file_obj.write(ocr_text)

    return ocr_text