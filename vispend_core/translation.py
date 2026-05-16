# vispend_core/translation.py
from typing import Tuple

try:
    from deep_translator import GoogleTranslator
except ImportError:
    GoogleTranslator = None


def detect_language(text: str) -> str:
    if any("\u0d80" <= ch <= "\u0dff" for ch in text):
        return "si"

    if any("\u0b80" <= ch <= "\u0bff" for ch in text):
        return "ta"

    return "auto"


def translate_to_english(text: str) -> Tuple[str, str]:
    if not text or not text.strip():
        return "", "auto"

    detected = detect_language(text)

    if GoogleTranslator is None:
        return text, detected

    try:
        translator = GoogleTranslator(source=detected, target="en")
        translated = translator.translate(text)
        return translated if translated else text, detected
    except Exception:
        return text, detected