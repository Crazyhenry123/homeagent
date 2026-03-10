"""Property-based tests for store isolation guarantee.

Uses Hypothesis to verify Property 1: Store Isolation Guarantee.

**Validates: Requirement 2.7**

Property 1: Store Isolation Guarantee — for any two distinct family_id
values family_a and family_b, calling ``get_store_id`` on each should
return different store_id values.  No two families ever share a memory
store.
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

# Pairs of *distinct* family IDs
_distinct_family_pair = (
    st.tuples(_family_id, _family_id)
    .filter(lambda pair: pair[0].strip() != pair[1].strip())
)

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
# Property test
# ---------------------------------------------------------------------------


class TestStoreIsolationGuarantee:
    """Property 1: Store Isolation Guarantee.

    **Validates: Requirement 2.7**
    """

    @given(pair=_distinct_family_pair)
    @settings(max_examples=50, deadline=None)
    def test_distinct_families_get_distinct_stores(
        self, pair: tuple[str, str]
    ) -> None:
        """For any two distinct family_id values, get_store_id returns
        different store_id values."""
        family_a, family_b = pair

        with mock_aws():
            ddb = boto3.resource("dynamodb", region_name=REGION)
            _create_table(ddb)
            ac = _make_agentcore_client()
            registry = FamilyMemoryStoreRegistry(ddb, ac, TABLE_NAME)

            store_a = registry.get_store_id(family_a)
            store_b = registry.get_store_id(family_b)

            assert store_a != store_b, (
                f"Families {family_a!r} and {family_b!r} must not share "
                f"a store, but both resolved to {store_a!r}"
            )
