# src/pii_desensitizer/engine/desensitize.py
"""Desensitization engine: orchestrates PII detection and placeholder replacement.

Stateful mode:
  1. Load existing mapping from Redis for session accumulation
  2. Run Presidio AnalyzerEngine to detect all PII entities
  3. Run Presidio AnonymizerEngine with PlaceholderOperator to replace PII
  4. Save the updated mapping to Redis
  5. Return desensitized text + session_id

Stateless mode:
  1. Run Presidio AnalyzerEngine to detect all PII entities
  2. Run Presidio AnonymizerEngine with PlaceholderOperator to replace PII
  3. Return desensitized text + flat mapping (no Redis, session_id=None)
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Dict, Optional

from presidio_analyzer import AnalyzerEngine
from presidio_anonymizer import AnonymizerEngine
from presidio_anonymizer.entities import OperatorConfig

from pii_desensitizer.engine.placeholder import PlaceholderOperator
from pii_desensitizer.recognizers import ALL_ENTITIES
from pii_desensitizer.store.redis_store import RedisMappingStore


class StatefulModeUnavailableError(Exception):
    """Raised when stateful mode is requested but Redis store is not configured."""


@dataclass
class DesensitizeResult:
    """Result of a desensitization operation."""

    text: str
    session_id: Optional[str]
    mapping: Optional[Dict[str, str]] = None


class DesensitizationEngine:
    """Orchestrates PII detection and placeholder replacement.

    In stateful mode, the placeholder→original mapping is persisted in Redis
    for later restoration. In stateless mode, the mapping is returned directly
    to the caller and Redis is not used.
    """

    def __init__(
        self,
        analyzer: AnalyzerEngine,
        store: Optional[RedisMappingStore] = None,
    ) -> None:
        self._analyzer = analyzer
        self._store = store

        self._anonymizer = AnonymizerEngine()
        self._anonymizer.add_anonymizer(PlaceholderOperator)

    def desensitize(
        self,
        text: str,
        system_id: str,
        session_id: Optional[str],
        *,
        mode: str = "stateful",
    ) -> DesensitizeResult:
        """Detect and replace PII in text with {{TYPE_N}} placeholders.

        Args:
            text: Original text that may contain PII.
            system_id: The calling system's identifier (for namespace isolation).
            session_id: Existing session ID for multi-turn accumulation.
                       If None, a new session is created. Ignored in stateless mode.
            mode: 'stateful' (default) or 'stateless'.

        Returns:
            DesensitizeResult with desensitized text, session_id (null in
            stateless), and mapping (only in stateless mode).
        """
        if mode == "stateless":
            return self._desensitize_stateless(text)

        if self._store is None:
            raise StatefulModeUnavailableError()

        return self._desensitize_stateful(text, system_id, session_id)

    def _desensitize_stateless(self, text: str) -> DesensitizeResult:
        entity_mapping: Dict[str, Dict[str, str]] = {}

        analyzer_results = self._analyzer.analyze(
            text=text,
            language="en",
            entities=ALL_ENTITIES,
        )

        operators = {
            "DEFAULT": OperatorConfig(
                "placeholder",
                {"entity_mapping": entity_mapping},
            )
        }

        anonymized = self._anonymizer.anonymize(
            text=text,
            analyzer_results=analyzer_results,
            operators=operators,
        )

        flat_mapping: Dict[str, str] = {}
        for entity_type, value_to_placeholder in entity_mapping.items():
            for original_value, placeholder in value_to_placeholder.items():
                key = placeholder.strip("{}")
                flat_mapping[key] = original_value

        return DesensitizeResult(
            text=anonymized.text,
            session_id=None,
            mapping=flat_mapping if flat_mapping else None,
        )

    def _desensitize_stateful(
        self,
        text: str,
        system_id: str,
        session_id: Optional[str],
    ) -> DesensitizeResult:
        if session_id is None:
            session_id = uuid.uuid4().hex

        existing_mapping: Dict[str, str] = self._store.load(
            system_id, session_id
        )
        entity_mapping: Dict[str, Dict[str, str]] = {}
        for placeholder, original_value in existing_mapping.items():
            parts = placeholder.rsplit("_", 1)
            if len(parts) == 2:
                entity_type, _ = parts
                if entity_type not in entity_mapping:
                    entity_mapping[entity_type] = {}
                entity_mapping[entity_type][original_value] = "{{" + placeholder + "}}"

        analyzer_results = self._analyzer.analyze(
            text=text,
            language="en",
            entities=ALL_ENTITIES,
        )

        operators = {
            "DEFAULT": OperatorConfig(
                "placeholder",
                {"entity_mapping": entity_mapping},
            )
        }

        anonymized = self._anonymizer.anonymize(
            text=text,
            analyzer_results=analyzer_results,
            operators=operators,
        )

        flat_mapping: Dict[str, str] = {}
        for entity_type, value_to_placeholder in entity_mapping.items():
            for original_value, placeholder in value_to_placeholder.items():
                key = placeholder.strip("{}")
                flat_mapping[key] = original_value

        if flat_mapping:
            self._store.save(system_id, session_id, flat_mapping)

        return DesensitizeResult(
            text=anonymized.text,
            session_id=session_id,
        )
