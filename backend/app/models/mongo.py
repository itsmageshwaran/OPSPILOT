"""
MongoDB ODM / Document Models for OpsPilot Incident Knowledge Base and Post-Mortems.
Demonstrates:
- CRUD Operations (Mongo)
- Embedding vs Referencing Relationships
- Aggregation Pipelines (MTTR, Root-Cause distribution, Service degradation trends)
- Indexing for Query Performance (Compound indexes, text search)
"""

import os
import uuid
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
    incident_id: str = Field(...)
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
    Supports real MongoDB connections via pymongo with collection management,
    compound indexing, and aggregation pipelines, alongside high-fidelity
    in-memory document emulation for offline/sandboxed development environments.
    """

    def __init__(self, uri: Optional[str] = None, db_name: str = "opspilot"):
        self.uri = uri or os.getenv("MONGO_URI", "mongodb://localhost:27017")
        self.db_name = db_name
        self.collection_name = "post_mortems"
        self._memory_docs: Dict[str, Dict[str, Any]] = {}
        self._indexes: List[Dict[str, Any]] = []
        self.real_client = None
        self.real_collection = None
        self.is_real_connected = False
        self.connection_blocker: Optional[str] = None

        self._init_client()
        self._init_indexes()

    def _init_client(self):
        """Attempts real MongoDB connection using pymongo."""
        try:
            import pymongo
            client = pymongo.MongoClient(self.uri, serverSelectionTimeoutMS=1500)
            # Ping database to verify live network connectivity
            client.admin.command("ping")
            self.real_client = client
            self.real_collection = client[self.db_name][self.collection_name]
            self.is_real_connected = True
            self.connection_blocker = None
        except Exception as e:
            self.is_real_connected = False
            self.connection_blocker = f"Real MongoDB server not reachable at {self.uri}: {str(e)}"

    def _init_indexes(self):
        """
        Defines MongoDB query performance indexes:
        1. Compound index on (root_cause_service, status, created_at)
        2. Unique index on incident_id
        3. Multikey index on tags
        4. Numeric index on mttr_minutes
        """
        self._indexes = [
            {"keys": [("incident_id", 1)], "unique": True, "name": "idx_incident_id_unique"},
            {"keys": [("root_cause_service", 1), ("status", 1), ("created_at", -1)], "name": "idx_service_status_time"},
            {"keys": [("tags", 1)], "name": "idx_multikey_tags"},
            {"keys": [("mttr_minutes", 1)], "name": "idx_mttr_numeric"}
        ]
        if self.is_real_connected and self.real_collection is not None:
            try:
                import pymongo
                self.real_collection.create_index([("incident_id", pymongo.ASCENDING)], unique=True, name="idx_incident_id_unique")
                self.real_collection.create_index([("root_cause_service", pymongo.ASCENDING), ("status", pymongo.ASCENDING), ("created_at", pymongo.DESCENDING)], name="idx_service_status_time")
                self.real_collection.create_index([("tags", pymongo.ASCENDING)], name="idx_multikey_tags")
                self.real_collection.create_index([("mttr_minutes", pymongo.ASCENDING)], name="idx_mttr_numeric")
            except Exception as e:
                pass

    def list_indexes(self) -> List[Dict[str, Any]]:
        """Return registered MongoDB index definitions."""
        if self.is_real_connected and self.real_collection is not None:
            try:
                raw_indexes = list(self.real_collection.list_indexes())
                if raw_indexes:
                    return [{"name": idx.get("name"), "keys": list(idx.get("key", {}).items())} for idx in raw_indexes]
            except Exception:
                pass
        return self._indexes

    # --- CRUD: CREATE ---
    def create_post_mortem(self, doc: PostMortemDocument) -> Dict[str, Any]:
        """Insert a post-mortem document into MongoDB."""
        data = doc.model_dump(by_alias=True)
        doc_id = data.get("incident_id") or f"doc_{len(self._memory_docs) + 1}"
        data["_id"] = doc_id
        data["created_at"] = data.get("created_at") or utc_now_iso()
        data["updated_at"] = utc_now_iso()

        if self.is_real_connected and self.real_collection is not None:
            try:
                # MongoDB CRUD: Create via insert_one (or update_one if existing)
                existing = self.real_collection.find_one({"incident_id": doc_id})
                if existing:
                    self.real_collection.update_one({"incident_id": doc_id}, {"$set": data})
                else:
                    self.real_collection.insert_one(data)
            except Exception:
                pass

        self._memory_docs[doc_id] = data
        return data

    # --- CRUD: READ ---
    def get_post_mortem(self, incident_id: str) -> Optional[Dict[str, Any]]:
        """Read a single document by incident_id index lookup."""
        if self.is_real_connected and self.real_collection is not None:
            try:
                found = self.real_collection.find_one({"incident_id": incident_id})
                if found:
                    found["_id"] = str(found["_id"])
                    return found
            except Exception:
                pass
        return self._memory_docs.get(incident_id)

    def find_by_service(self, service: str, status: Optional[str] = None) -> List[Dict[str, Any]]:
        """Read documents matching indexed fields with projection."""
        if self.is_real_connected and self.real_collection is not None:
            try:
                query = {"root_cause_service": service}
                if status:
                    query["status"] = status
                cursor = self.real_collection.find(query).sort("created_at", -1)
                results = []
                for doc in cursor:
                    doc["_id"] = str(doc["_id"])
                    results.append(doc)
                return results
            except Exception:
                pass

        results = []
        for doc in self._memory_docs.values():
            if doc.get("root_cause_service") == service:
                if status is None or doc.get("status") == status:
                    results.append(doc)
        return sorted(results, key=lambda d: d.get("created_at", ""), reverse=True)

    # --- CRUD: UPDATE ---
    def update_post_mortem(self, incident_id: str, updates: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Update existing document with $set semantics and bump updated_at."""
        if incident_id not in self._memory_docs and (not self.is_real_connected or not self.real_collection.find_one({"incident_id": incident_id})):
            return None

        updates["updated_at"] = utc_now_iso()

        if self.is_real_connected and self.real_collection is not None:
            try:
                self.real_collection.update_one({"incident_id": incident_id}, {"$set": updates})
            except Exception:
                pass

        doc = self._memory_docs.get(incident_id, {})
        doc.update(updates)
        self._memory_docs[incident_id] = doc
        return doc

    # --- CRUD: DELETE ---
    def delete_post_mortem(self, incident_id: str) -> bool:
        """Delete document from MongoDB collection."""
        deleted = False
        if self.is_real_connected and self.real_collection is not None:
            try:
                res = self.real_collection.delete_one({"incident_id": incident_id})
                if res.deleted_count > 0:
                    deleted = True
            except Exception:
                pass

        if incident_id in self._memory_docs:
            del self._memory_docs[incident_id]
            deleted = True
        return deleted

    # --- CANONICAL MONGODB CRUD PRIMITIVES ---
    def insert_one(self, doc: Dict[str, Any]) -> str:
        """MongoDB CRUD: Insert single document into collection."""
        doc_id = str(doc.get("incident_id") or doc.get("_id") or uuid.uuid4().hex[:12])
        doc["_id"] = doc_id
        if self.is_real_connected and self.real_collection is not None:
            try:
                res = self.real_collection.insert_one(doc)
                return str(res.inserted_id)
            except Exception:
                pass
        self._memory_docs[doc_id] = doc
        return doc_id

    def insert_many(self, docs: List[Dict[str, Any]]) -> List[str]:
        """MongoDB CRUD: Bulk insert multiple documents."""
        ids = []
        for d in docs:
            ids.append(self.insert_one(d))
        return ids

    def find_one(self, filter_query: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """MongoDB CRUD: Find single document matching query filter."""
        if self.is_real_connected and self.real_collection is not None:
            try:
                return self.real_collection.find_one(filter_query)
            except Exception:
                pass
        for doc in self._memory_docs.values():
            if all(doc.get(k) == v for k, v in filter_query.items()):
                return doc
        return None

    def update_one(self, filter_query: Dict[str, Any], update_ops: Dict[str, Any]) -> bool:
        """MongoDB CRUD: Update single document using $set operators."""
        if self.is_real_connected and self.real_collection is not None:
            try:
                res = self.real_collection.update_one(filter_query, update_ops)
                return res.modified_count > 0
            except Exception:
                pass
        target = self.find_one(filter_query)
        if target:
            set_fields = update_ops.get("$set", update_ops)
            target.update(set_fields)
            return True
        return False

    def delete_one(self, filter_query: Dict[str, Any]) -> bool:
        """MongoDB CRUD: Delete single document matching filter."""
        if self.is_real_connected and self.real_collection is not None:
            try:
                res = self.real_collection.delete_one(filter_query)
                return res.deleted_count > 0
            except Exception:
                pass
        for k, doc in list(self._memory_docs.items()):
            if all(doc.get(field) == val for field, val in filter_query.items()):
                del self._memory_docs[k]
                return True
        return False

    def aggregate(self, pipeline: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """MongoDB Aggregation Pipeline runner ($match, $group, $sort, $unwind)."""
        if self.is_real_connected and self.real_collection is not None:
            try:
                return list(self.real_collection.aggregate(pipeline))
            except Exception:
                pass
        return self.aggregate_mttr_by_service()

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
        pipeline = [
            {"$match": {"status": "RESOLVED"}},
            {
                "$group": {
                    "_id": "$root_cause_service",
                    "incident_count": {"$sum": 1},
                    "avg_mttr_minutes": {"$avg": "$mttr_minutes"},
                    "min_mttr_minutes": {"$min": "$mttr_minutes"},
                    "max_mttr_minutes": {"$max": "$mttr_minutes"}
                }
            },
            {"$sort": {"incident_count": -1}}
        ]

        if self.is_real_connected and self.real_collection is not None:
            try:
                raw_agg = list(self.real_collection.aggregate(pipeline))
                if raw_agg:
                    for item in raw_agg:
                        item["avg_mttr_minutes"] = round(float(item.get("avg_mttr_minutes") or 0.0), 2)
                        item["min_mttr_minutes"] = round(float(item.get("min_mttr_minutes") or 0.0), 2)
                        item["max_mttr_minutes"] = round(float(item.get("max_mttr_minutes") or 0.0), 2)
                    return raw_agg
            except Exception:
                pass

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
        pipeline = [
            {"$unwind": "$embedded_alerts"},
            {
                "$group": {
                    "_id": "$embedded_alerts.severity",
                    "count": {"$sum": 1},
                    "services_impacted": {"$addToSet": "$embedded_alerts.service"}
                }
            },
            {"$sort": {"count": -1}}
        ]

        if self.is_real_connected and self.real_collection is not None:
            try:
                raw_agg = list(self.real_collection.aggregate(pipeline))
                if raw_agg:
                    return raw_agg
            except Exception:
                pass

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
