# vispend_core/translation.py
from typing import Tuple

try:
    from deep_translator import GoogleTranslator
except ImportError:
    GoogleTranslator = None

def detect_language(text: str) -> str:
    # Very simple heuristic; you can plug in a real detector later
    if any("\u0d80" <= ch <= "\u0dff" for ch in text):  # Sinhala
        return "si"
    if any("\u0b80" <= ch <= "\u0bff" for ch in text):  # Tamil
        return "ta"
    return "auto"

def translate_to_english(text: str) -> Tuple[str, str]:
    """
    Returns (translated_text, detected_lang).
    If translator not installed, returns original text.
    """
    if not text.strip():
        return text, "auto"

    if GoogleTranslator is None:
        # Fallback: no translation library installed
        return text, "auto"

    detected = detect_language(text)
    translator = GoogleTranslator(source=detected, target="en")
    translated = translator.translate(text)
    return translated, detected