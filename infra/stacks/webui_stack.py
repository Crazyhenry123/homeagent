import aws_cdk as cdk
from aws_cdk import aws_cloudfront as cloudfront
from aws_cdk import aws_cloudfront_origins as origins
from aws_cdk import aws_elasticloadbalancingv2 as elbv2
from aws_cdk import aws_s3 as s3
from constructs import Construct


class WebUiStack(cdk.Stack):
    """S3 + CloudFront stack for the debug web UI, with API proxy to ALB."""

    def __init__(
        self,
        scope: Construct,
        id: str,
        load_balancer: elbv2.ApplicationLoadBalancer,
        **kwargs,
    ) -> None:
        super().__init__(scope, id, **kwargs)

        # S3 bucket for static web assets (private, accessed via CloudFront OAC)
        self.bucket = s3.Bucket(
            self,
            "WebUiBucket",
            removal_policy=cdk.RemovalPolicy.DESTROY,
            auto_delete_objects=True,
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            encryption=s3.BucketEncryption.S3_MANAGED,
        )

        # ALB origin for API requests (HTTP, no caching, long timeout for SSE)
        api_origin = origins.HttpOrigin(
            load_balancer.load_balancer_dns_name,
            protocol_policy=cloudfront.OriginProtocolPolicy.HTTP_ONLY,
            read_timeout=cdk.Duration.seconds(180),
        )

        # CloudFront distribution with OAC to the S3 bucket + API proxy
        self.distribution = cloudfront.Distribution(
            self,
            "WebUiDistribution",
            default_behavior=cloudfront.BehaviorOptions(
                origin=origins.S3BucketOrigin.with_origin_access_control(self.bucket),
                viewer_protocol_policy=cloudfront.ViewerProtocolPolicy.REDIRECT_TO_HTTPS,
                cache_policy=cloudfront.CachePolicy.CACHING_OPTIMIZED,
            ),
            additional_behaviors={
                "/api/*": cloudfront.BehaviorOptions(
                    origin=api_origin,
                    viewer_protocol_policy=cloudfront.ViewerProtocolPolicy.REDIRECT_TO_HTTPS,
                    allowed_methods=cloudfront.AllowedMethods.ALLOW_ALL,
                    cache_policy=cloudfront.CachePolicy.CACHING_DISABLED,
                    origin_request_policy=cloudfront.OriginRequestPolicy.ALL_VIEWER,
                ),
                "/health": cloudfront.BehaviorOptions(
                    origin=api_origin,
                    viewer_protocol_policy=cloudfront.ViewerProtocolPolicy.REDIRECT_TO_HTTPS,
                    cache_policy=cloudfront.CachePolicy.CACHING_DISABLED,
                    origin_request_policy=cloudfront.OriginRequestPolicy.ALL_VIEWER,
                ),
            },
            default_root_object="index.html",
            error_responses=[
                cloudfront.ErrorResponse(
                    http_status=403,
                    response_http_status=403,
                    response_page_path="/error.html",
                    ttl=cdk.Duration.seconds(0),
                ),
                cloudfront.ErrorResponse(
                    http_status=404,
                    response_http_status=404,
                    response_page_path="/error.html",
                    ttl=cdk.Duration.seconds(0),
                ),
            ],
        )

        # Outputs
        self.bucket_name_output = cdk.CfnOutput(
            self,
            "WebUiBucketName",
            value=self.bucket.bucket_name,
        )
        self.distribution_id_output = cdk.CfnOutput(
            self,
            "WebUiDistributionId",
            value=self.distribution.distribution_id,
        )
        cdk.CfnOutput(
            self,
            "WebUiUrl",
            value=f"https://{self.distribution.distribution_domain_name}",
        )
