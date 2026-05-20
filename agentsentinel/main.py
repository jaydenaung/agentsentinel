"""FastAPI application entry point."""

from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from agentsentinel.api.agents import router as agents_router
from agentsentinel.api.events import router as events_router
from agentsentinel.api.findings import router as findings_router
from agentsentinel.api.keys import router as keys_router
from agentsentinel.api.scores import router as scores_router
from agentsentinel.auth import bootstrap_admin_key
from agentsentinel.config import settings
from agentsentinel.database import AsyncSessionLocal

structlog.configure(
    processors=[
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.stdlib.add_log_level,
        structlog.processors.JSONRenderer(),
    ]
)

log = structlog.get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Run startup tasks before the server begins accepting requests."""
    async with AsyncSessionLocal() as db:
        await bootstrap_admin_key(db)
    yield


app = FastAPI(
    title="AgentSentinel",
    description="Enterprise AI agent security platform — posture + behavior monitoring",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_methods=["GET", "POST", "PATCH", "DELETE"],
    allow_headers=["*"],
)

API_PREFIX = "/api/v1"
app.include_router(agents_router, prefix=API_PREFIX)
app.include_router(events_router, prefix=API_PREFIX)
app.include_router(findings_router, prefix=API_PREFIX)
app.include_router(scores_router, prefix=API_PREFIX)
app.include_router(keys_router, prefix=API_PREFIX)


@app.get("/health")
async def health() -> dict:
    """Liveness probe."""
    return {"status": "ok"}
