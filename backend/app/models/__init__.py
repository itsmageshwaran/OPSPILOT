"""
OpsPilot Domain Models & MongoDB NoSQL Knowledge Base Layer.

This module provides:
1. Core Telemetry & Relational Models (Alert, Metric, LogEvent, SystemEvent, Service, Dependency)
2. MongoDB CRUD Operations (create, read, update, delete)
3. Embedding vs Referencing Relationships (EmbeddedAlert, EmbeddedTimelineStep vs referenced services/audits)
4. MongoDB Aggregation Pipelines ($match, $group, $sort, $unwind)
5. MongoDB Indexing for Query Performance (Compound indexes, unique indexes, multikey tag indexes)
"""

import os
from typing import List, Optional, Dict, Any
from datetime import datetime, timezone
from pydantic import BaseModel, Field

# Core relational and telemetry schemas
from .alert import Alert
from .metric import Metric
from .log_event import LogEvent
from .system_event import SystemEvent
from .service import Service
from .dependency import Dependency


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ==============================================================================
# MongoDB NoSQL Models, CRUD Primitives & Aggregation Pipelines
# ==============================================================================
from .mongo import (
    EmbeddedAlert,
    EmbeddedTimelineStep,
    PostMortemDocument,
    MongoIncidentKnowledgeBase,
    mongo_kb,
    insert_one,
    insert_many,
    find_one,
    find,
    update_one,
    update_many,
    delete_one,
    delete_many,
    aggregate,
    create_index,
)

__all__ = [
    "Alert",
    "Metric",
    "LogEvent",
    "SystemEvent",
    "Service",
    "Dependency",
    # MongoDB NoSQL Models & Knowledge Base
    "EmbeddedAlert",
    "EmbeddedTimelineStep",
    "PostMortemDocument",
    "MongoIncidentKnowledgeBase",
    "mongo_kb",
    "insert_one",
    "insert_many",
    "find_one",
    "find",
    "update_one",
    "update_many",
    "delete_one",
    "delete_many",
    "aggregate",
    "create_index",
]
