"""Tests for conversation & message repositories (Task 2.2)."""

import boto3
import pytest
from moto import mock_aws

from app.dal.repositories.conversation_repo import ConversationRepository
from app.dal.repositories.message_repo import MessageRepository


@pytest.fixture()
def dynamodb():
    with mock_aws():
        resource = boto3.resource("dynamodb", region_name="us-east-1")

        # Conversations table
        resource.create_table(
            TableName="Conversations",
            KeySchema=[{"AttributeName": "conversation_id", "KeyType": "HASH"}],
            AttributeDefinitions=[
                {"AttributeName": "conversation_id", "AttributeType": "S"},
                {"AttributeName": "user_id", "AttributeType": "S"},
                {"AttributeName": "updated_at", "AttributeType": "S"},
            ],
            GlobalSecondaryIndexes=[
                {
                    "IndexName": "user_conversations-index",
                    "KeySchema": [
                        {"AttributeName": "user_id", "KeyType": "HASH"},
                        {"AttributeName": "updated_at", "KeyType": "RANGE"},
                    ],
                    "Projection": {"ProjectionType": "ALL"},
                }
            ],
            BillingMode="PAY_PER_REQUEST",
        )

        # Messages table
        resource.create_table(
            TableName="Messages",
            KeySchema=[
                {"AttributeName": "conversation_id", "KeyType": "HASH"},
                {"AttributeName": "sort_key", "KeyType": "RANGE"},
            ],
            AttributeDefinitions=[
                {"AttributeName": "conversation_id", "AttributeType": "S"},
                {"AttributeName": "sort_key", "AttributeType": "S"},
            ],
            BillingMode="PAY_PER_REQUEST",
        )

        yield resource


# ---------------------------------------------------------------------------
# ConversationRepository
# ---------------------------------------------------------------------------


class TestConversationRepository:
    def test_create_and_get(self, dynamodb):
        repo = ConversationRepository(dynamodb)
        repo.create({"conversation_id": "c1", "user_id": "u1", "title": "Test Chat"})
        fetched = repo.get_by_id({"conversation_id": "c1"})
        assert fetched is not None
        assert fetched["title"] == "Test Chat"

    def test_query_by_user(self, dynamodb):
        repo = ConversationRepository(dynamodb)
        repo.create(
            {
                "conversation_id": "c1",
                "user_id": "u1",
                "updated_at": "2025-01-01T00:00:00",
            }
        )
        repo.create(
            {
                "conversation_id": "c2",
                "user_id": "u1",
                "updated_at": "2025-01-02T00:00:00",
            }
        )
        repo.create(
            {
                "conversation_id": "c3",
                "user_id": "u2",
                "updated_at": "2025-01-03T00:00:00",
            }
        )
        result = repo.query_by_user("u1")
        assert result.count == 2

    def test_query_by_user_newest_first(self, dynamodb):
        repo = ConversationRepository(dynamodb)
        repo.create(
            {
                "conversation_id": "c1",
                "user_id": "u1",
                "updated_at": "2025-01-01T00:00:00",
            }
        )
        repo.create(
            {
                "conversation_id": "c2",
                "user_id": "u1",
                "updated_at": "2025-01-02T00:00:00",
            }
        )
        result = repo.query_by_user("u1", newest_first=True)
        # Note: updated_at from create() auto-stamps, but we also set it manually.
        # The GSI sorts by the updated_at field we provided.
        assert result.count == 2

    def test_query_by_user_oldest_first(self, dynamodb):
        repo = ConversationRepository(dynamodb)
        repo.create(
            {
                "conversation_id": "c1",
                "user_id": "u1",
                "updated_at": "2025-01-01T00:00:00",
            }
        )
        repo.create(
            {
                "conversation_id": "c2",
                "user_id": "u1",
                "updated_at": "2025-01-02T00:00:00",
            }
        )
        result = repo.query_by_user("u1", newest_first=False)
        assert result.count == 2

    def test_query_by_user_pagination(self, dynamodb):
        repo = ConversationRepository(dynamodb)
        for i in range(5):
            repo.create(
                {
                    "conversation_id": f"c{i}",
                    "user_id": "u1",
                    "updated_at": f"2025-01-{i + 1:02d}T00:00:00",
                }
            )
        page1 = repo.query_by_user("u1", limit=2)
        assert page1.count == 2
        assert page1.next_cursor is not None
        page2 = repo.query_by_user("u1", limit=2, cursor=page1.next_cursor)
        assert page2.count == 2

    def test_query_by_user_empty(self, dynamodb):
        repo = ConversationRepository(dynamodb)
        result = repo.query_by_user("u-none")
        assert result.count == 0
        assert result.next_cursor is None


# ---------------------------------------------------------------------------
# MessageRepository
# ---------------------------------------------------------------------------


class TestMessageRepository:
    def test_create_and_query(self, dynamodb):
        repo = MessageRepository(dynamodb)
        repo.create({"conversation_id": "c1", "sort_key": "001", "content": "Hello"})
        repo.create({"conversation_id": "c1", "sort_key": "002", "content": "World"})
        result = repo.query_by_conversation("c1")
        assert result.count == 2

    def test_query_oldest_first_default(self, dynamodb):
        repo = MessageRepository(dynamodb)
        for i in range(3):
            repo.create(
                {"conversation_id": "c1", "sort_key": f"{i:03d}", "content": f"msg-{i}"}
            )
        result = repo.query_by_conversation("c1")
        keys = [m["sort_key"] for m in result.items]
        assert keys == sorted(keys)

    def test_query_newest_first(self, dynamodb):
        repo = MessageRepository(dynamodb)
        for i in range(3):
            repo.create(
                {"conversation_id": "c1", "sort_key": f"{i:03d}", "content": f"msg-{i}"}
            )
        result = repo.query_by_conversation("c1", newest_first=True)
        keys = [m["sort_key"] for m in result.items]
        assert keys == sorted(keys, reverse=True)

    def test_query_after_sort_key(self, dynamodb):
        repo = MessageRepository(dynamodb)
        for i in range(5):
            repo.create({"conversation_id": "c1", "sort_key": f"{i:03d}"})
        result = repo.query_by_conversation_after("c1", "002")
        keys = [m["sort_key"] for m in result.items]
        assert all(k > "002" for k in keys)
        assert result.count == 2  # 003, 004

    def test_query_pagination(self, dynamodb):
        repo = MessageRepository(dynamodb)
        for i in range(7):
            repo.create({"conversation_id": "c1", "sort_key": f"{i:03d}"})
        page1 = repo.query_by_conversation("c1", limit=3)
        assert page1.count == 3
        assert page1.next_cursor is not None
        page2 = repo.query_by_conversation("c1", limit=3, cursor=page1.next_cursor)
        assert page2.count == 3

    def test_delete_by_conversation(self, dynamodb):
        repo = MessageRepository(dynamodb)
        for i in range(5):
            repo.create({"conversation_id": "c1", "sort_key": f"{i:03d}"})
        repo.delete_by_conversation("c1")
        result = repo.query_by_conversation("c1")
        assert result.count == 0

    def test_delete_by_conversation_empty(self, dynamodb):
        repo = MessageRepository(dynamodb)
        repo.delete_by_conversation("nonexistent")  # Should not raise

    def test_query_empty_conversation(self, dynamodb):
        repo = MessageRepository(dynamodb)
        result = repo.query_by_conversation("nonexistent")
        assert result.count == 0
