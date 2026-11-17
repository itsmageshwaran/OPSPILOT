import os
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any
from jose import jwt, JWTError
import bcrypt
from fastapi import HTTPException, status, Header, Query

# ==============================================================================
# Environment Variables & Secrets Management: OpsPilot Authentication
# ==============================================================================
SECRET_KEY = os.getenv("JWT_SECRET_KEY")
if not SECRET_KEY:
    if os.getenv("ENVIRONMENT", "").lower() in ("production", "prod"):
        raise RuntimeError(
            "FATAL: JWT_SECRET_KEY environment variable must be set in production! "
            "Insecure fallback credentials are prohibited."
        )
    SECRET_KEY = "shopflow-secure-dev-jwt-secret-key-32bytes-entropy-minimum"

ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("JWT_EXPIRE_MINUTES", "1440"))

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Password verification using constant-time bcrypt checkpw."""
    if not plain_password or not hashed_password:
        return False
    try:
        plain_bytes = plain_password.encode("utf-8")[:72]
        hash_bytes = hashed_password.encode("utf-8")
        return bcrypt.checkpw(plain_bytes, hash_bytes)
    except Exception:
        return False

def get_password_hash(password: str) -> str:
    """Secure password hashing with bcrypt using 12 salt rounds."""
    if not password:
        raise ValueError("Password cannot be empty")
    plain_bytes = password.encode("utf-8")[:72]
    salt = bcrypt.gensalt(rounds=12)
    return bcrypt.hashpw(plain_bytes, salt).decode("utf-8")

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """JWT issuance: Encodes payload claims and cryptographic signature."""
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

def decode_token(token: str) -> Optional[Dict[str, Any]]:
    """JWT verification: Decodes and verifies signature, algorithm, and claims."""
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except JWTError:
        return None

def verify_jwt_authorization(authorization: Optional[str] = Header(None)) -> Dict[str, Any]:
    """
    FastAPI dependency for endpoints requiring Bearer JWT authorization.
    Rejects missing or invalid tokens with HTTP 401 Unauthorized.
    """
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or malformed Authorization header. Expected 'Bearer <token>'",
            headers={"WWW-Authenticate": "Bearer"}
        )
    token = authorization.split(" ", 1)[1].strip()
    payload = decode_token(token)
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid, expired, or tampered JWT token",
            headers={"WWW-Authenticate": "Bearer"}
        )
    return payload
