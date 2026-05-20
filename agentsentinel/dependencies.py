"""Shared FastAPI dependencies (Redis, etc.)."""

from collections.abc import AsyncGenerator

from redis.asyncio import Redis

from agentsentinel.config import settings

_redis_client: Redis | None = None


async def get_redis() -> AsyncGenerator[Redis, None]:
    """Yield a shared Redis client instance."""
    global _redis_client
    if _redis_client is None:
        _redis_client = Redis.from_url(settings.redis_url, decode_responses=True)
    yield _redis_client
