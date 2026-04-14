"""
advisor.py - Vispend AI RAG Pipeline

Combines:
1. user receipt analytics summary
2. retrieved budgeting knowledge chunks
3. Groq LLM generation

to produce grounded AI financial guidance.
"""

import os
import logging
from groq import Groq

try:
    from src.rag.retriever import Retriever
except ImportError:
    from retriever import Retriever

logger = logging.getLogger(__name__)

GROQ_MODEL  = "meta-llama/llama-4-scout-17b-16e-instruct"
TOP_K       = 5
MAX_TOKENS  = 800


SYSTEM_PROMPT = """
You are a personal finance assistant inside Vispend AI, a receipt analytics application.

Your role:
- Help users understand their spending habits.
- Use both the user's spending summary and retrieved finance education content.
- Give practical, simple, safe budgeting guidance.
- Do not invent facts.
- Do not give tax, legal, or investment advice.
- Cite the source title in brackets after each recommendation, for example:
  [Consumer tips for managing spending]

Keep the response concise, friendly, and actionable.
Prefer bullet points when giving recommendations.
"""


class Advisor:
    def __init__(self, groq_api_key=None):
        key = groq_api_key or os.getenv("GROQ_API_KEY")

        # Fix #4 - was: print("Loaded GROQ_API_KEY:", "YES" if key else "NO")
        logger.debug("GROQ_API_KEY loaded: %s", "YES" if key else "NO")

        if not key:
            raise ValueError(
                "Groq API key not found. Set it with:\n"
                "$env:GROQ_API_KEY=\"your_key_here\""
            )

        self.client    = Groq(api_key=key)
        self.retriever = Retriever()

    def _format_spending_summary(self, spending_summary: dict) -> str:
        if not spending_summary:
            return "No spending summary provided."

        lines = ["User Spending Summary:"]
        for key, value in spending_summary.items():
            pretty_key = key.replace("_", " ").title()
            lines.append(f"- {pretty_key}: {value}")
        return "\n".join(lines)

    def _build_context(self, chunks: list) -> str:
        context_parts = []
        for i, chunk in enumerate(chunks, start=1):
            context_parts.append(
                f"[{i}] Source Title: {chunk['doc_title']}\n"
                f"Source Organization: {chunk['source']}\n"
                f"Section: {chunk['section_title']}\n"
                f"Content:\n{chunk['text']}"
            )
        return "\n\n".join(context_parts)

    def _build_prompt(
        self,
        user_question: str,
        spending_summary: dict,
        chunks: list,
    ) -> str:
        spending_text = self._format_spending_summary(spending_summary)
        context_text  = self._build_context(chunks)

        prompt = f"""
{spending_text}

Retrieved Knowledge Base Excerpts:
{context_text}

User Question:
{user_question}

Instructions:
- Answer using only the user spending summary and the retrieved excerpts.
- Give practical spending or budgeting suggestions.
- Make the answer specific when possible.
- Cite the source title in brackets after each recommendation.
- Do not mention that you are using retrieval or chunks.
"""
        return prompt.strip()

    def advise(
        self,
        user_question: str,
        spending_summary: dict = None,
        top_k: int = TOP_K,
    ) -> dict:
        chunks = self.retriever.retrieve(user_question, top_k=top_k)
        prompt = self._build_prompt(user_question, spending_summary or {}, chunks)

        response = self.client.chat.completions.create(
            model=GROQ_MODEL,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user",   "content": prompt},
            ],
            temperature=0.3,
            max_tokens=MAX_TOKENS,
        )

        answer  = response.choices[0].message.content.strip()
        sources = sorted({chunk["doc_title"] for chunk in chunks})

        return {
            "answer":  answer,
            "sources": sources,
            "chunks":  chunks,
        }

    def auto_insights(self, spending_summary: dict) -> list:
        questions = []

        top_category  = spending_summary.get("top_category", "")
        anomaly_count = spending_summary.get("anomaly_count", 0)
        month_trend   = spending_summary.get("month_trend", "")

        if top_category:
            questions.append(
                f"How can I better manage my {top_category} spending?"
            )
        if anomaly_count and int(anomaly_count) > 0:
            questions.append(
                "What should I do when I notice unusually high purchases?"
            )
        if month_trend == "increasing":
            questions.append(
                "What are good strategies when monthly spending keeps rising?"
            )
        if not questions:
            questions.append(
                "What are the most important budgeting habits to build?"
            )

        insights = []
        for q in questions[:2]:
            result = self.advise(q, spending_summary=spending_summary)
            insights.append({
                "question": q,
                "answer":   result["answer"],
                "sources":  result["sources"],
                "chunks":   result["chunks"],
            })

        return insights


if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    advisor = Advisor()

    sample_summary = {
        "total_receipts":    86,
        "total_spend_usd":   1463.52,
        "top_category":      "Food & Beverage",
        "top_category_usd":  272.40,
        "anomaly_count":     3,
        "month_trend":       "increasing",
        "avg_receipt_usd":   17.02,
    }

    result = advisor.advise(
        user_question="How can I reduce my food spending?",
        spending_summary=sample_summary,
    )

    print("\nAnswer:\n")
    print(result["answer"])
    print("\nSources used:")
    print(result["sources"])