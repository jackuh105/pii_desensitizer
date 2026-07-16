# src/pii_desensitizer/engine/restore.py
"""Restore engine: replaces {{TYPE_N}} placeholders with original PII values.

Flow:
  1. Load mapping from Redis for the given session
  2. Regex-scan text for all {{TYPE_N}} patterns
  3. For each match, look up in mapping; replace if found, leave as-is if not
  4. Return restored text
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from pii_desensitizer.store.redis_store import RedisMappingStore

_PLACEHOLDER_PATTERN = re.compile(r"\{\{([A-Z_]+)_(\d+)\}\}")


@dataclass
class RestoreResult:
    """Result of a restore operation."""

    text: str


class RestoreEngine:
    """Restore original PII values by replacing {{TYPE_N}} placeholders.

    Uses exact regex matching + lookup. No fuzzy matching.
    - Placeholders found in mapping -> replaced with original value
    - Placeholders not found (unknown/rewritten by LLM) -> left as-is
    """

    def __init__(self, store: RedisMappingStore) -> None:
        self._store = store

    def restore(
        self,
        text: str,
        system_id: str,
        session_id: str,
    ) -> RestoreResult:
        """Replace {{TYPE_N}} placeholders with original PII values.

        Args:
            text: LLM response text that may contain placeholders.
            system_id: The calling system's identifier.
            session_id: Session ID from the original desensitize call.

        Returns:
            RestoreResult with restored text.
        """
        mapping = self._store.load(system_id, session_id)

        if not mapping:
            return RestoreResult(text=text)

        def _replace_match(match: re.Match) -> str:
            placeholder_key = match.group(0)
            lookup_key = match.group(1) + "_" + match.group(2)
            if lookup_key in mapping:
                return mapping[lookup_key]
            return placeholder_key

        restored_text = _PLACEHOLDER_PATTERN.sub(_replace_match, text)

        return RestoreResult(text=restored_text)
