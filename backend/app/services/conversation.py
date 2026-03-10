from datetime import datetime, timezone

from ulid import ULID

from app.dal import get_dal


def create_conversation(user_id: str, title: str) -> dict:
    """Create a new conversation. Returns the conversation item."""
    dal = get_dal()
    now = datetime.now(timezone.utc).isoformat()
    conversation_id = str(ULID())

    item = {
        "conversation_id": conversation_id,
        "user_id": user_id,
        "title": title,
        "created_at": now,
        "updated_at": now,
    }
    dal.conversations.create(item)
    return item


def get_conversation(conversation_id: str) -> dict | None:
    """Get a single conversation by ID."""
    dal = get_dal()
    return dal.conversations.get_conversation(conversation_id)


def list_conversations(
    user_id: str, limit: int = 20, cursor: str | None = None
) -> dict:
    """List conversations for a user, sorted by most recent.

    Returns dict with 'conversations' and optional 'next_cursor'.

    Note: The legacy cursor format was a raw updated_at string. The DAL
    uses opaque base64 cursors. For backward compatibility during migration,
    we pass the cursor through to the DAL which handles both formats.
    """
    dal = get_dal()

    # TODO(DAL-migration): Remove legacy cursor fallback once all mobile
    # clients (iOS 2.x+, Android 2.x+) send opaque DAL cursors.  The legacy
    # format was a raw updated_at string returned directly from DynamoDB.
    # Target removal: next major mobile release after DAL migration ships.
    if cursor:
        # Try DAL cursor first; if it fails, use legacy approach
        try:
            result = dal.conversations.query_by_user(
                user_id, limit=limit, cursor=cursor, newest_first=True
            )
            response: dict = {"conversations": result.items}
            if result.next_cursor:
                response["next_cursor"] = result.next_cursor
            return response
        except ValueError:
            pass

        # Legacy cursor format: raw updated_at value.
        # ExclusiveStartKey requires all key attributes of the GSI
        # projection; conversation_id is the table PK projected into the
        # index.  We use "_" as a sentinel — DynamoDB will start scanning
        # after this key position, which may skip the very first item that
        # shares this updated_at value.  Acceptable during migration.
        kwargs: dict = {
            "IndexName": "user_conversations-index",
            "ScanIndexForward": False,
            "Limit": limit,
            "ExclusiveStartKey": {
                "user_id": user_id,
                "updated_at": cursor,
                "conversation_id": "_",
            },
        }
        from boto3.dynamodb.conditions import Key

        kwargs["KeyConditionExpression"] = Key("user_id").eq(user_id)
        result_raw = dal.conversations._table.query(**kwargs)
        conversations = result_raw.get("Items", [])
        response = {"conversations": conversations}
        if "LastEvaluatedKey" in result_raw:
            response["next_cursor"] = result_raw["LastEvaluatedKey"]["updated_at"]
        return response

    result = dal.conversations.query_by_user(user_id, limit=limit, newest_first=True)
    response = {"conversations": result.items}
    if result.next_cursor:
        response["next_cursor"] = result.next_cursor
    return response


def delete_conversation(conversation_id: str) -> None:
    """Delete a conversation and all its messages."""
    dal = get_dal()
    dal.messages.delete_by_conversation(conversation_id)
    dal.conversations.delete({"conversation_id": conversation_id})


def add_message(
    conversation_id: str,
    role: str,
    content: str,
    model: str | None = None,
    tokens_used: int | None = None,
    media: list[dict] | None = None,
) -> dict:
    """Add a message to a conversation. Returns the message item."""
    dal = get_dal()
    now = datetime.now(timezone.utc)
    message_id = str(ULID())
    sort_key = f"{now.isoformat()}#{message_id}"

    item: dict = {
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
    if media:
        item["media"] = media

    dal.messages.create(item)

    # Update conversation's updated_at
    dal.conversations.update(
        {"conversation_id": conversation_id},
        {"updated_at": now.isoformat()},
    )

    return item


def get_messages(
    conversation_id: str, limit: int = 50, cursor: str | None = None
) -> dict:
    """Get messages for a conversation in chronological order.

    Returns dict with 'messages' and optional 'next_cursor'.
    """
    dal = get_dal()

    # Legacy cursor format: raw sort_key value
    if cursor:
        try:
            result = dal.messages.query_by_conversation(
                conversation_id, limit=limit, cursor=cursor
            )
            response: dict = {"messages": result.items}
            if result.next_cursor:
                response["next_cursor"] = result.next_cursor
            return response
        except ValueError:
            pass

        # Fallback to legacy cursor
        from boto3.dynamodb.conditions import Key

        kwargs: dict = {
            "KeyConditionExpression": Key("conversation_id").eq(conversation_id),
            "ScanIndexForward": True,
            "Limit": limit,
            "ExclusiveStartKey": {
                "conversation_id": conversation_id,
                "sort_key": cursor,
            },
        }
        result_raw = dal.messages._table.query(**kwargs)
        messages = result_raw.get("Items", [])
        response = {"messages": messages}
        if "LastEvaluatedKey" in result_raw:
            response["next_cursor"] = result_raw["LastEvaluatedKey"]["sort_key"]
        return response

    result = dal.messages.query_by_conversation(conversation_id, limit=limit)
    response = {"messages": result.items}
    if result.next_cursor:
        response["next_cursor"] = result.next_cursor
    return response
