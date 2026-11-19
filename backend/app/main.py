import asyncio
import hashlib
import json
import logging
import os
import sys
import time
import uuid
from contextlib import asynccontextmanager
from typing import Optional, Dict, Any

from fastapi import (
    FastAPI,
    Request,
    Response,
    HTTPException,
    status,
    Depends,
    WebSocket,
    WebSocketDisconnect,
    Query,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from sqlalchemy.orm import Session

from app.config import settings
from app.auth import router as auth_router, decode_token, verify_jwt_authorization
from app.database.session import init_db, get_db
from app.database.repository import TelemetryRepository
from app.database.transactions import execute_atomic_financial_transfer
from app.middleware import (
    RequestTimingAndCorrelationMiddleware,
    SecurityHeadersMiddleware,
    AuditLoggingMiddleware,
)
from app.cache import cache_manager as redis_client
from app.cron import scheduled_telemetry_sweep, trigger_manual_sweep, get_cron_status as cron_get_status, cron_stats
from app.ssr import render_incident_html_report
from app.sanitizer import detect_sql_injection, sanitize_html, sanitize_input

from app.api.routes import (
    health_router,
    services_router,
    topology_router,
    alerts_router,
    metrics_router,
    logs_router,
    events_router,
    sync_router,
    correlation_router,
    incidents_router,
    knowledge_base_router,
    ai_agent_router,
    checkout_router,
)
from app.api.routes.upload import router as upload_router
from app.api.status_codes import router as status_codes_router
from app.chatops.nlq import router as chatops_router

logging.basicConfig(
    level=logging.INFO,
    format='{"timestamp": "%(asctime)s", "logger": "%(name)s", "level": "%(levelname)s", "message": "%(message)s"}'
)
logger = logging.getLogger("opspilot.main")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: initialize database tables
    logger.info("Initializing OpsPilot SQLite database...")
    init_db()
    try:
        import yaml
        from app.topology.discovery import topology_discovery_engine
        possible_paths = [
            os.path.join(os.getcwd(), "config", "topology.yaml"),
            os.path.join(os.getcwd(), "..", "shopflow-test", "config", "topology.yaml"),
            os.path.join(os.getcwd(), "shopflow-test", "config", "topology.yaml"),
        ]
        for p in possible_paths:
            if os.path.exists(p):
                with open(p, "r", encoding="utf-8") as f:
                    topo = yaml.safe_load(f)
                    topology_discovery_engine.register_fallback_topology(topo.get("nodes", []), topo.get("edges", []))
                    logger.info(f"Loaded fallback topology baseline from {p}")
                break
    except Exception as e:
        logger.debug(f"Notice during startup topology load: {e}")

    # Launch scheduled background cron job
    cron_task = asyncio.create_task(scheduled_telemetry_sweep(interval_seconds=60))
    logger.info("OpsPilot backend service ready and background scheduled cron task started.")
    
    yield

    # Shutdown
    cron_task.cancel()
    try:
        await cron_task
    except asyncio.CancelledError:
        pass
    logger.info("OpsPilot backend service shutting down.")


app = FastAPI(
    title="OpsPilot — Autonomous AIOps Platform",
    version="1.0.0",
    description="Intelligent dependency-aware incident correlation, root-cause diagnosis, and automated remediation platform.",
    lifespan=lifespan
)

# ------------------------------------------------------------------------------
# Custom Middlewares (Request Timing, Security Headers, Audit Logging)
# ------------------------------------------------------------------------------
app.add_middleware(RequestTimingAndCorrelationMiddleware)
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(AuditLoggingMiddleware)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register Routers
app.include_router(health_router)
app.include_router(services_router)
app.include_router(topology_router)
app.include_router(alerts_router)
app.include_router(metrics_router)
app.include_router(logs_router)
app.include_router(events_router)
app.include_router(sync_router)
app.include_router(correlation_router)
app.include_router(incidents_router)
app.include_router(knowledge_base_router)
app.include_router(chatops_router)
app.include_router(ai_agent_router)
app.include_router(checkout_router)
app.include_router(auth_router)
app.include_router(upload_router)
app.include_router(status_codes_router)


# ------------------------------------------------------------------------------
# Redis Caching Tier Endpoints
# ------------------------------------------------------------------------------
@app.get("/api/cache/stats", tags=["Redis Caching"])
def get_cache_stats():
    """Returns real-time caching layer diagnostics and connected status."""
    return redis_client.get_stats()


@app.post("/api/cache/invalidate", tags=["Redis Caching"])
def invalidate_cache_key(key: str = Query(..., description="Cache key to purge")):
    """Active cache invalidation upon telemetry data mutation."""
    success = redis_client.delete(key)
    return {"key": key, "invalidated": success, "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}


# ------------------------------------------------------------------------------
# SQL ACID Transactions: Atomic Financial Transfer & Rollback Endpoint
# ------------------------------------------------------------------------------
@app.post("/api/financial/transfer", tags=["SQL Transactions"])
def financial_transfer_transaction(
    sender: str = Query("usr_sender_01"),
    receiver: str = Query("usr_receiver_02"),
    amount: float = Query(50.0),
    simulate_fault: bool = Query(False),
    db: Session = Depends(get_db)
):
    """
    Executes a relational database ACID transaction.
    Demonstrates commit on success and automatic rollback when simulate_fault is True.
    """
    try:
        result = execute_atomic_financial_transfer(
            db=db,
            sender_user_id=sender,
            receiver_user_id=receiver,
            amount=amount,
            simulate_fault=simulate_fault
        )
        return {"status": "SUCCESS", "transaction": result}
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Transaction rolled back: {str(e)}"
        )


# ------------------------------------------------------------------------------
# Input Sanitization & Injection Defense Endpoint
# ------------------------------------------------------------------------------
@app.post("/api/security/sanitize", tags=["Security & Sanitization"])
def sanitize_security_input(payload: Dict[str, Any]):
    """
    Demonstrates Input Sanitization and SQL/XSS Injection Awareness:
    - Scans query strings for destructive SQL injection vectors.
    - Encodes raw strings to HTML entities preventing Cross-Site Scripting (XSS).
    """
    query = payload.get("query", "")
    comment = payload.get("comment", "")

    is_injection, reason = detect_sql_injection(query)
    sanitized_comment = sanitize_html(comment)

    return {
        "sql_injection_detected": is_injection,
        "analysis": reason,
        "sanitized_comment": sanitized_comment,
        "status": "BLOCKED" if is_injection else "SAFE"
    }


# ------------------------------------------------------------------------------
# Server-Side Rendering (SSR) Incident Executive Summary Report
# ------------------------------------------------------------------------------
@app.get(
    "/api/reports/{incident_id}/ssr-html",
    response_class=HTMLResponse,
    status_code=status.HTTP_200_OK,
    summary="Server-Side Rendered (SSR) HTML Incident Executive Report",
    tags=["Reports & SSR"]
)
@app.get(
    "/reports/incidents/{incident_id}/executive",
    response_class=HTMLResponse,
    status_code=status.HTTP_200_OK,
    include_in_schema=False
)
def get_incident_ssr_report(incident_id: str, db: Session = Depends(get_db)):
    """
    Demonstrates Server-Side Rendering (SSR):
    Renders a complete, standalone, responsive HTML5 document directly on the server
    without requiring client-side JavaScript execution or SPA hydration.
    """
    incident = TelemetryRepository.get_incident_by_id(db, incident_id=incident_id)
    if not incident:
        # Fallback to simulated incident data if database doesn't have it yet
        incident = {
            "incident_id": incident_id,
            "title": f"Degradation Incident {incident_id}",
            "severity": "CRITICAL",
            "status": "OPEN",
            "started_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "alert_count": 3,
            "affected_services": ["postgresql", "order-api", "checkout-api"],
            "correlation_score": 0.94,
            "root_cause_service": "postgresql",
            "summary": "Connection pool exhaustion propagated downstream latency to order-api and checkout-api."
        }

    html_content = render_incident_html_report(incident)
    return HTMLResponse(content=html_content, status_code=status.HTTP_200_OK)


# ------------------------------------------------------------------------------
# Scheduled Job / Cron Manual Trigger & Status Endpoints
# ------------------------------------------------------------------------------
@app.post(
    "/api/cron/trigger-sweep",
    status_code=status.HTTP_200_OK,
    summary="Trigger immediate execution of background scheduled telemetry sweep",
    tags=["Scheduled Jobs"]
)
async def trigger_cron_sweep():
    """Manually fires the background cron job and returns execution statistics."""
    return trigger_manual_sweep()


@app.get(
    "/api/cron/status",
    status_code=status.HTTP_200_OK,
    summary="Get status and metrics for background scheduled jobs",
    tags=["Scheduled Jobs"]
)
def get_cron_status():
    """Returns runtime execution statistics for scheduled cron jobs."""
    return cron_get_status()


# ------------------------------------------------------------------------------
# WebSocket Real-Time Telemetry Stream with Authorization & Subscriptions
# ------------------------------------------------------------------------------
@app.websocket("/ws/telemetry")
async def websocket_telemetry_stream(
    websocket: WebSocket,
    token: Optional[str] = Query(None)
):
    """
    WebSocket Real-Time Communication with Mandatory JWT Authorization & Channel Subscriptions:
    - Rejects unauthorized clients with WebSocket close code 1008 (Policy Violation).
    - Authenticated clients receive live telemetry stream frames and bidirectional messaging.
    - Authorizes channel subscriptions based on user role claims (e.g. admin_audit_stream requires admin role).
    """
    claims = decode_token(token) if token else None
    if not claims:
        await websocket.close(
            code=status.WS_1008_POLICY_VIOLATION,
            reason="Unauthorized: Valid JWT required"
        )
        return

    await websocket.accept()
    user_role = claims.get("role", "customer")
    user_email = claims.get("sub", "authenticated_user")
    logger.info(f"WebSocket telemetry stream established for '{user_email}' (role: {user_role})")

    subscribed_channels = {"cluster_health"}
    try:
        await websocket.send_json({
            "type": "CONNECTION_ESTABLISHED",
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "status": "authenticated",
            "user": user_email,
            "role": user_role,
            "cluster_state": "OPTIMAL",
            "active_subscriptions": list(subscribed_channels)
        })
        while True:
            raw_msg = await websocket.receive_text()
            msg_str = raw_msg.strip()
            if msg_str.lower() == "ping":
                await websocket.send_json({
                    "type": "PONG",
                    "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                    "message": "heartbeat acknowledged"
                })
                continue

            try:
                msg_json = json.loads(msg_str)
                action = msg_json.get("action")
                if action == "subscribe":
                    channel = msg_json.get("channel", "cluster_health")
                    privileged_channels = {"admin_audit_stream", "remediation_control", "security_logs"}
                    if channel in privileged_channels and user_role not in ("admin", "sre_admin"):
                        await websocket.send_json({
                            "type": "SUBSCRIPTION_DENIED",
                            "channel": channel,
                            "reason": f"Role '{user_role}' is not authorized to subscribe to privileged channel '{channel}'",
                            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
                        })
                    else:
                        subscribed_channels.add(channel)
                        await websocket.send_json({
                            "type": "SUBSCRIPTION_CONFIRMED",
                            "channel": channel,
                            "active_subscriptions": sorted(list(subscribed_channels)),
                            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
                        })
                elif action == "unsubscribe":
                    channel = msg_json.get("channel")
                    if channel in subscribed_channels:
                        subscribed_channels.remove(channel)
                    await websocket.send_json({
                        "type": "UNSUBSCRIBE_CONFIRMED",
                        "channel": channel,
                        "active_subscriptions": sorted(list(subscribed_channels)),
                        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
                    })
                else:
                    await websocket.send_json({
                        "type": "TELEMETRY_ACK",
                        "received_action": action,
                        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
                    })
            except json.JSONDecodeError:
                await websocket.send_json({
                    "type": "TELEMETRY_ACK",
                    "received_payload": msg_str[:100],
                    "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
                })
    except (WebSocketDisconnect, asyncio.CancelledError):
        logger.info(f"WebSocket telemetry stream disconnected for '{user_email}'")
    except Exception as e:
        logger.warning(f"WebSocket telemetry error for '{user_email}': {e}")


@app.get("/", status_code=status.HTTP_200_OK)
def root():
    return {
        "app": "OpsPilot",
        "version": "1.0.0",
        "status": "operational",
        "docs_url": "/docs",
        "health_url": "/health",
        "ssr_report_example": "/api/reports/inc_sample/ssr-html",
        "file_upload_url": "/api/telemetry/upload-bundle"
    }
