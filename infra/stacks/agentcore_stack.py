import aws_cdk as cdk
from aws_cdk import aws_cognito as cognito
from aws_cdk import aws_dynamodb as dynamodb
from constructs import Construct


class AgentCoreStack(cdk.Stack):
    """Cognito User Pool and AgentCore-related DynamoDB tables."""

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
        # AgentCore DynamoDB tables (empty for now — extend as needed)
        # ------------------------------------------------------------------
        self.tables: dict[str, dynamodb.Table] = {}
