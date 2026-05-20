"""API integration tests — agents, events, and trust score endpoints."""

import hashlib
import uuid
from datetime import datetime, timezone

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from agentsentinel.models.agent import Agent
from agentsentinel.models.baseline import Baseline
from agentsentinel.models.event import AgentEvent


def sha256(s: str) -> str:
    return hashlib.sha256(s.encode()).hexdigest()


# ── POST /api/v1/agents ───────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_create_agent_returns_201(client: AsyncClient):
    response = await client.post("/api/v1/agents", json={
        "name": "my-agent",
        "agent_type": "llm_agent",
        "model": "claude-sonnet-4-6",
        "owner_team": "platform",
        "description": "A test agent",
    })
    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "my-agent"
    assert "id" in data
    assert data["status"] == "WATCH"


@pytest.mark.asyncio
async def test_create_agent_minimal_fields(client: AsyncClient):
    response = await client.post("/api/v1/agents", json={
        "name": "minimal",
        "agent_type": "rag_agent",
        "model": "gpt-4o",
        "owner_team": "ml-team",
    })
    assert response.status_code == 201
    assert response.json()["description"] is None


# ── GET /api/v1/agents ────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_list_agents_returns_list(client: AsyncClient):
    # Create two agents
    for i in range(2):
        await client.post("/api/v1/agents", json={
            "name": f"agent-{i}",
            "agent_type": "llm_agent",
            "model": "claude-sonnet-4-6",
            "owner_team": "security",
        })
    response = await client.get("/api/v1/agents")
    assert response.status_code == 200
    assert isinstance(response.json(), list)
    assert len(response.json()) >= 2


@pytest.mark.asyncio
async def test_list_agents_filter_by_status(client: AsyncClient, sample_agent: Agent):
    response = await client.get("/api/v1/agents?status=WATCH")
    assert response.status_code == 200
    statuses = [a["status"] for a in response.json()]
    assert all(s == "WATCH" for s in statuses)


# ── GET /api/v1/agents/{id} ───────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_get_agent_returns_404_for_unknown(client: AsyncClient):
    response = await client.get(f"/api/v1/agents/{uuid.uuid4()}")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_get_agent_returns_agent(client: AsyncClient, sample_agent: Agent):
    response = await client.get(f"/api/v1/agents/{sample_agent.id}")
    assert response.status_code == 200
    assert response.json()["id"] == str(sample_agent.id)


# ── POST /api/v1/events ───────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_ingest_event_returns_anomaly_score(client: AsyncClient, sample_agent: Agent):
    response = await client.post("/api/v1/events", json={
        "agent_id": str(sample_agent.id),
        "tool_name": "some_tool",
        "input_hash": sha256("test input"),
        "output_hash": sha256("test output"),
        "duration_ms": 42,
        "session_id": "session-001",
    })
    assert response.status_code == 201
    data = response.json()
    assert "event_id" in data
    assert "anomaly_score" in data
    assert 0.0 <= data["anomaly_score"] <= 1.0


@pytest.mark.asyncio
async def test_ingest_event_unknown_agent_returns_404(client: AsyncClient):
    response = await client.post("/api/v1/events", json={
        "agent_id": str(uuid.uuid4()),
        "tool_name": "tool",
        "input_hash": "a" * 64,
        "output_hash": "b" * 64,
    })
    assert response.status_code == 404


# ── GET /api/v1/agents/{id}/score ─────────────────────────────────────────────

@pytest.mark.asyncio
async def test_get_score_returns_trust_dict(client: AsyncClient, sample_agent: Agent):
    response = await client.get(f"/api/v1/agents/{sample_agent.id}/score")
    assert response.status_code == 200
    data = response.json()
    assert "trust_score" in data
    assert "posture_score" in data
    assert "behavior_score" in data
    assert "status" in data
    assert "findings_count" in data
    assert data["status"] in {"TRUSTED", "WATCH", "ALERT", "CRITICAL"}


@pytest.mark.asyncio
async def test_get_score_unknown_agent_returns_404(client: AsyncClient):
    response = await client.get(f"/api/v1/agents/{uuid.uuid4()}/score")
    assert response.status_code == 404
