"""Shared FastAPI dependencies (Redis, etc.)."""

import asyncio
from collections.abc import AsyncGenerator

from redis.asyncio import Redis

from agentsentinel.config import settings

_redis_client: Redis | None = None
_redis_init_lock = asyncio.Lock()


async def get_redis() -> AsyncGenerator[Redis, None]:
    """Yield a shared Redis client instance.

    Uses double-checked locking so that concurrent coroutines racing at startup
    do not create multiple connections — asyncio does not protect global mutation
    across await points without an explicit lock.
    """
    global _redis_client
    if _redis_client is None:
        async with _redis_init_lock:
            if _redis_client is None:
                _redis_client = Redis.from_url(settings.redis_url, decode_responses=True)
    yield _redis_client
