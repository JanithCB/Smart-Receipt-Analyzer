# src/backend/routers/analytics.py
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

# Fix 1: absolute imports → relative imports (consistent with all other routers)
from ..dependencies import get_db, get_current_active_user
from ..models import User
from ..services.analytics_service import build_spending_summary, get_recent_receipts


router = APIRouter(prefix="/analytics", tags=["Analytics"])


# Fix 2: added bare /analytics endpoint so api_client.get_analytics() doesn't 404
@router.get("")
def analytics_root(
    period: str = "month",
    year: int | None = None,
    month: int | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),  # Fix 1: was get_current_user
):
    if period == "year":
        month = None
    return build_spending_summary(db, current_user.id, year=year, month=month)


@router.get("/summary")
def analytics_summary(
    period: str = "month",
    year: int | None = None,
    month: int | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),  # Fix 1: was get_current_user
):
    if period == "year":
        month = None
    return build_spending_summary(db, current_user.id, year=year, month=month)


@router.get("/recent")
def analytics_recent(
    limit: int = 20,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),  # Fix 1: was get_current_user
):
    rows = get_recent_receipts(db, current_user.id, limit=limit)
    return {
        "items": [
            {
                "id":             r.id,
                "date":           r.receipt_date.isoformat() if r.receipt_date else None,  # Fix 3: was r.date
                "merchant":       r.merchant,
                "category":       r.category,
                "total":          r.total_amount,      # Fix 3: was r.total
                "currency":       r.currency,
                "payment_method": r.payment_method,
            }
            for r in rows
        ]
    }