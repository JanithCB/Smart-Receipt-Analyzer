# src/backend/schemas.py

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class UserBase(BaseModel):
    email: EmailStr
    username: str = Field(min_length=3, max_length=100)
    full_name: str | None = Field(default=None, max_length=255)


class UserCreate(UserBase):
    password: str = Field(min_length=6, max_length=128)


class UserLogin(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class UserUpdate(BaseModel):
    email: EmailStr | None = None
    username: str | None = Field(default=None, min_length=3, max_length=100)
    full_name: str | None = Field(default=None, max_length=255)
    password: str | None = Field(default=None, min_length=6, max_length=128)


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: EmailStr
    username: str
    full_name: str | None = None
    is_active: bool
    is_superuser: bool
    created_at: datetime
    updated_at: datetime


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


class LineItemBase(BaseModel):
    item_name: str = Field(min_length=1, max_length=255)
    quantity: float | None = None
    unit_price: float | None = None
    total_price: float | None = None
    category: str | None = Field(default=None, max_length=100)
    notes: str | None = None


class LineItemOut(LineItemBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    receipt_id: int
    created_at: datetime
    updated_at: datetime


class ReceiptCreate(BaseModel):
    original_filename: str | None = Field(default=None, max_length=255)
    notes: str | None = None


class ReceiptUpdate(BaseModel):
    merchant: str | None = Field(default=None, max_length=255)
    total_amount: float | None = None
    currency: str | None = Field(default=None, max_length=16)
    receipt_date: datetime | None = None
    category: str | None = Field(default=None, max_length=100)
    subcategory: str | None = Field(default=None, max_length=100)
    notes: str | None = None
    needs_review: bool | None = None
    language: str | None = Field(default=None, max_length=32)


class ReceiptOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    original_filename: str
    file_path: str
    mime_type: str | None = None
    ocr_text: str | None = None
    translated_text: str | None = None
    merchant: str | None = None
    total_amount: float | None = None
    currency: str | None = None
    receipt_date: datetime | None = None
    category: str | None = None
    subcategory: str | None = None
    notes: str | None = None
    processing_status: str
    confidence: float | None = None
    category_source: str | None = None
    needs_review: bool
    language: str | None = None
    created_at: datetime
    updated_at: datetime
    line_items: list[LineItemOut] = Field(default_factory=list)


class PaginationMeta(BaseModel):
    page: int = Field(ge=1)
    page_size: int = Field(ge=1)
    total_items: int = Field(ge=0)
    total_pages: int = Field(ge=0)


class ReceiptListResponse(BaseModel):
    items: list[ReceiptOut]
    pagination: PaginationMeta


class BudgetBase(BaseModel):
    category: str = Field(min_length=1, max_length=100)
    amount_limit: float = Field(gt=0)
    period: str = Field(default="monthly", min_length=1, max_length=20)
    is_active: bool = True


class BudgetCreate(BudgetBase):
    pass


class BudgetUpdate(BaseModel):
    category: str | None = Field(default=None, min_length=1, max_length=100)
    amount_limit: float | None = Field(default=None, gt=0)
    period: str | None = Field(default=None, min_length=1, max_length=20)
    is_active: bool | None = None


class BudgetOut(BudgetBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    created_at: datetime
    updated_at: datetime


class CategoryCorrectionRequest(BaseModel):
    category: str = Field(min_length=1, max_length=100)
    subcategory: str | None = Field(default=None, max_length=100)


class CategoryBreakdownItem(BaseModel):
    category: str
    amount: float
    count: int
    percentage: float


class MonthlyTrendItem(BaseModel):
    period: str
    amount: float
    count: int


class RecentReceiptItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    merchant: str | None = None
    total_amount: float | None = None
    currency: str | None = None
    category: str | None = None
    receipt_date: datetime | None = None
    processing_status: str
    created_at: datetime


class TopMerchantItem(BaseModel):
    merchant: str
    amount: float
    count: int


class AnomalyItem(BaseModel):
    type: str
    message: str
    category: str | None = None
    amount: float | None = None
    period: str | None = None
    metadata: dict[str, Any] | None = None


class AnalyticsSummaryResponse(BaseModel):
    total_spend: float
    receipt_count: int
    average_spend: float
    pending_count: int = 0
    currency: str = "LKR"
    top_category: str | None = None
    category_breakdown: list[CategoryBreakdownItem] = Field(default_factory=list)
    monthly_trend: list[MonthlyTrendItem] = Field(default_factory=list)
    top_merchants: list[TopMerchantItem] = Field(default_factory=list)
    anomalies: list[AnomalyItem] = Field(default_factory=list)


class InsightItem(BaseModel):
    id: str
    type: str
    title: str
    message: str
    severity: str = "info"
    category: str | None = None
    amount: float | None = None
    metadata: dict[str, Any] | None = None


class AskAdvisorRequest(BaseModel):
    question: str = Field(min_length=1, max_length=1000)


class AskAdvisorResponse(BaseModel):
    answer: str
    sources: list[str] = Field(default_factory=list)
    insights: list[InsightItem] = Field(default_factory=list)