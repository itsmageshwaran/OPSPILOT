import os
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any
import jwt
from jwt.exceptions import PyJWTError as JWTError
import bcrypt
from fastapi import APIRouter, HTTPException, status, Header, Depends
from pydantic import BaseModel, Field

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

# Simulated user credential store for authentication demonstration
demo_users_db: Dict[str, Dict[str, Any]] = {
    "admin@opspilot.dev": {
        "id": "usr_admin_01",
        "email": "admin@opspilot.dev",
        "full_name": "OpsPilot Administrator",
        "role": "admin",
        # Bcrypt hash for password 'SecureAdminPass2026!'
        "password_hash": "$2b$12$e0x4K5Qy7P3Lh1J8v5Wfqu6w4aL6N1B6.K5q0zR5yT5p2X9y7Z.6O"
    }
}


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


# ------------------------------------------------------------------------------
# Authentication API Router (Registration, Login, Token Verification)
# ------------------------------------------------------------------------------
router = APIRouter(prefix="/api/auth", tags=["Auth & Security (JWT & Bcrypt)"])


class RegisterRequest(BaseModel):
    email: str = Field(..., pattern=r"^[^@]+@[^@]+\.[^@]+$", description="User email address")
    password: str = Field(..., min_length=8, description="Plaintext password to be bcrypt-hashed")
    full_name: str = Field("SRE Engineer", description="User full name")
    role: str = Field("operator", description="RBAC role: admin, operator, or viewer")


class LoginRequest(BaseModel):
    email: str = Field(..., description="User email address")
    password: str = Field(..., description="Plaintext password to verify against bcrypt hash")


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in_minutes: int
    user: Dict[str, Any]


@router.post("/register", status_code=status.HTTP_201_CREATED, response_model=Dict[str, Any])
def register_user(req: RegisterRequest):
    """
    Password Hashing Demonstration:
    Registers a new user by securely hashing their password with bcrypt (12 salt rounds).
    Plaintext passwords are never stored.
    """
    if req.email in demo_users_db:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"User with email '{req.email}' already exists."
        )

    # Secure bcrypt password hash
    hashed = get_password_hash(req.password)
    user_record = {
        "id": f"usr_{uuid.uuid4().hex[:8]}",
        "email": req.email,
        "full_name": req.full_name,
        "role": req.role,
        "password_hash": hashed,
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    demo_users_db[req.email] = user_record

    return {
        "message": "User registered successfully with bcrypt password hash",
        "user_id": user_record["id"],
        "email": user_record["email"],
        "algorithm": "bcrypt_12_rounds"
    }


@router.post("/login", status_code=status.HTTP_200_OK, response_model=TokenResponse)
def login_user(req: LoginRequest):
    """
    Password Verification & JWT Issuance:
    1. Compares supplied plaintext password against bcrypt hash using constant-time checkpw.
    2. Issues signed HS256 JWT access token with user role and subject claims upon success.
    """
    user = demo_users_db.get(req.email)
    if not user or not verify_password(req.password, user["password_hash"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
            headers={"WWW-Authenticate": "Bearer"}
        )

    token = create_access_token({
        "sub": user["email"],
        "user_id": user["id"],
        "role": user["role"]
    })

    return TokenResponse(
        access_token=token,
        expires_in_minutes=ACCESS_TOKEN_EXPIRE_MINUTES,
        user={
            "id": user["id"],
            "email": user["email"],
            "full_name": user["full_name"],
            "role": user["role"]
        }
    )


@router.get("/verify-token", status_code=status.HTTP_200_OK)
def verify_token_endpoint(claims: Dict[str, Any] = Depends(verify_jwt_authorization)):
    """
    JWT Verification Demonstration:
    Validates token signature and expiration, returning decoded token claims.
    """
    return {
        "status": "authenticated",
        "valid": True,
        "claims": claims,
        "user": claims
    }
