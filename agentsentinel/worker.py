"""Background worker — recomputes baselines for all active agents every 5 minutes."""

import asyncio
from datetime import datetime, timedelta, timezone

import structlog
from sqlalchemy import func, select

from agentsentinel.behavior.baseline import compute_baseline
from agentsentinel.database import AsyncSessionLocal
from agentsentinel.models.agent import ToolGrant
from agentsentinel.models.event import AgentEvent

log = structlog.get_logger(__name__)

INTERVAL_SECONDS = 300  # 5 minutes


async def _refresh_grant_counts(db) -> None:
    """Recalculate call_count_7d for all ToolGrants from actual events in the last 7 days."""
    cutoff = datetime.now(tz=timezone.utc) - timedelta(days=7)

    count_result = await db.execute(
        select(AgentEvent.agent_id, AgentEvent.tool_name, func.count().label("cnt"))
        .where(AgentEvent.timestamp >= cutoff)
        .group_by(AgentEvent.agent_id, AgentEvent.tool_name)
    )
    count_map = {(row.agent_id, row.tool_name): row.cnt for row in count_result.all()}

    grants_result = await db.execute(select(ToolGrant))
    updated = 0
    for grant in grants_result.scalars().all():
        new_count = count_map.get((grant.agent_id, grant.tool_name), 0)
        if grant.call_count_7d != new_count:
            grant.call_count_7d = new_count
            updated += 1

    log.info("worker.grant_counts_refreshed", updated=updated)


async def run_once() -> None:
    """Compute baselines for all agent+tool pairs seen in the last 7 days."""
    async with AsyncSessionLocal() as db:
        try:
            result = await db.execute(
                select(AgentEvent.agent_id, AgentEvent.tool_name).distinct()
            )
            pairs = result.all()
            log.info("worker.baseline_run_start", pair_count=len(pairs))

            for agent_id, tool_name in pairs:
                try:
                    await compute_baseline(agent_id, tool_name, db)
                except Exception as exc:
                    log.warning(
                        "worker.baseline_error",
                        agent_id=str(agent_id),
                        tool_name=tool_name,
                        error=str(exc),
                        exc_info=True,
                    )

            await _refresh_grant_counts(db)
            await db.commit()
            log.info("worker.baseline_run_complete", pair_count=len(pairs))
        except Exception as exc:
            # Explicit rollback ensures no partial writes persist across the failure
            await db.rollback()
            log.error("worker.run_failed", error=str(exc), exc_info=True)


async def main() -> None:
    """Run the baseline computation loop indefinitely."""
    log.info("worker.started", interval_seconds=INTERVAL_SECONDS)
    while True:
        await run_once()
        await asyncio.sleep(INTERVAL_SECONDS)


if __name__ == "__main__":
    asyncio.run(main())
