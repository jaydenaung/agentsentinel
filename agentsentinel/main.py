"""FastAPI application entry point."""

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from agentsentinel.api.agents import router as agents_router
from agentsentinel.api.events import router as events_router
from agentsentinel.api.findings import router as findings_router
from agentsentinel.api.scores import router as scores_router

structlog.configure(
    processors=[
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.stdlib.add_log_level,
        structlog.processors.JSONRenderer(),
    ]
)

log = structlog.get_logger(__name__)

app = FastAPI(
    title="AgentSentinel",
    description="Enterprise AI agent security platform — posture + behavior monitoring",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

API_PREFIX = "/api/v1"
app.include_router(agents_router, prefix=API_PREFIX)
app.include_router(events_router, prefix=API_PREFIX)
app.include_router(findings_router, prefix=API_PREFIX)
app.include_router(scores_router, prefix=API_PREFIX)


@app.get("/health")
async def health() -> dict:
    """Liveness probe."""
    return {"status": "ok"}
