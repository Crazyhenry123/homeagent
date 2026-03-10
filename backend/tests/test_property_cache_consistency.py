"""Property-based tests for cache consistency.

Uses Hypothesis to verify Property 6: Cache Consistency.

**Validates: Requirements 9.1, 9.3, 2.3**

Property 6: Cache Consistency — for any family_id where the cache contains
an entry, the cached store_id should match the store_id in the
FamilyMemoryStores table.  After provisioning a new store, the cache should
immediately reflect the new mapping.
"""

from __future__ import annotations

import itertools
from unittest.mock import MagicMock

import boto3
from hypothesis import given, settings
from hypothesis import strategies as st
from moto import mock_aws

from app.services.family_memory_registry import FamilyMemoryStoreRegistry

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

REGION = "us-east-1"
TABLE_NAME = "FamilyMemoryStores"

# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

# Non-empty, non-whitespace-only family IDs
_family_id = st.text(min_size=1, max_size=50).filter(lambda s: s.strip())

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


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


def _make_agentcore_client():
    """Return a mock AgentCore client that returns a unique store_id per call."""
    client = MagicMock()
    counter = itertools.count(1)

    def _create_memory(**kwargs):
        uid = next(counter)
        return {"memory": {"memoryId": f"store-{uid}"}}

    client.create_memory.side_effect = _create_memory
    return client


# ---------------------------------------------------------------------------
# Property tests
# ---------------------------------------------------------------------------


class TestCacheConsistency:
    """Property 6: Cache Consistency.

    **Validates: Requirements 9.1, 9.3, 2.3**
    """

    @given(family_id=_family_id)
    @settings(max_examples=50, deadline=None)
    def test_cache_matches_dynamodb_after_provisioning(
        self, family_id: str
    ) -> None:
        """After provisioning, the cache entry's store_id matches the
        DynamoDB entry's store_id for the same family_id."""
        with mock_aws():
            ddb = boto3.resource("dynamodb", region_name=REGION)
            _create_table(ddb)
            ac = _make_agentcore_client()
            registry = FamilyMemoryStoreRegistry(ddb, ac, TABLE_NAME)

            # Provision the store (populates both DynamoDB and cache)
            store_id = registry.provision_family_store(family_id)

            # Read the DynamoDB entry directly
            table = ddb.Table(TABLE_NAME)
            dynamo_item = table.get_item(Key={"family_id": family_id})["Item"]

            # Read the cache entry directly
            cache_entry = registry._cache.get(family_id)

            # Cache must be populated
            assert cache_entry is not None, (
                f"Cache was not populated after provisioning family {family_id!r}"
            )

            # Cached store_id must match DynamoDB store_id
            assert cache_entry.store_id == dynamo_item["store_id"], (
                f"Cache store_id ({cache_entry.store_id!r}) does not match "
                f"DynamoDB store_id ({dynamo_item['store_id']!r}) "
                f"for family {family_id!r}"
            )

            # Both must match the returned store_id
            assert store_id == cache_entry.store_id, (
                f"Returned store_id ({store_id!r}) does not match "
                f"cached store_id ({cache_entry.store_id!r})"
            )

    @given(family_id=_family_id)
    @settings(max_examples=50, deadline=None)
    def test_cache_populated_immediately_after_provisioning(
        self, family_id: str
    ) -> None:
        """The cache is populated immediately after provisioning — no
        delay or separate step required."""
        with mock_aws():
            ddb = boto3.resource("dynamodb", region_name=REGION)
            _create_table(ddb)
            ac = _make_agentcore_client()
            registry = FamilyMemoryStoreRegistry(ddb, ac, TABLE_NAME)

            # Cache must be empty before provisioning
            assert family_id not in registry._cache, (
                f"Cache unexpectedly contained entry for {family_id!r} "
                "before provisioning"
            )

            store_id = registry.provision_family_store(family_id)

            # Cache must be populated immediately after provisioning
            assert family_id in registry._cache, (
                f"Cache not populated immediately after provisioning "
                f"family {family_id!r}"
            )

            # Cached value must be the provisioned store_id
            assert registry._cache[family_id].store_id == store_id, (
                f"Cached store_id does not match provisioned store_id "
                f"for family {family_id!r}"
            )
