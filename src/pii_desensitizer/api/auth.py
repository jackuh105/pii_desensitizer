# src/pii_desensitizer/api/auth.py
"""API Key authentication for the desensitization proxy.

Each client system is assigned an API key. The key maps to a system_id
which is used for Redis namespace isolation.
"""

from __future__ import annotations

from dataclasses import dataclass

from fastapi import Header, HTTPException, status

from pii_desensitizer.config import Settings


@dataclass
class AuthContext:
    """Authentication context injected into request handlers."""

    system_id: str


def create_auth_dependency(settings: Settings):
    """Create a FastAPI dependency that validates the X-API-Key header.

    Returns an AuthContext with the system_id derived from the API key.
    """

    def validate_api_key(x_api_key: str | None = Header(default=None)) -> AuthContext:
        if not x_api_key:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Missing X-API-Key header",
            )

        system_id = settings.api_keys.get(x_api_key)
        if not system_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid API key",
            )

        return AuthContext(system_id=system_id)

    return validate_api_key
