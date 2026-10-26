"""Fan Redis pub/sub messages out to many live connections. Owner: Lead (E11, used by E14).

Each API process keeps ONE Redis subscription per channel pattern and hands every
message to all of its SSE listeners through small in-memory queues. 5,000
spectators on the live leaderboard therefore cost one Redis connection per API
process, not 5,000.

    async with broadcaster(redis, "scans").listen("scans") as messages:
        async for data in messages:   # dicts, published as JSON
            ...

A listener that can't keep up (slow phone connection) misses messages instead of
slowing everyone else down. The pages re-fetch the full state anyway.
"""

import asyncio
import contextlib
import json
import logging
import weakref
from collections.abc import AsyncIterator
from typing import Any

from redis.asyncio import Redis

log = logging.getLogger("ekitirun.broadcast")
QUEUE_SIZE = 100
RECONNECT_DELAY_S = 2.0


async def publish(redis: Redis, channel: str, data: dict[str, Any]) -> None:
    await redis.publish(channel, json.dumps(data, default=str))


class Broadcaster:
    def __init__(self, redis: Redis, pattern: str) -> None:
        self.redis = redis
        self.pattern = pattern  # e.g. "scans", or "positions:*" for one channel per runner
        self.listeners: dict[str, set[asyncio.Queue[dict[str, Any]]]] = {}
        self.task: asyncio.Task[None] | None = None

    @contextlib.asynccontextmanager
    async def listen(self, channel: str) -> AsyncIterator[AsyncIterator[dict[str, Any]]]:
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=QUEUE_SIZE)
        self.listeners.setdefault(channel, set()).add(queue)
        if self.task is None or self.task.done():
            ready = asyncio.Event()
            self.task = asyncio.create_task(self._run(ready))
            await ready.wait()  # subscribed before the caller relies on it

        async def messages() -> AsyncIterator[dict[str, Any]]:
            while True:
                yield await queue.get()

        try:
            yield messages()
        finally:
            group = self.listeners.get(channel, set())
            group.discard(queue)
            if not group:
                self.listeners.pop(channel, None)
            if not self.listeners and self.task is not None:
                self.task.cancel()  # nobody left listening: drop the Redis subscription
                self.task = None

    def _deliver(self, channel: str, data: dict[str, Any]) -> None:
        for queue in list(self.listeners.get(channel, ())):
            try:
                queue.put_nowait(data)
            except asyncio.QueueFull:
                pass  # this listener is too slow: it misses this message

    async def _run(self, ready: asyncio.Event) -> None:
        while True:
            try:
                async with self.redis.pubsub() as pubsub:
                    await pubsub.psubscribe(self.pattern)
                    ready.set()
                    async for message in pubsub.listen():
                        if message.get("type") != "pmessage":
                            continue
                        try:
                            data = json.loads(message["data"])
                        except (TypeError, ValueError):
                            continue
                        self._deliver(str(message["channel"]), data)
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # Redis restarted or the network blipped: resubscribe
                ready.set()
                log.warning("Pub/sub on %s lost (%s); reconnecting", self.pattern, exc)
                await asyncio.sleep(RECONNECT_DELAY_S)


_broadcasters: "weakref.WeakKeyDictionary[Redis, dict[str, Broadcaster]]" = (
    weakref.WeakKeyDictionary()
)


def broadcaster(redis: Redis, pattern: str) -> Broadcaster:
    """The process-wide broadcaster for this Redis client and pattern."""
    per_client = _broadcasters.setdefault(redis, {})
    if pattern not in per_client:
        per_client[pattern] = Broadcaster(redis, pattern)
    return per_client[pattern]
