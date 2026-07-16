# src/pii_desensitizer/api/models.py
"""Pydantic models for API request/response schemas."""

from __future__ import annotations

from pydantic import BaseModel, Field


class DesensitizeRequest(BaseModel):
    """Request body for POST /desensitize."""

    text: str = Field(..., description="Original text that may contain PII")
    session_id: str | None = Field(
        default=None,
        description="Existing session ID for multi-turn accumulation. "
        "If omitted, a new session is created.",
    )


class DesensitizeResponse(BaseModel):
    """Response body for POST /desensitize."""

    text: str = Field(..., description="Desensitized text with {{TYPE_N}} placeholders")
    session_id: str = Field(..., description="Session ID for later restoration")


class RestoreRequest(BaseModel):
    """Request body for POST /restore."""

    text: str = Field(..., description="LLM response text that may contain placeholders")
    session_id: str = Field(..., description="Session ID from the desensitize call")


class RestoreResponse(BaseModel):
    """Response body for POST /restore."""

    text: str = Field(..., description="Restored text with original PII values")


class HealthResponse(BaseModel):
    """Response body for GET /health."""

    status: str
