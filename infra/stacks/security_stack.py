import aws_cdk as cdk
from aws_cdk import aws_dynamodb as dynamodb
from aws_cdk import aws_ecr as ecr
from aws_cdk import aws_iam as iam
from constructs import Construct


class SecurityStack(cdk.Stack):
    def __init__(
        self,
        scope: Construct,
        id: str,
        tables: dict[str, dynamodb.Table],
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

        # Bedrock permissions
        self.task_role.add_to_policy(
            iam.PolicyStatement(
                actions=[
                    "bedrock:InvokeModel",
                    "bedrock:InvokeModelWithResponseStream",
                ],
                resources=["*"],
            )
        )

        # ECR pull for ECS tasks
        self.ecr_repo.grant_pull(self.task_role)

        cdk.CfnOutput(self, "TaskRoleArn", value=self.task_role.role_arn)
        cdk.CfnOutput(self, "EcrRepoUri", value=self.ecr_repo.repository_uri)
