# Backend Subagent — Flask API (Python 3.12)

## Scope
- You work ONLY on files under `backend/`.
- You may READ `mobile/src/types/index.ts` and `mobile/src/services/api.ts` to understand what the client expects, but never modify mobile code.
- You may READ `infra/stacks/data_stack.py` to verify DynamoDB table schemas, but never modify infra code.
- When adding or changing API endpoints, verify the mobile client can consume them.

## Tech Stack
- **Python 3.12**, type hints on ALL function signatures (params + return)
- **Flask 3.1** with app factory pattern (`app/__init__.py`)
- **DynamoDB** via boto3, accessed through helpers in `app/models/dynamo.py`
- **Amazon Bedrock** for Claude streaming (`converse_stream`)
- **Strands Agents** for orchestrated multi-agent flows
- **Gunicorn + gevent** for production (SSE long-lived connections)
- **pytest** for testing

## Project Structure

```
backend/
├── app/
│   ├── __init__.py              # App factory: create_app()
│   ├── config.py                # Config from environment variables
│   ├── auth.py                  # @require_auth, @require_admin decorators
│   ├── models/
│   │   └── dynamo.py            # Table definitions, get_table() helper
│   ├── routes/                  # Flask Blueprints (one per domain)
│   │   ├── auth_routes.py
│   │   ├── chat.py
│   │   ├── conversations.py
│   │   └── ...
│   ├── services/                # Business logic (one per domain)
│   │   ├── bedrock.py
│   │   ├── conversation.py
│   │   ├── user.py
│   │   └── ...
│   └── agents/                  # Agent implementations + registry
│       ├── registry.py
│       └── ...
├── tests/                       # pytest test modules
│   ├── conftest.py              # Shared fixtures (app, client, dynamo)
│   └── test_*.py
├── Dockerfile
├── gunicorn.conf.py
└── requirements.txt
```

### Rules
- Routes handle HTTP concerns only: parse request, call service, format response.
- Services contain business logic: validation, DynamoDB operations, orchestration.
- Models define table schemas and provide access helpers. No business logic in models.
- One Blueprint per domain (auth, chat, conversations, profiles, etc.).
- One service module per domain. Services never import from routes.
- Agents live in `agents/` with a registry pattern for dynamic lookup.

## API Design

### Conventions
- All endpoints prefixed with `/api/`.
- Auth via `Authorization: Bearer <device_token>` header.
- JSON request and response bodies.
- Cursor-based pagination: `?limit=N&cursor=X`, response includes `next_cursor` if more pages exist.
- SSE streaming for chat: `Content-Type: text/event-stream`, events are `data: {json}\n\n`.

### HTTP Status Codes
- `200` — Success (GET, PUT, POST with body).
- `201` — Created (POST that creates a resource) — use when appropriate.
- `204` — No content (DELETE).
- `400` — Bad request (missing fields, invalid input).
- `401` — Unauthorized (missing/invalid token).
- `403` — Forbidden (non-admin accessing admin endpoint, wrong resource owner).
- `404` — Not found (resource doesn't exist).
- `500` — Server error (unhandled exception — should be rare).

### Request Validation
- Check required fields at the top of route handlers.
- Return `400` with `{"error": "descriptive message"}` immediately on validation failure.
- Validate enum values against known sets (e.g., `platform in ("ios", "android", "web")`).
- Never trust client input for authorization decisions — always check ownership server-side.

### Response Format
```python
# Success with data
return jsonify({"conversations": items, "next_cursor": cursor}), 200

# Success with no data
return "", 204

# Error
return jsonify({"error": "Conversation not found"}), 404
```

## DynamoDB Patterns

### Access
- Always use `get_table("TableName")` from `models/dynamo.py` — never create boto3 resources directly in routes or services.
- Table names are prefixed by `TABLE_PREFIX` config (for environment isolation).
- DynamoDB resource is cached per-request in Flask `g`.

### Queries
```python
# Single item
result = get_table("Users").get_item(Key={"user_id": user_id})
item = result.get("Item")  # Always check for None

# Query with GSI, newest first
result = get_table("Conversations").query(
    IndexName="user_conversations-index",
    KeyConditionExpression=Key("user_id").eq(user_id),
    ScanIndexForward=False,
    Limit=limit,
)

# Conditional write (idempotent)
table.put_item(
    Item=item,
    ConditionExpression="attribute_not_exists(pk)",
)
```

### Rules
- Always handle `item is None` after `get_item` — return 404 or raise ValueError.
- Use `ConditionExpression` for idempotent writes where duplicates are possible.
- Catch `ConditionalCheckFailedException` for conditional operations.
- Use `batch_writer()` for bulk deletes (cascade deletion).
- Never use `Scan` in production code — always query by key or GSI.
- Use `ScanIndexForward=False` for newest-first ordering.
- Cursor pagination: pass `ExclusiveStartKey` from client cursor, return `LastEvaluatedKey` as `next_cursor`.

## Authentication & Authorization

### Middleware
```python
@require_auth      # Validates Bearer token, sets g.user_id, g.user_role, g.user_name
@require_admin     # Checks g.user_role == "admin", returns 403 if not
```

### Rules
- Every route (except `/health` and `/api/auth/register`) must use `@require_auth`.
- Admin routes must stack `@require_auth` then `@require_admin`.
- Always check resource ownership in service layer — `conversation.user_id == g.user_id`.
- Never expose user IDs or device tokens in error messages.

## SSE Streaming

### Pattern
```python
def generate():
    try:
        for event in stream_source():
            yield f"data: {json.dumps(event)}\n\n"
    except Exception:
        logger.exception("Streaming error")
        yield f'data: {json.dumps({"type": "error", "content": "..."})}\n\n'

return Response(
    stream_with_context(generate()),
    mimetype="text/event-stream",
    headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
)
```

### Rules
- Always use `stream_with_context` to preserve Flask request context.
- Always set `X-Accel-Buffering: no` to prevent proxy buffering.
- Always yield `error` event on exception — never let the stream die silently.
- Store the final assistant message in DynamoDB inside the generator (on `message_done`).
- Clean up resources (threads, queues) when the generator completes.

## Error Handling

### Route-Level
```python
@bp.route("/api/resource/<id>")
@require_auth
def get_resource(id: str):
    try:
        result = some_service.get(id, g.user_id)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    if result is None:
        return jsonify({"error": "Resource not found"}), 404
    return jsonify(result), 200
```

### Service-Level
- Raise `ValueError` for business rule violations (invalid input, forbidden action).
- Let unexpected exceptions propagate — Flask returns 500 with logging.
- Use `logger.exception()` for errors that need investigation (includes traceback).
- Background threads must catch ALL exceptions — never crash silently.

### Logging
```python
import logging
logger = logging.getLogger(__name__)

logger.info("Created conversation %s for user %s", conv_id, user_id)
logger.warning("Health extraction returned non-JSON for %s", conv_id)
logger.exception("Bedrock call failed")  # Includes traceback
```

### Rules
- One logger per module: `logger = logging.getLogger(__name__)`.
- Use `%s` formatting (not f-strings) in log calls — lazy evaluation.
- `info` for successful operations worth tracking.
- `warning` for degraded but non-fatal conditions.
- `exception` for errors with tracebacks.
- Never log tokens, passwords, PII, or full request bodies.

## Type Hints

### Required On
- All function parameters.
- All function return types.
- Module-level constants when the type isn't obvious.

### Style
```python
# Use modern union syntax
def get_user(user_id: str) -> dict | None:

# Use built-in generics
def list_items(user_id: str, limit: int = 20) -> list[dict]:

# Generator return types for streaming
def stream_chat(messages: list[dict]) -> Generator[dict, None, None]:

# Optional parameters
def create(name: str, config: dict | None = None) -> dict:
```

### Rules
- Use `str | None` not `Optional[str]` (PEP 604, Python 3.10+).
- Use `list[dict]` not `List[Dict]` (PEP 585, Python 3.9+).
- DynamoDB items are typed as `dict` (boto3 returns untyped dicts).
- Never use `Any` — use `dict` for DynamoDB items, `unknown` patterns where possible.

## Testing

### Stack
- **pytest** with `conftest.py` fixtures.
- **DynamoDB Local** in Docker for integration tests.
- **unittest.mock.patch** for external services (Bedrock, S3).

### Patterns
```python
# Fixture hierarchy
@pytest.fixture(scope="session")
def dynamo_client():       # Connect to DynamoDB Local once

@pytest.fixture()
def app(dynamo_client):    # Clean tables, create fresh app per test

@pytest.fixture()
def client(app):           # Flask test client

# Test helpers at module top
def _register(client) -> str:          # Register user, return token
def _auth_headers(token: str) -> dict: # Build Authorization header
def _parse_sse(data: bytes) -> list:   # Parse SSE response events
```

### Rules
- Every new route needs tests covering: happy path, auth failure, validation errors, not-found.
- Mock external services (Bedrock, S3) — never call real AWS in tests.
- Use `@patch` decorator for mocking, targeting the import path in the module under test.
- Test SSE streams by parsing the full response body (not streaming in tests).
- Each test is independent — `conftest.py` cleans all tables between tests.
- Run tests: `cd backend && python -m pytest tests/ -v`.

## Config & Environment

### Adding New Config
1. Add to `Config` class in `app/config.py` with `os.environ.get()` and a sensible default.
2. Access via `current_app.config["KEY"]` in routes/services.
3. Document the variable in the root `CLAUDE.md` Environment Variables section.
4. Add to `ServiceStack` container environment in `infra/stacks/service_stack.py`.
5. Add to test fixtures if needed.

### Feature Flags
- Boolean flags read from env: `os.environ.get("FLAG", "false").lower() == "true"`.
- Check in routes or services to enable/disable features.
- Always provide a safe default (disabled).

## Pre-Completion Checklist

Before considering any task done, verify:
- [ ] `ruff check backend/` passes with zero errors
- [ ] `ruff format backend/ --check` passes
- [ ] `cd backend && python -m pytest tests/ -v` passes
- [ ] All function signatures have type hints (params + return)
- [ ] New routes have corresponding tests
- [ ] New endpoints follow REST conventions and return proper status codes
- [ ] DynamoDB access goes through `get_table()`, not direct boto3
- [ ] No tokens, passwords, or PII in log statements
- [ ] SSE streams handle errors and yield error events
- [ ] New config vars documented and added to infra stack
