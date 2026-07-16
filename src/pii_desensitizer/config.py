"""Application configuration loaded from environment variables."""

from __future__ import annotations

import os
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Settings:
    """Immutable application settings."""

    api_keys: dict[str, str] = field(default_factory=dict)  # {api_key: system_id}
    redis_url: str = "redis://localhost:6379/0"
    mapping_ttl_seconds: int = 3600
    host: str = "0.0.0.0"
    port: int = 8000


def _parse_api_keys(raw: str) -> dict[str, str]:
    """Parse 'system_a:key_a,system_b:key_b' into {key: system_id}."""
    result: dict[str, str] = {}
    for pair in raw.split(","):
        pair = pair.strip()
        if not pair:
            continue
        if ":" not in pair:
            continue
        system_id, api_key = pair.split(":", 1)
        result[api_key.strip()] = system_id.strip()
    return result


def load_settings() -> Settings:
    """Load settings from environment variables."""
    raw_keys = os.getenv("API_KEYS", "")
    return Settings(
        api_keys=_parse_api_keys(raw_keys),
        redis_url=os.getenv("REDIS_URL", "redis://localhost:6379/0"),
        mapping_ttl_seconds=int(os.getenv("MAPPING_TTL_SECONDS", "3600")),
        host=os.getenv("HOST", "0.0.0.0"),
        port=int(os.getenv("PORT", "8000")),
    )
