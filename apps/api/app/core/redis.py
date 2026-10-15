"""Redis client and rate limiting. Owner: Lead (E3, used by E11 and E14)."""

from typing import Annotated

from fastapi import Depends
from redis.asyncio import Redis

from app.core.config import settings

_client: Redis | None = None


def get_redis() -> Redis:
    """The shared Redis client. Tests override this dependency with fakeredis."""
    global _client
    if _client is None:
        _client = Redis.from_url(settings.redis_url, decode_responses=True)
    return _client


RedisDep = Annotated[Redis, Depends(get_redis)]


async def hit_fixed_window(redis: Redis, key: str, limit: int, window_s: int) -> bool:
    """Count one hit in a fixed window. Returns False once more than `limit` hits."""
    async with redis.pipeline(transaction=True) as pipe:
        pipe.incr(key)
        pipe.expire(key, window_s, nx=True)
        count, _ = await pipe.execute()
    return int(count) <= limit


async def claim_cooldown(redis: Redis, key: str, cooldown_s: int) -> bool:
    """Take a cooldown slot. Returns False while a previous claim is still active."""
    return bool(await redis.set(key, "1", nx=True, ex=cooldown_s))


async def cooldown_left_s(redis: Redis, key: str) -> int:
    return max(int(await redis.ttl(key)), 0)
