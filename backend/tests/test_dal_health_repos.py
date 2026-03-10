"""Tests for health entity repositories (Task 2.4)."""

import boto3
import pytest
from moto import mock_aws

from app.dal.repositories.health_record_repo import HealthRecordRepository
from app.dal.repositories.health_observation_repo import HealthObservationRepository
from app.dal.repositories.health_audit_repo import HealthAuditRepository
from app.dal.repositories.health_document_repo import HealthDocumentRepository


@pytest.fixture()
def dynamodb():
    with mock_aws():
        resource = boto3.resource("dynamodb", region_name="us-east-1")

        # HealthRecords table
        resource.create_table(
            TableName="HealthRecords",
            KeySchema=[
                {"AttributeName": "user_id", "KeyType": "HASH"},
                {"AttributeName": "record_id", "KeyType": "RANGE"},
            ],
            AttributeDefinitions=[
                {"AttributeName": "user_id", "AttributeType": "S"},
                {"AttributeName": "record_id", "AttributeType": "S"},
                {"AttributeName": "record_type", "AttributeType": "S"},
            ],
            GlobalSecondaryIndexes=[
                {
                    "IndexName": "record_type-index",
                    "KeySchema": [
                        {"AttributeName": "user_id", "KeyType": "HASH"},
                        {"AttributeName": "record_type", "KeyType": "RANGE"},
                    ],
                    "Projection": {"ProjectionType": "ALL"},
                },
            ],
            BillingMode="PAY_PER_REQUEST",
        )

        # HealthObservations table
        resource.create_table(
            TableName="HealthObservations",
            KeySchema=[
                {"AttributeName": "user_id", "KeyType": "HASH"},
                {"AttributeName": "observation_id", "KeyType": "RANGE"},
            ],
            AttributeDefinitions=[
                {"AttributeName": "user_id", "AttributeType": "S"},
                {"AttributeName": "observation_id", "AttributeType": "S"},
                {"AttributeName": "category", "AttributeType": "S"},
            ],
            GlobalSecondaryIndexes=[
                {
                    "IndexName": "category-index",
                    "KeySchema": [
                        {"AttributeName": "user_id", "KeyType": "HASH"},
                        {"AttributeName": "category", "KeyType": "RANGE"},
                    ],
                    "Projection": {"ProjectionType": "ALL"},
                },
            ],
            BillingMode="PAY_PER_REQUEST",
        )

        # HealthAuditLog table
        resource.create_table(
            TableName="HealthAuditLog",
            KeySchema=[
                {"AttributeName": "record_id", "KeyType": "HASH"},
                {"AttributeName": "audit_sk", "KeyType": "RANGE"},
            ],
            AttributeDefinitions=[
                {"AttributeName": "record_id", "AttributeType": "S"},
                {"AttributeName": "audit_sk", "AttributeType": "S"},
                {"AttributeName": "user_id", "AttributeType": "S"},
                {"AttributeName": "created_at", "AttributeType": "S"},
            ],
            GlobalSecondaryIndexes=[
                {
                    "IndexName": "user-audit-index",
                    "KeySchema": [
                        {"AttributeName": "user_id", "KeyType": "HASH"},
                        {"AttributeName": "created_at", "KeyType": "RANGE"},
                    ],
                    "Projection": {"ProjectionType": "ALL"},
                },
            ],
            BillingMode="PAY_PER_REQUEST",
        )

        # HealthDocuments table
        resource.create_table(
            TableName="HealthDocuments",
            KeySchema=[
                {"AttributeName": "user_id", "KeyType": "HASH"},
                {"AttributeName": "document_id", "KeyType": "RANGE"},
            ],
            AttributeDefinitions=[
                {"AttributeName": "user_id", "AttributeType": "S"},
                {"AttributeName": "document_id", "AttributeType": "S"},
            ],
            BillingMode="PAY_PER_REQUEST",
        )

        yield resource


# ---------------------------------------------------------------------------
# HealthRecordRepository
# ---------------------------------------------------------------------------


class TestHealthRecordRepository:
    def test_create_and_get(self, dynamodb):
        repo = HealthRecordRepository(dynamodb)
        repo.create(
            {
                "user_id": "u1",
                "record_id": "r1",
                "record_type": "vitals",
                "data": "bp=120/80",
            }
        )
        result = repo.get_record("u1", "r1")
        assert result is not None
        assert result["data"] == "bp=120/80"

    def test_query_by_user(self, dynamodb):
        repo = HealthRecordRepository(dynamodb)
        repo.create({"user_id": "u1", "record_id": "r1", "record_type": "vitals"})
        repo.create({"user_id": "u1", "record_id": "r2", "record_type": "medication"})
        result = repo.query_by_user("u1")
        assert result.count == 2

    def test_query_by_record_type(self, dynamodb):
        repo = HealthRecordRepository(dynamodb)
        repo.create({"user_id": "u1", "record_id": "r1", "record_type": "vitals"})
        repo.create({"user_id": "u1", "record_id": "r2", "record_type": "medication"})
        repo.create({"user_id": "u1", "record_id": "r3", "record_type": "vitals"})
        result = repo.query_by_record_type("u1", "vitals")
        assert result.count == 2

    def test_get_record_not_found(self, dynamodb):
        repo = HealthRecordRepository(dynamodb)
        assert repo.get_record("u1", "nonexistent") is None

    def test_query_empty(self, dynamodb):
        repo = HealthRecordRepository(dynamodb)
        result = repo.query_by_user("nonexistent")
        assert result.count == 0


# ---------------------------------------------------------------------------
# HealthObservationRepository
# ---------------------------------------------------------------------------


class TestHealthObservationRepository:
    def test_create_and_get(self, dynamodb):
        repo = HealthObservationRepository(dynamodb)
        repo.create(
            {
                "user_id": "u1",
                "observation_id": "o1",
                "category": "sleep",
                "note": "slept well",
            }
        )
        result = repo.get_observation("u1", "o1")
        assert result is not None
        assert result["note"] == "slept well"

    def test_query_by_category(self, dynamodb):
        repo = HealthObservationRepository(dynamodb)
        repo.create({"user_id": "u1", "observation_id": "o1", "category": "sleep"})
        repo.create({"user_id": "u1", "observation_id": "o2", "category": "exercise"})
        repo.create({"user_id": "u1", "observation_id": "o3", "category": "sleep"})
        result = repo.query_by_category("u1", "sleep")
        assert result.count == 2

    def test_query_by_user(self, dynamodb):
        repo = HealthObservationRepository(dynamodb)
        repo.create({"user_id": "u1", "observation_id": "o1", "category": "sleep"})
        repo.create({"user_id": "u1", "observation_id": "o2", "category": "exercise"})
        result = repo.query_by_user("u1")
        assert result.count == 2


# ---------------------------------------------------------------------------
# HealthAuditRepository
# ---------------------------------------------------------------------------


class TestHealthAuditRepository:
    def test_create_and_query_by_record(self, dynamodb):
        repo = HealthAuditRepository(dynamodb)
        repo.create(
            {
                "record_id": "r1",
                "audit_sk": "2025-01-01#a1",
                "user_id": "u1",
                "action": "create",
            }
        )
        repo.create(
            {
                "record_id": "r1",
                "audit_sk": "2025-01-02#a2",
                "user_id": "u1",
                "action": "update",
            }
        )
        result = repo.query_by_record("r1")
        assert result.count == 2

    def test_query_by_user(self, dynamodb):
        repo = HealthAuditRepository(dynamodb)
        repo.create(
            {
                "record_id": "r1",
                "audit_sk": "2025-01-01#a1",
                "user_id": "u1",
                "created_at": "2025-01-01T00:00:00",
                "action": "create",
            }
        )
        repo.create(
            {
                "record_id": "r2",
                "audit_sk": "2025-01-02#a2",
                "user_id": "u1",
                "created_at": "2025-01-02T00:00:00",
                "action": "update",
            }
        )
        result = repo.query_by_user("u1")
        assert result.count == 2

    def test_query_by_user_empty(self, dynamodb):
        repo = HealthAuditRepository(dynamodb)
        result = repo.query_by_user("nonexistent")
        assert result.count == 0


# ---------------------------------------------------------------------------
# HealthDocumentRepository
# ---------------------------------------------------------------------------


class TestHealthDocumentRepository:
    def test_create_and_get(self, dynamodb):
        repo = HealthDocumentRepository(dynamodb)
        repo.create({"user_id": "u1", "document_id": "d1", "filename": "report.pdf"})
        result = repo.get_document("u1", "d1")
        assert result is not None
        assert result["filename"] == "report.pdf"

    def test_query_by_user(self, dynamodb):
        repo = HealthDocumentRepository(dynamodb)
        repo.create({"user_id": "u1", "document_id": "d1"})
        repo.create({"user_id": "u1", "document_id": "d2"})
        result = repo.query_by_user("u1")
        assert result.count == 2

    def test_get_document_not_found(self, dynamodb):
        repo = HealthDocumentRepository(dynamodb)
        assert repo.get_document("u1", "nonexistent") is None
