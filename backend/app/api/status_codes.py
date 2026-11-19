"""
HTTP Status Codes Reference & Demonstrator for OpsPilot.
Demonstrates correct semantic usage of standard RESTful HTTP status codes:
- 200 OK: Successful GET/PATCH/PUT operation
- 201 CREATED: Resource created successfully via POST
- 204 NO CONTENT: Successful deletion with empty response body
- 400 BAD REQUEST: Malformed input syntax or payload validation failure
- 401 UNAUTHORIZED: Missing or invalid authentication token
- 403 FORBIDDEN: Valid authentication but insufficient permissions
- 404 NOT FOUND: Target resource does not exist
- 413 REQUEST ENTITY TOO LARGE: Upload payload exceeds size quota
- 422 UNPROCESSABLE ENTITY: Semantic validation error (Pydantic validation)
- 500 INTERNAL SERVER ERROR: Unhandled server-side fault
"""

from fastapi import APIRouter, Response, HTTPException, status
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api/status-codes", tags=["HTTP Status Codes Reference"])


class DummyEntity(BaseModel):
    name: str = Field(..., min_length=2)
    value: int = Field(..., gt=0)


@router.get("/ok", status_code=status.HTTP_200_OK)
def status_200_ok():
    """200 OK: Standard successful response for GET request."""
    return {"status_code": 200, "message": "Resource retrieved successfully"}


@router.post("/created", status_code=status.HTTP_201_CREATED)
def status_201_created(entity: DummyEntity):
    """201 CREATED: Resource created successfully via POST."""
    return {"status_code": 201, "message": "Resource created", "entity": entity.model_dump()}


@router.delete("/no-content/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
def status_204_no_content(item_id: str):
    """204 NO CONTENT: Resource successfully deleted with empty body."""
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/bad-request", status_code=status.HTTP_400_BAD_REQUEST)
def status_400_bad_request():
    """400 BAD REQUEST: Malformed input syntax or invalid query parameters."""
    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail="Malformed query parameter or invalid format"
    )


@router.get("/unauthorized", status_code=status.HTTP_401_UNAUTHORIZED)
def status_401_unauthorized():
    """401 UNAUTHORIZED: Missing or invalid JWT credentials."""
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Valid Bearer JWT token required to access this resource",
        headers={"WWW-Authenticate": "Bearer"}
    )


@router.get("/forbidden", status_code=status.HTTP_403_FORBIDDEN)
def status_403_forbidden():
    """403 FORBIDDEN: Insufficient role permissions or CSRF/Signature mismatch."""
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="User does not have permission to execute this administrative action"
    )


@router.get("/not-found/{item_id}", status_code=status.HTTP_404_NOT_FOUND)
def status_404_not_found(item_id: str):
    """404 NOT FOUND: Requested entity does not exist."""
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"Resource '{item_id}' not found"
    )
