# Stateless Desensitization Mode Implementation Plan

**Goal:** Add a `mode` parameter to `POST /desensitize` that supports a stateless mode — returns the placeholder→original mapping directly to the client without writing to Redis. Also make Redis optional at startup so the app can run without it.

**Architecture:** Add `mode: str = "stateful"` to the desensitize request/response. In stateless mode, the engine skips Redis load/save and returns the flat mapping in the response. In `create_app()`, Redis connection becomes optional — if unavailable, `store=None` and stateful mode returns 503.

---

## Decisions (from grilling session)

| # | Decision |
|---|---|
| 1 | `mode` parameter on existing `/desensitize` endpoint (not a new endpoint) |
| 2 | Default mode is `"stateful"` (backward compatible) |
| 3 | Stateless mode returns `session_id: null` and `mapping: {placeholder: original}` |
| 4 | Mapping format is flat: `{"PERSON_0": "何測試", "PHONE_NUMBER_1": "61111111"}` |
| 5 | `mapping` field only present in stateless response (not in stateful) |
| 6 | No multi-turn accumulation in stateless mode (ignore `session_id` if provided) |
| 7 | `/restore` unchanged — stateless clients restore locally |
| 8 | Engine skips Redis entirely in stateless mode (no load, no save) |
| 9 | Redis optional at startup; stateful without Redis returns 503 |

---

## Task 1: Update API Models

**Files:**
- Modify: `src/pii_desensitizer/api/models.py`

**Step 1: Add `mode` to request, `mapping` to response**

```python
class DesensitizeRequest(BaseModel):
    """Request body for POST /desensitize."""

    text: str = Field(..., description="Original text that may contain PII")
    session_id: str | None = Field(
        default=None,
        description="Existing session ID for multi-turn accumulation. "
        "If omitted, a new session is created. Ignored in stateless mode.",
    )
    mode: str = Field(
        default="stateful",
        description="Desensitization mode: 'stateful' (default, uses Redis for "
        "mapping storage) or 'stateless' (returns mapping directly, no Redis).",
    )


class DesensitizeResponse(BaseModel):
    """Response body for POST /desensitize."""

    text: str = Field(..., description="Desensitized text with {{TYPE_N}} placeholders")
    session_id: str | None = Field(
        ..., description="Session ID for later restoration. Null in stateless mode."
    )
    mapping: dict[str, str] | None = Field(
        default=None,
        description="Placeholder→original mapping. Only present in stateless mode.",
    )
```

---

## Task 2: Update DesensitizationEngine

**Files:**
- Modify: `src/pii_desensitizer/engine/desensitize.py`

**Step 1: Add `mapping` to `DesensitizeResult`**

```python
@dataclass
class DesensitizeResult:
    """Result of a desensitization operation."""

    text: str
    session_id: str | None
    mapping: dict[str, str] | None = None
```

**Step 2: Make `store` optional, add `mode` parameter to `desensitize()`**

```python
class DesensitizationEngine:
    def __init__(
        self,
        analyzer: AnalyzerEngine,
        store: RedisMappingStore | None = None,
    ) -> None:
        self._analyzer = analyzer
        self._store = store
        self._anonymizer = AnonymizerEngine()
        self._anonymizer.add_anonymizer(PlaceholderOperator)

    def desensitize(
        self,
        text: str,
        system_id: str,
        session_id: str | None,
        *,
        mode: str = "stateful",
    ) -> DesensitizeResult:
        if mode == "stateful" and self._store is None:
            raise StatefulModeUnavailableError()

        if mode == "stateless":
            return self._desensitize_stateless(text)

        # stateful (existing logic unchanged)
        ...
```

**Step 3: Add `_desensitize_stateless` method**

Extracts the detection + anonymization logic without any Redis calls. Builds the flat mapping and returns it with `session_id=None`.

**Step 4: Add `StatefulModeUnavailableError` exception**

```python
class StatefulModeUnavailableError(Exception):
    """Raised when stateful mode is requested but Redis is not configured."""
```

---

## Task 3: Update Route Handler

**Files:**
- Modify: `src/pii_desensitizer/api/routes.py`

**Step 1: Pass `mode` to engine, handle 503**

```python
@router.post("/desensitize", response_model=DesensitizeResponse)
async def desensitize(
    request: Request,
    body: DesensitizeRequest,
    auth: AuthContext = Depends(get_auth),
) -> DesensitizeResponse:
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

    return DesensitizeResponse(
        text=result.text,
        session_id=result.session_id,
        mapping=result.mapping,
    )
```

Also update `/restore` to return 503 if store is None.

---

## Task 4: Make Redis Optional at Startup

**Files:**
- Modify: `src/pii_desensitizer/config.py`
- Modify: `src/pii_desensitizer/api/app.py`

**Step 1: Make `redis_url` optional in config**

```python
@dataclass(frozen=True)
class Settings:
    api_keys: dict[str, str] = field(default_factory=dict)
    redis_url: str | None = None  # None = Redis disabled
    mapping_ttl_seconds: int = 3600
    host: str = "0.0.0.0"
    port: int = 8000
```

In `load_settings()`:
```python
redis_url_env = os.getenv("REDIS_URL")
redis_url = redis_url_env if redis_url_env else None
```

**Step 2: Conditional Redis initialization in `create_app()`**

```python
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
```

---

## Task 5: Tests

**Files:**
- Modify: `tests/engine/test_desensitize.py`
- Modify: `tests/api/test_routes.py`

**Engine tests:**
- `test_stateless_returns_mapping` — stateless mode returns mapping dict
- `test_stateless_session_id_is_none` — stateless mode returns null session_id
- `test_stateless_does_not_write_to_redis` — store.load() returns empty after stateless call
- `test_stateless_ignores_session_id` — providing session_id in stateless mode has no effect
- `test_stateful_without_store_raises` — calling stateful mode with store=None raises error

**API tests:**
- `test_desensitize_stateless_mode` — POST with `mode: "stateless"` returns mapping
- `test_desensitize_stateless_no_session_id` — response has `session_id: null`
- `test_desensitize_stateful_default` — no mode field → stateful behavior (backward compat)
- `test_desensitize_stateful_no_redis_returns_503` — when store is None, stateful returns 503

---

## Verification Checklist

- [ ] `mode: "stateful"` (default) behaves exactly as before (backward compatible)
- [ ] `mode: "stateless"` returns flat mapping, `session_id: null`
- [ ] Stateless mode does not read from or write to Redis
- [ ] `session_id` provided in stateless mode is silently ignored
- [ ] App starts without Redis if `REDIS_URL` is not set
- [ ] Stateful mode without Redis returns 503 with helpful message
- [ ] `/restore` without Redis returns 503
- [ ] All existing tests pass (no regressions)
- [ ] No real PII in any test case
