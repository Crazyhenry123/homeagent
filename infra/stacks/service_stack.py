import aws_cdk as cdk
from aws_cdk import aws_dynamodb as dynamodb
from aws_cdk import aws_ec2 as ec2
from aws_cdk import aws_ecr as ecr
from aws_cdk import aws_ecs as ecs
from aws_cdk import aws_ecs_patterns as ecs_patterns
from aws_cdk import aws_iam as iam
from aws_cdk import aws_logs as logs
from constructs import Construct


class ServiceStack(cdk.Stack):
    def __init__(
        self,
        scope: Construct,
        id: str,
        vpc: ec2.Vpc,
        task_role: iam.Role,
        ecr_repo: ecr.Repository,
        tables: dict[str, dynamodb.Table],
        **kwargs,
    ) -> None:
        super().__init__(scope, id, **kwargs)

        # CloudWatch log group
        log_group = logs.LogGroup(
            self,
            "ServiceLogs",
            log_group_name="/ecs/homeagent",
            retention=logs.RetentionDays.TWO_WEEKS,
            removal_policy=cdk.RemovalPolicy.DESTROY,
        )

        # ECS cluster
        cluster = ecs.Cluster(self, "Cluster", vpc=vpc)

        # Fargate task definition
        task_def = ecs.FargateTaskDefinition(
            self,
            "TaskDef",
            cpu=512,
            memory_limit_mib=1024,
            task_role=task_role,
        )

        container = task_def.add_container(
            "api",
            image=ecs.ContainerImage.from_ecr_repository(ecr_repo, tag="latest"),
            logging=ecs.LogDrivers.aws_logs(
                stream_prefix="api", log_group=log_group
            ),
            environment={
                "AWS_REGION": self.region,
                "BEDROCK_MODEL_ID": "us.anthropic.claude-opus-4-6-v1",
                "SYSTEM_PROMPT": (
                    "You are a helpful family assistant. "
                    "Be warm, friendly, and supportive."
                ),
                "ADMIN_INVITE_CODE": "FAMILY",
            },
            health_check=ecs.HealthCheck(
                command=[
                    "CMD-SHELL",
                    "python -c \"import urllib.request; "
                    "urllib.request.urlopen('http://localhost:5000/health')\"",
                ],
                interval=cdk.Duration.seconds(30),
                timeout=cdk.Duration.seconds(5),
                retries=3,
            ),
        )
        container.add_port_mappings(ecs.PortMapping(container_port=5000))

        # ALB-fronted Fargate service
        service = ecs_patterns.ApplicationLoadBalancedFargateService(
            self,
            "Service",
            cluster=cluster,
            task_definition=task_def,
            desired_count=1,
            public_load_balancer=True,
            assign_public_ip=False,
            min_healthy_percent=100,
        )

        # SSE requires long idle timeout
        service.load_balancer.set_attribute(
            "idle_timeout.timeout_seconds", "300"
        )

        # ALB health check
        service.target_group.configure_health_check(
            path="/health",
            healthy_http_codes="200",
            interval=cdk.Duration.seconds(30),
        )

        # Auto-scaling
        scaling = service.service.auto_scale_task_count(
            min_capacity=1, max_capacity=4
        )
        scaling.scale_on_cpu_utilization(
            "CpuScaling", target_utilization_percent=70
        )

        cdk.CfnOutput(
            self,
            "ServiceUrl",
            value=f"http://{service.load_balancer.load_balancer_dns_name}",
        )
        cdk.CfnOutput(self, "ClusterName", value=cluster.cluster_name)
        cdk.CfnOutput(self, "ServiceName", value=service.service.service_name)
