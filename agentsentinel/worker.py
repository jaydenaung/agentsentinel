"""Background worker — recomputes baselines for all active agents every 5 minutes."""

import asyncio

import structlog
from sqlalchemy import select

from agentsentinel.behavior.baseline import compute_baseline
from agentsentinel.database import AsyncSessionLocal
from agentsentinel.models.agent import Agent
from agentsentinel.models.event import AgentEvent

log = structlog.get_logger(__name__)

INTERVAL_SECONDS = 300  # 5 minutes


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
                    )

            await db.commit()
            log.info("worker.baseline_run_complete", pair_count=len(pairs))
        except Exception as exc:
            log.error("worker.run_failed", error=str(exc))


async def main() -> None:
    """Run the baseline computation loop indefinitely."""
    log.info("worker.started", interval_seconds=INTERVAL_SECONDS)
    while True:
        await run_once()
        await asyncio.sleep(INTERVAL_SECONDS)


if __name__ == "__main__":
    asyncio.run(main())
