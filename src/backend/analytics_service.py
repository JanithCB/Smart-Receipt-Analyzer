# src/backend/analytics_service.py

from collections import defaultdict
from datetime import datetime, timedelta
from statistics import mean, pstdev
from typing import Any

from sqlalchemy.orm import Session

from backend.models import Receipt


VALID_PERIODS = {"week", "month", "year", "all"}


def _get_period_start(period: str) -> datetime | None:
    now = datetime.utcnow()
    normalized = (period or "month").lower()

    if normalized == "week":
        return now - timedelta(days=7)
    if normalized == "month":
        return now - timedelta(days=30)
    if normalized == "year":
        return now - timedelta(days=365)
    return None


def _base_receipts_query(db: Session, user_id: int):
    return db.query(Receipt).filter(
        Receipt.user_id == user_id,
        Receipt.processing_status == "done",
        Receipt.total_amount.isnot(None),
    )


def _filter_receipts_by_period(receipts: list[Receipt], period: str) -> list[Receipt]:
    if (period or "month").lower() == "all":
        return receipts

    start = _get_period_start(period)
    if start is None:
        return receipts

    filtered: list[Receipt] = []
    for receipt in receipts:
        reference_date = receipt.receipt_date or receipt.created_at
        if reference_date and reference_date >= start:
            filtered.append(receipt)
    return filtered


def detect_anomalies(receipts: list[Receipt]) -> list[dict[str, Any]]:
    amounts = [float(r.total_amount) for r in receipts if r.total_amount is not None]
    anomalies: list[dict[str, Any]] = []

    if len(amounts) < 3:
        return anomalies

    avg = mean(amounts)
    deviation = pstdev(amounts)

    if deviation <= 0:
        return anomalies

    for receipt in receipts:
        if receipt.total_amount is None:
            continue

        amount = float(receipt.total_amount)
        if amount > avg + (2 * deviation):
            anomalies.append(
                {
                    "type": "high_spend",
                    "message": (
                        f"Unusually high receipt detected for "
                        f"{receipt.merchant or 'Unknown merchant'}: {amount:.2f}."
                    ),
                    "category": receipt.category,
                    "amount": amount,
                    "period": (
                        (receipt.receipt_date or receipt.created_at).strftime("%Y-%m")
                        if (receipt.receipt_date or receipt.created_at)
                        else None
                    ),
                    "metadata": {
                        "receipt_id": receipt.id,
                        "average_amount": round(avg, 2),
                        "std_deviation": round(deviation, 2),
                    },
                }
            )

    return anomalies[:10]


def get_recent_receipts(db: Session, user_id: int, limit: int = 10) -> list[Receipt]:
    return (
        _base_receipts_query(db, user_id)
        .order_by(Receipt.created_at.desc())
        .limit(limit)
        .all()
    )


def get_spending_summary(db: Session, user_id: int, period: str = "month") -> dict[str, Any]:
    normalized_period = (period or "month").lower()
    if normalized_period not in VALID_PERIODS:
        normalized_period = "month"

    receipts = _base_receipts_query(db, user_id).all()
    receipts = _filter_receipts_by_period(receipts, normalized_period)

    if not receipts:
        return {
            "total_spend": 0.0,
            "receipt_count": 0,
            "average_spend": 0.0,
            "top_category": None,
            "category_breakdown": [],
            "monthly_trend": [],
            "top_merchants": [],
            "anomalies": [],
        }

    total_spend = round(sum(float(r.total_amount or 0) for r in receipts), 2)
    receipt_count = len(receipts)
    average_spend = round(total_spend / receipt_count, 2) if receipt_count else 0.0

    category_totals: dict[str, float] = defaultdict(float)
    category_counts: dict[str, int] = defaultdict(int)
    merchant_totals: dict[str, float] = defaultdict(float)
    merchant_counts: dict[str, int] = defaultdict(int)
    monthly_amounts: dict[str, float] = defaultdict(float)
    monthly_counts: dict[str, int] = defaultdict(int)

    for receipt in receipts:
        amount = float(receipt.total_amount or 0)
        category = receipt.category or "Other"
        merchant = receipt.merchant or "Unknown"

        category_totals[category] += amount
        category_counts[category] += 1

        merchant_totals[merchant] += amount
        merchant_counts[merchant] += 1

        reference_date = receipt.receipt_date or receipt.created_at
        if reference_date:
            month_key = reference_date.strftime("%Y-%m")
            monthly_amounts[month_key] += amount
            monthly_counts[month_key] += 1

    top_category = None
    if category_totals:
        top_category = max(category_totals.items(), key=lambda item: item[1])[0]

    category_breakdown = []
    for category, amount in sorted(category_totals.items(), key=lambda item: item[1], reverse=True):
        percentage = round((amount / total_spend) * 100, 2) if total_spend > 0 else 0.0
        category_breakdown.append(
            {
                "category": category,
                "amount": round(amount, 2),
                "count": category_counts[category],
                "percentage": percentage,
            }
        )

    monthly_trend = []
    for month_key in sorted(monthly_amounts.keys()):
        monthly_trend.append(
            {
                "period": month_key,
                "amount": round(monthly_amounts[month_key], 2),
                "count": monthly_counts[month_key],
            }
        )

    top_merchants = []
    for merchant, amount in sorted(merchant_totals.items(), key=lambda item: item[1], reverse=True)[:10]:
        top_merchants.append(
            {
                "merchant": merchant,
                "amount": round(amount, 2),
                "count": merchant_counts[merchant],
            }
        )

    anomalies = detect_anomalies(receipts)

    return {
        "total_spend": total_spend,
        "receipt_count": receipt_count,
        "average_spend": average_spend,
        "top_category": top_category,
        "category_breakdown": category_breakdown,
        "monthly_trend": monthly_trend,
        "top_merchants": top_merchants,
        "anomalies": anomalies,
    }