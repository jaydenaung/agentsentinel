"""Trust score endpoint — triggers a full recompute and returns results."""

import uuid
from typing import Annotated

import structlog
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from agentsentinel.auth import require_read
from agentsentinel.database import get_db
from agentsentinel.models.agent import Agent
from agentsentinel.trust.engine import compute_trust_score

router = APIRouter(tags=["scores"])
log = structlog.get_logger(__name__)


@router.get("/agents/{agent_id}/score", dependencies=[Depends(require_read)])
async def get_trust_score(
    agent_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    """Trigger a full trust score recompute and return the result."""
    agent = await db.get(Agent, agent_id)
    if agent is None:
        raise HTTPException(status_code=404, detail="Agent not found")

    result = await compute_trust_score(agent_id, db)
    log.info("score.requested", agent_id=str(agent_id), trust_score=result["trust_score"])
    return result
