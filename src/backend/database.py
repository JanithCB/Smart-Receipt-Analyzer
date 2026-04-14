# src/backend/database.py
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base, Session
from typing import Generator
import os


DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "sqlite:///./receipt_app.db"
)

connect_args = {}
if DATABASE_URL.startswith("sqlite"):
    connect_args = {"check_same_thread": False}

engine = create_engine(
    DATABASE_URL,
    connect_args=connect_args,
    echo=False,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Fix: Base must be defined here and imported by models.py
# main.py does: from backend.database import Base, engine
Base = declarative_base()


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def create_tables():
    from . import models  # noqa: F401 - ensures all models are registered
    Base.metadata.create_all(bind=engine)