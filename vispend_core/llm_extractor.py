# vispend_core/llm_extractor.py
import json
from groq import Groq
from .config import GROQ_API_KEY
from .prompts import RECEIPT_EXTRACTION_PROMPT

groq_client = Groq(api_key=GROQ_API_KEY)

def extract_fields_with_groq(ocr_text: str) -> dict:
    prompt = RECEIPT_EXTRACTION_PROMPT.format(ocr_text=ocr_text)
    response = groq_client.chat.completions.create(
        model="meta-llama/llama-4-scout-17b-16e-instruct",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.0,
        max_tokens=1000,
        response_format={"type": "json_object"},
    )
    raw = response.choices[0].message.content.strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        # Fallback: try to fix trivial JSON issues or return empty dict
        return {}