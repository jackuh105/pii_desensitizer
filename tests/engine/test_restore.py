# tests/engine/test_restore.py
"""Tests for the restore engine."""

import pytest
from fakeredis import FakeRedis

from pii_desensitizer.store.redis_store import RedisMappingStore
from pii_desensitizer.engine.restore import RestoreEngine, RestoreResult


@pytest.fixture
def store():
    return RedisMappingStore(redis_client=FakeRedis(), ttl_seconds=3600)


@pytest.fixture
def engine(store):
    return RestoreEngine(store=store)


class TestRestoreEngine:
    def test_restore_replaces_placeholder(self, engine, store):
        store.save("sys", "sess", {"NAME_0": "陳大文"})

        result = engine.restore(
            text="Hello {{NAME_0}}",
            system_id="sys",
            session_id="sess",
        )
        assert result.text == "Hello 陳大文"

    def test_restore_multiple_placeholders(self, engine, store):
        store.save("sys", "sess", {
            "NAME_0": "陳大文",
            "PHONE_NUMBER_0": "98765432",
        })

        result = engine.restore(
            text="{{NAME_0}}的電話是{{PHONE_NUMBER_0}}",
            system_id="sys",
            session_id="sess",
        )
        assert result.text == "陳大文的電話是98765432"

    def test_restore_same_placeholder_multiple_times(self, engine, store):
        store.save("sys", "sess", {"NAME_0": "陳大文"})

        result = engine.restore(
            text="{{NAME_0}} said {{NAME_0}} is coming",
            system_id="sys",
            session_id="sess",
        )
        assert result.text == "陳大文 said 陳大文 is coming"

    def test_restore_unknown_placeholder_left_as_is(self, engine, store):
        store.save("sys", "sess", {"NAME_0": "陳大文"})

        result = engine.restore(
            text="{{NAME_0}} and {{UNKNOWN_0}}",
            system_id="sys",
            session_id="sess",
        )
        assert result.text == "陳大文 and {{UNKNOWN_0}}"

    def test_restore_no_placeholders_returns_original(self, engine, store):
        result = engine.restore(
            text="No placeholders here",
            system_id="sys",
            session_id="sess",
        )
        assert result.text == "No placeholders here"

    def test_restore_empty_mapping(self, engine, store):
        """Restore with no mapping (session not found) leaves placeholders as-is."""
        result = engine.restore(
            text="{{NAME_0}} is here",
            system_id="sys",
            session_id="nonexistent",
        )
        assert result.text == "{{NAME_0}} is here"

    def test_restore_namespace_isolation(self, engine, store):
        store.save("system_a", "sess", {"NAME_0": "Alice"})
        store.save("system_b", "sess", {"NAME_0": "Bob"})

        result_a = engine.restore(text="{{NAME_0}}", system_id="system_a", session_id="sess")
        result_b = engine.restore(text="{{NAME_0}}", system_id="system_b", session_id="sess")

        assert result_a.text == "Alice"
        assert result_b.text == "Bob"
