"""CloudFormation Custom Resource handler for AgentCore Memory CRUD.

Used with CDK cr.Provider framework — returns dict, not cfnresponse.
Uses boto3 bedrock-agentcore-control service (Python SDK only, no JS SDK).
"""

import logging
import time

import boto3

logger = logging.getLogger()
logger.setLevel(logging.INFO)


def on_event(event: dict, context: object) -> dict:
    request_type = event["RequestType"]
    props = event["ResourceProperties"]
    memory_name = props["MemoryName"]
    memory_description = props.get("MemoryDescription", "")
    event_expiry_days = int(props.get("EventExpiryDuration", 365))
    region = props.get("Region", "us-east-1")

    client = boto3.client("bedrock-agentcore-control", region_name=region)

    if request_type == "Create":
        resp = client.create_memory(
            name=memory_name,
            description=memory_description,
            eventExpiryDuration=event_expiry_days,
        )
        memory = resp["memory"]
        memory_id = memory["id"]
        logger.info("Created memory %s with id %s", memory_name, memory_id)

        # Wait for memory to become ACTIVE (up to 2 minutes)
        for _ in range(24):
            status = client.get_memory(memoryId=memory_id)["memory"]["status"]
            if status == "ACTIVE":
                break
            if status in ("FAILED", "DELETING"):
                raise RuntimeError(f"Memory {memory_id} entered {status} state")
            logger.info("Memory %s status: %s, waiting...", memory_id, status)
            time.sleep(5)

        return {
            "PhysicalResourceId": memory_id,
            "Data": {"memoryId": memory_id},
        }

    elif request_type == "Update":
        physical_id = event.get("PhysicalResourceId", "")
        logger.info("Update requested for memory %s — no-op", physical_id)
        return {
            "PhysicalResourceId": physical_id,
            "Data": {"memoryId": physical_id},
        }

    elif request_type == "Delete":
        physical_id = event.get("PhysicalResourceId", "")
        if physical_id:
            try:
                client.delete_memory(memoryId=physical_id)
                logger.info("Deleted memory %s", physical_id)
            except client.exceptions.ResourceNotFoundException:
                logger.info("Memory %s already deleted", physical_id)
            except Exception as e:
                logger.warning("Failed to delete memory %s: %s", physical_id, e)
        return {"PhysicalResourceId": physical_id}

    else:
        raise ValueError(f"Unknown request type: {request_type}")
