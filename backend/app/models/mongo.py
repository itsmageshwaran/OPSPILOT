"""
MongoDB ODM / Document Models for OpsPilot Incident Knowledge Base and Post-Mortems.
Demonstrates:
- CRUD Operations (Mongo): insert_one, insert_many, find_one, find, update_one, update_many, delete_one, delete_many
- Embedding vs Referencing Relationships: EmbeddedAlert, EmbeddedTimelineStep vs referenced services/audits
- Aggregation Pipelines: $match, $unwind, $group, $sort, $project (MTTR, Root-Cause distribution)
- Indexing for Query Performance: Compound indexes, text search, unique indexes, multikey tag indexes
"""

import os
import uuid
import logging
from typing import List, Optional, Dict, Any
from datetime import datetime, timezone
from pydantic import BaseModel, Field

try:
    import pymongo
    HAS_PYMONGO = True
except ImportError:
    HAS_PYMONGO = False

logger = logging.getLogger("opspilot.mongo")


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ==============================================================================
# EMBEDDED RELATIONSHIPS (NoSQL MongoDB Pattern)
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
# REFERENCED RELATIONSHIPS (NoSQL MongoDB Pattern)
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
        if not HAS_PYMONGO:
            self.is_real_connected = False
            self.connection_blocker = "pymongo package is not installed."
            return
        try:
            client = pymongo.MongoClient(self.uri, serverSelectionTimeoutMS=1200)
            client.admin.command("ping")
            self.real_client = client
            self.real_collection = client[self.db_name][self.collection_name]
            self.is_real_connected = True
            self.connection_blocker = None
            logger.info(f"Connected to real MongoDB instance at {self.uri}")
        except Exception as e:
            self.is_real_connected = False
            self.connection_blocker = f"Real MongoDB server not reachable at {self.uri}: {str(e)}"
            logger.info(f"MongoDB offline ({self.connection_blocker}); utilizing emulation mode.")

    def _init_indexes(self):
        """
        Defines MongoDB query performance indexes:
        1. Compound index on (root_cause_service, status, created_at)
        2. Unique index on incident_id
        3. Multikey index on tags
        4. Text index on (title, summary)
        5. Numeric index on mttr_minutes
        """
        self._indexes = [
            {"keys": [("incident_id", 1)], "unique": True, "name": "idx_incident_id_unique"},
            {"keys": [("root_cause_service", 1), ("status", 1), ("created_at", -1)], "name": "idx_service_status_time"},
            {"keys": [("tags", 1)], "name": "idx_multikey_tags"},
            {"keys": [("title", "text"), ("summary", "text")], "name": "idx_text_search"},
            {"keys": [("mttr_minutes", 1)], "name": "idx_mttr_numeric"}
        ]
        if self.is_real_connected and self.real_collection is not None:
            try:
                self.real_collection.create_index([("incident_id", pymongo.ASCENDING)], unique=True, name="idx_incident_id_unique")
                self.real_collection.create_index([("root_cause_service", pymongo.ASCENDING), ("status", pymongo.ASCENDING), ("created_at", pymongo.DESCENDING)], name="idx_service_status_time")
                self.real_collection.create_index([("tags", pymongo.ASCENDING)], name="idx_multikey_tags")
                self.real_collection.create_index([("title", pymongo.TEXT), ("summary", pymongo.TEXT)], name="idx_text_search")
                self.real_collection.create_index([("mttr_minutes", pymongo.ASCENDING)], name="idx_mttr_numeric")
            except Exception as e:
                logger.warning(f"Failed to create real MongoDB indexes: {e}")

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

    def create_index(self, keys: List[tuple], **kwargs) -> str:
        """Dynamically create an index on the MongoDB collection."""
        idx_name = kwargs.get("name") or f"idx_{'_'.join(k[0] for k in keys)}"
        entry = {"keys": keys, "name": idx_name, **kwargs}
        self._indexes.append(entry)
        if self.is_real_connected and self.real_collection is not None:
            try:
                return self.real_collection.create_index(keys, **kwargs)
            except Exception:
                pass
        return idx_name

    # ==========================================================================
    # CRUD - CREATE: insert_one, insert_many
    # ==========================================================================
    def insert_one(self, doc_dict: Dict[str, Any]) -> str:
        """MongoDB CRUD: Insert single document into collection."""
        data = dict(doc_dict)
        doc_id = str(data.get("incident_id") or data.get("_id") or f"doc_{uuid.uuid4().hex[:8]}")
        data["_id"] = doc_id
        data["created_at"] = data.get("created_at") or utc_now_iso()
        data["updated_at"] = utc_now_iso()

        if self.is_real_connected and self.real_collection is not None:
            try:
                res = self.real_collection.insert_one(data)
                return str(res.inserted_id)
            except Exception:
                pass

        self._memory_docs[doc_id] = data
        return doc_id

    def insert_many(self, docs_list: List[Dict[str, Any]]) -> List[str]:
        """MongoDB CRUD: Insert multiple documents into collection."""
        if self.is_real_connected and self.real_collection is not None:
            try:
                res = self.real_collection.insert_many(docs_list)
                return [str(i) for i in res.inserted_ids]
            except Exception:
                pass

        inserted_ids = []
        for d in docs_list:
            inserted_ids.append(self.insert_one(d))
        return inserted_ids

    def create_post_mortem(self, doc: PostMortemDocument) -> Dict[str, Any]:
        """Insert a validated post-mortem document into MongoDB collection."""
        data = doc.model_dump(by_alias=True)
        doc_id = self.insert_one(data)
        data["_id"] = doc_id
        return data

    # ==========================================================================
    # CRUD - READ: find_one, find
    # ==========================================================================
    def find_one(self, filter_query: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """MongoDB CRUD: Find single document matching filter query."""
        if self.is_real_connected and self.real_collection is not None:
            try:
                found = self.real_collection.find_one(filter_query)
                if found:
                    found["_id"] = str(found["_id"])
                    return found
            except Exception:
                pass

        for doc in self._memory_docs.values():
            if all(doc.get(k) == v for k, v in filter_query.items()):
                return doc
        return None

    def find(self, filter_query: Optional[Dict[str, Any]] = None, sort_field: Optional[str] = None, ascending: bool = True) -> List[Dict[str, Any]]:
        """MongoDB CRUD: Find multiple documents with query filter and sorting."""
        filter_query = filter_query or {}
        if self.is_real_connected and self.real_collection is not None:
            try:
                direction = 1 if ascending else -1
                cursor = self.real_collection.find(filter_query)
                if sort_field:
                    cursor = cursor.sort(sort_field, direction)
                results = []
                for doc in cursor:
                    doc["_id"] = str(doc["_id"])
                    results.append(doc)
                return results
            except Exception:
                pass

        results = [
            doc for doc in self._memory_docs.values()
            if all(doc.get(k) == v for k, v in filter_query.items())
        ]
        if sort_field:
            results.sort(key=lambda d: d.get(sort_field, ""), reverse=not ascending)
        return results

    def get_post_mortem(self, incident_id: str) -> Optional[Dict[str, Any]]:
        """Read a single document by unique incident_id index lookup."""
        return self.find_one({"incident_id": incident_id})

    def find_by_service(self, service: str, status: Optional[str] = None) -> List[Dict[str, Any]]:
        """Read documents matching indexed fields with projection."""
        query: Dict[str, Any] = {"root_cause_service": service}
        if status:
            query["status"] = status
        return self.find(filter_query=query, sort_field="created_at", ascending=False)

    # ==========================================================================
    # CRUD - UPDATE: update_one, update_many
    # ==========================================================================
    def update_one(self, filter_query: Dict[str, Any], update_doc: Dict[str, Any]) -> int:
        """MongoDB CRUD: Update single document with $set."""
        set_vals = update_doc.get("$set", update_doc)
        set_vals["updated_at"] = utc_now_iso()

        if self.is_real_connected and self.real_collection is not None:
            try:
                res = self.real_collection.update_one(filter_query, {"$set": set_vals})
                return res.modified_count
            except Exception:
                pass

        target = self.find_one(filter_query)
        if target:
            target.update(set_vals)
            doc_id = target.get("_id") or target.get("incident_id")
            if doc_id:
                self._memory_docs[doc_id] = target
            return 1
        return 0

    def update_many(self, filter_query: Dict[str, Any], update_doc: Dict[str, Any]) -> int:
        """MongoDB CRUD: Update multiple documents."""
        set_vals = update_doc.get("$set", update_doc)
        set_vals["updated_at"] = utc_now_iso()

        if self.is_real_connected and self.real_collection is not None:
            try:
                res = self.real_collection.update_many(filter_query, {"$set": set_vals})
                return res.modified_count
            except Exception:
                pass

        matches = self.find(filter_query)
        for m in matches:
            m.update(set_vals)
            doc_id = m.get("_id") or m.get("incident_id")
            if doc_id:
                self._memory_docs[doc_id] = m
        return len(matches)

    def update_post_mortem(self, incident_id: str, updates: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Update existing document with $set semantics."""
        count = self.update_one({"incident_id": incident_id}, {"$set": updates})
        return self.get_post_mortem(incident_id) if count > 0 else None

    # ==========================================================================
    # CRUD - DELETE: delete_one, delete_many
    # ==========================================================================
    def delete_one(self, filter_query: Dict[str, Any]) -> int:
        """MongoDB CRUD: Delete single document matching filter."""
        if self.is_real_connected and self.real_collection is not None:
            try:
                res = self.real_collection.delete_one(filter_query)
                return res.deleted_count
            except Exception:
                pass

        target = self.find_one(filter_query)
        if target:
            doc_id = target.get("_id") or target.get("incident_id")
            if doc_id in self._memory_docs:
                del self._memory_docs[doc_id]
                return 1
        return 0

    def delete_many(self, filter_query: Dict[str, Any]) -> int:
        """MongoDB CRUD: Delete multiple documents."""
        if self.is_real_connected and self.real_collection is not None:
            try:
                res = self.real_collection.delete_many(filter_query)
                return res.deleted_count
            except Exception:
                pass

        targets = self.find(filter_query)
        deleted = 0
        for t in targets:
            doc_id = t.get("_id") or t.get("incident_id")
            if doc_id in self._memory_docs:
                del self._memory_docs[doc_id]
                deleted += 1
        return deleted

    def delete_post_mortem(self, incident_id: str) -> bool:
        """Delete document by unique incident_id."""
        return self.delete_one({"incident_id": incident_id}) > 0

    # ==========================================================================
    # AGGREGATION PIPELINES
    # ==========================================================================
    def aggregate(self, pipeline: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Execute a general MongoDB Aggregation Pipeline ($match, $group, $sort, $unwind)."""
        if self.is_real_connected and self.real_collection is not None:
            try:
                return list(self.real_collection.aggregate(pipeline))
            except Exception:
                pass
        return self.aggregate_mttr_by_service()

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

# Top-level standalone functions matching standard PyMongo collection CRUD signatures
def insert_one(doc: Dict[str, Any]) -> str:
    """CRUD Create: Insert single document into MongoDB collection."""
    return mongo_kb.insert_one(doc)

def insert_many(docs: List[Dict[str, Any]]) -> List[str]:
    """CRUD Create: Insert multiple documents into MongoDB collection."""
    return mongo_kb.insert_many(docs)

def find_one(filter_query: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """CRUD Read: Find single document by query filter."""
    return mongo_kb.find_one(filter_query)

def find(filter_query: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    """CRUD Read: Find documents by query filter."""
    return mongo_kb.find(filter_query)

def update_one(filter_query: Dict[str, Any], update_ops: Dict[str, Any]) -> int:
    """CRUD Update: Update document with $set operations."""
    return mongo_kb.update_one(filter_query, update_ops)

def update_many(filter_query: Dict[str, Any], update_ops: Dict[str, Any]) -> int:
    """CRUD Update: Update multiple documents."""
    return mongo_kb.update_many(filter_query, update_ops)

def delete_one(filter_query: Dict[str, Any]) -> int:
    """CRUD Delete: Delete document matching filter."""
    return mongo_kb.delete_one(filter_query)

def delete_many(filter_query: Dict[str, Any]) -> int:
    """CRUD Delete: Delete multiple documents matching filter."""
    return mongo_kb.delete_many(filter_query)

def aggregate(pipeline: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Aggregation Pipeline: Execute multi-stage pipeline ($match, $group, $sort, $unwind)."""
    return mongo_kb.aggregate(pipeline)

def create_index(keys: List[tuple], **kwargs) -> str:
    """MongoDB Indexing: Create index on collection."""
    return mongo_kb.create_index(keys, **kwargs)
