from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from datetime import datetime, timezone
from app.database.session import get_db
from app.ingestion.adapter import shopflow_adapter
from app.config import settings

router = APIRouter(tags=["Health"])

@router.get("/health")
def health_check():
    """
    Returns OpsPilot's own system health independently of ShopFlow's status.
    Exposes ShopFlow connectivity status separately.
    """
    shopflow_connected = shopflow_adapter.check_connectivity()
    
    return {
        "status": "healthy",
        "service": "opspilot-backend",
        "version": "1.0.0",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "shopflow": "connected" if shopflow_connected else "disconnected",
        "shopflow_target_url": settings.shopflow_base_url
    }

@router.post("/api/reset")
def reset_opspilot_database(db: Session = Depends(get_db)):
    """
    Resets the OpsPilot database to a clean slate (clears alerts, incidents, audits).
    """
    from app.database.repository import TelemetryRepository
    TelemetryRepository.clear_all(db)
    shopflow_reset = shopflow_adapter.reset_chaos()
    return {
        "status": "success",
        "message": "OpsPilot database reset to clean state",
        "shopflow_reset": "success" if shopflow_reset else "unavailable",
    }


@router.get("/api/config/secrets-health", summary="Environment Variables & Secrets Management Health")
def secrets_health_check():
    """
    Environment Variables & Secrets Management Demonstration:
    Validates that required cryptographic secrets and connection URIs are loaded
    from the environment and comply with entropy policies, without leaking secrets.
    """
    settings.validate_secrets()
    return {
        "status": "VALIDATED",
        "environment": settings.environment,
        "secrets_management": {
            "jwt_secret_configured": bool(settings.jwt_secret_key),
            "jwt_secret_length_bytes": len(settings.jwt_secret_key),
            "payment_webhook_secret_configured": bool(settings.payment_webhook_secret),
            "mongo_uri_configured": bool(settings.mongo_uri),
            "redis_host_configured": bool(settings.redis_host),
            "hardcoded_fallbacks_prohibited": True,
        }
    }

