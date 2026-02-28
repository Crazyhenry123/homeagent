from datetime import datetime, timezone

from boto3.dynamodb.conditions import Key
from ulid import ULID

from app.models.dynamo import get_table


def create_conversation(user_id: str, title: str) -> dict:
    """Create a new conversation. Returns the conversation item."""
    table = get_table("Conversations")
    now = datetime.now(timezone.utc).isoformat()
    conversation_id = str(ULID())

    item = {
        "conversation_id": conversation_id,
        "user_id": user_id,
        "title": title,
        "created_at": now,
        "updated_at": now,
    }
    table.put_item(Item=item)
    return item


def get_conversation(conversation_id: str) -> dict | None:
    """Get a single conversation by ID."""
    table = get_table("Conversations")
    result = table.get_item(Key={"conversation_id": conversation_id})
    return result.get("Item")


def list_conversations(
    user_id: str, limit: int = 20, cursor: str | None = None
) -> dict:
    """List conversations for a user, sorted by most recent.

    Returns dict with 'conversations' and optional 'next_cursor'.
    """
    table = get_table("Conversations")
    kwargs = {
        "IndexName": "user_conversations-index",
        "KeyConditionExpression": Key("user_id").eq(user_id),
        "ScanIndexForward": False,  # newest first
        "Limit": limit,
    }

    if cursor:
        kwargs["ExclusiveStartKey"] = {
            "user_id": user_id,
            "updated_at": cursor,
            "conversation_id": "_",  # placeholder, will be overridden
        }

    result = table.query(**kwargs)
    conversations = result.get("Items", [])

    response = {"conversations": conversations}
    if "LastEvaluatedKey" in result:
        response["next_cursor"] = result["LastEvaluatedKey"]["updated_at"]

    return response


def delete_conversation(conversation_id: str) -> None:
    """Delete a conversation and all its messages."""
    # Delete messages first
    messages_table = get_table("Messages")
    result = messages_table.query(
        KeyConditionExpression=Key("conversation_id").eq(conversation_id),
        ProjectionExpression="conversation_id, sort_key",
    )
    with messages_table.batch_writer() as batch:
        for item in result["Items"]:
            batch.delete_item(
                Key={
                    "conversation_id": item["conversation_id"],
                    "sort_key": item["sort_key"],
                }
            )

    # Delete conversation
    table = get_table("Conversations")
    table.delete_item(Key={"conversation_id": conversation_id})


def add_message(
    conversation_id: str,
    role: str,
    content: str,
    model: str | None = None,
    tokens_used: int | None = None,
) -> dict:
    """Add a message to a conversation. Returns the message item."""
    table = get_table("Messages")
    now = datetime.now(timezone.utc)
    message_id = str(ULID())
    sort_key = f"{now.isoformat()}#{message_id}"

    item = {
        "conversation_id": conversation_id,
        "sort_key": sort_key,
        "message_id": message_id,
        "role": role,
        "content": content,
        "created_at": now.isoformat(),
    }
    if model:
        item["model"] = model
    if tokens_used is not None:
        item["tokens_used"] = tokens_used

    table.put_item(Item=item)

    # Update conversation's updated_at
    conv_table = get_table("Conversations")
    conv_table.update_item(
        Key={"conversation_id": conversation_id},
        UpdateExpression="SET updated_at = :now",
        ExpressionAttributeValues={":now": now.isoformat()},
    )

    return item


def get_messages(
    conversation_id: str, limit: int = 50, cursor: str | None = None
) -> dict:
    """Get messages for a conversation in chronological order.

    Returns dict with 'messages' and optional 'next_cursor'.
    """
    table = get_table("Messages")
    kwargs = {
        "KeyConditionExpression": Key("conversation_id").eq(conversation_id),
        "ScanIndexForward": True,
        "Limit": limit,
    }

    if cursor:
        kwargs["ExclusiveStartKey"] = {
            "conversation_id": conversation_id,
            "sort_key": cursor,
        }

    result = table.query(**kwargs)
    messages = result.get("Items", [])

    response = {"messages": messages}
    if "LastEvaluatedKey" in result:
        response["next_cursor"] = result["LastEvaluatedKey"]["sort_key"]

    return response
