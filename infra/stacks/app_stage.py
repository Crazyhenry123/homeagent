import aws_cdk as cdk
from constructs import Construct

from stacks.network_stack import NetworkStack
from stacks.data_stack import DataStack
from stacks.security_stack import SecurityStack
from stacks.service_stack import ServiceStack


class HomeAgentStage(cdk.Stage):
    """All HomeAgent infrastructure stacks grouped into a single deploy stage."""

    def __init__(self, scope: Construct, id: str, **kwargs) -> None:
        super().__init__(scope, id, **kwargs)

        network = NetworkStack(self, "Network")
        data = DataStack(self, "Data")
        security = SecurityStack(self, "Security", tables=data.tables)
        self.service_stack = ServiceStack(
            self,
            "Service",
            vpc=network.vpc,
            task_role=security.task_role,
            ecr_repo=security.ecr_repo,
            tables=data.tables,
        )
