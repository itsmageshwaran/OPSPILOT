from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from typing import Dict, Any
from app.database.session import get_db
from app.topology.graph import dependency_graph

router = APIRouter(prefix="/api", tags=["Topology"])

@router.get("/topology")
def get_topology():
    """Returns the current NetworkX dependency graph model."""
    return dependency_graph.to_dict()
