"""Baseline builder — computes rolling hourly call-rate statistics per agent+tool."""

import math
import uuid
from datetime import datetime, timedelta, timezone

import structlog
from sqlalchemy import func, select, text
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

    Queries the last ``window_days`` of AgentEvent rows, buckets by hour,
    then computes mean and stddev. Upserts the result into the Baseline table.
    """
    since = datetime.now(tz=timezone.utc) - timedelta(days=window_days)

    # Fetch all events for this agent+tool in the window
    result = await db.execute(
        select(AgentEvent.timestamp).where(
            AgentEvent.agent_id == agent_id,
            AgentEvent.tool_name == tool_name,
            AgentEvent.timestamp >= since,
        )
    )
    timestamps = [row[0] for row in result.all()]

    if not timestamps:
        counts_per_hour: list[int] = []
    else:
        # Build a map of hour → count
        hour_counts: dict[datetime, int] = {}
        for ts in timestamps:
            bucket = ts.replace(minute=0, second=0, microsecond=0)
            hour_counts[bucket] = hour_counts.get(bucket, 0) + 1
        counts_per_hour = list(hour_counts.values())

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
