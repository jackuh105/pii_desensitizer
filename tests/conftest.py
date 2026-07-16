# tests/conftest.py
"""Shared pytest fixtures."""

import pytest
from fakeredis import FakeRedis

from pii_desensitizer.store.redis_store import RedisMappingStore


@pytest.fixture
def fake_redis():
    """Provide a fresh FakeRedis instance for each test."""
    return FakeRedis()


@pytest.fixture
def mapping_store(fake_redis):
    """Provide a RedisMappingStore backed by FakeRedis."""
    return RedisMappingStore(redis_client=fake_redis, ttl_seconds=3600)
