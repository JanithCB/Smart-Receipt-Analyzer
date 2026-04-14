# src/backend/services/analytics_service.py
from collections import defaultdict
from datetime import date
from statistics import mean, pstdev
from sqlalchemy.orm import Session
from ..models import Receipt  # Fix #5 - was: from backend.models import Receipt


MONTH_NAMES = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
               "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def _filter_period(receipts, year=None, month=None):
    if year is None and month is None:
        today = date.today()
        year, month = today.year, today.month

    out = []
    for r in receipts:
        # Fix: correct column name is receipt_date, not date
        if not r.receipt_date:
            continue
        if year is not None and r.receipt_date.year != int(year):
            continue
        if month is not None and r.receipt_date.month != int(month):
            continue
        out.append(r)
    return out


def build_spending_summary(db: Session, user_id: int, year=None, month=None):
    # Fix: correct column is owner_id, not user_id
    all_receipts = db.query(Receipt).filter(Receipt.owner_id == user_id).all()
    filtered = _filter_period(all_receipts, year=year, month=month)

    # Fix: correct column is total_amount, not total
    totals = [float(r.total_amount or 0.0) for r in filtered]
    total_spend = round(sum(totals), 2)
    total_receipts = len(filtered)
    avg_receipt = round(total_spend / total_receipts, 2) if total_receipts else 0.0

    category_totals = defaultdict(float)
    for r in filtered:
        category_totals[r.category or "Other"] += float(r.total_amount or 0.0)

    sorted_categories = sorted(
        category_totals.items(), key=lambda x: x[1], reverse=True
    )
    top_category = sorted_categories[0][0] if sorted_categories else "None"
    top_category_amount = round(sorted_categories[0][1], 2) if sorted_categories else 0.0

    today = date.today()
    selected_year = int(year or today.year)
    monthly_buckets = {m: 0.0 for m in range(1, 13)}
    for r in all_receipts:
        # Fix: receipt_date column
        if r.receipt_date and r.receipt_date.year == selected_year:
            monthly_buckets[r.receipt_date.month] += float(r.total_amount or 0.0)

    monthly_trend = [
        {"month": MONTH_NAMES[m - 1], "total": round(monthly_buckets[m], 2)}
        for m in range(1, 13)
    ]

    category_breakdown = [
        {"category": k, "total": round(v, 2)}
        for k, v in sorted_categories
    ]

    if len(totals) >= 2:
        m = mean(totals)
        s = pstdev(totals)
        anomaly_count = len([x for x in totals if x > m + (2 * s)])
    else:
        anomaly_count = 0

    month_trend_flag = "stable"
    if len(monthly_trend) >= 2:
        non_zero = [x["total"] for x in monthly_trend if x["total"] > 0]
        if len(non_zero) >= 2:
            month_trend_flag = (
                "increasing" if non_zero[-1] > non_zero[-2] else "decreasing"
            )

    return {
        "total_spend": total_spend,
        "total_receipts": total_receipts,
        "avg_receipt": avg_receipt,
        "top_category": top_category,
        "top_category_amount": top_category_amount,
        "monthly_trend": monthly_trend,
        "category_breakdown": category_breakdown,
        "anomaly_count": anomaly_count,
        "month_trend": month_trend_flag,
    }


def get_recent_receipts(db: Session, user_id: int, limit: int = 20):
    rows = (
        db.query(Receipt)
        .filter(Receipt.owner_id == user_id)  # Fix: owner_id not user_id
        .order_by(Receipt.created_at.desc())
        .limit(limit)
        .all()
    )
    return rows