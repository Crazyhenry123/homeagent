# Infra Subagent — AWS CDK (Python)

## Scope
- You work ONLY on files under `infra/`.
- You may READ `backend/app/models/dynamo.py` to verify table schemas match CDK definitions.
- You may READ `backend/app/config.py` to verify environment variables match service stack container config.
- You may READ `webui/` to understand what static files get deployed.
- Never modify backend, mobile, or webui code.

## Tech Stack
- **AWS CDK** (`aws-cdk-lib 2.240+`) with Python
- **Constructs** library for base construct classes
- **Python 3.12**, type hints on all function signatures
- Only 2 dependencies: `aws-cdk-lib` and `constructs`

## Stack Architecture

```
infra/
├── app.py                    # CDK app entry point
├── cdk.json                  # CDK config + context values
├── cdk.context.json          # Cached context (AZs)
├── requirements.txt
└── stacks/
    ├── app_stage.py          # HomeAgentStage — orchestrates all stacks
    ├── pipeline_stack.py     # CI/CD pipeline (self-mutating + fast pipelines)
    ├── network_stack.py      # VPC + subnets
    ├── data_stack.py         # DynamoDB tables + S3 bucket
    ├── security_stack.py     # IAM roles + ECR repo
    ├── service_stack.py      # ECS Fargate + ALB
    └── webui_stack.py        # CloudFront + S3 static hosting
```

### Dependency Graph
```
NetworkStack ──┐
DataStack ─────┤──→ SecurityStack ──→ ServiceStack ──→ WebUiStack
               │                          │
               └──────────────────────────┘
```

### Rules
- One stack per concern — never merge unrelated resources into the same stack.
- Cross-stack dependencies pass through constructor parameters, not hardcoded names.
- `HomeAgentStage` in `app_stage.py` is the single place that wires stacks together.
- New stacks must be added to `HomeAgentStage` with explicit `add_dependency()` calls.

## CDK Patterns

### Construct Levels
- **L2 constructs** (default): Use curated constructs like `dynamodb.Table`, `ec2.Vpc`, `iam.Role`.
- **L3 patterns** (for complex setups): Use high-level patterns like `ecs_patterns.ApplicationLoadBalancedFargateService`.
- **L1 constructs** (escape hatch): Use `Cfn*` only when L2 doesn't expose a needed property. Always add a comment explaining why.
- **No custom constructs** unless a pattern is genuinely reused across 3+ stacks.

### Stack Constructor Pattern
```python
class DataStack(cdk.Stack):
    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # Create resources
        self.tables: dict[str, dynamodb.Table] = {}
        self.tables["Users"] = dynamodb.Table(
            self, "UsersTable",
            table_name="Users",
            partition_key=dynamodb.Attribute(
                name="user_id", type=dynamodb.AttributeType.STRING
            ),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            removal_policy=cdk.RemovalPolicy.RETAIN,
        )
```

### Rules
- Expose resources as instance attributes (`self.vpc`, `self.tables`, `self.task_role`) for cross-stack references.
- Use `cdk.RemovalPolicy.RETAIN` for all stateful resources (DynamoDB tables, S3 buckets with data).
- Use `cdk.RemovalPolicy.DESTROY` only for ephemeral resources (ECR images, log groups).
- Always set `billing_mode=PAY_PER_REQUEST` for DynamoDB (on-demand, no capacity planning).
- Tag resources with project context where appropriate.

## DynamoDB Table Definitions

### Adding a New Table
1. Add the table in `data_stack.py` with proper key schema and GSIs.
2. Add the table name to the `self.tables` dict so SecurityStack can grant permissions.
3. Verify the schema matches `backend/app/models/dynamo.py` exactly (key names, types, GSI names).
4. Add the corresponding table definition in `backend/app/models/dynamo.py` for local dev auto-creation.

### GSI Rules
- GSI names follow pattern: `field-name-index` (e.g., `user_conversations-index`).
- Always use `projection_type=ALL` unless you have a specific reason to limit projections.
- Never add a GSI that already exists on the physical table but isn't tracked by CDK — CloudFormation will fail. Add a comment explaining the situation.

### Schema Parity
- CDK table definitions (infra) and local auto-creation definitions (backend) MUST match exactly.
- When adding/changing a table, update BOTH files in the same change.

## ECS / ALB Configuration

### Key Settings
- **Task CPU**: 1024 (1 vCPU) — sufficient for Flask + gevent.
- **Task Memory**: 2048 MiB — sufficient for Bedrock streaming buffers.
- **ALB Idle Timeout**: 300 seconds — required for SSE long-lived connections.
- **Container Port**: 5000 — Flask default.
- **Health Check**: `GET /health` with 30s interval.
- **Auto-scaling**: 1-4 tasks, scale on 70% CPU utilization.

### Container Environment Variables
When adding a new backend config variable:
1. Add it to `ServiceStack` container `environment` dict.
2. Verify it matches `backend/app/config.py` `Config` class.
3. For secrets, use `secrets` parameter with `ecs.Secret.from_ssm_parameter()` — never put secrets in plain-text environment variables.

### Rules
- Never change the ALB idle timeout below 300s — it will break SSE streaming.
- Always use `assign_public_ip=False` — tasks run in private subnets behind ALB.
- Health check must match the backend's `/health` endpoint exactly.

## Pipeline Configuration

### Architecture
- **Main pipeline**: CDK Pipelines (self-mutating) — `homeagent-pipeline`.
- **Fast pipelines**: CodePipeline V2 with file-based triggers — deploy specific components without full CDK synth.

### Fast Pipeline Pattern
```
Source (GitHub, file filter: "area/**") → Build/Test (CodeBuild) → Deploy (CodeBuild)
```

### Rules
- Fast pipelines read resource names from **SSM Parameter Store** — never hardcode ARNs or names.
- When adding SSM parameters, store them in the stack that owns the resource (e.g., cluster name in ServiceStack).
- Fast pipeline CodeBuild environments need explicit IAM permissions for the resources they touch.
- Always test CodeBuild buildspec commands locally before committing.
- The main pipeline runs tests before deployment — fast pipelines may also run tests if deploying code.

### Adding a New Fast Pipeline
1. Define the pipeline in `pipeline_stack.py`.
2. Use `codepipeline.Pipeline` with `pipeline_type=V2` and `triggers` for git push filters.
3. Read resource references from SSM parameters.
4. Grant the CodeBuild role only the permissions it needs (least privilege).
5. Add file filters to trigger only on relevant directory changes.

## IAM & Security

### Principle of Least Privilege
```python
# Good: Grant per-table
for table in tables.values():
    table.grant_read_write_data(task_role)

# Bad: Grant all DynamoDB
task_role.add_to_policy(iam.PolicyStatement(
    actions=["dynamodb:*"], resources=["*"]
))
```

### Rules
- Use CDK grant methods (`grant_read_write_data`, `grant_pull`, `grant_read_write`) over raw IAM policy statements.
- When grant methods don't exist (e.g., Bedrock), use explicit `PolicyStatement` with specific actions and resources.
- `resources=["*"]` is acceptable for Bedrock model invocation (no resource-level ARN support), but add a comment explaining why.
- Never grant `*` actions — always enumerate specific actions.
- ECR repo grants pull only to the task role, not push.

## Network Configuration

### Current Setup
- VPC with 2 AZs, public + private subnets, 1 NAT gateway.
- ALB in public subnets, ECS tasks in private subnets.
- No custom security groups beyond what the L3 pattern creates.

### Rules
- Don't increase NAT gateways without justification — each costs ~$30/month.
- Don't add AZs beyond 2 unless high availability requirements change.
- Never put ECS tasks in public subnets.
- If adding a new service that needs internet access, route through the existing NAT gateway.

## Context & Configuration

### CDK Context (`cdk.json`)
- `account` — AWS account ID.
- `region` — Target region (default: us-east-1).
- `github_connection_arn` — CodeStar connection for GitHub.

### Rules
- Access context via `self.node.try_get_context("key")`.
- Validate required context values early — raise `ValueError` with a clear message if missing.
- Never hardcode account IDs or regions in stack code — use `cdk.Aws.ACCOUNT_ID` and `self.region`.
- `cdk.context.json` is auto-generated cache — commit it but don't edit manually.

## CloudFront / WebUI

### Architecture
- S3 bucket for static files (OAC restricted to CloudFront only).
- CloudFront distribution with behaviors:
  - Default (`*`) — S3 origin, cached.
  - `/api/*` — ALB origin, no caching.
  - `/health` — ALB origin, no caching.

### Rules
- API proxy behavior must have `CACHING_DISABLED` — never cache API responses.
- When adding new API path patterns, add a CloudFront behavior to route them to ALB.
- Static assets use `CACHING_OPTIMIZED` policy.

## Pre-Completion Checklist

Before considering any task done, verify:
- [ ] `cd infra && cdk synth` succeeds without errors
- [ ] New tables match `backend/app/models/dynamo.py` schema exactly
- [ ] New env vars match `backend/app/config.py` Config class
- [ ] Cross-stack dependencies are explicit (`add_dependency()`)
- [ ] Stateful resources use `RemovalPolicy.RETAIN`
- [ ] IAM follows least privilege (grant methods preferred)
- [ ] SSM parameters stored for anything fast pipelines need
- [ ] No hardcoded account IDs, regions, or resource ARNs
- [ ] Type hints on all function signatures
