# tests/engine/test_desensitize.py
"""Tests for the desensitization engine."""

import pytest
from fakeredis import FakeRedis

from pii_desensitizer.store.redis_store import RedisMappingStore
from pii_desensitizer.engine.placeholder import PlaceholderOperator
from pii_desensitizer.engine.desensitize import DesensitizationEngine


@pytest.fixture(scope="module")
def analyzer():
    """Build a real Presidio AnalyzerEngine (loads spaCy models)."""
    from pii_desensitizer.recognizers import build_analyzer
    return build_analyzer()


@pytest.fixture
def store():
    """Provide a fresh fake Redis mapping store."""
    return RedisMappingStore(redis_client=FakeRedis(), ttl_seconds=3600)


@pytest.fixture
def engine(analyzer, store):
    """Desensitization engine with real analyzer and fake store."""
    return DesensitizationEngine(analyzer=analyzer, store=store)


class TestDesensitizationEngine:
    def test_desensitize_replaces_email(self, engine, store):
        result = engine.desensitize(
            text="Contact john@example.com please",
            system_id="test_system",
            session_id=None,
        )
        assert "{{EMAIL_0}}" in result.text
        assert "john@example.com" not in result.text
        assert result.session_id  # auto-generated

    def test_desensitize_replaces_hkid(self, engine, store):
        result = engine.desensitize(
            text="My HKID is A123456(7)",
            system_id="test_system",
            session_id=None,
        )
        assert "A123456(7)" not in result.text
        assert "{{HKID_0}}" in result.text

    def test_desensitize_replaces_phone(self, engine, store):
        result = engine.desensitize(
            text="Call +852 98765432",
            system_id="test_system",
            session_id=None,
        )
        assert "98765432" not in result.text
        assert "{{PHONE_NUMBER_0}}" in result.text

    def test_same_value_same_placeholder_in_one_call(self, engine, store):
        text = "Email john@test.com twice: john@test.com"
        result = engine.desensitize(text=text, system_id="test_system", session_id=None)
        assert result.text.count("{{EMAIL_0}}") == 2

    def test_session_accumulation_reuses_placeholder(self, engine, store):
        """Same value in a second desensitize call (same session) gets same placeholder."""
        session_id = "test-session-001"

        first = engine.desensitize(
            text="Email: john@test.com",
            system_id="test_system",
            session_id=session_id,
        )
        second = engine.desensitize(
            text="Also john@test.com",
            system_id="test_system",
            session_id=session_id,
        )
        assert "{{EMAIL_0}}" in first.text
        assert "{{EMAIL_0}}" in second.text

    def test_mapping_stored_in_redis(self, engine, store):
        result = engine.desensitize(
            text="Email: john@test.com",
            system_id="test_system",
            session_id=None,
        )
        mapping = store.load("test_system", result.session_id)
        assert "EMAIL_0" in mapping
        assert mapping["EMAIL_0"] == "john@test.com"

    def test_namespace_isolation(self, engine, store):
        """Different system_ids have isolated mappings."""
        result_a = engine.desensitize(
            text="Email: alice@test.com",
            system_id="system_a",
            session_id=None,
        )
        result_b = engine.desensitize(
            text="Email: bob@test.com",
            system_id="system_b",
            session_id=None,
        )
        mapping_a = store.load("system_a", result_a.session_id)
        mapping_b = store.load("system_b", result_b.session_id)
        assert mapping_a["EMAIL_0"] == "alice@test.com"
        assert mapping_b["EMAIL_0"] == "bob@test.com"

    def test_text_without_pii_unchanged(self, engine, store):
        result = engine.desensitize(
            text="Hello world, no sensitive data here",
            system_id="test_system",
            session_id=None,
        )
        assert result.text == "Hello world, no sensitive data here"
