import aws_cdk as cdk
from aws_cdk import aws_dynamodb as dynamodb
from aws_cdk import aws_ecr as ecr
from aws_cdk import aws_iam as iam
from aws_cdk import aws_s3 as s3
from constructs import Construct


class SecurityStack(cdk.Stack):
    def __init__(
        self,
        scope: Construct,
        id: str,
        tables: dict[str, dynamodb.Table],
        documents_bucket: s3.Bucket | None = None,
        **kwargs,
    ) -> None:
        super().__init__(scope, id, **kwargs)

        # ECR repository for the backend image
        self.ecr_repo = ecr.Repository(
            self,
            "BackendRepo",
            repository_name="homeagent-backend",
            removal_policy=cdk.RemovalPolicy.DESTROY,
            empty_on_delete=True,
            lifecycle_rules=[
                ecr.LifecycleRule(max_image_count=10, description="Keep last 10 images")
            ],
        )

        # ECS task role
        self.task_role = iam.Role(
            self,
            "TaskRole",
            assumed_by=iam.ServicePrincipal("ecs-tasks.amazonaws.com"),
            description="HomeAgent ECS task role",
        )

        # DynamoDB permissions
        for table in tables.values():
            table.grant_read_write_data(self.task_role)

        # Bedrock permissions (model invocation)
        self.task_role.add_to_policy(
            iam.PolicyStatement(
                actions=[
                    "bedrock:InvokeModel",
                    "bedrock:InvokeModelWithResponseStream",
                ],
                resources=["*"],
            )
        )

        # Bedrock AgentCore Memory permissions
        # Control plane (create/get/list/delete memories)
        self.task_role.add_to_policy(
            iam.PolicyStatement(
                actions=[
                    "bedrock-agentcore-control:CreateMemory",
                    "bedrock-agentcore-control:GetMemory",
                    "bedrock-agentcore-control:ListMemories",
                    "bedrock-agentcore-control:DeleteMemory",
                    "bedrock-agentcore-control:UpdateMemory",
                    "bedrock-agentcore-control:CreateMemoryStrategy",
                    "bedrock-agentcore-control:DeleteMemoryStrategy",
                ],
                resources=["*"],
            )
        )
        # Data plane (read/write memory records)
        self.task_role.add_to_policy(
            iam.PolicyStatement(
                actions=[
                    "bedrock-agentcore:RetrieveMemoryRecords",
                    "bedrock-agentcore:CreateMemoryRecords",
                    "bedrock-agentcore:DeleteMemoryRecords",
                    "bedrock-agentcore:IngestMemoryEvents",
                ],
                resources=["*"],
            )
        )

        # Cognito permissions (token verification)
        self.task_role.add_to_policy(
            iam.PolicyStatement(
                actions=[
                    "cognito-idp:GetUser",
                    "cognito-idp:AdminGetUser",
                ],
                resources=["*"],
            )
        )

        # AWS Transcribe permissions (voice-to-chat audio transcription)
        self.task_role.add_to_policy(
            iam.PolicyStatement(
                actions=[
                    "transcribe:StartTranscriptionJob",
                    "transcribe:GetTranscriptionJob",
                    "transcribe:DeleteTranscriptionJob",
                ],
                resources=["*"],
            )
        )

        # S3 documents bucket permissions
        if documents_bucket:
            documents_bucket.grant_read_write(self.task_role)

        # ECR pull for ECS tasks
        self.ecr_repo.grant_pull(self.task_role)

        cdk.CfnOutput(self, "TaskRoleArn", value=self.task_role.role_arn)
        cdk.CfnOutput(self, "EcrRepoUri", value=self.ecr_repo.repository_uri)
