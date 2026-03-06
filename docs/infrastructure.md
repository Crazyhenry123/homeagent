# HomeAgent Infrastructure & DevOps Reference

This document provides a comprehensive reference for the homeagent infrastructure, covering local development, AWS CDK stacks, CI/CD pipelines, DynamoDB table definitions, tunneling for phone testing, persistent storage, and environment variables.

---

## Table of Contents

1. [Local Development Setup](#1-local-development-setup)
2. [AWS CDK Infrastructure](#2-aws-cdk-infrastructure)
3. [CI/CD Pipelines](#3-cicd-pipelines)
4. [DynamoDB Table Definitions](#4-dynamodb-table-definitions)
5. [Tunneling for Phone Testing](#5-tunneling-for-phone-testing)
6. [Persistent Storage](#6-persistent-storage)
7. [Environment Variables](#7-environment-variables)

---

## 1. Local Development Setup

### docker-compose.yml Services

The local development stack is defined in `/docker-compose.yml` and consists of four services:

#### api

- **Build context**: `./backend`
- **Port**: `5000:5000`
- **Volumes**: `./backend:/app` (live-reload during development)
- **Depends on**: `dynamodb-local` (healthy) and `minio-init` (completed successfully)
- **Environment**: see [Section 7](#7-environment-variables) for the full list; key values include `FLASK_ENV=development`, `DYNAMODB_ENDPOINT=http://dynamodb-local:8000`, `S3_ENDPOINT=http://minio:9000`

The API container runs the Flask backend. On startup, `app.models.dynamo.init_tables()` auto-creates all 17 DynamoDB tables in DynamoDB Local and seeds the admin invite code.

#### dynamodb-local

- **Image**: `amazon/dynamodb-local:latest`
- **Port**: `8000:8000`
- **Command**: `-jar DynamoDBLocal.jar -sharedDb -dbPath /data`
- **User**: `root` (required for writing to the mounted volume)
- **Volume**: `dynamodb-data:/data` (named Docker volume; see [Section 6](#6-persistent-storage))
- **Health check**: `curl -s http://localhost:8000/shell/` every 5s, 3s timeout, 5 retries

#### minio

- **Image**: `minio/minio:latest`
- **Ports**: `9000:9000` (S3 API), `9001:9001` (web console)
- **Credentials**: `MINIO_ROOT_USER=local`, `MINIO_ROOT_PASSWORD=locallocal`
- **Command**: `server /data --console-address ":9001"`
- **Health check**: `mc ready local` every 5s, 3s timeout, 5 retries

MinIO provides an S3-compatible object store for local development. The web console is available at `http://localhost:9001`.

#### minio-init

- **Image**: `minio/mc:latest` (MinIO CLI client)
- **Depends on**: `minio` (healthy)
- **Purpose**: One-shot init container that creates the `health-documents` bucket on MinIO, then exits. Uses `mc mb --ignore-existing` so it is idempotent.

#### Volumes

```yaml
volumes:
  dynamodb-data:
```

A single named volume `dynamodb-data` persists DynamoDB Local data across container restarts.

### The .env File Pattern

- `.env` is listed in `.gitignore` and must never be committed.
- `.env.example` serves as the template. It contains:

```
COGNITO_USER_POOL_ID=
COGNITO_CLIENT_ID=
COGNITO_REGION=us-east-1
```

To set up locally, copy the example and fill in values:

```bash
cp .env.example .env
# Edit .env with your Cognito pool details (or leave blank to skip Cognito auth locally)
```

Docker Compose automatically loads `.env` from the project root and interpolates `${VAR}` references in `docker-compose.yml`.

### Starting Local Development

```bash
docker compose up          # Starts all four services
# API available at http://localhost:5000
# MinIO console at http://localhost:9001
# DynamoDB Local shell at http://localhost:8000/shell/
```

---

## 2. AWS CDK Infrastructure

All CDK code lives under `/infra/`. The CDK app is Python-based (aws-cdk-lib 2.240.0) and uses one stack per concern.

### Entry Point

`/infra/app.py` creates a single `PipelineStack` which contains a self-mutating CDK Pipeline. The pipeline deploys a `HomeAgentStage` that bundles all application stacks.

Context parameters passed at deploy time:

| Context Key              | Purpose                                      |
|--------------------------|----------------------------------------------|
| `account`                | AWS account ID                               |
| `region`                 | AWS region (default: `us-east-1`)            |
| `github_connection_arn`  | CodeStar Connection ARN for GitHub access    |

### Stack Structure

Defined in `/infra/stacks/app_stage.py`, the `HomeAgentStage` instantiates stacks in this order:

```
HomeAgentStage
  +-- NetworkStack    (VPC, subnets, NAT gateway)
  +-- DataStack       (DynamoDB tables, S3 bucket)
  +-- SecurityStack   (ECR repo, IAM task role)
  +-- ServiceStack    (ECS Fargate, ALB, auto-scaling)
  +-- WebUiStack      (S3 + CloudFront for debug web UI)
```

The `PipelineStack` sits outside the stage and defines the CodePipeline plus four fast-path pipelines.

#### NetworkStack (`/infra/stacks/network_stack.py`)

- **VPC**: 2 AZs, 1 NAT gateway
- **Subnets**: Public (`/24`) and Private with Egress (`/24`)
- **Output**: `VpcId`

#### DataStack (`/infra/stacks/data_stack.py`)

Creates all DynamoDB tables and the S3 documents bucket. See [Section 4](#4-dynamodb-table-definitions) for the full table list.

**S3 Bucket** -- `homeagent-health-documents-{ACCOUNT_ID}`:

| Setting                 | Value                                            |
|-------------------------|--------------------------------------------------|
| Encryption              | S3-managed (SSE-S3)                              |
| Public access           | Blocked entirely                                 |
| SSL enforcement         | Enabled                                          |
| Removal policy          | RETAIN                                           |
| Lifecycle rule          | Transition to Infrequent Access after 90 days    |
| CORS                    | GET/PUT from any origin, any header, 3600s max-age |

This single bucket stores health documents, chat media images, audio uploads, and transcription output using separate S3 key prefixes.

#### SecurityStack (`/infra/stacks/security_stack.py`)

**ECR Repository** -- `homeagent-backend`:
- Lifecycle rule: keep last 10 images
- Removal policy: DESTROY (with `empty_on_delete=True`)

**ECS Task Role** -- IAM role assumed by `ecs-tasks.amazonaws.com` with:

| Permission                           | Resources   |
|--------------------------------------|-------------|
| DynamoDB read/write                  | All 14+ tables (granted per-table) |
| `bedrock:InvokeModel`, `bedrock:InvokeModelWithResponseStream` | `*` |
| Bedrock AgentCore memory operations  | `*` |
| `transcribe:StartTranscriptionJob`, `GetTranscriptionJob`, `DeleteTranscriptionJob` | `*` |
| S3 read/write on documents bucket    | The health-documents bucket |
| ECR pull                             | `homeagent-backend` repo |

#### ServiceStack (`/infra/stacks/service_stack.py`)

**ECS Cluster + Fargate Service**:

| Setting                  | Value                                          |
|--------------------------|-------------------------------------------------|
| CPU                      | 1024 (1 vCPU)                                  |
| Memory                   | 2048 MiB                                       |
| Container image          | `homeagent-backend:latest` from ECR            |
| Container port           | 5000                                           |
| Desired count            | 1                                              |
| Public load balancer     | Yes                                            |
| Assign public IP         | No (tasks in private subnets)                  |
| Min healthy percent      | 100%                                           |
| Auto-scaling             | 1-4 tasks, scale on 70% CPU utilization        |

**Container health check**: Python urllib check against `http://localhost:5000/health` every 30s.

**ALB configuration**:

| Setting                            | Value     | Why                                       |
|------------------------------------|-----------|-------------------------------------------|
| `idle_timeout.timeout_seconds`     | `300`     | SSE streams and WebSocket connections need long-lived connections |
| `stickiness.enabled`               | `true`    | WebSocket connections must stay on the same target |
| `stickiness.type`                  | `lb_cookie` | Cookie-based session affinity            |
| `stickiness.lb_cookie.duration_seconds` | `3600` | 1-hour sticky sessions                  |

**ALB health check**: `GET /health`, expects HTTP 200, every 30s.

**SSM Parameters** (used by fast-path pipelines to discover cluster/service):
- `/homeagent/backend/cluster-name`
- `/homeagent/backend/service-name`

**CloudWatch Logs**: `/ecs/homeagent`, 2-week retention.

#### WebUiStack (`/infra/stacks/webui_stack.py`)

**S3 Bucket** (private, auto-delete on destroy):
- Stores static HTML/CSS/JS from the `webui/` directory
- Accessed exclusively through CloudFront OAC (Origin Access Control)

**CloudFront Distribution**:

| Behavior        | Origin                    | Cache Policy          | Notes                           |
|-----------------|---------------------------|-----------------------|---------------------------------|
| Default (`/*`)  | S3 bucket (OAC)           | CACHING_OPTIMIZED     | Static assets                   |
| `/api/*`        | ALB (HTTP origin)         | CACHING_DISABLED      | All methods allowed, full viewer request forwarding |
| `/health`       | ALB (HTTP origin)         | CACHING_DISABLED      | Health check passthrough        |

- Default root object: `index.html`
- Error pages (403, 404) redirect to `/error.html` with 0s TTL
- API origin read timeout: 60s
- Viewer protocol: redirect HTTP to HTTPS

**SSM Parameters**:
- `/homeagent/webui/bucket-name`
- `/homeagent/webui/distribution-id`

#### Cognito User Pool

Cognito configuration is referenced in the backend environment variables (`COGNITO_USER_POOL_ID`, `COGNITO_CLIENT_ID`, `COGNITO_REGION`) but is not created by CDK. The Cognito User Pool is provisioned separately (likely via the AWS Console) and its IDs are injected through environment variables or `.env`.

---

## 3. CI/CD Pipelines

The project defines **five** CodePipeline pipelines in `/infra/stacks/pipeline_stack.py`. One is the main self-mutating CDK Pipeline; the other four are fast-path V2 pipelines triggered by file-path filters.

### 3.1 Main Pipeline (`homeagent-pipeline`)

Self-mutating CDK Pipeline using `pipelines.CodePipeline`. Triggers on any push to `main`.

```
Source (GitHub main)
  |
  v
Synth (CDK synth)
  |
  v
SelfMutation (auto-updates pipeline definition)
  |
  v
[Pre] BackendTests (pytest with DynamoDB Local in Docker)
  |
  v
Deploy Stage (HomeAgentStage: Network, Data, Security, Service, WebUi)
  |
  v
[Post] DockerBuildPush     -- builds image, pushes to ECR, force-redeploys ECS
[Post] WebUiDeploy         -- s3 sync webui/ + CloudFront invalidation
```

**Synth step**: Installs `infra/requirements.txt`, runs `npx cdk synth` in the `infra/` directory. Uses CodeBuild STANDARD_7_0 image with privileged mode.

**BackendTests step** (pre-deploy gate):
- Installs Python 3.12, backend requirements, pytest, strands-agents
- Starts DynamoDB Local in Docker (in-memory mode for speed)
- Runs `python -m pytest tests/ -v`
- Environment: `AWS_REGION=us-east-1`, dummy credentials, `DYNAMODB_ENDPOINT=http://localhost:8000`, `ADMIN_INVITE_CODE=TESTCODE`

**DockerBuildPush step** (post-deploy):
1. `aws ecr get-login-password` to authenticate with ECR
2. `docker build` in `backend/`
3. Tags with both git SHA and `latest`
4. Pushes both tags
5. `aws ecs update-service --force-new-deployment` to trigger rolling deploy

**WebUiDeploy step** (post-deploy):
1. `aws s3 sync webui/ s3://$BUCKET --delete`
2. `aws cloudfront create-invalidation --paths "/*"`

### 3.2 Fast WebUI Pipeline (`homeagent-webui-fast`)

**Trigger**: Push to `main` with changes in `webui/**` only.
**Stages**: Source -> Deploy (S3 sync + CloudFront invalidation)
**Duration**: ~1 minute
**Reads bucket name and distribution ID from SSM Parameter Store.**

### 3.3 Fast Backend Pipeline (`homeagent-backend-fast`)

**Trigger**: Push to `main` with changes in `backend/**` only.
**Stages**: Source -> Test (pytest with DynamoDB Local) -> Deploy (Docker build + ECR push + ECS update)
**Duration**: ~5-6 minutes
**Reads cluster name and service name from SSM Parameter Store.**

### 3.4 Infra Pipeline (`homeagent-infra`)

**Trigger**: Push to `main` with changes in `infra/**` only.
**Stages**: Source -> Deploy (CDK synth + `cdk deploy --all --require-approval never`)
**Post-deploy**: Triggers the main pipeline (`aws codepipeline start-pipeline-execution`) to deploy app-level stacks (Security, Service, etc.) that live inside `HomeAgentStage`.

### 3.5 Mobile Pipeline (`homeagent-mobile`)

**Trigger**: Push to `main` with changes in `mobile/**` only.
**Stages**: Source -> Validate (`npm ci` + `npx tsc --noEmit`)
**Duration**: ~2 minutes
**Purpose**: TypeScript type-checking only; no build artifact or deployment (Expo apps are built on-device or via EAS).

### Pipeline Architecture Summary

```
Push to main
  |
  +-- infra/** changed?   --> homeagent-infra       (CDK deploy, then triggers main pipeline)
  +-- backend/** changed? --> homeagent-backend-fast (test + Docker + ECS)
  +-- webui/** changed?   --> homeagent-webui-fast   (S3 sync + CF invalidation)
  +-- mobile/** changed?  --> homeagent-mobile       (TypeScript check)
  +-- any change          --> homeagent-pipeline     (full: synth + test + deploy all + Docker + WebUI)
```

The fast-path pipelines provide quicker feedback when changes are scoped to a single directory. The main pipeline serves as the comprehensive deploy path.

---

## 4. DynamoDB Table Definitions

All tables use **PAY_PER_REQUEST** (on-demand) billing and have a **RETAIN** removal policy in CDK. The authoritative table schema lives in `/backend/app/models/dynamo.py` (`TABLE_DEFINITIONS` dict), which is also used by `_create_local_tables()` to auto-create tables in DynamoDB Local.

The CDK `DataStack` mirrors these definitions for cloud deployment.

### Complete Table Reference (17 tables)

| # | Table | Partition Key (PK) | Sort Key (SK) | GSIs | TTL | Purpose |
|---|-------|--------------------|---------------|------|-----|---------|
| 1 | **Users** | `user_id` (S) | -- | `email-index` (PK: `email`), `cognito_sub-index` (PK: `cognito_sub`) | -- | User accounts; lookup by email or Cognito subject |
| 2 | **Devices** | `device_id` (S) | -- | `device_token-index` (PK: `device_token`), `user_id-index` (PK: `user_id`) | -- | Registered devices; auth token lookup, per-user device list |
| 3 | **InviteCodes** | `code` (S) | -- | `invited_email-index` (PK: `invited_email`) | -- | Single-use invite codes for registration |
| 4 | **Families** | `family_id` (S) | -- | `owner-index` (PK: `owner_user_id`) | -- | Family groups; lookup by owner |
| 5 | **FamilyMembers** | `family_id` (S) | `user_id` (S) | -- | -- | Many-to-many family membership |
| 6 | **Conversations** | `conversation_id` (S) | -- | `user_conversations-index` (PK: `user_id`, SK: `updated_at`) | -- | Chat conversations; list by user sorted by recency |
| 7 | **Messages** | `conversation_id` (S) | `sort_key` (S) | -- | -- | Chat messages within a conversation |
| 8 | **MemberProfiles** | `user_id` (S) | -- | -- | -- | Per-member profile (name, role, interests, health notes) |
| 9 | **AgentConfigs** | `user_id` (S) | `agent_type` (S) | -- | -- | Per-user agent enable/disable configuration |
| 10 | **FamilyRelationships** | `user_id` (S) | `related_user_id` (S) | -- | -- | Bidirectional family tree relationships |
| 11 | **HealthRecords** | `user_id` (S) | `record_id` (S) | `record_type-index` (PK: `user_id`, SK: `record_type`) | -- | Health records (medications, conditions, etc.) |
| 12 | **HealthAuditLog** | `record_id` (S) | `audit_sk` (S) | `user-audit-index` (PK: `user_id`, SK: `created_at`) | -- | Audit trail for health record changes |
| 13 | **HealthObservations** | `user_id` (S) | `observation_id` (S) | `category-index` (PK: `user_id`, SK: `category`) | -- | AI-extracted health observations from chat |
| 14 | **AgentTemplates** | `template_id` (S) | -- | `agent_type-index` (PK: `agent_type`) | -- | Built-in and custom agent template definitions |
| 15 | **HealthDocuments** | `user_id` (S) | `document_id` (S) | -- | -- | Metadata for uploaded health documents (files in S3) |
| 16 | **MemberPermissions** | `user_id` (S) | `permission_type` (S) | -- | -- | Per-user permission grants |
| 17 | **ChatMedia** | `media_id` (S) | -- | -- | `expires_at` | Image/audio upload metadata with automatic TTL expiry |

### GSI Details

All GSIs use `ProjectionType: ALL` (full item projection).

| GSI Name | Table | Partition Key | Sort Key | Use Case |
|----------|-------|---------------|----------|----------|
| `email-index` | Users | `email` | -- | Look up user by email address |
| `cognito_sub-index` | Users | `cognito_sub` | -- | Look up user by Cognito subject ID |
| `device_token-index` | Devices | `device_token` | -- | Auth: validate bearer token |
| `user_id-index` | Devices | `user_id` | -- | List all devices for a user |
| `invited_email-index` | InviteCodes | `invited_email` | -- | Check pending invites by email |
| `owner-index` | Families | `owner_user_id` | -- | Find family owned by a user |
| `user_conversations-index` | Conversations | `user_id` | `updated_at` | List conversations by user, sorted by last update |
| `record_type-index` | HealthRecords | `user_id` | `record_type` | Filter health records by type (medication, condition, etc.) |
| `user-audit-index` | HealthAuditLog | `user_id` | `created_at` | Audit trail by user, sorted chronologically |
| `category-index` | HealthObservations | `user_id` | `category` | Filter observations by category |
| `agent_type-index` | AgentTemplates | `agent_type` | -- | Look up templates by agent type |

### CDK vs. Backend Discrepancy Note

The `Devices` table has a `user_id-index` GSI defined in the backend `TABLE_DEFINITIONS` but **not** in the CDK `DataStack`. A comment in `data_stack.py` explains:

> NOTE: Devices user_id-index GSI already exists on the physical table but is not tracked by CloudFormation. Do NOT add it here or CFN will fail with "index already exists". The GSI was created out-of-band.

Similarly, `Users` GSIs (`email-index`, `cognito_sub-index`), `InviteCodes` GSI (`invited_email-index`), and `Families` GSI (`owner-index`) are defined in backend `TABLE_DEFINITIONS` but not explicitly in CDK. These were likely created out-of-band or are managed by the local auto-creation only. The backend code's `_create_local_tables()` is the source of truth for what the application expects to exist.

---

## 5. Tunneling for Phone Testing

### Problem

The mobile app (Expo React Native on a physical iPhone) needs to reach the local backend API running on the developer's machine. Direct `localhost` access is not possible from a phone.

### Solution: Cloudflare Tunnel (via Expo)

Expo's `--tunnel` mode uses **Cloudflare's `@expo/ws-tunnel`** (which replaced the earlier `localtunnel` package) to expose the Expo dev server through a `*.trycloudflare.com` URL.

To start the Expo dev server with tunneling:

```bash
cd mobile && npx expo start --tunnel
```

This generates a public URL (e.g., `https://agreements-biblical-symantec-mixture.trycloudflare.com`) that the phone can reach. The mobile app's `app.json` stores this URL under `expo.extra.apiBaseUrl`.

### How It Connects to the Local API

The tunnel URL in `app.json` is the **API base URL** the mobile app uses for all HTTP requests. The mobile `api.ts` client sends a `bypass-tunnel-reminder: true` header with every request (a legacy header from the localtunnel era, harmless with Cloudflare).

**Important**: The `apiBaseUrl` in `app.json` must be updated each time a new tunnel session starts, because `trycloudflare.com` URLs are ephemeral. When testing against the deployed ECS backend instead, set `apiBaseUrl` to the ALB or CloudFront URL.

### Typical Phone Testing Flow

1. Start the backend: `docker compose up`
2. Start Expo with tunnel: `cd mobile && npx expo start --tunnel`
3. Update `app.json` `extra.apiBaseUrl` to the tunnel URL (or to your ECS ALB URL)
4. Scan the QR code with the Expo Go app on iPhone
5. The app loads and all API calls route through the tunnel to `localhost:5000`

---

## 6. Persistent Storage

### DynamoDB Local with dbPath Volume Mount

The `dynamodb-local` service in docker-compose.yml uses the flag `-dbPath /data` backed by a named Docker volume:

```yaml
command: "-jar DynamoDBLocal.jar -sharedDb -dbPath /data"
volumes:
  - dynamodb-data:/data
```

### Why This Matters

Without `-dbPath`, DynamoDB Local defaults to **in-memory mode** (`-inMemory`), meaning all data is lost when the container stops. By specifying `-dbPath /data` with a persistent volume:

- **Tables survive restarts**: You do not need to re-create tables or re-seed data after `docker compose down` / `docker compose up`.
- **Test data accumulates**: Conversations, user registrations, health records, etc., persist between development sessions.
- **Matches production behavior**: Data durability mirrors the real DynamoDB experience.

The `-sharedDb` flag means all clients (regardless of AWS credentials or region) share the same database file. This simplifies local development since the API container uses dummy credentials (`local` / `local`).

### CI vs. Local

In CI (CodePipeline test steps), DynamoDB Local runs with `-inMemory` intentionally -- tests should start from a clean slate and run independently. The in-memory flag is used in both the main pipeline's `BackendTests` step and the fast backend pipeline's test stage.

### Clearing Local Data

To reset local state entirely:

```bash
docker compose down -v   # -v removes named volumes including dynamodb-data
docker compose up
```

---

## 7. Environment Variables

Complete reference of all environment variables consumed by the backend. Source of truth: `/backend/app/config.py`.

### Core Configuration

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `AWS_REGION` | string | `us-east-1` | AWS region for all SDK calls (DynamoDB, Bedrock, S3, Transcribe) |
| `DYNAMODB_ENDPOINT` | string | `None` | Override DynamoDB endpoint. Set to `http://dynamodb-local:8000` for local dev. When set, triggers auto-creation of tables on startup. |
| `TABLE_PREFIX` | string | `""` | Optional prefix prepended to all DynamoDB table names (e.g., `dev-Users`) |
| `ADMIN_INVITE_CODE` | string | `None` | Pre-seeded invite code for the first admin user. Set to `FAMILY` in local and ECS environments. Seeded idempotently on startup. |

### AI / Model Configuration

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `BEDROCK_MODEL_ID` | string | `us.anthropic.claude-opus-4-6-v1` | Bedrock model ID for the main chat assistant |
| `SYSTEM_PROMPT` | string | `"You are a helpful family assistant..."` | System prompt injected into every Claude conversation |
| `USE_AGENT_ORCHESTRATOR` | bool | `false` | Enable the Strands Agent orchestrator for sub-agent routing. Set to `true` in both local and production. |
| `AGENTCORE_MEMORY_ID` | string | `None` | Bedrock AgentCore memory ID for persistent conversation memory across sessions |
| `HEALTH_EXTRACTION_ENABLED` | bool | `true` | Enable automatic AI extraction of health observations from chat messages |
| `HEALTH_EXTRACTION_MODEL_ID` | string | `us.anthropic.claude-haiku-4-5-20251001-v1:0` | Bedrock model ID used for health extraction (smaller/faster model) |

### Storage

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `S3_HEALTH_DOCUMENTS_BUCKET` | string | `None` | S3 bucket name for health documents, chat media images, audio uploads, and transcription output. In cloud: `homeagent-health-documents-{ACCOUNT_ID}`. Locally: `health-documents` (MinIO). |
| `S3_ENDPOINT` | string | `None` | Override S3 endpoint. Set to `http://minio:9000` for local dev with MinIO. |
| `CHAT_MEDIA_MAX_SIZE` | int | `5242880` (5 MB) | Maximum allowed image upload size in bytes |
| `CHAT_MEDIA_AUDIO_MAX_SIZE` | int | `26214400` (25 MB) | Maximum allowed audio upload size in bytes |

### Voice

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `VOICE_ENABLED` | bool | `false` | Enable the `/api/voice` WebSocket endpoint for bidirectional audio with Nova Sonic. Set to `true` in both local and production. |
| `VOICE_MODEL_ID` | string | `amazon.nova-sonic-v1:0` | Amazon Nova Sonic model ID for voice mode |

### Authentication (Cognito)

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `COGNITO_USER_POOL_ID` | string | `None` | Cognito User Pool ID. When set, enables Cognito JWT validation on auth endpoints. |
| `COGNITO_CLIENT_ID` | string | `None` | Cognito App Client ID |
| `COGNITO_REGION` | string | value of `AWS_REGION` | Region of the Cognito User Pool (can differ from the main region) |

### Email (SES)

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `SES_ENABLED` | bool | `false` | Enable sending emails via Amazon SES (e.g., invite notifications) |
| `SES_FROM_EMAIL` | string | `""` | Verified SES sender email address |

### Runtime / Server

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `FLASK_ENV` | string | -- | Set to `development` in docker-compose for debug mode. Not set in production. |

### docker-compose.yml Hardcoded Values

These are set directly in `docker-compose.yml` and do not come from `.env`:

| Variable | Value | Notes |
|----------|-------|-------|
| `AWS_ACCESS_KEY_ID` | `${AWS_ACCESS_KEY_ID:-local}` | Falls back to `local`; DynamoDB Local and MinIO accept any credentials |
| `AWS_SECRET_ACCESS_KEY` | `${AWS_SECRET_ACCESS_KEY:-local}` | Falls back to `local` |

### Gunicorn Configuration

The production container runs Gunicorn with the config at `/backend/gunicorn.conf.py`:

| Setting | Value | Notes |
|---------|-------|-------|
| `bind` | `0.0.0.0:5000` | Listens on all interfaces |
| `worker_class` | `gevent` | Async workers for SSE streaming and WebSocket support |
| `workers` | `cpu_count * 2 + 1` | Standard formula; 3 workers on Fargate 1-vCPU |
| `timeout` | `300` | Matches the ALB idle timeout for long-lived SSE/WebSocket connections |
| `keepalive` | `5` | Seconds to wait for next request on a keep-alive connection |

---

## Appendix: Key File Paths

| File | Purpose |
|------|---------|
| `/docker-compose.yml` | Local development service definitions |
| `/.env.example` | Template for local environment variables |
| `/.gitignore` | Git ignore rules (includes `.env`, `cdk.out/`, etc.) |
| `/backend/Dockerfile` | Production container image definition |
| `/backend/app/__init__.py` | Flask app factory |
| `/backend/app/config.py` | All environment variable parsing and defaults |
| `/backend/app/models/dynamo.py` | DynamoDB table definitions and auto-creation logic |
| `/backend/gunicorn.conf.py` | Production WSGI server configuration |
| `/infra/app.py` | CDK app entry point |
| `/infra/stacks/app_stage.py` | Groups all stacks into a deploy stage |
| `/infra/stacks/network_stack.py` | VPC, subnets, NAT gateway |
| `/infra/stacks/data_stack.py` | DynamoDB tables, S3 bucket |
| `/infra/stacks/security_stack.py` | ECR repository, IAM task role |
| `/infra/stacks/service_stack.py` | ECS Fargate, ALB, auto-scaling |
| `/infra/stacks/webui_stack.py` | S3 + CloudFront for web UI |
| `/infra/stacks/pipeline_stack.py` | All five CI/CD pipelines |
| `/mobile/app.json` | Expo config including `apiBaseUrl` for tunnel/prod URL |
