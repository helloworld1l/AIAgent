"""
FastAPI service for conversational AI assistant.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Optional

import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel

from agents.crm_agent import CRMAgent
from agents.tools import list_supported_models
from config.settings import settings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class ChatRequest(BaseModel):
    message: str
    user_id: str = "default"
    session_id: str = "default"


class QueryRequest(BaseModel):
    question: str
    user_id: str = "default"
    session_id: str = "default"


class ApiResponse(BaseModel):
    success: bool
    message: str
    data: Optional[dict] = None


app = FastAPI(title="Conversational AI Assistant API", version="3.0.0")
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
    _ensure_agent()
    logger.info("Conversational AI assistant API started.")


def _ensure_agent() -> CRMAgent:
    global agent
    if agent is None:
        agent = CRMAgent()
    return agent


@app.get("/")
async def root():
    return {
        "service": "Conversational AI Assistant API",
        "version": "3.0.0",
        "routes": {
            "/ui": "web chat page",
            "/api/chat": "chat endpoint",
            "/api/query": "compat endpoint (same as chat)",
            "/api/models": "list MATLAB templates",
            "/api/health": "service health check",
            "/docs": "Swagger UI",
        },
    }


@app.get("/ui")
async def ui():
    project_root = Path(__file__).resolve().parent.parent
    return FileResponse(str(project_root / "web_ui.html"))


@app.get("/api/health")
async def health_check():
    runtime_agent = _ensure_agent()
    return {
        "status": "healthy",
        "agent_initialized": runtime_agent is not None,
        "session_store_backend": getattr(getattr(runtime_agent, "session_store", None), "backend_name", "unknown"),
    }


@app.get("/api/models")
async def models():
    return json.loads(list_supported_models())


@app.post("/api/chat", response_model=ApiResponse)
async def chat(request: ChatRequest):
    runtime_agent = _ensure_agent()
    if not request.message.strip():
        raise HTTPException(status_code=422, detail="message cannot be empty")

    result = runtime_agent.chat(
        message=request.message,
        user_id=request.user_id,
        session_id=request.session_id,
    )
    return ApiResponse(success=True, message=result.get("message", ""), data=result.get("data", {}))


@app.post("/api/query", response_model=ApiResponse)
async def query(request: QueryRequest):
    runtime_agent = _ensure_agent()
    if not request.question.strip():
        raise HTTPException(status_code=422, detail="question cannot be empty")

    result = runtime_agent.process_query(
        question=request.question,
        user_id=request.user_id,
        session_id=request.session_id,
    )
    return ApiResponse(success=True, message=result.get("message", ""), data=result.get("data", {}))


def run_server():
    uvicorn.run(app, host=settings.API_HOST, port=settings.API_PORT)


if __name__ == "__main__":
    run_server()
