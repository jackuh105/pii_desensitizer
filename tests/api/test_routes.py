# tests/api/test_routes.py
"""Tests for API routes."""

import pytest
from fastapi.testclient import TestClient
from fakeredis import FakeRedis

from pii_desensitizer.api.app import create_app
from pii_desensitizer.store.redis_store import RedisMappingStore


@pytest.fixture(scope="module")
def client():
    """Create a test client with a real app instance using fakeredis.

    Note: This loads spaCy models (slow on first run).
    """
    import os
    os.environ["API_KEYS"] = "test_system:test-api-key-1234"

    app = create_app()

    fake_redis = FakeRedis()
    fake_store = RedisMappingStore(redis_client=fake_redis, ttl_seconds=3600)
    app.state.desensitize_engine._store = fake_store
    app.state.restore_engine._store = fake_store

    return TestClient(app)


@pytest.fixture(scope="module")
def auth_headers():
    return {"X-API-Key": "test-api-key-1234"}


class TestHealthEndpoint:
    def test_health_check(self, client):
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}


class TestAuth:
    def test_missing_api_key_returns_401(self, client):
        response = client.post("/desensitize", json={"text": "hello"})
        assert response.status_code == 401

    def test_invalid_api_key_returns_401(self, client):
        response = client.post(
            "/desensitize",
            json={"text": "hello"},
            headers={"X-API-Key": "wrong-key"},
        )
        assert response.status_code == 401


class TestDesensitizeEndpoint:
    def test_desensitize_email(self, client, auth_headers):
        response = client.post(
            "/desensitize",
            json={"text": "Contact john@example.com"},
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert "text" in data
        assert "session_id" in data
        assert "john@example.com" not in data["text"]
        assert "{{EMAIL_0}}" in data["text"]

    def test_desensitize_with_session_id(self, client, auth_headers):
        response = client.post(
            "/desensitize",
            json={"text": "Email john@test.com", "session_id": "my-session-001"},
            headers=auth_headers,
        )
        assert response.status_code == 200
        assert response.json()["session_id"] == "my-session-001"

    def test_desensitize_no_pii(self, client, auth_headers):
        response = client.post(
            "/desensitize",
            json={"text": "Hello world"},
            headers=auth_headers,
        )
        assert response.status_code == 200
        assert response.json()["text"] == "Hello world"


class TestRestoreEndpoint:
    def test_restore_placeholder(self, client, auth_headers):
        desensitize_resp = client.post(
            "/desensitize",
            json={"text": "Contact john@example.com"},
            headers=auth_headers,
        )
        session_id = desensitize_resp.json()["session_id"]

        restore_resp = client.post(
            "/restore",
            json={
                "text": f"Got it: {{{{EMAIL_0}}}}",
                "session_id": session_id,
            },
            headers=auth_headers,
        )
        assert restore_resp.status_code == 200
        assert "john@example.com" in restore_resp.json()["text"]

    def test_restore_without_session_id_returns_422(self, client, auth_headers):
        response = client.post(
            "/restore",
            json={"text": "hello"},
            headers=auth_headers,
        )
        assert response.status_code == 422


class TestStatelessMode:
    def test_stateless_returns_mapping(self, client, auth_headers):
        response = client.post(
            "/desensitize",
            json={"text": "Contact john@example.com", "mode": "stateless"},
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["session_id"] is None
        assert data["mapping"] is not None
        assert data["mapping"]["EMAIL_0"] == "john@example.com"
        assert "john@example.com" not in data["text"]

    def test_stateless_no_mapping_field_in_stateful(self, client, auth_headers):
        response = client.post(
            "/desensitize",
            json={"text": "Contact john@example.com", "mode": "stateful"},
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["session_id"] is not None
        assert "mapping" not in data or data["mapping"] is None

    def test_stateless_default_is_stateful(self, client, auth_headers):
        response = client.post(
            "/desensitize",
            json={"text": "Contact john@example.com"},
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["session_id"] is not None

    def test_stateless_ignores_session_id(self, client, auth_headers):
        response = client.post(
            "/desensitize",
            json={
                "text": "Contact john@example.com",
                "mode": "stateless",
                "session_id": "should-be-ignored",
            },
            headers=auth_headers,
        )
        assert response.status_code == 200
        assert response.json()["session_id"] is None
