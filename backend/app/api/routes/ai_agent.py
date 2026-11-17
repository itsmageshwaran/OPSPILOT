from fastapi import APIRouter, Depends, HTTPException, Header, status
from sqlalchemy.orm import Session
from typing import Dict, Any, Optional

from app.database.session import get_db
from app.ai_tools.agent import (
    TOOL_DEFINITIONS,
    ToolCallExecutionRequest,
    ai_tool_executor
)

router = APIRouter(prefix="/api/ai", tags=["AI Function Calling & Tool Use"])

@router.get(
    "/tools/definitions",
    status_code=status.HTTP_200_OK,
    summary="Get OpenAI/Gemini compatible function calling schemas"
)
def get_tool_definitions():
    """
    Returns registered function calling tool specifications for LLM agent integration.
    """
    return {
        "status": "success",
        "tool_count": len(TOOL_DEFINITIONS),
        "tools": TOOL_DEFINITIONS
    }

@router.post(
    "/tools/execute",
    status_code=status.HTTP_200_OK,
    summary="Execute validated AI tool call with Safety Gate authorization"
)
def execute_ai_tool_call(
    request: ToolCallExecutionRequest,
    authorization: Optional[str] = Header(None),
    db: Session = Depends(get_db)
):
    """
    Executes an AI tool call with:
    1. Strict Pydantic argument parsing and validation
    2. Role-based authorization
    3. OpsPilot 10-rule Safety Gate policy check
    """
    caller_role = request.caller_role or "sre_admin"

    try:
        result = ai_tool_executor.execute(
            tool_name=request.tool_name,
            arguments=request.arguments,
            caller_role=caller_role,
            db=db
        )
        return result
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Argument validation failed: {str(e)}"
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Tool execution failed: {str(e)}"
        )
