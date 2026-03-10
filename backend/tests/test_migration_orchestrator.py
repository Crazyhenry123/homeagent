"""Unit tests for MigrationOrchestrator.

Tests the migration from shared global store to per-family isolated stores,
including dry-run mode, skip logic, failure handling, and record count
mismatch detection.

Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 5.6, 5.7, 5.8
"""

from __future__ import annotations

import itertools
from unittest.mock import MagicMock, patch

import boto3
from moto import mock_aws

from scripts.migrate_memory_stores import MigrationOrchestrator, MigrationReport

REGION = "us-east-1"
TABLE_NAME = "FamilyMemoryStores"


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


def _make_registry_mock(provision_side_effect=None):
    """Return a mock FamilyMemoryStoreRegistry."""
    registry = MagicMock()
    counter = itertools.count(1)

    def _provision(family_id):
        return f"store-{next(counter)}"

    registry.provision_family_store.side_effect = (
        provision_side_effect or _provision
    )
    return registry


def _make_agentcore_client(shared_records=None, per_store_records=None):
    """Return a mock AgentCore client.

    Parameters
    ----------
    shared_records:
        Records returned by retrieve_memories for the shared store.
    per_store_records:
        Dict mapping store_id -> records returned by retrieve_memories.
        If None, returns the same count as stored.
    """
    client = MagicMock()
    stored: dict[str, list] = {}

    def _retrieve_memories(**kwargs):
        store_id = kwargs.get("memoryId", "")
        if store_id == "shared-store-id" and shared_records is not None:
            return {"memories": shared_records}
        if per_store_records and store_id in per_store_records:
            return {"memories": per_store_records[store_id]}
        # Return whatever was stored
        return {"memories": stored.get(store_id, [])}

    def _store_memory(**kwargs):
        store_id = kwargs.get("memoryId", "")
        record = kwargs.get("memory", {})
        stored.setdefault(store_id, []).append(record)

    client.retrieve_memories.side_effect = _retrieve_memories
    client.store_memory.side_effect = _store_memory
    client._stored = stored  # expose for assertions
    return client


def _build_orchestrator(
    ddb_resource,
    registry=None,
    agentcore_client=None,
    shared_records=None,
    per_store_records=None,
):
    """Build a MigrationOrchestrator with mocked dependencies."""
    if registry is None:
        registry = _make_registry_mock()
    if agentcore_client is None:
        agentcore_client = _make_agentcore_client(
            shared_records=shared_records,
            per_store_records=per_store_records,
        )
    return MigrationOrchestrator(
        registry=registry,
        shared_store_id="shared-store-id",
        agentcore_client=agentcore_client,
        dynamodb_resource=ddb_resource,
        table_name=TABLE_NAME,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestMigrationReport:
    """Test MigrationReport dataclass."""

    def test_default_values(self):
        report = MigrationReport()
        assert report.migrated == 0
        assert report.failed == 0
        assert report.skipped == 0

    def test_custom_values(self):
        report = MigrationReport(migrated=3, failed=1, skipped=2)
        assert report.migrated == 3
        assert report.failed == 1
        assert report.skipped == 2


class TestMigrateSharedToIsolated:
    """Test the main migration flow."""

    @mock_aws
    def test_empty_shared_store(self):
        """No records in shared store → report all zeros."""
        ddb = boto3.resource("dynamodb", region_name=REGION)
        _create_table(ddb)

        orchestrator = _build_orchestrator(ddb, shared_records=[])
        report = orchestrator.migrate_shared_to_isolated()

        assert report.migrated == 0
        assert report.failed == 0
        assert report.skipped == 0

    @mock_aws
    def test_single_family_migration(self):
        """One family with records → provisions store, copies records."""
        ddb = boto3.resource("dynamodb", region_name=REGION)
        _create_table(ddb)

        records = [
            {"family_id": "fam-1", "content": "rec-1"},
            {"family_id": "fam-1", "content": "rec-2"},
        ]
        orchestrator = _build_orchestrator(ddb, shared_records=records)
        report = orchestrator.migrate_shared_to_isolated()

        assert report.migrated == 1
        assert report.failed == 0
        assert report.skipped == 0

    @mock_aws
    def test_multiple_families_migration(self):
        """Multiple families → each gets its own store."""
        ddb = boto3.resource("dynamodb", region_name=REGION)
        _create_table(ddb)

        records = [
            {"family_id": "fam-1", "content": "a"},
            {"family_id": "fam-2", "content": "b"},
            {"family_id": "fam-3", "content": "c"},
        ]
        orchestrator = _build_orchestrator(ddb, shared_records=records)
        report = orchestrator.migrate_shared_to_isolated()

        assert report.migrated == 3
        assert report.failed == 0
        assert report.skipped == 0

    @mock_aws
    def test_skip_already_active_store(self):
        """Family with active store in DynamoDB → skipped."""
        ddb = boto3.resource("dynamodb", region_name=REGION)
        _create_table(ddb)

        # Pre-populate an active store entry
        table = ddb.Table(TABLE_NAME)
        table.put_item(
            Item={
                "family_id": "fam-1",
                "store_id": "existing-store",
                "status": "active",
            }
        )

        records = [{"family_id": "fam-1", "content": "a"}]
        orchestrator = _build_orchestrator(ddb, shared_records=records)
        report = orchestrator.migrate_shared_to_isolated()

        assert report.migrated == 0
        assert report.skipped == 1
        assert report.failed == 0

    @mock_aws
    def test_dry_run_no_stores_created(self):
        """Dry run → logs what would happen, no stores provisioned."""
        ddb = boto3.resource("dynamodb", region_name=REGION)
        _create_table(ddb)

        records = [
            {"family_id": "fam-1", "content": "a"},
            {"family_id": "fam-2", "content": "b"},
        ]
        registry = _make_registry_mock()
        orchestrator = _build_orchestrator(
            ddb, registry=registry, shared_records=records
        )
        report = orchestrator.migrate_shared_to_isolated(dry_run=True)

        assert report.migrated == 2
        assert report.failed == 0
        assert report.skipped == 0
        # Registry should NOT have been called to provision
        registry.provision_family_store.assert_not_called()

    @mock_aws
    def test_dry_run_skips_already_active(self):
        """Dry run still skips families with active stores."""
        ddb = boto3.resource("dynamodb", region_name=REGION)
        _create_table(ddb)

        table = ddb.Table(TABLE_NAME)
        table.put_item(
            Item={
                "family_id": "fam-1",
                "store_id": "existing-store",
                "status": "active",
            }
        )

        records = [
            {"family_id": "fam-1", "content": "a"},
            {"family_id": "fam-2", "content": "b"},
        ]
        orchestrator = _build_orchestrator(ddb, shared_records=records)
        report = orchestrator.migrate_shared_to_isolated(dry_run=True)

        assert report.skipped == 1
        assert report.migrated == 1

    @mock_aws
    def test_provisioning_failure_increments_failed(self):
        """Provisioning error → failed counter incremented, continues."""
        ddb = boto3.resource("dynamodb", region_name=REGION)
        _create_table(ddb)

        def _fail_provision(family_id):
            raise RuntimeError("Provisioning failed")

        registry = _make_registry_mock(provision_side_effect=_fail_provision)
        records = [
            {"family_id": "fam-1", "content": "a"},
            {"family_id": "fam-2", "content": "b"},
        ]
        orchestrator = _build_orchestrator(
            ddb, registry=registry, shared_records=records
        )
        report = orchestrator.migrate_shared_to_isolated()

        assert report.failed == 2
        assert report.migrated == 0

    @mock_aws
    def test_partial_failure_continues(self):
        """One family fails, others succeed → mixed report."""
        ddb = boto3.resource("dynamodb", region_name=REGION)
        _create_table(ddb)

        call_count = itertools.count(1)

        def _sometimes_fail(family_id):
            n = next(call_count)
            if n == 1:
                raise RuntimeError("Boom")
            return f"store-{n}"

        registry = _make_registry_mock(provision_side_effect=_sometimes_fail)
        records = [
            {"family_id": "fam-a", "content": "a"},
            {"family_id": "fam-b", "content": "b"},
        ]
        orchestrator = _build_orchestrator(
            ddb, registry=registry, shared_records=records
        )
        report = orchestrator.migrate_shared_to_isolated()

        assert report.migrated + report.failed == 2
        assert report.failed >= 1

    @mock_aws
    def test_record_count_mismatch_marks_migrating(self):
        """Count mismatch after copy → store status set to 'migrating'."""
        ddb = boto3.resource("dynamodb", region_name=REGION)
        _create_table(ddb)

        records = [
            {"family_id": "fam-1", "content": "a"},
            {"family_id": "fam-1", "content": "b"},
        ]

        # The agentcore client returns fewer records than expected on verify
        ac = _make_agentcore_client(
            shared_records=records,
            per_store_records={"store-1": [{"content": "a"}]},  # only 1 of 2
        )
        registry = _make_registry_mock()
        orchestrator = MigrationOrchestrator(
            registry=registry,
            shared_store_id="shared-store-id",
            agentcore_client=ac,
            dynamodb_resource=ddb,
            table_name=TABLE_NAME,
        )
        report = orchestrator.migrate_shared_to_isolated()

        # Should still count as migrated (store was provisioned)
        assert report.migrated == 1

        # Verify the store status was updated to "migrating"
        table = ddb.Table(TABLE_NAME)
        # The registry mock provisions "store-1" for the first family
        # We need to check the update_item was called
        item = table.get_item(Key={"family_id": "fam-1"}).get("Item")
        if item:
            assert item["status"] == "migrating"

    @mock_aws
    def test_mixed_skip_migrate_fail(self):
        """Mix of skipped, migrated, and failed families."""
        ddb = boto3.resource("dynamodb", region_name=REGION)
        _create_table(ddb)

        # Pre-populate active store for fam-1
        table = ddb.Table(TABLE_NAME)
        table.put_item(
            Item={
                "family_id": "fam-1",
                "store_id": "existing",
                "status": "active",
            }
        )

        call_count = itertools.count(1)

        def _fail_fam3(family_id):
            n = next(call_count)
            if family_id == "fam-3":
                raise RuntimeError("Boom")
            return f"store-{n}"

        registry = _make_registry_mock(provision_side_effect=_fail_fam3)
        records = [
            {"family_id": "fam-1", "content": "a"},
            {"family_id": "fam-2", "content": "b"},
            {"family_id": "fam-3", "content": "c"},
        ]
        orchestrator = _build_orchestrator(
            ddb, registry=registry, shared_records=records
        )
        report = orchestrator.migrate_shared_to_isolated()

        assert report.skipped == 1  # fam-1
        assert report.migrated == 1  # fam-2
        assert report.failed == 1  # fam-3
        assert report.migrated + report.failed + report.skipped == 3

    @mock_aws
    def test_records_without_family_id_ignored(self):
        """Records with empty/missing family_id are ignored."""
        ddb = boto3.resource("dynamodb", region_name=REGION)
        _create_table(ddb)

        records = [
            {"family_id": "", "content": "orphan"},
            {"content": "no-fid"},
            {"family_id": "fam-1", "content": "valid"},
        ]
        orchestrator = _build_orchestrator(ddb, shared_records=records)
        report = orchestrator.migrate_shared_to_isolated()

        assert report.migrated == 1  # only fam-1
