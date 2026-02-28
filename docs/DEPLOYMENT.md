# HomeAgent — Deployment Guide

## Prerequisites

- **AWS Account** with admin access
- **GitHub account** with the `homeagent` repository
- **AWS CLI** configured with credentials (`aws configure`)
- **Node.js** 18+ and **Python** 3.12+
- **AWS CDK CLI** (`npm install -g aws-cdk`)

---

## 1. First-Time AWS Setup

### 1.1 Enable Bedrock Model Access

1. Open the [Amazon Bedrock console](https://console.aws.amazon.com/bedrock/)
2. Go to **Model access** in the left sidebar
3. Click **Manage model access**
4. Enable **Anthropic → Claude Opus 4.6**
5. Submit and wait for access to be granted

### 1.2 Create CodeStar Connection to GitHub

1. Open the [CodePipeline console](https://console.aws.amazon.com/codesuite/settings/connections)
2. Click **Create connection**
3. Select **GitHub** as the provider
4. Name it `homeagent-github`
5. Click **Connect to GitHub** and complete the OAuth flow
6. Copy the connection ARN (format: `arn:aws:codeconnections:REGION:ACCOUNT:connection/UUID`)

### 1.3 Bootstrap CDK

```bash
cd infra
pip install -r requirements.txt
cdk bootstrap aws://ACCOUNT_ID/us-east-1
```

Replace `ACCOUNT_ID` with your AWS account number.

---

## 2. Configure CDK Context

Edit `infra/cdk.json` and set:

```json
{
  "app": "python3 app.py",
  "context": {
    "@aws-cdk/core:stackRelativeExports": true,
    "@aws-cdk/aws-ecs:arnFormatIncludesClusterName": true,
    "github_connection_arn": "arn:aws:codeconnections:us-east-1:ACCOUNT_ID:connection/YOUR-UUID",
    "account": "ACCOUNT_ID",
    "region": "us-east-1"
  }
}
```

---

## 3. Deploy the Pipeline

```bash
cd infra
cdk deploy HomeAgentPipeline
```

This creates the CodePipeline and all application stacks:
- **NetworkStack** — VPC with public/private subnets
- **DataStack** — 5 DynamoDB tables
- **SecurityStack** — ECR repository + IAM task role
- **ServiceStack** — ECS Fargate cluster, task, ALB

### 3.1 Bootstrap the Docker Image (First Deploy Only)

ECS needs an image in ECR before the first deployment can succeed. The pipeline builds the image as a post-deploy step, creating a chicken-and-egg problem on the very first deploy.

**Solution:** Manually push the initial image:

```bash
# Get your account ID and region
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
REGION=us-east-1

# Login to ECR
aws ecr get-login-password --region $REGION \
  | docker login --username AWS --password-stdin $ACCOUNT_ID.dkr.ecr.$REGION.amazonaws.com

# Build and push
cd backend
docker build -t $ACCOUNT_ID.dkr.ecr.$REGION.amazonaws.com/homeagent-backend:latest .
docker push $ACCOUNT_ID.dkr.ecr.$REGION.amazonaws.com/homeagent-backend:latest
```

### 3.2 Trigger the Pipeline

Push to GitHub to trigger the pipeline:

```bash
git push origin master
```

Monitor progress in the [CodePipeline console](https://console.aws.amazon.com/codesuite/codepipeline/pipelines/homeagent-pipeline/).

Or via CLI:

```bash
# Check stage status
aws codepipeline get-pipeline-state --name homeagent-pipeline \
  --query 'stageStates[*].{Stage:stageName,Status:latestExecution.status}' \
  --output table

# Manually start a new execution
aws codepipeline start-pipeline-execution --name homeagent-pipeline
```

---

## 4. Get the Backend URL

After the pipeline completes successfully:

```bash
aws cloudformation describe-stacks \
  --stack-name Deploy-Service \
  --query 'Stacks[0].Outputs[?OutputKey==`ServiceUrl`].OutputValue' \
  --output text
```

Or find it in the CloudFormation console under **Deploy-Service** stack → Outputs → **ServiceUrl**.

Verify:

```bash
curl http://<ALB-URL>/health
# {"status": "healthy"}
```

---

## 5. Update the Mobile App

Set the backend URL in `mobile/app.json`:

```json
{
  "expo": {
    "extra": {
      "apiBaseUrl": "http://<ALB-URL>"
    }
  }
}
```

Commit and push — the pipeline will automatically pick up the change on the next run.

---

## 6. Environment Variables

### ECS Task Environment (set in `infra/stacks/service_stack.py`)

| Variable | Default | Description |
|----------|---------|-------------|
| `AWS_REGION` | `us-east-1` | AWS region for Bedrock and DynamoDB |
| `BEDROCK_MODEL_ID` | `us.anthropic.claude-opus-4-6-v1` | Claude model to use |
| `SYSTEM_PROMPT` | Family assistant persona | System prompt sent to Claude |
| `ADMIN_INVITE_CODE` | `FAMILY` | Pre-seeded invite code for the first admin user |

To change these, edit `service_stack.py` and push — the pipeline will update ECS.

### Pipeline Test Environment

| Variable | Value | Description |
|----------|-------|-------------|
| `DYNAMODB_ENDPOINT` | `http://localhost:8000` | DynamoDB Local for tests |
| `ADMIN_INVITE_CODE` | `TESTCODE` | Test invite code |

---

## 7. Infrastructure Stacks

The pipeline deploys these stacks in order:

| Stack | Resources | Dependencies |
|-------|-----------|-------------|
| `Deploy-Network` | VPC, subnets, NAT Gateway | — |
| `Deploy-Data` | 5 DynamoDB tables | — |
| `Deploy-Security` | ECR repo, IAM task role | Data (table ARNs) |
| `Deploy-Service` | ECS cluster, task, ALB, auto-scaling | Network, Security |

### Stack Outputs

| Stack | Output | Description |
|-------|--------|-------------|
| `Deploy-Service` | `ServiceUrl` | ALB DNS name |
| `Deploy-Service` | `ClusterName` | ECS cluster name |
| `Deploy-Service` | `ServiceName` | ECS service name |

---

## 8. Scaling

### ECS Auto-Scaling

Current configuration (in `service_stack.py`):
- Min tasks: 1
- Max tasks: 4
- Scale trigger: CPU utilization > 70%

To adjust:
```python
scaling = service.service.auto_scale_task_count(
    min_capacity=1, max_capacity=10  # Increase max
)
scaling.scale_on_cpu_utilization(
    "CpuScaling", target_utilization_percent=60  # More aggressive scaling
)
```

### Task Size

Current: 512 CPU / 1024 MiB. To increase for heavier workloads:
```python
task_def = ecs.FargateTaskDefinition(
    self, "TaskDef",
    cpu=1024,            # 1 vCPU
    memory_limit_mib=2048,  # 2 GB
    task_role=task_role,
)
```

### DynamoDB

All tables use on-demand billing — no scaling configuration needed. DynamoDB scales automatically.

---

## 9. Monitoring

### CloudWatch Logs

Application logs are in the `/ecs/homeagent` log group with a 2-week retention.

```bash
# Tail recent logs
aws logs tail /ecs/homeagent --follow --since 5m
```

### ECS Service Status

```bash
# Service health
aws ecs describe-services \
  --cluster <ClusterName> \
  --services <ServiceName> \
  --query 'services[0].{Status:status,Running:runningCount,Desired:desiredCount,Deployments:deployments[*].status}'
```

### Pipeline Monitoring

```bash
# Check all stages
aws codepipeline get-pipeline-state --name homeagent-pipeline \
  --query 'stageStates[*].{Stage:stageName,Status:latestExecution.status}' \
  --output table

# Recent executions
aws codepipeline list-pipeline-executions --name homeagent-pipeline \
  --max-items 5 \
  --query 'pipelineExecutionSummaries[*].{Id:pipelineExecutionId,Status:status,Start:startTime}' \
  --output table
```

---

## 10. Rollback

### ECS Rollback

ECS maintains the previous task definition. To roll back:

```bash
# List task definition revisions
aws ecs list-task-definitions --family-prefix Deploy-Service --sort DESC --max-items 5

# Update service to previous revision
aws ecs update-service \
  --cluster <ClusterName> \
  --service <ServiceName> \
  --task-definition <previous-task-def-arn>
```

### ECR Image Rollback

ECR keeps the last 10 images. To deploy a previous image:

```bash
# List available images
aws ecr list-images --repository-name homeagent-backend \
  --query 'imageIds[*].imageTag' --output table

# Tag a previous image as latest
MANIFEST=$(aws ecr batch-get-image --repository-name homeagent-backend \
  --image-ids imageTag=<commit-hash> --query 'images[0].imageManifest' --output text)

aws ecr put-image --repository-name homeagent-backend \
  --image-tag latest --image-manifest "$MANIFEST"

# Force ECS to pick up the new latest
aws ecs update-service --cluster <ClusterName> --service <ServiceName> --force-new-deployment
```

---

## 11. Teardown

To remove all resources:

```bash
cd infra

# Destroy the pipeline (this also destroys all application stacks)
cdk destroy HomeAgentPipeline

# If stacks remain, destroy individually
cdk destroy Deploy-Service Deploy-Security Deploy-Data Deploy-Network
```

**Note:** DynamoDB tables have `RETAIN` removal policy — they won't be deleted with the stack. Delete them manually if needed:

```bash
aws dynamodb delete-table --table-name Users
aws dynamodb delete-table --table-name Devices
aws dynamodb delete-table --table-name InviteCodes
aws dynamodb delete-table --table-name Conversations
aws dynamodb delete-table --table-name Messages
```
