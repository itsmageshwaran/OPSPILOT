import os
from typing import Optional, List
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field, field_validator

class Settings(BaseSettings):
    """
    OpsPilot Global Configuration & Environment Secrets Management.
    Enforces fail-fast secrets validation in production:
    - Insecure defaults prohibited
    - Minimum entropy for cryptographic tokens
    """
    app_name: str = "OpsPilot"
    environment: str = "development"
    port: int = 8080
    host: str = "0.0.0.0"

    # Comma-separated browser origins allowed to call the backend directly.
    cors_allowed_origins: str = Field(
        default="http://localhost:5173,http://127.0.0.1:5173",
        validation_alias="CORS_ALLOWED_ORIGINS",
    )

    @property
    def cors_origins(self) -> List[str]:
        return [origin.strip() for origin in self.cors_allowed_origins.split(",") if origin.strip()]
    
    # External ShopFlow Environment
    shopflow_base_url: str = Field(default="http://127.0.0.1:8000", validation_alias="SHOPFLOW_BASE_URL")
    shopflow_timeout_seconds: float = Field(default=5.0, validation_alias="SHOPFLOW_TIMEOUT_SECONDS")
    
    # SQLite / PostgreSQL Relational Database Configuration
    database_url: str = Field(default="sqlite:///./opspilot.db", validation_alias="DATABASE_URL")

    # MongoDB Knowledge Base Configuration (NoSQL)
    mongo_uri: str = Field(default="mongodb://localhost:27017", validation_alias="MONGO_URI")
    mongo_db_name: str = Field(default="opspilot_kb", validation_alias="MONGO_DB_NAME")

    # Redis Caching & Distributed Synchronization
    redis_host: str = Field(default="127.0.0.1", validation_alias="REDIS_HOST")
    redis_port: int = Field(default=6379, validation_alias="REDIS_PORT")
    redis_password: Optional[str] = Field(default=None, validation_alias="REDIS_PASSWORD")

    # Secrets Management: JWT & Cryptographic Tokens
    jwt_secret_key: str = Field(
        default="shopflow-secure-dev-jwt-secret-key-32bytes-entropy-minimum",
        validation_alias="JWT_SECRET_KEY"
    )
    jwt_algorithm: str = Field(default="HS256", validation_alias="JWT_ALGORITHM")
    jwt_expire_minutes: int = Field(default=1440, validation_alias="JWT_EXPIRE_MINUTES")

    # Secrets Management: Payment Gateway Webhook HMAC Secret
    payment_gateway_api_key: str = Field(
        default="sk_test_shopflow_mock_gateway_api_key_2026",
        validation_alias="PAYMENT_GATEWAY_API_KEY"
    )
    payment_webhook_secret: str = Field(
        default="whsec_test_mock_webhook_secret_shopflow_2026_strict",
        validation_alias="PAYMENT_WEBHOOK_SECRET"
    )

    # LLM Root-Cause Analysis Configuration (OpenAI-compatible)
    llm_api_key: Optional[str] = Field(default=None, validation_alias="LLM_API_KEY")
    llm_base_url: str = Field(default="https://api.openai.com/v1", validation_alias="LLM_BASE_URL")
    llm_model: str = Field(default="gpt-4o-mini", validation_alias="LLM_MODEL")
    llm_timeout_seconds: float = Field(default=15.0, validation_alias="LLM_TIMEOUT_SECONDS")
    llm_temperature: float = Field(default=0.1, validation_alias="LLM_TEMPERATURE")

    # Remediation Configuration
    remediation_allowlist_path: str = Field(default="config/remediation_allowlist.yaml", validation_alias="REMEDIATION_ALLOWLIST_PATH")
    remediation_enabled: bool = Field(default=True, validation_alias="REMEDIATION_ENABLED")
    remediation_simulation_mode: bool = Field(default=True, validation_alias="REMEDIATION_SIMULATION_MODE")

    # Grafana Observability Source (Optional / Read-Only Discovery)
    grafana_url: str = Field(default="http://127.0.0.1:3000", validation_alias="GRAFANA_URL")
    grafana_api_key: Optional[str] = Field(default=None, validation_alias="GRAFANA_API_KEY")
    grafana_timeout_seconds: float = Field(default=2.0, validation_alias="GRAFANA_TIMEOUT_SECONDS")
    grafana_enabled: bool = Field(default=True, validation_alias="GRAFANA_ENABLED")

    def validate_secrets(self) -> None:
        """
        Enforces strict secrets policy:
        In production, verifies that JWT secrets and payment webhook secrets
        are injected securely via environment and do not match placeholder values.
        """
        if self.environment.lower() in ("production", "prod"):
            if len(self.jwt_secret_key) < 32 or "dev-jwt" in self.jwt_secret_key:
                raise ValueError("FATAL: JWT_SECRET_KEY must be a cryptographically secure 32+ byte string in production.")
            if "mock" in self.payment_webhook_secret or len(self.payment_webhook_secret) < 16:
                raise ValueError("FATAL: PAYMENT_WEBHOOK_SECRET must be configured securely in production.")

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        populate_by_name=True,
        extra="ignore"
    )

settings = Settings()
settings.validate_secrets()
