"""Migrate family memory records from the shared global store to per-family isolated stores.

One-time migration tool that enumerates distinct family_ids from the shared
AgentCore Memory store, provisions per-family dedicated stores via the
FamilyMemoryStoreRegistry, copies records, and verifies counts.

Supports dry-run mode for validation before execution.

Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 5.6, 5.7, 5.8
"""

from __future__ import annotations

import argparse
import logging
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

import boto3

from app.models.agentcore import FamilyMemoryStoresItem
from app.services.family_memory_registry import FamilyMemoryStoreRegistry

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# MigrationReport
# ---------------------------------------------------------------------------


@dataclass
class MigrationReport:
    """Summary of a migration run."""

    migrated: int = 0
    failed: int = 0
    skipped: int = 0


# ---------------------------------------------------------------------------
# MigrationOrchestrator
# ---------------------------------------------------------------------------


class MigrationOrchestrator:
    """Migrates family memory records from a shared store to per-family isolated stores.

    Uses the FamilyMemoryStoreRegistry for store provisioning and lookup,
    and interacts with the shared AgentCore Memory store to enumerate and
    copy records.

    Parameters
    ----------
    registry:
        A :class:`FamilyMemoryStoreRegistry` instance for store lookup
        and provisioning.
    shared_store_id:
        The AgentCore Memory store ID of the shared global family store.
    agentcore_client:
        A ``boto3.client("bedrock-agentcore")`` (or compatible) used for
        memory operations (retrieve and store).
    dynamodb_resource:
        A ``boto3.resource("dynamodb")`` instance for updating store status.
    table_name:
        Override the DynamoDB table name (default ``"FamilyMemoryStores"``).
    """

    def __init__(
        self,
        registry: FamilyMemoryStoreRegistry,
        shared_store_id: str,
        agentcore_client: Any,
        dynamodb_resource: Any,
        table_name: str = "FamilyMemoryStores",
    ) -> None:
        self._registry = registry
        self._shared_store_id = shared_store_id
        self._agentcore = agentcore_client
        self._table = dynamodb_resource.Table(table_name)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def migrate_shared_to_isolated(self, dry_run: bool = False) -> MigrationReport:
        """Run the migration from shared store to per-family isolated stores.

        Algorithm:
        1. Enumerate all records from the shared store.
        2. Extract distinct family_ids.
        3. For each family:
           a. Skip if an active dedicated store already exists.
           b. In dry-run mode, log what would be migrated.
           c. Otherwise, provision a store, copy records, verify counts.
        4. Return a MigrationReport with migrated/failed/skipped counts.

        Parameters
        ----------
        dry_run:
            When True, log what would be migrated without creating stores
            or copying records.

        Returns
        -------
        MigrationReport
            Counts of migrated, failed, and skipped families.
        """
        report = MigrationReport()

        # Step 1: Enumerate all records from the shared store
        all_records = self._scan_shared_store()
        logger.info("Scanned %d total records from shared store", len(all_records))

        # Step 2: Extract distinct family_ids
        family_records_map: dict[str, list[dict]] = {}
        for record in all_records:
            fid = record.get("family_id", "")
            if fid:
                family_records_map.setdefault(fid, []).append(record)

        family_ids = sorted(family_records_map.keys())
        logger.info("Found %d distinct families to process", len(family_ids))

        # Step 3: Process each family
        for fid in family_ids:
            self._process_family(
                fid,
                family_records_map[fid],
                report,
                dry_run,
            )

        logger.info(
            "Migration complete: migrated=%d, failed=%d, skipped=%d",
            report.migrated,
            report.failed,
            report.skipped,
        )
        return report

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _process_family(
        self,
        family_id: str,
        family_records: list[dict],
        report: MigrationReport,
        dry_run: bool,
    ) -> None:
        """Process migration for a single family.

        Handles skip, dry-run, provisioning, copy, and verification.
        On failure, logs the error, increments the failed counter, and
        continues (does not raise).
        """
        # Check if already migrated (active dedicated store)
        existing = self._get_existing_store(family_id)
        if existing is not None and existing.get("status") == "active":
            logger.info(
                "Family %s already has active store %s; skipping",
                family_id,
                existing.get("store_id"),
            )
            report.skipped += 1
            return

        if dry_run:
            logger.info(
                "DRY RUN: Would migrate %d records for %s",
                len(family_records),
                family_id,
            )
            report.migrated += 1
            return

        try:
            # Provision dedicated store
            store_id = self._registry.provision_family_store(family_id)
            logger.info(
                "Provisioned store %s for family %s", store_id, family_id
            )

            # Copy records to dedicated store
            for record in family_records:
                self._store_record(store_id, record)

            # Verify record count
            migrated_count = self._count_records(store_id, family_id)
            expected_count = len(family_records)

            if migrated_count != expected_count:
                logger.warning(
                    "Record count mismatch for family %s: expected %d, got %d; "
                    "marking store as 'migrating'",
                    family_id,
                    expected_count,
                    migrated_count,
                )
                self._update_store_status(family_id, "migrating")

            report.migrated += 1

        except Exception:
            logger.error(
                "Migration failed for family %s",
                family_id,
                exc_info=True,
            )
            report.failed += 1

    def _scan_shared_store(self) -> list[dict]:
        """Enumerate all records from the shared global memory store.

        Calls the AgentCore Memory retrieve/list API to get all records
        from the shared store.

        Returns
        -------
        list[dict]
            All records from the shared store, each containing at least
            a ``family_id`` field.
        """
        try:
            response = self._agentcore.retrieve_memories(
                memoryId=self._shared_store_id,
            )
            return response.get("memories", [])
        except Exception:
            logger.error(
                "Failed to scan shared store %s",
                self._shared_store_id,
                exc_info=True,
            )
            return []

    def _get_existing_store(self, family_id: str) -> dict | None:
        """Look up an existing store entry in the FamilyMemoryStores table."""
        try:
            response = self._table.get_item(Key={"family_id": family_id})
            return response.get("Item")
        except Exception:
            logger.warning(
                "DynamoDB lookup failed for family %s",
                family_id,
                exc_info=True,
            )
            return None

    def _store_record(self, store_id: str, record: dict) -> None:
        """Copy a single record to the dedicated store."""
        self._agentcore.store_memory(
            memoryId=store_id,
            memory=record,
        )

    def _count_records(self, store_id: str, family_id: str) -> int:
        """Retrieve all records from a dedicated store and return the count."""
        try:
            response = self._agentcore.retrieve_memories(
                memoryId=store_id,
            )
            return len(response.get("memories", []))
        except Exception:
            logger.warning(
                "Failed to count records in store %s for family %s",
                store_id,
                family_id,
                exc_info=True,
            )
            return 0

    def _update_store_status(self, family_id: str, status: str) -> None:
        """Update the store status in the FamilyMemoryStores DynamoDB table."""
        now = datetime.now(timezone.utc).isoformat()
        try:
            self._table.update_item(
                Key={"family_id": family_id},
                UpdateExpression="SET #s = :status, updated_at = :ts",
                ExpressionAttributeNames={"#s": "status"},
                ExpressionAttributeValues={
                    ":status": status,
                    ":ts": now,
                },
            )
            logger.info(
                "Updated store status for family %s to '%s'",
                family_id,
                status,
            )
        except Exception:
            logger.error(
                "Failed to update store status for family %s to '%s'",
                family_id,
                status,
                exc_info=True,
            )


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


def main() -> None:
    """CLI entry point for the memory store migration script."""
    parser = argparse.ArgumentParser(
        description="Migrate family memory from shared store to per-family isolated stores"
    )
    parser.add_argument(
        "--shared-store-id",
        required=True,
        help="AgentCore Memory store ID of the shared global family store",
    )
    parser.add_argument(
        "--region",
        default="us-east-1",
        help="AWS region (default: us-east-1)",
    )
    parser.add_argument(
        "--dynamodb-endpoint",
        help="DynamoDB endpoint URL (for local dev)",
    )
    parser.add_argument(
        "--table-name",
        default="FamilyMemoryStores",
        help="FamilyMemoryStores DynamoDB table name (default: FamilyMemoryStores)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview migration without creating stores or copying records",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable debug logging",
    )

    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    # Initialize AWS clients
    ddb_kwargs: dict = {"region_name": args.region}
    if args.dynamodb_endpoint:
        ddb_kwargs["endpoint_url"] = args.dynamodb_endpoint
    dynamodb_resource = boto3.resource("dynamodb", **ddb_kwargs)

    agentcore_client = boto3.client(
        "bedrock-agentcore", region_name=args.region
    )

    registry = FamilyMemoryStoreRegistry(
        dynamodb_resource=dynamodb_resource,
        agentcore_client=agentcore_client,
        table_name=args.table_name,
    )

    orchestrator = MigrationOrchestrator(
        registry=registry,
        shared_store_id=args.shared_store_id,
        agentcore_client=agentcore_client,
        dynamodb_resource=dynamodb_resource,
        table_name=args.table_name,
    )

    report = orchestrator.migrate_shared_to_isolated(dry_run=args.dry_run)

    # Summary
    mode = "DRY RUN " if args.dry_run else ""
    print(
        f"\n{mode}Migration complete: "
        f"{report.migrated} migrated, "
        f"{report.failed} failed, "
        f"{report.skipped} skipped"
    )

    if report.failed > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
