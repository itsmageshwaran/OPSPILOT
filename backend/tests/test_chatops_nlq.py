import pytest
from app.chatops.nlq import (
    sanitize_and_validate_sql,
    _fallback_heuristic_translator,
    execute_readonly_sql,
    query_natural_language,
    query_raw_sql,
    get_schema_metadata,
    NLQRequest,
    NLQRawQueryRequest
)
from app.database.models import IncidentModel, AlertModel

def test_sql_sanitizer_permits_valid_select():
    sql = "SELECT id, title FROM incidents WHERE severity = 'CRITICAL'"
    sanitized = sanitize_and_validate_sql(sql)
    assert "SELECT id, title FROM incidents WHERE severity = 'CRITICAL'" in sanitized
    assert "LIMIT" in sanitized

def test_sql_sanitizer_clamps_limit():
    sql = "SELECT * FROM alerts LIMIT 500"
    sanitized = sanitize_and_validate_sql(sql, max_rows=50)
    assert "LIMIT 50" in sanitized

def test_sql_sanitizer_blocks_dangerous_mutations():
    bad_queries = [
        "DROP TABLE incidents",
        "DELETE FROM alerts",
        "UPDATE services SET status = 'Offline'",
        "INSERT INTO incidents (title) VALUES ('hacked')",
        "SELECT * FROM incidents; DROP TABLE alerts;",
        "ATTACH DATABASE 'other.db' AS other",
        "PRAGMA foreign_keys = OFF",
        "TRUNCATE TABLE metrics"
    ]
    for bad in bad_queries:
        with pytest.raises(Exception):
            sanitize_and_validate_sql(bad)

def test_heuristic_translator_scenarios():
    q1 = _fallback_heuristic_translator("Show me all critical database incidents from last week")
    assert "incidents" in q1["sql"].lower()
    assert "critical" in q1["sql"].lower()

    q2 = _fallback_heuristic_translator("List all alerts for postgresql")
    assert "alerts" in q2["sql"].lower()
    assert "postgresql" in q2["sql"].lower()

    q3 = _fallback_heuristic_translator("Show remediation audits")
    assert "remediation_audits" in q3["sql"].lower()

    q4 = _fallback_heuristic_translator("Show degraded services")
    assert "services" in q4["sql"].lower()

    q5 = _fallback_heuristic_translator("Show recent error logs")
    assert "logs" in q5["sql"].lower()

def test_execute_readonly_sql(db_session):
    # Insert test incident into db
    inc = IncidentModel(
        incident_id="inc-test-chatops",
        title="Test ChatOps Incident",
        severity="CRITICAL",
        status="OPEN",
        started_at="2026-11-11T10:00:00Z",
        alert_count=5,
        root_cause_service="postgresql"
    )
    db_session.add(inc)
    db_session.commit()

    res = execute_readonly_sql(db_session, "SELECT incident_id, title, severity FROM incidents WHERE incident_id = 'inc-test-chatops'")
    assert res["row_count"] == 1
    assert res["columns"] == ["incident_id", "title", "severity"]
    assert res["rows"][0]["incident_id"] == "inc-test-chatops"
    assert res["execution_time_ms"] >= 0.0

def test_query_natural_language_handler(db_session):
    req = NLQRequest(query="Show me all critical database incidents from last week")
    res = query_natural_language(req, db=db_session)
    assert res.query == req.query
    assert "SELECT" in res.sql
    assert isinstance(res.rows, list)
    assert isinstance(res.columns, list)
    assert res.execution_time_ms >= 0.0

def test_query_raw_sql_handler(db_session):
    req = NLQRawQueryRequest(sql="SELECT id, service_id FROM services")
    res = query_raw_sql(req, db=db_session)
    assert res.query == req.sql
    assert "SELECT" in res.sql
    assert isinstance(res.rows, list)

def test_query_raw_sql_handler_blocks_mutation(db_session):
    req = NLQRawQueryRequest(sql="DELETE FROM services WHERE id = 1")
    with pytest.raises(Exception):
        query_raw_sql(req, db=db_session)

def test_get_schema_metadata_handler():
    tables = get_schema_metadata()
    assert len(tables) >= 4
    names = [t.table_name for t in tables]
    assert "incidents" in names
    assert "alerts" in names
    assert "remediation_audits" in names
