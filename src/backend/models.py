from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship

from backend.database import Base


class User(Base):
    __tablename__ = "users"

    id = Integer().with_variant(Integer, "sqlite")
    id = __import__("sqlalchemy").Column(id, primary_key=True, index=True)

    full_name = __import__("sqlalchemy").Column(String(255), nullable=True)
    username = __import__("sqlalchemy").Column(String(100), unique=True, index=True, nullable=False)
    email = __import__("sqlalchemy").Column(String(255), unique=True, index=True, nullable=False)
    hashed_password = __import__("sqlalchemy").Column(String(255), nullable=False)

    is_active = __import__("sqlalchemy").Column(Boolean, default=True, nullable=False)
    is_superuser = __import__("sqlalchemy").Column(Boolean, default=False, nullable=False)

    created_at = __import__("sqlalchemy").Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = __import__("sqlalchemy").Column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )

    receipts = relationship(
        "Receipt",
        back_populates="user",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    budgets = relationship(
        "Budget",
        back_populates="user",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    category_feedback = relationship(
        "CategoryFeedback",
        back_populates="user",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class Receipt(Base):
    __tablename__ = "receipts"

    id = __import__("sqlalchemy").Column(Integer, primary_key=True, index=True)
    user_id = __import__("sqlalchemy").Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    original_filename = __import__("sqlalchemy").Column(String(255), nullable=False)
    file_path = __import__("sqlalchemy").Column(String(500), nullable=False)
    mime_type = __import__("sqlalchemy").Column(String(100), nullable=True)

    ocr_text = __import__("sqlalchemy").Column(Text, nullable=True)
    translated_text = __import__("sqlalchemy").Column(Text, nullable=True)

    merchant = __import__("sqlalchemy").Column(String(255), index=True, nullable=True)
    total_amount = __import__("sqlalchemy").Column(Float, nullable=True)
    currency = __import__("sqlalchemy").Column(String(16), nullable=True)
    receipt_date = __import__("sqlalchemy").Column(DateTime, nullable=True)

    category = __import__("sqlalchemy").Column(String(100), index=True, nullable=True)
    subcategory = __import__("sqlalchemy").Column(String(100), nullable=True)
    notes = __import__("sqlalchemy").Column(Text, nullable=True)

    processing_status = __import__("sqlalchemy").Column(
        String(50),
        default="pending",
        nullable=False,
        index=True,
    )
    confidence = __import__("sqlalchemy").Column(Float, nullable=True)
    category_source = __import__("sqlalchemy").Column(String(50), nullable=True)
    needs_review = __import__("sqlalchemy").Column(Boolean, default=False, nullable=False, index=True)
    language = __import__("sqlalchemy").Column(String(32), nullable=True)

    created_at = __import__("sqlalchemy").Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = __import__("sqlalchemy").Column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )

    user = relationship("User", back_populates="receipts")
    line_items = relationship(
        "LineItem",
        back_populates="receipt",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="LineItem.id",
    )


class LineItem(Base):
    __tablename__ = "line_items"

    id = __import__("sqlalchemy").Column(Integer, primary_key=True, index=True)
    receipt_id = __import__("sqlalchemy").Column(
        Integer,
        ForeignKey("receipts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    item_name = __import__("sqlalchemy").Column(String(255), nullable=False)
    quantity = __import__("sqlalchemy").Column(Float, nullable=True)
    unit_price = __import__("sqlalchemy").Column(Float, nullable=True)
    total_price = __import__("sqlalchemy").Column(Float, nullable=True)
    category = __import__("sqlalchemy").Column(String(100), nullable=True)
    notes = __import__("sqlalchemy").Column(Text, nullable=True)

    created_at = __import__("sqlalchemy").Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = __import__("sqlalchemy").Column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )

    receipt = relationship("Receipt", back_populates="line_items")


class Budget(Base):
    __tablename__ = "budgets"
    __table_args__ = (
        UniqueConstraint("user_id", "category", "period", name="uq_budget_user_category_period"),
    )

    id = __import__("sqlalchemy").Column(Integer, primary_key=True, index=True)
    user_id = __import__("sqlalchemy").Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    category = __import__("sqlalchemy").Column(String(100), nullable=False, index=True)
    amount_limit = __import__("sqlalchemy").Column(Float, nullable=False)
    period = __import__("sqlalchemy").Column(String(20), default="monthly", nullable=False)
    is_active = __import__("sqlalchemy").Column(Boolean, default=True, nullable=False)

    created_at = __import__("sqlalchemy").Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = __import__("sqlalchemy").Column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )

    user = relationship("User", back_populates="budgets")


class CategoryFeedback(Base):
    __tablename__ = "category_feedback"

    id = __import__("sqlalchemy").Column(Integer, primary_key=True, index=True)
    user_id = __import__("sqlalchemy").Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    receipt_id = __import__("sqlalchemy").Column(
        Integer,
        ForeignKey("receipts.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    merchant = __import__("sqlalchemy").Column(String(255), nullable=False, index=True)
    merchant_normalized = __import__("sqlalchemy").Column(String(255), nullable=True, index=True)

    ai_predicted_category = __import__("sqlalchemy").Column(String(100), nullable=True)
    user_corrected_category = __import__("sqlalchemy").Column(String(100), nullable=False)

    ai_predicted_subcategory = __import__("sqlalchemy").Column(String(100), nullable=True)
    user_corrected_subcategory = __import__("sqlalchemy").Column(String(100), nullable=True)

    created_at = __import__("sqlalchemy").Column(DateTime, default=datetime.utcnow, nullable=False)

    user = relationship("User", back_populates="category_feedback")
    receipt = relationship("Receipt")