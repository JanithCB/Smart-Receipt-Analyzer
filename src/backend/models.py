from datetime import datetime

from sqlalchemy import (
    Boolean,
    Column,
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

    id = Column(Integer, primary_key=True, index=True)
    full_name = Column(String(255), nullable=True)
    username = Column(String(100), unique=True, index=True, nullable=False)
    email = Column(String(255), unique=True, index=True, nullable=False)
    hashed_password = Column(String(255), nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    is_superuser = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(
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

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    original_filename = Column(String(255), nullable=False)
    file_path = Column(String(500), nullable=False)
    mime_type = Column(String(100), nullable=True)

    ocr_text = Column(Text, nullable=True)
    translated_text = Column(Text, nullable=True)

    merchant = Column(String(255), index=True, nullable=True)
    total_amount = Column(Float, nullable=True)
    currency = Column(String(16), nullable=True)
    receipt_date = Column(DateTime, nullable=True)

    category = Column(String(100), index=True, nullable=True)
    subcategory = Column(String(100), nullable=True)
    notes = Column(Text, nullable=True)

    processing_status = Column(
        String(50),
        default="pending",
        nullable=False,
        index=True,
    )
    confidence = Column(Float, nullable=True)
    category_source = Column(String(50), nullable=True)
    needs_review = Column(Boolean, default=False, nullable=False, index=True)
    language = Column(String(32), nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(
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

    id = Column(Integer, primary_key=True, index=True)
    receipt_id = Column(
        Integer,
        ForeignKey("receipts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    item_name = Column(String(255), nullable=False)
    quantity = Column(Float, nullable=True)
    unit_price = Column(Float, nullable=True)
    total_price = Column(Float, nullable=True)
    category = Column(String(100), nullable=True)
    notes = Column(Text, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(
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

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    category = Column(String(100), nullable=False, index=True)
    amount_limit = Column(Float, nullable=False)
    period = Column(String(20), default="monthly", nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )

    user = relationship("User", back_populates="budgets")


class CategoryFeedback(Base):
    __tablename__ = "category_feedback"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    receipt_id = Column(
        Integer,
        ForeignKey("receipts.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    merchant = Column(String(255), nullable=False, index=True)
    merchant_normalized = Column(String(255), nullable=True, index=True)

    ai_predicted_category = Column(String(100), nullable=True)
    user_corrected_category = Column(String(100), nullable=False)

    ai_predicted_subcategory = Column(String(100), nullable=True)
    user_corrected_subcategory = Column(String(100), nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    user = relationship("User", back_populates="category_feedback")
    receipt = relationship("Receipt")