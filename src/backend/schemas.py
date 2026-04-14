from pydantic import BaseModel, EmailStr, Field
from typing import Optional, List, Any
from datetime import datetime


# ─── Auth / User ────────────────────────────────────────────────────────────

class UserCreate(BaseModel):
    email: EmailStr
    username: str = Field(..., min_length=3, max_length=50)
    password: str = Field(..., min_length=6)
    full_name: Optional[str] = None


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class UserOut(BaseModel):
    id: int
    email: str
    username: str
    full_name: Optional[str]
    is_active: bool
    is_verified: bool
    created_at: datetime

    class Config:
        from_attributes = True


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


class TokenData(BaseModel):
    user_id: Optional[int] = None


# ─── Line Items ──────────────────────────────────────────────────────────────

class LineItemOut(BaseModel):
    id: int
    description: Optional[str]
    description_translated: Optional[str]
    quantity: Optional[float]
    unit_price: Optional[float]
    total_price: Optional[float]
    category: Optional[str]

    class Config:
        from_attributes = True


# ─── Receipt ─────────────────────────────────────────────────────────────────

class ReceiptUpdate(BaseModel):
    merchant: Optional[str] = None
    total_amount: Optional[float] = None
    currency: Optional[str] = None
    receipt_date: Optional[datetime] = None
    category: Optional[str] = None
    subcategory: Optional[str] = None
    payment_method: Optional[str] = None
    notes: Optional[str] = None
    user_verified: Optional[bool] = None


class ReceiptOut(BaseModel):
    id: int
    filename: str
    merchant: Optional[str]
    merchant_normalized: Optional[str]
    total_amount: Optional[float]
    currency: Optional[str]
    receipt_date: Optional[datetime]
    tax_amount: Optional[float]
    tip_amount: Optional[float]
    payment_method: Optional[str]
    category: Optional[str]
    subcategory: Optional[str]
    category_confidence: Optional[float]
    category_source: Optional[str]
    needs_review: bool
    processing_status: str
    processing_error: Optional[str]
    detected_language: Optional[str]
    user_verified: bool
    notes: Optional[str]
    line_items_detail: List[LineItemOut] = []
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class ReceiptListOut(BaseModel):
    total: int
    page: int
    page_size: int
    items: List[ReceiptOut]


# ─── Analytics ───────────────────────────────────────────────────────────────

class CategorySpend(BaseModel):
    category: str
    total: float
    count: int
    percentage: float


class MonthlyTrend(BaseModel):
    month: str
    total: float
    count: int


class MerchantSummary(BaseModel):
    merchant: str
    total: float
    count: int
    last_visit: Optional[datetime]


class AnalyticsSummary(BaseModel):
    total_spend: float
    total_receipts: int
    avg_per_receipt: float
    top_category: Optional[str]
    top_merchant: Optional[str]
    uncategorized_count: int
    needs_review_count: int
    currency: str


class AnalyticsResponse(BaseModel):
    summary: AnalyticsSummary
    category_breakdown: List[CategorySpend]
    monthly_trends: List[MonthlyTrend]
    top_merchants: List[MerchantSummary]


# ─── AI Insights ─────────────────────────────────────────────────────────────

class InsightItem(BaseModel):
    type: str          # 'alert', 'tip', 'trend', 'anomaly'
    title: str
    description: str
    value: Optional[Any] = None
    category: Optional[str] = None


class InsightsResponse(BaseModel):
    insights: List[InsightItem]
    generated_at: datetime


# ─── Ask AI ──────────────────────────────────────────────────────────────────

class AskQuestion(BaseModel):
    question: str = Field(..., min_length=3, max_length=500)


class AskResponse(BaseModel):
    question: str
    answer: str
    related_receipts: Optional[List[int]] = None
    generated_at: datetime


# ─── Budget ──────────────────────────────────────────────────────────────────

class BudgetCreate(BaseModel):
    category: str
    amount: float = Field(..., gt=0)
    period: str = "monthly"
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None


class BudgetOut(BaseModel):
    id: int
    category: str
    amount: float
    period: str
    start_date: Optional[datetime]
    end_date: Optional[datetime]
    created_at: datetime

    class Config:
        from_attributes = True


# ─── Category Correction ─────────────────────────────────────────────────────

class CategoryCorrection(BaseModel):
    receipt_id: int
    corrected_category: str
    corrected_subcategory: Optional[str] = None