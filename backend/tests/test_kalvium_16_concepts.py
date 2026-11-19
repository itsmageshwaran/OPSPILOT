"""
Comprehensive Test Suite for the 16 Kalvium Concepts:
1. Mongo CRUD
2. Environment variables & secrets management
3. Correct HTTP status codes
4. Middleware
5. Mongo embedding vs referencing
6. Mongo aggregation pipelines
7. Mongo indexes
8. Password hashing
9. File upload handling
10. SQL transactions
11. JWT issuance & verification
12. Input sanitization & injection awareness
13. Redis caching
14. Scheduled jobs / cron
15. Server-side rendering
16. Payment gateway integration
"""

import os
import json
import time
import uuid
import hmac
import hashlib
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.config import Settings
from app.auth import get_password_hash, verify_password, create_access_token, decode_token
from app.models.mongo import (
    EmbeddedAlert,
    EmbeddedTimelineStep,
    PostMortemDocument,
    MongoIncidentKnowledgeBase,
)
from app.cache import cache_manager
from app.cron import trigger_manual_sweep, get_cron_status
from app.sanitizer import detect_sql_injection, sanitize_html, sanitize_input
from app.ssr import render_incident_html_report
from app.database.session import SessionLocal
from app.database.transactions import execute_atomic_financial_transfer, execute_atomic_incident_mitigation

client = TestClient(app)


# 1. MongoDB CRUD
def test_mongo_crud_primitives():
    kb = MongoIncidentKnowledgeBase()
    doc_id = f"test_crud_{uuid.uuid4().hex[:6]}"
    doc = {
        "incident_id": doc_id,
        "title": "CRUD Test Incident",
        "root_cause_service": "order-api",
        "status": "OPEN",
        "severity": "CRITICAL"
    }
    # Create (insert_one)
    inserted_id = kb.insert_one(doc)
    assert inserted_id == doc_id

    # Read (find_one)
    retrieved = kb.find_one({"incident_id": doc_id})
    assert retrieved is not None
    assert retrieved["title"] == "CRUD Test Incident"

    # Update (update_one)
    updated = kb.update_one({"incident_id": doc_id}, {"$set": {"status": "RESOLVED"}})
    assert updated is True
    assert kb.find_one({"incident_id": doc_id})["status"] == "RESOLVED"

    # Delete (delete_one)
    deleted = kb.delete_one({"incident_id": doc_id})
    assert deleted is True
    assert kb.find_one({"incident_id": doc_id}) is None


# 2. Environment Variables & Secrets Management
def test_secrets_management_validation():
    # Development allows default fallback
    dev_settings = Settings(environment="development")
    dev_settings.validate_secrets()
    assert dev_settings.jwt_secret_key is not None

    # Production strictly rejects insecure placeholder secrets
    with pytest.raises(ValueError, match="FATAL"):
        prod_settings = Settings(
            environment="production",
            jwt_secret_key="dev-jwt-placeholder-insecure",
            payment_webhook_secret="mock-secret"
        )
        prod_settings.validate_secrets()


# 3. Correct HTTP Status Codes
def test_correct_http_status_codes():
    assert client.get("/api/status-codes/ok").status_code == 200
    assert client.post("/api/status-codes/created", json={"name": "test", "value": 10}).status_code == 201
    assert client.delete("/api/status-codes/no-content/123").status_code == 204
    assert client.get("/api/status-codes/bad-request").status_code == 400
    assert client.get("/api/status-codes/unauthorized").status_code == 401
    assert client.get("/api/status-codes/forbidden").status_code == 403
    assert client.get("/api/status-codes/not-found/xyz").status_code == 404


# 4. Middleware
def test_middleware_headers_applied():
    res = client.get("/health")
    assert res.status_code == 200
    # Request timing middleware
    assert "X-Response-Time-Ms" in res.headers
    # Distributed correlation tracing middleware
    assert "X-Correlation-ID" in res.headers
    # Security headers middleware
    assert res.headers.get("X-Content-Type-Options") == "nosniff"
    assert res.headers.get("X-Frame-Options") == "DENY"


# 5. MongoDB Embedding vs Referencing
def test_mongo_embedding_vs_referencing_structure():
    doc = PostMortemDocument(
        incident_id="inc_rel_test",
        title="Relationship Test",
        summary="Testing embedded vs referenced patterns",
        root_cause_service="postgresql",
        referenced_service_ids=["postgresql", "order-api"],
        referenced_audit_ids=["audit_1001", "audit_1002"],
        embedded_alerts=[
            EmbeddedAlert(
                alert_id="alt_1",
                service="postgresql",
                severity="CRITICAL",
                metric="connections",
                metric_value=99.0,
                threshold=80.0,
                message="Connection exhaustion"
            )
        ],
        embedded_timeline=[
            EmbeddedTimelineStep(
                stage=1,
                event_type="CASCADE_DETECTED",
                service="postgresql",
                description="Database pool starved"
            )
        ]
    )
    dumped = doc.model_dump()
    # Embedded documents reside directly inside parent document array
    assert len(dumped["embedded_alerts"]) == 1
    assert dumped["embedded_alerts"][0]["alert_id"] == "alt_1"
    # Referenced entities are stored as external ID foreign references
    assert "postgresql" in dumped["referenced_service_ids"]
    assert "audit_1001" in dumped["referenced_audit_ids"]


# 6. MongoDB Aggregation Pipelines
def test_mongo_aggregation_pipeline_route():
    res = client.get("/api/knowledge-base/analytics/mttr-aggregation")
    assert res.status_code == 200
    data = res.json()
    assert "$match (status=RESOLVED)" in data["pipeline_stages"][0]
    assert "$group" in data["pipeline_stages"][1]
    assert isinstance(data["results"], list)


# 7. MongoDB Indexes
def test_mongo_indexes_catalog():
    res = client.get("/api/knowledge-base/indexes")
    assert res.status_code == 200
    indexes = res.json()["indexes"]
    names = [idx.get("name") for idx in indexes]
    assert "idx_incident_id_unique" in names
    assert "idx_service_status_time" in names


# 8. Password Hashing (Bcrypt 12 Salt Rounds)
def test_password_hashing_and_auth_service():
    password = "CorrectHorseBatteryStaple2026!"
    hashed = get_password_hash(password)
    assert hashed.startswith("$2b$12$")
    assert verify_password(password, hashed) is True
    assert verify_password("WrongPassword!", hashed) is False

    # Auth router register endpoint
    reg_email = f"user_{uuid.uuid4().hex[:6]}@opspilot.dev"
    res = client.post(
        "/api/auth/register",
        json={"email": reg_email, "password": "SecretPassword123!", "full_name": "Test User"}
    )
    assert res.status_code == 201
    assert res.json()["algorithm"] == "bcrypt_12_rounds"


# 9. File Upload Handling
def test_secure_file_upload_handling():
    # Disallowed extension (.exe) rejected
    bad_res = client.post(
        "/api/upload/telemetry-bundle",
        files={"file": ("exploit.exe", b"MZ\x00\x00", "application/octet-stream")}
    )
    assert bad_res.status_code == 400

    # Allowed extension (.json) accepted
    good_res = client.post(
        "/api/upload/telemetry-bundle",
        files={"file": ("valid_logs.json", b'{"log": "sample"}', "application/json")}
    )
    assert good_res.status_code == 201
    assert good_res.json()["status"] == "UPLOAD_SUCCESS"


# 10. SQL Transactions
def test_sql_acid_transactions():
    db = SessionLocal()
    try:
        # Atomic commit
        res = execute_atomic_financial_transfer(
            db=db,
            sender_user_id="usr_alice",
            receiver_user_id="usr_bob",
            amount=25.0,
            simulate_fault=False
        )
        assert res["status"] == "COMMITTED"

        # Atomic rollback on fault
        with pytest.raises(RuntimeError, match="ACID Transaction Failure"):
            execute_atomic_financial_transfer(
                db=db,
                sender_user_id="usr_alice",
                receiver_user_id="usr_bob",
                amount=25.0,
                simulate_fault=True
            )

        # Domain model atomic transaction
        mitigation_res = execute_atomic_incident_mitigation(
            db=db,
            incident_id="inc_tx_test_01",
            simulate_fault=False
        )
        assert mitigation_res["status"] == "COMMITTED"
        assert mitigation_res["final_incident_status"] == "MITIGATED"

        with pytest.raises(RuntimeError, match="ACID Transaction Failure"):
            execute_atomic_incident_mitigation(
                db=db,
                incident_id="inc_tx_test_fail",
                simulate_fault=True
            )
    finally:
        db.close()


# 11. JWT Issuance & Verification
def test_jwt_issuance_and_verification_flow():
    token = create_access_token({"sub": "sre@opspilot.dev", "role": "admin"})
    assert isinstance(token, str)

    # Decode token
    claims = decode_token(token)
    assert claims is not None
    assert claims["sub"] == "sre@opspilot.dev"
    assert claims["role"] == "admin"

    # API route verification
    res = client.get(
        "/api/auth/verify-token",
        headers={"Authorization": f"Bearer {token}"}
    )
    assert res.status_code == 200
    assert res.json()["valid"] is True


# 12. Input Sanitization & Injection Defense
def test_input_sanitization_and_sql_injection():
    # SQL injection detection
    bad_sql = "SELECT * FROM users WHERE id = 1 UNION SELECT password_hash, email FROM admin_users --"
    is_inj, reason = detect_sql_injection(bad_sql)
    assert is_inj is True
    assert "UNION" in reason

    # Safe SQL query
    safe_sql = "SELECT alert_id, service, metric FROM alerts WHERE service = 'postgresql' LIMIT 10"
    is_inj_safe, _ = detect_sql_injection(safe_sql)
    assert is_inj_safe is False

    # HTML entity escaping
    xss_payload = "<script>alert('xss')</script>"
    escaped = sanitize_html(xss_payload)
    assert "&lt;script&gt;" in escaped
    assert "<script>" not in escaped


# 13. Redis Caching
def test_redis_caching_layer():
    cache_key = f"key_{uuid.uuid4().hex[:6]}"
    cache_manager.set(cache_key, "cached_telemetry_payload", ex=10)
    assert cache_manager.get(cache_key) == "cached_telemetry_payload"

    # Invalidation
    cache_manager.delete(cache_key)
    assert cache_manager.get(cache_key) is None

    # Distributed locking
    lock_key = f"lock_{uuid.uuid4().hex[:6]}"
    assert cache_manager.acquire_lock(lock_key, ttl=5) is True
    assert cache_manager.acquire_lock(lock_key, ttl=5) is False
    cache_manager.release_lock(lock_key)


# 14. Scheduled Jobs / Cron
def test_scheduled_jobs_cron():
    sweep_result = trigger_manual_sweep()
    assert sweep_result["status"] == "success"
    assert sweep_result["cron_stats"]["runs_count"] > 0

    status = get_cron_status()
    assert status["is_active"] is True
    assert status["job_name"] == "scheduled_telemetry_sweep"


# 15. Server-Side Rendering (SSR)
def test_server_side_rendering_executive_report():
    res = client.get("/reports/incidents/inc_executive_01/executive")
    assert res.status_code == 200
    assert "text/html" in res.headers["content-type"]
    assert "<!DOCTYPE html>" in res.text
    assert "OpsPilot SSR Incident Report — inc_executive_01" in res.text
    assert "Server-Rendered HTML" in res.text


# 16. Payment Gateway Integration
def test_payment_gateway_integration():
    # Intent creation
    res = client.post(
        "/checkout/payment-intent",
        json={
            "order_id": "ord_pay_001",
            "amount": 99.50,
            "currency": "usd",
            "customer_email": "buyer@shopflow.dev"
        }
    )
    assert res.status_code == 201
    intent = res.json()
    assert intent["id"].startswith("pi_test_")
    assert intent["status"] == "requires_payment_method"

    # Stripe signature webhook verification
    payload = json.dumps({
        "id": f"evt_{uuid.uuid4().hex[:8]}",
        "type": "payment_intent.succeeded",
        "data": {"object": {"id": intent["id"]}}
    }).encode("utf-8")

    now_t = str(int(time.time()))
    signed_payload = f"{now_t}.".encode("utf-8") + payload
    v1_sig = hmac.new(b"whsec_test_mock_webhook_secret_shopflow_2026_strict", signed_payload, hashlib.sha256).hexdigest()
    stripe_sig = f"t={now_t},v1={v1_sig}"

    wh_res = client.post(
        "/checkout/webhook/payment",
        content=payload,
        headers={"Stripe-Signature": stripe_sig, "Content-Type": "application/json"}
    )
    assert wh_res.status_code == 200
    assert wh_res.json()["status"] == "processed"
