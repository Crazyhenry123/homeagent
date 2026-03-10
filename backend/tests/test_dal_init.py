"""Tests for DAL initialization and Flask wiring."""

import boto3
import pytest
from moto import mock_aws

from app.dal import DAL, get_dal
from app.dal.repositories.user_repo import UserRepository
from app.dal.repositories.conversation_repo import ConversationRepository
from app.dal.repositories.message_repo import MessageRepository


@pytest.fixture()
def dynamodb():
    with mock_aws():
        resource = boto3.resource("dynamodb", region_name="us-east-1")
        yield resource


class TestDAL:
    def test_all_repositories_instantiated(self, dynamodb):
        dal = DAL(dynamodb)
        assert isinstance(dal.users, UserRepository)
        assert isinstance(dal.conversations, ConversationRepository)
        assert isinstance(dal.messages, MessageRepository)

    def test_all_repo_attributes_exist(self, dynamodb):
        dal = DAL(dynamodb)
        expected = [
            "users",
            "devices",
            "invite_codes",
            "families",
            "memberships",
            "conversations",
            "messages",
            "profiles",
            "agent_configs",
            "agent_templates",
            "health_records",
            "health_observations",
            "health_audit",
            "health_documents",
            "family_relationships",
            "chat_media",
            "member_permissions",
            "memory_sharing_config",
            "storage_config",
            "oauth_tokens",
            "oauth_state",
        ]
        for attr in expected:
            assert hasattr(dal, attr), f"DAL missing attribute: {attr}"

    def test_table_prefix_passed_through(self, dynamodb):
        dal = DAL(dynamodb, table_prefix="test_")
        assert dal.users.table_name == "test_Users"
        assert dal.conversations.table_name == "test_Conversations"

    def test_get_dal_in_app_context(self, dynamodb):
        """Test get_dal() returns the DAL from Flask app extensions."""
        from flask import Flask

        app = Flask(__name__)
        dal = DAL(dynamodb)
        app.extensions["dal"] = dal

        with app.app_context():
            result = get_dal()
            assert result is dal
