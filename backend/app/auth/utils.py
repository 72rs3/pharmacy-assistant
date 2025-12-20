import hashlib
import os
from datetime import datetime, timedelta
from typing import Optional

import bcrypt
from jose import jwt

ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24  # 1 day default

# IMPORTANT: Set a strong secret in production.
SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-change-me")

def _password_bytes(password: str) -> bytes:
    password_bytes = password.encode("utf-8")
    if len(password_bytes) > 72:
        return hashlib.sha256(password_bytes).digest()
    return password_bytes


def hash_password(password: str) -> str:
    password_bytes = _password_bytes(password)
    hashed = bcrypt.hashpw(password_bytes, bcrypt.gensalt())
    return hashed.decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    plain_bytes = _password_bytes(plain_password)
    return bcrypt.checkpw(plain_bytes, hashed_password.encode("utf-8"))


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt
