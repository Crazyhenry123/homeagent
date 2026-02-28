import aws_cdk as cdk
from aws_cdk import aws_codecommit as codecommit
from aws_cdk import aws_codebuild as codebuild
from aws_cdk import aws_codepipeline as codepipeline
from aws_cdk import aws_iam as iam
from aws_cdk import pipelines
from constructs import Construct

from stacks.app_stage import HomeAgentStage


class PipelineStack(cdk.Stack):
    """Self-mutating CDK Pipeline: CodeCommit -> Test -> Deploy infra -> Build & push Docker -> Update ECS."""

    def __init__(self, scope: Construct, id: str, **kwargs) -> None:
        super().__init__(scope, id, **kwargs)

        # ------------------------------------------------------------------
        # Source: CodeCommit
        # ------------------------------------------------------------------
        repo = codecommit.Repository(
            self,
            "Repo",
            repository_name="homeagent",
            description="HomeAgent family AI agent monorepo",
        )

        source = pipelines.CodePipelineSource.code_commit(repo, "main")

        # ------------------------------------------------------------------
        # Synth: install CDK deps and synthesize CloudFormation
        # ------------------------------------------------------------------
        synth = pipelines.ShellStep(
            "Synth",
            input=source,
            install_commands=[
                "cd infra",
                "pip install -r requirements.txt",
            ],
            commands=[
                "cd infra",
                "npx cdk synth",
            ],
            primary_output_directory="infra/cdk.out",
        )

        build_env = codebuild.BuildEnvironment(
            build_image=codebuild.LinuxBuildImage.STANDARD_7_0,
            privileged=True,
            compute_type=codebuild.ComputeType.MEDIUM,
        )

        pipeline = pipelines.CodePipeline(
            self,
            "Pipeline",
            pipeline_name="homeagent-pipeline",
            synth=synth,
            pipeline_type=codepipeline.PipelineType.V2,
            docker_enabled_for_synth=True,
            docker_enabled_for_self_mutation=True,
            code_build_defaults=pipelines.CodeBuildOptions(
                build_environment=build_env,
            ),
        )

        # ------------------------------------------------------------------
        # Pre-deploy: run backend unit tests with DynamoDB Local
        # ------------------------------------------------------------------
        test_step = pipelines.CodeBuildStep(
            "BackendTests",
            input=source,
            install_commands=[
                "cd backend",
                "pip install -r requirements.txt pytest",
            ],
            commands=[
                "docker run -d --name dynamodb-test -p 8000:8000 "
                "amazon/dynamodb-local -jar DynamoDBLocal.jar -sharedDb -inMemory",
                "sleep 3",
                "cd backend",
                "python -m pytest tests/ -v",
            ],
            build_environment=build_env,
            env={
                "AWS_REGION": "us-east-1",
                "AWS_ACCESS_KEY_ID": "testing",
                "AWS_SECRET_ACCESS_KEY": "testing",
                "DYNAMODB_ENDPOINT": "http://localhost:8000",
                "ADMIN_INVITE_CODE": "TESTCODE",
            },
        )

        # ------------------------------------------------------------------
        # Post-deploy: build Docker image, push to ECR, update ECS service
        # ------------------------------------------------------------------
        docker_build_step = pipelines.CodeBuildStep(
            "DockerBuildPush",
            input=source,
            commands=[
                # Login to ECR
                "aws ecr get-login-password --region $AWS_DEFAULT_REGION "
                "| docker login --username AWS --password-stdin $ECR_REPO_URI",
                # Build
                "cd backend",
                "docker build -t $ECR_REPO_URI:$CODEBUILD_RESOLVED_SOURCE_VERSION .",
                "docker tag $ECR_REPO_URI:$CODEBUILD_RESOLVED_SOURCE_VERSION $ECR_REPO_URI:latest",
                # Push
                "docker push $ECR_REPO_URI:$CODEBUILD_RESOLVED_SOURCE_VERSION",
                "docker push $ECR_REPO_URI:latest",
                # Force new ECS deployment to pick up latest image
                "aws ecs update-service --cluster $ECS_CLUSTER_NAME --service $ECS_SERVICE_NAME --force-new-deployment",
            ],
            build_environment=build_env,
            env={
                "ECR_REPO_URI": f"{self.account}.dkr.ecr.{self.region}.amazonaws.com/homeagent-backend",
                "ECS_CLUSTER_NAME": "Deploy-Service-Cluster",
                "ECS_SERVICE_NAME": "Deploy-Service-Service",
            },
            role_policy_statements=[
                iam.PolicyStatement(
                    actions=[
                        "ecr:GetAuthorizationToken",
                    ],
                    resources=["*"],
                ),
                iam.PolicyStatement(
                    actions=[
                        "ecr:BatchCheckLayerAvailability",
                        "ecr:GetDownloadUrlForLayer",
                        "ecr:BatchGetImage",
                        "ecr:PutImage",
                        "ecr:InitiateLayerUpload",
                        "ecr:UploadLayerPart",
                        "ecr:CompleteLayerUpload",
                    ],
                    resources=[
                        f"arn:aws:ecr:{self.region}:{self.account}:repository/homeagent-backend"
                    ],
                ),
                iam.PolicyStatement(
                    actions=[
                        "ecs:UpdateService",
                        "ecs:DescribeServices",
                    ],
                    resources=["*"],
                ),
            ],
        )

        # ------------------------------------------------------------------
        # Wire up the deploy stage
        # ------------------------------------------------------------------
        deploy_stage = HomeAgentStage(
            self,
            "Deploy",
            env=cdk.Environment(
                account=self.account,
                region=self.region,
            ),
        )

        pipeline.add_stage(
            deploy_stage,
            pre=[test_step],
            post=[docker_build_step],
        )

        # ------------------------------------------------------------------
        # Outputs
        # ------------------------------------------------------------------
        cdk.CfnOutput(self, "RepoCloneUrlHttp", value=repo.repository_clone_url_http)
        cdk.CfnOutput(self, "RepoCloneUrlGrc", value=repo.repository_clone_url_grc)
