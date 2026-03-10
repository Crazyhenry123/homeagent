"""Tests for remaining entity repositories (Task 2.5)."""

import boto3
import pytest
from moto import mock_aws

from app.dal.repositories.family_relationship_repo import FamilyRelationshipRepository
from app.dal.repositories.chat_media_repo import ChatMediaRepository
from app.dal.repositories.member_permission_repo import MemberPermissionRepository
from app.dal.repositories.memory_sharing_config_repo import (
    MemorySharingConfigRepository,
)
from app.dal.repositories.storage_config_repo import StorageConfigRepository
from app.dal.repositories.oauth_token_repo import OAuthTokenRepository
from app.dal.repositories.oauth_state_repo import OAuthStateRepository


@pytest.fixture()
def dynamodb():
    with mock_aws():
        resource = boto3.resource("dynamodb", region_name="us-east-1")

        # FamilyRelationships
        resource.create_table(
            TableName="FamilyRelationships",
            KeySchema=[
                {"AttributeName": "user_id", "KeyType": "HASH"},
                {"AttributeName": "related_user_id", "KeyType": "RANGE"},
            ],
            AttributeDefinitions=[
                {"AttributeName": "user_id", "AttributeType": "S"},
                {"AttributeName": "related_user_id", "AttributeType": "S"},
            ],
            BillingMode="PAY_PER_REQUEST",
        )

        # ChatMedia
        resource.create_table(
            TableName="ChatMedia",
            KeySchema=[{"AttributeName": "media_id", "KeyType": "HASH"}],
            AttributeDefinitions=[
                {"AttributeName": "media_id", "AttributeType": "S"},
            ],
            BillingMode="PAY_PER_REQUEST",
        )

        # MemberPermissions
        resource.create_table(
            TableName="MemberPermissions",
            KeySchema=[
                {"AttributeName": "user_id", "KeyType": "HASH"},
                {"AttributeName": "permission_type", "KeyType": "RANGE"},
            ],
            AttributeDefinitions=[
                {"AttributeName": "user_id", "AttributeType": "S"},
                {"AttributeName": "permission_type", "AttributeType": "S"},
            ],
            BillingMode="PAY_PER_REQUEST",
        )

        # MemorySharingConfig
        resource.create_table(
            TableName="MemorySharingConfig",
            KeySchema=[{"AttributeName": "user_id", "KeyType": "HASH"}],
            AttributeDefinitions=[
                {"AttributeName": "user_id", "AttributeType": "S"},
            ],
            BillingMode="PAY_PER_REQUEST",
        )

        # StorageConfig
        resource.create_table(
            TableName="StorageConfig",
            KeySchema=[{"AttributeName": "user_id", "KeyType": "HASH"}],
            AttributeDefinitions=[
                {"AttributeName": "user_id", "AttributeType": "S"},
            ],
            BillingMode="PAY_PER_REQUEST",
        )

        # OAuthTokens
        resource.create_table(
            TableName="OAuthTokens",
            KeySchema=[
                {"AttributeName": "user_id", "KeyType": "HASH"},
                {"AttributeName": "provider", "KeyType": "RANGE"},
            ],
            AttributeDefinitions=[
                {"AttributeName": "user_id", "AttributeType": "S"},
                {"AttributeName": "provider", "AttributeType": "S"},
            ],
            BillingMode="PAY_PER_REQUEST",
        )

        # OAuthState
        resource.create_table(
            TableName="OAuthState",
            KeySchema=[{"AttributeName": "state", "KeyType": "HASH"}],
            AttributeDefinitions=[
                {"AttributeName": "state", "AttributeType": "S"},
            ],
            BillingMode="PAY_PER_REQUEST",
        )

        yield resource


# ---------------------------------------------------------------------------
# FamilyRelationshipRepository
# ---------------------------------------------------------------------------


class TestFamilyRelationshipRepository:
    def test_create_and_get(self, dynamodb):
        repo = FamilyRelationshipRepository(dynamodb)
        repo.create(
            {
                "user_id": "u1",
                "related_user_id": "u2",
                "relationship": "parent",
            }
        )
        result = repo.get_relationship("u1", "u2")
        assert result is not None
        assert result["relationship"] == "parent"

    def test_query_by_user(self, dynamodb):
        repo = FamilyRelationshipRepository(dynamodb)
        repo.create(
            {"user_id": "u1", "related_user_id": "u2", "relationship": "parent"}
        )
        repo.create(
            {"user_id": "u1", "related_user_id": "u3", "relationship": "sibling"}
        )
        result = repo.query_by_user("u1")
        assert result.count == 2

    def test_delete_relationship(self, dynamodb):
        repo = FamilyRelationshipRepository(dynamodb)
        repo.create({"user_id": "u1", "related_user_id": "u2"})
        repo.delete_relationship("u1", "u2")
        assert repo.get_relationship("u1", "u2") is None

    def test_get_not_found(self, dynamodb):
        repo = FamilyRelationshipRepository(dynamodb)
        assert repo.get_relationship("u1", "u999") is None


# ---------------------------------------------------------------------------
# ChatMediaRepository
# ---------------------------------------------------------------------------


class TestChatMediaRepository:
    def test_create_with_ttl(self, dynamodb):
        repo = ChatMediaRepository(dynamodb)
        item = repo.create_with_ttl(
            {"media_id": "m1", "content_type": "image/png"},
            expires_at=1700000000,
        )
        assert item["expires_at"] == 1700000000
        fetched = repo.get_by_id({"media_id": "m1"})
        assert fetched is not None
        assert fetched["content_type"] == "image/png"

    def test_create_basic(self, dynamodb):
        repo = ChatMediaRepository(dynamodb)
        item = repo.create({"media_id": "m1", "content_type": "image/png"})
        assert item["media_id"] == "m1"

    def test_delete(self, dynamodb):
        repo = ChatMediaRepository(dynamodb)
        repo.create({"media_id": "m1"})
        repo.delete({"media_id": "m1"})
        assert repo.get_by_id({"media_id": "m1"}) is None


# ---------------------------------------------------------------------------
# MemberPermissionRepository
# ---------------------------------------------------------------------------


class TestMemberPermissionRepository:
    def test_create_and_get(self, dynamodb):
        repo = MemberPermissionRepository(dynamodb)
        repo.create(
            {"user_id": "u1", "permission_type": "health_read", "allowed": True}
        )
        result = repo.get_permission("u1", "health_read")
        assert result is not None
        assert result["allowed"] is True

    def test_query_by_user(self, dynamodb):
        repo = MemberPermissionRepository(dynamodb)
        repo.create({"user_id": "u1", "permission_type": "health_read"})
        repo.create({"user_id": "u1", "permission_type": "health_write"})
        result = repo.query_by_user("u1")
        assert result.count == 2

    def test_delete_permission(self, dynamodb):
        repo = MemberPermissionRepository(dynamodb)
        repo.create({"user_id": "u1", "permission_type": "health_read"})
        repo.delete_permission("u1", "health_read")
        assert repo.get_permission("u1", "health_read") is None


# ---------------------------------------------------------------------------
# MemorySharingConfigRepository
# ---------------------------------------------------------------------------


class TestMemorySharingConfigRepository:
    def test_create_and_get(self, dynamodb):
        repo = MemorySharingConfigRepository(dynamodb)
        repo.create({"user_id": "u1", "sharing_enabled": True})
        fetched = repo.get_by_id({"user_id": "u1"})
        assert fetched is not None
        assert fetched["sharing_enabled"] is True

    def test_update(self, dynamodb):
        repo = MemorySharingConfigRepository(dynamodb)
        repo.create({"user_id": "u1", "sharing_enabled": True})
        updated = repo.update({"user_id": "u1"}, {"sharing_enabled": False})
        assert updated["sharing_enabled"] is False


# ---------------------------------------------------------------------------
# StorageConfigRepository
# ---------------------------------------------------------------------------


class TestStorageConfigRepository:
    def test_create_and_get(self, dynamodb):
        repo = StorageConfigRepository(dynamodb)
        repo.create({"user_id": "u1", "provider": "s3", "bucket": "my-bucket"})
        fetched = repo.get_by_id({"user_id": "u1"})
        assert fetched is not None
        assert fetched["bucket"] == "my-bucket"

    def test_update(self, dynamodb):
        repo = StorageConfigRepository(dynamodb)
        repo.create({"user_id": "u1", "provider": "s3"})
        updated = repo.update({"user_id": "u1"}, {"bucket": "new-bucket"})
        assert updated["bucket"] == "new-bucket"


# ---------------------------------------------------------------------------
# OAuthTokenRepository
# ---------------------------------------------------------------------------


class TestOAuthTokenRepository:
    def test_create_and_get(self, dynamodb):
        repo = OAuthTokenRepository(dynamodb)
        repo.create({"user_id": "u1", "provider": "google", "access_token": "tok-abc"})
        result = repo.get_token("u1", "google")
        assert result is not None
        assert result["access_token"] == "tok-abc"

    def test_query_by_user(self, dynamodb):
        repo = OAuthTokenRepository(dynamodb)
        repo.create({"user_id": "u1", "provider": "google"})
        repo.create({"user_id": "u1", "provider": "github"})
        result = repo.query_by_user("u1")
        assert result.count == 2

    def test_delete_token(self, dynamodb):
        repo = OAuthTokenRepository(dynamodb)
        repo.create({"user_id": "u1", "provider": "google"})
        repo.delete_token("u1", "google")
        assert repo.get_token("u1", "google") is None

    def test_get_not_found(self, dynamodb):
        repo = OAuthTokenRepository(dynamodb)
        assert repo.get_token("u1", "nonexistent") is None


# ---------------------------------------------------------------------------
# OAuthStateRepository
# ---------------------------------------------------------------------------


class TestOAuthStateRepository:
    def test_create_with_ttl(self, dynamodb):
        repo = OAuthStateRepository(dynamodb)
        item = repo.create_with_ttl(
            {"state": "state-abc", "redirect_uri": "http://localhost"},
            expires_at=1700000000,
        )
        assert item["expires_at"] == 1700000000
        fetched = repo.get_by_id({"state": "state-abc"})
        assert fetched is not None

    def test_create_basic(self, dynamodb):
        repo = OAuthStateRepository(dynamodb)
        item = repo.create({"state": "state-abc", "redirect_uri": "http://localhost"})
        assert item["state"] == "state-abc"

    def test_delete(self, dynamodb):
        repo = OAuthStateRepository(dynamodb)
        repo.create({"state": "state-abc"})
        repo.delete({"state": "state-abc"})
        assert repo.get_by_id({"state": "state-abc"}) is None
