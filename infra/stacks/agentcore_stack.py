import aws_cdk as cdk
from aws_cdk import aws_cognito as cognito
from aws_cdk import aws_dynamodb as dynamodb
from aws_cdk import aws_iam as iam
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
        # AgentCore Memories (via Custom Resource — no L2 construct yet)
        # Two separate stores: family (long-term) and member (short-term)
        # ------------------------------------------------------------------
        agentcore_policy = cr.AwsCustomResourcePolicy.from_statements([
            iam.PolicyStatement(
                actions=[
                    "bedrock-agentcore-control:CreateMemory",
                    "bedrock-agentcore-control:DeleteMemory",
                    "bedrock-agentcore-control:GetMemory",
                ],
                resources=["*"],
            ),
        ])

        family_memory = cr.AwsCustomResource(
            self,
            "FamilyMemory",
            install_latest_aws_sdk=True,
            on_create=cr.AwsSdkCall(
                service="BedrockAgentCoreControl",
                action="CreateMemory",
                parameters={
                    "name": "homeagent_family_memory",
                    "description": "Long-term family memory: health, preferences, context",
                },
                physical_resource_id=cr.PhysicalResourceId.from_response(
                    "memoryId"
                ),
            ),
            on_delete=cr.AwsSdkCall(
                service="BedrockAgentCoreControl",
                action="DeleteMemory",
                parameters={
                    "memoryId": cr.PhysicalResourceIdReference(),
                },
            ),
            policy=agentcore_policy,
        )

        member_memory = cr.AwsCustomResource(
            self,
            "MemberMemory",
            install_latest_aws_sdk=True,
            on_create=cr.AwsSdkCall(
                service="BedrockAgentCoreControl",
                action="CreateMemory",
                parameters={
                    "name": "homeagent_member_memory",
                    "description": "Short-term member memory: session context and summaries",
                },
                physical_resource_id=cr.PhysicalResourceId.from_response(
                    "memoryId"
                ),
            ),
            on_delete=cr.AwsSdkCall(
                service="BedrockAgentCoreControl",
                action="DeleteMemory",
                parameters={
                    "memoryId": cr.PhysicalResourceIdReference(),
                },
            ),
            policy=agentcore_policy,
        )

        self.family_memory_id = family_memory.get_response_field("memoryId")
        self.member_memory_id = member_memory.get_response_field("memoryId")

        # ------------------------------------------------------------------
        # AgentCore DynamoDB tables (empty for now — extend as needed)
        # ------------------------------------------------------------------
        self.tables: dict[str, dynamodb.Table] = {}
