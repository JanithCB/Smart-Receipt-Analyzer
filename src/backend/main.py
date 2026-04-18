# src/backend/main.py

import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv

# Load .env from src/.env before importing app modules that read env vars
load_dotenv(Path(__file__).resolve().parents[1] / ".env")

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.database import Base, engine
from backend.routers import router


def configure_logging() -> None:
    log_level = os.getenv("LOG_LEVEL", "INFO").upper()

    logging.basicConfig(
        level=getattr(logging, log_level, logging.INFO),
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )

    for logger_name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        logging.getLogger(logger_name).setLevel(getattr(logging, log_level, logging.INFO))


logger = logging.getLogger(__name__)
configure_logging()


def get_allowed_origins() -> list[str]:
    origins_env = os.getenv("BACKEND_CORS_ORIGINS", "").strip()
    if origins_env:
        return [origin.strip() for origin in origins_env.split(",") if origin.strip()]

    return [
        "http://localhost",
        "http://localhost:3000",
        "http://localhost:5173",
        "http://127.0.0.1",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:5173",
    ]


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting Vispend AI Backend")
    Base.metadata.create_all(bind=engine)
    logger.info("Database tables ensured")
    yield
    logger.info("Shutting down Vispend AI Backend")


app = FastAPI(
    title="Vispend AI Backend",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=get_allowed_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)


@app.get("/", tags=["System"])
def root() -> dict[str, str]:
    return {
        "message": "Vispend AI backend is running",
        "app": "Vispend AI Backend",
        "version": "1.0.0",
    }


@app.get("/health", tags=["System"])
def health() -> dict[str, bool | str]:
    return {
        "healthy": True,
        "status": "ok",
    }