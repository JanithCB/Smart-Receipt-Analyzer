# vispend_core/llm_extractor.py
import json

from groq import Groq

from .config import GROQ_API_KEY, GROQ_MODEL
from .prompts import RECEIPT_EXTRACTION_PROMPT

groq_client = Groq(api_key=GROQ_API_KEY) if GROQ_API_KEY else None


def _safe_json_load(raw: str) -> dict:
    if not raw:
        return {}

    cleaned = raw.strip()

    if cleaned.startswith("```json"):
        cleaned = cleaned[7:]
    if cleaned.startswith("```"):
        cleaned = cleaned[3:]
    if cleaned.endswith("```"):
        cleaned = cleaned[:-3]

    cleaned = cleaned.strip()

    try:
        parsed = json.loads(cleaned)
        return parsed if isinstance(parsed, dict) else {}
    except json.JSONDecodeError:
        return {}


def extract_fields_with_groq(ocr_text: str) -> dict:
    if not ocr_text or not ocr_text.strip():
        return {}

    if groq_client is None:
        return {}

    prompt = RECEIPT_EXTRACTION_PROMPT.format(ocr_text=ocr_text)

    try:
        response = groq_client.chat.completions.create(
            model=GROQ_MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.0,
            max_tokens=1000,
            response_format={"type": "json_object"},
        )
        raw = response.choices.message.content.strip()
        return _safe_json_load(raw)
    except Exception:
        return {}