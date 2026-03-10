"""Property-based tests for migration completeness.

Uses Hypothesis to verify Property 5: Migration Completeness.

**Validates: Requirements 5.2, 5.3**

Property 5: Migration Completeness — for any set of families with
random record counts in the shared store, after running the
MigrationOrchestrator, each family's dedicated store should contain
exactly the same number of records as the source shared store had
for that family.
"""

from __future__ import annotations

import itertools
from unittest.mock import MagicMock

import boto3
from hypothesis import given, settings
from hypothesis import strategies as st
from moto import mock_aws

from scripts.migrate_memory_stores import MigrationOrchestrator, MigrationReport

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

REGION = "us-east-1"
TABLE_NAME = "FamilyMemoryStores"
SHARED_STORE_ID = "shared-store-id"

# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

# Family IDs: short alphanumeric strings to keep things readable
_family_id = st.text(
    alphabet=st.characters(whitelist_categories=("Ll", "Nd")),
    min_size=3,
    max_size=15,
)

# A single family entry: (family_id, record_count)
_family_entry = st.tuples(
    _family_id,
    st.integers(min_value=1, max_value=10),
)

# A set of families with unique IDs and random record counts
_families = st.lists(
    _family_entry,
    min_size=1,
    max_size=8,
    unique_by=lambda entry: entry[0],
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


def _build_shared_records(families: list[tuple[str, int]]) -> list[dict]:
    """Build a flat list of shared-store records from family entries."""
    records = []
    for family_id, count in families:
        for i in range(count):
            records.append({"family_id": family_id, "content": f"rec-{i}"})
    return records


def _make_registry_mock():
    """Return a mock FamilyMemoryStoreRegistry that provisions unique stores."""
    registry = MagicMock()
    counter = itertools.count(1)

    def _provision(family_id):
        return f"store-{next(counter)}"

    registry.provision_family_store.side_effect = _provision
    return registry


def _make_agentcore_client(shared_records: list[dict]):
    """Return a mock AgentCore client that tracks stored records per store.

    The client's ``retrieve_memories`` returns the shared records when
    queried with the shared store ID, and returns whatever was stored
    via ``store_memory`` for per-family stores.
    """
    client = MagicMock()
    stored: dict[str, list] = {}

    def _retrieve_memories(**kwargs):
        store_id = kwargs.get("memoryId", "")
        if store_id == SHARED_STORE_ID:
            return {"memories": shared_records}
        return {"memories": stored.get(store_id, [])}

    def _store_memory(**kwargs):
        store_id = kwargs.get("memoryId", "")
        record = kwargs.get("memory", {})
        stored.setdefault(store_id, []).append(record)

    client.retrieve_memories.side_effect = _retrieve_memories
    client.store_memory.side_effect = _store_memory
    client._stored = stored
    return client


# ---------------------------------------------------------------------------
# Property test
# ---------------------------------------------------------------------------


class TestMigrationCompleteness:
    """Property 5: Migration Completeness.

    **Validates: Requirements 5.2, 5.3**
    """

    @given(families=_families)
    @settings(max_examples=50, deadline=None)
    def test_each_family_store_has_same_record_count_as_source(
        self,
        families: list[tuple[str, int]],
    ) -> None:
        """For any set of families with random record counts in the shared
        store, after migration each family's dedicated store should contain
        exactly the same number of records as the source.

        Steps:
        1. Generate random families with random record counts.
        2. Build a mock shared store with those records.
        3. Run the MigrationOrchestrator.
        4. Assert each family's dedicated store received exactly the
           same number of records as were in the shared store for that
           family.
        """
        with mock_aws():
            ddb = boto3.resource("dynamodb", region_name=REGION)
            _create_table(ddb)

            # Build shared records from generated families
            shared_records = _build_shared_records(families)
            expected_counts = {fid: count for fid, count in families}

            # Set up mocks
            registry = _make_registry_mock()
            ac = _make_agentcore_client(shared_records)

            # Run migration
            orchestrator = MigrationOrchestrator(
                registry=registry,
                shared_store_id=SHARED_STORE_ID,
                agentcore_client=ac,
                dynamodb_resource=ddb,
                table_name=TABLE_NAME,
            )
            report = orchestrator.migrate_shared_to_isolated()

            # All families should be migrated (none pre-existing)
            assert report.migrated == len(families), (
                f"Expected {len(families)} migrated, got {report.migrated}"
            )
            assert report.failed == 0, (
                f"Expected 0 failures, got {report.failed}"
            )
            assert report.skipped == 0, (
                f"Expected 0 skipped, got {report.skipped}"
            )

            # Verify each family's dedicated store has the correct
            # record count matching the source shared store
            for family_id, expected_count in expected_counts.items():
                # Find the store_id that was provisioned for this family
                # by checking what was stored in the agentcore client
                family_stored = False
                for store_id, records in ac._stored.items():
                    family_records = [
                        r for r in records
                        if r.get("family_id") == family_id
                    ]
                    if family_records:
                        assert len(family_records) == expected_count, (
                            f"Family {family_id!r}: expected {expected_count} "
                            f"records in dedicated store, got "
                            f"{len(family_records)}"
                        )
                        family_stored = True
                        break

                assert family_stored, (
                    f"Family {family_id!r} records were not stored in any "
                    f"dedicated store"
                )
