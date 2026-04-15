# src/rag/advisor.py

import logging
import os
from typing import Any
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[2] / ".env")

logger = logging.getLogger(__name__)

GROQ_MODEL      = os.getenv("GROQ_MODEL",       "llama-4-scout-17b-16e-instruct")
GROQ_MAX_TOKENS = int(os.getenv("GROQ_MAX_TOKENS", "1024"))
GROQ_TEMPERATURE = float(os.getenv("GROQ_TEMPERATURE", "0.3"))
RAG_TOP_K       = int(os.getenv("RAG_ADVISOR_TOP_K", "4"))


# ──────────────────────────────────────────────────────────────────────────────
# Prompt builders
# ──────────────────────────────────────────────────────────────────────────────


def _format_spending_summary(summary: dict) -> str:
    total     = float(summary.get("total_spend")    or 0)
    count     = int(summary.get("receipt_count")    or 0)
    avg       = float(summary.get("average_spend")  or 0)
    top_cat   = summary.get("top_category")         or "Unknown"
    breakdown = summary.get("category_breakdown")   or []
    anomalies = summary.get("anomalies")            or []

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
            lines.append(f"  - {cat}: {amt:,.2f} ({pct:.1f}%)")

    if anomalies:
        lines.append("Detected anomalies:")
        for a in anomalies[:3]:
            lines.append(f"  - {a.get('message', '')}")

    return "\n".join(lines)


def _format_retrieved_chunks(chunks: list[dict]) -> str:
    if not chunks:
        return "No relevant knowledge base content retrieved."

    parts: list[str] = []
    for i, chunk in enumerate(chunks, start=1):
        title   = chunk.get("title")   or "Knowledge"
        source  = chunk.get("source")  or ""
        section = chunk.get("section") or ""
        text    = chunk.get("chunk_text", "").strip()

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
        '  "type": one of trend, alert, tip, anomaly\n'
        '  "title": short title (max 8 words)\n'
        '  "message": actionable explanation (1-2 sentences)\n'
        '  "category": relevant spending category or null\n'
        '  "amount": relevant amount as a number or null\n'
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


def _call_groq(client, prompt: str) -> str | None:
    try:
        response = client.chat.completions.create(
            model=GROQ_MODEL,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=GROQ_MAX_TOKENS,
            temperature=GROQ_TEMPERATURE,
        )
        return response.choices[0].message.content or ""
    except Exception as exc:
        logger.warning("Groq API call failed: %s", exc)
        return None


# ──────────────────────────────────────────────────────────────────────────────
# Rule-based fallback logic
# ──────────────────────────────────────────────────────────────────────────────


def _fallback_answer(
    question: str,
    spending_summary: dict,
    chunks: list[dict],
) -> str:
    question_lower = question.lower()
    total     = float(spending_summary.get("total_spend")   or 0)
    top_cat   = spending_summary.get("top_category")        or None
    avg       = float(spending_summary.get("average_spend") or 0)
    anomalies = spending_summary.get("anomalies")           or []
    breakdown = spending_summary.get("category_breakdown")  or []

    knowledge_hint = ""
    if chunks:
        first_chunk = chunks[0].get("chunk_text", "").strip()
        if first_chunk:
            knowledge_hint = f" Relevant guidance: {first_chunk[:300].strip()}..."

    if total == 0:
        return (
            "No spending data is available yet. "
            "Upload receipts to begin tracking your finances."
            + knowledge_hint
        )

    if any(kw in question_lower for kw in ("food", "grocery", "groceries", "dining", "eat")):
        food_cats  = {"Groceries", "Dining"}
        food_total = sum(
            float(item.get("amount", 0) or 0)
            for item in breakdown
            if item.get("category") in food_cats
        )
        return (
            f"Your combined food-related spending is {food_total:,.2f}. "
            "Consider meal planning, buying in bulk, and limiting impulse dining out "
            "to reduce this category."
            + knowledge_hint
        )

    if any(kw in question_lower for kw in ("most", "top", "category", "where", "spend")):
        if top_cat:
            cat_amount = next(
                (
                    float(item.get("amount", 0) or 0)
                    for item in breakdown
                    if item.get("category") == top_cat
                ),
                0.0,
            )
            return (
                f"Your highest spending category is {top_cat} at {cat_amount:,.2f}. "
                f"Your total spend is {total:,.2f} across {spending_summary.get('receipt_count', 0)} receipts."
                + knowledge_hint
            )

    if any(kw in question_lower for kw in ("anomal", "unusual", "weird", "spike")):
        if anomalies:
            msgs = [a.get("message", "") for a in anomalies[:2]]
            return "Unusual spending detected: " + " ".join(msgs) + knowledge_hint
        return "No strong spending anomalies were detected in the selected period." + knowledge_hint

    if any(kw in question_lower for kw in ("average", "avg", "typical", "mean")):
        return (
            f"Your average receipt amount is {avg:,.2f}. "
            f"Your total spend is {total:,.2f} across {spending_summary.get('receipt_count', 0)} receipts."
            + knowledge_hint
        )

    return (
        f"Your total spend is {total:,.2f} with an average of {avg:,.2f} per receipt. "
        f"Your top spending category is {top_cat or 'not yet identified'}. "
        "Review your category breakdown to identify areas where you can reduce costs."
        + knowledge_hint
    )


def _fallback_auto_insights(spending_summary: dict) -> list[dict]:
    insights: list[dict] = []
    total     = float(spending_summary.get("total_spend")   or 0)
    count     = int(spending_summary.get("receipt_count")   or 0)
    avg       = float(spending_summary.get("average_spend") or 0)
    top_cat   = spending_summary.get("top_category")
    breakdown = spending_summary.get("category_breakdown")  or []
    anomalies = spending_summary.get("anomalies")           or []
    trend     = spending_summary.get("monthly_trend")       or []

    if count == 0:
        return [
            {
                "type":     "tip",
                "title":    "No receipts uploaded yet",
                "message":  "Upload your first receipt to start receiving personalised spending insights.",
                "category": None,
                "amount":   None,
            }
        ]

    if top_cat:
        top_amount = next(
            (float(item.get("amount", 0) or 0) for item in breakdown if item.get("category") == top_cat),
            0.0,
        )
        insights.append(
            {
                "type":     "trend",
                "title":    f"Highest spend in {top_cat}",
                "message":  f"You spent {top_amount:,.2f} in {top_cat}, your largest category this period.",
                "category": top_cat,
                "amount":   round(top_amount, 2),
            }
        )

    if breakdown:
        top_item      = breakdown[0]
        top_pct       = float(top_item.get("percentage", 0) or 0)
        top_cat_name  = top_item.get("category", "")
        if top_pct >= 40:
            insights.append(
                {
                    "type":     "alert",
                    "title":    "Spending heavily concentrated",
                    "message":  (
                        f"{top_cat_name} makes up {top_pct:.1f}% of your spending. "
                        "Diversifying your budget across categories can improve financial resilience."
                    ),
                    "category": top_cat_name,
                    "amount":   round(float(top_item.get("amount", 0) or 0), 2),
                }
            )

    if len(breakdown) < 3 and count >= 5:
        insights.append(
            {
                "type":     "tip",
                "title":    "Low spending category diversity",
                "message":  (
                    "Your receipts cover very few categories. "
                    "Make sure all spending types are being tracked for a complete financial picture."
                ),
                "category": None,
                "amount":   None,
            }
        )

    if len(trend) >= 2:
        last_two = trend[-2:]
        prev_amt = float(last_two[0].get("amount", 0) or 0)
        curr_amt = float(last_two[1].get("amount", 0) or 0)
        if prev_amt > 0 and curr_amt > prev_amt * 1.20:
            increase_pct = ((curr_amt - prev_amt) / prev_amt) * 100
            insights.append(
                {
                    "type":     "alert",
                    "title":    "Spending increased recently",
                    "message":  (
                        f"Your spending rose by {increase_pct:.1f}% compared to the previous period "
                        f"({prev_amt:,.2f} to {curr_amt:,.2f}). Review recent receipts for unusual charges."
                    ),
                    "category": None,
                    "amount":   round(curr_amt, 2),
                }
            )

    for anomaly in anomalies[:2]:
        insights.append(
            {
                "type":     "anomaly",
                "title":    "Unusual spending detected",
                "message":  anomaly.get("message", "An unusually high transaction was detected."),
                "category": anomaly.get("category"),
                "amount":   anomaly.get("amount"),
            }
        )

    if avg > 0:
        insights.append(
            {
                "type":     "tip",
                "title":    "Track your average spend",
                "message":  (
                    f"Your average receipt is {avg:,.2f}. "
                    "Receipts significantly above this average are worth a closer review."
                ),
                "category": None,
                "amount":   round(avg, 2),
            }
        )

    return insights[:6]


# ──────────────────────────────────────────────────────────────────────────────
# JSON insight parser
# ──────────────────────────────────────────────────────────────────────────────


def _parse_insights_json(text: str) -> list[dict] | None:
    import json
    import re

    match = re.search(r"\[.*\]", text, flags=re.DOTALL)
    if not match:
        return None

    try:
        data = json.loads(match.group(0))
        if not isinstance(data, list):
            return None
        cleaned: list[dict] = []
        for item in data:
            if isinstance(item, dict) and "title" in item and "message" in item:
                cleaned.append(
                    {
                        "type":     item.get("type", "tip"),
                        "title":    str(item.get("title", "Insight")),
                        "message":  str(item.get("message", "")),
                        "category": item.get("category"),
                        "amount":   item.get("amount"),
                    }
                )
        return cleaned if cleaned else None
    except (json.JSONDecodeError, ValueError):
        return None


# ──────────────────────────────────────────────────────────────────────────────
# Advisor class
# ──────────────────────────────────────────────────────────────────────────────


class Advisor:
    def __init__(self, top_k: int = RAG_TOP_K) -> None:
        self._top_k = top_k
        self._retriever = None
        self._retriever_ready = False

    def _get_retriever(self):
        if self._retriever_ready:
            return self._retriever

        try:
            from rag.retriever import Retriever
        except ImportError:
            try:
                from retriever import Retriever
            except ImportError:
                logger.warning("Could not import Retriever — RAG knowledge will be unavailable")
                self._retriever_ready = True
                return None

        try:
            self._retriever = Retriever()
            self._retriever_ready = True
        except Exception as exc:
            logger.warning("Failed to initialise Retriever: %s", exc)
            self._retriever_ready = True

        return self._retriever

    def _retrieve(self, query: str) -> list[dict]:
        retriever = self._get_retriever()
        if retriever is None:
            return []

        try:
            return retriever.search(query, top_k=self._top_k)
        except Exception as exc:
            logger.warning("Retrieval failed for query %r: %s", query[:60], exc)
            return []

    def _deduplicate_sources(self, chunks: list[dict]) -> list[str]:
        seen: set[str] = set()
        sources: list[str] = []
        for chunk in chunks:
            title  = chunk.get("title")  or ""
            source = chunk.get("source") or ""
            key = title or source
            if key and key not in seen:
                seen.add(key)
                sources.append(title if title else source)
        return sources

    # ──────────────────────────────────────────────────────────
    # advise
    # ──────────────────────────────────────────────────────────

    def advise(self, user_question: str, spending_summary: dict) -> dict[str, Any]:
        if not user_question or not user_question.strip():
            return {
                "answer":   "Please provide a question about your spending.",
                "sources":  [],
                "insights": [],
            }

        chunks           = self._retrieve(user_question)
        spending_context = _format_spending_summary(spending_summary)
        knowledge_context = _format_retrieved_chunks(chunks)
        sources          = self._deduplicate_sources(chunks)

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
            "answer":   answer.strip(),
            "sources":  sources,
            "insights": [],
        }

    # ──────────────────────────────────────────────────────────
    # auto_insights
    # ──────────────────────────────────────────────────────────

    def auto_insights(self, spending_summary: dict) -> list[dict[str, Any]]:
        top_cat = spending_summary.get("top_category") or "spending"
        query   = f"advice for reducing {top_cat} spending and managing personal finances"

        chunks            = self._retrieve(query)
        spending_context  = _format_spending_summary(spending_summary)
        knowledge_context = _format_retrieved_chunks(chunks)

        groq_client = _get_groq_client()
        insights: list[dict] | None = None

        if groq_client:
            prompt = _build_auto_insights_prompt(spending_context, knowledge_context)
            raw    = _call_groq(groq_client, prompt)
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


# ──────────────────────────────────────────────────────────────────────────────
# CLI smoke test
# ──────────────────────────────────────────────────────────────────────────────


if __name__ == "__main__":
    import json

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s  %(levelname)-8s  %(message)s",
        datefmt="%H:%M:%S",
    )

    sample_summary = {
        "total_spend":    18450.75,
        "receipt_count":  34,
        "average_spend":  542.67,
        "top_category":   "Dining",
        "category_breakdown": [
            {"category": "Dining",    "amount": 6200.00, "percentage": 33.6},
            {"category": "Groceries", "amount": 4800.00, "percentage": 26.0},
            {"category": "Transport", "amount": 3100.00, "percentage": 16.8},
            {"category": "Utilities", "amount": 2200.00, "percentage": 11.9},
            {"category": "Other",     "amount": 2150.75, "percentage": 11.7},
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