"""Findings endpoints — list and update security findings."""

import uuid
from datetime import datetime, timezone
from typing import Annotated

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from agentsentinel.database import get_db
from agentsentinel.models.finding import Finding
from agentsentinel.schemas.finding import FindingResponse, FindingStatusUpdate

router = APIRouter(tags=["findings"])
log = structlog.get_logger(__name__)

_VALID_STATUSES = {"OPEN", "ACKNOWLEDGED", "RESOLVED"}


@router.get("/agents/{agent_id}/findings", response_model=list[FindingResponse])
async def list_findings(
    agent_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
    status: Annotated[str | None, Query()] = None,
    severity: Annotated[str | None, Query()] = None,
) -> list[Finding]:
    """List all findings for an agent, optionally filtered by status and severity."""
    stmt = select(Finding).where(Finding.agent_id == agent_id)
    if status:
        stmt = stmt.where(Finding.status == status)
    if severity:
        stmt = stmt.where(Finding.severity == severity)
    stmt = stmt.order_by(Finding.created_at.desc())
    result = await db.execute(stmt)
    return list(result.scalars().all())


@router.patch("/findings/{finding_id}", response_model=FindingResponse)
async def update_finding_status(
    finding_id: uuid.UUID,
    body: FindingStatusUpdate,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Finding:
    """Acknowledge or resolve a finding."""
    if body.status not in _VALID_STATUSES:
        raise HTTPException(status_code=422, detail=f"status must be one of {_VALID_STATUSES}")
    finding = await db.get(Finding, finding_id)
    if finding is None:
        raise HTTPException(status_code=404, detail="Finding not found")
    finding.status = body.status
    if body.status == "RESOLVED":
        finding.resolved_at = datetime.now(tz=timezone.utc)
    log.info("finding.updated", finding_id=str(finding_id), status=body.status)
    return finding
