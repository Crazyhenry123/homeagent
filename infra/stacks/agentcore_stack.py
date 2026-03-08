import os

import aws_cdk as cdk
from aws_cdk import aws_cognito as cognito
from aws_cdk import aws_dynamodb as dynamodb
from aws_cdk import aws_iam as iam
from aws_cdk import aws_lambda as _lambda
from aws_cdk import custom_resources as cr
from constructs import Construct


class AgentCoreStack(cdk.Stack):
    """Cognito User Pool, AgentCore Memory, and related resources."""

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
