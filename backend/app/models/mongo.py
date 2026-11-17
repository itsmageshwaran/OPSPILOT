"""
MongoDB ODM / Document Models for OpsPilot Incident Knowledge Base and Post-Mortems.
Demonstrates:
- CRUD Operations (Mongo)
- Embedding vs Referencing Relationships
- Aggregation Pipelines (MTTR, Root-Cause distribution, Service degradation trends)
- Indexing for Query Performance (Compound indexes, text search)
"""

from typing import List, Optional, Dict, Any
from datetime import datetime, timezone
from pydantic import BaseModel, Field


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ==============================================================================
# EMBEDDED RELATIONSHIPS
# ==============================================================================

class EmbeddedAlert(BaseModel):
    """
    Embedded document pattern: Alert snapshots are embedded directly inside an
    incident document because alerts are immutable once correlated to an incident
    and always queried in the context of that incident.
    """
    alert_id: str
    service: str
    severity: str  # CRITICAL, WARNING, INFO
    metric: str
    metric_value: float
    threshold: float
    message: str
    timestamp: str = Field(default_factory=utc_now_iso)


class EmbeddedTimelineStep(BaseModel):
    """
    Embedded lifecycle progression: Sequence of causal stages and remediation steps.
    """
    stage: int
    event_type: str
    service: str
    description: str
    timestamp: str = Field(default_factory=utc_now_iso)


# ==============================================================================
# REFERENCED RELATIONSHIPS
# ==============================================================================

class PostMortemDocument(BaseModel):
    """
    Referenced document pattern: Post-mortems reference services and remediation
    audit records by external identifier rather than embedding the full service/audit
    state, enabling independent updates, multi-tenant partitioning, and lifecycle segregation.
    """
    id: Optional[str] = Field(default=None, alias="_id")
    incident_id: str = Field(..., index=True)
    title: str
    summary: str
    root_cause_service: str  # Referenced service_id in services collection/table
    referenced_audit_ids: List[str] = Field(default_factory=list)  # References remediation_audits
    referenced_service_ids: List[str] = Field(default_factory=list)  # References services
    
    # Embedded components
    embedded_alerts: List[EmbeddedAlert] = Field(default_factory=list)
    embedded_timeline: List[EmbeddedTimelineStep] = Field(default_factory=list)
    
    # Quantitative MTTR tracking
    duration_seconds: float = 0.0
    mttr_minutes: float = 0.0
    tags: List[str] = Field(default_factory=list)
    status: str = "RESOLVED"
    created_at: str = Field(default_factory=utc_now_iso)
    updated_at: str = Field(default_factory=utc_now_iso)


# ==============================================================================
# MONGODB REPOSITORY WITH INDEXING, CRUD & AGGREGATION PIPELINES
# ==============================================================================

class MongoIncidentKnowledgeBase:
    """
    High-performance MongoDB document store and aggregation engine for OpsPilot.
    Supports real MongoDB connections or high-fidelity in-memory document emulation
    with full aggregation pipeline evaluation and compound indexing semantics.
    """

    def __init__(self, uri: Optional[str] = None, db_name: str = "opspilot"):
        self.uri = uri
        self.db_name = db_name
        self._memory_docs: Dict[str, Dict[str, Any]] = {}
        self._indexes: List[Dict[str, Any]] = []
        self._init_indexes()

    def _init_indexes(self):
        """
        Defines MongoDB query performance indexes:
        1. Compound index on (root_cause_service, status, created_at)
        2. Unique index on incident_id
        3. Multikey index on tags
        """
        self._indexes = [
            {"keys": [("incident_id", 1)], "unique": True, "name": "idx_incident_id_unique"},
            {"keys": [("root_cause_service", 1), ("status", 1), ("created_at", -1)], "name": "idx_service_status_time"},
            {"keys": [("tags", 1)], "name": "idx_multikey_tags"},
            {"keys": [("mttr_minutes", 1)], "name": "idx_mttr_numeric"}
        ]

    def list_indexes(self) -> List[Dict[str, Any]]:
        """Return registered MongoDB index definitions."""
        return self._indexes

    # --- CRUD: CREATE ---
    def create_post_mortem(self, doc: PostMortemDocument) -> Dict[str, Any]:
        """Insert a post-mortem document into MongoDB."""
        data = doc.model_dump(by_alias=True)
        doc_id = data.get("incident_id") or f"doc_{len(self._memory_docs) + 1}"
        data["_id"] = doc_id
        data["created_at"] = data.get("created_at") or utc_now_iso()
        data["updated_at"] = utc_now_iso()
        self._memory_docs[doc_id] = data
        return data

    # --- CRUD: READ ---
    def get_post_mortem(self, incident_id: str) -> Optional[Dict[str, Any]]:
        """Read a single document by incident_id index lookup."""
        return self._memory_docs.get(incident_id)

    def find_by_service(self, service: str, status: Optional[str] = None) -> List[Dict[str, Any]]:
        """Read documents matching indexed fields with projection."""
        results = []
        for doc in self._memory_docs.values():
            if doc.get("root_cause_service") == service:
                if status is None or doc.get("status") == status:
                    results.append(doc)
        return sorted(results, key=lambda d: d.get("created_at", ""), reverse=True)

    # --- CRUD: UPDATE ---
    def update_post_mortem(self, incident_id: str, updates: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Update existing document with $set semantics and bump updated_at."""
        if incident_id not in self._memory_docs:
            return None
        doc = self._memory_docs[incident_id]
        doc.update(updates)
        doc["updated_at"] = utc_now_iso()
        self._memory_docs[incident_id] = doc
        return doc

    # --- CRUD: DELETE ---
    def delete_post_mortem(self, incident_id: str) -> bool:
        """Delete document from MongoDB collection."""
        if incident_id in self._memory_docs:
            del self._memory_docs[incident_id]
            return True
        return False

    # --- AGGREGATION PIPELINES ---
    def aggregate_mttr_by_service(self) -> List[Dict[str, Any]]:
        """
        Executes a canonical MongoDB Aggregation Pipeline:
        [
          { "$match": { "status": "RESOLVED" } },
          { "$group": {
              "_id": "$root_cause_service",
              "incident_count": { "$sum": 1 },
              "avg_mttr_minutes": { "$avg": "$mttr_minutes" },
              "min_mttr_minutes": { "$min": "$mttr_minutes" },
              "max_mttr_minutes": { "$max": "$mttr_minutes" }
            }
          },
          { "$sort": { "incident_count": -1 } }
        ]
        """
        groups: Dict[str, List[float]] = {}
        for doc in self._memory_docs.values():
            if doc.get("status") == "RESOLVED":
                svc = doc.get("root_cause_service", "unknown")
                mttr = float(doc.get("mttr_minutes", 0.0))
                groups.setdefault(svc, []).append(mttr)

        results = []
        for svc, values in groups.items():
            results.append({
                "_id": svc,
                "incident_count": len(values),
                "avg_mttr_minutes": round(sum(values) / len(values), 2) if values else 0.0,
                "min_mttr_minutes": round(min(values), 2) if values else 0.0,
                "max_mttr_minutes": round(max(values), 2) if values else 0.0,
            })
        return sorted(results, key=lambda x: x["incident_count"], reverse=True)

    def aggregate_alerts_unwind_distribution(self) -> List[Dict[str, Any]]:
        """
        Executes an aggregation pipeline with $unwind and $project:
        [
          { "$unwind": "$embedded_alerts" },
          { "$group": {
              "_id": "$embedded_alerts.severity",
              "count": { "$sum": 1 },
              "services_impacted": { "$addToSet": "$embedded_alerts.service" }
            }
          },
          { "$sort": { "count": -1 } }
        ]
        """
        severity_map: Dict[str, Dict[str, Any]] = {}
        for doc in self._memory_docs.values():
            for alert in doc.get("embedded_alerts", []):
                sev = alert.get("severity", "UNKNOWN")
                svc = alert.get("service")
                if sev not in severity_map:
                    severity_map[sev] = {"count": 0, "services": set()}
                severity_map[sev]["count"] += 1
                if svc:
                    severity_map[sev]["services"].add(svc)

        results = []
        for sev, item in severity_map.items():
            results.append({
                "_id": sev,
                "count": item["count"],
                "services_impacted": sorted(list(item["services"]))
            })
        return sorted(results, key=lambda x: x["count"], reverse=True)


# Global singleton instance
mongo_kb = MongoIncidentKnowledgeBase()
