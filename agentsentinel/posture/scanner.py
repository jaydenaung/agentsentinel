"""Posture scanner — orchestrates posture rules and persists findings."""

import uuid

import structlog
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from agentsentinel.alerts.slack import send_critical_alert
from agentsentinel.models.agent import Agent, McpConnection, ToolGrant
from agentsentinel.models.finding import Finding
from agentsentinel.posture.rules import run_all_rules
from agentsentinel.posture.scoring import calculate_posture_score

log = structlog.get_logger(__name__)


async def run_posture_scan(agent_id: uuid.UUID, db: AsyncSession) -> int:
    """Run all posture rules for an agent, persist new findings, return posture score."""
    agent = await db.get(Agent, agent_id)
    if agent is None:
        log.warning("posture_scan.agent_not_found", agent_id=str(agent_id))
        return 0

    grants_result = await db.execute(select(ToolGrant).where(ToolGrant.agent_id == agent_id))
    grants = list(grants_result.scalars().all())

    connections_result = await db.execute(
        select(McpConnection).where(McpConnection.agent_id == agent_id)
    )
    connections = list(connections_result.scalars().all())

    findings = run_all_rules(agent, grants, connections)

    # Replace existing OPEN posture findings with fresh scan results
    await db.execute(
        delete(Finding).where(
            Finding.agent_id == agent_id,
            Finding.finding_type == "POSTURE",
            Finding.status == "OPEN",
        )
    )
    for f in findings:
        db.add(f)
    await db.flush()  # make findings visible to subsequent queries in this session

    score = calculate_posture_score(findings)
    log.info("posture_scan.complete", agent_id=str(agent_id), score=score, findings=len(findings))

    for f in findings:
        if f.severity == "CRITICAL":
            await send_critical_alert(f, agent.name)

    return score
