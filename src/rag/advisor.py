# src/rag/advisor.py

import json
import logging
import os
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[2] / ".env")

logger = logging.getLogger(__name__)

DEFAULT_GROQ_MODELS = [
    os.getenv("GROQ_MODEL", "").strip(),
    os.getenv("GROQ_FALLBACK_MODEL", "").strip(),
    "meta-llama/llama-4-scout-17b-16e-instruct",
    "llama-3.3-70b-versatile",
    "llama3-70b-8192",
    "mixtral-8x7b-32768",
]

GROQ_MODELS = []
_seen_models: set[str] = set()
for model in DEFAULT_GROQ_MODELS:
    model = model.strip()
    if model and model not in _seen_models:
        _seen_models.add(model)
        GROQ_MODELS.append(model)

GROQ_MAX_TOKENS = int(os.getenv("GROQ_MAX_TOKENS", "1024"))
GROQ_TEMPERATURE = float(os.getenv("GROQ_TEMPERATURE", "0.3"))
RAG_TOP_K = int(os.getenv("RAG_ADVISOR_TOP_K", "4"))


# ──────────────────────────────────────────────────────────────────────────────
# Prompt builders
# ──────────────────────────────────────────────────────────────────────────────

def _format_spending_summary(summary: dict[str, Any]) -> str:
    total = float(summary.get("total_spend") or 0)
    count = int(summary.get("receipt_count") or 0)
    avg = float(summary.get("average_spend") or 0)
    top_cat = summary.get("top_category") or "Unknown"
    breakdown = summary.get("category_breakdown") or []
    anomalies = summary.get("anomalies") or []

    lines = [
        f"Total spend: {total:,.2f}",
        f"Receipt count: {count}",
        f"Average receipt: {avg:,.2f}",
        f"Top spending category: {top_cat}",
    ]

    if breakdown:
        lines.append("Category breakdown:")
        for item in breakdown[:6]:
            cat = item.get("category", "Unknown")
            amt = float(item.get("amount", 0) or 0)
            pct = float(item.get("percentage", 0) or 0)
            lines.append(f" - {cat}: {amt:,.2f} ({pct:.1f}%)")

    if anomalies:
        lines.append("Detected anomalies:")
        for anomaly in anomalies[:3]:
            lines.append(f" - {anomaly.get('message', '')}")

    return "\n".join(lines)


def _format_retrieved_chunks(chunks: list[dict[str, Any]]) -> str:
    if not chunks:
        return "No relevant knowledge base content retrieved."

    parts: list[str] = []
    for i, chunk in enumerate(chunks, start=1):
        title = chunk.get("title") or "Knowledge"
        source = chunk.get("source") or ""
        section = chunk.get("section") or ""
        text = str(chunk.get("chunk_text", "")).strip()

        header = f"[{i}] {title}"
        if section:
            header += f" — {section}"
        if source:
            header += f" (source: {source})"
        parts.append(f"{header}\n{text}")

    return "\n\n".join(parts)


def _build_advise_prompt(
    question: str,
    spending_context: str,
    knowledge_context: str,
) -> str:
    return (
        "You are a helpful personal finance advisor for Vispend AI, a receipt management app.\n"
        "Answer the user's question using only the spending data and knowledge provided below.\n"
        "Be concise, practical, and grounded. Do not invent data not present in the context.\n"
        "If the data is insufficient, say so clearly and give general advice.\n\n"
        "--- USER SPENDING DATA ---\n"
        f"{spending_context}\n\n"
        "--- RELEVANT KNOWLEDGE ---\n"
        f"{knowledge_context}\n\n"
        "--- USER QUESTION ---\n"
        f"{question}\n\n"
        "--- YOUR ANSWER ---"
    )


def _build_auto_insights_prompt(spending_context: str, knowledge_context: str) -> str:
    return (
        "You are a personal finance advisor for Vispend AI.\n"
        "Based on the user's spending data and the provided knowledge, "
        "generate 4 to 6 concise, actionable financial insights.\n"
        "Each insight must be grounded in the actual spending data shown.\n"
        "Return insights as a JSON array. Each object must have:\n"
        ' "type": one of trend, alert, tip, anomaly\n'
        ' "title": short title (max 8 words)\n'
        ' "message": actionable explanation (1-2 sentences)\n'
        ' "category": relevant spending category or null\n'
        ' "amount": relevant amount as a number or null\n'
        "Return only valid JSON. No explanation outside the array.\n\n"
        "--- USER SPENDING DATA ---\n"
        f"{spending_context}\n\n"
        "--- RELEVANT KNOWLEDGE ---\n"
        f"{knowledge_context}\n\n"
        "--- JSON INSIGHTS ---"
    )


# ──────────────────────────────────────────────────────────────────────────────
# Groq client
# ──────────────────────────────────────────────────────────────────────────────

def _get_groq_client():
    api_key = os.getenv("GROQ_API_KEY", "").strip()
    if not api_key:
        logger.info("GROQ_API_KEY not configured; advisor will use fallback logic")
        return None

    try:
        from groq import Groq
        return Groq(api_key=api_key)
    except ImportError:
        logger.warning("groq package is not installed. Install it with: pip install groq")
        return None
    except Exception as exc:
        logger.warning("Failed to initialise Groq client: %s", exc)
        return None


def _extract_error_text(exc: Exception) -> str:
    try:
        return str(exc).strip()
    except Exception:
        return exc.__class__.__name__


def _call_groq(client, prompt: str) -> str | None:
    if not GROQ_MODELS:
        logger.warning("No Groq model names configured; using fallback logic")
        return None

    last_error: str | None = None

    for model_name in GROQ_MODELS:
        try:
            response = client.chat.completions.create(
                model=model_name,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=GROQ_MAX_TOKENS,
                temperature=GROQ_TEMPERATURE,
            )
            logger.info("Groq response generated using model: %s", model_name)
            return response.choices[0].message.content or ""
        except Exception as exc:
            last_error = _extract_error_text(exc)
            logger.warning("Groq API call failed for model %s: %s", model_name, last_error)

            lowered = last_error.lower()
            retryable_model_error = (
                "model_not_found" in lowered
                or "does not exist" in lowered
                or "do not have access" in lowered
                or "not found" in lowered
            )
            if retryable_model_error:
                continue

            return None

    logger.warning("All configured Groq models failed. Last error: %s", last_error)
    return None


# ──────────────────────────────────────────────────────────────────────────────
# Rule-based fallback logic
# ──────────────────────────────────────────────────────────────────────────────

def _fallback_answer(
    user_question: str,
    spending_summary: dict[str, Any],
    chunks: list[dict[str, Any]],
) -> str:
    total = float(spending_summary.get("total_spend") or 0)
    avg = float(spending_summary.get("average_spend") or 0)
    top_cat = spending_summary.get("top_category") or "your top category"
    anomalies = spending_summary.get("anomalies") or []

    suggestions: list[str] = []

    if total <= 0:
        suggestions.append(
            "I don’t have enough spending data yet. Upload a few receipts so I can give tailored advice."
        )
    else:
        suggestions.append(
            f"Your current total recorded spend is {total:,.2f}, with an average receipt of {avg:,.2f}."
        )
        suggestions.append(
            f"The biggest spending area appears to be {top_cat}, so that is the best place to look for savings first."
        )

    if anomalies:
        suggestions.append(
            "I also noticed unusually high receipts, so reviewing those one-off expenses may help you reduce overspending."
        )

    if chunks:
        first = chunks[0].get("chunk_text", "")
        if first:
            suggestions.append(first[:300].strip())

    question_lower = user_question.lower()

    if "grocery" in question_lower:
        suggestions.append(
            "Try setting a weekly grocery budget, making a shopping list before visiting stores, and comparing recurring item prices."
        )
    elif "dining" in question_lower or "restaurant" in question_lower or "food" in question_lower:
        suggestions.append(
            "Reducing dining costs often works best by limiting takeout frequency, setting a weekly meal plan, and tracking lunch or coffee purchases separately."
        )
    elif "transport" in question_lower:
        suggestions.append(
            "For transport savings, combine errands into fewer trips, compare ride frequency, and identify whether fuel or ride-hailing is driving the category."
        )
    else:
        suggestions.append(
            "A practical next step is to focus on your highest category, cut a few repeat purchases, and monitor changes week by week."
        )

    return " ".join(suggestions).strip()


def _fallback_auto_insights(spending_summary: dict[str, Any]) -> list[dict[str, Any]]:
    insights: list[dict[str, Any]] = []

    total = float(spending_summary.get("total_spend") or 0)
    avg = float(spending_summary.get("average_spend") or 0)
    top_cat = spending_summary.get("top_category")
    breakdown = spending_summary.get("category_breakdown") or []
    anomalies = spending_summary.get("anomalies") or []
    monthly_trend = spending_summary.get("monthly_trend") or []

    if total > 0:
        insights.append(
            {
                "type": "trend",
                "title": "Overall spending snapshot",
                "message": f"You recorded total spending of {total:,.2f} with an average receipt value of {avg:,.2f}.",
                "category": None,
                "amount": total,
            }
        )

    if top_cat:
        top_amount = None
        for item in breakdown:
            if item.get("category") == top_cat:
                top_amount = item.get("amount")
                break

        insights.append(
            {
                "type": "alert",
                "title": "Top category identified",
                "message": f"Your highest spending category is {top_cat}. Focusing there is likely to give the biggest savings impact.",
                "category": top_cat,
                "amount": top_amount,
            }
        )

    if len(monthly_trend) >= 2:
        latest = monthly_trend[-1].get("amount", 0) or 0
        previous = monthly_trend[-2].get("amount", 0) or 0
        if latest > previous:
            insights.append(
                {
                    "type": "trend",
                    "title": "Monthly spending increased",
                    "message": f"Your latest month is higher than the previous one ({latest:,.2f} vs {previous:,.2f}). Review what changed in your biggest categories.",
                    "category": top_cat,
                    "amount": float(latest),
                }
            )
        elif latest < previous:
            insights.append(
                {
                    "type": "trend",
                    "title": "Monthly spending improved",
                    "message": f"Your latest month is lower than the previous one ({latest:,.2f} vs {previous:,.2f}). Keep the habits that helped reduce spending.",
                    "category": top_cat,
                    "amount": float(latest),
                }
            )

    if anomalies:
        first = anomalies[0]
        insights.append(
            {
                "type": "anomaly",
                "title": "Unusual expense detected",
                "message": first.get("message", "An unusual expense was detected in your receipts."),
                "category": first.get("category"),
                "amount": first.get("amount"),
            }
        )

    if top_cat:
        insights.append(
            {
                "type": "tip",
                "title": "Actionable savings step",
                "message": f"Set a short-term budget for {top_cat} and compare your next few receipts to see whether spending starts to fall.",
                "category": top_cat,
                "amount": None,
            }
        )

    return insights[:6]


def _parse_insights_json(raw: str) -> list[dict[str, Any]] | None:
    raw = raw.strip()
    if not raw:
        return None

    try:
        data = json.loads(raw)
        if isinstance(data, list):
            valid_items: list[dict[str, Any]] = []
            for item in data:
                if isinstance(item, dict):
                    valid_items.append(
                        {
                            "type": item.get("type", "tip"),
                            "title": item.get("title", "Insight"),
                            "message": item.get("message", ""),
                            "category": item.get("category"),
                            "amount": item.get("amount"),
                        }
                    )
            return valid_items
    except json.JSONDecodeError:
        pass

    start = raw.find("[")
    end = raw.rfind("]")
    if start != -1 and end != -1 and end > start:
        try:
            data = json.loads(raw[start : end + 1])
            if isinstance(data, list):
                valid_items: list[dict[str, Any]] = []
                for item in data:
                    if isinstance(item, dict):
                        valid_items.append(
                            {
                                "type": item.get("type", "tip"),
                                "title": item.get("title", "Insight"),
                                "message": item.get("message", ""),
                                "category": item.get("category"),
                                "amount": item.get("amount"),
                            }
                        )
                return valid_items
        except json.JSONDecodeError:
            return None

    return None


# ──────────────────────────────────────────────────────────────────────────────
# Advisor class
# ──────────────────────────────────────────────────────────────────────────────

class Advisor:
    def __init__(self, top_k: int = RAG_TOP_K) -> None:
        self._top_k = top_k
        self._retriever = None
        self._retriever_attempted = False

    def _get_retriever(self):
        if self._retriever is not None:
            return self._retriever

        if self._retriever_attempted:
            return None

        self._retriever_attempted = True

        try:
            from rag.retriever import Retriever
        except ImportError:
            try:
                from retriever import Retriever
            except ImportError:
                logger.warning("Could not import Retriever — RAG knowledge will be unavailable")
                return None

        try:
            self._retriever = Retriever()
        except Exception as exc:
            logger.warning("Failed to initialise Retriever: %s", exc)
            self._retriever = None

        return self._retriever

    def retry_retriever_initialization(self) -> None:
        self._retriever = None
        self._retriever_attempted = False

    def _retrieve(self, query: str) -> list[dict[str, Any]]:
        retriever = self._get_retriever()
        if retriever is None:
            return []

        try:
            results = retriever.search(query, top_k=self._top_k)
            return results if isinstance(results, list) else []
        except Exception as exc:
            logger.warning("Retrieval failed for query %r: %s", query[:60], exc)
            return []

    def _deduplicate_sources(self, chunks: list[dict[str, Any]]) -> list[str]:
        seen: set[str] = set()
        sources: list[str] = []

        for chunk in chunks:
            title = str(chunk.get("title") or "").strip()
            source = str(chunk.get("source") or "").strip()
            key = title or source
            if key and key not in seen:
                seen.add(key)
                sources.append(key)

        return sources

    def advise(self, user_question: str, spending_summary: dict[str, Any]) -> dict[str, Any]:
        if not user_question or not user_question.strip():
            return {
                "answer": "Please provide a question about your spending.",
                "sources": [],
                "insights": [],
            }

        chunks = self._retrieve(user_question)
        spending_context = _format_spending_summary(spending_summary)
        knowledge_context = _format_retrieved_chunks(chunks)
        sources = self._deduplicate_sources(chunks)

        groq_client = _get_groq_client()
        answer: str | None = None

        if groq_client:
            prompt = _build_advise_prompt(
                question=user_question,
                spending_context=spending_context,
                knowledge_context=knowledge_context,
            )
            answer = _call_groq(groq_client, prompt)

        if not answer:
            logger.info("Using rule-based fallback for advise()")
            answer = _fallback_answer(user_question, spending_summary, chunks)

        return {
            "answer": answer.strip(),
            "sources": sources,
            "insights": [],
        }

    def auto_insights(self, spending_summary: dict[str, Any]) -> list[dict[str, Any]]:
        top_cat = spending_summary.get("top_category") or "spending"
        query = f"advice for reducing {top_cat} spending and managing personal finances"

        chunks = self._retrieve(query)
        spending_context = _format_spending_summary(spending_summary)
        knowledge_context = _format_retrieved_chunks(chunks)

        groq_client = _get_groq_client()
        insights: list[dict[str, Any]] | None = None

        if groq_client:
            prompt = _build_auto_insights_prompt(spending_context, knowledge_context)
            raw = _call_groq(groq_client, prompt)
            if raw:
                insights = _parse_insights_json(raw)
                if insights is None:
                    logger.warning("Could not parse JSON insights from Groq response — using fallback")

        if not insights:
            logger.info("Using rule-based fallback for auto_insights()")
            insights = _fallback_auto_insights(spending_summary)

        for i, item in enumerate(insights, start=1):
            if "id" not in item:
                item["id"] = f"insight-{i}"

        return insights[:6]


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-8s %(message)s",
        datefmt="%H:%M:%S",
    )

    sample_summary = {
        "total_spend": 18450.75,
        "receipt_count": 34,
        "average_spend": 542.67,
        "top_category": "Dining",
        "category_breakdown": [
            {"category": "Dining", "amount": 6200.00, "percentage": 33.6},
            {"category": "Groceries", "amount": 4800.00, "percentage": 26.0},
            {"category": "Transport", "amount": 3100.00, "percentage": 16.8},
            {"category": "Utilities", "amount": 2200.00, "percentage": 11.9},
            {"category": "Other", "amount": 2150.75, "percentage": 11.7},
        ],
        "monthly_trend": [
            {"period": "2026-01", "amount": 5200.00},
            {"period": "2026-02", "amount": 6100.00},
            {"period": "2026-03", "amount": 7150.75},
        ],
        "anomalies": [],
    }

    advisor = Advisor()

    result = advisor.advise(
        user_question="How can I reduce my dining expenses?",
        spending_summary=sample_summary,
    )
    print("\n--- advise() ---")
    print(f"Answer: {result['answer']}")
    print(f"Sources: {result['sources']}")

    insights = advisor.auto_insights(sample_summary)
    print("\n--- auto_insights() ---")
    print(json.dumps(insights, indent=2))