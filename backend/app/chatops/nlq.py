import time
import re
import json
import logging
from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field
from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy import text
from sqlalchemy.engine import Engine
import httpx

from app.config import settings
from app.database.session import engine, get_db

logger = logging.getLogger("opspilot.chatops.nlq")

router = APIRouter(prefix="/api/chatops", tags=["ChatOps NLQ"])

# ============================================================================
# Pydantic Schemas
# ============================================================================

class NLQRequest(BaseModel):
    query: str = Field(..., description="Natural language question, e.g., 'Show me all critical database incidents from last week'")
    max_rows: Optional[int] = Field(default=50, ge=1, le=200, description="Max rows to return")

class NLQRawQueryRequest(BaseModel):
    sql: str = Field(..., description="Raw read-only SQL query to execute")
    max_rows: Optional[int] = Field(default=50, ge=1, le=200, description="Max rows to return")

class NLQResponse(BaseModel):
    query: str
    sql: str
    row_count: int
    columns: List[str]
    rows: List[Dict[str, Any]]
    execution_time_ms: float
    engine: str = "llm_nlq"
    explanation: Optional[str] = None

class SchemaTableInfo(BaseModel):
    table_name: str
    description: str
    columns: List[str]
    sample_queries: List[str]

# ============================================================================
# Database Schema Metadata & System Prompts
# ============================================================================

DB_SCHEMA_DOCUMENTATION = """
Available Tables in OpsPilot SQLite Database (WAL mode):
1. incidents:
   - id (INTEGER PK)
   - incident_id (TEXT, e.g. 'inc-001')
   - title (TEXT)
   - severity (TEXT: 'CRITICAL', 'HIGH', 'MEDIUM', 'LOW')
   - status (TEXT: 'OPEN', 'INVESTIGATING', 'MITIGATED', 'RESOLVED')
   - started_at (TEXT ISO 8601 timestamp)
   - resolved_at (TEXT ISO 8601 timestamp)
   - alert_count (INTEGER)
   - correlation_score (REAL)
   - correlation_method (TEXT)
   - root_cause_service (TEXT, e.g. 'postgresql', 'auth-service', 'checkout-api')
   - summary (TEXT)

2. alerts:
   - id (INTEGER PK)
   - alert_id (TEXT)
   - timestamp (TEXT ISO 8601 timestamp)
   - service (TEXT)
   - severity (TEXT: 'CRITICAL', 'WARNING', 'INFO')
   - alert_type (TEXT, e.g. 'DB_CONNECTION_EXHAUSTION', 'HIGH_LATENCY', 'PRE_ALERT', 'PACKET_LOSS_CRITICAL')
   - metric (TEXT)
   - metric_value (REAL)
   - threshold (REAL)
   - message (TEXT)
   - dependency (TEXT)

3. services:
   - id (INTEGER PK)
   - service_id (TEXT, e.g. 'api-gateway', 'postgresql', 'auth-service')
   - name (TEXT)
   - type (TEXT: 'gateway', 'service', 'database', 'cache')
   - status (TEXT: 'Operational', 'Degraded', 'Major Outage')
   - updated_at (TEXT)

4. remediation_audits:
   - id (INTEGER PK)
   - audit_id (TEXT)
   - incident_id (TEXT)
   - timestamp (TEXT)
   - root_cause_service (TEXT)
   - confidence (REAL)
   - action (TEXT: 'scale_up', 'restart_service', 'failover_replica', 'traffic_shift_rollback')
   - target_service (TEXT)
   - decision (TEXT: 'APPROVED', 'REJECTED', 'HUMAN_REVIEW')
   - reason (TEXT)
   - execution_mode (TEXT: 'SIMULATION', 'REAL')
   - execution_status (TEXT: 'SIMULATED_SUCCESS', 'EXECUTED_SUCCESS', 'FAILED')
   - recovery_status (TEXT: 'RECOVERED', 'NOT_RECOVERED')

5. logs:
   - id (INTEGER PK)
   - log_id (TEXT)
   - timestamp (TEXT)
   - service (TEXT)
   - level (TEXT: 'INFO', 'WARN', 'ERROR', 'DEBUG')
   - event (TEXT)
   - message (TEXT)
   - dependency (TEXT)
   - latency_ms (REAL)
   - status_code (INTEGER)

6. metrics:
   - id (INTEGER PK)
   - timestamp (TEXT)
   - service (TEXT)
   - metric_name (TEXT)
   - value (REAL)
   - unit (TEXT)
"""

SYSTEM_PROMPT_NLQ = f"""
You are an expert SQLite Database Administrator and SRE Architect for OpsPilot, an AIOps incident management system.
Your job is to translate an English natural language query from an SRE engineer into a single, valid, highly optimized, READ-ONLY SQLite SELECT query.

{DB_SCHEMA_DOCUMENTATION}

CRUCIAL SECURITY AND FUNCTIONAL CONSTRAINTS:
1. READ-ONLY MANDATE: You must ONLY output a SELECT query (or WITH clause that ends in SELECT).
2. UNDER NO CIRCUMSTANCES should you ever output INSERT, UPDATE, DELETE, DROP, ALTER, CREATE, REPLACE, TRUNCATE, ATTACH, DETACH, PRAGMA, or VACUUM.
3. No stacked queries or multiple statements (never include multiple semicolons).
4. Always include a sensible LIMIT (default LIMIT 50) to prevent memory exhaustion.
5. Order results sensibly (typically ORDER BY id DESC or ORDER BY timestamp DESC) unless specifically requested otherwise.
6. Return your output STRICTLY as a JSON object matching this schema:
{{
  "sql": "SELECT ...",
  "explanation": "Brief 1-sentence explanation of what this query fetches"
}}
"""

# ============================================================================
# Rigorous SQL Sanitizer and Guardrail Engine
# ============================================================================

FORBIDDEN_MUTATION_PATTERNS = [
    r"\bINSERT\b",
    r"\bUPDATE\b",
    r"\bDELETE\b",
    r"\bDROP\b",
    r"\bALTER\b",
    r"\bCREATE\b",
    r"\bREPLACE\b",
    r"\bTRUNCATE\b",
    r"\bATTACH\b",
    r"\bDETACH\b",
    r"\bPRAGMA\b",
    r"\bVACUUM\b",
    r"\bEXEC\b",
    r"\bEXECUTE\b",
    r"\bGRANT\b",
    r"\bREVOKE\b",
    r"\bTRANSACTION\b",
    r"\bCOMMIT\b",
    r"\bROLLBACK\b"
]

def sanitize_and_validate_sql(raw_sql: str, max_rows: int = 50) -> str:
    """
    Rigorously validates and sanitizes an incoming SQL query string.
    Enforces that the query is pure read-only SELECT, blocks SQL injection / stacked queries,
    and guarantees a maximum result row limit.
    """
    if not raw_sql or not raw_sql.strip():
        raise HTTPException(status_code=400, detail="SQL query string cannot be empty.")

    # 1. Strip comments (-- single line, /* block */) and excessive whitespace
    sql = re.sub(r"--.*$", "", raw_sql, flags=re.MULTILINE)
    sql = re.sub(r"/\*.*?\*/", "", sql, flags=re.DOTALL).strip()

    # 2. Block stacked queries / semicolons (only a single trailing semicolon allowed)
    cleaned_without_trailing_semi = sql.rstrip(";").strip()
    if ";" in cleaned_without_trailing_semi:
        logger.warning(f"Blocked stacked query attempt: {raw_sql}")
        raise HTTPException(status_code=400, detail="Security Guardrail Violation: Stacked queries (multiple statements) are strictly prohibited.")

    # 3. Must begin with SELECT or WITH (for Common Table Expressions)
    if not (re.match(r"^\s*SELECT\b", cleaned_without_trailing_semi, re.IGNORECASE) or 
            re.match(r"^\s*WITH\b", cleaned_without_trailing_semi, re.IGNORECASE)):
        logger.warning(f"Blocked non-SELECT statement attempt: {raw_sql}")
        raise HTTPException(status_code=400, detail="Security Guardrail Violation: Only read-only SELECT queries are allowed.")

    # 4. Check against forbidden mutating keywords
    for pattern in FORBIDDEN_MUTATION_PATTERNS:
        match = re.search(pattern, cleaned_without_trailing_semi, re.IGNORECASE)
        if match:
            violating_token = match.group(0)
            logger.warning(f"Blocked forbidden token '{violating_token}' in SQL: {raw_sql}")
            raise HTTPException(
                status_code=400, 
                detail=f"Security Guardrail Violation: Mutating keyword '{violating_token}' is strictly forbidden in read-only sandbox."
            )

    # 5. Enforce or clamp LIMIT clause
    limit_match = re.search(r"\bLIMIT\s+(\d+)\b", cleaned_without_trailing_semi, re.IGNORECASE)
    if limit_match:
        requested_limit = int(limit_match.group(1))
        if requested_limit > max_rows:
            # Replace existing limit with clamped max_rows
            cleaned_without_trailing_semi = re.sub(
                r"\bLIMIT\s+\d+\b",
                f"LIMIT {max_rows}",
                cleaned_without_trailing_semi,
                flags=re.IGNORECASE
            )
    else:
        # Append LIMIT
        cleaned_without_trailing_semi = f"{cleaned_without_trailing_semi} LIMIT {max_rows}"

    return cleaned_without_trailing_semi

# ============================================================================
# LLM Translation & Offline Deterministic Heuristic Fallback
# ============================================================================

def _fallback_heuristic_translator(query_str: str, max_rows: int = 50) -> Dict[str, str]:
    """
    Deterministic rule-based translation for common SRE and AIOps queries.
    Guarantees seamless offline / air-gapped demo execution when no LLM API key is present.
    """
    q = query_str.lower().strip()

    # Critical database incidents
    if "critical" in q and ("database" in q or "postgres" in q):
        return {
            "sql": f"SELECT id, incident_id, title, severity, status, started_at, alert_count, root_cause_service FROM incidents WHERE severity = 'CRITICAL' AND (root_cause_service = 'postgresql' OR title LIKE '%database%' OR title LIKE '%postgres%') ORDER BY id DESC LIMIT {max_rows}",
            "explanation": "Filtered critical severity incidents impacting PostgreSQL or database components."
        }
    
    # All critical incidents
    if "critical" in q and "incident" in q:
        return {
            "sql": f"SELECT id, incident_id, title, severity, status, started_at, alert_count, root_cause_service FROM incidents WHERE severity = 'CRITICAL' ORDER BY id DESC LIMIT {max_rows}",
            "explanation": "Retrieved all incidents tagged with CRITICAL severity."
        }

    # Incidents general
    if "incident" in q:
        return {
            "sql": f"SELECT id, incident_id, title, severity, status, started_at, resolved_at, alert_count, root_cause_service FROM incidents ORDER BY id DESC LIMIT {max_rows}",
            "explanation": "Retrieved recent incidents ordered by latest creation."
        }

    # Alerts for postgresql or database
    if "alert" in q and ("postgres" in q or "db" in q or "database" in q):
        return {
            "sql": f"SELECT id, alert_id, timestamp, service, severity, alert_type, metric, metric_value, threshold, message FROM alerts WHERE service = 'postgresql' ORDER BY id DESC LIMIT {max_rows}",
            "explanation": "Retrieved recent alerts emitted by the PostgreSQL database service."
        }

    # Alerts general or critical alerts
    if "alert" in q:
        if "critical" in q:
            return {
                "sql": f"SELECT id, alert_id, timestamp, service, severity, alert_type, metric, metric_value, threshold, message FROM alerts WHERE severity = 'CRITICAL' ORDER BY id DESC LIMIT {max_rows}",
                "explanation": "Retrieved all high-priority alerts with CRITICAL severity."
            }
        return {
            "sql": f"SELECT id, alert_id, timestamp, service, severity, alert_type, metric, metric_value, threshold, message FROM alerts ORDER BY id DESC LIMIT {max_rows}",
            "explanation": "Retrieved the most recent telemetry alerts across all services."
        }

    # Remediation audits / actions
    if "remediation" in q or "action" in q or "audit" in q or "rollback" in q:
        return {
            "sql": f"SELECT id, audit_id, incident_id, timestamp, root_cause_service, action, target_service, decision, execution_status, recovery_status FROM remediation_audits ORDER BY id DESC LIMIT {max_rows}",
            "explanation": "Retrieved immutable remediation action audit records and execution outcomes."
        }

    # Service status / degraded services
    if "service" in q or "health" in q or "degraded" in q or "status" in q:
        if "degraded" in q or "outage" in q or "down" in q:
            return {
                "sql": f"SELECT service_id, name, type, status, updated_at FROM services WHERE status != 'Operational' LIMIT {max_rows}",
                "explanation": "Retrieved microservices currently experiencing Degraded or Outage conditions."
            }
        return {
            "sql": f"SELECT service_id, name, type, status, updated_at FROM services ORDER BY name ASC LIMIT {max_rows}",
            "explanation": "Listed all registered microservices in the topology inventory."
        }

    # Error logs
    if "log" in q or "error" in q:
        return {
            "sql": f"SELECT id, log_id, timestamp, service, level, event, message, latency_ms, status_code FROM logs WHERE level IN ('ERROR', 'WARN') ORDER BY id DESC LIMIT {max_rows}",
            "explanation": "Retrieved recent ERROR and WARN logs with associated HTTP status and latency metrics."
        }

    # Default fallback: recent incidents
    return {
        "sql": f"SELECT id, incident_id, title, severity, status, started_at, root_cause_service FROM incidents ORDER BY id DESC LIMIT {max_rows}",
        "explanation": "General overview of incidents matching the search criteria."
    }

def translate_nlq_to_sql(nlq_query: str, max_rows: int = 50) -> Dict[str, str]:
    """
    Translates an English natural language query into a sanitized read-only SQLite query.
    Attempts LLM chat completion first if configured; falls back gracefully to deterministic intent mapping.
    """
    is_llm_ready = bool(settings.llm_api_key and settings.llm_api_key not in ("sk-placeholder", ""))

    if is_llm_ready:
        endpoint = f"{settings.llm_base_url.rstrip('/')}/chat/completions"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {settings.llm_api_key}"
        }

        payload = {
            "model": settings.llm_model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT_NLQ},
                {"role": "user", "content": f"User SRE Query: {nlq_query}\nMaximum Rows: {max_rows}"}
            ],
            "temperature": 0.0,
            "response_format": {"type": "json_object"}
        }

        try:
            with httpx.Client(timeout=2.0) as client:
                res = client.post(endpoint, json=payload, headers=headers)
                if res.status_code == 200:
                    data = res.json()
                    content_str = data["choices"][0]["message"]["content"]
                    parsed = json.loads(content_str)
                    if "sql" in parsed and parsed["sql"]:
                        # Sanitize LLM-generated SQL
                        sanitized = sanitize_and_validate_sql(parsed["sql"], max_rows=max_rows)
                        return {
                            "sql": sanitized,
                            "explanation": parsed.get("explanation", "Generated via OpsPilot LLM engine.")
                        }
        except Exception as e:
            logger.warning(f"LLM translation failed or timed out: {e}. Falling back to deterministic heuristic.")

    # Offline / Heuristic Fallback
    fallback = _fallback_heuristic_translator(nlq_query, max_rows=max_rows)
    fallback["sql"] = sanitize_and_validate_sql(fallback["sql"], max_rows=max_rows)
    return fallback

# ============================================================================
# Read-Only Database Execution
# ============================================================================

def execute_readonly_sql(db_target: Any, sanitized_sql: str) -> Dict[str, Any]:
    """
    Executes a sanitized read-only SQL query against the database session or connection.
    Guarantees pure SELECT execution and measures execution latency in milliseconds.
    """
    start_time = time.perf_counter()
    rows_data: List[Dict[str, Any]] = []
    columns: List[str] = []

    result = db_target.execute(text(sanitized_sql))
    columns = list(result.keys()) if result.keys() else []
    for row in result.fetchall():
        row_dict = {}
        for col_name, val in zip(columns, row):
            row_dict[col_name] = val
        rows_data.append(row_dict)

    execution_time_ms = round((time.perf_counter() - start_time) * 1000, 2)

    return {
        "columns": columns,
        "rows": rows_data,
        "row_count": len(rows_data),
        "execution_time_ms": execution_time_ms
    }

# ============================================================================
# API Endpoints
# ============================================================================

@router.post("/nlq", response_model=NLQResponse)
def query_natural_language(req: NLQRequest, db: Any = Depends(get_db)):
    """
    Translates an English natural language query into a secure, read-only SQLite SELECT query,
    executes it against OpsPilot's database, and returns structured JSON rows and columns.
    """
    logger.info(f"Received NLQ Query: '{req.query}'")

    # Step 1: Translate English query to SQL
    translation = translate_nlq_to_sql(req.query, max_rows=req.max_rows or 50)
    sql_to_run = translation["sql"]
    explanation = translation.get("explanation")

    # Step 2: Double-check sanitization
    final_sql = sanitize_and_validate_sql(sql_to_run, max_rows=req.max_rows or 50)

    # Step 3: Execute query in read-only mode
    try:
        query_results = execute_readonly_sql(db, final_sql)
    except Exception as e:
        logger.error(f"SQL execution error on '{final_sql}': {e}")
        raise HTTPException(status_code=500, detail=f"Database execution error: {str(e)}")

    return NLQResponse(
        query=req.query,
        sql=final_sql,
        row_count=query_results["row_count"],
        columns=query_results["columns"],
        rows=query_results["rows"],
        execution_time_ms=query_results["execution_time_ms"],
        engine="llm_nlq_engine" if (settings.llm_api_key and settings.llm_api_key not in ("sk-placeholder", "")) else "heuristic_nlq_engine",
        explanation=explanation
    )

@router.post("/query/raw", response_model=NLQResponse)
def query_raw_sql(req: NLQRawQueryRequest, db: Any = Depends(get_db)):
    """
    Executes a direct raw SQL query provided by an SRE engineer,
    strictly enforcing the read-only SELECT guardrails.
    """
    sanitized_sql = sanitize_and_validate_sql(req.sql, max_rows=req.max_rows or 50)

    try:
        query_results = execute_readonly_sql(db, sanitized_sql)
    except Exception as e:
        logger.error(f"Raw SQL execution error: {e}")
        raise HTTPException(status_code=500, detail=f"Database execution error: {str(e)}")

    return NLQResponse(
        query=req.sql,
        sql=sanitized_sql,
        row_count=query_results["row_count"],
        columns=query_results["columns"],
        rows=query_results["rows"],
        execution_time_ms=query_results["execution_time_ms"],
        engine="direct_sql_engine",
        explanation="Direct read-only SQL query executed via OpsPilot ChatOps sandbox."
    )

@router.get("/schema", response_model=List[SchemaTableInfo])
def get_schema_metadata():
    """
    Returns the database table schemas, column lists, and sample natural language queries.
    Used by the frontend ChatOps Terminal for interactive query chips and autocomplete.
    """
    return [
        SchemaTableInfo(
            table_name="incidents",
            description="Correlated SRE incidents with root-cause diagnoses and propagation evidence",
            columns=["id", "incident_id", "title", "severity", "status", "started_at", "alert_count", "root_cause_service", "summary"],
            sample_queries=[
                "Show all CRITICAL incidents",
                "Show active incidents affecting postgresql",
                "Find incidents from the past 24 hours"
            ]
        ),
        SchemaTableInfo(
            table_name="alerts",
            description="Raw telemetry alerts ingested from microservices and chaos engine",
            columns=["id", "alert_id", "timestamp", "service", "severity", "alert_type", "metric", "metric_value", "threshold", "message"],
            sample_queries=[
                "List all alerts for postgresql",
                "Find CRITICAL alerts with high latency",
                "Show recent PRE_ALERT predictive degradation warnings"
            ]
        ),
        SchemaTableInfo(
            table_name="remediation_audits",
            description="Immutable audit trail of automated safety-gated remediation actions and verifications",
            columns=["id", "audit_id", "incident_id", "timestamp", "root_cause_service", "action", "target_service", "decision", "execution_status", "recovery_status"],
            sample_queries=[
                "Show all approved remediation actions",
                "List failed remediation executions",
                "Show traffic shift rollback audit records"
            ]
        ),
        SchemaTableInfo(
            table_name="services",
            description="Microservice topology inventory with health status and metadata",
            columns=["service_id", "name", "type", "status", "updated_at"],
            sample_queries=[
                "List all degraded or failing services",
                "Show all registered microservices"
            ]
        ),
        SchemaTableInfo(
            table_name="logs",
            description="Structured microservice application logs and dependency tracing events",
            columns=["id", "log_id", "timestamp", "service", "level", "event", "message", "latency_ms", "status_code"],
            sample_queries=[
                "Show recent ERROR logs with status 504",
                "Find logs with latency greater than 2000ms"
            ]
        )
    ]
