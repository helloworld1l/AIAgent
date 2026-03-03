"""
FastAPI service for MATLAB model generation.
"""

from __future__ import annotations

import json
import logging
from typing import Optional

import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from agents.crm_agent import CRMAgent
from agents.tools import list_supported_models
from config.settings import settings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class QueryRequest(BaseModel):
    question: str
    user_id: str = "default"
    session_id: str = "default"


class QueryResponse(BaseModel):
    success: bool
    message: str
    data: Optional[dict] = None


app = FastAPI(title="MATLAB Model Generator API", version="2.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

agent: Optional[CRMAgent] = None


@app.on_event("startup")
async def startup_event():
    global agent
    agent = CRMAgent()
    logger.info("MATLAB model generation API started.")


@app.get("/")
async def root():
    return {
        "service": "MATLAB Model Generator API",
        "version": "2.0.0",
        "routes": {
            "/api/query": "Generate MATLAB .m file from natural language description",
            "/api/models": "List supported model templates",
            "/api/health": "Service health check",
            "/docs": "Swagger UI",
        },
    }


@app.get("/api/health")
async def health_check():
    return {"status": "healthy", "agent_initialized": agent is not None}


@app.get("/api/models")
async def models():
    return json.loads(list_supported_models())


@app.post("/api/query", response_model=QueryResponse)
async def query(request: QueryRequest):
    if agent is None:
        raise HTTPException(status_code=503, detail="Agent is not initialized.")
    if not request.question.strip():
        raise HTTPException(status_code=422, detail="question cannot be empty")

    result = agent.process_query(
        question=request.question,
        user_id=request.user_id,
        session_id=request.session_id,
    )
    return QueryResponse(success=True, message=result.get("message", ""), data=result.get("data", {}))


def run_server():
    uvicorn.run(app, host=settings.API_HOST, port=settings.API_PORT)


if __name__ == "__main__":
    run_server()
