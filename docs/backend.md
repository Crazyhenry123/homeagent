# Backend Engineering Documentation

## 1. Architecture Overview

### Tech Stack

- **Runtime**: Python 3.12
- **Framework**: Flask 3.1 with app factory pattern
- **WSGI Server**: Gunicorn with gevent worker class
- **Database**: Amazon DynamoDB (17 tables, on-demand billing)
- **AI**: Amazon Bedrock (Claude via `converse_stream`), Amazon Nova Sonic (voice)
- **Agent Framework**: Strands Agents SDK
- **Auth**: AWS Cognito JWT + device token fallback
- **Object Storage**: S3 (health documents, chat media, transcribe output)
- **Container**: Docker (Python 3.12-slim), deployed on ECS Fargate

### App Factory Pattern

The Flask application is created via `create_app()` in `/home/ubuntu/homeagent/backend/app/__init__.py`. This function:

1. Instantiates a `Flask` app and loads `Config` (environment-driven).
2. Enables CORS globally via `flask-cors`.
3. Calls `init_tables()` -- creates DynamoDB tables when using DynamoDB Local, and seeds the admin invite code.
4. Calls `seed_builtin_templates()` -- ensures built-in agent templates exist in the `AgentTemplates` table.
5. Registers 16+ blueprints with their URL prefixes.
6. Conditionally initializes the voice WebSocket endpoint if `VOICE_ENABLED=true`.

### Gunicorn Configuration

Defined in `/home/ubuntu/homeagent/backend/gunicorn.conf.py`:

```python
bind = "0.0.0.0:5000"
worker_class = "gevent"           # async greenlet workers for SSE + WebSocket
workers = multiprocessing.cpu_count() * 2 + 1
timeout = 300                     # 5 min -- needed for long SSE streams
keepalive = 5
```

The `gevent` worker class is required because the backend serves long-lived SSE streams and WebSocket connections that would block sync workers.

### Request Lifecycle

1. Gunicorn receives the HTTP request and dispatches it to a gevent greenlet.
2. Flask matches the URL to a blueprint route.
3. The `@require_auth` decorator (or variant) extracts the `Authorization: Bearer <token>` header, validates it (Cognito JWT first, device token fallback), and populates `flask.g` with user context.
4. The route handler calls into services (`app/services/`) which interact with DynamoDB via `get_table()`.
5. `get_table()` calls `get_dynamodb()`, which caches a `boto3.resource("dynamodb")` on `flask.g` (per-request scope).
6. For streaming endpoints (chat), a `Response` with `mimetype="text/event-stream"` is returned using `stream_with_context`.

### Docker

The Dockerfile (`/home/ubuntu/homeagent/backend/Dockerfile`) builds a slim image, runs as non-root `appuser`, exposes port 5000, includes a health check hitting `/health`, and launches Gunicorn.

---

## 2. Authentication System

All auth logic lives in `/home/ubuntu/homeagent/backend/app/auth.py`.

### Dual Auth Strategy

The system supports two authentication mechanisms, tried in order:

1. **Cognito JWT** -- For web/mobile users who sign up with email + password. The `access_token` from Cognito is sent as a Bearer token.
2. **Device Token** -- For invite-code-based registration (legacy/device flow). A random `secrets.token_urlsafe(48)` is generated at registration and stored in the `Devices` table.

### Cognito JWT Validation (`_try_cognito_auth`)

1. Calls `verify_token()` in `app/services/cognito.py`.
2. Fetches JWKS from `https://cognito-idp.{region}.amazonaws.com/{pool_id}/.well-known/jwks.json` (cached 1 hour).
3. Decodes the JWT with RS256, verifying issuer and `token_use == "access"`.
4. Extracts the `sub` claim and looks up the user via the `cognito_sub-index` GSI on the `Users` table.
5. Sets `g.user_id`, `g.user_name`, `g.user_role`, `g.cognito_sub`.

### Device Token Auth (`_try_device_auth`)

1. Queries the `Devices` table via the `device_token-index` GSI.
2. Looks up the associated user in the `Users` table.
3. Sets `g.user_id`, `g.user_name`, `g.user_role`, `g.device_id`.

### Decorators

| Decorator | Purpose | Populates on `g` |
|-----------|---------|-----------------|
| `@require_auth` | Accepts either Cognito JWT or device token | `user_id`, `user_name`, `user_role`, optionally `cognito_sub` or `device_id` |
| `@require_cognito_auth` | Cognito JWT only (used for signup-related flows) | `user_id`, `user_name`, `user_role`, `cognito_sub` |
| `@require_admin` | Must be stacked after `@require_auth`. Checks `g.user_role in ("admin", "owner")` | (none additional) |
| `@require_owner` | Must be stacked after `@require_auth`. Checks `g.user_role == "owner"` | (none additional) |

### Roles

- **owner** -- Created via Cognito signup (`/api/auth/signup`). Owns a family.
- **admin** -- Created via invite code with `is_admin=True` (seeded by `ADMIN_INVITE_CODE`).
- **member** -- Created via standard invite code.

Both `admin` and `owner` pass the `@require_admin` check.

---

## 3. API Routes

All routes are prefixed with `/api/` unless otherwise noted. Authentication is via `Authorization: Bearer <token>` header.

### 3.1 Health Check

**Blueprint**: `health_bp` (no prefix)

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/health` | None | Returns `{"status": "healthy"}` |

### 3.2 Auth Routes

**Blueprint**: `auth_bp` (prefix: `/api/auth`)

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| POST | `/api/auth/register` | None | Register via invite code (device token flow) |
| POST | `/api/auth/signup` | None | Register new owner with email/password via Cognito |
| POST | `/api/auth/confirm` | None | Confirm email verification code |
| POST | `/api/auth/login` | None | Authenticate with email/password, returns Cognito tokens |
| POST | `/api/auth/resend-code` | None | Resend email verification code |
| POST | `/api/auth/verify` | `require_auth` | Validate token, returns user info |

**POST /api/auth/register**
```
Request:  { "invite_code": str, "device_name": str, "platform": "ios"|"android"|"web", "display_name": str }
Response: { "user_id": str, "device_token": str }  (201)
```

**POST /api/auth/signup**
```
Request:  { "email": str, "password": str, "display_name": str }
Response: { "user_id": str, "email": str }  (201)
```

**POST /api/auth/confirm**
```
Request:  { "email": str, "confirmation_code": str }
Response: { "confirmed": true }
```

**POST /api/auth/login**
```
Request:  { "email": str, "password": str }
Response: { "tokens": { "id_token", "access_token", "refresh_token" }, "user": { "user_id", "name", "email", "role" } }
```

**POST /api/auth/verify**
```
Response: { "valid": true, "user_id": str, "name": str, "role": str }
```

### 3.3 Session Routes

**Blueprint**: `session_bp` (prefix: `/api`)

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/api/session` | `require_auth` | Bootstrap all user data in a single call |

**GET /api/session**

Returns an aggregated payload that replaces 7 separate API calls on app startup:

```json
{
  "user": { "user_id", "name", "email", "role" },
  "profile": { "display_name", "family_role", "preferences", "health_notes", "interests", ... },
  "family": { "info": { "family_id", "name", "owner_user_id" }, "members": [...] } | null,
  "agents": {
    "available": [{ "template_id", "agent_type", "name", "description", "enabled": bool, ... }],
    "my_configs": [{ "user_id", "agent_type", "enabled", "config", ... }],
    "agent_types": { ... }  // only for admin/owner
  },
  "permissions": [{ "user_id", "permission_type", "config", "status", ... }],
  "conversations": {
    "items": [{ "conversation_id", "title", "updated_at", ... }],
    "next_cursor": str | null
  }
}
```

### 3.4 Chat Routes

**Blueprint**: `chat_bp` (prefix: `/api`)

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| POST | `/api/chat` | `require_auth` | Send a message, receive SSE stream |

**POST /api/chat**

```
Request: {
  "message": str,              // text content (optional if media provided)
  "conversation_id": str?,     // omit to auto-create
  "media": [str]?              // array of media_id from upload-image
}
```

Response: `text/event-stream` with SSE events:

```
data: {"type": "text_delta", "content": "partial text...", "conversation_id": "..."}

data: {"type": "message_done", "conversation_id": "...", "message_id": "..."}

data: {"type": "error", "content": "error message"}
```

**Flow**:
1. Resolves media attachments (images become Bedrock content blocks, audio gets transcribed via AWS Transcribe and prepended as text).
2. Creates conversation if `conversation_id` is not provided (auto-titled from first 50 chars of message).
3. Stores user message in `Messages` table.
4. Loads last 50 messages as history for Bedrock.
5. Streams response via `stream_chat()` (direct Bedrock) or `stream_agent_chat()` (Strands orchestrator, if `USE_AGENT_ORCHESTRATOR=true`).
6. Stores assistant message with token count.
7. Fires a background thread for health observation extraction (if `HEALTH_EXTRACTION_ENABLED=true`).

### 3.5 Conversation Routes

**Blueprint**: `conversations_bp` (prefix: `/api`)

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/api/conversations` | `require_auth` | List user's conversations (paginated) |
| GET | `/api/conversations/<conversation_id>/messages` | `require_auth` | Get messages for a conversation |
| DELETE | `/api/conversations/<conversation_id>` | `require_auth` | Delete a conversation and its messages |

**GET /api/conversations**
```
Query: ?limit=20&cursor=<updated_at>
Response: { "conversations": [...], "next_cursor": str? }
```

**GET /api/conversations/<id>/messages**
```
Query: ?limit=50&cursor=<sort_key>
Response: { "messages": [...], "next_cursor": str? }
```

Ownership is enforced: users can only access their own conversations.

### 3.6 Chat Media / Upload Routes

**Blueprint**: `chat_media_bp` (prefix: `/api`)

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| POST | `/api/chat/upload-image` | `require_auth` | Get a presigned S3 URL for image/audio upload |

**POST /api/chat/upload-image**
```
Request:  { "content_type": str, "file_size": int }
Response: { "media_id": str, "upload_url": str }  (201)
```

Allowed content types: `image/jpeg`, `image/png`, `image/gif`, `image/webp`, `audio/wav`.
Max sizes: 5 MB for images, 25 MB for audio (configurable).

The client uploads the file directly to S3 using the presigned URL, then includes `media_id` in the chat request's `media` array. Media records have a TTL of 1 hour; once attached to a message, the TTL is removed.

### 3.7 Member Agent Routes

**Blueprint**: `member_agent_bp` (prefix: `/api`)

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/api/agents/available` | `require_auth` | List agents available to this member, with enabled status |
| GET | `/api/agents/my` | `require_auth` | List member's agent configs |
| PUT | `/api/agents/my/<agent_type>` | `require_auth` | Enable an agent for yourself |
| DELETE | `/api/agents/my/<agent_type>` | `require_auth` | Disable an agent (keeps config, sets `enabled=false`) |

### 3.8 Admin Routes

#### Invite Codes

**Blueprint**: `admin_bp` (prefix: `/api/admin`)

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| POST | `/api/admin/invite-codes` | `require_auth` + `require_admin` | Generate an invite code |

#### Agent Config Management

**Blueprint**: `agent_config_bp` (prefix: `/api/admin`)

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/api/admin/agents/types` | `require_auth` + `require_admin` | List all agent type definitions |
| GET | `/api/admin/agents/<user_id>` | `require_auth` + `require_admin` | List agent configs for a member |
| PUT | `/api/admin/agents/<user_id>/<agent_type>` | `require_auth` + `require_admin` | Configure/enable agent for a member |
| DELETE | `/api/admin/agents/<user_id>/<agent_type>` | `require_auth` + `require_admin` | Remove agent config for a member |

**PUT /api/admin/agents/<user_id>/<agent_type>**
```
Request: { "enabled": bool, "config": { ... } }
```

#### Agent Template Management

**Blueprint**: `agent_template_bp` (prefix: `/api/admin`)

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/api/admin/agent-templates` | `require_auth` + `require_admin` | List all templates |
| POST | `/api/admin/agent-templates` | `require_auth` + `require_admin` | Create a new template |
| PUT | `/api/admin/agent-templates/<template_id>` | `require_auth` + `require_admin` | Update a template |
| DELETE | `/api/admin/agent-templates/<template_id>` | `require_auth` + `require_admin` | Delete a template (rejects built-ins, cascades to AgentConfigs) |

**POST /api/admin/agent-templates**
```
Request: {
  "name": str,
  "agent_type": str,       // unique slug
  "description": str,
  "system_prompt": str,
  "default_config": {}?,
  "available_to": "all" | [user_id, ...]?
}
```

#### Profile Management

**Blueprint**: `admin_profiles_bp` (prefix: `/api/admin`)

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/api/admin/profiles` | `require_auth` + `require_admin` | List all member profiles |
| GET | `/api/admin/profiles/<user_id>` | `require_auth` + `require_admin` | Get a member's profile |
| PUT | `/api/admin/profiles/<user_id>` | `require_auth` + `require_admin` | Update a member's profile |
| DELETE | `/api/admin/profiles/<user_id>` | `require_auth` + `require_admin` | Delete a member and all their data |

DELETE cascades across: Devices, Conversations, Messages, AgentConfigs, FamilyRelationships, MemberPermissions, HealthRecords, HealthObservations, HealthDocuments, MemberProfiles, Users.

#### Family Tree

**Blueprint**: `family_tree_bp` (prefix: `/api/admin`)

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/api/admin/family/relationships` | `require_auth` + `require_admin` | Get all relationships (full tree) |
| GET | `/api/admin/family/relationships/<user_id>` | `require_auth` + `require_admin` | Get relationships for a user |
| POST | `/api/admin/family/relationships` | `require_auth` + `require_admin` | Create a bidirectional relationship |
| DELETE | `/api/admin/family/relationships/<user_id>/<related_user_id>` | `require_auth` + `require_admin` | Delete a relationship (both directions) |

**POST /api/admin/family/relationships**
```
Request: { "user_id": str, "related_user_id": str, "relationship_type": str }
```

Valid relationship types: `parent_of`, `child_of`, `spouse_of`, `sibling_of`. Relationships are stored bidirectionally with automatic inverse mapping (e.g., `parent_of` creates a corresponding `child_of` in the other direction).

#### Health Records (Admin)

**Blueprint**: `admin_health_records_bp` (prefix: `/api/admin`)

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/api/admin/health-records/<user_id>` | admin | List health records (optional `?record_type=` filter) |
| POST | `/api/admin/health-records/<user_id>` | admin | Create a health record |
| GET | `/api/admin/health-records/<user_id>/<record_id>` | admin | Get a specific record |
| PUT | `/api/admin/health-records/<user_id>/<record_id>` | admin | Update a record |
| DELETE | `/api/admin/health-records/<user_id>/<record_id>` | admin | Delete a record |
| GET | `/api/admin/health-records/<user_id>/summary` | admin | Get health summary grouped by type |
| GET | `/api/admin/health-records/<user_id>/<record_id>/audit` | admin | Get audit log for a record |
| GET | `/api/admin/health-records/<user_id>/audit-log` | admin | Get all audit entries for a user |

**POST /api/admin/health-records/<user_id>**
```
Request: { "record_type": str, "data": { ... } }
```

Valid record types: `condition`, `medication`, `allergy`, `appointment`, `vital`, `immunization`, `growth`.

#### Health Reports

**Blueprint**: `health_reports_bp` (prefix: `/api/admin`)

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| POST | `/api/admin/health-reports/<user_id>/generate` | admin | Generate a health report from records + observations |

Response includes profile info, records summary grouped by type, observations grouped by category, and total observation count.

#### Health Documents

**Blueprint**: `admin_health_documents_bp` (prefix: `/api/admin`)

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/api/admin/health-documents/<user_id>` | admin | List documents |
| POST | `/api/admin/health-documents/<user_id>/upload` | admin | Create metadata + get presigned upload URL |
| GET | `/api/admin/health-documents/<user_id>/<document_id>/download` | admin | Get metadata + presigned download URL |
| DELETE | `/api/admin/health-documents/<user_id>/<document_id>` | admin | Delete document (S3 + DynamoDB) |

**POST /api/admin/health-documents/<user_id>/upload**
```
Request: { "filename": str, "content_type": str, "file_size": int, "record_id"?: str, "description"?: str }
```
Allowed types: `image/jpeg`, `image/png`, `image/heic`, `image/heif`, `application/pdf`. Max 10 MB.

### 3.9 Permission Routes

**Blueprint**: `permission_bp` (prefix: `/api`)

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/api/permissions` | `require_auth` | Get my active permissions |
| PUT | `/api/permissions/<permission_type>` | `require_auth` | Grant/update a permission |
| DELETE | `/api/permissions/<permission_type>` | `require_auth` | Revoke a permission |
| GET | `/api/permissions/agent-required/<agent_type>` | `require_auth` | Get required permissions for an agent |

Valid permission types: `email_access`, `calendar_access`, `health_data`, `medical_records`.

**PUT /api/permissions/<permission_type>**
```
Request: { "config": { ... } }
```

Config schemas vary by type:
- `email_access`: `{ "email_address": str, "provider": str }`
- `calendar_access`: `{ "calendar_id": str, "provider": str }`
- `health_data`: `{ "consent_given": bool, "data_sources": [str] }`
- `medical_records`: `{ "folder_path": str, "s3_prefix": str }`

### 3.10 Family Routes

**Blueprint**: `family_bp` (prefix: `/api/family`)

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| POST | `/api/family` | `require_auth` + `require_admin` | Create a family |
| GET | `/api/family` | `require_auth` | Get family info + members |
| POST | `/api/family/invite` | `require_auth` + `require_admin` | Invite a member by email |
| GET | `/api/family/invites` | `require_auth` + `require_admin` | List pending invites |
| DELETE | `/api/family/invites/<code>` | `require_auth` + `require_admin` | Cancel a pending invite |

**POST /api/family**
```
Request: { "name": str }
Response: { "family_id", "name", "owner_user_id", "created_at" }  (201)
```

**POST /api/family/invite**
```
Request: { "email": str, "family_name"?: str }
Response: { "code": str, "expires_at": str, "email_sent": bool, "family_name": str, ... }  (201)
```
Invite emails are sent via AWS SES if `SES_ENABLED=true`.

### 3.11 Profile Routes (Self-Service)

**Blueprint**: `profiles_bp` (prefix: `/api`)

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/api/profiles/me` | `require_auth` | Get my profile (auto-creates if missing) |
| PUT | `/api/profiles/me` | `require_auth` | Update my profile |

Updatable fields: `display_name`, `family_role`, `preferences`, `health_notes`, `interests`.

### 3.12 Health Records (Self-Access)

**Blueprint**: `health_records_bp` (prefix: `/api`)

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/api/health-records/me` | `require_auth` | List my health records (optional `?record_type=`) |
| GET | `/api/health-records/me/summary` | `require_auth` | Get my health summary |

### 3.13 Voice Routes

**Blueprint**: `voice_bp` (prefix: `/api`), only registered when `VOICE_ENABLED=true`

| Protocol | Path | Auth | Description |
|----------|------|------|-------------|
| WebSocket | `/api/voice?token=<device_token>&conversation_id=<id>` | Query param token | Bidirectional voice streaming |

See section 8 for details.

---

## 4. Data Models

All tables are defined in `/home/ubuntu/homeagent/backend/app/models/dynamo.py` in the `TABLE_DEFINITIONS` dict. Tables use on-demand billing (PAY_PER_REQUEST). IDs use ULID (time-sortable) except device IDs which use UUID4.

### 4.1 Users

| Attribute | Type | Key |
|-----------|------|-----|
| `user_id` | S | PK (HASH) |
| `name` | S | |
| `email` | S | GSI: `email-index` (HASH) |
| `cognito_sub` | S | GSI: `cognito_sub-index` (HASH) |
| `role` | S | "owner", "admin", or "member" |
| `family_id` | S | Set when user joins a family |
| `created_at` | S | ISO 8601 |

### 4.2 Devices

| Attribute | Type | Key |
|-----------|------|-----|
| `device_id` | S | PK (HASH) |
| `user_id` | S | GSI: `user_id-index` (HASH) |
| `device_token` | S | GSI: `device_token-index` (HASH) |
| `platform` | S | "ios", "android", or "web" |
| `device_name` | S | |
| `registered_at` | S | ISO 8601 |

### 4.3 InviteCodes

| Attribute | Type | Key |
|-----------|------|-----|
| `code` | S | PK (HASH) |
| `invited_email` | S | GSI: `invited_email-index` (HASH) |
| `created_by` | S | User ID of creator |
| `status` | S | "active", "used", "cancelled" |
| `is_admin` | BOOL | |
| `family_id` | S | Optional -- auto-join family on registration |
| `invite_type` | S | "email" or "code" |
| `expires_at` | S | ISO 8601 |
| `created_at` | S | ISO 8601 |

### 4.4 Families

| Attribute | Type | Key |
|-----------|------|-----|
| `family_id` | S | PK (HASH) |
| `owner_user_id` | S | GSI: `owner-index` (HASH) |
| `name` | S | |
| `created_at` | S | ISO 8601 |

### 4.5 FamilyMembers

| Attribute | Type | Key |
|-----------|------|-----|
| `family_id` | S | PK (HASH) |
| `user_id` | S | SK (RANGE) |
| `role` | S | "owner" or "member" |
| `joined_at` | S | ISO 8601 |

### 4.6 Conversations

| Attribute | Type | Key |
|-----------|------|-----|
| `conversation_id` | S | PK (HASH) |
| `user_id` | S | GSI: `user_conversations-index` (HASH) |
| `updated_at` | S | GSI: `user_conversations-index` (RANGE) |
| `title` | S | Auto-generated from first message (50 chars) |
| `created_at` | S | ISO 8601 |

### 4.7 Messages

| Attribute | Type | Key |
|-----------|------|-----|
| `conversation_id` | S | PK (HASH) |
| `sort_key` | S | SK (RANGE) -- format: `{iso_timestamp}#{message_id}` |
| `message_id` | S | ULID |
| `role` | S | "user" or "assistant" |
| `content` | S | Message text |
| `model` | S | Optional -- Bedrock model ID |
| `tokens_used` | N | Optional -- total tokens (input + output) |
| `media` | L | Optional -- list of `{media_id, content_type}` |
| `created_at` | S | ISO 8601 |

### 4.8 MemberProfiles

| Attribute | Type | Key |
|-----------|------|-----|
| `user_id` | S | PK (HASH) |
| `display_name` | S | |
| `family_role` | S | e.g., "father", "grandmother" |
| `preferences` | M | Arbitrary key-value map |
| `health_notes` | S | Free-text health notes |
| `interests` | L | List of strings |
| `role` | S | "owner", "admin", or "member" |
| `created_at` | S | ISO 8601 |
| `updated_at` | S | ISO 8601 |

### 4.9 AgentConfigs

| Attribute | Type | Key |
|-----------|------|-----|
| `user_id` | S | PK (HASH) |
| `agent_type` | S | SK (RANGE) -- e.g., "health_advisor" |
| `enabled` | BOOL | |
| `config` | M | Merged template defaults + user overrides |
| `updated_at` | S | ISO 8601 |

### 4.10 AgentTemplates

| Attribute | Type | Key |
|-----------|------|-----|
| `template_id` | S | PK (HASH) -- ULID or `builtin-{agent_type}` |
| `agent_type` | S | GSI: `agent_type-index` (HASH) -- unique slug |
| `name` | S | Display name |
| `description` | S | |
| `system_prompt` | S | Prompt for the agent |
| `default_config` | M | Default config merged into AgentConfigs |
| `required_permissions` | L | List of permission_type strings required |
| `is_builtin` | BOOL | True for system-seeded agents |
| `is_default` | BOOL | Auto-enabled for new users |
| `available_to` | S or L | `"all"` or list of user IDs |
| `created_by` | S | User ID or "system" |
| `created_at` | S | ISO 8601 |
| `updated_at` | S | ISO 8601 |

### 4.11 FamilyRelationships

| Attribute | Type | Key |
|-----------|------|-----|
| `user_id` | S | PK (HASH) |
| `related_user_id` | S | SK (RANGE) |
| `relationship_type` | S | "parent_of", "child_of", "spouse_of", "sibling_of" |
| `created_at` | S | ISO 8601 |

Stored bidirectionally: creating `A parent_of B` also creates `B child_of A`.

### 4.12 HealthRecords

| Attribute | Type | Key |
|-----------|------|-----|
| `user_id` | S | PK (HASH) |
| `record_id` | S | SK (RANGE) -- ULID |
| `record_type` | S | GSI: `record_type-index` (HASH: `user_id`, RANGE: `record_type`) |
| `data` | M | Arbitrary record payload |
| `created_by` | S | User ID who created it |
| `created_at` | S | ISO 8601 |
| `updated_at` | S | ISO 8601 |

Valid record types: `condition`, `medication`, `allergy`, `appointment`, `vital`, `immunization`, `growth`.

### 4.13 HealthAuditLog

| Attribute | Type | Key |
|-----------|------|-----|
| `record_id` | S | PK (HASH) |
| `audit_sk` | S | SK (RANGE) -- format: `{iso_timestamp}#{audit_id}` |
| `audit_id` | S | ULID |
| `user_id` | S | GSI: `user-audit-index` (HASH) |
| `created_at` | S | GSI: `user-audit-index` (RANGE) |
| `actor_id` | S | Who performed the action |
| `action` | S | "create", "update", or "delete" |
| `changes` | M | Optional -- `{before, after}` for updates |
| `record_snapshot` | M | Optional -- full record for create/delete |

### 4.14 HealthObservations

| Attribute | Type | Key |
|-----------|------|-----|
| `user_id` | S | PK (HASH) |
| `observation_id` | S | SK (RANGE) -- ULID |
| `category` | S | GSI: `category-index` (HASH: `user_id`, RANGE: `category`) |
| `summary` | S | Brief one-sentence summary |
| `detail` | S | Optional longer description |
| `confidence` | S | "high", "medium", or "low" |
| `source_conversation_id` | S | Optional -- conversation that produced it |
| `observed_at` | S | ISO 8601 |
| `created_at` | S | ISO 8601 |

Valid categories: `diet`, `exercise`, `sleep`, `symptom`, `mood`, `general`.

### 4.15 HealthDocuments

| Attribute | Type | Key |
|-----------|------|-----|
| `user_id` | S | PK (HASH) |
| `document_id` | S | SK (RANGE) -- ULID |
| `filename` | S | Original filename |
| `s3_key` | S | `health-documents/{user_id}/{document_id}/{filename}` |
| `content_type` | S | MIME type |
| `file_size` | N | Bytes |
| `uploaded_by` | S | User ID |
| `description` | S | Optional |
| `record_id` | S | Optional -- linked health record |
| `uploaded_at` | S | ISO 8601 |

### 4.16 MemberPermissions

| Attribute | Type | Key |
|-----------|------|-----|
| `user_id` | S | PK (HASH) |
| `permission_type` | S | SK (RANGE) |
| `config` | M | Permission-specific configuration |
| `status` | S | "active" or "revoked" |
| `granted_at` | S | ISO 8601 |
| `granted_by` | S | User ID |
| `revoked_at` | S | Optional -- set on revocation |

### 4.17 ChatMedia

| Attribute | Type | Key |
|-----------|------|-----|
| `media_id` | S | PK (HASH) -- ULID |
| `user_id` | S | |
| `s3_key` | S | `chat-media/{user_id}/{media_id}/{prefix}.{ext}` |
| `content_type` | S | MIME type |
| `file_size` | N | Bytes |
| `status` | S | "pending" or "attached" |
| `uploaded_at` | S | ISO 8601 |
| `expires_at` | N | TTL attribute (epoch seconds, enabled) -- removed when attached |

---

## 5. Services Layer

All services are in `/home/ubuntu/homeagent/backend/app/services/`.

### bedrock.py
Direct Bedrock integration. `stream_chat()` calls `converse_stream` on the configured model, yields `text_delta` and `message_done` chunks. Handles image attachments as S3-referenced content blocks on the last user message.

### agent_orchestrator.py
Alternative to direct Bedrock, activated by `USE_AGENT_ORCHESTRATOR=true`. Uses the Strands Agents SDK to create a personalized agent with:
- Profile-aware system prompt (name, family role, interests, health notes, preferences)
- Family tree context injected into the system prompt
- Sub-agent tools built from the user's enabled agent configs
- Optional AgentCore Memory for cross-conversation memory

Runs the async Strands agent in a background thread via `ThreadPoolExecutor`, bridging to the SSE generator via a `queue.Queue`.

### agent_template.py
CRUD for `AgentTemplates` table. Seeds 3 built-in agents on startup: `health_advisor`, `logistics_assistant`, `shopping_assistant`. Built-in templates use deterministic IDs (`builtin-{agent_type}`) and cannot be deleted.

### agent_config.py
CRUD for `AgentConfigs` table. Per-user agent enable/disable with config. Merges template defaults with user overrides. Also provides `get_available_agent_types()` which returns a dict of all templates keyed by `agent_type`.

### cognito.py
Cognito integration: `sign_up`, `confirm_sign_up`, `sign_in`, `resend_confirmation_code`, `verify_token`. Caches JWKS keys for 1 hour. All errors wrapped in `CognitoError` with Cognito error codes.

### conversation.py
CRUD for conversations and messages. Uses ULID for IDs, `{timestamp}#{id}` as sort keys for chronological ordering. `list_conversations` uses the `user_conversations-index` GSI sorted by `updated_at` descending. Cursor-based pagination.

### family.py
Family creation, membership management. Creating a family auto-adds the owner as the first member and sets `family_id` on the user record. `get_family_members` enriches with user names.

### family_tree.py
Bidirectional relationship management. `set_relationship` writes both forward and inverse records. `build_family_context()` generates a natural language description of family relationships for injection into the agent system prompt.

### health_records.py
CRUD for structured health records. All mutations are audit-logged via `health_audit.py`. `get_health_summary` returns records grouped by type.

### health_observations.py
CRUD for AI-extracted and manually-created health observations. Filterable by category via GSI.

### health_documents.py
Document metadata management with S3 presigned URLs for upload/download. Documents stored at `health-documents/{user_id}/{document_id}/{filename}`. Deletion removes both S3 object and DynamoDB record.

### health_audit.py
Immutable audit log for health record changes. Every create/update/delete on HealthRecords writes an entry with actor, action, and before/after snapshots.

### health_extraction.py
Background health observation extraction from chat conversations. Runs in a daemon thread (fire-and-forget from the chat endpoint). Uses a separate Bedrock `converse` call (non-streaming, using the `HEALTH_EXTRACTION_MODEL_ID` -- defaults to Claude Haiku) to analyze the user message + assistant response and extract structured observations. Creates its own boto3 clients to avoid Flask request-context dependencies.

### member_permissions.py
Permission grant/revoke management. Tracks consent for data access (`email_access`, `calendar_access`, `health_data`, `medical_records`). Revocation sets `status = "revoked"` rather than deleting.

### profile.py
Member profile CRUD. Updatable fields: `display_name`, `family_role`, `preferences`, `health_notes`, `interests`.

### user.py
User lifecycle: `register_device` (invite code flow), `create_owner_user` (Cognito flow), `generate_invite_code`, `send_invite_email` (SES), `delete_member` (cascade delete across all tables).

### chat_media.py
Chat media upload management. Creates a `ChatMedia` record with TTL, generates a presigned S3 PUT URL. `resolve_media_for_message` validates ownership, verifies S3 upload exists, marks media as attached (removing TTL), and returns S3 URIs for Bedrock. Max 5 media items per message.

### memory.py
Optional AgentCore Memory integration. Creates a `AgentCoreMemorySessionManager` for the Strands agent, enabling cross-conversation persistent memory with per-user preferences, facts, and session summaries.

### transcribe.py
Audio transcription using AWS Transcribe. Starts a transcription job with `IdentifyLanguage=True` (supports `en-US` and `zh-CN`), polls until complete, reads the transcript JSON from S3, then cleans up both the output file and the job.

### voice_session.py
Nova Sonic bidirectional streaming session management. See section 8.

---

## 6. Agent System

### Overview

The agent system is a 2-layer architecture:

```
Personal Agent (Strands Agent, per-user)
  |-- Sub-Agent: Health Advisor (registered factory)
  |-- Sub-Agent: Custom Agent (template-driven)
  |-- Sub-Agent: ...
```

### Layer 1: Agent Templates (admin authorizes)

Admins create `AgentTemplate` records that define agent types. Each template has:
- `agent_type` -- unique slug (e.g., `health_advisor`)
- `system_prompt` -- drives the agent's behavior
- `default_config` -- merged into user configs
- `available_to` -- `"all"` or explicit user ID list
- `required_permissions` -- permissions the user must grant

Three built-in templates are seeded on startup:

| Agent Type | Name | Default | Required Permissions |
|------------|------|---------|---------------------|
| `health_advisor` | Health Advisor | Yes | `health_data`, `medical_records` |
| `logistics_assistant` | Logistics Assistant | Yes | `email_access`, `calendar_access` |
| `shopping_assistant` | Shopping Assistant | No | (none) |

### Layer 2: Agent Configs (member enables)

Members enable agents for themselves via `PUT /api/agents/my/<agent_type>`. This creates an `AgentConfig` record with `enabled=true` and a merged config (template defaults + any overrides).

### Strands SDK Integration

When `USE_AGENT_ORCHESTRATOR=true`, the chat flow uses `stream_agent_chat()`:

1. A `BedrockModel` is created with the configured model ID.
2. `build_sub_agent_tools(user_id)` iterates the user's enabled `AgentConfig` records:
   - For each agent type, it first tries the **registry** (`app/agents/registry.py`) for a Python factory function (e.g., `health_advisor` maps to `create_health_advisor_tool`).
   - If no registry entry exists, it falls back to the **generic custom agent** factory (`app/agents/custom_agent.py`), which creates a Strands `@tool` function driven by the template's `system_prompt`.
3. A Strands `Agent` is instantiated with the personalized system prompt, message history, sub-agent tools, and optional session manager.
4. The agent streams responses asynchronously; a queue bridges the async loop to the SSE generator.

### Agent Registry

`/home/ubuntu/homeagent/backend/app/agents/registry.py` provides:
- `@register_agent(agent_type)` -- decorator for factory functions
- `create_agent_tool(agent_type, config, user_id, model_id)` -- creates a `@tool` function

### Health Advisor Agent

`/home/ubuntu/homeagent/backend/app/agents/health_advisor.py` is the primary built-in agent. It is a Strands agent with 7 tools:

1. `get_family_health_records` -- reads health records for a family member
2. `get_health_summary` -- structured summary by record type
3. `get_family_health_context` -- family composition, roles, health notes
4. `save_health_observation` -- persists observations (if `observation_tracking_enabled`)
5. `get_health_observations` -- reads past observations/trends
6. `search_health_conversations` -- keyword search across recent conversations (if `conversation_mining_enabled`)
7. `search_health_info` -- web search placeholder (if `web_search_enabled`)

All tools enforce family access control: users can only access their own data or data of users they have a `FamilyRelationship` with.

### Custom Agents

`/home/ubuntu/homeagent/backend/app/agents/custom_agent.py` creates a generic Strands `@tool` from any template with a non-empty `system_prompt`. The tool name is `ask_{agent_type}`.

---

## 7. SSE Streaming

### How It Works

The `POST /api/chat` endpoint returns a `text/event-stream` response using Flask's `stream_with_context`.

**Direct Bedrock path** (`USE_AGENT_ORCHESTRATOR=false`):

1. `stream_chat()` in `bedrock.py` calls `bedrock-runtime.converse_stream()`.
2. Iterates over `response["stream"]` events:
   - `contentBlockDelta` with `text` -> yields `{"type": "text_delta", "content": chunk}`
   - `metadata` -> captures `inputTokens` and `outputTokens`
3. After the stream ends, yields `{"type": "message_done", "content": full_text, ...}`

**Agent orchestrator path** (`USE_AGENT_ORCHESTRATOR=true`):

1. `stream_agent_chat()` in `agent_orchestrator.py` creates a Strands `Agent`.
2. The agent runs in a background thread (via `ThreadPoolExecutor`) with its own `asyncio` event loop.
3. Streaming events are pushed to a `queue.Queue`.
4. The SSE generator pulls from the queue, yielding `text_delta` events.
5. When the queue receives `None` (sentinel), the stream emits `message_done`.

**SSE event format** (Server-Sent Events):

```
data: {"type": "text_delta", "content": "Hello", "conversation_id": "01HX..."}

data: {"type": "message_done", "conversation_id": "01HX...", "message_id": "01HX..."}
```

**Response headers**:
```
Content-Type: text/event-stream
Cache-Control: no-cache
X-Accel-Buffering: no
```

The `X-Accel-Buffering: no` header prevents nginx/ALB from buffering the stream. The Gunicorn timeout is 300 seconds to accommodate long conversations.

---

## 8. Voice Mode

### Architecture

Voice mode uses a WebSocket endpoint backed by Amazon Nova Sonic for bidirectional audio streaming. It is gated behind `VOICE_ENABLED=true`.

### WebSocket Endpoint

```
ws://<host>/api/voice?token=<device_token>&conversation_id=<optional_id>
```

Authentication is via the `token` query parameter (device token lookup, same as `_try_device_auth`). This is necessary because WebSocket connections cannot use standard `Authorization` headers in all clients.

### VoiceSession Class

`/home/ubuntu/homeagent/backend/app/services/voice_session.py` manages the Nova Sonic stream:

1. **Start**: Creates a persistent `asyncio` event loop on a background thread. Opens a bidirectional stream via `invoke_model_with_bidirectional_stream`. Sends 6 setup events:
   - `sessionStart` with inference config
   - `promptStart` with audio input config (16kHz 16-bit PCM), audio output config (24kHz 16-bit PCM, voice: "tiffany"), and text I/O config
   - `contentStart` + `textInput` + `contentEnd` for the system prompt
   - `contentStart` for the audio stream (interactive mode)

2. **Send audio**: `send_audio(pcm_bytes)` base64-encodes PCM data and sends an `audioInput` event.

3. **Receive**: An async coroutine reads from the stream and pushes events to `_output_queue`:
   - `audioOutput` -> `{"type": "audio_chunk", "data": base64_wav}` (raw LPCM is wrapped in a WAV header for mobile playback)
   - `textOutput` -> `{"type": "transcript", "role": str, "content": str}`
   - `sessionEnd` -> `{"type": "session_end"}`
   - `error` -> `{"type": "error", "content": str}`

4. **End**: Sends `promptEnd` and `sessionEnd` events, stops the event loop.

### WebSocket Message Protocol

**Client -> Server:**

| Message Type | Fields | Description |
|-------------|--------|-------------|
| `audio_start` | (none) | Signals start of audio (informational) |
| `audio_chunk` | `data`: base64 PCM | Audio data (WAV headers stripped if present) |
| `audio_end` | (none) | Signals end of audio input |
| `text` | `content`: str | Optional text alongside voice |

**Server -> Client:**

| Message Type | Fields | Description |
|-------------|--------|-------------|
| `audio_chunk` | `data`: base64 WAV | Audio response (24kHz PCM in WAV container) |
| `transcript` | `role`, `content` | Text transcript of speech |
| `session_end` | (none) | Session has ended |
| `error` | `content` | Error message |

Transcripts are saved to conversation history when a `conversation_id` is provided.

### Concurrency Model

The voice WebSocket handler uses gevent greenlets:
- **Main greenlet**: receives messages from the WebSocket client and forwards audio to Nova Sonic.
- **Receiver greenlet**: reads from Nova Sonic and sends events back through the WebSocket.

---

## 9. Health System

### Overview

The health system provides structured medical record management, AI-extracted observations from conversations, document storage, and an immutable audit trail.

### Health Records

Structured records stored in the `HealthRecords` table with 7 types:
- **condition** -- diagnoses, chronic conditions
- **medication** -- current/past medications
- **allergy** -- allergies and reactions
- **appointment** -- scheduled/past medical appointments
- **vital** -- vital signs (blood pressure, temperature, etc.)
- **immunization** -- vaccination records
- **growth** -- height, weight, growth charts (typically for children)

Each record has an arbitrary `data` map for the payload. All CRUD operations are audit-logged.

### Health Observations

Observations are lighter-weight data points extracted from conversations or created manually. They track health patterns across 6 categories: `diet`, `exercise`, `sleep`, `symptom`, `mood`, `general`.

Each observation includes a `confidence` level (`high`, `medium`, `low`) and optionally links back to the source conversation.

### AI Extraction Pipeline

After every chat message, if `HEALTH_EXTRACTION_ENABLED=true`:

1. A daemon thread is spawned (fire-and-forget).
2. The thread calls Bedrock `converse` (non-streaming) with Claude Haiku and a structured prompt containing the user message and assistant response.
3. The model returns a JSON array of observations.
4. Valid observations are written to the `HealthObservations` table.

The extraction thread creates its own boto3 clients since it runs outside Flask's request context.

### Health Documents

File attachments (PDFs, images) linked to users and optionally to health records. Stored in S3 at `health-documents/{user_id}/{document_id}/{filename}`. Upload/download use presigned URLs with 1-hour expiry.

### Health Reports

On-demand report generation aggregates:
- Member profile (name, role, health notes)
- Health records summary grouped by type
- Health observations grouped by category

### Audit Trail

Every create, update, and delete on health records writes an immutable entry to `HealthAuditLog`:
- **create/delete**: stores a full `record_snapshot`
- **update**: stores `changes` with `before` and `after` states

Queryable per-record (by `record_id`) or per-user (via `user-audit-index` GSI).
