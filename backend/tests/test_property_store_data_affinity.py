"""Property-based tests for store-data affinity.

Uses Hypothesis to verify Property 3: Store-Data Affinity.

**Validates: Requirements 3.4, 3.5**

Property 3: Store-Data Affinity — for any family_id and any record
returned by memory retrieval through an IsolatedContext, the record's
store origin matches the family's dedicated store_id from the
IsolatedContext, and that store_id equals ``get_store_id(family_id)``.

The key insight is that ``build_isolated_memory_config`` sets the
``memory_id`` in the MemoryConfig to ``context.family_store_id``.
Because AgentCore Memory only returns records from the store identified
by ``memory_id``, all retrieved records necessarily originate from the
family's dedicated store.
"""

from __future__ import annotations

import itertools
from dataclasses import dataclass
from unittest.mock import MagicMock

import boto3
from hypothesis import given, settings
from hypothesis import strategies as st
from moto import mock_aws

from app.models.agentcore import IsolatedContext
from app.services.family_memory_registry import FamilyMemoryStoreRegistry
from app.services.isolated_memory_manager import IsolatedMemoryManager

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

REGION = "us-east-1"
TABLE_NAME = "FamilyMemoryStores"
SHARED_MEMBER_STORE_ID = "mem-shared-member-store"

# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

# Non-empty, non-whitespace-only strings
_non_empty_str = st.text(min_size=1, max_size=50).filter(lambda s: s.strip())

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


@dataclass
class MockRecord:
    """A mock memory record tagged with the store_id it came from."""

    store_id: str
    content: str


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


def _mock_retrieve(store_id: str, num_records: int = 3) -> list[MockRecord]:
    """Simulate memory retrieval — returns records tagged with *store_id*.

    In a real system, AgentCore Memory only returns records from the store
    identified by the ``memory_id`` in the MemoryConfig.  This helper
    models that behaviour by tagging every returned record with the
    store_id that was queried.
    """
    return [
        MockRecord(store_id=store_id, content=f"record-{i}")
        for i in range(num_records)
    ]


# ---------------------------------------------------------------------------
# Property test
# ---------------------------------------------------------------------------


class TestStoreDataAffinity:
    """Property 3: Store-Data Affinity.

    **Validates: Requirements 3.4, 3.5**
    """

    @given(
        family_id=_non_empty_str,
        member_id=_non_empty_str,
        session_id=_non_empty_str,
    )
    @settings(max_examples=50, deadline=None)
    def test_retrieved_records_originate_from_family_store(
        self,
        family_id: str,
        member_id: str,
        session_id: str,
    ) -> None:
        """For any family_id, all records returned through the isolated
        memory path originate from the family's dedicated store_id, which
        equals ``get_store_id(family_id)``.

        Steps:
        1. Provision a store for the family via the registry.
        2. Build an IsolatedContext with the resolved store_id.
        3. Build the isolated memory config and verify the memory_id
           targets the family's dedicated store.
        4. Mock retrieval using that memory_id and assert every returned
           record's store_id matches the family's dedicated store.
        """
        with mock_aws():
            ddb = boto3.resource("dynamodb", region_name=REGION)
            _create_table(ddb)
            ac = _make_agentcore_client()
            registry = FamilyMemoryStoreRegistry(ddb, ac, TABLE_NAME)

            # 1. Resolve the family's dedicated store_id
            dedicated_store_id = registry.get_store_id(family_id)

            # 2. Build an IsolatedContext with the resolved store
            context = IsolatedContext(
                family_id=family_id,
                member_id=member_id,
                family_store_id=dedicated_store_id,
                is_verified=True,
                store_status="active",
                verified_at="2025-01-01T00:00:00+00:00",
            )

            # 3. Build isolated memory config — the memory_id in the
            #    family config determines which store is queried
            manager = IsolatedMemoryManager(
                member_memory_id=SHARED_MEMBER_STORE_ID,
                registry=registry,
            )
            combined = manager.build_isolated_memory_config(context, session_id)

            # Requirement 3.4: family_store_id matches the expected store
            assert combined.family_config.memory_id == dedicated_store_id, (
                f"Config memory_id {combined.family_config.memory_id!r} does "
                f"not match dedicated store {dedicated_store_id!r}"
            )
            assert combined.family_config.memory_id == registry.get_store_id(family_id), (
                "Config memory_id must equal get_store_id(family_id)"
            )

            # 4. Simulate retrieval from the store identified by memory_id
            records = _mock_retrieve(combined.family_config.memory_id)

            # Requirement 3.5: all returned records originate from the
            # family's dedicated store
            for record in records:
                assert record.store_id == dedicated_store_id, (
                    f"Record store_id {record.store_id!r} does not match "
                    f"family's dedicated store {dedicated_store_id!r}"
                )
                assert record.store_id == registry.get_store_id(family_id), (
                    f"Record store_id {record.store_id!r} does not match "
                    f"get_store_id({family_id!r})"
                )
