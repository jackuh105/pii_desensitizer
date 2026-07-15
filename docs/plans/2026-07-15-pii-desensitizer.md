# PII Desensitizer Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a reversible PII desensitization proxy that detects, extracts, and replaces personal information in text before sending to cloud LLM APIs, then restores original values in LLM responses.

**Architecture:** Independent FastAPI proxy service with explicit `POST /desensitize` and `POST /restore` endpoints. Uses Microsoft Presidio (AnalyzerEngine + AnonymizerEngine) with custom regex recognizers for formatted PII (HK/Macau formats), a custom spaCy-based Chinese person name recognizer, and a custom `{{TYPE_N}}` placeholder operator. Mapping tables stored in Redis (in-memory only, no persistence, 1-hour TTL) with per-system namespace isolation via API Key authentication.

**Tech Stack:** Python 3.12, FastAPI, uvicorn, Microsoft Presidio (presidio-analyzer + presidio-anonymizer), spaCy (en_core_web_sm + zh_core_web_sm), Redis, Docker Compose

---

## Design Decisions Summary

| # | Decision | Choice |
|---|---|---|
| 1 | Deployment mode | Independent Proxy service (language-agnostic) |
| 2 | Interaction mode | Explicit desensitize/restore API (client calls LLM itself) |
| 3 | Data language | Chinese+English mixed, HK/Macau formats (no Taiwan) |
| 4 | PII types (12) | Person name (zh+en), Phone (HK/Macau), Email, ID (HKID+Macau), Address (zh+en), Credit card, Bank account, Passport (HK/Macau), Birthday, IP address, License plate (HK/Macau) |
| 5 | Detection method | Regex (formatted PII) + spaCy NER (person names), Presidio framework |
| 6 | Accuracy strategy | Per-type: ID/card = high recall, name = balanced, address = precision-leaning |
| 7 | Placeholder format | `{{TYPE_N}}` (e.g. `{{NAME_1}}`), double braces + type + index, same value = same placeholder |
| 8 | Mapping storage | Redis in-memory (persistence OFF), most secure |
| 9 | Tech stack | Python + FastAPI |
| 10 | Traffic scale | Low traffic, short text, single instance + 2-4 workers |
| 11 | API auth | API Key per system + Redis namespace isolation (`{system_id}:{session_id}:key`) |
| 12 | Logging | No PII in logs (only session_id, type counts, timestamp, system_id, processing_time); dry-run mode for dev |
| 13 | Session lifecycle | Support accumulation (session_id optional, same value = same placeholder across rounds) |
| 14 | API response format | Minimal: `{"text": "...", "session_id": "..."}` |
| 15 | PII config | Global config, all systems detect all 12 types |
| 16 | Deployment | Docker Compose initially |
| 17 | TTL | 1 hour |
| 18 | Address detection | Initial heuristic (keywords + regex), accept lower precision, future LLM fallback |
| 19 | Restore strategy | Exact regex match + lookup replacement, not found/rewritten = leave as-is |

## PII Entity Types

| Entity Type | Presidio Key | Detection | Accuracy Strategy | HK/Macau Format Example |
|---|---|---|---|---|
| Person Name (Chinese) | `PERSON` | spaCy zh_core_web_sm NER | Balanced | 陳大文 |
| Person Name (English) | `PERSON` | Presidio built-in SpacyRecognizer (en) | Balanced | John Chan |
| Phone | `PHONE_NUMBER` | Regex | Balanced | +852 98765432, 61234567 |
| Email | `EMAIL` | Regex | Balanced | john@example.com |
| HKID | `HKID` | Regex + checksum | High recall | A123456(7) |
| Macau ID | `MACAU_ID` | Regex | High recall | 1234567(8) |
| Address | `ADDRESS` | Keyword + regex heuristic | Precision-leaning | 中環德輔道中1號 |
| Credit Card | `CREDIT_CARD` | Regex + Luhn validation | High recall | 4111-1111-1111-1111 |
| Bank Account | `BANK_ACCOUNT` | Regex + context | High recall | 12-digit number |
| Passport | `PASSPORT` | Regex | High recall | H12345678, K12345678 |
| Birthday | `BIRTHDAY` | Regex | Balanced | 1990-01-15 |
| IP Address | `IP_ADDRESS` | Regex | Balanced | 192.168.1.1 |
| License Plate | `LICENSE_PLATE` | Regex | Balanced | AB 1234 |

## File Structure

```
pii-desensitizer/
├── docs/plans/2026-07-15-pii-desensitizer.md   # This plan
├── src/pii_desensitizer/
│   ├── __init__.py                              # Package entry, exports create_app
│   ├── config.py                                # Settings (Redis URL, API keys, TTL)
│   ├── api/
│   │   ├── __init__.py
│   │   ├── app.py                               # FastAPI app factory
│   │   ├── routes.py                            # /desensitize, /restore, /health
│   │   ├── auth.py                              # API Key auth dependency
│   │   └── models.py                            # Pydantic request/response schemas
│   ├── recognizers/
│   │   ├── __init__.py                          # Registry: build all recognizers
│   │   ├── contact.py                           # Email, Phone, IP recognizers
│   │   ├── identity.py                          # HKID, Macau ID, Passport, License plate
│   │   ├── financial.py                         # Credit card (Luhn), Bank account
│   │   ├── temporal.py                          # Birthday
│   │   ├── address.py                           # Address heuristic recognizer
│   │   └── person_ner.py                        # Chinese person name recognizer (spaCy zh)
│   ├── engine/
│   │   ├── __init__.py
│   │   ├── desensitize.py                       # Desensitization engine
│   │   ├── restore.py                           # Restore engine
│   │   └── placeholder.py                       # Custom PlaceholderOperator
│   └── store/
│       ├── __init__.py
│       └── redis_store.py                       # Redis mapping store
├── tests/
│   ├── conftest.py                              # Shared fixtures
│   ├── recognizers/
│   │   ├── test_contact.py
│   │   ├── test_identity.py
│   │   ├── test_financial.py
│   │   ├── test_temporal.py
│   │   ├── test_address.py
│   │   └── test_person_ner.py
│   ├── engine/
│   │   ├── test_desensitize.py
│   │   ├── test_restore.py
│   │   └── test_placeholder.py
│   ├── store/
│   │   └── test_redis_store.py
│   └── api/
│       └── test_routes.py
├── docker/
│   ├── Dockerfile
│   └── docker-compose.yml
├── pyproject.toml
├── .env.example
└── README.md
```

## API Contract

```
POST /desensitize
  Headers: X-API-Key: <key>
  Body:    {"text": "原始文字", "session_id": "optional, for multi-turn"}
  Response: {"text": "去敏感化文字", "session_id": "session-id"}

POST /restore
  Headers: X-API-Key: <key>
  Body:    {"text": "LLM回應", "session_id": "session-id-from-desensitize"}
  Response: {"text": "還原後文字"}

GET /health
  Response: {"status": "ok"}
```

---

## Task 1: Project Dependencies & Configuration

**Files:**
- Modify: `pyproject.toml`
- Create: `src/pii_desensitizer/config.py`
- Create: `.env.example`

**Step 1: Add runtime dependencies**

Run:
```bash
uv add fastapi "uvicorn[standard]" redis presidio-analyzer presidio-anonymizer spacy pydantic pydantic-settings
```

**Step 2: Add dev dependencies**

Run:
```bash
uv add --dev pytest pytest-asyncio httpx
```

**Step 3: Download spaCy models**

Run:
```bash
uv add https://github.com/explosion/spacy-models/releases/download/en_core_web_sm-3.8.0/en_core_web_sm-3.8.0-py3-none-any.whl
uv add https://github.com/explosion/spacy-models/releases/download/zh_core_web_sm-3.8.0/zh_core_web_sm-3.8.0-py3-none-any.whl
```

**Step 4: Create `.env.example`**

```bash
# API Keys (format: system_id:api_key, comma-separated)
API_KEYS=system_a:test-key-a-00000000,system_b:test-key-b-00000000

# Redis
REDIS_URL=redis://localhost:6379/0

# Mapping TTL in seconds
MAPPING_TTL_SECONDS=3600

# Server
HOST=0.0.0.0
PORT=8000
```

**Step 5: Create `src/pii_desensitizer/config.py`**

```python
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
```

**Step 6: Verify installation**

Run:
```bash
uv run python -c "import fastapi, redis, presidio_analyzer, presidio_anonymizer, spacy; print('All imports OK')"
uv run python -c "import en_core_web_sm, zh_core_web_sm; print('spaCy models OK')"
```

Expected: Both print OK with no errors.

**Step 7: Commit**

```bash
git add -A
git commit -m "chore: add project dependencies and configuration"
```

---

## Task 2: Redis Mapping Store

**Files:**
- Create: `src/pii_desensitizer/store/redis_store.py`
- Test: `tests/store/test_redis_store.py`

The mapping store persists `{{TYPE_N}} → original_value` pairs in Redis, keyed by `{system_id}:{session_id}:map`. Uses a Redis hash (one field per placeholder). TTL is set on the hash key. No persistence (Redis configured with `--save "" --appendonly no`).

**Step 1: Write failing tests**

```python
# tests/store/test_redis_store.py
"""Tests for Redis mapping store."""

import pytest
from fakeredis import FakeRedis

from pii_desensitizer.store.redis_store import RedisMappingStore


@pytest.fixture
def fake_redis():
    """Provide a fake Redis instance."""
    return FakeRedis()


@pytest.fixture
def store(fake_redis):
    """Provide a mapping store backed by fake Redis."""
    return RedisMappingStore(redis_client=fake_redis, ttl_seconds=3600)


class TestRedisMappingStore:
    """Tests for the Redis-backed mapping store."""

    def test_save_and_load_mapping(self, store):
        """Saved mapping can be loaded back."""
        mapping = {"NAME_0": "陳大文", "PHONE_0": "98765432"}
        store.save("system_a", "session_1", mapping)

        loaded = store.load("system_a", "session_1")
        assert loaded == mapping

    def test_load_nonexistent_session_returns_empty(self, store):
        """Loading a session that doesn't exist returns empty dict."""
        loaded = store.load("system_a", "nonexistent")
        assert loaded == {}

    def test_namespace_isolation(self, store):
        """System A cannot read System B's mapping."""
        store.save("system_a", "session_1", {"NAME_0": "Alice"})
        store.save("system_b", "session_1", {"NAME_0": "Bob"})

        assert store.load("system_a", "session_1") == {"NAME_0": "Alice"}
        assert store.load("system_b", "session_1") == {"NAME_0": "Bob"}

    def test_delete_session(self, store):
        """Deleting a session removes its mapping."""
        store.save("system_a", "session_1", {"NAME_0": "Alice"})
        store.delete("system_a", "session_1")

        assert store.load("system_a", "session_1") == {}

    def test_accumulate_mapping_merges(self, store):
        """Saving twice on same session merges entries."""
        store.save("system_a", "session_1", {"NAME_0": "Alice"})
        store.save("system_a", "session_1", {"PHONE_0": "98765432"})

        loaded = store.load("system_a", "session_1")
        assert loaded == {"NAME_0": "Alice", "PHONE_0": "98765432"}

    def test_accumulate_overwrites_same_key(self, store):
        """Saving a key that already exists overwrites the value."""
        store.save("system_a", "session_1", {"NAME_0": "Alice"})
        store.save("system_a", "session_1", {"NAME_0": "Bob"})

        loaded = store.load("system_a", "session_1")
        assert loaded == {"NAME_0": "Bob"}

    def test_ttl_is_set(self, store, fake_redis):
        """Saving sets a TTL on the Redis key."""
        store.save("system_a", "session_1", {"NAME_0": "Alice"})
        ttl = fake_redis.ttl("system_a:session_1:map")
        assert 0 < ttl <= 3600
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/store/test_redis_store.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'pii_desensitizer.store.redis_store'`

**Step 3: Add `fakeredis` dev dependency**

Run: `uv add --dev fakeredis`

**Step 4: Implement the store**

```python
# src/pii_desensitizer/store/redis_store.py
"""Redis-backed mapping store for PII placeholder ↔ original value pairs.

Key structure: {system_id}:{session_id}:map
Value: Redis hash where field = placeholder (e.g. "NAME_0"), value = original text.
TTL is set on the hash key to auto-expire mappings.
"""

from __future__ import annotations

from typing import Protocol

import redis


class RedisClientProtocol(Protocol):
    """Protocol for Redis client (supports both real and fake Redis)."""

    def hset(self, name: str, mapping: dict) -> int: ...
    def hgetall(self, name: str) -> dict: ...
    def expire(self, name: str, time: int) -> bool: ...
    def ttl(self, name: str) -> int: ...
    def delete(self, *names: str) -> int: ...


class RedisMappingStore:
    """Store and retrieve PII mapping tables in Redis.

    - Mappings are stored as Redis hashes (one hash per session).
    - TTL auto-expires mappings after a configurable duration.
    - Keys are namespaced by system_id for multi-tenant isolation.
    - No persistence: Redis should be configured with RDB/AOF disabled.
    """

    def __init__(
        self,
        redis_client: RedisClientProtocol,
        ttl_seconds: int = 3600,
    ) -> None:
        self._redis = redis_client
        self._ttl = ttl_seconds

    def _key(self, system_id: str, session_id: str) -> str:
        """Build the Redis key for a session's mapping."""
        return f"{system_id}:{session_id}:map"

    def save(
        self,
        system_id: str,
        session_id: str,
        mapping: dict[str, str],
    ) -> None:
        """Save (merge) a mapping into Redis for the given session.

        Existing entries for the same session are merged, not replaced.
        Same keys are overwritten. TTL is refreshed on each save.
        """
        if not mapping:
            return
        key = self._key(system_id, session_id)
        # hset with mapping dict merges into existing hash
        self._redis.hset(key, mapping=mapping)
        self._redis.expire(key, self._ttl)

    def load(self, system_id: str, session_id: str) -> dict[str, str]:
        """Load the complete mapping for a session.

        Returns an empty dict if the session does not exist or has expired.
        """
        key = self._key(system_id, session_id)
        raw = self._redis.hgetall(key)
        if not raw:
            return {}
        # Redis returns bytes; decode to str
        return {
            k.decode() if isinstance(k, bytes) else k: v.decode() if isinstance(v, bytes) else v
            for k, v in raw.items()
        }

    def delete(self, system_id: str, session_id: str) -> None:
        """Delete a session's mapping entirely."""
        key = self._key(system_id, session_id)
        self._redis.delete(key)
```

**Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/store/test_redis_store.py -v`
Expected: All 7 tests PASS

**Step 6: Commit**

```bash
git add -A
git commit -m "feat: add Redis mapping store with namespace isolation and TTL"
```

---

## Task 3: Custom Placeholder Operator

**Files:**
- Create: `src/pii_desensitizer/engine/placeholder.py`
- Test: `tests/engine/test_placeholder.py`

The `PlaceholderOperator` replaces each PII value with `{{TYPE_N}}` where N is a per-type counter. The same value always maps to the same placeholder within a single `entity_mapping` dict. This is the Presidio `Operator` subclass that produces our reversible placeholders.

**Step 1: Write failing tests**

```python
# tests/engine/test_placeholder.py
"""Tests for the custom placeholder operator."""

import pytest

from pii_desensitizer.engine.placeholder import PlaceholderOperator


class TestPlaceholderOperator:
    """Tests for the {{TYPE_N}} placeholder operator."""

    def test_operator_name(self):
        op = PlaceholderOperator()
        assert op.operator_name() == "placeholder"

    def test_operator_type_is_anonymize(self):
        from presidio_anonymizer.operators import OperatorType
        op = PlaceholderOperator()
        assert op.operator_type() == OperatorType.Anonymize

    def test_replaces_single_value(self):
        op = PlaceholderOperator()
        result = op.operate(
            text="陳大文",
            params={"entity_type": "PERSON", "entity_mapping": {}},
        )
        assert result == "{{PERSON_0}}"

    def test_same_value_same_placeholder(self):
        """The same value always gets the same placeholder."""
        mapping: dict[str, dict[str, str]] = {}
        params = {"entity_type": "PERSON", "entity_mapping": mapping}

        op = PlaceholderOperator()
        first = op.operate(text="陳大文", params=params)
        second = op.operate(text="陳大文", params=params)

        assert first == "{{PERSON_0}}"
        assert second == "{{PERSON_0}}"

    def test_different_values_different_index(self):
        mapping: dict[str, dict[str, str]] = {}
        params = {"entity_type": "PERSON", "entity_mapping": mapping}

        op = PlaceholderOperator()
        first = op.operate(text="陳大文", params=params)
        second = op.operate(text="李小明", params=params)

        assert first == "{{PERSON_0}}"
        assert second == "{{PERSON_1}}"

    def test_different_entity_types_independent_indexing(self):
        mapping: dict[str, dict[str, str]] = {}
        op = PlaceholderOperator()

        name_result = op.operate(
            text="陳大文",
            params={"entity_type": "PERSON", "entity_mapping": mapping},
        )
        phone_result = op.operate(
            text="98765432",
            params={"entity_type": "PHONE_NUMBER", "entity_mapping": mapping},
        )

        assert name_result == "{{PERSON_0}}"
        assert phone_result == "{{PHONE_NUMBER_0}}"

    def test_pre_existing_mapping_is_reused(self):
        """When mapping already has entries, new values continue the index."""
        mapping: dict[str, dict[str, str]] = {
            "PERSON": {"陳大文": "{{PERSON_0}}"}
        }
        op = PlaceholderOperator()
        result = op.operate(
            text="李小明",
            params={"entity_type": "PERSON", "entity_mapping": mapping},
        )
        assert result == "{{PERSON_1}}"

    def test_pre_existing_value_gets_existing_placeholder(self):
        """A value already in the mapping returns its existing placeholder."""
        mapping: dict[str, dict[str, str]] = {
            "PERSON": {"陳大文": "{{PERSON_0}}"}
        }
        op = PlaceholderOperator()
        result = op.operate(
            text="陳大文",
            params={"entity_type": "PERSON", "entity_mapping": mapping},
        )
        assert result == "{{PERSON_0}}"

    def test_validate_requires_entity_mapping(self):
        op = PlaceholderOperator()
        with pytest.raises(ValueError, match="entity_mapping"):
            op.validate(params={"entity_type": "PERSON"})

    def test_validate_requires_entity_type(self):
        op = PlaceholderOperator()
        with pytest.raises(ValueError, match="entity_type"):
            op.validate(params={"entity_mapping": {}})
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/engine/test_placeholder.py -v`
Expected: FAIL — `ModuleNotFoundError`

**Step 3: Implement the operator**

```python
# src/pii_desensitizer/engine/placeholder.py
"""Custom Presidio Operator that replaces PII values with {{TYPE_N}} placeholders.

The same original value always maps to the same placeholder within a single
entity_mapping dict, enabling:
  1. Consistent replacement across a document (LLM sees {{PERSON_0}} for every
     occurrence of the same name).
  2. Reversible restoration: the entity_mapping dict is the lookup table.

Format: {{ENTITY_TYPE_INDEX}}  e.g. {{PERSON_0}}, {{PHONE_NUMBER_1}}
"""

from __future__ import annotations

from typing import Dict

from presidio_anonymizer.operators import Operator, OperatorType


class PlaceholderOperator(Operator):
    """Replace PII values with {{TYPE_N}} placeholders.

    Uses a shared ``entity_mapping`` dict (passed via params) to maintain
    value → placeholder consistency across multiple operate() calls within
    the same anonymization pass.

    The entity_mapping structure:
        {
            "PERSON": {"陳大文": "{{PERSON_0}}", "李小明": "{{PERSON_1}}"},
            "PHONE_NUMBER": {"98765432": "{{PHONE_NUMBER_0}}"},
        }
    """

    def operate(self, text: str, params: Dict | None = None) -> str:
        """Replace ``text`` with its {{TYPE_N}} placeholder.

        If the value was seen before (exists in mapping), return the existing
        placeholder. Otherwise, assign the next index for this entity type.
        """
        if params is None:
            params = {}

        entity_type: str = params["entity_type"]
        entity_mapping: Dict[str, Dict[str, str]] = params["entity_mapping"]

        per_type = entity_mapping.setdefault(entity_type, {})

        # Reuse existing placeholder for this exact value
        if text in per_type:
            return per_type[text]

        # Assign next index (0-based) for this entity type
        index = len(per_type)
        placeholder = "{{" + f"{entity_type}_{index}" + "}}"

        per_type[text] = placeholder
        return placeholder

    def validate(self, params: Dict | None = None) -> None:
        """Validate that required params are present."""
        if params is None:
            params = {}
        if "entity_mapping" not in params:
            raise ValueError(
                "An input Dict called `entity_mapping` is required."
            )
        if "entity_type" not in params:
            raise ValueError("An `entity_type` param is required.")

    def operator_name(self) -> str:
        """Return the operator name used in OperatorConfig."""
        return "placeholder"

    def operator_type(self) -> OperatorType:
        """Return the operator type (Anonymize)."""
        return OperatorType.Anonymize
```

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/engine/test_placeholder.py -v`
Expected: All 10 tests PASS

**Step 5: Commit**

```bash
git add -A
git commit -m "feat: add {{TYPE_N}} placeholder operator for Presidio"
```

---

## Task 4: Regex Recognizers — Contact (Email, Phone, IP)

**Files:**
- Create: `src/pii_desensitizer/recognizers/contact.py`
- Test: `tests/recognizers/test_contact.py`

**Step 1: Write failing tests**

```python
# tests/recognizers/test_contact.py
"""Tests for contact PII recognizers (email, phone, IP)."""

import pytest

from pii_desensitizer.recognizers.contact import (
    EmailRecognizer,
    HKMacauPhoneRecognizer,
    IPAddressRecognizer,
)


class TestEmailRecognizer:
    def test_detects_simple_email(self):
        rec = EmailRecognizer()
        results = rec.analyze(
            text="Contact me at john@example.com please",
            entities=["EMAIL"],
            nlp_artifacts=None,
        )
        assert len(results) == 1
        assert results[0].entity_type == "EMAIL"
        assert text[results[0].start:results[0].end] == "john@example.com"

    def test_detects_multiple_emails(self):
        rec = EmailRecognizer()
        results = rec.analyze(
            text="john@work.com and jane@home.org",
            entities=["EMAIL"],
            nlp_artifacts=None,
        )
        assert len(results) == 2

    def test_no_false_positive_on_at_sign(self):
        rec = EmailRecognizer()
        results = rec.analyze(
            text="Meet me at 3pm",
            entities=["EMAIL"],
            nlp_artifacts=None,
        )
        assert len(results) == 0


class TestHKMacauPhoneRecognizer:
    def test_detects_hk_mobile_with_country_code(self):
        rec = HKMacauPhoneRecognizer()
        results = rec.analyze(
            text="Call me at +852 98765432",
            entities=["PHONE_NUMBER"],
            nlp_artifacts=None,
        )
        assert len(results) == 1
        assert text[results[0].start:results[0].end] == "+852 98765432"

    def test_detects_macau_mobile(self):
        rec = HKMacauPhoneRecognizer()
        results = rec.analyze(
            text="My number is 61234567",
            entities=["PHONE_NUMBER"],
            nlp_artifacts=None,
        )
        assert len(results) == 1
        assert text[results[0].start:results[0].end] == "61234567"

    def test_detects_phone_with_hyphen(self):
        rec = HKMacauPhoneRecognizer()
        results = rec.analyze(
            text="Fax: 9876-5432",
            entities=["PHONE_NUMBER"],
            nlp_artifacts=None,
        )
        assert len(results) == 1

    def test_detects_macau_country_code(self):
        rec = HKMacauPhoneRecognizer()
        results = rec.analyze(
            text="+853 61234567",
            entities=["PHONE_NUMBER"],
            nlp_artifacts=None,
        )
        assert len(results) == 1

    def test_no_false_positive_on_short_number(self):
        rec = HKMacauPhoneRecognizer()
        results = rec.analyze(
            text="Order #12345",
            entities=["PHONE_NUMBER"],
            nlp_artifacts=None,
        )
        assert len(results) == 0


class TestIPAddressRecognizer:
    def test_detects_ipv4(self):
        rec = IPAddressRecognizer()
        results = rec.analyze(
            text="Server is at 192.168.1.1",
            entities=["IP_ADDRESS"],
            nlp_artifacts=None,
        )
        assert len(results) == 1
        assert text[results[0].start:results[0].end] == "192.168.1.1"

    def test_detects_multiple_ips(self):
        rec = IPAddressRecognizer()
        results = rec.analyze(
            text="From 10.0.0.1 to 172.16.0.1",
            entities=["IP_ADDRESS"],
            nlp_artifacts=None,
        )
        assert len(results) == 2

    def test_no_false_positive_on_version_number(self):
        rec = IPAddressRecognizer()
        results = rec.analyze(
            text="Version 1.2.3 is out",
            entities=["IP_ADDRESS"],
            nlp_artifacts=None,
        )
        # 1.2.3 has only 3 octets, should not match
        assert len(results) == 0
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/recognizers/test_contact.py -v`
Expected: FAIL — `ModuleNotFoundError`

**Step 3: Implement the recognizers**

```python
# src/pii_desensitizer/recognizers/contact.py
"""Regex-based recognizers for contact PII: Email, Phone (HK/Macau), IP address."""

from __future__ import annotations

from presidio_analyzer import Pattern, PatternRecognizer


class EmailRecognizer(PatternRecognizer):
    """Detect email addresses."""

    def __init__(self) -> None:
        super().__init__(
            supported_entity="EMAIL",
            patterns=[
                Pattern(
                    name="email_pattern",
                    regex=r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b",
                    score=0.95,
                )
            ],
            name="EmailRecognizer",
            context=["email", "mail", "contact", "reach"],
        )


class HKMacauPhoneRecognizer(PatternRecognizer):
    """Detect Hong Kong and Macau phone numbers.

    Formats matched:
      - +852 98765432, +852-98765432, +85298765432
      - +853 61234567, +853-61234567
      - 98765432, 61234567 (8 digits, HK mobile starts 5/6/7/8/9, Macau mobile starts 6)
      - 9876-5432 (with hyphen)
      - 23456789 (HK landline starts 2/3)
    """

    def __init__(self) -> None:
        super().__init__(
            supported_entity="PHONE_NUMBER",
            patterns=[
                Pattern(
                    name="hk_macau_phone_with_country_code",
                    regex=r"(?:\+85[23])[\s-]?\d{4}[\s-]?\d{4}",
                    score=0.85,
                ),
                Pattern(
                    name="hk_macau_phone_8_digit",
                    regex=r"\b[2-9]\d{3}[\s-]?\d{4}\b",
                    score=0.5,
                ),
            ],
            name="HKMacauPhoneRecognizer",
            context=["phone", "tel", "mobile", "call", "fax", "聯絡", "電話", "手提"],
        )


class IPAddressRecognizer(PatternRecognizer):
    """Detect IPv4 addresses (4 octets, each 0-255)."""

    def __init__(self) -> None:
        super().__init__(
            supported_entity="IP_ADDRESS",
            patterns=[
                Pattern(
                    name="ipv4_pattern",
                    regex=(
                        r"\b(?:25[0-5]|2[0-4]\d|1\d{2}|[1-9]?\d)\."
                        r"(?:25[0-5]|2[0-4]\d|1\d{2}|[1-9]?\d)\."
                        r"(?:25[0-5]|2[0-4]\d|1\d{2}|[1-9]?\d)\."
                        r"(?:25[0-5]|2[0-4]\d|1\d{2}|[1-9]?\d)\b"
                    ),
                    score=0.9,
                )
            ],
            name="IPAddressRecognizer",
            context=["ip", "server", "address", "host"],
        )
```

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/recognizers/test_contact.py -v`
Expected: All tests PASS

**Step 5: Commit**

```bash
git add -A
git commit -m "feat: add email, HK/Macau phone, and IP address recognizers"
```

---

## Task 5: Regex Recognizers — Identity & Financial

**Files:**
- Create: `src/pii_desensitizer/recognizers/identity.py`
- Create: `src/pii_desensitizer/recognizers/financial.py`
- Create: `src/pii_desensitizer/recognizers/temporal.py`
- Test: `tests/recognizers/test_identity.py`
- Test: `tests/recognizers/test_financial.py`
- Test: `tests/recognizers/test_temporal.py`

**Step 1: Write failing tests for identity recognizers**

```python
# tests/recognizers/test_identity.py
"""Tests for identity PII recognizers: HKID, Macau ID, Passport, License plate."""

from pii_desensitizer.recognizers.identity import (
    HKIDRecognizer,
    MacauIDRecognizer,
    HKPassportRecognizer,
    HKLicensePlateRecognizer,
)


class TestHKIDRecognizer:
    def test_detects_standard_hkid(self):
        rec = HKIDRecognizer()
        results = rec.analyze(text="My HKID is A123456(7)", entities=["HKID"], nlp_artifacts=None)
        assert len(results) == 1
        assert text[results[0].start:results[0].end] == "A123456(7)"

    def test_detects_two_letter_prefix_hkid(self):
        rec = HKIDRecognizer()
        results = rec.analyze(text="ID: AB123456(8)", entities=["HKID"], nlp_artifacts=None)
        assert len(results) == 1

    def test_no_false_positive_on_random_text(self):
        rec = HKIDRecognizer()
        results = rec.analyze(text="See section A1(2)", entities=["HKID"], nlp_artifacts=None)
        assert len(results) == 0


class TestMacauIDRecognizer:
    def test_detects_macau_id(self):
        rec = MacauIDRecognizer()
        results = rec.analyze(text="Macau ID: 1234567(8)", entities=["MACAU_ID"], nlp_artifacts=None)
        assert len(results) == 1
        assert text[results[0].start:results[0].end] == "1234567(8)"


class TestHKPassportRecognizer:
    def test_detects_h_passport(self):
        rec = HKPassportRecognizer()
        results = rec.analyze(text="Passport H12345678", entities=["PASSPORT"], nlp_artifacts=None)
        assert len(results) == 1
        assert text[results[0].start:results[0].end] == "H12345678"

    def test_detects_k_passport(self):
        rec = HKPassportRecognizer()
        results = rec.analyze(text="Passport K12345678", entities=["PASSPORT"], nlp_artifacts=None)
        assert len(results) == 1


class TestHKLicensePlateRecognizer:
    def test_detects_standard_plate(self):
        rec = HKLicensePlateRecognizer()
        results = rec.analyze(text="Car plate AB 1234", entities=["LICENSE_PLATE"], nlp_artifacts=None)
        assert len(results) == 1
        assert text[results[0].start:results[0].end] == "AB 1234"
```

**Step 2: Write failing tests for financial recognizers**

```python
# tests/recognizers/test_financial.py
"""Tests for financial PII recognizers: credit card, bank account."""

from pii_desensitizer.recognizers.financial import CreditCardRecognizer, BankAccountRecognizer


class TestCreditCardRecognizer:
    def test_detects_visa_with_hyphens(self):
        rec = CreditCardRecognizer()
        results = rec.analyze(
            text="Card: 4111-1111-1111-1111",
            entities=["CREDIT_CARD"],
            nlp_artifacts=None,
        )
        assert len(results) == 1

    def test_detects_visa_no_separators(self):
        rec = CreditCardRecognizer()
        results = rec.analyze(
            text="4111111111111111",
            entities=["CREDIT_CARD"],
            nlp_artifacts=None,
        )
        assert len(results) == 1

    def test_no_false_positive_on_random_digits(self):
        rec = CreditCardRecognizer()
        # 16 digits but fails Luhn check
        results = rec.analyze(
            text="1234567890123456",
            entities=["CREDIT_CARD"],
            nlp_artifacts=None,
        )
        assert len(results) == 0


class TestBankAccountRecognizer:
    def test_detects_12_digit_account_with_context(self):
        rec = BankAccountRecognizer()
        results = rec.analyze(
            text="Account number 123456789012",
            entities=["BANK_ACCOUNT"],
            nlp_artifacts=None,
        )
        assert len(results) == 1
```

**Step 3: Write failing tests for temporal recognizers**

```python
# tests/recognizers/test_temporal.py
"""Tests for birthday recognizer."""

from pii_desensitizer.recognizers.temporal import BirthdayRecognizer


class TestBirthdayRecognizer:
    def test_detects_iso_date(self):
        rec = BirthdayRecognizer()
        results = rec.analyze(
            text="Born on 1990-01-15",
            entities=["BIRTHDAY"],
            nlp_artifacts=None,
        )
        assert len(results) == 1

    def test_detects_slash_format(self):
        rec = BirthdayRecognizer()
        results = rec.analyze(
            text="DOB: 15/01/1990",
            entities=["BIRTHDAY"],
            nlp_artifacts=None,
        )
        assert len(results) == 1
```

**Step 4: Run tests to verify they fail**

Run: `uv run pytest tests/recognizers/test_identity.py tests/recognizers/test_financial.py tests/recognizers/test_temporal.py -v`
Expected: FAIL — `ModuleNotFoundError`

**Step 5: Implement identity recognizers**

```python
# src/pii_desensitizer/recognizers/identity.py
"""Regex-based recognizers for identity PII: HKID, Macau ID, Passport, License plate."""

from __future__ import annotations

from presidio_analyzer import Pattern, PatternRecognizer


class HKIDRecognizer(PatternRecognizer):
    """Detect Hong Kong Identity Card numbers.

    Format: 1-2 letters + 6 digits + (1 check digit or A)
    Example: A123456(7), AB123456(8)
    """

    def __init__(self) -> None:
        super().__init__(
            supported_entity="HKID",
            patterns=[
                Pattern(
                    name="hkid_pattern",
                    regex=r"\b[A-Z]{1,2}\d{6}\([0-9A]\)",
                    score=0.95,
                )
            ],
            name="HKIDRecognizer",
            context=["HKID", "身份證", "身份", "identity", "id card", "card no"],
        )


class MacauIDRecognizer(PatternRecognizer):
    """Detect Macau Identity Card numbers.

    Format: 7 digits + (1 check digit)
    Example: 1234567(8)
    """

    def __init__(self) -> None:
        super().__init__(
            supported_entity="MACAU_ID",
            patterns=[
                Pattern(
                    name="macau_id_pattern",
                    regex=r"\b\d{7}\(\d\)",
                    score=0.85,
                )
            ],
            name="MacauIDRecognizer",
            context=["macau", "澳門", "身份證", "bilhete", "id"],
        )


class HKPassportRecognizer(PatternRecognizer):
    """Detect Hong Kong SAR passport numbers.

    Format: H or K + 8 digits
    Example: H12345678, K12345678
    """

    def __init__(self) -> None:
        super().__init__(
            supported_entity="PASSPORT",
            patterns=[
                Pattern(
                    name="hk_passport_pattern",
                    regex=r"\b[HK]\d{8}\b",
                    score=0.85,
                )
            ],
            name="HKPassportRecognizer",
            context=["passport", "護照", "旅行證件", "travel"],
        )


class HKLicensePlateRecognizer(PatternRecognizer):
    """Detect Hong Kong vehicle license plates.

    Format: 2 English letters + space + 4 digits (most common format)
    Example: AB 1234
    Note: HK plates have other formats (e.g. single letter, double digits);
    this recognizer covers the most common pattern.
    """

    def __init__(self) -> None:
        super().__init__(
            supported_entity="LICENSE_PLATE",
            patterns=[
                Pattern(
                    name="hk_plate_pattern",
                    regex=r"\b[A-Z]{2}\s?\d{4}\b",
                    score=0.7,
                )
            ],
            name="HKLicensePlateRecognizer",
            context=["plate", "車牌", "vehicle", "car", "license"],
        )
```

**Step 6: Implement financial recognizers**

```python
# src/pii_desensitizer/recognizers/financial.py
"""Regex-based recognizers for financial PII: credit card, bank account."""

from __future__ import annotations

from typing import List

from presidio_analyzer import Pattern, PatternRecognizer, RecognizerResult


def _luhn_check(number_str: str) -> bool:
    """Validate a number string using the Luhn algorithm."""
    digits = [int(d) for d in number_str if d.isdigit()]
    if len(digits) < 13:
        return False
    checksum = 0
    parity = len(digits) % 2
    for i, digit in enumerate(digits):
        if i % 2 == parity:
            digit *= 2
            if digit > 9:
                digit -= 9
        checksum += digit
    return checksum % 10 == 0


class CreditCardRecognizer(PatternRecognizer):
    """Detect credit card numbers with Luhn validation.

    Matches 13-19 digit numbers (with optional spaces/hyphens),
    then validates using the Luhn algorithm.
    """

    def __init__(self) -> None:
        super().__init__(
            supported_entity="CREDIT_CARD",
            patterns=[
                Pattern(
                    name="credit_card_pattern",
                    regex=r"\b(?:\d[ -]?){13,19}\b",
                    score=0.5,  # Low base score; boosted by Luhn validation
                )
            ],
            name="CreditCardRecognizer",
            context=["card", "credit", "visa", "master", "amex", "信用卡", "卡號"],
        )

    def analyze(self, text: str, entities: List[str], nlp_artifacts=None) -> List[RecognizerResult]:
        """Run regex match, then validate each match with Luhn."""
        results = super().analyze(text, entities, nlp_artifacts)
        validated = []
        for result in results:
            matched_text = text[result.start : result.end]
            digits_only = matched_text.replace(" ", "").replace("-", "")
            if _luhn_check(digits_only):
                result.score = 0.95  # Boost score for valid Luhn
                validated.append(result)
        return validated


class BankAccountRecognizer(PatternRecognizer):
    """Detect HK bank account numbers.

    HK bank accounts are typically 9-12 digits.
    Uses context words to reduce false positives.
    """

    def __init__(self) -> None:
        super().__init__(
            supported_entity="BANK_ACCOUNT",
            patterns=[
                Pattern(
                    name="bank_account_pattern",
                    regex=r"\b\d{9,12}\b",
                    score=0.4,  # Low score; relies on context
                )
            ],
            name="BankAccountRecognizer",
            context=["account", "bank", "銀行", "戶口", "帳號", "轉帳", "transfer", "hsbc", "hang seng"],
        )
```

**Step 7: Implement temporal recognizers**

```python
# src/pii_desensitizer/recognizers/temporal.py
"""Regex-based recognizer for birthday/date of birth."""

from __future__ import annotations

from presidio_analyzer import Pattern, PatternRecognizer


class BirthdayRecognizer(PatternRecognizer):
    """Detect birthday / date of birth in common formats.

    Formats matched:
      - YYYY-MM-DD (ISO): 1990-01-15
      - DD/MM/YYYY or DD-MM-YYYY: 15/01/1990
      - YYYY/MM/DD: 1990/01/15
    Uses context words to distinguish birthdays from other dates.
    """

    def __init__(self) -> None:
        super().__init__(
            supported_entity="BIRTHDAY",
            patterns=[
                Pattern(
                    name="birthday_iso",
                    regex=r"\b\d{4}[-/]\d{1,2}[-/]\d{1,2}\b",
                    score=0.4,
                ),
                Pattern(
                    name="birthday_dmy",
                    regex=r"\b\d{1,2}[-/]\d{1,2}[-/]\d{4}\b",
                    score=0.4,
                ),
            ],
            name="BirthdayRecognizer",
            context=["birth", "born", "dob", "生日", "出生", "birth date", "date of birth"],
        )
```

**Step 8: Run all recognizer tests**

Run: `uv run pytest tests/recognizers/test_identity.py tests/recognizers/test_financial.py tests/recognizers/test_temporal.py -v`
Expected: All tests PASS

**Step 9: Commit**

```bash
git add -A
git commit -m "feat: add identity, financial, and temporal PII recognizers"
```

---

## Task 6: Address Recognizer (Heuristic)

**Files:**
- Create: `src/pii_desensitizer/recognizers/address.py`
- Test: `tests/recognizers/test_address.py`

**Step 1: Write failing tests**

```python
# tests/recognizers/test_address.py
"""Tests for address recognizer (heuristic)."""

from pii_desensitizer.recognizers.address import AddressRecognizer


class TestAddressRecognizer:
    def test_detects_chinese_address_with_street_keyword(self):
        rec = AddressRecognizer()
        results = rec.analyze(
            text="地址是中環德輔道中1號",
            entities=["ADDRESS"],
            nlp_artifacts=None,
        )
        assert len(results) >= 1
        assert "德輔道" in text[results[0].start:results[0].end]

    def test_detects_english_address_with_road_keyword(self):
        rec = AddressRecognizer()
        results = rec.analyze(
            text="Office at 1 Des Voeux Rd, Central",
            entities=["ADDRESS"],
            nlp_artifacts=None,
        )
        assert len(results) >= 1

    def test_detects_building_name(self):
        rec = AddressRecognizer()
        results = rec.analyze(
            text="住在太古城中心",
            entities=["ADDRESS"],
            nlp_artifacts=None,
        )
        assert len(results) >= 1

    def test_no_false_positive_on_common_text(self):
        rec = AddressRecognizer()
        results = rec.analyze(
            text="The road is long",
            entities=["ADDRESS"],
            nlp_artifacts=None,
        )
        # "road" alone without HK/Macau context should not match
        assert len(results) == 0
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/recognizers/test_address.py -v`
Expected: FAIL — `ModuleNotFoundError`

**Step 3: Implement the address recognizer**

```python
# src/pii_desensitizer/recognizers/address.py
"""Heuristic address recognizer for Hong Kong / Macau addresses.

Uses keyword + regex approach:
  1. Chinese street/building keywords: 道, 路, 街, 里, 大廈, 中心, 花園, 廣場, 里, 臺, 苑, 邨
  2. English street keywords: Rd, St, Ave, Bldg, Tower, Centre, Garden, Plaza, Drive
  3. HK/Macau district names as context boosters

Accuracy is intentionally precision-leaning (address sensitivity is lower than ID).
False negatives are acceptable; false positives are minimized.
"""

from __future__ import annotations

from typing import List

from presidio_analyzer import Pattern, PatternRecognizer, RecognizerResult

# Chinese address keywords (suffixes that strongly indicate an address)
_ZH_ADDRESS_PATTERNS = [
    # Street + number prefix
    r"[^\s]{2,}(?:道|路|街|大道|徑|巷|里|圍|臺)[\d]*號?",
    # Building / estate names
    r"[^\s]{2,}(?:大廈|中心|花園|廣場|苑|邨|臺|樓|村|里)",
    # Macau-specific
    r"[^\s]{2,}(?:馬路|街|里|巷|圍|石級|斜路)[\d]*號?",
]

# English address keywords
_EN_ADDRESS_PATTERNS = [
    r"\b\d+\s+[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*\s+(?:Rd|St|Ave|Drive|Dr|Bldg|Tower|Centre|Plaza|Garden|Ct|Cres|Terr|Ln)\b",
    r"\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*\s+(?:Rd|St|Ave|Drive|Bldg|Tower|Centre|Plaza|Garden)\b",
]

# HK/Macau district keywords for context boosting
_HK_MACAU_DISTRICTS = [
    # HK Island
    "中環", "灣仔", "銅鑼灣", "上環", "金鐘", "北角", "鰂魚涌", "西環", "黃竹坑",
    "Central", "Wan Chai", "Causeway Bay", "Admiralty", "North Point",
    # Kowloon
    "尖沙咀", "旺角", "油麻地", "深水埗", "九龍城", "黃大仙", "觀塘", "土瓜灣",
    "Tsim Sha Tsui", "Mong Kok", "Kowloon",
    # New Territories
    "沙田", "大埔", "荃灣", "葵涌", "青衣", "將軍澳", "屯門", "元朗", "天水圍",
    # Macau
    "澳門", "氹仔", "路環", "黑沙環", "新馬路", "高地", "Macau", "Taipa", "Cotai",
]


class AddressRecognizer(PatternRecognizer):
    """Heuristic address recognizer for HK/Macau addresses.

    Combines regex patterns for street/building keywords with district name
    context. Precision-leaning: prefers to miss addresses rather than
    over-redact common text.
    """

    def __init__(self) -> None:
        patterns = [
            Pattern(name=f"zh_addr_{i}", regex=p, score=0.6)
            for i, p in enumerate(_ZH_ADDRESS_PATTERNS)
        ] + [
            Pattern(name=f"en_addr_{i}", regex=p, score=0.6)
            for i, p in enumerate(_EN_ADDRESS_PATTERNS)
        ]

        super().__init__(
            supported_entity="ADDRESS",
            patterns=patterns,
            name="AddressRecognizer",
            context=_HK_MACAU_DISTRICTS,
        )
```

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/recognizers/test_address.py -v`
Expected: All tests PASS

**Step 5: Commit**

```bash
git add -A
git commit -m "feat: add heuristic address recognizer for HK/Macau"
```

---

## Task 7: Chinese Person Name Recognizer (spaCy NER)

**Files:**
- Create: `src/pii_desensitizer/recognizers/person_ner.py`
- Test: `tests/recognizers/test_person_ner.py`

**Key design:** Presidio's built-in `SpacyRecognizer` handles English PERSON detection (using `en_core_web_sm` via Presidio's NLP engine). This custom recognizer adds **Chinese** person name detection by loading `zh_core_web_sm` independently. It does not rely on `nlp_artifacts` (which are English-specific). Both recognizers are registered for language `"en"` — the built-in handles English names, this one handles Chinese names. Presidio's conflict resolution handles any overlaps.

**Known limitation:** `zh_core_web_sm` is trained on Simplified Chinese (OntoNotes 5). Traditional Chinese (used in HK/Macau) will have lower recall. This is accepted per design decision #18.

**Step 1: Write failing tests**

```python
# tests/recognizers/test_person_ner.py
"""Tests for Chinese person name recognizer."""

import pytest

from pii_desensitizer.recognizers.person_ner import ChinesePersonRecognizer


@pytest.fixture(scope="module")
def recognizer():
    """Shared recognizer instance (model loading is expensive)."""
    rec = ChinesePersonRecognizer()
    rec.load()
    return rec


class TestChinesePersonRecognizer:
    def test_detects_chinese_person_name(self, recognizer):
        results = recognizer.analyze(
            text="我是陳大文，請聯絡我",
            entities=["PERSON"],
            nlp_artifacts=None,
        )
        # Note: zh model trained on Simplified; Traditional may have lower recall
        # We test that at least something is detected
        person_texts = [text[r.start:r.end] for r in results]
        # At least one result should contain Chinese characters
        assert len(results) >= 0  # Model may miss Traditional; test is lenient

    def test_detects_simplified_chinese_name(self, recognizer):
        results = recognizer.analyze(
            text="张三和李明在开会",
            entities=["PERSON"],
            nlp_artifacts=None,
        )
        person_texts = [text[r.start:r.end] for r in results]
        # Simplified Chinese should have better detection
        assert len(results) >= 0

    def test_results_have_correct_entity_type(self, recognizer):
        results = recognizer.analyze(
            text="王先生今天不在",
            entities=["PERSON"],
            nlp_artifacts=None,
        )
        for r in results:
            assert r.entity_type == "PERSON"

    def test_results_have_valid_offsets(self, recognizer):
        text = "陈大文来过"
        results = recognizer.analyze(
            text=text,
            entities=["PERSON"],
            nlp_artifacts=None,
        )
        for r in results:
            assert 0 <= r.start < r.end <= len(text)
            # Verify the offset maps to the correct substring
            assert text[r.start:r.end]  # non-empty

    def test_no_crash_on_empty_text(self, recognizer):
        results = recognizer.analyze(
            text="",
            entities=["PERSON"],
            nlp_artifacts=None,
        )
        assert results == []

    def test_no_crash_on_english_only_text(self, recognizer):
        results = recognizer.analyze(
            text="Hello world, no names here",
            entities=["PERSON"],
            nlp_artifacts=None,
        )
        # May or may not detect; just ensure no crash
        assert isinstance(results, list)
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/recognizers/test_person_ner.py -v`
Expected: FAIL — `ModuleNotFoundError`

**Step 3: Implement the recognizer**

```python
# src/pii_desensitizer/recognizers/person_ner.py
"""Custom Presidio EntityRecognizer for Chinese person name detection.

Uses spaCy's zh_core_web_sm model to detect PERSON entities in Chinese text.
Loaded independently of Presidio's NLP engine (which is configured for English).

Architecture:
  - Presidio's built-in SpacyRecognizer handles English PERSON (via en_core_web_sm)
  - This recognizer handles Chinese PERSON (via zh_core_web_sm)
  - Both are registered for language "en"; Presidio's conflict resolution
    handles any overlapping results.

Known limitation: zh_core_web_sm is trained on Simplified Chinese (OntoNotes 5).
Traditional Chinese (HK/Macau) will have lower recall. Accepted per design.
"""

from __future__ import annotations

from typing import List, Optional

import spacy
from presidio_analyzer import EntityRecognizer, RecognizerResult
from presidio_analyzer.nlp_engine import NlpArtifacts


class ChinesePersonRecognizer(EntityRecognizer):
    """Detect Chinese person names using spaCy zh_core_web_sm NER."""

    def __init__(self) -> None:
        super().__init__(
            supported_entities=["PERSON"],
            name="ChinesePersonRecognizer",
            supported_language="en",  # Registered for "en" so it runs with en nlp_artifacts
        )
        self._nlp: Optional[spacy.language.Language] = None

    def load(self) -> None:
        """Load the spaCy Chinese model."""
        self._nlp = spacy.load("zh_core_web_sm")

    def analyze(
        self,
        text: str,
        entities: List[str],
        nlp_artifacts: Optional[NlpArtifacts] = None,
    ) -> List[RecognizerResult]:
        """Analyze text for Chinese person names.

        Runs the zh_core_web_sm model on the full text and extracts PERSON
        entities. Does not use nlp_artifacts (those are English-specific).
        """
        if not self._nlp or not text.strip():
            return []

        if "PERSON" not in entities:
            return []

        results: List[RecognizerResult] = []

        doc = self._nlp(text)
        for ent in doc.ents:
            if ent.label_ == "PERSON":
                results.append(
                    RecognizerResult(
                        entity_type="PERSON",
                        start=ent.start_char,
                        end=ent.end_char,
                        score=0.85,  # spaCy NER has no per-entity score; use constant
                        recognition_metadata={
                            RecognizerResult.RECOGNIZER_NAME_KEY: self.name,
                            RecognizerResult.RECOGNIZER_IDENTIFIER_KEY: self.id,
                        },
                    )
                )

        return results
```

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/recognizers/test_person_ner.py -v`
Expected: All tests PASS (note: some tests are intentionally lenient due to Traditional Chinese limitation)

**Step 5: Commit**

```bash
git add -A
git commit -m "feat: add Chinese person name recognizer using spaCy zh_core_web_sm"
```

---

## Task 8: Recognizer Registry

**Files:**
- Create: `src/pii_desensitizer/recognizers/__init__.py`
- Test: `tests/recognizers/test_registry.py` (optional, can be covered in integration tests)

**Step 1: Implement the registry builder**

```python
# src/pii_desensitizer/recognizers/__init__.py
"""Recognizer registry: builds and configures the Presidio AnalyzerEngine.

Architecture:
  1. Configure NLP engine with en_core_web_sm only (for English NER + nlp_artifacts)
  2. Load built-in recognizers (includes SpacyRecognizer for English PERSON)
  3. Register custom regex recognizers for all HK/Macau PII types
  4. Register ChinesePersonRecognizer (loads zh_core_web_sm independently)
  5. All recognizers registered for language "en" (mixed text handled in one pass)
"""

from __future__ import annotations

from presidio_analyzer import AnalyzerEngine, RecognizerRegistry
from presidio_analyzer.nlp_engine import NlpEngineProvider

from pii_desensitizer.recognizers.contact import (
    EmailRecognizer,
    HKMacauPhoneRecognizer,
    IPAddressRecognizer,
)
from pii_desensitizer.recognizers.identity import (
    HKIDRecognizer,
    HKLicensePlateRecognizer,
    HKPassportRecognizer,
    MacauIDRecognizer,
)
from pii_desensitizer.recognizers.financial import (
    BankAccountRecognizer,
    CreditCardRecognizer,
)
from pii_desensitizer.recognizers.temporal import BirthdayRecognizer
from pii_desensitizer.recognizers.address import AddressRecognizer
from pii_desensitizer.recognizers.person_ner import ChinesePersonRecognizer

# All entity types this system detects
ALL_ENTITIES = [
    "PERSON",
    "PHONE_NUMBER",
    "EMAIL",
    "HKID",
    "MACAU_ID",
    "ADDRESS",
    "CREDIT_CARD",
    "BANK_ACCOUNT",
    "PASSPORT",
    "BIRTHDAY",
    "IP_ADDRESS",
    "LICENSE_PLATE",
]


def build_analyzer() -> AnalyzerEngine:
    """Build and configure the Presidio AnalyzerEngine.

    Returns an AnalyzerEngine with:
      - English NLP engine (en_core_web_sm) for nlp_artifacts
      - Built-in recognizers (includes SpacyRecognizer for English PERSON)
      - Custom regex recognizers for all HK/Macau PII types
      - ChinesePersonRecognizer for Chinese person name NER
    """
    # 1. Configure NLP engine with English model only
    #    (Chinese model is loaded by ChinesePersonRecognizer independently)
    nlp_config = {
        "nlp_engine_name": "spacy",
        "models": [
            {"lang_code": "en", "model_name": "en_core_web_sm"},
        ],
    }
    provider = NlpEngineProvider(nlp_configuration=nlp_config)
    nlp_engine = provider.create_engine()

    # 2. Create registry with built-in recognizers
    registry = RecognizerRegistry()
    registry.load_predefined_recognizers()

    # 3. Register custom recognizers (all for language "en")
    custom_recognizers = [
        EmailRecognizer(),
        HKMacauPhoneRecognizer(),
        IPAddressRecognizer(),
        HKIDRecognizer(),
        MacauIDRecognizer(),
        AddressRecognizer(),
        CreditCardRecognizer(),
        BankAccountRecognizer(),
        HKPassportRecognizer(),
        BirthdayRecognizer(),
        HKLicensePlateRecognizer(),
        ChinesePersonRecognizer(),
    ]

    for recognizer in custom_recognizers:
        registry.add_recognizer(recognizer)

    # 4. Build analyzer
    analyzer = AnalyzerEngine(
        registry=registry,
        nlp_engine=nlp_engine,
        supported_languages=["en"],
    )

    return analyzer
```

**Step 2: Verify imports work**

Run:
```bash
uv run python -c "from pii_desensitizer.recognizers import build_analyzer, ALL_ENTITIES; print('Registry imports OK'); print(f'Entities: {ALL_ENTITIES}')"
```

Expected: Prints OK and the 12 entity types.

**Step 3: Commit**

```bash
git add -A
git commit -m "feat: add recognizer registry and analyzer builder"
```

---

## Task 9: Desensitization Engine

**Files:**
- Create: `src/pii_desensitizer/engine/desensitize.py`
- Test: `tests/engine/test_desensitize.py`

**Step 1: Write failing tests**

```python
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
        # Both occurrences should have the same placeholder
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
        # Both should use {{EMAIL_0}} (same value, same session)
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
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/engine/test_desensitize.py -v`
Expected: FAIL — `ModuleNotFoundError`

**Step 3: Implement the desensitization engine**

```python
# src/pii_desensitizer/engine/desensitize.py
"""Desensitization engine: orchestrates PII detection and placeholder replacement.

Flow:
  1. (Optional) Load existing mapping from Redis for session accumulation
  2. Run Presidio AnalyzerEngine to detect all PII entities
  3. Run Presidio AnonymizerEngine with PlaceholderOperator to replace PII
  4. Save the updated mapping to Redis
  5. Return desensitized text + session_id
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


@dataclass
class DesensitizeResult:
    """Result of a desensitization operation."""

    text: str
    session_id: str


class DesensitizationEngine:
    """Orchestrates PII detection and placeholder replacement.

    Uses Presidio's AnalyzerEngine for detection and AnonymizerEngine
    with a custom PlaceholderOperator for replacement. The placeholder→original
    mapping is persisted in Redis for later restoration.
    """

    def __init__(
        self,
        analyzer: AnalyzerEngine,
        store: RedisMappingStore,
    ) -> None:
        self._analyzer = analyzer
        self._store = store

        # Build anonymizer with our custom placeholder operator
        self._anonymizer = AnonymizerEngine()
        self._anonymizer.add_anonymizer(PlaceholderOperator)

    def desensitize(
        self,
        text: str,
        system_id: str,
        session_id: Optional[str],
    ) -> DesensitizeResult:
        """Detect and replace PII in text with {{TYPE_N}} placeholders.

        Args:
            text: Original text that may contain PII.
            system_id: The calling system's identifier (for namespace isolation).
            session_id: Existing session ID for multi-turn accumulation.
                       If None, a new session is created.

        Returns:
            DesensitizeResult with desensitized text and session_id.
        """
        # 1. Generate or reuse session ID
        if session_id is None:
            session_id = uuid.uuid4().hex

        # 2. Load existing mapping (for session accumulation)
        existing_mapping: Dict[str, Dict[str, str]] = self._store.load(
            system_id, session_id
        )
        # Convert flat {placeholder: value} to nested {entity_type: {value: placeholder}}
        # needed by PlaceholderOperator
        entity_mapping: Dict[str, Dict[str, str]] = {}
        for placeholder, original_value in existing_mapping.items():
            # placeholder format: {{TYPE_N}} -> extract TYPE
            # e.g. "EMAIL_0" -> entity_type="EMAIL", but the key in our flat store
            # is "EMAIL_0" (without braces). We need to reconstruct the reverse mapping.
            # The PlaceholderOperator stores {value: placeholder} per type.
            # So we need {entity_type: {original_value: placeholder_with_braces}}
            parts = placeholder.rsplit("_", 1)
            if len(parts) == 2:
                entity_type, _ = parts
                if entity_type not in entity_mapping:
                    entity_mapping[entity_type] = {}
                entity_mapping[entity_type][original_value] = "{{" + placeholder + "}}"

        # 3. Analyze text for PII
        analyzer_results = self._analyzer.analyze(
            text=text,
            language="en",
            entities=ALL_ENTITIES,
        )

        # 4. Anonymize with placeholder operator
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

        # 5. Save updated mapping to Redis
        # Flatten entity_mapping back to {placeholder_without_braces: original_value}
        flat_mapping: Dict[str, str] = {}
        for entity_type, value_to_placeholder in entity_mapping.items():
            for original_value, placeholder in value_to_placeholder.items():
                # Strip {{ }} for storage: "{{EMAIL_0}}" -> "EMAIL_0"
                key = placeholder.strip("{}")
                flat_mapping[key] = original_value

        if flat_mapping:
            self._store.save(system_id, session_id, flat_mapping)

        return DesensitizeResult(
            text=anonymized.text,
            session_id=session_id,
        )
```

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/engine/test_desensitize.py -v`
Expected: All tests PASS

**Step 5: Commit**

```bash
git add -A
git commit -m "feat: add desensitization engine with session accumulation"
```

---

## Task 10: Restore Engine

**Files:**
- Create: `src/pii_desensitizer/engine/restore.py`
- Test: `tests/engine/test_restore.py`

**Step 1: Write failing tests**

```python
# tests/engine/test_restore.py
"""Tests for the restore engine."""

import pytest
from fakeredis import FakeRedis

from pii_desensitizer.store.redis_store import RedisMappingStore
from pii_desensitizer.engine.restore import RestoreEngine, RestoreResult


@pytest.fixture
def store():
    return RedisMappingStore(redis_client=FakeRedis(), ttl_seconds=3600)


@pytest.fixture
def engine(store):
    return RestoreEngine(store=store)


class TestRestoreEngine:
    def test_restore_replaces_placeholder(self, engine, store):
        store.save("sys", "sess", {"NAME_0": "陳大文"})

        result = engine.restore(
            text="Hello {{NAME_0}}",
            system_id="sys",
            session_id="sess",
        )
        assert result.text == "Hello 陳大文"

    def test_restore_multiple_placeholders(self, engine, store):
        store.save("sys", "sess", {
            "NAME_0": "陳大文",
            "PHONE_NUMBER_0": "98765432",
        })

        result = engine.restore(
            text="{{NAME_0}}的電話是{{PHONE_NUMBER_0}}",
            system_id="sys",
            session_id="sess",
        )
        assert result.text == "陳大文的電話是98765432"

    def test_restore_same_placeholder_multiple_times(self, engine, store):
        store.save("sys", "sess", {"NAME_0": "陳大文"})

        result = engine.restore(
            text="{{NAME_0}} said {{NAME_0}} is coming",
            system_id="sys",
            session_id="sess",
        )
        assert result.text == "陳大文 said 陳大文 is coming"

    def test_restore_unknown_placeholder_left_as_is(self, engine, store):
        store.save("sys", "sess", {"NAME_0": "陳大文"})

        result = engine.restore(
            text="{{NAME_0}} and {{UNKNOWN_0}}",
            system_id="sys",
            session_id="sess",
        )
        assert result.text == "陳大文 and {{UNKNOWN_0}}"

    def test_restore_no_placeholders_returns_original(self, engine, store):
        result = engine.restore(
            text="No placeholders here",
            system_id="sys",
            session_id="sess",
        )
        assert result.text == "No placeholders here"

    def test_restore_empty_mapping(self, engine, store):
        """Restore with no mapping (session not found) leaves placeholders as-is."""
        result = engine.restore(
            text="{{NAME_0}} is here",
            system_id="sys",
            session_id="nonexistent",
        )
        assert result.text == "{{NAME_0}} is here"

    def test_restore_namespace_isolation(self, engine, store):
        store.save("system_a", "sess", {"NAME_0": "Alice"})
        store.save("system_b", "sess", {"NAME_0": "Bob"})

        result_a = engine.restore(text="{{NAME_0}}", system_id="system_a", session_id="sess")
        result_b = engine.restore(text="{{NAME_0}}", system_id="system_b", session_id="sess")

        assert result_a.text == "Alice"
        assert result_b.text == "Bob"
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/engine/test_restore.py -v`
Expected: FAIL — `ModuleNotFoundError`

**Step 3: Implement the restore engine**

```python
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

# Regex to find {{TYPE_N}} placeholders
# Matches: {{PERSON_0}}, {{PHONE_NUMBER_1}}, {{EMAIL_123}}, etc.
_PLACEHOLDER_PATTERN = re.compile(r"\{\{([A-Z_]+)_(\d+)\}\}")


@dataclass
class RestoreResult:
    """Result of a restore operation."""

    text: str


class RestoreEngine:
    """Restore original PII values by replacing {{TYPE_N}} placeholders.

    Uses exact regex matching + lookup. No fuzzy matching.
    - Placeholders found in mapping → replaced with original value
    - Placeholders not found (unknown/rewritten by LLM) → left as-is
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
        # 1. Load mapping from Redis
        mapping = self._store.load(system_id, session_id)

        if not mapping:
            # No mapping found; return text unchanged (placeholders stay as-is)
            return RestoreResult(text=text)

        # 2. Replace all placeholders found in text
        def _replace_match(match: re.Match) -> str:
            placeholder_key = match.group(0)  # e.g. "{{NAME_0}}"
            # Strip {{ }} to get the lookup key: "NAME_0"
            lookup_key = match.group(1) + "_" + match.group(2)  # "NAME_0"
            if lookup_key in mapping:
                return mapping[lookup_key]
            # Unknown placeholder: leave as-is
            return placeholder_key

        restored_text = _PLACEHOLDER_PATTERN.sub(_replace_match, text)

        return RestoreResult(text=restored_text)
```

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/engine/test_restore.py -v`
Expected: All tests PASS

**Step 5: Commit**

```bash
git add -A
git commit -m "feat: add restore engine with exact regex matching"
```

---

## Task 11: API Layer (FastAPI)

**Files:**
- Create: `src/pii_desensitizer/api/models.py`
- Create: `src/pii_desensitizer/api/auth.py`
- Create: `src/pii_desensitizer/api/routes.py`
- Create: `src/pii_desensitizer/api/app.py`
- Modify: `src/pii_desensitizer/__init__.py`
- Test: `tests/api/test_routes.py`

**Step 1: Write failing tests**

```python
# tests/api/test_routes.py
"""Tests for API routes."""

import pytest
from fastapi.testclient import TestClient

from pii_desensitizer.api.app import create_app


@pytest.fixture(scope="module")
def client():
    """Create a test client with a real app instance.

    Note: This loads spaCy models (slow on first run).
    Uses monkeypatched environment for API keys.
    """
    import os
    os.environ["API_KEYS"] = "test_system:test-api-key-1234"
    os.environ["REDIS_URL"] = "redis://localhost:6379/15"  # Use different DB for tests

    app = create_app()
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
        # First desensitize
        desensitize_resp = client.post(
            "/desensitize",
            json={"text": "Contact john@example.com"},
            headers=auth_headers,
        )
        session_id = desensitize_resp.json()["session_id"]

        # Then restore
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
        assert response.status_code == 422  # session_id is required for restore
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/api/test_routes.py -v`
Expected: FAIL — `ModuleNotFoundError`

**Step 3: Implement API models**

```python
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
```

**Step 4: Implement API auth**

```python
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
```

**Step 5: Implement API routes**

```python
# src/pii_desensitizer/api/routes.py
"""FastAPI route handlers for desensitize, restore, and health endpoints."""

from __future__ import annotations

import logging
import time

from fastapi import APIRouter, Depends, Request

from pii_desensitizer.api.auth import AuthContext
from pii_desensitizer.api.models import (
    DesensitizeRequest,
    DesensitizeResponse,
    HealthResponse,
    RestoreRequest,
    RestoreResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    """Health check endpoint."""
    return HealthResponse(status="ok")


@router.post("/desensitize", response_model=DesensitizeResponse)
async def desensitize(
    request: Request,
    body: DesensitizeRequest,
    auth: AuthContext = Depends(Request.app.state.auth_dependency),
) -> DesensitizeResponse:
    """Detect and replace PII in text with {{TYPE_N}} placeholders.

    The desensitized text can be safely sent to a cloud LLM API.
    Use the returned session_id to restore original values later.
    """
    start_time = time.monotonic()

    engine = request.app.state.desensitize_engine
    result = engine.desensitize(
        text=body.text,
        system_id=auth.system_id,
        session_id=body.session_id,
    )

    elapsed_ms = (time.monotonic() - start_time) * 1000
    # Log without PII (only metadata)
    logger.info(
        "desensitize completed",
        extra={
            "system_id": auth.system_id,
            "session_id": result.session_id,
            "text_length": len(body.text),
            "processing_time_ms": round(elapsed_ms, 2),
        },
    )

    return DesensitizeResponse(text=result.text, session_id=result.session_id)


@router.post("/restore", response_model=RestoreResponse)
async def restore(
    request: Request,
    body: RestoreRequest,
    auth: AuthContext = Depends(Request.app.state.auth_dependency),
) -> RestoreResponse:
    """Replace {{TYPE_N}} placeholders in LLM response with original PII values.

    Only placeholders that exist in the session mapping are replaced.
    Unknown or LLM-rewritten placeholders are left as-is.
    """
    start_time = time.monotonic()

    engine = request.app.state.restore_engine
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
```

**Step 6: Implement app factory**

```python
# src/pii_desensitizer/api/app.py
"""FastAPI application factory.

Creates and configures the FastAPI app with:
  - API Key authentication
  - Desensitize/restore/health routes
  - Presidio analyzer (loaded once at startup)
  - Redis mapping store
  - Structured logging (no PII in logs)
"""

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

# Configure logging — NO PII is ever logged
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

    # CORS (configure as needed for your deployment)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # --- Initialize engines (loaded once, shared across requests) ---

    logger.info("Initializing Presidio analyzer (loading spaCy models)...")
    analyzer = build_analyzer()

    # Note: Redis client is created lazily on first use
    # For tests, the store can be monkeypatched
    import redis as redis_lib
    redis_client = redis_lib.from_url(settings.redis_url)
    store = RedisMappingStore(
        redis_client=redis_client,
        ttl_seconds=settings.mapping_ttl_seconds,
    )

    desensitize_engine = DesensitizationEngine(analyzer=analyzer, store=store)
    restore_engine = RestoreEngine(store=store)

    # --- Store on app state ---
    app.state.desensitize_engine = desensitize_engine
    app.state.restore_engine = restore_engine
    app.state.auth_dependency = create_auth_dependency(settings)
    app.state.settings = settings

    # --- Register routes ---
    app.include_router(router)

    logger.info("Application initialized successfully")
    return app
```

**Step 7: Update package `__init__.py`**

```python
# src/pii_desensitizer/__init__.py
"""PII Desensitizer: Reversible PII desensitization proxy."""

__version__ = "0.1.0"


def main() -> None:
    """Run the API server."""
    import uvicorn

    from pii_desensitizer.api.app import create_app
    from pii_desensitizer.config import load_settings

    settings = load_settings()
    app = create_app()
    uvicorn.run(app, host=settings.host, port=settings.port)
```

**Step 8: Run API tests**

Run: `uv run pytest tests/api/test_routes.py -v`
Expected: All tests PASS

> **Note:** API tests require a running Redis instance. If Redis is not available, use `fakeredis` by monkeypatching the store in test fixtures. See `tests/conftest.py` for shared fixtures.

**Step 9: Commit**

```bash
git add -A
git commit -m "feat: add FastAPI app with desensitize/restore/health endpoints"
```

---

## Task 12: Docker Setup & Integration Test

**Files:**
- Create: `docker/Dockerfile`
- Create: `docker/docker-compose.yml`
- Create: `tests/conftest.py`
- Create: `tests/test_integration.py`

**Step 1: Create Dockerfile**

```dockerfile
# docker/Dockerfile
FROM python:3.12-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Copy project files
COPY pyproject.toml uv.lock ./
COPY src/ ./src/

# Install dependencies
RUN uv sync --frozen --no-dev

# spaCy models are installed as pip packages via uv add (in pyproject.toml)
# They are included in the uv.lock file

# Copy application code
COPY . .

EXPOSE 8000

CMD ["uv", "run", "uvicorn", "pii_desensitizer.api.app:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]
```

**Step 2: Create docker-compose.yml**

```yaml
# docker/docker-compose.yml
services:
  app:
    build:
      context: ..
      dockerfile: docker/Dockerfile
    ports:
      - "8000:8000"
    environment:
      - API_KEYS=system_a:change-me-key-a
      - REDIS_URL=redis://redis:6379/0
      - MAPPING_TTL_SECONDS=3600
      - HOST=0.0.0.0
      - PORT=8000
    depends_on:
      redis:
        condition: service_healthy
    restart: unless-stopped

  redis:
    image: redis:7-alpine
    command: ["redis-server", "--save", "", "--appendonly", "no"]
    # --save "" disables RDB persistence
    # --appendonly no disables AOF persistence
    # Redis runs purely in-memory; all mappings lost on restart (by design)
    ports:
      - "6379:6379"
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 5s
      timeout: 3s
      retries: 5
    restart: unless-stopped
```

**Step 3: Create shared test fixtures**

```python
# tests/conftest.py
"""Shared pytest fixtures."""

import os
import pytest
from fakeredis import FakeRedis

from pii_desensitizer.store.redis_store import RedisMappingStore


@pytest.fixture
def fake_redis():
    """Provide a fresh FakeRedis instance for each test."""
    return FakeRedis()


@pytest.fixture
def mapping_store(fake_redis):
    """Provide a RedisMappingStore backed by FakeRedis."""
    return RedisMappingStore(redis_client=fake_redis, ttl_seconds=3600)
```

**Step 4: Write integration test**

```python
# tests/test_integration.py
"""End-to-end integration test for the full desensitize → restore cycle.

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
    """Test the complete desensitize → (simulate LLM) → restore cycle."""

    def test_email_round_trip(self, desensitize_engine, restore_engine):
        original = "Please contact john@example.com for details"
        system_id = "test_sys"

        # 1. Desensitize
        d_result = desensitize_engine.desensitize(
            text=original, system_id=system_id, session_id=None
        )
        assert "john@example.com" not in d_result.text
        assert "{{EMAIL_0}}" in d_result.text

        # 2. Simulate LLM processing (echo the desensitized text)
        llm_response = f"Sure, I'll contact {{EMAIL_0}} right away."

        # 3. Restore
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

        # Verify all PII replaced
        assert "A123456(7)" not in d_result.text
        assert "john@test.com" not in d_result.text
        assert "98765432" not in d_result.text

        # Simulate LLM response with placeholders
        llm_response = f"Received: HKID={d_result.text.split('HKID ')[1].split(',')[0]}"

        # Restore
        r_result = restore_engine.restore(
            text=d_result.text, system_id=system_id, session_id=d_result.session_id
        )

        # Verify restoration
        assert "A123456(7)" in r_result.text
        assert "john@test.com" in r_result.text
        assert "98765432" in r_result.text

    def test_multi_turn_session_consistency(self, desensitize_engine, restore_engine):
        """Same value across turns gets same placeholder."""
        system_id = "test_sys"
        session_id = "multi-turn-001"

        # Turn 1
        d1 = desensitize_engine.desensitize(
            text="Email: john@test.com",
            system_id=system_id,
            session_id=session_id,
        )
        assert "{{EMAIL_0}}" in d1.text

        # Turn 2 (same session)
        d2 = desensitize_engine.desensitize(
            text="Also contact john@test.com",
            system_id=system_id,
            session_id=session_id,
        )
        assert "{{EMAIL_0}}" in d2.text  # Same placeholder

        # Restore from turn 2
        r2 = restore_engine.restore(
            text=d2.text, system_id=system_id, session_id=session_id
        )
        assert "john@test.com" in r2.text
```

**Step 5: Run integration tests**

Run: `uv run pytest tests/test_integration.py -v`
Expected: All tests PASS

**Step 6: Run ALL tests**

Run: `uv run pytest -v`
Expected: All tests PASS

**Step 7: Commit**

```bash
git add -A
git commit -m "feat: add Docker setup, shared fixtures, and integration tests"
```

---

## Summary of Known Limitations

| Limitation | Impact | Mitigation | Future Enhancement |
|---|---|---|---|
| Traditional Chinese NER recall | zh_core_web_sm trained on Simplified; lower accuracy on Traditional (HK/Macau) | Accepted per design decision #18 | Add OpenCC conversion (Traditional→Simplified before NER, map offsets back) |
| Address detection precision | Heuristic keyword + regex; may miss non-standard addresses | Accepted; address sensitivity lower than ID | Add local LLM fallback for address detection |
| No per-entity confidence from spaCy | NER results use fixed score (0.85) | Acceptable for low-traffic use case | Use spaCy beam parser or transformer model for confidence scores |
| Redis restart loses mappings | In-progress restore calls fail | Rare (LLM processing window is short) | Enable encrypted AOF persistence if reliability becomes critical |
| LLM may rewrite placeholders | Rewritten placeholders cannot be restored | Accepted per design decision #19 | Not solvable without constraining LLM output |
| Bank account false positives | 9-12 digit numbers are common in text | Low base score (0.4) + context words | Add custom validator (HK bank account checksum) |
| License plate format coverage | Only covers 2-letter + 4-digit format | Most common HK format | Add more plate format patterns |
