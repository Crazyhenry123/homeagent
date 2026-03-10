"""Tests for profile, config & template repositories (Task 2.3)."""

import boto3
import pytest
from moto import mock_aws

from app.dal.repositories.profile_repo import ProfileRepository
from app.dal.repositories.agent_config_repo import AgentConfigRepository
from app.dal.repositories.agent_template_repo import AgentTemplateRepository


@pytest.fixture()
def dynamodb():
    with mock_aws():
        resource = boto3.resource("dynamodb", region_name="us-east-1")

        # MemberProfiles table
        resource.create_table(
            TableName="MemberProfiles",
            KeySchema=[{"AttributeName": "user_id", "KeyType": "HASH"}],
            AttributeDefinitions=[
                {"AttributeName": "user_id", "AttributeType": "S"},
            ],
            BillingMode="PAY_PER_REQUEST",
        )

        # AgentConfigs table
        resource.create_table(
            TableName="AgentConfigs",
            KeySchema=[
                {"AttributeName": "user_id", "KeyType": "HASH"},
                {"AttributeName": "agent_type", "KeyType": "RANGE"},
            ],
            AttributeDefinitions=[
                {"AttributeName": "user_id", "AttributeType": "S"},
                {"AttributeName": "agent_type", "AttributeType": "S"},
            ],
            BillingMode="PAY_PER_REQUEST",
        )

        # AgentTemplates table
        resource.create_table(
            TableName="AgentTemplates",
            KeySchema=[{"AttributeName": "template_id", "KeyType": "HASH"}],
            AttributeDefinitions=[
                {"AttributeName": "template_id", "AttributeType": "S"},
                {"AttributeName": "agent_type", "AttributeType": "S"},
            ],
            GlobalSecondaryIndexes=[
                {
                    "IndexName": "agent_type-index",
                    "KeySchema": [{"AttributeName": "agent_type", "KeyType": "HASH"}],
                    "Projection": {"ProjectionType": "ALL"},
                },
            ],
            BillingMode="PAY_PER_REQUEST",
        )

        yield resource


# ---------------------------------------------------------------------------
# ProfileRepository
# ---------------------------------------------------------------------------


class TestProfileRepository:
    def test_create_and_get(self, dynamodb):
        repo = ProfileRepository(dynamodb)
        repo.create({"user_id": "u1", "display_name": "Alice"})
        fetched = repo.get_by_id({"user_id": "u1"})
        assert fetched is not None
        assert fetched["display_name"] == "Alice"

    def test_batch_get_by_user_ids(self, dynamodb):
        repo = ProfileRepository(dynamodb)
        repo.create({"user_id": "u1", "display_name": "Alice"})
        repo.create({"user_id": "u2", "display_name": "Bob"})
        repo.create({"user_id": "u3", "display_name": "Charlie"})
        results = repo.batch_get_by_user_ids(["u1", "u3"])
        assert len(results) == 2
        ids = {r["user_id"] for r in results}
        assert ids == {"u1", "u3"}

    def test_batch_get_empty(self, dynamodb):
        repo = ProfileRepository(dynamodb)
        assert repo.batch_get_by_user_ids([]) == []

    def test_batch_get_missing_users(self, dynamodb):
        repo = ProfileRepository(dynamodb)
        repo.create({"user_id": "u1", "display_name": "Alice"})
        results = repo.batch_get_by_user_ids(["u1", "u999"])
        assert len(results) == 1

    def test_update_profile(self, dynamodb):
        repo = ProfileRepository(dynamodb)
        repo.create({"user_id": "u1", "display_name": "Alice"})
        updated = repo.update({"user_id": "u1"}, {"display_name": "Alice Smith"})
        assert updated["display_name"] == "Alice Smith"


# ---------------------------------------------------------------------------
# AgentConfigRepository
# ---------------------------------------------------------------------------


class TestAgentConfigRepository:
    def test_create_and_get_config(self, dynamodb):
        repo = AgentConfigRepository(dynamodb)
        repo.create({"user_id": "u1", "agent_type": "health", "model": "claude-3"})
        result = repo.get_config("u1", "health")
        assert result is not None
        assert result["model"] == "claude-3"

    def test_query_by_user(self, dynamodb):
        repo = AgentConfigRepository(dynamodb)
        repo.create({"user_id": "u1", "agent_type": "health"})
        repo.create({"user_id": "u1", "agent_type": "chat"})
        repo.create({"user_id": "u2", "agent_type": "health"})
        result = repo.query_by_user("u1")
        assert result.count == 2

    def test_delete_config(self, dynamodb):
        repo = AgentConfigRepository(dynamodb)
        repo.create({"user_id": "u1", "agent_type": "health"})
        repo.delete_config("u1", "health")
        assert repo.get_config("u1", "health") is None

    def test_get_config_not_found(self, dynamodb):
        repo = AgentConfigRepository(dynamodb)
        assert repo.get_config("u1", "nonexistent") is None


# ---------------------------------------------------------------------------
# AgentTemplateRepository
# ---------------------------------------------------------------------------


class TestAgentTemplateRepository:
    def test_create_and_get(self, dynamodb):
        repo = AgentTemplateRepository(dynamodb)
        repo.create(
            {"template_id": "t1", "agent_type": "health", "name": "Health Agent"}
        )
        fetched = repo.get_by_id({"template_id": "t1"})
        assert fetched is not None
        assert fetched["name"] == "Health Agent"

    def test_query_by_agent_type(self, dynamodb):
        repo = AgentTemplateRepository(dynamodb)
        repo.create({"template_id": "t1", "agent_type": "health"})
        repo.create({"template_id": "t2", "agent_type": "health"})
        repo.create({"template_id": "t3", "agent_type": "chat"})
        result = repo.query_by_agent_type("health")
        assert result.count == 2

    def test_list_all(self, dynamodb):
        repo = AgentTemplateRepository(dynamodb)
        for i in range(3):
            repo.create({"template_id": f"t{i}", "agent_type": "type"})
        result = repo.list_all()
        assert result.count == 3

    def test_list_all_with_limit(self, dynamodb):
        repo = AgentTemplateRepository(dynamodb)
        for i in range(5):
            repo.create({"template_id": f"t{i}", "agent_type": "type"})
        result = repo.list_all(limit=2)
        assert result.count == 2
