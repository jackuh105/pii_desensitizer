# tests/test_integration.py
"""End-to-end integration test for the full desensitize -> restore cycle.

This test uses a real Presidio analyzer (with spaCy models) and a fake Redis
store to verify the complete workflow without requiring external services.
"""

import pytest
from fakeredis import FakeRedis

from pii_desensitizer.recognizers import build_analyzer
from pii_desensitizer.store.redis_store import RedisMappingStore
from pii_desensitizer.engine.desensitize import DesensitizationEngine
from pii_desensitizer.engine.restore import RestoreEngine


@pytest.fixture(scope="module")
def analyzer():
    """Shared analyzer (model loading is expensive)."""
    return build_analyzer()


@pytest.fixture
def store():
    """Fresh fake store per test."""
    return RedisMappingStore(redis_client=FakeRedis(), ttl_seconds=3600)


@pytest.fixture
def desensitize_engine(analyzer, store):
    return DesensitizationEngine(analyzer=analyzer, store=store)


@pytest.fixture
def restore_engine(store):
    return RestoreEngine(store=store)


class TestFullCycle:
    """Test the complete desensitize -> (simulate LLM) -> restore cycle."""

    def test_email_round_trip(self, desensitize_engine, restore_engine):
        original = "Please contact john@example.com for details"
        system_id = "test_sys"

        d_result = desensitize_engine.desensitize(
            text=original, system_id=system_id, session_id=None
        )
        assert "john@example.com" not in d_result.text
        assert "{{EMAIL_0}}" in d_result.text

        llm_response = f"Sure, I'll contact {{{{EMAIL_0}}}} right away."

        r_result = restore_engine.restore(
            text=llm_response, system_id=system_id, session_id=d_result.session_id
        )
        assert "john@example.com" in r_result.text
        assert "{{EMAIL_0}}" not in r_result.text

    def test_multiple_pii_types_round_trip(self, desensitize_engine, restore_engine):
        original = "HKID A123456(7), email john@test.com, phone +852 98765432"
        system_id = "test_sys"

        d_result = desensitize_engine.desensitize(
            text=original, system_id=system_id, session_id=None
        )

        assert "A123456(7)" not in d_result.text
        assert "john@test.com" not in d_result.text
        assert "98765432" not in d_result.text

        r_result = restore_engine.restore(
            text=d_result.text, system_id=system_id, session_id=d_result.session_id
        )

        assert "A123456(7)" in r_result.text
        assert "john@test.com" in r_result.text
        assert "98765432" in r_result.text

    def test_multi_turn_session_consistency(self, desensitize_engine, restore_engine):
        """Same value across turns gets same placeholder."""
        system_id = "test_sys"
        session_id = "multi-turn-001"

        d1 = desensitize_engine.desensitize(
            text="Email: john@test.com",
            system_id=system_id,
            session_id=session_id,
        )
        assert "{{EMAIL_0}}" in d1.text

        d2 = desensitize_engine.desensitize(
            text="Also contact john@test.com",
            system_id=system_id,
            session_id=session_id,
        )
        assert "{{EMAIL_0}}" in d2.text

        r2 = restore_engine.restore(
            text=d2.text, system_id=system_id, session_id=session_id
        )
        assert "john@test.com" in r2.text
