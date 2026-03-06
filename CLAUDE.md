# Family AI Agent (homeagent)

## Project Overview
Family AI agent app — family members chat with Claude (via Amazon Bedrock) through a mobile app. Supports text chat (SSE streaming), image attachments (S3 presigned uploads), voice-to-chat (inline recording with AWS Transcribe), and voice mode (WebSocket with Amazon Nova Sonic). Backend runs on ECS Fargate with Flask, data in DynamoDB (14 tables), infra managed with AWS CDK.

## Monorepo Structure
- `backend/` — Flask API (Python 3.12)
- `mobile/` — Expo React Native app (TypeScript)
- `webui/` — Debug web console (static HTML/CSS/JS, hosted on S3+CloudFront)
- `infra/` — AWS CDK stacks (Python)

## Git Workflow
- **ALWAYS create a new branch for every feature** before making changes. Branch from `main`.
- Branch naming: `feature/<short-description>` (e.g., `feature/cognito-auth`, `feature/logistics-agent`)
- Never commit directly to `main` or `master`. Each feature branch gets its own PR.
- This prevents merge conflicts when multiple features are developed in parallel.

## Conventions

### Python (backend + infra)
- Python 3.12, type hints on all function signatures
- Flask app factory pattern in `backend/app/__init__.py`
- Use `ulid` for user/conversation IDs, `uuid4` for device IDs
- DynamoDB access through helpers in `backend/app/models/dynamo.py`
- Tests with `pytest`; run: `cd backend && python -m pytest tests/`
- Lint: `ruff check backend/`
- Format: `ruff format backend/`

### TypeScript (mobile)
- Strict TypeScript, no `any`
- Expo managed workflow (SDK 52)
- State management: React Context + useReducer
- API client in `mobile/src/services/api.ts`
- Secure token storage via `expo-secure-store`
- Test on device via Expo Go app (scan QR code)

### API
- All endpoints prefixed with `/api/`
- Auth via `Authorization: Bearer <device_token>` header
- SSE streaming for text chat responses (`text/event-stream`)
- WebSocket for voice mode (`/api/voice?token=<token>`)
- Image/audio uploads via S3 presigned PUT URLs (`POST /api/chat/upload-image`)
- Audio transcription via AWS Transcribe (auto-detects en-US/zh-CN)
- Pagination via cursor-based `?limit=N&cursor=X`

### Infrastructure
- CDK Python, one stack per concern (network, data, security, service, webui, pipeline)
- CDK Pipelines self-mutating pattern for CI/CD
- DynamoDB on-demand billing (14 tables), tables created by CDK (cloud) or auto-init (local)
- ECS Fargate with ALB, 300s idle timeout for SSE and WebSocket
- ECR repository `homeagent-backend` for Docker images
- S3 for health documents + chat media images + audio uploads + transcribe output (shared bucket, separate prefixes)
- S3 + CloudFront for debug web UI static hosting

## CI/CD Pipeline (AWS CodePipeline)
```
GitHub (main) → Synth CDK → Run Tests → Deploy Infra → Docker Build+Push → Update ECS → Deploy Web UI
```
- **Source**: GitHub `Crazyhenry123/homeagent` repo via CodeStar Connection
- **Test**: CodeBuild runs pytest with DynamoDB Local in Docker
- **Deploy**: CDK Pipelines deploys Network, Data, Security, Service, WebUi stacks
- **Build**: CodeBuild builds Docker image, pushes to ECR, triggers ECS rolling deploy
- **WebUI**: Syncs `webui/` to S3 bucket and invalidates CloudFront cache

### First-time setup
```bash
# 1. Create a CodeStar Connection to GitHub in AWS Console
#    (Developer Tools → Settings → Connections → Create connection)
# 2. Bootstrap CDK
cd infra
pip install -r requirements.txt
cdk bootstrap aws://ACCOUNT_ID/us-east-1

# 3. Deploy pipeline with connection ARN
cdk deploy HomeAgentPipeline \
  -c account=ACCOUNT_ID \
  -c region=us-east-1 \
  -c github_connection_arn=arn:aws:codeconnections:us-east-1:ACCOUNT_ID:connection/UUID

# 4. Push to GitHub to trigger the pipeline
git push origin main
```

## Local Development
```bash
# Backend
docker-compose up              # Flask + DynamoDB Local

# Mobile
cd mobile
npm install
npx expo start                 # Scan QR code with Expo Go on your phone

# Web Debug Console
# Open webui/index.html directly in a browser, or serve with:
python -m http.server 8080 -d webui
# Then configure the API endpoint to http://localhost:5000
```

## Environment Variables
- `AWS_REGION` — AWS region (default: us-east-1)
- `DYNAMODB_ENDPOINT` — DynamoDB endpoint (local dev only: http://dynamodb-local:8000)
- `TABLE_PREFIX` — Optional prefix for DynamoDB table names
- `BEDROCK_MODEL_ID` — Claude model ID (default: us.anthropic.claude-opus-4-6-v1)
- `SYSTEM_PROMPT` — System prompt for Claude
- `ADMIN_INVITE_CODE` — Pre-seeded invite code for first admin
- `USE_AGENT_ORCHESTRATOR` — Enable Strands Agent orchestrator (default: false)
- `AGENTCORE_MEMORY_ID` — AgentCore memory ID for conversation memory
- `S3_HEALTH_DOCUMENTS_BUCKET` — S3 bucket for health docs and chat media images
- `S3_ENDPOINT` — S3 endpoint override (local dev only)
- `CHAT_MEDIA_MAX_SIZE` — Max image upload size in bytes (default: 5MB)
- `CHAT_MEDIA_AUDIO_MAX_SIZE` — Max audio upload size in bytes (default: 25MB)
- `HEALTH_EXTRACTION_ENABLED` — Enable AI health extraction from chats (default: true)
- `HEALTH_EXTRACTION_MODEL_ID` — Model for health extraction (default: claude-haiku)
- `VOICE_ENABLED` — Enable voice mode WebSocket endpoint (default: false)
- `VOICE_MODEL_ID` — Nova Sonic model ID (default: amazon.nova-sonic-v1:0)

## Key Features
- **Text Chat** — SSE streaming with Claude via Bedrock `converse_stream`
- **Image Attachments** — Up to 5 images per message via S3 presigned upload
- **Voice-to-Chat** — Inline mic recording in chat, transcribed server-side via AWS Transcribe, sent as text to Claude (supports en-US/zh-CN auto-detection)
- **Voice Mode** — Bidirectional WebSocket audio with Amazon Nova Sonic
- **Agent System** — Pluggable sub-agents via Strands SDK (built-in + custom)
- **Health Management** — Records, observations, documents, reports, AI extraction, audit trail
- **Family Tree** — Relationship tracking with context injection into system prompt
- **Profiles** — Per-member personalization (name, role, interests, health notes)
