import time
import uuid
import re
import bcrypt
from fastapi import FastAPI, HTTPException, Depends, Header, status
from pydantic import BaseModel, Field, field_validator
from typing import Optional, Dict, Any, List

from services.common.db import db
from services.common.security import verify_password, get_password_hash, create_access_token, decode_token
from telemetry.logger import get_logger
from chaos.engine import chaos_engine

logger = get_logger("auth-service")

app = FastAPI(
    title="ShopFlow Auth Service",
    version="1.0.0",
    description="Authentication and Identity microservice featuring bcrypt password hashing, JWT claims, and strict request body validation."
)

EMAIL_REGEX = r"^[\w\.\+\-]+@[a-zA-Z0-9\-]+\.[a-zA-Z0-9\-\.]+$"

# ------------------------------------------------------------------------------
# Request Body Validation Models
# ------------------------------------------------------------------------------
class RegisterRequest(BaseModel):
    """
    Request body validation: Enforces valid email syntax, minimum password entropy,
    and non-empty user metadata.
    """
    email: str = Field(..., description="User's primary email address")
    password: str = Field(..., min_length=6, max_length=72, description="Plaintext password (6-72 chars)")
    full_name: str = Field(..., min_length=2, max_length=128, description="User full display name")
    role: Optional[str] = Field("customer", description="Role: customer or admin")

    @field_validator("email")
    @classmethod
    def validate_email_format(cls, v: str) -> str:
        clean = v.strip().lower()
        if not re.match(EMAIL_REGEX, clean):
            raise ValueError(f"Invalid email format: '{v}'")
        return clean

class LoginRequest(BaseModel):
    """
    Request body validation for authentication.
    """
    email: str = Field(..., description="Account email")
    password: str = Field(..., min_length=1, max_length=72, description="Account password")

    @field_validator("email")
    @classmethod
    def validate_email(cls, v: str) -> str:
        return v.strip().lower()

class UserResponse(BaseModel):
    id: str
    email: str
    full_name: str
    role: str

class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserResponse

@app.get("/health", status_code=status.HTTP_200_OK)
def health():
    return {"status": "healthy", "service": "auth-service", "dependencies": {"postgresql": "healthy"}}

@app.get("/auth/users", response_model=List[UserResponse], status_code=status.HTTP_200_OK)
def get_demo_users():
    return [
        UserResponse(
            id=u["id"],
            email=u["email"],
            full_name=u["full_name"],
            role=u["role"]
        )
        for u in db.users.values()
    ]

@app.post("/auth/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def register(request: RegisterRequest):
    """
    Demonstrates Password Hashing with bcrypt:
    Salted 12-round bcrypt hash computed before persistence in database.
    """
    start = time.time()
    existing = db.get_user_by_email(request.email)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"User with email '{request.email}' already exists."
        )

    # Password hashing using bcrypt with 12 salt rounds
    plain_bytes = request.password.encode("utf-8")[:72]
    salt = bcrypt.gensalt(rounds=12)
    hashed_pwd = bcrypt.hashpw(plain_bytes, salt).decode("utf-8")

    new_user = {
        "id": f"usr_{uuid.uuid4().hex[:8]}",
        "email": request.email,
        "password_hash": hashed_pwd,
        "full_name": request.full_name,
        "role": request.role or "customer"
    }

    db.users[new_user["id"]] = new_user
    latency = (time.time() - start) * 1000
    logger.info("AUTH_REGISTER_SUCCESS", f"Registered new user {request.email}", latency_ms=latency, status_code=201)

    return UserResponse(
        id=new_user["id"],
        email=new_user["email"],
        full_name=new_user["full_name"],
        role=new_user["role"]
    )

@app.post("/auth/login", response_model=LoginResponse, status_code=status.HTTP_200_OK)
def login(request: LoginRequest):
    """
    Demonstrates Password Hashing verification and JWT Issuance.
    """
    start = time.time()
    logger.info("AUTH_LOGIN_ATTEMPT", f"Login attempt for user: {request.email}", metadata={"email": request.email})
    
    user = db.get_user_by_email(request.email)
    if not user or not verify_password(request.password, user["password_hash"]):
        latency = (time.time() - start) * 1000
        logger.warn("AUTH_FAILED", f"Invalid credentials for {request.email}", latency_ms=latency, status_code=401)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
            headers={"WWW-Authenticate": "Bearer"}
        )

    # JWT Issuance with claims
    token = create_access_token(data={"sub": user["email"], "user_id": user["id"], "role": user["role"]})
    latency = (time.time() - start) * 1000
    logger.info("AUTH_SUCCESS", f"User {request.email} authenticated successfully", latency_ms=latency, status_code=200)

    return LoginResponse(
        access_token=token,
        token_type="bearer",
        user=UserResponse(
            id=user["id"],
            email=user["email"],
            full_name=user["full_name"],
            role=user["role"]
        )
    )

@app.get("/auth/verify", response_model=UserResponse, status_code=status.HTTP_200_OK)
def verify_token(authorization: Optional[str] = Header(None)):
    """
    Demonstrates JWT Verification:
    Extracts Bearer token, validates cryptographic signature and expiry claims.
    """
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid authorization token",
            headers={"WWW-Authenticate": "Bearer"}
        )
    
    token = authorization.split(" ")[1]
    payload = decode_token(token)
    if not payload or "sub" not in payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token expired or invalid signature",
            headers={"WWW-Authenticate": "Bearer"}
        )
    
    user = db.get_user_by_email(payload["sub"])
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    return UserResponse(
        id=user["id"],
        email=user["email"],
        full_name=user["full_name"],
        role=user["role"]
    )

