import aws_cdk as cdk
from aws_cdk import aws_dynamodb as dynamodb
from aws_cdk import aws_ec2 as ec2
from aws_cdk import aws_ecr as ecr
from aws_cdk import aws_ecs as ecs
from aws_cdk import aws_ecs_patterns as ecs_patterns
from aws_cdk import aws_iam as iam
from aws_cdk import aws_logs as logs
from aws_cdk import aws_ssm as ssm
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
        documents_bucket_name: str | None = None,
        cognito_user_pool_id: str | None = None,
        cognito_client_id: str | None = None,
        agentcore_memory_id: str | None = None,
        agentcore_family_memory_id: str | None = None,
        agentcore_member_memory_id: str | None = None,
        agentcore_runtime_arn: str | None = None,
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

        # Fargate task definition (bumped for agent orchestration workload)
        task_def = ecs.FargateTaskDefinition(
            self,
            "TaskDef",
            cpu=1024,
            memory_limit_mib=2048,
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
                "USE_AGENT_ORCHESTRATOR": "true",
                "HEALTH_EXTRACTION_ENABLED": "true",
                "HEALTH_EXTRACTION_MODEL_ID": "us.anthropic.claude-haiku-4-5-20251001-v1:0",
                "CHAT_MEDIA_MAX_SIZE": str(5 * 1024 * 1024),
                "VOICE_ENABLED": "true",
                "VOICE_MODEL_ID": "amazon.nova-sonic-v1:0",
                **({"S3_HEALTH_DOCUMENTS_BUCKET": documents_bucket_name} if documents_bucket_name else {}),
                **({"COGNITO_USER_POOL_ID": cognito_user_pool_id} if cognito_user_pool_id else {}),
                **({"COGNITO_CLIENT_ID": cognito_client_id} if cognito_client_id else {}),
                **({"AGENTCORE_MEMORY_ID": agentcore_memory_id} if agentcore_memory_id else {}),
                **({"AGENTCORE_FAMILY_MEMORY_ID": agentcore_family_memory_id} if agentcore_family_memory_id else {}),
                **({"AGENTCORE_MEMBER_MEMORY_ID": agentcore_member_memory_id} if agentcore_member_memory_id else {}),
                **({"AGENTCORE_RUNTIME_ARN": agentcore_runtime_arn} if agentcore_runtime_arn else {}),
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

        # SSE and WebSocket connections require long idle timeout
        service.load_balancer.set_attribute(
            "idle_timeout.timeout_seconds", "300"
        )

        # Enable stickiness so WebSocket connections stay on the same target
        service.target_group.set_attribute(
            "stickiness.enabled", "true"
        )
        service.target_group.set_attribute(
            "stickiness.type", "lb_cookie"
        )
        service.target_group.set_attribute(
            "stickiness.lb_cookie.duration_seconds", "3600"
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

        # Expose ALB for CloudFront origin
        self.load_balancer = service.load_balancer

        cdk.CfnOutput(
            self,
            "ServiceUrl",
            value=f"http://{service.load_balancer.load_balancer_dns_name}",
        )
        self.cluster_name_output = cdk.CfnOutput(
            self, "ClusterName", value=cluster.cluster_name
        )
        self.service_name_output = cdk.CfnOutput(
            self, "ServiceName", value=service.service.service_name
        )

        # SSM parameters so the fast backend pipeline can look up cluster/service
        ssm.StringParameter(
            self,
            "BackendClusterNameParam",
            parameter_name="/homeagent/backend/cluster-name",
            string_value=cluster.cluster_name,
        )
        ssm.StringParameter(
            self,
            "BackendServiceNameParam",
            parameter_name="/homeagent/backend/service-name",
            string_value=service.service.service_name,
        )
        # API base URL for mobile pipeline to inject into Expo builds
        ssm.StringParameter(
            self,
            "BackendApiBaseUrlParam",
            parameter_name="/homeagent/backend/api-base-url",
            string_value=f"http://{service.load_balancer.load_balancer_dns_name}",
        )
