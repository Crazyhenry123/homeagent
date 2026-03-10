"""Unit tests for FamilyMemoryStoreRegistry."""

from __future__ import annotations

import time
from unittest.mock import MagicMock, patch

import boto3
import pytest
from botocore.exceptions import ClientError
from moto import mock_aws

from app.models.agentcore import FamilyMemoryStoresItem
from app.services.family_memory_registry import (
    FamilyMemoryStoreRegistry,
    MemoryStoreProvisioningError,
    StoreStatus,
    _CACHE_TTL_SECONDS,
)

REGION = "us-east-1"
TABLE_NAME = "FamilyMemoryStores"


def _create_table(dynamodb_resource):
    """Create the FamilyMemoryStores table in mocked DynamoDB."""
    dynamodb_resource.create_table(
        TableName=TABLE_NAME,
        KeySchema=[{"AttributeName": "family_id", "KeyType": "HASH"}],
        AttributeDefinitions=[
            {"AttributeName": "family_id", "AttributeType": "S"}
        ],
        BillingMode="PAY_PER_REQUEST",
    )


def _make_agentcore_client(store_id: str = "store-abc-123"):
    """Return a mock AgentCore client that returns a fixed store_id."""
    client = MagicMock()
    client.create_memory.return_value = {
        "memory": {"memoryId": store_id}
    }
    return client


# ---------------------------------------------------------------------------
# get_store_id
# ---------------------------------------------------------------------------


class TestGetStoreId:
    """Tests for FamilyMemoryStoreRegistry.get_store_id."""

    @mock_aws
    def test_cache_hit_returns_immediately(self):
        ddb = boto3.resource("dynamodb", region_name=REGION)
        _create_table(ddb)
        ac = _make_agentcore_client()
        registry = FamilyMemoryStoreRegistry(ddb, ac, TABLE_NAME)

        # Provision first
        sid = registry.get_store_id("fam-1")
        assert sid == "store-abc-123"

        # Second call should hit cache — no extra DynamoDB or AC calls
        ac.create_memory.reset_mock()
        sid2 = registry.get_store_id("fam-1")
        assert sid2 == sid
        ac.create_memory.assert_not_called()

    @mock_aws
    def test_dynamo_fallback_on_cache_miss(self):
        ddb = boto3.resource("dynamodb", region_name=REGION)
        _create_table(ddb)
        ac = _make_agentcore_client()
        registry = FamilyMemoryStoreRegistry(ddb, ac, TABLE_NAME)

        # Pre-populate DynamoDB directly
        table = ddb.Table(TABLE_NAME)
        table.put_item(Item={
            "family_id": "fam-2",
            "store_id": "existing-store",
            "store_name": "family_fam-2",
            "created_at": "2025-01-01T00:00:00Z",
            "updated_at": "2025-01-01T00:00:00Z",
            "status": "active",
            "event_expiry_days": 365,
        })

        sid = registry.get_store_id("fam-2")
        assert sid == "existing-store"
        ac.create_memory.assert_not_called()

    @mock_aws
    def test_provisions_on_demand_when_no_entry(self):
        ddb = boto3.resource("dynamodb", region_name=REGION)
        _create_table(ddb)
        ac = _make_agentcore_client("new-store-xyz")
        registry = FamilyMemoryStoreRegistry(ddb, ac, TABLE_NAME)

        sid = registry.get_store_id("fam-new")
        assert sid == "new-store-xyz"
        ac.create_memory.assert_called_once()

        # Verify DynamoDB entry was created
        table = ddb.Table(TABLE_NAME)
        item = table.get_item(Key={"family_id": "fam-new"}).get("Item")
        assert item is not None
        assert item["store_id"] == "new-store-xyz"
        assert item["status"] == "active"

    def test_empty_family_id_raises(self):
        registry = FamilyMemoryStoreRegistry(MagicMock(), MagicMock())
        with pytest.raises(ValueError, match="family_id"):
            registry.get_store_id("")

    def test_blank_family_id_raises(self):
        registry = FamilyMemoryStoreRegistry(MagicMock(), MagicMock())
        with pytest.raises(ValueError, match="family_id"):
            registry.get_store_id("   ")


# ---------------------------------------------------------------------------
# get_store_status
# ---------------------------------------------------------------------------


class TestGetStoreStatus:
    """Tests for FamilyMemoryStoreRegistry.get_store_status."""

    @mock_aws
    def test_active_store(self):
        ddb = boto3.resource("dynamodb", region_name=REGION)
        _create_table(ddb)
        ac = _make_agentcore_client()
        registry = FamilyMemoryStoreRegistry(ddb, ac, TABLE_NAME)

        table = ddb.Table(TABLE_NAME)
        table.put_item(Item={
            "family_id": "fam-1",
            "store_id": "store-1",
            "store_name": "family_fam-1",
            "created_at": "2025-01-01T00:00:00Z",
            "updated_at": "2025-01-01T00:00:00Z",
            "status": "active",
            "event_expiry_days": 365,
        })

        result = registry.get_store_status("fam-1")
        assert result == StoreStatus(store_id="store-1", status="active")

    @mock_aws
    def test_no_entry_returns_pending(self):
        ddb = boto3.resource("dynamodb", region_name=REGION)
        _create_table(ddb)
        ac = _make_agentcore_client()
        registry = FamilyMemoryStoreRegistry(ddb, ac, TABLE_NAME)

        result = registry.get_store_status("fam-missing")
        assert result == StoreStatus(store_id=None, status="pending")

    @mock_aws
    def test_provisioning_status_returns_pending(self):
        ddb = boto3.resource("dynamodb", region_name=REGION)
        _create_table(ddb)
        ac = _make_agentcore_client()
        registry = FamilyMemoryStoreRegistry(ddb, ac, TABLE_NAME)

        table = ddb.Table(TABLE_NAME)
        table.put_item(Item={
            "family_id": "fam-prov",
            "store_id": "store-prov",
            "store_name": "family_fam-prov",
            "created_at": "2025-01-01T00:00:00Z",
            "updated_at": "2025-01-01T00:00:00Z",
            "status": "provisioning",
            "event_expiry_days": 365,
        })

        result = registry.get_store_status("fam-prov")
        assert result == StoreStatus(store_id="store-prov", status="pending")


# ---------------------------------------------------------------------------
# provision_family_store
# ---------------------------------------------------------------------------


class TestProvisionFamilyStore:
    """Tests for FamilyMemoryStoreRegistry.provision_family_store."""

    @mock_aws
    def test_successful_provisioning(self):
        ddb = boto3.resource("dynamodb", region_name=REGION)
        _create_table(ddb)
        ac = _make_agentcore_client("prov-store-1")
        registry = FamilyMemoryStoreRegistry(ddb, ac, TABLE_NAME)

        sid = registry.provision_family_store("fam-p1")
        assert sid == "prov-store-1"

        # Verify DynamoDB
        item = ddb.Table(TABLE_NAME).get_item(
            Key={"family_id": "fam-p1"}
        ).get("Item")
        assert item["store_id"] == "prov-store-1"
        assert item["store_name"] == "family_fam-p1"
        assert item["status"] == "active"

    @mock_aws
    def test_conditional_write_conflict_uses_winner(self):
        ddb = boto3.resource("dynamodb", region_name=REGION)
        _create_table(ddb)

        # Pre-populate the table (simulating a concurrent winner)
        table = ddb.Table(TABLE_NAME)
        table.put_item(Item={
            "family_id": "fam-race",
            "store_id": "winner-store",
            "store_name": "family_fam-race",
            "created_at": "2025-01-01T00:00:00Z",
            "updated_at": "2025-01-01T00:00:00Z",
            "status": "active",
            "event_expiry_days": 365,
        })

        ac = _make_agentcore_client("loser-store")
        registry = FamilyMemoryStoreRegistry(ddb, ac, TABLE_NAME)

        # This should hit ConditionalCheckFailedException and re-read
        sid = registry.provision_family_store("fam-race")
        assert sid == "winner-store"

    @mock_aws
    def test_retry_on_create_memory_failure(self):
        ddb = boto3.resource("dynamodb", region_name=REGION)
        _create_table(ddb)

        ac = MagicMock()
        # Fail twice, succeed on third
        ac.create_memory.side_effect = [
            Exception("transient error 1"),
            Exception("transient error 2"),
            {"memory": {"memoryId": "retry-store"}},
        ]

        registry = FamilyMemoryStoreRegistry(ddb, ac, TABLE_NAME)

        with patch("app.services.family_memory_registry.time.sleep"):
            sid = registry.provision_family_store("fam-retry")

        assert sid == "retry-store"
        assert ac.create_memory.call_count == 3

    @mock_aws
    def test_all_retries_exhausted_raises(self):
        ddb = boto3.resource("dynamodb", region_name=REGION)
        _create_table(ddb)

        ac = MagicMock()
        ac.create_memory.side_effect = Exception("permanent failure")

        registry = FamilyMemoryStoreRegistry(ddb, ac, TABLE_NAME)

        with patch("app.services.family_memory_registry.time.sleep"):
            with pytest.raises(MemoryStoreProvisioningError) as exc_info:
                registry.provision_family_store("fam-fail")

        assert exc_info.value.family_id == "fam-fail"
        assert ac.create_memory.call_count == 3


# ---------------------------------------------------------------------------
# Cache TTL
# ---------------------------------------------------------------------------


class TestCacheTTL:
    """Tests for the in-memory cache TTL behaviour."""

    @mock_aws
    def test_cache_expires_after_ttl(self):
        ddb = boto3.resource("dynamodb", region_name=REGION)
        _create_table(ddb)
        ac = _make_agentcore_client("cached-store")
        registry = FamilyMemoryStoreRegistry(ddb, ac, TABLE_NAME)

        # Provision to populate cache
        registry.get_store_id("fam-ttl")

        # Manually expire the cache entry
        entry = registry._cache["fam-ttl"]
        entry.cached_at = time.monotonic() - _CACHE_TTL_SECONDS - 1

        # Next call should fall through to DynamoDB (not provision again)
        ac.create_memory.reset_mock()
        sid = registry.get_store_id("fam-ttl")
        assert sid == "cached-store"
        # Should NOT have called create_memory again (DynamoDB has the entry)
        ac.create_memory.assert_not_called()

    @mock_aws
    def test_cache_populated_after_provisioning(self):
        ddb = boto3.resource("dynamodb", region_name=REGION)
        _create_table(ddb)
        ac = _make_agentcore_client("new-cached")
        registry = FamilyMemoryStoreRegistry(ddb, ac, TABLE_NAME)

        registry.provision_family_store("fam-cache")
        assert "fam-cache" in registry._cache
        assert registry._cache["fam-cache"].store_id == "new-cached"
