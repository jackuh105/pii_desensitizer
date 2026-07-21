# PII Desensitizer

Reversible PII desensitization proxy for cloud LLM API protection. Designed for Macau / Hong Kong Chinese, Portuguese, and English mixed text.

Detects, extracts, and replaces personal information (names, phone numbers, ID cards, emails, addresses, etc.) with `{{TYPE_N}}` placeholders before sending text to a cloud LLM. After LLM processing, restores original values by replacing placeholders back.

## How It Works

### Stateful Mode (default)

Mapping stored in Redis; proxy handles restore via `/restore` endpoint.

```
Client System                    Desensitizer Proxy                 Redis
                                                           (in-memory, TTL=1hr)
      │                                    │
      │  POST /desensitize                 │
      │  "我是陳大文，電話61234567"  ──────▶│  detect PII → replace → store mapping
      │                                    │
      │  {"text":"我是{{PERSON_0}}，       │
      │   "session_id":"abc123"}  ◀──────│
      │                                    │
      │         (send desensitized text to cloud LLM)
      │                                    │
      │  POST /restore                     │
      │  "好的，{{PERSON_0}}已登記"  ──────▶│  regex scan → lookup → replace back
      │                                    │
      │  "好的，陳大文已登記"       ◀──────│
      │                                    │
```

### Stateless Mode

No Redis needed; mapping returned directly to client for local restoration.

```
Client System                    Desensitizer Proxy
      │                                    │
      │  POST /desensitize                 │
      │  {"text":"...", "mode":"stateless"}│
      │  ─────────────────────────────────▶│  detect PII → replace
      │                                    │
      │  {"text":"我是{{PERSON_0}}...",    │
      │   "session_id":null,               │
      │   "mapping":{"PERSON_0":"陳大文"}}│
      │  ◀─────────────────────────────────│
      │                                    │
      │         (send to LLM, restore locally using mapping)
```

## PII Types Detected (10)

| Type | Entity Key | Method | Example |
|---|---|---|---|
| Person Name (Chinese) | `PERSON` | spaCy NER (`zh_core_web_sm` + OpenCC) + context fallback | 陳大文 |
| Person Name (English/Portuguese) | `PERSON` | spaCy NER (`en_core_web_sm`, CJK filtered) + context fallback | ALVES TESTE RODRIGUES |
| Phone (Macau/HK/Mainland) | `PHONE_NUMBER` | Regex (tiered scoring) | +852 98765432, 61234567, 13800138000 |
| Email | `EMAIL` | Regex | john@example.com |
| HKID | `HKID` | Regex | A123456(7) |
| Macau ID | `MACAU_ID` | Regex (tiered scoring) | 1234567(8) |
| Address | `ADDRESS` | Keyword + Regex heuristic (Chinese/English/Portuguese) | 中環德輔道中1號, Rua de Exemplo |
| Credit Card | `CREDIT_CARD` | BIN regex (5 brands) + Luhn | 4111-1111-1111-1111 |
| Passport (HK) | `PASSPORT` | Regex | H12345678 |
| IP Address | `IP_ADDRESS` | Regex | 192.168.1.1 |
| License Plate (HK+Macau) | `LICENSE_PLATE` | Regex | AB 1234, MX-00-00 |

## Quick Start

### Option A: Docker Compose (recommended)

Runs both the API and Redis in containers — nothing to install locally.

```bash
docker compose -f docker/docker-compose.yml up --build
```

API available at `http://localhost:8000`.

### Option B: Local development

Run Redis in Docker, run the API locally with hot reload.

```bash
# 1. Start Redis only
docker compose -f docker/docker-compose.yml up -d redis

# 2. Configure environment
cp .env.example .env

# 3. Install dependencies (including spaCy models)
uv sync

# 4. Run the API with auto-reload
uv run uvicorn pii_desensitizer.api.app:create_app --factory --reload
```

### Option C: Stateless-only (no Redis)

If you only need stateless mode, you can skip Redis entirely:

```bash
# 1. Install dependencies
uv sync

# 2. Configure API keys (no REDIS_URL needed)
echo 'API_KEYS=system_a:your-api-key' > .env

# 3. Run the API
uv run uvicorn pii_desensitizer.api.app:create_app --factory --reload
```

Stateful mode and `/restore` will return 503; stateless `/desensitize` works normally.

## Configuration

All settings are via environment variables (see `.env.example`):

| Variable | Default | Description |
|---|---|---|
| `API_KEYS` | — | Comma-separated `system_id:api_key` pairs |
| `REDIS_URL` | *(none)* | Redis connection URL. If not set, runs in stateless-only mode |
| `MAPPING_TTL_SECONDS` | `3600` | Mapping expiry in seconds (1 hour) |
| `HOST` | `0.0.0.0` | Server bind address |
| `PORT` | `8000` | Server port |

## API Reference

### `POST /desensitize`

Detect and replace PII with `{{TYPE_N}}` placeholders.

#### Stateful mode (default)

```bash
curl -X POST http://localhost:8000/desensitize \
  -H "X-API-Key: change-me-key-a" \
  -H "Content-Type: application/json" \
  -d '{"text": "我是陳大文，電話 +852 61234567，email john@test.com"}'
```

Response:
```json
{
  "text": "我是{{PERSON_0}}，電話{{PHONE_NUMBER_0}}，email {{EMAIL_0}}",
  "session_id": "a1b2c3d4e5f6..."
}
```

**Multi-turn conversations:** Pass the `session_id` from the first call to reuse the same placeholders for the same values across turns.

```bash
curl -X POST http://localhost:8000/desensitize \
  -H "X-API-Key: change-me-key-a" \
  -H "Content-Type: application/json" \
  -d '{"text": "陳大文想改地址", "session_id": "a1b2c3d4e5f6..."}'
# "陳大文" → {{PERSON_0}} (same as first call, same session)
```

#### Stateless mode

No Redis needed; mapping returned directly. Client restores locally using the placeholder regex `\{\{([A-Z_]+)_(\d+)\}\}`.

```bash
curl -X POST http://localhost:8000/desensitize \
  -H "X-API-Key: change-me-key-a" \
  -H "Content-Type: application/json" \
  -d '{"text": "我是陳大文，電話61234567", "mode": "stateless"}'
```

Response:
```json
{
  "text": "我是{{PERSON_0}}，電話{{PHONE_NUMBER_0}}",
  "session_id": null,
  "mapping": {
    "PERSON_0": "陳大文",
    "PHONE_NUMBER_0": "61234567"
  }
}
```

| Field | Stateful | Stateless |
|---|---|---|
| `text` | Desensitized text | Desensitized text |
| `session_id` | UUID for `/restore` | `null` |
| `mapping` | *(absent)* | `{placeholder: original_value}` |

### `POST /restore`

Replace `{{TYPE_N}}` placeholders with original PII values. Only available in stateful mode (when Redis is configured).

```bash
curl -X POST http://localhost:8000/restore \
  -H "X-API-Key: change-me-key-a" \
  -H "Content-Type: application/json" \
  -d '{"text": "已記錄{{PERSON_0}}的資料，電話{{PHONE_NUMBER_0}}", "session_id": "a1b2c3d4e5f6..."}'
```

Response:
```json
{
  "text": "已記錄陳大文的資料，電話61234567"
}
```

Placeholders not found in the mapping (unknown or LLM-rewritten) are left as-is.

### `GET /health`

```bash
curl http://localhost:8000/health
# {"status": "ok"}
```

## Testing

```bash
# Run all tests (144 tests, uses fakeredis — no Redis needed)
uv run pytest -v

# Run specific test suite
uv run pytest tests/recognizers/ -v    # Recognizer tests
uv run pytest tests/engine/ -v         # Engine tests
uv run pytest tests/api/ -v            # API tests
uv run pytest tests/test_integration.py -v  # End-to-end tests
```

## Architecture

```
pii-desensitizer/
├── src/pii_desensitizer/
│   ├── config.py              # Environment-based settings
│   ├── api/
│   │   ├── app.py             # FastAPI app factory (conditional Redis init)
│   │   ├── routes.py          # /desensitize, /restore, /health
│   │   ├── auth.py            # API Key authentication
│   │   └── models.py          # Pydantic request/response schemas
│   ├── recognizers/
│   │   ├── __init__.py        # build_analyzer() — assembles all recognizers
│   │   ├── contact.py         # Email, phone (Macau/HK/mainland), IP address
│   │   ├── identity.py        # HKID, Macau ID, passport, license plate
│   │   ├── financial.py       # Credit card (Luhn), bank account
│   │   ├── temporal.py        # Birthday (unregistered — dates are ambiguous)
│   │   ├── address.py         # Address heuristic (Chinese/English/Portuguese)
│   │   └── person_ner.py      # Person names (zh+en NER, OpenCC, context fallback)
│   ├── engine/
│   │   ├── desensitize.py     # Orchestrates detect → replace (stateful + stateless)
│   │   ├── restore.py         # Regex scan → lookup → replace back
│   │   └── placeholder.py     # Custom {{TYPE_N}} Presidio Operator
│   └── store/
│       └── redis_store.py     # Redis mapping store (namespace + TTL)
├── tests/                     # 144 tests (unit + integration)
├── docker/
│   ├── Dockerfile
│   └── docker-compose.yml
├── docs/plans/                # Implementation plans
└── pyproject.toml
```

### Key Design Decisions

- **Two modes** — stateful (Redis-backed, proxy handles restore) or stateless (mapping returned to client, no Redis)
- **Independent proxy service** — language-agnostic, any system can call the HTTP API
- **Explicit desensitize/restore API** — client calls LLM itself, proxy is LLM-agnostic
- **`{{TYPE_N}}` placeholders** — double braces avoid collision with natural text; type prefix preserves context for LLM
- **Same value = same placeholder** — consistency within a session for multi-turn conversations (stateful mode)
- **Redis optional** — app starts without `REDIS_URL`; stateful mode returns 503 if Redis unavailable
- **Redis in-memory only** — no persistence (`--save "" --appendonly no`), mappings lost on restart (by design, for security)
- **API Key + namespace isolation** — each system gets its own key; mappings are namespaced by `system_id`
- **No PII in logs** — only session ID, PII type counts, and timing are logged
- **Macau-focused phone detection** — 6-prefix mobile, 28-prefix landline, +852/+853/+86 country codes; non-6-prefix 8-digit numbers (error codes, reference numbers) are not matched

### Known Limitations

- **Compound surnames** — Chinese compound surnames (歐陽, 司徒, 司馬) may still be missed by NER even after OpenCC conversion; this is a spaCy segmenter limitation.
- **Bank account numbers** — not detected. Bank account numbers have no reliable format (vary by bank, 9-19 digits), making regex detection highly prone to false positives.
- **Birthday dates** — not detected. Dates in government forms are usually timestamps or deadlines, not birthdays. Too ambiguous without context.
- **Address detection** — heuristic keyword + regex; may miss non-standard addresses. Future: add LLM fallback.
- **Redis restart** — in-progress restore calls fail if Redis restarts (acceptable: LLM processing window is short). Not applicable to stateless mode.

## Tech Stack

- **Python 3.12** + **FastAPI** + **uvicorn**
- **Microsoft Presidio** (presidio-analyzer + presidio-anonymizer)
- **spaCy** (`en_core_web_sm` + `zh_core_web_sm`)
- **OpenCC** (`opencc-python-reimplemented`) — Traditional→Simplified conversion before Chinese NER
- **Redis 7** (in-memory, no persistence) — optional in stateless-only mode
- **Docker Compose** for deployment
