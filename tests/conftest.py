"""Shared pytest fixtures for AgentSentinel tests."""

import os

# Must be set before importing agentsentinel modules so that Settings() does not raise
# when SECRET_KEY is the insecure default (acceptable in the test environment only).
os.environ.setdefault("SENTINEL_ALLOW_WEAK_SECRET", "true")

import uuid
from collections.abc import AsyncGenerator
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from agentsentinel.auth import generate_raw_key, hash_key, key_prefix
from agentsentinel.main import app
from agentsentinel.models import Base
from agentsentinel.models.agent import Agent, McpConnection, ToolGrant
from agentsentinel.models.api_key import ApiKey
from agentsentinel.models.baseline import Baseline
from agentsentinel.models.event import AgentEvent

# SQLite in-memory for unit tests (no TimescaleDB dependency)
TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"


@pytest_asyncio.fixture
async def engine():
    """Create an in-memory SQLite engine and apply the schema."""
    _engine = create_async_engine(TEST_DATABASE_URL, echo=False)
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield _engine
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await _engine.dispose()


@pytest_asyncio.fixture
async def db(engine) -> AsyncGenerator[AsyncSession, None]:
    """Yield an async database session bound to the in-memory engine."""
    session_factory = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as session:
        yield session


@pytest_asyncio.fixture
async def sample_agent(db: AsyncSession) -> Agent:
    """Create and persist a basic agent for use in tests."""
    agent = Agent(
        id=uuid.uuid4(),
        name="test-agent",
        agent_type="llm_agent",
        model="claude-sonnet-4-6",
        owner_team="security",
        description="A test agent for read queries and view operations",
        status="WATCH",
    )
    db.add(agent)
    await db.commit()
    await db.refresh(agent)
    return agent


@pytest_asyncio.fixture
async def admin_api_key(db: AsyncSession) -> str:
    """Create a test admin API key and return the plaintext value."""
    raw = generate_raw_key("admin")
    key = ApiKey(
        id=uuid.uuid4(),
        name="test-admin",
        key_prefix=key_prefix(raw),
        key_hash=hash_key(raw),
        scope="admin",
        agent_id=None,
        is_active=True,
    )
    db.add(key)
    await db.commit()
    return raw


@pytest_asyncio.fixture
async def client(db: AsyncSession, admin_api_key: str):
    """Async test client with the DB dependency overridden and auth header set."""
    from agentsentinel.database import get_db
    from agentsentinel.dependencies import get_redis

    async def override_db():
        yield db

    mock_redis = AsyncMock()
    mock_redis.xadd = AsyncMock(return_value=b"1-0")

    async def override_redis():
        yield mock_redis

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_redis] = override_redis

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        headers={"X-API-Key": admin_api_key},
    ) as c:
        yield c

    app.dependency_overrides.clear()
