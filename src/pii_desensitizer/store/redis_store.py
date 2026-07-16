# src/pii_desensitizer/store/redis_store.py
"""Redis-backed mapping store for PII placeholder <-> original value pairs.

Key structure: {system_id}:{session_id}:map
Value: Redis hash where field = placeholder (e.g. "NAME_0"), value = original text.
TTL is set on the hash key to auto-expire mappings.
"""

from __future__ import annotations

from typing import Protocol


class RedisClientProtocol(Protocol):
    """Protocol for Redis client (supports both real and fake Redis)."""

    def hset(self, name: str, mapping: dict) -> int: ...
    def hgetall(self, name: str) -> dict: ...
    def expire(self, name: str, time: int) -> bool: ...
    def ttl(self, name: str) -> int: ...
    def delete(self, *names: str) -> int: ...


class RedisMappingStore:
    """Store and retrieve PII mapping tables in Redis.

    - Mappings are stored as Redis hashes (one hash per session).
    - TTL auto-expires mappings after a configurable duration.
    - Keys are namespaced by system_id for multi-tenant isolation.
    - No persistence: Redis should be configured with RDB/AOF disabled.
    """

    def __init__(
        self,
        redis_client: RedisClientProtocol,
        ttl_seconds: int = 3600,
    ) -> None:
        self._redis = redis_client
        self._ttl = ttl_seconds

    def _key(self, system_id: str, session_id: str) -> str:
        """Build the Redis key for a session's mapping."""
        return f"{system_id}:{session_id}:map"

    def save(
        self,
        system_id: str,
        session_id: str,
        mapping: dict[str, str],
    ) -> None:
        """Save (merge) a mapping into Redis for the given session.

        Existing entries for the same session are merged, not replaced.
        Same keys are overwritten. TTL is refreshed on each save.
        """
        if not mapping:
            return
        key = self._key(system_id, session_id)
        # hset with mapping dict merges into existing hash
        self._redis.hset(key, mapping=mapping)
        self._redis.expire(key, self._ttl)

    def load(self, system_id: str, session_id: str) -> dict[str, str]:
        """Load the complete mapping for a session.

        Returns an empty dict if the session does not exist or has expired.
        """
        key = self._key(system_id, session_id)
        raw = self._redis.hgetall(key)
        if not raw:
            return {}
        # Redis returns bytes; decode to str
        return {
            k.decode() if isinstance(k, bytes) else k: v.decode() if isinstance(v, bytes) else v
            for k, v in raw.items()
        }

    def delete(self, system_id: str, session_id: str) -> None:
        """Delete a session's mapping entirely."""
        key = self._key(system_id, session_id)
        self._redis.delete(key)
