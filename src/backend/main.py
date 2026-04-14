# src/backend/main.py
# Run:
#   cd src
#   uvicorn backend.main:app --reload --port 8000
# Required env:
#   GROQ_API_KEY=...
#   OCR_SPACE_API_KEY=...

import os
import sys
import logging
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SRC_DIR = PROJECT_ROOT / "src"

for p in [str(PROJECT_ROOT), str(SRC_DIR)]:
    if p not in sys.path:
        sys.path.insert(0, p)

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

from backend.database import Base, engine
from backend.routers.auth import router as auth_router
from backend.routers.receipts import router as receipts_router
from backend.routers.analytics import router as analytics_router
from backend.routers.advisor import router as advisor_router

logger = logging.getLogger(__name__)

# Create all tables
Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="Vispend AI API",
    version="1.0.0",
    description="Receipt processing, analytics, and AI advisor backend.",
)

# ✅ Fix #8 — CORS: wildcard + credentials is rejected by browsers.
# Since this is a desktop app (PyQt6), we use explicit localhost origins.
# To allow additional origins, set ALLOWED_ORIGINS in your .env:
#   ALLOWED_ORIGINS=http://localhost,http://127.0.0.1,http://localhost:3000
_raw_origins = os.getenv(
    "ALLOWED_ORIGINS",
    "http://localhost,http://127.0.0.1,http://127.0.0.1:8000,http://localhost:8000"
)
ALLOWED_ORIGINS = [o.strip() for o in _raw_origins.split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,      # ✅ explicit — was ["*"]
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)
app.include_router(receipts_router)
app.include_router(analytics_router)
app.include_router(advisor_router)


@app.get("/")
def root():
    return {"message": "Vispend AI backend is running", "version": "1.0.0"}


@app.get("/health")
def health():
    return {"healthy": True}


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8000)