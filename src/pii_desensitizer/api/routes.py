# src/pii_desensitizer/api/routes.py
"""FastAPI route handlers for desensitize, restore, and health endpoints."""

from __future__ import annotations

import logging
import time

from fastapi import APIRouter, Depends, HTTPException, Request

from pii_desensitizer.api.auth import AuthContext
from pii_desensitizer.api.models import (
    DesensitizeRequest,
    DesensitizeResponse,
    HealthResponse,
    RestoreRequest,
    RestoreResponse,
)
from pii_desensitizer.engine.desensitize import StatefulModeUnavailableError

logger = logging.getLogger(__name__)

router = APIRouter()


def get_auth(request: Request) -> AuthContext:
    """Request-scoped dependency that delegates to the app's auth validator."""
    validator = request.app.state.auth_dependency
    return validator(x_api_key=request.headers.get("x-api-key"))


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    """Health check endpoint."""
    return HealthResponse(status="ok")


@router.post("/desensitize", response_model=DesensitizeResponse)
async def desensitize(
    request: Request,
    body: DesensitizeRequest,
    auth: AuthContext = Depends(get_auth),
) -> DesensitizeResponse:
    """Detect and replace PII in text with {{TYPE_N}} placeholders."""
    start_time = time.monotonic()

    engine = request.app.state.desensitize_engine
    try:
        result = engine.desensitize(
            text=body.text,
            system_id=auth.system_id,
            session_id=body.session_id,
            mode=body.mode,
        )
    except StatefulModeUnavailableError:
        raise HTTPException(
            status_code=503,
            detail="Stateful mode is not available in the current setup. "
            "Please contact the administrator for more information.",
        )

    elapsed_ms = (time.monotonic() - start_time) * 1000
    logger.info(
        "desensitize completed",
        extra={
            "system_id": auth.system_id,
            "session_id": result.session_id,
            "text_length": len(body.text),
            "processing_time_ms": round(elapsed_ms, 2),
        },
    )

    return DesensitizeResponse(
        text=result.text,
        session_id=result.session_id,
        mapping=result.mapping,
    )


@router.post("/restore", response_model=RestoreResponse)
async def restore(
    request: Request,
    body: RestoreRequest,
    auth: AuthContext = Depends(get_auth),
) -> RestoreResponse:
    """Replace {{TYPE_N}} placeholders in LLM response with original PII values."""
    start_time = time.monotonic()

    engine = request.app.state.restore_engine
    if engine is None:
        raise HTTPException(
            status_code=503,
            detail="Restore is not available in the current setup. "
            "Please contact the administrator for more information.",
        )

    result = engine.restore(
        text=body.text,
        system_id=auth.system_id,
        session_id=body.session_id,
    )

    elapsed_ms = (time.monotonic() - start_time) * 1000
    logger.info(
        "restore completed",
        extra={
            "system_id": auth.system_id,
            "session_id": body.session_id,
            "text_length": len(body.text),
            "processing_time_ms": round(elapsed_ms, 2),
        },
    )

    return RestoreResponse(text=result.text)
