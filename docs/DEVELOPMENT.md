# HomeAgent — Developer Guide

## Project Structure

```
homeagent/
├── backend/          Flask API (Python 3.12)
├── mobile/           Expo React Native app (TypeScript)
├── infra/            AWS CDK stacks (Python)
├── docs/             Documentation
├── docker-compose.yml
├── CLAUDE.md         AI assistant context file
└── .gitignore
```

---

## Local Development Setup

### Prerequisites

- Python 3.12+
- Node.js 18+
- Docker and Docker Compose
- AWS CLI (for Bedrock access in local dev)

### Backend

```bash
# Start Flask + DynamoDB Local
docker-compose up

# Backend runs at http://localhost:5000
# DynamoDB Local at http://localhost:8000
```

The backend auto-creates DynamoDB tables on first request. A pre-seeded invite code `FAMILY` is created on startup.

**Hot reload:** The Docker Compose setup mounts `./backend` as a volume. Flask dev mode reloads on file changes.

### Mobile

```bash
cd mobile
npm install
npx expo start
```

This starts the Expo dev server and displays a QR code. Scan it with Expo Go on your phone.

**API auto-discovery:** In dev mode, the mobile app automatically discovers the backend at `http://<your-machine-ip>:5000` using Expo's `hostUri`.

### Full Local Stack

1. Start backend: `docker-compose up`
2. Start mobile: `cd mobile && npx expo start`
3. Scan QR code with Expo Go
4. Register with invite code `FAMILY`
5. Start chatting (requires AWS credentials for Bedrock)

**Note:** Local chat requires valid AWS credentials with Bedrock access. Set `AWS_ACCESS_KEY_ID` and `AWS_SECRET_ACCESS_KEY` in `docker-compose.yml` or use `~/.aws/credentials`.

---

## Running Tests

### Backend Unit Tests

Tests use DynamoDB Local in Docker. Start it first:

```bash
# Option 1: Using docker-compose (runs DynamoDB Local)
docker-compose up dynamodb-local

# Option 2: Standalone DynamoDB Local
docker run -d -p 8000:8000 amazon/dynamodb-local -jar DynamoDBLocal.jar -sharedDb -inMemory
```

Then run tests:

```bash
cd backend
export DYNAMODB_ENDPOINT=http://localhost:8000
export ADMIN_INVITE_CODE=TESTCODE
python -m pytest tests/ -v
```

### Test Coverage

| File | Tests | What's Tested |
|------|-------|--------------|
| `test_auth.py` | 9 | Registration, token verification, invite codes, admin creation |
| `test_chat.py` | 5 | SSE streaming, conversation creation, auth checks |
| `test_conversations.py` | 5 | List, get messages, delete, pagination |

### Linting

```bash
ruff check backend/
ruff format backend/
```

---

## Code Conventions

### Python (Backend + Infra)

- Type hints on all function signatures
- Flask app factory pattern (`create_app()`)
- ULID for user/conversation IDs, UUID for device IDs
- DynamoDB access via helper functions in `app/models/dynamo.py`
- Route blueprints in `app/routes/`
- Business logic in `app/services/`

### TypeScript (Mobile)

- Strict TypeScript, no `any`
- Types defined in `src/types/index.ts`
- State management: React Context + useReducer (when needed)
- API calls in `src/services/api.ts`
- Secure token storage via `expo-secure-store`
- Stack navigation with React Navigation 7

### API Design

- All endpoints prefixed with `/api/`
- Auth via `Authorization: Bearer <device_token>`
- SSE for streaming chat responses
- Cursor-based pagination with `?limit=N&cursor=X`
- JSON request/response bodies
- Error format: `{"error": "message"}`

---

## Adding a New Feature

### New Backend Endpoint

1. Create or edit a route in `backend/app/routes/`
2. Register the blueprint in `backend/app/__init__.py` (if new)
3. Add business logic in `backend/app/services/`
4. Add tests in `backend/tests/`
5. Run tests: `python -m pytest tests/ -v`

Example: Adding a new route
```python
# backend/app/routes/my_feature.py
from flask import Blueprint, jsonify
from app.auth import require_auth

bp = Blueprint("my_feature", __name__)

@bp.route("/my-feature", methods=["GET"])
@require_auth
def get_my_feature():
    # g.user_id is available from @require_auth
    return jsonify({"data": "hello"})
```

Register in `__init__.py`:
```python
from app.routes.my_feature import bp as my_feature_bp
app.register_blueprint(my_feature_bp, url_prefix="/api")
```

### New Mobile Screen

1. Create screen in `mobile/src/screens/MyScreen.tsx`
2. Add to navigator in `mobile/src/navigation/AppNavigator.tsx`
3. Add type to the navigation param list
4. Create any needed components in `mobile/src/components/`

### New DynamoDB Table

1. Add table definition in `infra/stacks/data_stack.py`
2. Add table to the `tables` dict exposed by `DataStack`
3. Grant permissions in `infra/stacks/security_stack.py`
4. Add initialization in `backend/app/models/dynamo.py`
5. Push to deploy via pipeline

---

## Architecture Decisions

### Why Expo (Not Bare React Native)?

- No Mac or Xcode required for iOS testing
- Expo Go app on iPhone for instant preview
- Managed OTA updates in the future
- Simplified build configuration

### Why DynamoDB (Not PostgreSQL)?

- Serverless: no database servers to manage
- On-demand pricing: pay only for what you use
- Built-in scaling for read/write throughput
- Good fit for key-value access patterns (user lookup, message history)

### Why SSE (Not WebSockets)?

- Simpler server implementation (standard HTTP)
- Works through ALB without sticky sessions
- One-directional streaming is sufficient (server → client)
- Natural fit for LLM token-by-token generation

### Why gevent Workers?

- gunicorn's sync workers block during SSE streaming
- gevent provides cooperative multitasking via greenlets
- Handles many concurrent SSE connections efficiently
- Minimal code changes vs async frameworks

---

## Debugging

### Check Backend Logs

```bash
# Local
docker-compose logs -f api

# AWS (CloudWatch)
aws logs tail /ecs/homeagent --follow --since 5m
```

### Check ECS Task Status

```bash
aws ecs describe-services \
  --cluster <ClusterName> \
  --services <ServiceName> \
  --query 'services[0].{Running:runningCount,Desired:desiredCount}'
```

### Test Endpoints Manually

```bash
# Health
curl http://localhost:5000/health

# Register
curl -X POST http://localhost:5000/api/auth/register \
  -H "Content-Type: application/json" \
  -d '{"invite_code":"FAMILY","device_name":"test","platform":"ios","display_name":"Dev"}'

# Chat (with SSE)
curl -N http://localhost:5000/api/chat \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{"message":"Hello"}'
```

### DynamoDB Local Shell

Access the DynamoDB Local web shell at `http://localhost:8000/shell/` when running via docker-compose.

```bash
# List tables
aws dynamodb list-tables --endpoint-url http://localhost:8000

# Scan a table
aws dynamodb scan --table-name Users --endpoint-url http://localhost:8000
```

---

## CI/CD Pipeline Details

### Pipeline Stages

| Stage | CodeBuild Image | What It Does |
|-------|----------------|-------------|
| Synth | STANDARD_7_0 | `pip install CDK deps` → `cdk synth` |
| BackendTests | STANDARD_7_0 | Start DynamoDB Local → `pytest` |
| Deploy | CloudFormation | Deploy 4 CDK stacks |
| DockerBuildPush | STANDARD_7_0 | Build image → ECR push → ECS update |

### Self-Mutation

The pipeline uses CDK Pipelines' self-mutating pattern. If you change `pipeline_stack.py`, the pipeline will:
1. Detect the change during Synth
2. Update its own definition in the UpdatePipeline stage
3. Restart with the new definition

### Adding a Pipeline Step

Edit `infra/stacks/pipeline_stack.py`:

```python
# Pre-deploy step (runs before infra deployment)
my_step = pipelines.CodeBuildStep(
    "MyStep",
    input=source,
    commands=["echo hello"],
    build_environment=build_env,
)

pipeline.add_stage(
    deploy_stage,
    pre=[test_step, my_step],  # Add to pre list
    post=[docker_build_step],
)
```
