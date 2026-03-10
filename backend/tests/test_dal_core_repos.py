"""Tests for core entity repositories (Task 2.1): User, Device, InviteCode, Family, Membership."""

import boto3
import pytest
from moto import mock_aws

from app.dal.repositories.user_repo import UserRepository
from app.dal.repositories.device_repo import DeviceRepository
from app.dal.repositories.invite_code_repo import InviteCodeRepository
from app.dal.repositories.family_repo import FamilyRepository
from app.dal.repositories.membership_repo import MembershipRepository


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def dynamodb():
    with mock_aws():
        resource = boto3.resource("dynamodb", region_name="us-east-1")

        # Users table
        resource.create_table(
            TableName="Users",
            KeySchema=[{"AttributeName": "user_id", "KeyType": "HASH"}],
            AttributeDefinitions=[
                {"AttributeName": "user_id", "AttributeType": "S"},
                {"AttributeName": "email", "AttributeType": "S"},
                {"AttributeName": "cognito_sub", "AttributeType": "S"},
            ],
            GlobalSecondaryIndexes=[
                {
                    "IndexName": "email-index",
                    "KeySchema": [{"AttributeName": "email", "KeyType": "HASH"}],
                    "Projection": {"ProjectionType": "ALL"},
                },
                {
                    "IndexName": "cognito_sub-index",
                    "KeySchema": [{"AttributeName": "cognito_sub", "KeyType": "HASH"}],
                    "Projection": {"ProjectionType": "ALL"},
                },
            ],
            BillingMode="PAY_PER_REQUEST",
        )

        # Devices table
        resource.create_table(
            TableName="Devices",
            KeySchema=[{"AttributeName": "device_id", "KeyType": "HASH"}],
            AttributeDefinitions=[
                {"AttributeName": "device_id", "AttributeType": "S"},
                {"AttributeName": "device_token", "AttributeType": "S"},
                {"AttributeName": "user_id", "AttributeType": "S"},
            ],
            GlobalSecondaryIndexes=[
                {
                    "IndexName": "device_token-index",
                    "KeySchema": [{"AttributeName": "device_token", "KeyType": "HASH"}],
                    "Projection": {"ProjectionType": "ALL"},
                },
                {
                    "IndexName": "user_id-index",
                    "KeySchema": [{"AttributeName": "user_id", "KeyType": "HASH"}],
                    "Projection": {"ProjectionType": "ALL"},
                },
            ],
            BillingMode="PAY_PER_REQUEST",
        )

        # InviteCodes table
        resource.create_table(
            TableName="InviteCodes",
            KeySchema=[{"AttributeName": "code", "KeyType": "HASH"}],
            AttributeDefinitions=[
                {"AttributeName": "code", "AttributeType": "S"},
                {"AttributeName": "invited_email", "AttributeType": "S"},
            ],
            GlobalSecondaryIndexes=[
                {
                    "IndexName": "invited_email-index",
                    "KeySchema": [
                        {"AttributeName": "invited_email", "KeyType": "HASH"}
                    ],
                    "Projection": {"ProjectionType": "ALL"},
                },
            ],
            BillingMode="PAY_PER_REQUEST",
        )

        # Families table
        resource.create_table(
            TableName="Families",
            KeySchema=[{"AttributeName": "family_id", "KeyType": "HASH"}],
            AttributeDefinitions=[
                {"AttributeName": "family_id", "AttributeType": "S"},
                {"AttributeName": "owner_user_id", "AttributeType": "S"},
            ],
            GlobalSecondaryIndexes=[
                {
                    "IndexName": "owner-index",
                    "KeySchema": [
                        {"AttributeName": "owner_user_id", "KeyType": "HASH"}
                    ],
                    "Projection": {"ProjectionType": "ALL"},
                },
            ],
            BillingMode="PAY_PER_REQUEST",
        )

        # FamilyMembers table
        resource.create_table(
            TableName="FamilyMembers",
            KeySchema=[
                {"AttributeName": "family_id", "KeyType": "HASH"},
                {"AttributeName": "user_id", "KeyType": "RANGE"},
            ],
            AttributeDefinitions=[
                {"AttributeName": "family_id", "AttributeType": "S"},
                {"AttributeName": "user_id", "AttributeType": "S"},
            ],
            BillingMode="PAY_PER_REQUEST",
        )

        yield resource


# ---------------------------------------------------------------------------
# UserRepository
# ---------------------------------------------------------------------------


class TestUserRepository:
    def test_create_and_get(self, dynamodb):
        repo = UserRepository(dynamodb)
        item = repo.create(
            {"user_id": "u1", "email": "alice@test.com", "cognito_sub": "sub-1"}
        )
        assert item["user_id"] == "u1"
        assert "created_at" in item

        fetched = repo.get_by_id({"user_id": "u1"})
        assert fetched is not None
        assert fetched["email"] == "alice@test.com"

    def test_get_by_email(self, dynamodb):
        repo = UserRepository(dynamodb)
        repo.create(
            {"user_id": "u1", "email": "alice@test.com", "cognito_sub": "sub-1"}
        )
        result = repo.get_by_email("alice@test.com")
        assert result is not None
        assert result["user_id"] == "u1"

    def test_get_by_email_not_found(self, dynamodb):
        repo = UserRepository(dynamodb)
        assert repo.get_by_email("nobody@test.com") is None

    def test_get_by_cognito_sub(self, dynamodb):
        repo = UserRepository(dynamodb)
        repo.create(
            {"user_id": "u1", "email": "alice@test.com", "cognito_sub": "sub-abc"}
        )
        result = repo.get_by_cognito_sub("sub-abc")
        assert result is not None
        assert result["user_id"] == "u1"

    def test_get_by_cognito_sub_not_found(self, dynamodb):
        repo = UserRepository(dynamodb)
        assert repo.get_by_cognito_sub("sub-nope") is None

    def test_list_all(self, dynamodb):
        repo = UserRepository(dynamodb)
        for i in range(3):
            repo.create(
                {
                    "user_id": f"u{i}",
                    "email": f"u{i}@test.com",
                    "cognito_sub": f"sub-{i}",
                }
            )
        result = repo.list_all(limit=10)
        assert result.count == 3

    def test_update_user(self, dynamodb):
        repo = UserRepository(dynamodb)
        repo.create(
            {"user_id": "u1", "email": "alice@test.com", "cognito_sub": "sub-1"}
        )
        updated = repo.update({"user_id": "u1"}, {"name": "Alice"})
        assert updated["name"] == "Alice"


# ---------------------------------------------------------------------------
# DeviceRepository
# ---------------------------------------------------------------------------


class TestDeviceRepository:
    def test_create_and_get_by_token(self, dynamodb):
        repo = DeviceRepository(dynamodb)
        repo.create({"device_id": "d1", "device_token": "tok-abc", "user_id": "u1"})
        result = repo.get_by_token("tok-abc")
        assert result is not None
        assert result["device_id"] == "d1"

    def test_get_by_token_not_found(self, dynamodb):
        repo = DeviceRepository(dynamodb)
        assert repo.get_by_token("tok-nope") is None

    def test_query_by_user(self, dynamodb):
        repo = DeviceRepository(dynamodb)
        repo.create({"device_id": "d1", "device_token": "tok-1", "user_id": "u1"})
        repo.create({"device_id": "d2", "device_token": "tok-2", "user_id": "u1"})
        repo.create({"device_id": "d3", "device_token": "tok-3", "user_id": "u2"})
        result = repo.query_by_user("u1")
        assert result.count == 2

    def test_query_by_user_pagination(self, dynamodb):
        repo = DeviceRepository(dynamodb)
        for i in range(5):
            repo.create(
                {"device_id": f"d{i}", "device_token": f"tok-{i}", "user_id": "u1"}
            )
        page1 = repo.query_by_user("u1", limit=2)
        assert page1.count == 2
        assert page1.next_cursor is not None


# ---------------------------------------------------------------------------
# InviteCodeRepository
# ---------------------------------------------------------------------------


class TestInviteCodeRepository:
    def test_create_and_get(self, dynamodb):
        repo = InviteCodeRepository(dynamodb)
        repo.create(
            {"code": "ABC123", "invited_email": "bob@test.com", "status": "active"}
        )
        fetched = repo.get_by_id({"code": "ABC123"})
        assert fetched is not None
        assert fetched["invited_email"] == "bob@test.com"

    def test_get_by_email(self, dynamodb):
        repo = InviteCodeRepository(dynamodb)
        repo.create({"code": "ABC123", "invited_email": "bob@test.com"})
        result = repo.get_by_email("bob@test.com")
        assert result is not None
        assert result["code"] == "ABC123"

    def test_query_by_email_multiple(self, dynamodb):
        repo = InviteCodeRepository(dynamodb)
        repo.create({"code": "C1", "invited_email": "bob@test.com"})
        repo.create({"code": "C2", "invited_email": "bob@test.com"})
        result = repo.query_by_email("bob@test.com")
        assert result.count == 2


# ---------------------------------------------------------------------------
# FamilyRepository
# ---------------------------------------------------------------------------


class TestFamilyRepository:
    def test_create_and_get(self, dynamodb):
        repo = FamilyRepository(dynamodb)
        repo.create({"family_id": "f1", "owner_user_id": "u1", "name": "Smiths"})
        fetched = repo.get_by_id({"family_id": "f1"})
        assert fetched is not None
        assert fetched["name"] == "Smiths"

    def test_get_by_owner(self, dynamodb):
        repo = FamilyRepository(dynamodb)
        repo.create({"family_id": "f1", "owner_user_id": "u1", "name": "Smiths"})
        result = repo.get_by_owner("u1")
        assert result is not None
        assert result["family_id"] == "f1"

    def test_get_by_owner_not_found(self, dynamodb):
        repo = FamilyRepository(dynamodb)
        assert repo.get_by_owner("u999") is None

    def test_query_by_owner_multiple(self, dynamodb):
        repo = FamilyRepository(dynamodb)
        repo.create({"family_id": "f1", "owner_user_id": "u1"})
        repo.create({"family_id": "f2", "owner_user_id": "u1"})
        result = repo.query_by_owner("u1")
        assert result.count == 2


# ---------------------------------------------------------------------------
# MembershipRepository
# ---------------------------------------------------------------------------


class TestMembershipRepository:
    def test_create_and_query_by_family(self, dynamodb):
        repo = MembershipRepository(dynamodb)
        repo.create({"family_id": "f1", "user_id": "u1", "role": "admin"})
        repo.create({"family_id": "f1", "user_id": "u2", "role": "member"})
        result = repo.query_by_family("f1")
        assert result.count == 2

    def test_get_membership(self, dynamodb):
        repo = MembershipRepository(dynamodb)
        repo.create({"family_id": "f1", "user_id": "u1", "role": "admin"})
        result = repo.get_membership("f1", "u1")
        assert result is not None
        assert result["role"] == "admin"

    def test_get_membership_not_found(self, dynamodb):
        repo = MembershipRepository(dynamodb)
        assert repo.get_membership("f1", "u999") is None

    def test_delete_membership(self, dynamodb):
        repo = MembershipRepository(dynamodb)
        repo.create({"family_id": "f1", "user_id": "u1", "role": "admin"})
        repo.delete_membership("f1", "u1")
        assert repo.get_membership("f1", "u1") is None

    def test_query_empty_family(self, dynamodb):
        repo = MembershipRepository(dynamodb)
        result = repo.query_by_family("nonexistent")
        assert result.count == 0
