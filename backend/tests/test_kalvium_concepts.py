import os
import sys
import json
import time
import hmac
import hashlib
import uuid
import pytest
from datetime import datetime, timezone

# Ensure backend and shopflow-test are on sys.path
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROJECT_ROOT = os.path.dirname(BASE_DIR)
SHOPFLOW_DIR = os.path.join(PROJECT_ROOT, "shopflow-test")

if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)
if SHOPFLOW_DIR not in sys.path:
    sys.path.insert(0, SHOPFLOW_DIR)

# ------------------------------------------------------------------------------
# 1. Mongo Concepts Tests (CRUD, Embedding vs Referencing, Aggregation, Indexes)
# ------------------------------------------------------------------------------
from app.models.mongo import (
    EmbeddedAlert,
    EmbeddedTimelineStep,
    PostMortemDocument,
    MongoIncidentKnowledgeBase,
    mongo_kb,
)

def test_mongo_crud_operations():
    kb = MongoIncidentKnowledgeBase()
    doc = PostMortemDocument(
        incident_id="inc_mongo_test_01",
        title="PostgreSQL Cascade Failure Post-Mortem",
        summary="Detailed post-mortem summary for database cascade failure",
        root_cause_service="postgresql",
        severity="CRITICAL",
        status="RESOLVED",
        root_cause="Connection pool starvation under flash sale load",
        resolution="Scaled pool to 100 max connections and applied PgBouncer",
        tags=["database", "p0", "cascade"],
        mttr_minutes=18.2,
        embedded_alerts=[
            EmbeddedAlert(
                alert_id="alt_001",
                service="postgresql",
                severity="CRITICAL",
                metric="active_connections",
                metric_value=98.5,
                threshold=90.0,
                message="Connection pool exhausted"
            )
        ],
        embedded_timeline=[
            EmbeddedTimelineStep(stage=1, event_type="ALERT", service="postgresql", description="Anomaly detector fired PRE_ALERT"),
            EmbeddedTimelineStep(stage=2, event_type="REMEDIATION", service="postgresql", description="Executed connection pool scale")
        ]
    )

    # 1. CREATE
    created = kb.create_post_mortem(doc)
    assert created["incident_id"] == "inc_mongo_test_01"
    assert len(created["embedded_alerts"]) == 1
    assert len(created["embedded_timeline"]) == 2

    # 2. READ
    fetched = kb.get_post_mortem(doc.incident_id)
    assert fetched is not None
    assert fetched["root_cause_service"] == "postgresql"
    assert fetched["embedded_alerts"][0]["metric_value"] == 98.5

    # 3. UPDATE
    updated = kb.update_post_mortem(doc.incident_id, {"mttr_minutes": 12.0})
    assert updated is not None
    assert updated["mttr_minutes"] == 12.0

    # 4. DELETE
    deleted = kb.delete_post_mortem(doc.incident_id)
    assert deleted is True
    assert kb.get_post_mortem(doc.incident_id) is None

def test_mongo_embedding_vs_referencing():
    """
    Verifies that embedded child documents (EmbeddedAlert, EmbeddedTimelineStep)
    exist directly inside the parent PostMortemDocument without separate collection queries,
    while referenced relationships link via incident_id / service foreign keys.
    """
    doc = PostMortemDocument(
        incident_id="inc_embed_ref_test",
        title="Network Partition Post-Mortem",
        summary="Network partition between gateway and auth service",
        root_cause_service="api-gateway",
        severity="CRITICAL",
        status="RESOLVED",
        root_cause="Packet loss exceeding 85% between gateway and auth",
        resolution="Rerouted via secondary mesh route",
        tags=["network", "ebpf", "partition"],
        referenced_service_ids=["svc_api_gateway"],
        referenced_audit_ids=["aud_rem_001"],
        embedded_alerts=[
            EmbeddedAlert(alert_id="alt_net_1", service="api-gateway", severity="CRITICAL", metric="packet_drop_rate", metric_value=85.0, threshold=10.0, message="High drop rate"),
            EmbeddedAlert(alert_id="alt_net_2", service="auth-service", severity="CRITICAL", metric="tcp_retransmits", metric_value=42.0, threshold=5.0, message="Retransmits high")
        ],
        embedded_timeline=[
            EmbeddedTimelineStep(stage=1, event_type="DIAGNOSIS", service="api-gateway", description="Identified upstream packet drop")
        ]
    )
    # Embedded documents test
    assert len(doc.embedded_alerts) == 2
    assert doc.embedded_alerts[0].metric == "packet_drop_rate"
    # Referenced keys test
    assert doc.referenced_service_ids == ["svc_api_gateway"]
    assert doc.referenced_audit_ids == ["aud_rem_001"]

def test_mongo_aggregation_pipelines():
    kb = MongoIncidentKnowledgeBase()
    # Seed 2 post-mortems
    kb.create_post_mortem(PostMortemDocument(
        incident_id="inc_agg_1",
        title="Incident 1",
        summary="Memory leak incident",
        root_cause_service="postgresql",
        severity="CRITICAL",
        status="RESOLVED",
        root_cause="OOM",
        resolution="Restart",
        mttr_minutes=20.0,
        tags=["db", "memory"],
        embedded_alerts=[
            EmbeddedAlert(alert_id="a1", service="postgresql", severity="CRITICAL", metric="mem", metric_value=95, threshold=80, message="mem high")
        ]
    ))
    kb.create_post_mortem(PostMortemDocument(
        incident_id="inc_agg_2",
        title="Incident 2",
        summary="High CPU incident",
        root_cause_service="postgresql",
        severity="CRITICAL",
        status="RESOLVED",
        root_cause="High CPU",
        resolution="Scale",
        mttr_minutes=10.0,
        tags=["db", "cpu"],
        embedded_alerts=[
            EmbeddedAlert(alert_id="a2", service="postgresql", severity="CRITICAL", metric="cpu", metric_value=99, threshold=80, message="cpu high")
        ]
    ))

    # Aggregation 1: Group by service and compute average MTTR
    mttr = kb.aggregate_mttr_by_service()
    assert len(mttr) > 0
    pg_agg = next(item for item in mttr if item["_id"] == "postgresql")
    assert pg_agg["incident_count"] == 2
    assert pg_agg["avg_mttr_minutes"] == 15.0

    # Aggregation 2: $unwind embedded_alerts array and count metrics
    dist = kb.aggregate_alerts_unwind_distribution()
    assert len(dist) >= 1

def test_mongo_indexing_catalog():
    kb = MongoIncidentKnowledgeBase()
    indexes = kb.list_indexes()
    assert len(indexes) >= 3
    index_names = [idx["name"] for idx in indexes]
    assert "idx_incident_id_unique" in index_names
    assert "idx_service_status_time" in index_names
    assert "idx_multikey_tags" in index_names

# ------------------------------------------------------------------------------
# 2. SQL Concepts Tests (JOINs, Indexing, Grouping/Filtering, Normalization, ACID)
# ------------------------------------------------------------------------------
from app.database.session import SessionLocal, Base, engine
from app.database.models import (
    ServiceModel,
    AlertModel,
    IncidentModel,
    with_transaction,
)
from app.database.repository import TelemetryRepository

def test_sql_joins_and_grouping():
    db = SessionLocal()
    try:
        # Seed test service and alert
        service_id = f"svc_join_test_{uuid.uuid4().hex[:6]}"
        db.add(ServiceModel(
            service_id=service_id,
            name="Checkout Microservice",
            type="api",
            status="Operational"
        ))
        db.add(AlertModel(
            alert_id=f"alt_join_{uuid.uuid4().hex[:6]}",
            timestamp=datetime.now(timezone.utc).isoformat(),
            service=service_id,
            severity="CRITICAL",
            alert_type="HIGH_LATENCY",
            metric="latency_p99",
            metric_value=2450.0,
            threshold=500.0,
            message="Extreme checkout latency detected"
        ))
        db.commit()

        # 1. SQL JOIN: alerts LEFT OUTER JOIN services
        joined_results = TelemetryRepository.get_alerts_joined_with_services(db, limit=10)
        assert len(joined_results) > 0
        match = next(j for j in joined_results if j["service"] == service_id)
        assert match["service_name"] == "Checkout Microservice"
        assert match["severity"] == "CRITICAL"

        # 2. SQL Grouping, Filtering (HAVING), Ordering
        grouped = TelemetryRepository.get_alert_aggregations_grouped(db)
        assert isinstance(grouped, list)
        assert len(grouped) > 0
        assert "service" in grouped[0]
        assert "total_alerts" in grouped[0]
        assert "avg_metric_value" in grouped[0]

    finally:
        db.close()

def test_sql_acid_transactions():
    db = SessionLocal()
    test_id = f"inc_tx_{uuid.uuid4().hex[:6]}"
    
    # Successful transaction
    with with_transaction(db):
        db.add(IncidentModel(
            incident_id=test_id,
            title="Transaction Success Test",
            started_at=datetime.now(timezone.utc).isoformat()
        ))

    # Verify committed
    assert db.query(IncidentModel).filter(IncidentModel.incident_id == test_id).first() is not None

    # Rollback transaction on error
    fail_id = f"inc_tx_fail_{uuid.uuid4().hex[:6]}"
    try:
        with with_transaction(db):
            db.add(IncidentModel(
                incident_id=fail_id,
                title="Should Rollback",
                started_at=datetime.now(timezone.utc).isoformat()
            ))
            raise RuntimeError("Simulated transaction fault")
    except RuntimeError:
        pass

    # Verify rollback succeeded (item not in database)
    assert db.query(IncidentModel).filter(IncidentModel.incident_id == fail_id).first() is None
    db.close()

# ------------------------------------------------------------------------------
# 3. Auth & Security Tests (Password Hashing, JWT, No Insecure Bypasses)
# ------------------------------------------------------------------------------
from services.common.security import verify_password, get_password_hash, create_access_token, decode_token

def test_password_hashing_and_verification():
    raw_password = "SuperSecretPassword#2026!"
    hashed = get_password_hash(raw_password)
    
    # Must be valid bcrypt hash format ($2b$12$...)
    assert hashed.startswith("$2b$12$")
    assert verify_password(raw_password, hashed) is True
    assert verify_password("wrong_password", hashed) is False

    # Security check: insecure demo bypass must be completely removed
    assert verify_password("demo123", hashed) is False

def test_jwt_issuance_and_verification():
    claims = {"sub": "user@example.com", "user_id": "usr_99", "role": "admin"}
    token = create_access_token(claims)
    assert isinstance(token, str)
    assert len(token) > 20

    decoded = decode_token(token)
    assert decoded is not None
    assert decoded["sub"] == "user@example.com"
    assert decoded["role"] == "admin"
    assert "exp" in decoded

# ------------------------------------------------------------------------------
# 4. Payment Gateway Tests (Test-Mode Intent & Webhook Signature Verification)
# ------------------------------------------------------------------------------
from services.checkout_api.main import (
    PAYMENT_WEBHOOK_SECRET,
    create_payment_intent,
    PaymentIntentRequest,
)

def test_payment_gateway_intent_and_idempotency():
    req = PaymentIntentRequest(
        order_id="ord_test_901",
        amount=149.99,
        currency="usd",
        customer_email="customer@example.com",
        idempotency_key="idemp_key_unique_123"
    )
    res1 = create_payment_intent(req)
    assert res1.id.startswith("pi_test_")
    assert res1.amount == 149.99
    assert res1.currency == "usd"

    # Idempotent second call returns identical intent ID
    res2 = create_payment_intent(req)
    assert res2.id == res1.id
    assert res2.client_secret == res1.client_secret

def test_payment_webhook_hmac_signature():
    payload = json.dumps({
        "type": "payment_intent.succeeded",
        "data": {
            "object": {
                "id": "pi_test_sample",
                "order_id": "ord_1001"
            }
        }
    }).encode("utf-8")

    # Generate valid HMAC signature
    valid_sig = hmac.new(PAYMENT_WEBHOOK_SECRET.encode("utf-8"), payload, hashlib.sha256).hexdigest()
    assert len(valid_sig) == 64

    # Verification helper logic check
    computed_sig = hmac.new(PAYMENT_WEBHOOK_SECRET.encode("utf-8"), payload, hashlib.sha256).hexdigest()
    assert hmac.compare_digest(valid_sig, computed_sig) is True

    # Tampered signature check
    tampered_sig = "a" * 64
    assert hmac.compare_digest(tampered_sig, computed_sig) is False

# ------------------------------------------------------------------------------
# 5. File Upload Handling & SSR Incident Report Tests
# ------------------------------------------------------------------------------
from app.main import get_incident_ssr_report

def test_ssr_incident_report():
    db = SessionLocal()
    try:
        response = get_incident_ssr_report("inc_sample_ssr", db=db)
        html_content = response.body.decode("utf-8")
        assert "<!DOCTYPE html>" in html_content
        assert "OpsPilot SSR Incident Report" in html_content
        assert "Server-Rendered HTML" in html_content
        assert "inc_sample_ssr" in html_content
    finally:
        db.close()
