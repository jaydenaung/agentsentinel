"""Tests for the anomaly detector — novel calls, frequency, and normal cases."""

import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from agentsentinel.behavior.anomaly import score_event
from agentsentinel.models.baseline import Baseline
from agentsentinel.models.event import AgentEvent


def make_event(agent_id: uuid.UUID, tool_name: str = "test_tool") -> AgentEvent:
    """Build an AgentEvent without persisting it."""
    return AgentEvent(
        id=uuid.uuid4(),
        agent_id=agent_id,
        tool_name=tool_name,
        input_hash="a" * 64,
        output_hash="b" * 64,
        timestamp=datetime.now(tz=timezone.utc),
    )


@pytest.mark.asyncio
async def test_first_ever_call_scores_0_9(db: AsyncSession, sample_agent):
    """First-ever call to a tool should score 0.9 (no prior events exist)."""
    event = make_event(sample_agent.id, tool_name="brand_new_tool")
    # Don't persist the event — score_event queries for prior events
    score = await score_event(event, db)
    assert score == pytest.approx(0.9)


@pytest.mark.asyncio
async def test_no_baseline_scores_0_7(db: AsyncSession, sample_agent):
    """Call with prior events but no baseline should score 0.7."""
    # Insert a prior event so is_first_ever_call returns False
    prior = AgentEvent(
        id=uuid.uuid4(),
        agent_id=sample_agent.id,
        tool_name="known_tool",
        input_hash="a" * 64,
        output_hash="b" * 64,
        timestamp=datetime.now(tz=timezone.utc) - timedelta(hours=2),
    )
    db.add(prior)
    await db.commit()

    # No Baseline row → should score 0.7
    event = make_event(sample_agent.id, tool_name="known_tool")
    score = await score_event(event, db)
    assert score == pytest.approx(0.7)


@pytest.mark.asyncio
async def test_high_frequency_2sigma_scores_0_5(db: AsyncSession, sample_agent):
    """Call rate > mean + 2σ but ≤ mean + 3σ should score 0.5."""
    tool_name = "frequent_tool"

    # Insert a prior event (so it's not a first-ever call)
    prior = AgentEvent(
        id=uuid.uuid4(),
        agent_id=sample_agent.id,
        tool_name=tool_name,
        input_hash="a" * 64,
        output_hash="b" * 64,
        timestamp=datetime.now(tz=timezone.utc) - timedelta(days=3),
    )
    db.add(prior)

    # Baseline: mean=1, stddev=1 → 2σ threshold = 3, 3σ threshold = 4
    baseline = Baseline(
        agent_id=sample_agent.id,
        tool_name=tool_name,
        mean_calls_per_hour=1.0,
        stddev_calls_per_hour=1.0,
        sample_count=10,
    )
    db.add(baseline)
    await db.commit()

    # Insert 4 events in last hour (4 > mean+2σ=3 but 4 ≤ mean+3σ=4)
    for _ in range(4):
        db.add(AgentEvent(
            id=uuid.uuid4(),
            agent_id=sample_agent.id,
            tool_name=tool_name,
            input_hash="c" * 64,
            output_hash="d" * 64,
            timestamp=datetime.now(tz=timezone.utc) - timedelta(minutes=10),
        ))
    await db.commit()

    event = make_event(sample_agent.id, tool_name=tool_name)
    score = await score_event(event, db)
    assert score == pytest.approx(0.5)


@pytest.mark.asyncio
async def test_high_frequency_3sigma_scores_0_8(db: AsyncSession, sample_agent):
    """Call rate > mean + 3σ should score 0.8."""
    tool_name = "very_frequent_tool"

    prior = AgentEvent(
        id=uuid.uuid4(),
        agent_id=sample_agent.id,
        tool_name=tool_name,
        input_hash="a" * 64,
        output_hash="b" * 64,
        timestamp=datetime.now(tz=timezone.utc) - timedelta(days=3),
    )
    db.add(prior)

    # mean=1, stddev=1 → 3σ threshold = 4; insert 5 events in last hour
    baseline = Baseline(
        agent_id=sample_agent.id,
        tool_name=tool_name,
        mean_calls_per_hour=1.0,
        stddev_calls_per_hour=1.0,
        sample_count=10,
    )
    db.add(baseline)
    await db.commit()

    for _ in range(5):
        db.add(AgentEvent(
            id=uuid.uuid4(),
            agent_id=sample_agent.id,
            tool_name=tool_name,
            input_hash="c" * 64,
            output_hash="d" * 64,
            timestamp=datetime.now(tz=timezone.utc) - timedelta(minutes=5),
        ))
    await db.commit()

    event = make_event(sample_agent.id, tool_name=tool_name)
    score = await score_event(event, db)
    assert score == pytest.approx(0.8)


@pytest.mark.asyncio
async def test_normal_call_scores_0(db: AsyncSession, sample_agent):
    """A call within the baseline range should score 0.0."""
    tool_name = "normal_tool"

    # Prior event (not first-ever)
    prior = AgentEvent(
        id=uuid.uuid4(),
        agent_id=sample_agent.id,
        tool_name=tool_name,
        input_hash="a" * 64,
        output_hash="b" * 64,
        timestamp=datetime.now(tz=timezone.utc) - timedelta(days=1),
    )
    db.add(prior)

    # mean=10, stddev=2 → 2σ threshold = 14; only 1 call in last hour
    baseline = Baseline(
        agent_id=sample_agent.id,
        tool_name=tool_name,
        mean_calls_per_hour=10.0,
        stddev_calls_per_hour=2.0,
        sample_count=20,
    )
    db.add(baseline)
    await db.commit()

    event = make_event(sample_agent.id, tool_name=tool_name)
    score = await score_event(event, db)
    assert score == pytest.approx(0.0)
