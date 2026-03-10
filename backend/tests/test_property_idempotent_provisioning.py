"""Property-based tests for idempotent provisioning.

Uses Hypothesis to verify Property 4: Idempotent Provisioning.

**Validates: Requirements 2.4, 2.6**

Property 4: Idempotent Provisioning — for any family_id, calling
``get_store_id`` multiple times should always return the same store_id.
Provisioning is idempotent — concurrent or repeated calls never create
duplicate stores.
"""

from __future__ import annotations

import itertools
import threading
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
    """Return a mock AgentCore client that returns a unique store_id per call.

    Uses a counter so each ``create_memory`` invocation returns a distinct
    store_id.  This lets the test verify that only the first call actually
    provisions — subsequent calls must return the same store_id from cache
    or DynamoDB, not a new one.
    """
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


class TestIdempotentProvisioning:
    """Property 4: Idempotent Provisioning.

    **Validates: Requirements 2.4, 2.6**
    """

    @given(family_id=_family_id)
    @settings(max_examples=50, deadline=None)
    def test_repeated_get_store_id_returns_same_value(
        self, family_id: str
    ) -> None:
        """For any family_id, calling get_store_id multiple times always
        returns the same store_id."""
        with mock_aws():
            ddb = boto3.resource("dynamodb", region_name=REGION)
            _create_table(ddb)
            ac = _make_agentcore_client()
            registry = FamilyMemoryStoreRegistry(ddb, ac, TABLE_NAME)

            first = registry.get_store_id(family_id)
            second = registry.get_store_id(family_id)
            third = registry.get_store_id(family_id)

            assert first == second == third, (
                f"get_store_id({family_id!r}) returned different values "
                f"across calls: {first!r}, {second!r}, {third!r}"
            )

    @given(family_id=_family_id)
    @settings(max_examples=50, deadline=None)
    def test_concurrent_get_store_id_returns_same_value(
        self, family_id: str
    ) -> None:
        """Simulate concurrent calls to get_store_id using threading.

        All threads must resolve to the same store_id, verifying that
        the conditional write (attribute_not_exists) prevents duplicate
        store provisioning.
        """
        num_threads = 5

        with mock_aws():
            ddb = boto3.resource("dynamodb", region_name=REGION)
            _create_table(ddb)
            ac = _make_agentcore_client()
            registry = FamilyMemoryStoreRegistry(ddb, ac, TABLE_NAME)

            results: list[str | None] = [None] * num_threads
            errors: list[Exception | None] = [None] * num_threads
            barrier = threading.Barrier(num_threads)

            def _worker(idx: int) -> None:
                try:
                    barrier.wait(timeout=5)
                    results[idx] = registry.get_store_id(family_id)
                except Exception as exc:
                    errors[idx] = exc

            threads = [
                threading.Thread(target=_worker, args=(i,))
                for i in range(num_threads)
            ]
            for t in threads:
                t.start()
            for t in threads:
                t.join(timeout=30)

            # Check no thread raised an exception
            for i, err in enumerate(errors):
                assert err is None, (
                    f"Thread {i} raised an exception: {err}"
                )

            # All results must be the same store_id
            unique_ids = set(results)
            assert len(unique_ids) == 1, (
                f"Concurrent get_store_id({family_id!r}) returned "
                f"multiple store_ids: {unique_ids}"
            )
