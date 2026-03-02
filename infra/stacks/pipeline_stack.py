import aws_cdk as cdk
from aws_cdk import aws_codebuild as codebuild
from aws_cdk import aws_codepipeline as codepipeline
from aws_cdk import aws_codepipeline_actions as codepipeline_actions
from aws_cdk import aws_iam as iam
from aws_cdk import pipelines
from constructs import Construct

from stacks.app_stage import HomeAgentStage


class PipelineStack(cdk.Stack):
    """Self-mutating CDK Pipeline: GitHub -> Test -> Deploy infra -> Build & push Docker -> Update ECS."""

    def __init__(self, scope: Construct, id: str, **kwargs) -> None:
        super().__init__(scope, id, **kwargs)

        # ------------------------------------------------------------------
        # Source: GitHub via CodeStar Connections
        # ------------------------------------------------------------------
        connection_arn = self.node.try_get_context("github_connection_arn")
        if not connection_arn:
            raise ValueError(
                "Missing required context: github_connection_arn. "
                "Create a CodeStar Connection in the AWS Console and pass it via "
                "-c github_connection_arn=arn:aws:codeconnections:REGION:ACCOUNT:connection/ID"
            )

        source = pipelines.CodePipelineSource.connection(
            "Crazyhenry123/homeagent",
            "master",
            connection_arn=connection_arn,
        )

        # ------------------------------------------------------------------
        # Synth: install CDK deps and synthesize CloudFormation
        # ------------------------------------------------------------------
        build_env = codebuild.BuildEnvironment(
            build_image=codebuild.LinuxBuildImage.STANDARD_7_0,
            privileged=True,
            compute_type=codebuild.ComputeType.MEDIUM,
        )

        synth = pipelines.CodeBuildStep(
            "Synth",
            input=source,
            install_commands=[
                "pip install -r infra/requirements.txt",
            ],
            commands=[
                "cd infra",
                "npx cdk synth",
            ],
            primary_output_directory="infra/cdk.out",
            build_environment=build_env,
            role_policy_statements=[
                iam.PolicyStatement(
                    actions=["ec2:DescribeAvailabilityZones"],
                    resources=["*"],
                ),
            ],
        )

        pipeline = pipelines.CodePipeline(
            self,
            "Pipeline",
            pipeline_name="homeagent-pipeline",
            synth=synth,
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
                "pip install -r backend/requirements.txt pytest",
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
            },
            env_from_cfn_outputs={
                "ECS_CLUSTER_NAME": deploy_stage.service_stack.cluster_name_output,
                "ECS_SERVICE_NAME": deploy_stage.service_stack.service_name_output,
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
        # Post-deploy: sync web UI static files to S3 + invalidate CloudFront
        # ------------------------------------------------------------------
        webui_deploy_step = pipelines.CodeBuildStep(
            "WebUiDeploy",
            input=source,
            commands=[
                "aws s3 sync webui/ s3://$WEBUI_BUCKET_NAME --delete",
                'aws cloudfront create-invalidation --distribution-id $WEBUI_DISTRIBUTION_ID --paths "/*"',
            ],
            build_environment=build_env,
            env_from_cfn_outputs={
                "WEBUI_BUCKET_NAME": deploy_stage.webui_stack.bucket_name_output,
                "WEBUI_DISTRIBUTION_ID": deploy_stage.webui_stack.distribution_id_output,
            },
            role_policy_statements=[
                iam.PolicyStatement(
                    actions=[
                        "s3:PutObject",
                        "s3:DeleteObject",
                        "s3:ListBucket",
                        "s3:GetBucketLocation",
                    ],
                    resources=[
                        "arn:aws:s3:::deploy-webui*",
                        "arn:aws:s3:::deploy-webui*/*",
                    ],
                ),
                iam.PolicyStatement(
                    actions=["cloudfront:CreateInvalidation"],
                    resources=[
                        f"arn:aws:cloudfront::{self.account}:distribution/*",
                    ],
                ),
            ],
        )

        pipeline.add_stage(
            deploy_stage,
            pre=[test_step],
            post=[docker_build_step, webui_deploy_step],
        )

        # ==================================================================
        # Fast WebUI Pipeline: S3 sync + CloudFront invalidation (~1 min)
        # Triggered only when webui/ files change on master.
        # ==================================================================
        source_output = codepipeline.Artifact("WebUiFastSource")

        fast_source_action = codepipeline_actions.CodeStarConnectionsSourceAction(
            action_name="GitHub",
            owner="Crazyhenry123",
            repo="homeagent",
            branch="master",
            connection_arn=connection_arn,
            output=source_output,
            trigger_on_push=False,  # V2 trigger handles push filtering
        )

        fast_deploy_project = codebuild.PipelineProject(
            self,
            "WebUiFastDeploy",
            project_name="homeagent-webui-fast-deploy",
            environment=codebuild.BuildEnvironment(
                build_image=codebuild.LinuxBuildImage.STANDARD_7_0,
                compute_type=codebuild.ComputeType.SMALL,
            ),
            build_spec=codebuild.BuildSpec.from_object({
                "version": "0.2",
                "phases": {
                    "build": {
                        "commands": [
                            "aws s3 sync webui/ s3://$WEBUI_BUCKET_NAME --delete",
                            'aws cloudfront create-invalidation --distribution-id $WEBUI_DISTRIBUTION_ID --paths "/*"',
                        ],
                    },
                },
            }),
            environment_variables={
                "WEBUI_BUCKET_NAME": codebuild.BuildEnvironmentVariable(
                    value="/homeagent/webui/bucket-name",
                    type=codebuild.BuildEnvironmentVariableType.PARAMETER_STORE,
                ),
                "WEBUI_DISTRIBUTION_ID": codebuild.BuildEnvironmentVariable(
                    value="/homeagent/webui/distribution-id",
                    type=codebuild.BuildEnvironmentVariableType.PARAMETER_STORE,
                ),
            },
        )

        fast_deploy_project.add_to_role_policy(
            iam.PolicyStatement(
                actions=[
                    "s3:PutObject",
                    "s3:DeleteObject",
                    "s3:ListBucket",
                    "s3:GetBucketLocation",
                ],
                resources=[
                    "arn:aws:s3:::deploy-webui*",
                    "arn:aws:s3:::deploy-webui*/*",
                ],
            )
        )
        fast_deploy_project.add_to_role_policy(
            iam.PolicyStatement(
                actions=["cloudfront:CreateInvalidation"],
                resources=[
                    f"arn:aws:cloudfront::{self.account}:distribution/*",
                ],
            )
        )

        fast_build_action = codepipeline_actions.CodeBuildAction(
            action_name="DeployWebUI",
            project=fast_deploy_project,
            input=source_output,
        )

        codepipeline.Pipeline(
            self,
            "WebUiFastPipeline",
            pipeline_name="homeagent-webui-fast",
            pipeline_type=codepipeline.PipelineType.V2,
            stages=[
                codepipeline.StageProps(
                    stage_name="Source",
                    actions=[fast_source_action],
                ),
                codepipeline.StageProps(
                    stage_name="Deploy",
                    actions=[fast_build_action],
                ),
            ],
            triggers=[
                codepipeline.TriggerProps(
                    provider_type=codepipeline.ProviderType.CODE_STAR_SOURCE_CONNECTION,
                    git_configuration=codepipeline.GitConfiguration(
                        source_action=fast_source_action,
                        push_filter=[
                            codepipeline.GitPushFilter(
                                branches_includes=["master"],
                                file_paths_includes=["webui/**"],
                            ),
                        ],
                    ),
                ),
            ],
        )

        # ==================================================================
        # Fast Backend Pipeline: Test -> Docker build + ECS deploy (~5-6 min)
        # Triggered only when backend/ files change on master.
        # ==================================================================
        backend_source_output = codepipeline.Artifact("BackendFastSource")

        backend_fast_source_action = codepipeline_actions.CodeStarConnectionsSourceAction(
            action_name="GitHub",
            owner="Crazyhenry123",
            repo="homeagent",
            branch="master",
            connection_arn=connection_arn,
            output=backend_source_output,
            trigger_on_push=False,  # V2 trigger handles push filtering
        )

        # -- Test stage: run pytest with DynamoDB Local --
        backend_fast_test_project = codebuild.PipelineProject(
            self,
            "BackendFastTest",
            project_name="homeagent-backend-fast-test",
            environment=codebuild.BuildEnvironment(
                build_image=codebuild.LinuxBuildImage.STANDARD_7_0,
                compute_type=codebuild.ComputeType.MEDIUM,
                privileged=True,
            ),
            build_spec=codebuild.BuildSpec.from_object({
                "version": "0.2",
                "phases": {
                    "install": {
                        "commands": [
                            "pip install -r backend/requirements.txt pytest",
                        ],
                    },
                    "pre_build": {
                        "commands": [
                            "docker run -d --name dynamodb-test -p 8000:8000 "
                            "amazon/dynamodb-local -jar DynamoDBLocal.jar -sharedDb -inMemory",
                            "sleep 3",
                        ],
                    },
                    "build": {
                        "commands": [
                            "cd backend",
                            "python -m pytest tests/ -v",
                        ],
                    },
                },
            }),
            environment_variables={
                "AWS_REGION": codebuild.BuildEnvironmentVariable(
                    value="us-east-1",
                ),
                "AWS_ACCESS_KEY_ID": codebuild.BuildEnvironmentVariable(
                    value="testing",
                ),
                "AWS_SECRET_ACCESS_KEY": codebuild.BuildEnvironmentVariable(
                    value="testing",
                ),
                "DYNAMODB_ENDPOINT": codebuild.BuildEnvironmentVariable(
                    value="http://localhost:8000",
                ),
                "ADMIN_INVITE_CODE": codebuild.BuildEnvironmentVariable(
                    value="TESTCODE",
                ),
            },
        )

        backend_fast_test_action = codepipeline_actions.CodeBuildAction(
            action_name="Test",
            project=backend_fast_test_project,
            input=backend_source_output,
        )

        # -- Deploy stage: Docker build + push to ECR + ECS update --
        backend_fast_deploy_project = codebuild.PipelineProject(
            self,
            "BackendFastDeploy",
            project_name="homeagent-backend-fast-deploy",
            environment=codebuild.BuildEnvironment(
                build_image=codebuild.LinuxBuildImage.STANDARD_7_0,
                compute_type=codebuild.ComputeType.MEDIUM,
                privileged=True,
            ),
            build_spec=codebuild.BuildSpec.from_object({
                "version": "0.2",
                "phases": {
                    "pre_build": {
                        "commands": [
                            "aws ecr get-login-password --region $AWS_DEFAULT_REGION "
                            "| docker login --username AWS --password-stdin $ECR_REPO_URI",
                            "export GIT_SHA=$(echo $CODEBUILD_RESOLVED_SOURCE_VERSION)",
                        ],
                    },
                    "build": {
                        "commands": [
                            "cd backend",
                            "docker build -t $ECR_REPO_URI:$GIT_SHA .",
                            "docker tag $ECR_REPO_URI:$GIT_SHA $ECR_REPO_URI:latest",
                        ],
                    },
                    "post_build": {
                        "commands": [
                            "docker push $ECR_REPO_URI:$GIT_SHA",
                            "docker push $ECR_REPO_URI:latest",
                            "aws ecs update-service "
                            "--cluster $ECS_CLUSTER_NAME "
                            "--service $ECS_SERVICE_NAME "
                            "--force-new-deployment",
                        ],
                    },
                },
            }),
            environment_variables={
                "ECR_REPO_URI": codebuild.BuildEnvironmentVariable(
                    value=f"{self.account}.dkr.ecr.{self.region}.amazonaws.com/homeagent-backend",
                ),
                "ECS_CLUSTER_NAME": codebuild.BuildEnvironmentVariable(
                    value="/homeagent/backend/cluster-name",
                    type=codebuild.BuildEnvironmentVariableType.PARAMETER_STORE,
                ),
                "ECS_SERVICE_NAME": codebuild.BuildEnvironmentVariable(
                    value="/homeagent/backend/service-name",
                    type=codebuild.BuildEnvironmentVariableType.PARAMETER_STORE,
                ),
            },
        )

        backend_fast_deploy_project.add_to_role_policy(
            iam.PolicyStatement(
                actions=["ecr:GetAuthorizationToken"],
                resources=["*"],
            )
        )
        backend_fast_deploy_project.add_to_role_policy(
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
            )
        )
        backend_fast_deploy_project.add_to_role_policy(
            iam.PolicyStatement(
                actions=[
                    "ecs:UpdateService",
                    "ecs:DescribeServices",
                ],
                resources=["*"],
            )
        )

        backend_fast_deploy_action = codepipeline_actions.CodeBuildAction(
            action_name="Deploy",
            project=backend_fast_deploy_project,
            input=backend_source_output,
        )

        codepipeline.Pipeline(
            self,
            "BackendFastPipeline",
            pipeline_name="homeagent-backend-fast",
            pipeline_type=codepipeline.PipelineType.V2,
            stages=[
                codepipeline.StageProps(
                    stage_name="Source",
                    actions=[backend_fast_source_action],
                ),
                codepipeline.StageProps(
                    stage_name="Test",
                    actions=[backend_fast_test_action],
                ),
                codepipeline.StageProps(
                    stage_name="Deploy",
                    actions=[backend_fast_deploy_action],
                ),
            ],
            triggers=[
                codepipeline.TriggerProps(
                    provider_type=codepipeline.ProviderType.CODE_STAR_SOURCE_CONNECTION,
                    git_configuration=codepipeline.GitConfiguration(
                        source_action=backend_fast_source_action,
                        push_filter=[
                            codepipeline.GitPushFilter(
                                branches_includes=["master"],
                                file_paths_includes=["backend/**"],
                            ),
                        ],
                    ),
                ),
            ],
        )
