# src/backend/security.py
from datetime import datetime, timedelta
from typing import Optional
import os
import bcrypt
from jose import JWTError, jwt


SECRET_KEY = os.getenv("SECRET_KEY", "your-super-secret-key-change-in-production-please")
ALGORITHM  = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "1440"))  # 24 hrs


# Fix 1: dropped passlib entirely — bcrypt directly avoids the
#         passlib 1.7.4 + bcrypt 4.x + Python 3.13 incompatibility


def hash_password(password: str) -> str:
    # Fix 2: encode to bytes, enforce 72-byte limit bcrypt requires
    secret = password.encode("utf-8")[:72]
    return bcrypt.hashpw(secret, bcrypt.gensalt()).decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    secret = plain_password.encode("utf-8")[:72]
    try:
        return bcrypt.checkpw(secret, hashed_password.encode("utf-8"))
    except Exception:
        return False


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    expire    = datetime.utcnow() + (
        expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def decode_token(token: str) -> Optional[dict]:
    try:
        return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except JWTError:
        return None