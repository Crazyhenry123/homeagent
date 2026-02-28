import boto3
from flask import Flask, g, current_app

TABLE_DEFINITIONS = {
    "Users": {
        "KeySchema": [{"AttributeName": "user_id", "KeyType": "HASH"}],
        "AttributeDefinitions": [{"AttributeName": "user_id", "AttributeType": "S"}],
    },
    "Devices": {
        "KeySchema": [{"AttributeName": "device_id", "KeyType": "HASH"}],
        "AttributeDefinitions": [
            {"AttributeName": "device_id", "AttributeType": "S"},
            {"AttributeName": "device_token", "AttributeType": "S"},
        ],
        "GlobalSecondaryIndexes": [
            {
                "IndexName": "device_token-index",
                "KeySchema": [
                    {"AttributeName": "device_token", "KeyType": "HASH"},
                ],
                "Projection": {"ProjectionType": "ALL"},
            }
        ],
    },
    "InviteCodes": {
        "KeySchema": [{"AttributeName": "code", "KeyType": "HASH"}],
        "AttributeDefinitions": [{"AttributeName": "code", "AttributeType": "S"}],
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
        dynamodb.create_table(**params)


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
