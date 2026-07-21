# src/pii_desensitizer/api/app.py
"""FastAPI application factory."""

from __future__ import annotations

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from pii_desensitizer.api.auth import create_auth_dependency
from pii_desensitizer.api.routes import router
from pii_desensitizer.config import load_settings
from pii_desensitizer.engine.desensitize import DesensitizationEngine
from pii_desensitizer.engine.restore import RestoreEngine
from pii_desensitizer.recognizers import build_analyzer
from pii_desensitizer.store.redis_store import RedisMappingStore

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger(__name__)


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    settings = load_settings()

    app = FastAPI(
        title="PII Desensitizer",
        description="Reversible PII desensitization proxy for cloud LLM API protection",
        version="0.1.0",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    logger.info("Initializing Presidio analyzer (loading spaCy models)...")
    analyzer = build_analyzer()

    store: RedisMappingStore | None = None
    if settings.redis_url:
        try:
            import redis as redis_lib
            redis_client = redis_lib.from_url(settings.redis_url)
            redis_client.ping()
            store = RedisMappingStore(
                redis_client=redis_client,
                ttl_seconds=settings.mapping_ttl_seconds,
            )
            logger.info("Redis connected successfully")
        except Exception as e:
            logger.warning(f"Redis unavailable, stateful mode disabled: {e}")
    else:
        logger.info("REDIS_URL not set, running in stateless-only mode")

    desensitize_engine = DesensitizationEngine(analyzer=analyzer, store=store)
    restore_engine = RestoreEngine(store=store) if store else None

    app.state.desensitize_engine = desensitize_engine
    app.state.restore_engine = restore_engine
    app.state.auth_dependency = create_auth_dependency(settings)
    app.state.settings = settings

    app.include_router(router)

    logger.info("Application initialized successfully")
    return app
