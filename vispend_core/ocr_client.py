import os
from typing import Dict, Any

import cv2
import requests

from .config import OCRSPACEAPIKEY, OCROUTPUTDIR
from .preprocessing import preprocessreceipt


OCRSPACE_URL = "https://api.ocr.space/parse/image"


def _safe_stem(path: str) -> str:
    return os.path.splitext(os.path.basename(path))[0]


def runocrspace(imagepath: str, language: str = "eng", apikey: str | None = None) -> Dict[str, Any]:
    key = apikey or OCRSPACEAPIKEY
    if not key:
        raise ValueError("OCRSPACEAPIKEY is missing. Add it to your .env file.")

    with open(imagepath, "rb") as f:
        response = requests.post(
            OCRSPACE_URL,
            files={"file": f},
            data={
                "apikey": key,
                "language": language,
                "isOverlayRequired": False,
                "OCREngine": 2,
            },
            timeout=60,
        )

    response.raise_for_status()
    return response.json()


def extracttextfromocrspace(result: Dict[str, Any]) -> str:
    if not result:
        return ""

    if result.get("IsErroredOnProcessing"):
        message = result.get("ErrorMessage") or result.get("ErrorDetails") or "OCR processing failed."
        if isinstance(message, list):
            message = " | ".join(str(x) for x in message)
        raise ValueError(str(message))

    parsed_results = result.get("ParsedResults", [])
    parts = []

    for item in parsed_results:
        text = item.get("ParsedText", "")
        if text and text.strip():
            parts.append(text.strip())

    return "\n".join(parts).strip()


def savepreprocessedimage(imgpath: str) -> str:
    processed = preprocessreceipt(imgpath)
    stem = _safe_stem(imgpath)
    outpath = os.path.join(OCROUTPUTDIR, f"{stem}_prep.png")

    success = cv2.imwrite(outpath, processed)
    if not success:
        raise IOError(f"Failed to save preprocessed image: {outpath}")

    return outpath


def getocrtext(imgpath: str, language: str = "eng", force: bool = False) -> str:
    stem = _safe_stem(imgpath)
    txtpath = os.path.join(OCROUTPUTDIR, f"{stem}_ocr.txt")

    if os.path.exists(txtpath) and not force:
        with open(txtpath, "r", encoding="utf-8") as f:
            return f.read().strip()

    preppath = savepreprocessedimage(imgpath)
    result = runocrspace(preppath, language=language)
    ocrtext = extracttextfromocrspace(result)

    with open(txtpath, "w", encoding="utf-8") as f:
        f.write(ocrtext)

    return ocrtext