from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from typing import List, Dict, Any, Optional
from app.database.session import get_db
from app.database.repository import TelemetryRepository

router = APIRouter(prefix="/api", tags=["Alerts"])

@router.get("/alerts")
def get_alerts(
    limit: int = Query(100, ge=1, le=1000),
    service: Optional[str] = None,
    severity: Optional[str] = None,
    alert_type: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """Returns stored alerts from SQLite with filtering."""
    return TelemetryRepository.get_alerts(
        db=db,
        limit=limit,
        service=service,
        severity=severity,
        alert_type=alert_type
    )

@router.get("/alerts/joined", summary="Get alerts joined with service metadata via SQL JOIN")
def get_alerts_joined(
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db)
):
    """
    SQL JOINs demonstration:
    Executes an explicit SQL LEFT OUTER JOIN between alerts and services.
    """
    return TelemetryRepository.get_alerts_joined_with_services(db=db, limit=limit)

@router.get("/alerts/grouped", summary="Get aggregated alert counts using SQL GROUP BY and HAVING")
def get_alerts_grouped(db: Session = Depends(get_db)):
    """
    Filtering, Ordering, and Grouping demonstration:
    Executes SQL aggregation with GROUP BY service, severity, HAVING count > 0, ORDER BY count DESC.
    """
    return TelemetryRepository.get_alert_aggregations_grouped(db=db)
