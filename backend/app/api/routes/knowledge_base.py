"""
FastAPI Routes for NoSQL (MongoDB) Knowledge Base & Aggregation Pipelines.
Demonstrates:
- CRUD endpoints (Create, Read, Update, Delete)
- Embedding vs Referencing schema representation
- Indexing metadata introspection
- Aggregation Pipeline analytics execution
"""

from typing import List, Dict, Any, Optional
from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, Field

from app.models.mongo import (
    PostMortemDocument,
    EmbeddedAlert,
    EmbeddedTimelineStep,
    mongo_kb,
)

router = APIRouter(prefix="/api/knowledge-base", tags=["MongoDB Knowledge Base"])


class PostMortemCreateRequest(BaseModel):
    incident_id: str
    title: str
    summary: str
    root_cause_service: str
    referenced_audit_ids: List[str] = Field(default_factory=list)
    referenced_service_ids: List[str] = Field(default_factory=list)
    embedded_alerts: List[EmbeddedAlert] = Field(default_factory=list)
    embedded_timeline: List[EmbeddedTimelineStep] = Field(default_factory=list)
    duration_seconds: float = 0.0
    mttr_minutes: float = 0.0
    tags: List[str] = Field(default_factory=list)
    status: str = "RESOLVED"


class PostMortemUpdateRequest(BaseModel):
    title: Optional[str] = None
    summary: Optional[str] = None
    mttr_minutes: Optional[float] = None
    tags: Optional[List[str]] = None
    status: Optional[str] = None


@router.post("/post-mortems", status_code=status.HTTP_201_CREATED)
def create_post_mortem(req: PostMortemCreateRequest):
    """CRUD - CREATE: Insert a new post-mortem document into MongoDB collection."""
    doc = PostMortemDocument(**req.model_dump())
    created = mongo_kb.create_post_mortem(doc)
    return {"message": "Document created successfully in MongoDB collection", "document": created}


@router.get("/post-mortems/{incident_id}")
def get_post_mortem(incident_id: str):
    """CRUD - READ: Fetch document using unique indexed incident_id."""
    doc = mongo_kb.get_post_mortem(incident_id)
    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Post-mortem document for incident '{incident_id}' not found."
        )
    return doc


@router.get("/post-mortems")
def find_post_mortems_by_service(
    service: str = Query(..., description="Root cause service to filter"),
    status: Optional[str] = Query(None, description="Optional status filter")
):
    """CRUD - READ: Query post-mortems using indexed compound key (root_cause_service, status)."""
    docs = mongo_kb.find_by_service(service=service, status=status)
    return {"count": len(docs), "documents": docs}


@router.patch("/post-mortems/{incident_id}")
def update_post_mortem(incident_id: str, req: PostMortemUpdateRequest):
    """CRUD - UPDATE: Update post-mortem with $set semantics."""
    updates = {k: v for k, v in req.model_dump().items() if v is not None}
    if not updates:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No fields provided for update")
    updated = mongo_kb.update_post_mortem(incident_id, updates)
    if not updated:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document with incident_id '{incident_id}' not found."
        )
    return {"message": "Document updated", "document": updated}


@router.delete("/post-mortems/{incident_id}")
def delete_post_mortem(incident_id: str):
    """CRUD - DELETE: Remove document from MongoDB collection."""
    deleted = mongo_kb.delete_post_mortem(incident_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document with incident_id '{incident_id}' not found."
        )
    return {"message": f"Document '{incident_id}' deleted successfully"}


@router.get("/indexes")
def get_mongo_indexes():
    """List defined MongoDB query performance compound and multikey indexes."""
    return {"collection": "post_mortems", "indexes": mongo_kb.list_indexes()}


@router.get("/analytics/mttr-aggregation")
def get_mttr_aggregation_pipeline():
    """Execute MongoDB Aggregation Pipeline: $match -> $group (avg, min, max MTTR) -> $sort."""
    data = mongo_kb.aggregate_mttr_by_service()
    return {
        "pipeline_stages": ["$match (status=RESOLVED)", "$group (_id, avg_mttr, count)", "$sort"],
        "results": data
    }


@router.get("/analytics/alerts-distribution")
def get_alerts_distribution_aggregation():
    """Execute MongoDB Aggregation Pipeline with $unwind on embedded alerts."""
    data = mongo_kb.aggregate_alerts_unwind_distribution()
    return {
        "pipeline_stages": ["$unwind ($embedded_alerts)", "$group (by severity, $addToSet service)", "$sort"],
        "results": data
    }
