# src/backend/routers/advisor.py
import os
import json
import logging
from datetime import datetime, timedelta
from typing import List
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from ..database import get_db
from ..models import Receipt, User, Budget
from ..schemas import InsightsResponse, InsightItem, AskQuestion, AskResponse  # ✅ correct
from ..dependencies import get_current_active_user  # ✅ fix #2: was get_current_user

router = APIRouter(prefix="/advisor", tags=["AI Advisor"])
logger = logging.getLogger(__name__)


def _get_spending_context(db: Session, user_id: int, days: int = 60) -> dict:
    """Build a spending context dict for AI prompts."""
    since = datetime.utcnow() - timedelta(days=days)
    receipts = (
        db.query(Receipt)
        .filter(
            Receipt.owner_id == user_id,
            Receipt.processing_status == "done",
            Receipt.total_amount.isnot(None),
            Receipt.created_at >= since,
        )
        .all()
    )

    cat_map = {}
    merchant_map = {}
    monthly = {}

    for r in receipts:
        cat = r.category or "Other"
        cat_map.setdefault(cat, 0.0)
        cat_map[cat] += r.total_amount

        m = r.merchant_normalized or r.merchant or "Unknown"
        merchant_map.setdefault(m, 0.0)
        merchant_map[m] += r.total_amount

        mo = r.created_at.strftime("%Y-%m")
        monthly.setdefault(mo, 0.0)
        monthly[mo] += r.total_amount

    total = sum(cat_map.values())
    return {
        "total_spend": round(total, 2),
        "receipt_count": len(receipts),
        "category_totals": {k: round(v, 2) for k, v in sorted(cat_map.items(), key=lambda x: -x[1])},
        "top_merchants": dict(sorted(merchant_map.items(), key=lambda x: -x[1])[:5]),
        "monthly_totals": dict(sorted(monthly.items())),
        "needs_review": sum(1 for r in receipts if r.needs_review),
        "uncategorized": sum(1 for r in receipts if not r.category or r.category == "Other"),
    }


def _rule_based_insights(context: dict) -> List[InsightItem]:
    """Generate insights without AI when OpenAI/Groq is unavailable."""
    insights = []
    cats = context["category_totals"]
    monthly = context["monthly_totals"]
    total = context["total_spend"]

    if cats:
        top_cat, top_val = list(cats.items())[0]
        pct = round(top_val / total * 100) if total else 0
        insights.append(InsightItem(
            type="trend",
            title=f"Top Spending: {top_cat}",
            description=f"{top_cat} accounts for {pct}% of your recent spending ({top_val:.2f}).",
            value=top_val,
            category=top_cat,
        ))

    months = list(monthly.values())
    if len(months) >= 2:
        last, prev = months[-1], months[-2]
        change = ((last - prev) / prev * 100) if prev else 0
        direction = "increased" if change > 0 else "decreased"
        insights.append(InsightItem(
            type="alert" if change > 15 else "tip",
            title=f"Monthly Spend {direction.title()}",
            description=f"Your spending {direction} by {abs(change):.1f}% compared to the previous month.",
            value=round(change, 1),
        ))

    if context["uncategorized"] > 0:
        insights.append(InsightItem(
            type="alert",
            title="Uncategorized Receipts",
            description=f"You have {context['uncategorized']} receipts in 'Other'. Review them for accurate analytics.",
            value=context["uncategorized"],
        ))

    if context["needs_review"] > 0:
        insights.append(InsightItem(
            type="tip",
            title="Receipts Need Review",
            description=f"{context['needs_review']} receipts were flagged for low-confidence categorization.",
            value=context["needs_review"],
        ))

    dining = cats.get("Dining", 0)
    if total and dining / total > 0.30:
        insights.append(InsightItem(
            type="tip",
            title="High Dining Spend",
            description="Dining makes up over 30% of your spend. Consider meal planning to reduce costs.",
            value=round(dining, 2),
            category="Dining",
        ))

    return insights


def _ai_insights(context: dict) -> List[InsightItem]:
    """Generate richer insights using OpenAI if available."""
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return _rule_based_insights(context)

    try:
        from openai import OpenAI
        client = OpenAI(api_key=api_key)

        prompt = f"""You are a personal finance advisor analyzing receipt spending data.

Spending context (last 60 days):
{json.dumps(context, indent=2)}

Generate 4-6 actionable financial insights. Each must be one of: 'alert', 'tip', 'trend', 'anomaly'.

Return ONLY a JSON array:
[
  {{
    "type": "trend|alert|tip|anomaly",
    "title": "Short title (5 words max)",
    "description": "One clear, specific sentence.",
    "value": <optional number>,
    "category": "<optional category name>"
  }}
]"""

        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=600,
            temperature=0.4,
        )
        items = json.loads(response.choices[0].message.content.strip())
        return [InsightItem(**item) for item in items]

    except Exception as e:
        logger.warning(f"AI insights failed: {e}, falling back to rules")
        return _rule_based_insights(context)


def _rule_based_answer(question: str, context: dict) -> str:
    """Simple keyword-based Q&A fallback."""
    q = question.lower()
    cats = context["category_totals"]
    total = context["total_spend"]

    if "most" in q and ("spend" in q or "spent" in q):
        if cats:
            top = list(cats.items())[0]
            return f"Your highest spending category is {top[0]} at {top[1]:.2f}."

    if "total" in q:
        return f"Your total spending in the last 90 days is {total:.2f}."

    if "dining" in q or "food" in q or "restaurant" in q:
        return f"You spent {cats.get('Dining', 0):.2f} on Dining."

    if "transport" in q or "fuel" in q or "grab" in q:
        return f"You spent {cats.get('Transport', 0):.2f} on Transport."

    if "groceries" in q or "grocery" in q or "supermarket" in q:
        return f"You spent {cats.get('Groceries', 0):.2f} on Groceries."

    if "how many" in q and "receipt" in q:
        return f"You have {context['receipt_count']} receipts in the last 90 days."

    top_cat = list(cats.keys())[0] if cats else "N/A"
    return (
        f"Based on your last 90 days: total spend is {total:.2f} "
        f"across {context['receipt_count']} receipts. Top category: {top_cat}."
    )


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("/insights", response_model=InsightsResponse)
def get_insights(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),  # ✅ fixed
):
    context = _get_spending_context(db, current_user.id)

    if context["receipt_count"] == 0:
        return InsightsResponse(
            insights=[InsightItem(
                type="tip",
                title="No Data Yet",
                description="Upload your first receipts to get personalized spending insights.",
            )],
            generated_at=datetime.utcnow(),
        )

    return InsightsResponse(
        insights=_ai_insights(context),
        generated_at=datetime.utcnow(),
    )


# ✅ Fix #1: payload type was AskAdvisorRequest (doesn't exist) → AskQuestion
@router.post("/ask", response_model=AskResponse)
def ask_question(
    payload: AskQuestion,                                    # ✅ fixed
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),  # ✅ fixed
):
    context = _get_spending_context(db, current_user.id, days=90)
    api_key = os.getenv("OPENAI_API_KEY")

    if not api_key:
        return AskResponse(
            question=payload.question,
            answer=_rule_based_answer(payload.question, context),
            generated_at=datetime.utcnow(),
        )

    try:
        from openai import OpenAI
        client = OpenAI(api_key=api_key)

        prompt = f"""You are a helpful personal finance assistant.
The user asked: "{payload.question}"

Their spending data (last 90 days):
{json.dumps(context, indent=2)}

Answer concisely and specifically. Keep under 100 words."""

        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=200,
            temperature=0.5,
        )
        answer = response.choices[0].message.content.strip()

    except Exception as e:
        logger.warning(f"AI ask failed: {e}")
        answer = _rule_based_answer(payload.question, context)

    return AskResponse(
        question=payload.question,
        answer=answer,
        generated_at=datetime.utcnow(),
    )


# ✅ Kept your original /insights/auto endpoint — wired to same logic
@router.get("/insights/auto")
def auto_insights(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),  # ✅ fixed
):
    try:
        context = _get_spending_context(db, current_user.id)
        insights = _ai_insights(context)
        return {
            "items": [i.dict() for i in insights],
            "spending_summary": context,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Auto insights failed: {e}")