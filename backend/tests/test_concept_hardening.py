import os
import sys
import json
import time
import hmac
import hashlib
import uuid
import pytest
from datetime import timedelta
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROJECT_ROOT = os.path.dirname(BASE_DIR)
SHOPFLOW_DIR = os.path.join(PROJECT_ROOT, "shopflow-test")

if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)
if SHOPFLOW_DIR not in sys.path:
    sys.path.insert(0, SHOPFLOW_DIR)

from app.main import app, trigger_cron_sweep, get_cron_status
from app.auth import create_access_token, decode_token
from app.database.session import SessionLocal
from app.database.models import IncidentModel, with_transaction
from services.checkout_api.main import (
    app as checkout_app,
    PAYMENT_WEBHOOK_SECRET,
    create_payment_intent,
    PaymentIntentRequest,
)
from services.common.redis_client import redis_client

client = TestClient(app)
checkout_client = TestClient(checkout_app)


# ------------------------------------------------------------------------------
# 1. Authentication Failures & JWT Verification Tests
# ------------------------------------------------------------------------------
def test_auth_failure_missing_header():
    """Requesting protected endpoints without Authorization header returns 401."""
    res = client.get("/api/auth/verify-token")
    assert res.status_code == 401
    assert "Missing or malformed Authorization header" in res.json()["detail"]

def test_auth_failure_invalid_token():
    """Requesting protected endpoints with an invalid/forged JWT returns 401."""
    res = client.get(
        "/api/auth/verify-token",
        headers={"Authorization": "Bearer invalid.jwt.forged.signature"}
    )
    assert res.status_code == 401
    assert "Invalid, expired, or tampered JWT" in res.json()["detail"]

def test_auth_failure_expired_token():
    """Requesting protected endpoints with an expired JWT returns 401."""
    expired_token = create_access_token(
        data={"sub": "user@example.com", "role": "admin"},
        expires_delta=timedelta(seconds=-60)
    )
    res = client.get(
        "/api/auth/verify-token",
        headers={"Authorization": f"Bearer {expired_token}"}
    )
    assert res.status_code == 401
    assert "Invalid, expired, or tampered JWT" in res.json()["detail"]

def test_auth_success_valid_token():
    """Valid JWT returns 200 and authorized user payload."""
    valid_token = create_access_token(data={"sub": "admin@opspilot.dev", "role": "sre_admin"})
    res = client.get(
        "/api/auth/verify-token",
        headers={"Authorization": f"Bearer {valid_token}"}
    )
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "authenticated"
    assert data["user"]["sub"] == "admin@opspilot.dev"
    assert data["user"]["role"] == "sre_admin"


# ------------------------------------------------------------------------------
# 2. Input Validation & Sanitization Tests (HTTP 400 & HTTP 422)
# ------------------------------------------------------------------------------
def test_input_validation_disallowed_file_extension():
    """Uploading a disallowed executable extension returns 400 Bad Request."""
    res = client.post(
        "/api/telemetry/upload-bundle",
        files={"file": ("malicious_payload.exe", b"MZ\x90\x00\x03", "application/octet-stream")}
    )
    assert res.status_code == 400
    assert "Unsupported file extension" in res.json()["detail"]

def test_input_validation_empty_filename():
    """Uploading without a valid filename returns 400 Bad Request or 422 Unprocessable Content."""
    res = client.post(
        "/api/telemetry/upload-bundle",
        files={"file": ("", b"some log contents", "text/plain")}
    )
    assert res.status_code in (400, 422)

def test_input_validation_payment_intent_invalid_amount():
    """Creating payment intent with non-positive amount returns HTTP 422 Unprocessable Content."""
    res = checkout_client.post(
        "/checkout/payment-intent",
        json={
            "order_id": "ord_invalid_01",
            "amount": -50.0,
            "currency": "usd",
            "customer_email": "customer@example.com"
        }
    )
    assert res.status_code == 422

def test_input_validation_payment_intent_missing_fields():
    """Creating payment intent with missing required fields returns HTTP 422."""
    res = checkout_client.post(
        "/checkout/payment-intent",
        json={"currency": "usd"}
    )
    assert res.status_code == 422


# ------------------------------------------------------------------------------
# 3. Transaction Rollback & ACID Atomicity Test
# ------------------------------------------------------------------------------
def test_transaction_rollback_guarantee():
    """
    Verifies that when an exception is raised within with_transaction,
    the database rolls back and uncommitted records are completely discarded.
    """
    db = SessionLocal()
    test_id = f"inc_rollback_{uuid.uuid4().hex[:8]}"
    
    # 1. Attempt insert inside failing transaction block
    with pytest.raises(ZeroDivisionError):
        with with_transaction(db):
            db.add(IncidentModel(
                incident_id=test_id,
                title="Rollback Verification Incident",
                started_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                status="INVESTIGATING"
            ))
            _ = 1 / 0  # Trigger uncaught error inside transaction

    # 2. Assert record was NOT persisted to database
    retrieved = db.query(IncidentModel).filter(IncidentModel.incident_id == test_id).first()
    assert retrieved is None, "Transaction rollback failed: Uncommitted record persisted in DB!"
    db.close()


# ------------------------------------------------------------------------------
# 4. Redis Caching & Explicit Cache Invalidation Test
# ------------------------------------------------------------------------------
def test_redis_cache_invalidation_lifecycle():
    """
    Demonstrates Cache-Aside pattern and Cache Invalidation:
    1. Writes cart data via /cart
    2. Reads cart from cache via /cart/{session_id}
    3. Explicitly evicts cache key via DELETE /cart/{session_id}/cache
    4. Verifies cache key is deleted
    """
    session_id = f"sess_{uuid.uuid4().hex[:8]}"
    cart_items = [
        {"product_id": "prod_101", "product_title": "Mechanical Keyboard", "price": 89.99, "quantity": 1}
    ]

    # 1. Update cart -> populates cache
    update_res = checkout_client.post(
        "/cart",
        json={"session_id": session_id, "items": cart_items}
    )
    assert update_res.status_code == 200
    assert update_res.json()["cached"] is True

    # 2. Get cart -> served from cache
    get_res = checkout_client.get(f"/cart/{session_id}")
    assert get_res.status_code == 200
    assert get_res.json()["items"][0]["product_id"] == "prod_101"

    # 3. Invalidate cache key
    cache_key = f"cart_session:{session_id}"
    del_res = checkout_client.delete(f"/cart/{session_id}/cache")
    assert del_res.status_code == 200
    assert del_res.json()["invalidated"] is True

    # 4. Verify evicted from Redis
    assert redis_client.get(cache_key) is None


# ------------------------------------------------------------------------------
# 5. WebSocket Authorization & Rejection Test
# ------------------------------------------------------------------------------
def test_websocket_authorization_rejection():
    """WebSocket connection without valid JWT is rejected with code 1008 (Policy Violation)."""
    with pytest.raises(WebSocketDisconnect) as exc_info:
        with client.websocket_connect("/ws/telemetry") as ws:
            pass
    assert exc_info.value.code == 1008

def test_websocket_authorization_success():
    """WebSocket connection with valid JWT receives connection frame and responds to ping."""
    token = create_access_token({"sub": "admin@opspilot.dev", "role": "admin"})
    with client.websocket_connect(f"/ws/telemetry?token={token}") as ws:
        frame = ws.receive_json()
        assert frame["type"] == "CONNECTION_ESTABLISHED"
        assert frame["status"] == "authenticated"

        # Bidirectional ping-pong test
        ws.send_text("ping")
        pong = ws.receive_json()
        assert pong["type"] == "PONG"
        assert pong["message"] == "heartbeat acknowledged"


# ------------------------------------------------------------------------------
# 6. Scheduled Cron Jobs & Duplicate Execution Test
# ------------------------------------------------------------------------------
def test_scheduled_cron_job_metrics_and_duplicate_triggers():
    """
    Verifies that background scheduled sweeps can be triggered repeatedly
    without race conditions or metric state corruption.
    """
    initial_status = client.get("/api/cron/status").json()
    initial_runs = initial_status["statistics"]["runs_count"]

    # Trigger manual execution 1
    res1 = client.post("/api/cron/trigger-sweep")
    assert res1.status_code == 200
    assert res1.json()["cron_stats"]["runs_count"] == initial_runs + 1

    # Trigger manual execution 2
    res2 = client.post("/api/cron/trigger-sweep")
    assert res2.status_code == 200
    assert res2.json()["cron_stats"]["runs_count"] == initial_runs + 2


# ------------------------------------------------------------------------------
# 7. Payment Webhook Signatures, Tampering & Duplicate-Event Idempotency
# ------------------------------------------------------------------------------
def test_payment_webhook_tampered_signature_rejected():
    """Webhook with forged/tampered signature is rejected with HTTP 403 Forbidden."""
    payload = json.dumps({"type": "payment_intent.succeeded", "id": "evt_forged_01"}).encode("utf-8")
    forged_sig = "0" * 64

    res = checkout_client.post(
        "/checkout/webhook/payment",
        content=payload,
        headers={"X-Signature": forged_sig, "Content-Type": "application/json"}
    )
    assert res.status_code == 403
    assert "Cryptographic signature verification failed" in res.json()["detail"]

def test_payment_webhook_missing_signature_rejected():
    """Webhook with missing signature is rejected with HTTP 401 Unauthorized."""
    payload = json.dumps({"type": "payment_intent.succeeded", "id": "evt_nosig_01"}).encode("utf-8")
    res = checkout_client.post(
        "/checkout/webhook/payment",
        content=payload,
        headers={"Content-Type": "application/json"}
    )
    assert res.status_code == 401
    assert "Missing signature header" in res.json()["detail"]

def test_payment_webhook_duplicate_event_handling():
    """
    Replaying identical webhook deliveries:
    First delivery returns 200 with duplicate=False.
    Second delivery is recognized and ignored idempotently with duplicate=True.
    """
    event_id = f"evt_dup_{uuid.uuid4().hex[:10]}"
    payload = json.dumps({
        "id": event_id,
        "type": "payment_intent.succeeded",
        "data": {"object": {"id": "pi_test_dup", "order_id": "ord_1001"}}
    }).encode("utf-8")

    sig = hmac.new(PAYMENT_WEBHOOK_SECRET.encode("utf-8"), payload, hashlib.sha256).hexdigest()

    # First delivery
    r1 = checkout_client.post(
        "/checkout/webhook/payment",
        content=payload,
        headers={"X-Signature": sig, "Content-Type": "application/json"}
    )
    assert r1.status_code == 200
    assert r1.json()["received"] is True
    assert r1.json().get("duplicate") is not True

    # Second delivery (Duplicate Replay)
    r2 = checkout_client.post(
        "/checkout/webhook/payment",
        content=payload,
        headers={"X-Signature": sig, "Content-Type": "application/json"}
    )
    assert r2.status_code == 200
    assert r2.json()["received"] is True
    assert r2.json()["duplicate"] is True
    assert "Duplicate webhook event ignored idempotently" in r2.json()["message"]


# ------------------------------------------------------------------------------
# 8. Server-Side Rendering (SSR) HTML Generation Test
# ------------------------------------------------------------------------------
def test_ssr_html_report_rendering_and_headers():
    """
    Verifies actual Server-Side Rendering (SSR):
    Returns 200 OK, Content-Type: text/html; charset=utf-8,
    contains full responsive HTML5 structure and dynamic incident data.
    """
    incident_id = f"inc_ssr_{uuid.uuid4().hex[:6]}"
    res = client.get(f"/api/reports/{incident_id}/ssr-html")
    assert res.status_code == 200
    assert "text/html" in res.headers["content-type"]
    body = res.text
    assert "<!DOCTYPE html>" in body
    assert f"OpsPilot SSR Incident Report — {incident_id}" in body
    assert "Server-Rendered HTML" in body
    assert "Impacted Services Cascade" in body
    assert "Executive Summary &amp; Root Cause Analysis" in body or "Executive Summary & Root Cause Analysis" in body
