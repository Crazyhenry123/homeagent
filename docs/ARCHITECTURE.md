# HomeAgent — System Architecture

## Overview

HomeAgent is a family AI chat application. Family members interact with Claude (via Amazon Bedrock) through a mobile app. The system is composed of three layers:

```
+-----------------+       +-------------------+       +------------------+
|  Mobile Client  | <---> |   Backend API     | <---> |  AWS Services    |
|  (Expo / RN)    |  HTTP |   (Flask / ECS)   |       |  Bedrock, Dynamo |
+-----------------+  SSE  +-------------------+       +------------------+
```

- **Mobile** — Expo React Native app (TypeScript). Runs on iOS/Android via Expo Go.
- **Backend** — Python Flask API on ECS Fargate behind an ALB. Handles auth, chat, conversations.
- **Infrastructure** — AWS CDK (Python). VPC, DynamoDB, ECR, ECS, ALB, CodePipeline.

---

## Deployment Architecture

```
                        ┌─────────────────────────────────────────────┐
                        │              AWS Account (us-east-1)        │
                        │                                             │
┌──────────┐            │  ┌──────────────────────────────────────┐   │
│  GitHub  │──webhook──►│  │       CodePipeline (CI/CD)           │   │
│  (master)│            │  │  Source → Synth → Test → Deploy →    │   │
└──────────┘            │  │  DockerBuild → ECS Update            │   │
                        │  └──────────────────────────────────────┘   │
                        │                                             │
                        │  ┌────────────────────────────┐             │
                        │  │         VPC (2 AZs)         │             │
                        │  │                              │             │
                        │  │  ┌─────────────────────┐    │             │
┌──────────┐            │  │  │   Public Subnets     │    │             │
│  Mobile  │──HTTPS────►│  │  │  ┌───────────────┐  │    │             │
│  App     │            │  │  │  │      ALB       │  │    │             │
│(Expo Go) │◄───SSE─────│  │  │  │  (idle: 300s)  │  │    │             │
└──────────┘            │  │  │  └───────┬───────┘  │    │             │
                        │  │  └──────────┼──────────┘    │             │
                        │  │             │                │             │
                        │  │  ┌──────────▼──────────┐    │             │
                        │  │  │  Private Subnets     │    │             │
                        │  │  │  ┌────────────────┐  │    │             │
                        │  │  │  │  ECS Fargate    │  │    │  ┌───────┐ │
                        │  │  │  │  (1–4 tasks)    │──┼────┼─►│Bedrock│ │
                        │  │  │  │  Flask + gunicorn│ │    │  │Claude │ │
                        │  │  │  └────────────────┘  │    │  └───────┘ │
                        │  │  └──────────────────────┘    │             │
                        │  │         │  NAT GW            │             │
                        │  └─────────┼────────────────────┘             │
                        │            │                                  │
                        │  ┌─────────▼──────────┐  ┌──────────┐        │
                        │  │     DynamoDB        │  │   ECR    │        │
                        │  │  (5 tables,         │  │ homeagent│        │
                        │  │   on-demand)        │  │ -backend │        │
                        │  └────────────────────┘  └──────────┘        │
                        └─────────────────────────────────────────────┘
```

### Network Layer

| Resource | Details |
|----------|---------|
| VPC | 2 Availability Zones |
| Public Subnets | ALB, NAT Gateway |
| Private Subnets | ECS tasks (no public IPs) |
| NAT Gateway | 1 (single for cost savings) |

### Compute Layer

| Resource | Details |
|----------|---------|
| ECS Cluster | Fargate launch type |
| Task Definition | 512 CPU, 1024 MiB memory |
| Container | `homeagent-backend:latest` from ECR |
| Worker | gunicorn + gevent (async I/O for SSE) |
| Auto-scaling | 1–4 tasks, CPU target 70% |
| ALB | Public, idle timeout 300s for SSE |
| Health Check | `GET /health` every 30s |

### Data Layer

| Table | Key Schema | GSI | Purpose |
|-------|-----------|-----|---------|
| Users | PK: `user_id` | — | User accounts |
| Devices | PK: `device_id` | `device_token-index` | Device registration, token lookup |
| InviteCodes | PK: `code` | — | One-time invite codes |
| Conversations | PK: `conversation_id` | `user_conversations-index` (user_id + updated_at) | Chat threads |
| Messages | PK: `conversation_id`, SK: `sort_key` | — | Chat messages, sorted by time |

All tables use on-demand billing (PAY_PER_REQUEST).

### AI Layer

| Resource | Details |
|----------|---------|
| Service | Amazon Bedrock |
| Model | Claude Opus 4.6 (`us.anthropic.claude-opus-4-6-v1`) |
| API | `converse_stream` (streaming) |
| Max Tokens | 4096 |
| Temperature | 0.7 |
| System Prompt | Configurable (default: family assistant persona) |

### Security

| Concern | Implementation |
|---------|---------------|
| Auth | Bearer token per device (`secrets.token_urlsafe(48)`) |
| Token Storage | Expo SecureStore (iOS Keychain / Android Keystore) |
| Role-Based Access | `admin` / `member` roles, decorator-enforced |
| Invite Codes | Single-use, required for registration |
| Container | Non-root user (`appuser`) |
| Network | Tasks in private subnets, ALB in public |
| IAM | Task role scoped to DynamoDB tables + Bedrock invoke |
| ECR | Lifecycle policy: keep last 10 images |

---

## CI/CD Pipeline

```
GitHub Push (master)
       │
       ▼
┌──────────────┐
│   Source      │  CodeStar Connection to GitHub
└──────┬───────┘
       ▼
┌──────────────┐
│   Synth       │  pip install CDK deps → cdk synth
└──────┬───────┘
       ▼
┌──────────────┐
│ UpdatePipeline│  Self-mutation: pipeline updates its own definition
└──────┬───────┘
       ▼
┌──────────────┐
│ BackendTests  │  DynamoDB Local in Docker → pytest
│  (pre-deploy) │  Blocks deploy if tests fail
└──────┬───────┘
       ▼
┌──────────────┐
│   Deploy      │  CDK deploys: Network → Data → Security → Service
└──────┬───────┘
       ▼
┌──────────────┐
│DockerBuildPush│  Build image → Push to ECR → Force new ECS deployment
│ (post-deploy) │  ECS cluster/service names resolved from CloudFormation
└──────────────┘
```

The pipeline is self-mutating: changes to `infra/stacks/pipeline_stack.py` automatically update the pipeline definition on the next run.

---

## Request Flow: Chat Message

```
1. Mobile sends POST /api/chat with Bearer token
2. ALB routes to ECS task (private subnet)
3. Flask @require_auth decorator:
   a. Extract token from Authorization header
   b. Query Devices GSI (device_token-index)
   c. Look up user from Users table
   d. Set g.user_id, g.user_name, g.user_role
4. Chat route:
   a. Create or validate conversation
   b. Store user message in Messages table
   c. Load last 50 messages as context
   d. Call Bedrock converse_stream API
5. SSE streaming response:
   a. Yield text_delta events as tokens arrive
   b. Yield message_done with token counts
   c. Store assistant message in Messages table
6. Mobile SSE client:
   a. Parse data: lines from stream
   b. Append text_delta content to UI in real-time
   c. On message_done, finalize conversation state
```

---

## Technology Stack

| Layer | Technology | Version |
|-------|-----------|---------|
| Mobile | Expo (React Native) | SDK 52, RN 0.76 |
| Mobile Language | TypeScript | 5.7 |
| Navigation | React Navigation | 7.0 |
| Secure Storage | expo-secure-store | 14.0 |
| Backend | Flask | 3.1 |
| WSGI Server | gunicorn + gevent | 23.0 / 24.11 |
| AI | Amazon Bedrock | Claude Opus 4.6 |
| Database | Amazon DynamoDB | On-demand |
| Container | Docker | python:3.12-slim |
| Orchestration | ECS Fargate | — |
| Load Balancer | Application LB | — |
| Infrastructure | AWS CDK | 2.177 |
| CI/CD | AWS CodePipeline | CDK Pipelines |
| Source Control | GitHub | CodeStar Connection |
| Container Registry | Amazon ECR | — |
