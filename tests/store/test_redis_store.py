# tests/store/test_redis_store.py
"""Tests for Redis mapping store."""

import pytest
from fakeredis import FakeRedis

from pii_desensitizer.store.redis_store import RedisMappingStore


@pytest.fixture
def fake_redis():
    """Provide a fake Redis instance."""
    return FakeRedis()


@pytest.fixture
def store(fake_redis):
    """Provide a mapping store backed by fake Redis."""
    return RedisMappingStore(redis_client=fake_redis, ttl_seconds=3600)


class TestRedisMappingStore:
    """Tests for the Redis-backed mapping store."""

    def test_save_and_load_mapping(self, store):
        """Saved mapping can be loaded back."""
        mapping = {"NAME_0": "陳大文", "PHONE_0": "98765432"}
        store.save("system_a", "session_1", mapping)

        loaded = store.load("system_a", "session_1")
        assert loaded == mapping

    def test_load_nonexistent_session_returns_empty(self, store):
        """Loading a session that doesn't exist returns empty dict."""
        loaded = store.load("system_a", "nonexistent")
        assert loaded == {}

    def test_namespace_isolation(self, store):
        """System A cannot read System B's mapping."""
        store.save("system_a", "session_1", {"NAME_0": "Alice"})
        store.save("system_b", "session_1", {"NAME_0": "Bob"})

        assert store.load("system_a", "session_1") == {"NAME_0": "Alice"}
        assert store.load("system_b", "session_1") == {"NAME_0": "Bob"}

    def test_delete_session(self, store):
        """Deleting a session removes its mapping."""
        store.save("system_a", "session_1", {"NAME_0": "Alice"})
        store.delete("system_a", "session_1")

        assert store.load("system_a", "session_1") == {}

    def test_accumulate_mapping_merges(self, store):
        """Saving twice on same session merges entries."""
        store.save("system_a", "session_1", {"NAME_0": "Alice"})
        store.save("system_a", "session_1", {"PHONE_0": "98765432"})

        loaded = store.load("system_a", "session_1")
        assert loaded == {"NAME_0": "Alice", "PHONE_0": "98765432"}

    def test_accumulate_overwrites_same_key(self, store):
        """Saving a key that already exists overwrites the value."""
        store.save("system_a", "session_1", {"NAME_0": "Alice"})
        store.save("system_a", "session_1", {"NAME_0": "Bob"})

        loaded = store.load("system_a", "session_1")
        assert loaded == {"NAME_0": "Bob"}

    def test_ttl_is_set(self, store, fake_redis):
        """Saving sets a TTL on the Redis key."""
        store.save("system_a", "session_1", {"NAME_0": "Alice"})
        ttl = fake_redis.ttl("system_a:session_1:map")
        assert 0 < ttl <= 3600
