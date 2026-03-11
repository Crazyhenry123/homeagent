"""CloudFormation Custom Resource handler for AgentCore Runtime + Endpoint.

Creates an AgentCore Runtime (code-based deployment from S3) and an endpoint
for it.  Used with CDK cr.Provider framework.
"""

import logging
import time

import boto3

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Status polling: 5s interval, up to 5 minutes
POLL_INTERVAL = 5
MAX_POLLS = 60


def _wait_for_status(
    client: "boto3.client",
    get_fn: str,
    id_param: str,
    resource_id: str,
    target_status: str,
    resource_name: str,
) -> str:
    """Poll until the resource reaches target_status or fails."""
    for _ in range(MAX_POLLS):
        if get_fn == "get_agent_runtime":
            resp = client.get_agent_runtime(agentRuntimeId=resource_id)
            status = resp.get("status", "")
            failure = resp.get("failureReason", "")
        else:
            resp = client.get_agent_runtime_endpoint(
                agentRuntimeId=id_param,
                endpointName=resource_id,
            )
            status = resp.get("status", "")
            failure = resp.get("failureReason", "")

        if status == target_status:
            logger.info("%s %s reached %s", resource_name, resource_id, status)
            return status
        if status in ("FAILED", "DELETE_FAILED"):
            raise RuntimeError(
                f"{resource_name} {resource_id} entered {status}: {failure}"
            )
        logger.info(
            "%s %s status: %s, waiting...", resource_name, resource_id, status
        )
        time.sleep(POLL_INTERVAL)

    raise TimeoutError(
        f"{resource_name} {resource_id} did not reach {target_status} "
        f"within {MAX_POLLS * POLL_INTERVAL}s"
    )


def on_event(event: dict, context: object) -> dict:
    request_type = event["RequestType"]
    props = event["ResourceProperties"]
    region = props.get("Region", "us-east-1")

    client = boto3.client("bedrock-agentcore-control", region_name=region)

    if request_type == "Create":
        return _handle_create(client, props)
    elif request_type == "Update":
        return _handle_update(event, client, props)
    elif request_type == "Delete":
        return _handle_delete(client, event)
    else:
        raise ValueError(f"Unknown request type: {request_type}")


def _copy_to_agentcore_bucket(
    source_bucket: str, source_key: str, agent_name: str, region: str
) -> tuple[str, str]:
    """Copy the code zip to the AgentCore-managed S3 bucket.

    AgentCore can only read from its own managed bucket
    (bedrock-agentcore-codebuild-sources-<account>-<region>), not from
    arbitrary S3 buckets. We copy the CDK asset zip there.
    """
    s3 = boto3.client("s3", region_name=region)
    sts = boto3.client("sts", region_name=region)
    account_id = sts.get_caller_identity()["Account"]

    dest_bucket = f"bedrock-agentcore-codebuild-sources-{account_id}-{region}"
    dest_key = f"{agent_name}/deployment.zip"

    logger.info(
        "Copying s3://%s/%s -> s3://%s/%s",
        source_bucket, source_key, dest_bucket, dest_key,
    )
    s3.copy_object(
        Bucket=dest_bucket,
        Key=dest_key,
        CopySource={"Bucket": source_bucket, "Key": source_key},
    )
    return dest_bucket, dest_key


def _handle_create(client: "boto3.client", props: dict) -> dict:
    agent_name = props["AgentRuntimeName"]
    role_arn = props["RoleArn"]
    source_bucket = props["S3Bucket"]
    source_key = props["S3Prefix"]
    network_mode = props.get("NetworkMode", "PUBLIC")
    region = props.get("Region", "us-east-1")

    # Copy zip to the AgentCore-managed bucket where the service can read it
    dest_bucket, dest_key = _copy_to_agentcore_bucket(
        source_bucket, source_key, agent_name, region
    )

    # Wait for IAM role propagation — CloudFormation may have just created the
    # role in the same stack update.  AgentCore validates role permissions at
    # creation time, so a freshly-created role may not be visible yet.
    logger.info("Waiting 15s for IAM role propagation before creating runtime")
    time.sleep(15)

    # Create the agent runtime with code configuration.
    # If a previous CloudFormation rollback left an orphaned runtime with the
    # same name, adopt it instead of failing.
    try:
        resp = client.create_agent_runtime(
            agentRuntimeName=agent_name,
            agentRuntimeArtifact={
                "codeConfiguration": {
                    "code": {
                        "s3": {
                            "bucket": dest_bucket,
                            "prefix": dest_key,
                        }
                    },
                    "runtime": "PYTHON_3_13",
                    "entryPoint": ["main.py"],
                }
            },
            networkConfiguration={"networkMode": network_mode},
            roleArn=role_arn,
            environmentVariables={
                "AWS_REGION": region,
            },
        )
        runtime_id = resp["agentRuntimeId"]
        runtime_arn = resp["agentRuntimeArn"]
        logger.info("Created agent runtime %s (id=%s)", agent_name, runtime_id)

        # Wait for runtime to become READY
        _wait_for_status(
            client, "get_agent_runtime", "", runtime_id, "READY", "AgentRuntime"
        )
    except client.exceptions.ConflictException:
        logger.info("Runtime %s already exists, adopting existing runtime", agent_name)
        runtimes = client.list_agent_runtimes()
        runtime_id = ""
        runtime_arn = ""
        for rt in runtimes.get("agentRuntimes", []):
            rt_id = rt.get("agentRuntimeId", "")
            if rt_id.startswith(f"{agent_name}-"):
                runtime_id = rt_id
                resp = client.get_agent_runtime(agentRuntimeId=runtime_id)
                runtime_arn = resp.get("agentRuntimeArn", "")
                logger.info("Adopted existing runtime %s (id=%s)", agent_name, runtime_id)
                break
        if not runtime_id:
            raise RuntimeError(
                f"Runtime {agent_name} reported as existing but not found in list"
            )

    # Create an endpoint for the runtime (skip if one already exists)
    endpoint_name = f"{agent_name}_endpoint"
    try:
        client.create_agent_runtime_endpoint(
            agentRuntimeId=runtime_id,
            name=endpoint_name,
        )
        logger.info("Created endpoint %s for runtime %s", endpoint_name, runtime_id)

        # Wait for endpoint to become READY
        _wait_for_status(
            client,
            "get_agent_runtime_endpoint",
            runtime_id,
            endpoint_name,
            "READY",
            "Endpoint",
        )
    except client.exceptions.ConflictException:
        logger.info("Endpoint %s already exists, skipping creation", endpoint_name)

    return {
        "PhysicalResourceId": runtime_id,
        "Data": {
            "agentRuntimeId": runtime_id,
            "agentRuntimeArn": runtime_arn,
            "endpointName": endpoint_name,
        },
    }


def _handle_update(event: dict, client: "boto3.client", props: dict) -> dict:
    physical_id = event.get("PhysicalResourceId", "")
    logger.info("Update requested for runtime %s — fetching current state", physical_id)

    # Retrieve existing runtime ARN and endpoint name
    runtime_arn = ""
    endpoint_name = ""
    try:
        resp = client.get_agent_runtime(agentRuntimeId=physical_id)
        runtime_arn = resp.get("agentRuntimeArn", "")
    except Exception as e:
        logger.warning("Failed to get runtime %s during update: %s", physical_id, e)

    try:
        endpoints = client.list_agent_runtime_endpoints(agentRuntimeId=physical_id)
        eps = endpoints.get("agentRuntimeEndpoints", [])
        if eps:
            endpoint_name = eps[0].get("name", "")
    except Exception as e:
        logger.warning("Failed to list endpoints for %s during update: %s", physical_id, e)

    return {
        "PhysicalResourceId": physical_id,
        "Data": {
            "agentRuntimeId": physical_id,
            "agentRuntimeArn": runtime_arn,
            "endpointName": endpoint_name,
        },
    }


def _handle_delete(client: "boto3.client", event: dict) -> dict:
    physical_id = event.get("PhysicalResourceId", "")
    if not physical_id:
        return {"PhysicalResourceId": physical_id}

    # Delete endpoints first, then the runtime
    try:
        endpoints = client.list_agent_runtime_endpoints(
            agentRuntimeId=physical_id
        )
        for ep in endpoints.get("agentRuntimeEndpoints", []):
            try:
                client.delete_agent_runtime_endpoint(
                    agentRuntimeId=physical_id,
                    endpointName=ep["name"],
                )
                logger.info("Deleted endpoint %s", ep["name"])
            except Exception as e:
                logger.warning("Failed to delete endpoint %s: %s", ep["name"], e)
    except Exception as e:
        logger.warning("Failed to list endpoints for %s: %s", physical_id, e)

    try:
        client.delete_agent_runtime(agentRuntimeId=physical_id)
        logger.info("Deleted agent runtime %s", physical_id)
    except client.exceptions.ResourceNotFoundException:
        logger.info("Runtime %s already deleted", physical_id)
    except Exception as e:
        logger.warning("Failed to delete runtime %s: %s", physical_id, e)

    return {"PhysicalResourceId": physical_id}
