import os

import aws_cdk as cdk
from aws_cdk import aws_cognito as cognito
from aws_cdk import aws_dynamodb as dynamodb
from aws_cdk import aws_iam as iam
from aws_cdk import aws_lambda as _lambda
from aws_cdk import aws_s3 as s3
from aws_cdk import aws_s3_deployment as s3deploy
from aws_cdk import custom_resources as cr
from constructs import Construct


class AgentCoreStack(cdk.Stack):
    """Cognito User Pool, AgentCore Memory, Runtime, and Gateway resources."""

    def __init__(self, scope: Construct, id: str, **kwargs) -> None:
        super().__init__(scope, id, **kwargs)

        # ------------------------------------------------------------------
        # Cognito User Pool for authentication
        # ------------------------------------------------------------------
        self.user_pool = cognito.UserPool(
            self,
            "UserPool",
            user_pool_name="homeagent-users",
            self_sign_up_enabled=True,
            sign_in_aliases=cognito.SignInAliases(email=True),
            auto_verify=cognito.AutoVerifiedAttrs(email=True),
            standard_attributes=cognito.StandardAttributes(
                email=cognito.StandardAttribute(required=True, mutable=True),
            ),
            password_policy=cognito.PasswordPolicy(
                min_length=8,
                require_lowercase=True,
                require_uppercase=True,
                require_digits=True,
                require_symbols=False,
            ),
            removal_policy=cdk.RemovalPolicy.RETAIN,
        )

        self.user_pool_client = self.user_pool.add_client(
            "AppClient",
            user_pool_client_name="homeagent-app",
            auth_flows=cognito.AuthFlow(
                user_password=True,
                user_srp=True,
            ),
            generate_secret=False,
        )

        # ------------------------------------------------------------------
        # AgentCore Memories via Python Lambda Custom Resource
        # AwsCustomResource (JS SDK) doesn't work — no JS SDK for
        # bedrock-agentcore-control. Use Python Lambda with boto3 instead.
        # ------------------------------------------------------------------
        memory_handler = _lambda.Function(
            self,
            "MemoryHandler",
            runtime=_lambda.Runtime.PYTHON_3_12,
            handler="index.on_event",
            code=_lambda.Code.from_asset(
                os.path.join(os.path.dirname(__file__), "..", "lambda", "agentcore_memory"),
                bundling=cdk.BundlingOptions(
                    image=_lambda.Runtime.PYTHON_3_12.bundling_image,
                    command=[
                        "bash",
                        "-c",
                        "pip install boto3 -t /asset-output && cp -au . /asset-output",
                    ],
                ),
            ),
            timeout=cdk.Duration.minutes(5),
        )

        # Grant both bedrock-agentcore and bedrock-agentcore-control namespaces.
        # The signing name is "bedrock-agentcore" but some actions may use
        # the control-plane namespace. Grant both to avoid permission errors.
        memory_handler.add_to_role_policy(
            iam.PolicyStatement(
                actions=[
                    "bedrock-agentcore:CreateMemory",
                    "bedrock-agentcore:DeleteMemory",
                    "bedrock-agentcore:GetMemory",
                    "bedrock-agentcore-control:CreateMemory",
                    "bedrock-agentcore-control:DeleteMemory",
                    "bedrock-agentcore-control:GetMemory",
                ],
                resources=["*"],
            )
        )

        provider = cr.Provider(
            self,
            "MemoryProvider",
            on_event_handler=memory_handler,
        )

        family_memory = cdk.CustomResource(
            self,
            "FamilyMemory",
            service_token=provider.service_token,
            properties={
                "MemoryName": "homeagent_family_memory",
                "MemoryDescription": "Long-term family memory: health, preferences, context",
                "EventExpiryDuration": "365",
                "Region": self.region,
            },
        )
        # Ensure IAM policy is applied before the custom resource invokes Lambda
        family_memory.node.add_dependency(memory_handler.role)

        member_memory = cdk.CustomResource(
            self,
            "MemberMemory",
            service_token=provider.service_token,
            properties={
                "MemoryName": "homeagent_member_memory",
                "MemoryDescription": "Short-term member memory: session context and summaries",
                "EventExpiryDuration": "30",
                "Region": self.region,
            },
        )
        # Ensure IAM policy is applied before the custom resource invokes Lambda
        member_memory.node.add_dependency(memory_handler.role)

        self.family_memory_id = family_memory.get_att_string("memoryId")
        self.member_memory_id = member_memory.get_att_string("memoryId")

        # ------------------------------------------------------------------
        # AgentCore DynamoDB tables (empty for now — extend as needed)
        # ------------------------------------------------------------------
        self.tables: dict[str, dynamodb.Table] = {}

        # ------------------------------------------------------------------
        # AgentCore Runtime — orchestrator agent deployed as code
        # ------------------------------------------------------------------

        # S3 bucket for agent deployment package
        agent_code_bucket = s3.Bucket(
            self,
            "AgentCodeBucket",
            removal_policy=cdk.RemovalPolicy.DESTROY,
            auto_delete_objects=True,
        )

        # Deploy agent code to S3
        agent_code_path = os.path.join(
            os.path.dirname(__file__), "..", "..", "agent"
        )
        deployment = s3deploy.BucketDeployment(
            self,
            "AgentCodeDeployment",
            sources=[s3deploy.Source.asset(agent_code_path)],
            destination_bucket=agent_code_bucket,
            destination_key_prefix="homeagent-orchestrator",
        )

        # IAM role for the AgentCore Runtime agent
        self.runtime_role = iam.Role(
            self,
            "AgentRuntimeRole",
            assumed_by=iam.CompositePrincipal(
                iam.ServicePrincipal("bedrock-agentcore.amazonaws.com"),
                iam.ServicePrincipal("bedrock.amazonaws.com"),
            ),
            description="IAM role for HomeAgent AgentCore Runtime orchestrator",
        )

        # Runtime needs Bedrock model invocation
        self.runtime_role.add_to_policy(
            iam.PolicyStatement(
                actions=[
                    "bedrock:InvokeModel",
                    "bedrock:InvokeModelWithResponseStream",
                ],
                resources=["*"],
            )
        )

        # Runtime needs S3 access to read its own code
        agent_code_bucket.grant_read(self.runtime_role)

        # Runtime needs CloudWatch Logs
        self.runtime_role.add_to_policy(
            iam.PolicyStatement(
                actions=[
                    "logs:CreateLogGroup",
                    "logs:CreateLogStream",
                    "logs:PutLogEvents",
                ],
                resources=["*"],
            )
        )

        # Lambda custom resource for AgentCore Runtime + Endpoint
        runtime_handler = _lambda.Function(
            self,
            "RuntimeHandler",
            runtime=_lambda.Runtime.PYTHON_3_12,
            handler="index.on_event",
            code=_lambda.Code.from_asset(
                os.path.join(
                    os.path.dirname(__file__), "..", "lambda", "agentcore_runtime"
                ),
                bundling=cdk.BundlingOptions(
                    image=_lambda.Runtime.PYTHON_3_12.bundling_image,
                    command=[
                        "bash",
                        "-c",
                        "pip install boto3 -t /asset-output && cp -au . /asset-output",
                    ],
                ),
            ),
            timeout=cdk.Duration.minutes(10),
        )

        # Grant the Lambda permissions to manage AgentCore Runtimes
        runtime_handler.add_to_role_policy(
            iam.PolicyStatement(
                actions=[
                    "bedrock-agentcore:CreateAgentRuntime",
                    "bedrock-agentcore:GetAgentRuntime",
                    "bedrock-agentcore:DeleteAgentRuntime",
                    "bedrock-agentcore:CreateAgentRuntimeEndpoint",
                    "bedrock-agentcore:GetAgentRuntimeEndpoint",
                    "bedrock-agentcore:DeleteAgentRuntimeEndpoint",
                    "bedrock-agentcore:ListAgentRuntimeEndpoints",
                    "bedrock-agentcore-control:CreateAgentRuntime",
                    "bedrock-agentcore-control:GetAgentRuntime",
                    "bedrock-agentcore-control:DeleteAgentRuntime",
                    "bedrock-agentcore-control:CreateAgentRuntimeEndpoint",
                    "bedrock-agentcore-control:GetAgentRuntimeEndpoint",
                    "bedrock-agentcore-control:DeleteAgentRuntimeEndpoint",
                    "bedrock-agentcore-control:ListAgentRuntimeEndpoints",
                ],
                resources=["*"],
            )
        )

        # Lambda needs to pass the runtime role to AgentCore
        runtime_handler.add_to_role_policy(
            iam.PolicyStatement(
                actions=["iam:PassRole"],
                resources=[self.runtime_role.role_arn],
            )
        )

        runtime_provider = cr.Provider(
            self,
            "RuntimeProvider",
            on_event_handler=runtime_handler,
        )

        agent_runtime = cdk.CustomResource(
            self,
            "OrchestratorRuntime",
            service_token=runtime_provider.service_token,
            properties={
                "AgentRuntimeName": "homeagent_orchestrator",
                "RoleArn": self.runtime_role.role_arn,
                "S3Bucket": agent_code_bucket.bucket_name,
                "S3Prefix": "homeagent-orchestrator",
                "NetworkMode": "PUBLIC",
                "Region": self.region,
            },
        )
        # Ensure code is deployed and IAM is ready before creating runtime
        agent_runtime.node.add_dependency(deployment)
        agent_runtime.node.add_dependency(runtime_handler.role)
        agent_runtime.node.add_dependency(self.runtime_role)

        self.agent_runtime_id = agent_runtime.get_att_string("agentRuntimeId")
        self.agent_runtime_arn = agent_runtime.get_att_string("agentRuntimeArn")

        # ------------------------------------------------------------------
        # Outputs
        # ------------------------------------------------------------------
        cdk.CfnOutput(self, "UserPoolId", value=self.user_pool.user_pool_id)
        cdk.CfnOutput(
            self, "UserPoolClientId",
            value=self.user_pool_client.user_pool_client_id,
        )
        cdk.CfnOutput(self, "FamilyMemoryId", value=self.family_memory_id)
        cdk.CfnOutput(self, "MemberMemoryId", value=self.member_memory_id)
        cdk.CfnOutput(self, "AgentRuntimeId", value=self.agent_runtime_id)
        cdk.CfnOutput(self, "AgentRuntimeArn", value=self.agent_runtime_arn)
        cdk.CfnOutput(
            self, "AgentCodeBucketName", value=agent_code_bucket.bucket_name
        )
