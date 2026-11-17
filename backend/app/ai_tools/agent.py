import logging
import json
from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session

from app.remediation.safety_gate import RemediationSafetyGate, remediation_allowlist
from app.remediation.models import SafetyDecision
from app.database.repository import TelemetryRepository
from app.models.mongo import mongo_kb

logger = logging.getLogger("opspilot.ai_tools")

# ==============================================================================
# OpenAI / Gemini Function Calling & Tool Specifications
# ==============================================================================
TOOL_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "propose_remediation_action",
            "description": "Propose an automated or safety-gated remediation action for an active incident. Must pass 10-rule Safety Gate.",
            "parameters": {
                "type": "object",
                "properties": {
                    "incident_id": {
                        "type": "string",
                        "description": "Unique identifier of the target incident (e.g. inc_abc123)"
                    },
                    "action": {
                        "type": "string",
                        "enum": [
                            "restart_service",
                            "scale_service",
                            "traffic_shift_rollback",
                            "clear_cache",
                            "flush_connection_pool",
                            "adjust_circuit_breaker",
                            "reroute_traffic"
                        ],
                        "description": "Allowlisted remediation action to perform"
                    },
                    "target_service": {
                        "type": "string",
                        "description": "Target microservice or infrastructure component"
                    },
                    "parameters": {
                        "type": "object",
                        "description": "Action-specific parameters (e.g. replica_count, timeout_ms, version_tag)"
                    },
                    "confidence": {
                        "type": "number",
                        "minimum": 0.0,
                        "maximum": 1.0,
                        "description": "Diagnostic confidence score (0.0 - 1.0)"
                    }
                },
                "required": ["incident_id", "action", "target_service"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "query_service_telemetry",
            "description": "Query historical metrics, alert logs, and operational health of a microservice.",
            "parameters": {
                "type": "object",
                "properties": {
                    "service_name": {
                        "type": "string",
                        "description": "Target service ID (e.g. postgresql, checkout-api, auth-service)"
                    },
                    "metric_name": {
                        "type": "string",
                        "description": "Specific metric to query (e.g. latency_p99, error_rate, active_connections)"
                    },
                    "time_window_minutes": {
                        "type": "integer",
                        "minimum": 1,
                        "maximum": 1440,
                        "default": 30,
                        "description": "Lookback time window in minutes"
                    }
                },
                "required": ["service_name"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "fetch_historical_incidents",
            "description": "Query MongoDB incident memory and historical post-mortems for similar past degradations.",
            "parameters": {
                "type": "object",
                "properties": {
                    "service_name": {
                        "type": "string",
                        "description": "Filter past incidents by service name"
                    },
                    "tags": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Matching tags (e.g. ['database', 'cascade', 'timeout'])"
                    },
                    "limit": {
                        "type": "integer",
                        "minimum": 1,
                        "maximum": 20,
                        "default": 5
                    }
                },
                "required": ["service_name"]
            }
        }
    }
]

# ==============================================================================
# Strict Pydantic Argument Validation Models
# ==============================================================================
class ProposeRemediationArgs(BaseModel):
    incident_id: str = Field(..., min_length=3, max_length=64)
    action: str = Field(..., min_length=3, max_length=64)
    target_service: str = Field(..., min_length=2, max_length=64)
    parameters: Dict[str, Any] = Field(default_factory=dict)
    confidence: float = Field(0.85, ge=0.0, le=1.0)

    @field_validator("action")
    @classmethod
    def validate_action(cls, v: str) -> str:
        clean = v.strip().lower()
        allowed = [
            "restart_service",
            "scale_service",
            "traffic_shift_rollback",
            "clear_cache",
            "flush_connection_pool",
            "adjust_circuit_breaker",
            "reroute_traffic"
        ]
        if clean not in allowed:
            raise ValueError(f"Action '{v}' is not in the allowlist: {allowed}")
        return clean

class QueryTelemetryArgs(BaseModel):
    service_name: str = Field(..., min_length=2, max_length=64)
    metric_name: Optional[str] = Field(None, max_length=64)
    time_window_minutes: int = Field(30, ge=1, le=1440)

class FetchHistoricalArgs(BaseModel):
    service_name: str = Field(..., min_length=2, max_length=64)
    tags: List[str] = Field(default_factory=list)
    limit: int = Field(5, ge=1, le=20)

class ToolCallExecutionRequest(BaseModel):
    tool_name: str
    arguments: Dict[str, Any]
    caller_role: Optional[str] = "sre_admin"

# ==============================================================================
# AI Tool Execution Engine with Authorization & Safety Gate Enforcement
# ==============================================================================
class AIToolExecutor:
    """
    Executes function calls produced by LLM agents.
    Enforces argument validation and routes remediation actions through OpsPilot's
    10-rule Safety Gate and authorization policies.
    """

    def __init__(self):
        self.safety_gate = RemediationSafetyGate(allowlist=remediation_allowlist)

    def execute(
        self,
        tool_name: str,
        arguments: Dict[str, Any],
        caller_role: str,
        db: Session
    ) -> Dict[str, Any]:
        logger.info(f"[AIToolExecutor] Dispatching tool '{tool_name}' for caller with role '{caller_role}'")

        if tool_name == "propose_remediation_action":
            # 1. Validate Arguments
            args = ProposeRemediationArgs(**arguments)

            # 2. Authorization Check (Only admin, SRE, or opspilot system roles can trigger remediation)
            if caller_role not in ["sre_admin", "admin", "opspilot-core"]:
                return {
                    "tool": tool_name,
                    "status": "unauthorized",
                    "error": f"Role '{caller_role}' is not authorized to propose remediation actions.",
                    "allowed_roles": ["sre_admin", "admin", "opspilot-core"]
                }

            # 3. Safety Gate Evaluation (10 deterministic safety checks)
            gate_result = self.safety_gate.evaluate(
                db=db,
                incident_id=args.incident_id,
                action=args.action,
                target_service=args.target_service,
                mode="SIMULATION",
                parameters=args.parameters
            )

            is_approved = gate_result.decision == SafetyDecision.APPROVED
            requires_review = gate_result.decision == SafetyDecision.HUMAN_REVIEW

            return {
                "tool": tool_name,
                "status": "success",
                "incident_id": args.incident_id,
                "action": args.action,
                "target_service": args.target_service,
                "safety_decision": gate_result.decision.value,
                "is_approved": is_approved,
                "requires_human_review": requires_review,
                "reason": gate_result.reason,
                "conditions_passed": sum(1 for c in gate_result.conditions if c.passed),
                "total_conditions": len(gate_result.conditions)
            }

        elif tool_name == "query_service_telemetry":
            args = QueryTelemetryArgs(**arguments)
            alerts = TelemetryRepository.get_alerts(db, service=args.service_name, limit=10)
            metrics = TelemetryRepository.get_metrics(db, service=args.service_name, metric_name=args.metric_name, limit=20)
            return {
                "tool": tool_name,
                "status": "success",
                "service": args.service_name,
                "recent_alerts_count": len(alerts),
                "alerts": alerts[:5],
                "metrics_sampled": len(metrics)
            }

        elif tool_name == "fetch_historical_incidents":
            args = FetchHistoricalArgs(**arguments)
            history = mongo_kb.find_by_service(service=args.service_name)
            return {
                "tool": tool_name,
                "status": "success",
                "service": args.service_name,
                "matched_count": len(history),
                "results": history[:args.limit]
            }

        else:
            return {
                "tool": tool_name,
                "status": "error",
                "error": f"Unknown tool '{tool_name}'"
            }

ai_tool_executor = AIToolExecutor()
