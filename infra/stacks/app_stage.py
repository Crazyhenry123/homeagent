import aws_cdk as cdk
from constructs import Construct

from stacks.agentcore_stack import AgentCoreStack
from stacks.network_stack import NetworkStack
from stacks.data_stack import DataStack
from stacks.security_stack import SecurityStack
from stacks.service_stack import ServiceStack
from stacks.webui_stack import WebUiStack


class HomeAgentStage(cdk.Stage):
    """All HomeAgent infrastructure stacks grouped into a single deploy stage."""

    def __init__(self, scope: Construct, id: str, **kwargs) -> None:
        super().__init__(scope, id, **kwargs)

        network = NetworkStack(self, "Network")
        data = DataStack(self, "Data")
        agentcore = AgentCoreStack(self, "AgentCore")
        security = SecurityStack(
            self,
            "Security",
            tables={**data.tables, **agentcore.tables},
            documents_bucket=data.documents_bucket,
        )
        self.service_stack = ServiceStack(
            self,
            "Service",
            vpc=network.vpc,
            task_role=security.task_role,
            ecr_repo=security.ecr_repo,
            tables={**data.tables, **agentcore.tables},
            documents_bucket_name=data.documents_bucket.bucket_name,
            cognito_user_pool_id=agentcore.user_pool.user_pool_id,
            cognito_client_id=agentcore.user_pool_client.user_pool_client_id,
            agentcore_memory_id=agentcore.family_memory_id,
            agentcore_family_memory_id=agentcore.family_memory_id,
            agentcore_member_memory_id=agentcore.member_memory_id,
        )
        self.webui_stack = WebUiStack(
            self,
            "WebUi",
            load_balancer=self.service_stack.load_balancer,
        )
