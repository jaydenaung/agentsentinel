"""Baseline builder — computes rolling hourly call-rate statistics per agent+tool."""

import math
import uuid
from datetime import datetime, timedelta, timezone

import structlog
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from agentsentinel.models.baseline import Baseline
from agentsentinel.models.event import AgentEvent

log = structlog.get_logger(__name__)


async def compute_baseline(
    agent_id: uuid.UUID,
    tool_name: str,
    db: AsyncSession,
    window_days: int = 7,
) -> Baseline:
    """Compute or refresh the hourly call-rate baseline for an agent+tool pair.

    Aggregates event counts per hour in the database — never loads raw timestamps
    into Python memory, so memory usage is O(distinct hours) regardless of event volume.
    """
    since = datetime.now(tz=timezone.utc) - timedelta(days=window_days)

    # Push bucketing into the DB: one row per hour with its event count
    bucket_col = func.date_trunc("hour", AgentEvent.timestamp).label("hour")
    result = await db.execute(
        select(bucket_col, func.count().label("cnt"))
        .where(
            AgentEvent.agent_id == agent_id,
            AgentEvent.tool_name == tool_name,
            AgentEvent.timestamp >= since,
        )
        .group_by(bucket_col)
    )
    counts_per_hour = [row.cnt for row in result.all()]

    sample_count = len(counts_per_hour)
    mean = sum(counts_per_hour) / sample_count if sample_count else 0.0
    variance = (
        sum((x - mean) ** 2 for x in counts_per_hour) / sample_count if sample_count > 1 else 0.0
    )
    stddev = math.sqrt(variance)

    # Upsert baseline
    existing_result = await db.execute(
        select(Baseline).where(
            Baseline.agent_id == agent_id,
            Baseline.tool_name == tool_name,
        )
    )
    baseline = existing_result.scalar_one_or_none()

    if baseline is None:
        baseline = Baseline(
            agent_id=agent_id,
            tool_name=tool_name,
            mean_calls_per_hour=mean,
            stddev_calls_per_hour=stddev,
            sample_count=sample_count,
            window_days=window_days,
        )
        db.add(baseline)
    else:
        baseline.mean_calls_per_hour = mean
        baseline.stddev_calls_per_hour = stddev
        baseline.sample_count = sample_count
        baseline.window_days = window_days
        baseline.updated_at = datetime.now(tz=timezone.utc)

    log.info(
        "baseline.computed",
        agent_id=str(agent_id),
        tool_name=tool_name,
        mean=mean,
        stddev=stddev,
        samples=sample_count,
    )
    return baseline
