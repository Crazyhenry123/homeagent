import boto3
from flask import Flask, g, current_app

TABLE_DEFINITIONS = {
    "Users": {
        "KeySchema": [{"AttributeName": "user_id", "KeyType": "HASH"}],
        "AttributeDefinitions": [
            {"AttributeName": "user_id", "AttributeType": "S"},
            {"AttributeName": "email", "AttributeType": "S"},
            {"AttributeName": "cognito_sub", "AttributeType": "S"},
        ],
        "GlobalSecondaryIndexes": [
            {
                "IndexName": "email-index",
                "KeySchema": [
                    {"AttributeName": "email", "KeyType": "HASH"},
                ],
                "Projection": {"ProjectionType": "ALL"},
            },
            {
                "IndexName": "cognito_sub-index",
                "KeySchema": [
                    {"AttributeName": "cognito_sub", "KeyType": "HASH"},
                ],
                "Projection": {"ProjectionType": "ALL"},
            },
        ],
    },
    "Devices": {
        "KeySchema": [{"AttributeName": "device_id", "KeyType": "HASH"}],
        "AttributeDefinitions": [
            {"AttributeName": "device_id", "AttributeType": "S"},
            {"AttributeName": "device_token", "AttributeType": "S"},
            {"AttributeName": "user_id", "AttributeType": "S"},
        ],
        "GlobalSecondaryIndexes": [
            {
                "IndexName": "device_token-index",
                "KeySchema": [
                    {"AttributeName": "device_token", "KeyType": "HASH"},
                ],
                "Projection": {"ProjectionType": "ALL"},
            },
            {
                "IndexName": "user_id-index",
                "KeySchema": [
                    {"AttributeName": "user_id", "KeyType": "HASH"},
                ],
                "Projection": {"ProjectionType": "ALL"},
            },
        ],
    },
    "InviteCodes": {
        "KeySchema": [{"AttributeName": "code", "KeyType": "HASH"}],
        "AttributeDefinitions": [
            {"AttributeName": "code", "AttributeType": "S"},
            {"AttributeName": "invited_email", "AttributeType": "S"},
        ],
        "GlobalSecondaryIndexes": [
            {
                "IndexName": "invited_email-index",
                "KeySchema": [
                    {"AttributeName": "invited_email", "KeyType": "HASH"},
                ],
                "Projection": {"ProjectionType": "ALL"},
            },
        ],
    },
    "Families": {
        "KeySchema": [{"AttributeName": "family_id", "KeyType": "HASH"}],
        "AttributeDefinitions": [
            {"AttributeName": "family_id", "AttributeType": "S"},
            {"AttributeName": "owner_user_id", "AttributeType": "S"},
        ],
        "GlobalSecondaryIndexes": [
            {
                "IndexName": "owner-index",
                "KeySchema": [
                    {"AttributeName": "owner_user_id", "KeyType": "HASH"},
                ],
                "Projection": {"ProjectionType": "ALL"},
            },
        ],
    },
    "FamilyMembers": {
        "KeySchema": [
            {"AttributeName": "family_id", "KeyType": "HASH"},
            {"AttributeName": "user_id", "KeyType": "RANGE"},
        ],
        "AttributeDefinitions": [
            {"AttributeName": "family_id", "AttributeType": "S"},
            {"AttributeName": "user_id", "AttributeType": "S"},
        ],
    },
    "Conversations": {
        "KeySchema": [{"AttributeName": "conversation_id", "KeyType": "HASH"}],
        "AttributeDefinitions": [
            {"AttributeName": "conversation_id", "AttributeType": "S"},
            {"AttributeName": "user_id", "AttributeType": "S"},
            {"AttributeName": "updated_at", "AttributeType": "S"},
        ],
        "GlobalSecondaryIndexes": [
            {
                "IndexName": "user_conversations-index",
                "KeySchema": [
                    {"AttributeName": "user_id", "KeyType": "HASH"},
                    {"AttributeName": "updated_at", "KeyType": "RANGE"},
                ],
                "Projection": {"ProjectionType": "ALL"},
            }
        ],
    },
    "Messages": {
        "KeySchema": [
            {"AttributeName": "conversation_id", "KeyType": "HASH"},
            {"AttributeName": "sort_key", "KeyType": "RANGE"},
        ],
        "AttributeDefinitions": [
            {"AttributeName": "conversation_id", "AttributeType": "S"},
            {"AttributeName": "sort_key", "AttributeType": "S"},
        ],
    },
    "MemberProfiles": {
        "KeySchema": [{"AttributeName": "user_id", "KeyType": "HASH"}],
        "AttributeDefinitions": [{"AttributeName": "user_id", "AttributeType": "S"}],
    },
    "AgentConfigs": {
        "KeySchema": [
            {"AttributeName": "user_id", "KeyType": "HASH"},
            {"AttributeName": "agent_type", "KeyType": "RANGE"},
        ],
        "AttributeDefinitions": [
            {"AttributeName": "user_id", "AttributeType": "S"},
            {"AttributeName": "agent_type", "AttributeType": "S"},
        ],
    },
    "FamilyRelationships": {
        "KeySchema": [
            {"AttributeName": "user_id", "KeyType": "HASH"},
            {"AttributeName": "related_user_id", "KeyType": "RANGE"},
        ],
        "AttributeDefinitions": [
            {"AttributeName": "user_id", "AttributeType": "S"},
            {"AttributeName": "related_user_id", "AttributeType": "S"},
        ],
    },
    "HealthRecords": {
        "KeySchema": [
            {"AttributeName": "user_id", "KeyType": "HASH"},
            {"AttributeName": "record_id", "KeyType": "RANGE"},
        ],
        "AttributeDefinitions": [
            {"AttributeName": "user_id", "AttributeType": "S"},
            {"AttributeName": "record_id", "AttributeType": "S"},
            {"AttributeName": "record_type", "AttributeType": "S"},
        ],
        "GlobalSecondaryIndexes": [
            {
                "IndexName": "record_type-index",
                "KeySchema": [
                    {"AttributeName": "user_id", "KeyType": "HASH"},
                    {"AttributeName": "record_type", "KeyType": "RANGE"},
                ],
                "Projection": {"ProjectionType": "ALL"},
            },
        ],
    },
    "HealthAuditLog": {
        "KeySchema": [
            {"AttributeName": "record_id", "KeyType": "HASH"},
            {"AttributeName": "audit_sk", "KeyType": "RANGE"},
        ],
        "AttributeDefinitions": [
            {"AttributeName": "record_id", "AttributeType": "S"},
            {"AttributeName": "audit_sk", "AttributeType": "S"},
            {"AttributeName": "user_id", "AttributeType": "S"},
            {"AttributeName": "created_at", "AttributeType": "S"},
        ],
        "GlobalSecondaryIndexes": [
            {
                "IndexName": "user-audit-index",
                "KeySchema": [
                    {"AttributeName": "user_id", "KeyType": "HASH"},
                    {"AttributeName": "created_at", "KeyType": "RANGE"},
                ],
                "Projection": {"ProjectionType": "ALL"},
            },
        ],
    },
    "HealthObservations": {
        "KeySchema": [
            {"AttributeName": "user_id", "KeyType": "HASH"},
            {"AttributeName": "observation_id", "KeyType": "RANGE"},
        ],
        "AttributeDefinitions": [
            {"AttributeName": "user_id", "AttributeType": "S"},
            {"AttributeName": "observation_id", "AttributeType": "S"},
            {"AttributeName": "category", "AttributeType": "S"},
        ],
        "GlobalSecondaryIndexes": [
            {
                "IndexName": "category-index",
                "KeySchema": [
                    {"AttributeName": "user_id", "KeyType": "HASH"},
                    {"AttributeName": "category", "KeyType": "RANGE"},
                ],
                "Projection": {"ProjectionType": "ALL"},
            },
        ],
    },
    "AgentTemplates": {
        "KeySchema": [{"AttributeName": "template_id", "KeyType": "HASH"}],
        "AttributeDefinitions": [
            {"AttributeName": "template_id", "AttributeType": "S"},
            {"AttributeName": "agent_type", "AttributeType": "S"},
        ],
        "GlobalSecondaryIndexes": [
            {
                "IndexName": "agent_type-index",
                "KeySchema": [
                    {"AttributeName": "agent_type", "KeyType": "HASH"},
                ],
                "Projection": {"ProjectionType": "ALL"},
            },
        ],
    },
    "FamilyGroups": {
        "KeySchema": [
            {"AttributeName": "family_id", "KeyType": "HASH"},
            {"AttributeName": "member_id", "KeyType": "RANGE"},
        ],
        "AttributeDefinitions": [
            {"AttributeName": "family_id", "AttributeType": "S"},
            {"AttributeName": "member_id", "AttributeType": "S"},
        ],
        "GlobalSecondaryIndexes": [
            {
                "IndexName": "member-family-index",
                "KeySchema": [
                    {"AttributeName": "member_id", "KeyType": "HASH"},
                ],
                "Projection": {"ProjectionType": "ALL"},
            },
        ],
    },
    "HealthDocuments": {
        "KeySchema": [
            {"AttributeName": "user_id", "KeyType": "HASH"},
            {"AttributeName": "document_id", "KeyType": "RANGE"},
        ],
        "AttributeDefinitions": [
            {"AttributeName": "user_id", "AttributeType": "S"},
            {"AttributeName": "document_id", "AttributeType": "S"},
        ],
    },
    "MemberPermissions": {
        "KeySchema": [
            {"AttributeName": "user_id", "KeyType": "HASH"},
            {"AttributeName": "permission_type", "KeyType": "RANGE"},
        ],
        "AttributeDefinitions": [
            {"AttributeName": "user_id", "AttributeType": "S"},
            {"AttributeName": "permission_type", "AttributeType": "S"},
        ],
    },
    "ChatMedia": {
        "KeySchema": [{"AttributeName": "media_id", "KeyType": "HASH"}],
        "AttributeDefinitions": [{"AttributeName": "media_id", "AttributeType": "S"}],
        "TimeToLiveSpecification": {
            "AttributeName": "expires_at",
            "Enabled": True,
        },
    },
    "MemorySharingConfig": {
        "KeySchema": [{"AttributeName": "user_id", "KeyType": "HASH"}],
        "AttributeDefinitions": [
            {"AttributeName": "user_id", "AttributeType": "S"},
        ],
    },
    "StorageConfig": {
        "KeySchema": [{"AttributeName": "user_id", "KeyType": "HASH"}],
        "AttributeDefinitions": [
            {"AttributeName": "user_id", "AttributeType": "S"},
        ],
    },
    "OAuthTokens": {
        "KeySchema": [
            {"AttributeName": "user_id", "KeyType": "HASH"},
            {"AttributeName": "provider", "KeyType": "RANGE"},
        ],
        "AttributeDefinitions": [
            {"AttributeName": "user_id", "AttributeType": "S"},
            {"AttributeName": "provider", "AttributeType": "S"},
        ],
    },
    "OAuthState": {
        "KeySchema": [{"AttributeName": "state", "KeyType": "HASH"}],
        "AttributeDefinitions": [
            {"AttributeName": "state", "AttributeType": "S"},
        ],
        "TimeToLiveSpecification": {
            "AttributeName": "expires_at",
            "Enabled": True,
        },
    },
    "FamilyMemoryStores": {
        "KeySchema": [{"AttributeName": "family_id", "KeyType": "HASH"}],
        "AttributeDefinitions": [
            {"AttributeName": "family_id", "AttributeType": "S"},
        ],
    },
}


def get_dynamodb():
    """Get DynamoDB resource, cached per-request on Flask g."""
    if "dynamodb" not in g:
        endpoint_url = current_app.config.get("DYNAMODB_ENDPOINT")
        kwargs = {"region_name": current_app.config["AWS_REGION"]}
        if endpoint_url:
            kwargs["endpoint_url"] = endpoint_url
        g.dynamodb = boto3.resource("dynamodb", **kwargs)
    return g.dynamodb


def get_table(table_name: str):
    """Get a DynamoDB Table resource."""
    return get_dynamodb().Table(table_name)


def _get_dynamo_resources(app: Flask):
    """Build boto3 DynamoDB resource + client from app config."""
    region = app.config["AWS_REGION"]
    endpoint_url = app.config.get("DYNAMODB_ENDPOINT")
    kwargs = {"region_name": region}
    if endpoint_url:
        kwargs["endpoint_url"] = endpoint_url
    return (
        boto3.resource("dynamodb", **kwargs),
        boto3.client("dynamodb", **kwargs),
    )


def _create_local_tables(app: Flask) -> None:
    """Create tables when using DynamoDB Local (development only)."""
    if not app.config.get("DYNAMODB_ENDPOINT"):
        return

    dynamodb, client = _get_dynamo_resources(app)
    existing = client.list_tables()["TableNames"]

    for table_name, schema in TABLE_DEFINITIONS.items():
        if table_name in existing:
            continue
        params = {
            "TableName": table_name,
            "KeySchema": schema["KeySchema"],
            "AttributeDefinitions": schema["AttributeDefinitions"],
            "BillingMode": "PAY_PER_REQUEST",
        }
        if "GlobalSecondaryIndexes" in schema:
            params["GlobalSecondaryIndexes"] = schema["GlobalSecondaryIndexes"]
        try:
            dynamodb.create_table(**params)
            # Enable TTL if specified
            ttl_spec = schema.get("TimeToLiveSpecification")
            if ttl_spec and ttl_spec.get("Enabled"):
                try:
                    client.update_time_to_live(
                        TableName=table_name,
                        TimeToLiveSpecification={
                            "Enabled": True,
                            "AttributeName": ttl_spec["AttributeName"],
                        },
                    )
                except Exception:
                    pass  # TTL may not be supported in DynamoDB Local
        except client.exceptions.ResourceInUseException:
            pass  # Another worker already created it


def _seed_admin_invite_code(app: Flask) -> None:
    """Seed the admin invite code into InviteCodes table (idempotent)."""
    admin_code = app.config.get("ADMIN_INVITE_CODE")
    if not admin_code:
        return

    dynamodb, client = _get_dynamo_resources(app)
    table = dynamodb.Table("InviteCodes")
    try:
        table.put_item(
            Item={
                "code": admin_code,
                "created_by": "system",
                "status": "active",
                "is_admin": True,
            },
            ConditionExpression="attribute_not_exists(code)",
        )
    except client.exceptions.ConditionalCheckFailedException:
        pass


def init_tables(app: Flask) -> None:
    """Initialize database: create local tables if needed, seed admin code."""
    _create_local_tables(app)
    _seed_admin_invite_code(app)
