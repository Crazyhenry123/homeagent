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
        return _handle_update(event, props)
    elif request_type == "Delete":
        return _handle_delete(client, event)
    else:
        raise ValueError(f"Unknown request type: {request_type}")


def _handle_create(client: "boto3.client", props: dict) -> dict:
    agent_name = props["AgentRuntimeName"]
    role_arn = props["RoleArn"]
    s3_bucket = props["S3Bucket"]
    s3_prefix = props["S3Prefix"]
    network_mode = props.get("NetworkMode", "PUBLIC")

    # Create the agent runtime with code configuration
    resp = client.create_agent_runtime(
        agentRuntimeName=agent_name,
        agentRuntimeArtifact={
            "codeConfiguration": {
                "code": {
                    "s3": {
                        "bucket": s3_bucket,
                        "prefix": s3_prefix,
                    }
                },
                "runtime": "PYTHON_3_13",
                "entryPoint": ["main.py"],
            }
        },
        networkConfiguration={"networkMode": network_mode},
        roleArn=role_arn,
        environmentVariables={
            "AWS_REGION": props.get("Region", "us-east-1"),
        },
    )

    runtime_id = resp["agentRuntimeId"]
    runtime_arn = resp["agentRuntimeArn"]
    logger.info("Created agent runtime %s (id=%s)", agent_name, runtime_id)

    # Wait for runtime to become READY
    _wait_for_status(
        client, "get_agent_runtime", "", runtime_id, "READY", "AgentRuntime"
    )

    # Create an endpoint for the runtime
    endpoint_name = f"{agent_name}-endpoint"
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

    return {
        "PhysicalResourceId": runtime_id,
        "Data": {
            "agentRuntimeId": runtime_id,
            "agentRuntimeArn": runtime_arn,
            "endpointName": endpoint_name,
        },
    }


def _handle_update(event: dict, props: dict) -> dict:
    physical_id = event.get("PhysicalResourceId", "")
    logger.info("Update requested for runtime %s — no-op", physical_id)
    return {
        "PhysicalResourceId": physical_id,
        "Data": {
            "agentRuntimeId": physical_id,
            "agentRuntimeArn": "",
            "endpointName": "",
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
