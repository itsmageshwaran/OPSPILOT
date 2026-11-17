import json
from datetime import datetime, timezone
from contextlib import contextmanager
from sqlalchemy import Column, Integer, String, Float, Text, JSON, DateTime, Index
from .session import Base

# ==============================================================================
# Relational Normalization Architecture (1NF, 2NF, 3NF):
#
# 1. First Normal Form (1NF):
#    - All column values are atomic (indivisible scalars: strings, floats, ints).
#    - Unique primary keys (id, service_id, alert_id) identify every tuple.
#    - No repeating attribute groups.
#
# 2. Second Normal Form (2NF):
#    - Satisfies 1NF.
#    - All non-key attributes are fully functionally dependent on the complete primary key,
#      avoiding partial key dependencies on composite keys (e.g. dependencies table).
#
# 3. Third Normal Form (3NF):
#    - Satisfies 2NF.
#    - No transitive functional dependencies: non-key attributes depend ONLY on the primary key,
#      not on another non-key attribute (e.g. services, dependencies, alerts, and incidents
#      are decomposed into separate normalized relations rather than a single denormalized table).
# ==============================================================================

def current_time():
    return datetime.now(timezone.utc)

@contextmanager
def with_transaction(db_session):
    """
    ACID Transaction Context Manager:
    Guarantees Atomicity, Consistency, Isolation, and Durability.
    Automatically commits on success; executes rollback on any exception.
    """
    try:
        yield db_session
        db_session.commit()
    except Exception as e:
        db_session.rollback()
        raise e

class ServiceModel(Base):
    __tablename__ = "services"

    id = Column(Integer, primary_key=True, index=True)
    service_id = Column(String(64), unique=True, index=True, nullable=False)
    name = Column(String(128), nullable=False)
    type = Column(String(64), nullable=False)
    status = Column(String(32), default="Operational")
    metadata_json = Column(JSON, default=dict)
    updated_at = Column(DateTime, default=current_time, onupdate=current_time)

class DependencyModel(Base):
    __tablename__ = "dependencies"

    id = Column(Integer, primary_key=True, index=True)
    source = Column(String(64), index=True, nullable=False)
    target = Column(String(64), index=True, nullable=False)
    relationship = Column(String(64), default="calls")
    metadata_json = Column(JSON, default=dict)
    created_at = Column(DateTime, default=current_time)

    __table_args__ = (
        Index("ix_dependency_source_target", "source", "target", unique=True),
    )

class AlertModel(Base):
    __tablename__ = "alerts"

    id = Column(Integer, primary_key=True, index=True)
    alert_id = Column(String(64), unique=True, index=True, nullable=False)
    timestamp = Column(String(64), index=True, nullable=False)
    service = Column(String(64), index=True, nullable=False)
    severity = Column(String(32), index=True, nullable=False)
    alert_type = Column(String(64), index=True, nullable=False)
    metric = Column(String(128), nullable=False)
    metric_value = Column(Float, nullable=False)
    threshold = Column(Float, nullable=False)
    message = Column(Text, nullable=False)
    source = Column(String(64), default="shopflow-telemetry-agent")
    dependency = Column(String(64), nullable=True)
    tags_json = Column(JSON, default=dict)
    raw_payload_json = Column(JSON, default=dict)
    created_at = Column(DateTime, default=current_time)

    __table_args__ = (
        Index("ix_alerts_service_timestamp", "service", "timestamp"),
        Index("ix_alerts_severity_created", "severity", "created_at"),
    )

class MetricModel(Base):
    __tablename__ = "metrics"

    id = Column(Integer, primary_key=True, index=True)
    timestamp = Column(String(64), index=True, nullable=False)
    service = Column(String(64), index=True, nullable=False)
    metric_name = Column(String(128), index=True, nullable=False)
    value = Column(Float, nullable=False)
    unit = Column(String(32), nullable=True)
    tags_json = Column(JSON, default=dict)
    raw_payload_json = Column(JSON, default=dict)
    created_at = Column(DateTime, default=current_time)

    __table_args__ = (
        Index("ix_metrics_service_name_time", "service", "metric_name", "timestamp"),
    )

class LogModel(Base):
    __tablename__ = "logs"

    id = Column(Integer, primary_key=True, index=True)
    log_id = Column(String(64), unique=True, index=True, nullable=False)
    timestamp = Column(String(64), index=True, nullable=False)
    service = Column(String(64), index=True, nullable=False)
    level = Column(String(16), index=True, nullable=False)
    event = Column(String(64), index=True, nullable=False)
    message = Column(Text, nullable=False)
    request_id = Column(String(64), nullable=True)
    dependency = Column(String(64), nullable=True)
    latency_ms = Column(Float, nullable=True)
    status_code = Column(Integer, nullable=True)
    metadata_json = Column(JSON, default=dict)
    raw_payload_json = Column(JSON, default=dict)
    created_at = Column(DateTime, default=current_time)

    __table_args__ = (
        Index("ix_logs_service_level_time", "service", "level", "timestamp"),
    )

class EventModel(Base):
    __tablename__ = "events"

    id = Column(Integer, primary_key=True, index=True)
    event_id = Column(String(64), unique=True, index=True, nullable=False)
    timestamp = Column(String(64), index=True, nullable=False)
    service = Column(String(64), index=True, nullable=False)
    event_type = Column(String(64), index=True, nullable=False)
    message = Column(Text, nullable=False)
    metadata_json = Column(JSON, default=dict)
    raw_payload_json = Column(JSON, default=dict)
    created_at = Column(DateTime, default=current_time)

class IncidentModel(Base):
    """Phase 3: Dependency-Aware Correlation & Incident Management"""
    __tablename__ = "incidents"

    id = Column(Integer, primary_key=True, index=True)
    incident_id = Column(String(64), unique=True, index=True, nullable=False)
    title = Column(String(255), nullable=False)
    severity = Column(String(32), default="CRITICAL")
    status = Column(String(32), default="OPEN")  # OPEN, INVESTIGATING, MITIGATED, RESOLVED
    started_at = Column(String(64), nullable=False)
    updated_at = Column(String(64), nullable=True)
    resolved_at = Column(String(64), nullable=True)
    alert_count = Column(Integer, default=0)
    alert_ids_json = Column(JSON, default=list)
    affected_services_json = Column(JSON, default=list)
    correlation_score = Column(Float, default=1.0)
    correlation_method = Column(String(64), default="dependency_aware")
    evidence_json = Column(JSON, default=dict)
    diagnosis_json = Column(JSON, default=dict)
    root_cause_service = Column(String(64), nullable=True)
    summary = Column(Text, nullable=True)
    created_at = Column(DateTime, default=current_time)

    __table_args__ = (
        Index("ix_incidents_status_severity", "status", "severity"),
        Index("ix_incidents_started_at", "started_at"),
    )

class RemediationAuditModel(Base):
    """Phase 5: Safety-Gated Remediation, Recovery & Immutable Audit Trail"""
    __tablename__ = "remediation_audits"

    id = Column(Integer, primary_key=True, index=True)
    audit_id = Column(String(64), unique=True, index=True, nullable=False)
    incident_id = Column(String(64), index=True, nullable=False)
    timestamp = Column(String(64), index=True, nullable=False)
    root_cause_service = Column(String(64), nullable=True)
    confidence = Column(Float, default=0.0)
    action = Column(String(64), nullable=False)
    target_service = Column(String(64), nullable=False)
    decision = Column(String(32), index=True, nullable=False)  # APPROVED, REJECTED, HUMAN_REVIEW
    reason = Column(Text, nullable=False)
    execution_mode = Column(String(32), default="SIMULATION")  # SIMULATION, REAL
    execution_status = Column(String(32), default="PENDING")   # SIMULATED_SUCCESS, EXECUTED_SUCCESS, FAILED, SKIPPED
    recovery_status = Column(String(32), default="UNKNOWN")    # RECOVERED, NOT_RECOVERED, UNKNOWN, PENDING
    actor = Column(String(64), default="opspilot-remediation-engine")
    allowlist_policy_json = Column(JSON, default=dict)
    details_json = Column(JSON, default=dict)
    created_at = Column(DateTime, default=current_time)

    __table_args__ = (
        Index("ix_remediation_incident_decision", "incident_id", "decision"),
    )

