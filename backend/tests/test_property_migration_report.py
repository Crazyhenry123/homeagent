"""Property-based tests for migration report consistency.

Uses Hypothesis to verify Property 11: Migration Report Consistency.

**Validates: Requirements 5.5, 5.8**

Property 11: Migration Report Consistency — for any migration run,
the MigrationReport's migrated + failed + skipped counts should equal
the total number of distinct family_id values in the shared store.
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

# Family IDs: short alphanumeric strings
_family_id = st.text(
    alphabet=st.characters(whitelist_categories=("Ll", "Nd")),
    min_size=3,
    max_size=15,
)

# Category for each family: already_migrated, new, or failing
_family_category = st.sampled_from(["already_migrated", "new", "failing"])

# A single family entry: (family_id, category)
_family_entry = st.tuples(_family_id, _family_category)

# A set of families with unique IDs and random categories
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


def _seed_already_migrated(table, family_ids: list[str]) -> None:
    """Insert active store entries for families that are already migrated."""
    for fid in family_ids:
        table.put_item(
            Item={
                "family_id": fid,
                "store_id": f"existing-store-{fid}",
                "store_name": f"family_{fid}",
                "status": "active",
                "created_at": "2024-01-01T00:00:00Z",
                "updated_at": "2024-01-01T00:00:00Z",
            }
        )


def _build_shared_records(family_ids: list[str]) -> list[dict]:
    """Build shared-store records — one record per family for simplicity."""
    return [{"family_id": fid, "content": f"rec-{fid}"} for fid in family_ids]


def _make_registry_mock(failing_ids: set[str]):
    """Return a mock registry where provision raises for failing families."""
    registry = MagicMock()
    counter = itertools.count(1)

    def _provision(family_id):
        if family_id in failing_ids:
            raise RuntimeError(f"Provisioning failed for {family_id}")
        return f"store-{next(counter)}"

    registry.provision_family_store.side_effect = _provision
    return registry


def _make_agentcore_client(shared_records: list[dict]):
    """Return a mock AgentCore client that tracks stored records per store."""
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
    return client


# ---------------------------------------------------------------------------
# Property test
# ---------------------------------------------------------------------------


class TestMigrationReportConsistency:
    """Property 11: Migration Report Consistency.

    **Validates: Requirements 5.5, 5.8**
    """

    @given(families=_families)
    @settings(max_examples=50, deadline=None)
    def test_migrated_plus_failed_plus_skipped_equals_total(
        self,
        families: list[tuple[str, str]],
    ) -> None:
        """For any set of families categorised as already_migrated, new,
        or failing, after running the MigrationOrchestrator the report
        must satisfy:

            migrated + failed + skipped == len(distinct family_ids)

        Steps:
        1. Generate random families each tagged as already_migrated,
           new, or failing.
        2. Pre-populate DynamoDB with active entries for already_migrated
           families (so they get skipped).
        3. Configure the registry mock to raise on failing families.
        4. Build shared-store records for all families.
        5. Run the MigrationOrchestrator.
        6. Assert the report totals equal the number of distinct families.
        """
        with mock_aws():
            ddb = boto3.resource("dynamodb", region_name=REGION)
            _create_table(ddb)
            table = ddb.Table(TABLE_NAME)

            # Categorise families
            already_migrated = [fid for fid, cat in families if cat == "already_migrated"]
            failing = {fid for fid, cat in families if cat == "failing"}
            all_family_ids = [fid for fid, _ in families]

            # Seed DynamoDB with already-migrated families
            _seed_already_migrated(table, already_migrated)

            # Build shared records for ALL families (the orchestrator
            # discovers families by scanning the shared store)
            shared_records = _build_shared_records(all_family_ids)

            # Set up mocks
            registry = _make_registry_mock(failing)
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

            # KEY PROPERTY: migrated + failed + skipped == total families
            total = len(all_family_ids)
            actual = report.migrated + report.failed + report.skipped
            assert actual == total, (
                f"Report totals mismatch: "
                f"migrated({report.migrated}) + failed({report.failed}) + "
                f"skipped({report.skipped}) = {actual}, "
                f"expected {total} distinct families. "
                f"Categories: already_migrated={len(already_migrated)}, "
                f"failing={len(failing)}, "
                f"new={total - len(already_migrated) - len(failing)}"
            )
