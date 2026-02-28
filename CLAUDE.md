# Family AI Agent (homeagent)

## Project Overview
Family AI agent app — family members chat with Claude (via Amazon Bedrock) through React Native mobile apps. Backend runs on ECS Fargate with Flask, data in DynamoDB, infra managed with AWS CDK.

## Monorepo Structure
- `backend/` — Flask API (Python 3.12)
- `mobile/` — React Native app (TypeScript)
- `infra/` — AWS CDK stacks (Python)

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
- React Native CLI (not Expo)
- State management: React Context + useReducer
- API client in `mobile/src/services/api.ts`
- Secure token storage via `react-native-keychain`

### API
- All endpoints prefixed with `/api/`
- Auth via `Authorization: Bearer <device_token>` header
- SSE streaming for chat responses (`text/event-stream`)
- Pagination via cursor-based `?limit=N&cursor=X`

### Infrastructure
- CDK Python, one stack per concern (network, data, security, service, pipeline)
- CDK Pipelines self-mutating pattern for CI/CD
- DynamoDB on-demand billing, tables created by CDK (cloud) or auto-init (local)
- ECS Fargate with ALB, 300s idle timeout for SSE
- ECR repository `homeagent-backend` for Docker images

## CI/CD Pipeline (AWS CodePipeline)
```
CodeCommit (main) → Synth CDK → Run Tests → Deploy Infra → Docker Build+Push → Update ECS
```
- **Source**: CodeCommit `homeagent` repo, `main` branch
- **Test**: CodeBuild runs pytest with DynamoDB Local in Docker
- **Deploy**: CDK Pipelines deploys Network, Data, Security, Service stacks
- **Build**: CodeBuild builds Docker image, pushes to ECR, triggers ECS rolling deploy

### First-time setup
```bash
cd infra
pip install -r requirements.txt
cdk bootstrap                  # one-time CDK bootstrap
cdk deploy HomeAgentPipeline   # creates pipeline + CodeCommit repo
# Push code to the CodeCommit repo to trigger the pipeline
```

## Local Development
```bash
docker-compose up              # Flask + DynamoDB Local
```

## Environment Variables
- `AWS_REGION` — AWS region (default: us-east-1)
- `DYNAMODB_ENDPOINT` — DynamoDB endpoint (local dev only: http://dynamodb-local:8000)
- `TABLE_PREFIX` — Optional prefix for DynamoDB table names
- `BEDROCK_MODEL_ID` — Claude model ID
- `SYSTEM_PROMPT` — System prompt for Claude
- `ADMIN_INVITE_CODE` — Pre-seeded invite code for first admin
