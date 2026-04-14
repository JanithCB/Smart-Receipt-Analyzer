# src/backend/models.py
from .database import Base                          # Base comes from database.py
from sqlalchemy import (
    Column, Integer, String, Float, DateTime,
    Text, Boolean, ForeignKey, JSON
)
from sqlalchemy.orm import relationship
# removed: from sqlalchemy.ext.declarative import declarative_base
# removed: Base = declarative_base()   <-- this was overwriting the imported Base
from datetime import datetime


class User(Base):
    __tablename__ = "users"

    id              = Column(Integer, primary_key=True, index=True)
    email           = Column(String, unique=True, index=True, nullable=False)
    username        = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    full_name       = Column(String, nullable=True)
    is_active       = Column(Boolean, default=True)
    is_verified     = Column(Boolean, default=False)
    created_at      = Column(DateTime, default=datetime.utcnow)
    updated_at      = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    receipts = relationship("Receipt",  back_populates="owner", cascade="all, delete-orphan")
    budgets  = relationship("Budget",   back_populates="owner", cascade="all, delete-orphan")


class Receipt(Base):
    __tablename__ = "receipts"

    id       = Column(Integer, primary_key=True, index=True)
    owner_id = Column(Integer, ForeignKey("users.id"), nullable=False)

    # File info
    filename  = Column(String, nullable=False)
    file_path = Column(String, nullable=True)
    file_size = Column(Integer, nullable=True)
    mime_type = Column(String, nullable=True)

    # OCR & Extraction
    raw_ocr_text       = Column(Text,    nullable=True)
    detected_language  = Column(String,  nullable=True)
    translated_text    = Column(Text,    nullable=True)
    ocr_confidence     = Column(Float,   nullable=True)

    # Parsed Fields
    merchant            = Column(String,   nullable=True)
    merchant_normalized = Column(String,   nullable=True)
    total_amount        = Column(Float,    nullable=True)
    currency            = Column(String,   nullable=True)
    receipt_date        = Column(DateTime, nullable=True)
    tax_amount          = Column(Float,    nullable=True)
    tip_amount          = Column(Float,    nullable=True)
    payment_method      = Column(String,   nullable=True)

    # AI Categorization
    category            = Column(String, nullable=True)
    subcategory         = Column(String, nullable=True)
    category_confidence = Column(Float,  nullable=True)
    category_source     = Column(String, nullable=True)  # ai, user, rule
    needs_review        = Column(Boolean, default=False)

    # Line Items (JSON list)
    line_items = Column(JSON, nullable=True)

    # Status
    processing_status = Column(String, default="pending")  # pending, processing, done, failed
    processing_error  = Column(Text,   nullable=True)

    # User corrections
    user_verified = Column(Boolean, default=False)
    notes         = Column(Text,    nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    owner            = relationship("User",     back_populates="receipts")
    line_items_detail = relationship("LineItem", back_populates="receipt", cascade="all, delete-orphan")


class LineItem(Base):
    __tablename__ = "line_items"

    id         = Column(Integer, primary_key=True, index=True)
    receipt_id = Column(Integer, ForeignKey("receipts.id"), nullable=False)

    description             = Column(String, nullable=True)
    description_translated  = Column(String, nullable=True)
    quantity                = Column(Float,  nullable=True)
    unit_price              = Column(Float,  nullable=True)
    total_price             = Column(Float,  nullable=True)
    category                = Column(String, nullable=True)

    receipt = relationship("Receipt", back_populates="line_items_detail")


class Budget(Base):
    __tablename__ = "budgets"

    id       = Column(Integer, primary_key=True, index=True)
    owner_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    category = Column(String, nullable=False)
    amount   = Column(Float,  nullable=False)
    period   = Column(String, default="monthly")  # monthly, weekly, yearly
    start_date = Column(DateTime, nullable=True)
    end_date   = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    owner = relationship("User", back_populates="budgets")


class CategoryFeedback(Base):
    __tablename__ = "category_feedback"

    id                      = Column(Integer, primary_key=True, index=True)
    user_id                 = Column(Integer, ForeignKey("users.id"),    nullable=False)
    receipt_id              = Column(Integer, ForeignKey("receipts.id"), nullable=False)
    merchant_normalized     = Column(String, nullable=True)
    ai_predicted_category   = Column(String, nullable=True)
    user_corrected_category = Column(String, nullable=False)
    created_at              = Column(DateTime, default=datetime.utcnow)