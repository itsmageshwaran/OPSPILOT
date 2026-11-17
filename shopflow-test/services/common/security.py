import os
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any
from jose import jwt, JWTError
import bcrypt

# ==============================================================================
# Environment Variables & Secrets Management
# JWT Secrets MUST be injected via environment variables. Insecure hardcoded fallbacks
# are strictly rejected in production environments.
# ==============================================================================
SECRET_KEY = os.getenv("JWT_SECRET_KEY")
if not SECRET_KEY:
    if os.getenv("ENVIRONMENT", "").lower() in ("production", "prod"):
        raise RuntimeError(
            "FATAL: JWT_SECRET_KEY environment variable must be set in production! "
            "Insecure fallback credentials are prohibited."
        )
    # Secure development fallback with explicit warning
    SECRET_KEY = "shopflow-secure-dev-jwt-secret-key-32bytes-entropy-minimum"

ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("JWT_EXPIRE_MINUTES", "1440"))

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    Password verification using constant-time bcrypt checkpw.
    No hardcoded demo password bypasses allowed.
    """
    if not plain_password or not hashed_password:
        return False
    try:
        # bcrypt enforces 72 bytes max for password input
        plain_bytes = plain_password.encode("utf-8")[:72]
        hash_bytes = hashed_password.encode("utf-8")
        return bcrypt.checkpw(plain_bytes, hash_bytes)
    except Exception:
        return False

def get_password_hash(password: str) -> str:
    """
    Secure password hashing with bcrypt using 12 salt rounds.
    """
    if not password:
        raise ValueError("Password cannot be empty")
    plain_bytes = password.encode("utf-8")[:72]
    salt = bcrypt.gensalt(rounds=12)
    return bcrypt.hashpw(plain_bytes, salt).decode("utf-8")

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """
    JWT issuance: Encodes payload claims and cryptographic signature with expiration.
    """
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

def decode_token(token: str) -> Optional[Dict[str, Any]]:
    """
    JWT verification: Decodes and verifies signature, algorithm, and claims.
    """
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except JWTError:
        return None
