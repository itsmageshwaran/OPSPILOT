import json
from fastapi import APIRouter, Depends, Query, HTTPException, Body
from sqlalchemy.orm import Session
from typing import List, Dict, Any, Optional

from app.database.session import get_db
from app.database.repository import TelemetryRepository
from app.cache import cache_manager
from app.root_cause import root_cause_service, RootCauseAnalysis, RootCauseRequest
from app.remediation import (
    remediation_service,
    RemediationRequest,
    RemediationResult,
    RecoveryEvidence
)

router = APIRouter(prefix="/api/incidents", tags=["Incidents"])

@router.get("", summary="List incidents (Cache-Aside with Redis)")
def list_incidents(
    status: Optional[str] = Query(None, description="Filter by status (OPEN, MITIGATED, RESOLVED)"),
    severity: Optional[str] = Query(None, description="Filter by severity (CRITICAL, WARNING)"),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db)
) -> List[Dict[str, Any]]:
    cache_key = f"incidents:list:{status}:{severity}:{limit}"
    cached = cache_manager.get(cache_key)
    if cached:
        try:
            return json.loads(cached)
        except Exception:
            pass

    incidents = TelemetryRepository.get_incidents(db, status=status, severity=severity, limit=limit)
    cache_manager.set(cache_key, json.dumps(incidents), ex=60)
    return incidents

@router.get("/{incident_id}", summary="Get incident details with correlation evidence (Cache-Aside with Redis)")
def get_incident(incident_id: str, db: Session = Depends(get_db)) -> Dict[str, Any]:
    cache_key = f"incidents:detail:{incident_id}"
    cached = cache_manager.get(cache_key)
    if cached:
        try:
            return json.loads(cached)
        except Exception:
            pass

    incident = TelemetryRepository.get_incident_by_id(db, incident_id=incident_id)
    if not incident:
        raise HTTPException(status_code=404, detail=f"Incident '{incident_id}' not found")

    # Fetch detailed alert objects for the alerts in this incident
    alert_ids = set(incident.get("alert_ids", []))
    all_alerts = TelemetryRepository.get_alerts(db, limit=1000)
    linked_alerts = [a for a in all_alerts if a["id"] in alert_ids]

    payload = {
        **incident,
        "alerts": linked_alerts
    }
    cache_manager.set(cache_key, json.dumps(payload), ex=60)
    return payload

@router.post("/{incident_id}/root-cause", summary="Diagnose incident root cause (AI or deterministic fallback)", response_model=RootCauseAnalysis)
def diagnose_root_cause(
    incident_id: str,
    request: Optional[RootCauseRequest] = Body(default_factory=RootCauseRequest),
    db: Session = Depends(get_db)
) -> RootCauseAnalysis:
    req = request or RootCauseRequest()
    try:
        return root_cause_service.diagnose_incident(
            db=db,
            incident_id=incident_id,
            force_refresh=req.force_refresh,
            force_fallback=req.force_fallback
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Root cause diagnosis failed: {str(e)}")

@router.get("/{incident_id}/root-cause", summary="Get cached root cause diagnosis or compute if missing", response_model=RootCauseAnalysis)
def get_root_cause(incident_id: str, db: Session = Depends(get_db)) -> RootCauseAnalysis:
    diagnosis = root_cause_service.get_diagnosis(db, incident_id=incident_id)
    if not diagnosis:
        try:
            return root_cause_service.diagnose_incident(db=db, incident_id=incident_id)
        except ValueError as e:
            raise HTTPException(status_code=404, detail=str(e))
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Root cause diagnosis failed: {str(e)}")
    return diagnosis

# ----------------- PHASE 5: REMEDIATION & AUDIT TRAIL -----------------

@router.post("/{incident_id}/remediate", summary="Execute safety-gated remediation (Simulation default)", response_model=RemediationResult)
def remediate_incident(
    incident_id: str,
    request: Optional[RemediationRequest] = Body(default_factory=RemediationRequest),
    db: Session = Depends(get_db)
) -> RemediationResult:
    req = request or RemediationRequest()
    try:
        result = remediation_service.remediate_incident(
            db=db,
            incident_id=incident_id,
            request=req
        )
        # Cache Invalidation: Purge cached incident queries upon state mutation
        cache_manager.delete(f"incidents:detail:{incident_id}")
        cache_manager.delete_pattern("incidents:list:*")
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Remediation processing failed: {str(e)}")

@router.get("/{incident_id}/remediation", summary="Get latest remediation decision and status")
def get_latest_remediation(incident_id: str, db: Session = Depends(get_db)) -> Optional[Dict[str, Any]]:
    latest = remediation_service.get_latest_remediation(db, incident_id=incident_id)
    return latest

@router.get("/{incident_id}/audit", summary="Get complete immutable audit trail for incident")
def get_incident_audit_trail(
    incident_id: str,
    db: Session = Depends(get_db)
) -> List[Dict[str, Any]]:
    return remediation_service.get_audits(db, incident_id=incident_id)

@router.post("/{incident_id}/remediate/verify", summary="Verify recovery status against ShopFlow telemetry", response_model=RecoveryEvidence)
def verify_recovery(incident_id: str, db: Session = Depends(get_db)) -> RecoveryEvidence:
    return remediation_service.verify_recovery(db, incident_id=incident_id)

@router.delete("", summary="Delete all incidents")
def delete_all_incidents(db: Session = Depends(get_db)) -> Dict[str, str]:
    TelemetryRepository.delete_incidents(db)
    return {"status": "success", "message": "All incidents deleted"}
