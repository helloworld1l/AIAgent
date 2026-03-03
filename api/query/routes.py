"""
Optional router module for MATLAB generator API.
"""

from __future__ import annotations

import json
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from agents.crm_agent import CRMAgent
from agents.tools import list_supported_models

router = APIRouter(prefix="/api", tags=["matlab-generator"])
agent: Optional[CRMAgent] = None


def set_agent(instance: CRMAgent):
    global agent
    agent = instance


class QueryRequest(BaseModel):
    question: str
    user_id: str = "default"
    session_id: str = "default"


@router.post("/query")
async def query(payload: QueryRequest):
    if agent is None:
        raise HTTPException(status_code=503, detail="Agent is not initialized")
    if not payload.question.strip():
        raise HTTPException(status_code=422, detail="question cannot be empty")
    result = agent.process_query(payload.question, payload.user_id, payload.session_id)
    return {"success": True, "message": result.get("message", ""), "data": result.get("data", {})}


@router.get("/models")
async def models():
    return json.loads(list_supported_models())

