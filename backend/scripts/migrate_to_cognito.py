"""Migrate existing device-token users to Cognito.

For each user in the Users table without a cognito_sub:
1. Create a Cognito user with the user's email
2. Update the Users table with the cognito_sub
3. Preserve all existing conversations, profiles, and health records

Requirements: 19.1, 19.2, 19.3, 19.4
"""

from __future__ import annotations

import argparse
import logging
import sys
from dataclasses import dataclass

import boto3

logger = logging.getLogger(__name__)


@dataclass
class MigrationResult:
    """Result of migrating a single user."""

    user_id: str
    cognito_sub: str | None
    status: str  # "created", "skipped", "error"
    error: str | None = None


def migrate_users_to_cognito(
    user_pool_id: str,
    region: str = "us-east-1",
    dynamodb_endpoint: str | None = None,
    dry_run: bool = False,
) -> list[MigrationResult]:
    """Migrate all users without cognito_sub to Cognito.

    For each user in the Users table:
    - If the user already has a cognito_sub, skip (no re-migration)
    - Otherwise, create a Cognito user with the user's email
    - Update the Users table with the new cognito_sub

    Existing conversations, profiles, and health records are preserved
    because we only update the Users table — no other tables are modified.

    Args:
        user_pool_id: Cognito User Pool ID.
        region: AWS region.
        dynamodb_endpoint: Optional DynamoDB endpoint (for local dev).
        dry_run: If True, log what would happen without making changes.

    Returns:
        List of MigrationResult for each user processed.
    """
    # Initialize clients
    cognito_client = boto3.client("cognito-idp", region_name=region)

    ddb_kwargs: dict = {"region_name": region}
    if dynamodb_endpoint:
        ddb_kwargs["endpoint_url"] = dynamodb_endpoint
    dynamodb = boto3.resource("dynamodb", **ddb_kwargs)
    users_table = dynamodb.Table("Users")

    # Scan all users
    results: list[MigrationResult] = []
    scan_kwargs: dict = {}

    while True:
        response = users_table.scan(**scan_kwargs)
        items = response.get("Items", [])

        for user in items:
            user_id = user["user_id"]

            # Skip users who already have cognito_sub
            if user.get("cognito_sub"):
                logger.info(
                    "User %s already has cognito_sub=%s, skipping",
                    user_id,
                    user["cognito_sub"],
                )
                results.append(
                    MigrationResult(
                        user_id=user_id,
                        cognito_sub=user["cognito_sub"],
                        status="skipped",
                    )
                )
                continue

            email = user.get("email")
            if not email:
                logger.warning("User %s has no email, skipping", user_id)
                results.append(
                    MigrationResult(
                        user_id=user_id,
                        cognito_sub=None,
                        status="error",
                        error="No email address",
                    )
                )
                continue

            if dry_run:
                logger.info("[DRY RUN] Would create Cognito user for %s (%s)", user_id, email)
                results.append(
                    MigrationResult(
                        user_id=user_id,
                        cognito_sub=None,
                        status="dry_run",
                    )
                )
                continue

            # Create Cognito user
            try:
                cognito_sub = _create_cognito_user(
                    cognito_client=cognito_client,
                    user_pool_id=user_pool_id,
                    email=email,
                    user_id=user_id,
                    role=user.get("role", "member"),
                    family_id=user.get("family_id", ""),
                )
            except Exception as e:
                logger.error("Failed to create Cognito user for %s: %s", user_id, e)
                results.append(
                    MigrationResult(
                        user_id=user_id,
                        cognito_sub=None,
                        status="error",
                        error=str(e),
                    )
                )
                continue

            # Update Users table with cognito_sub
            try:
                users_table.update_item(
                    Key={"user_id": user_id},
                    UpdateExpression="SET cognito_sub = :cs",
                    ExpressionAttributeValues={":cs": cognito_sub},
                )
                logger.info(
                    "Migrated user %s -> cognito_sub=%s", user_id, cognito_sub
                )
                results.append(
                    MigrationResult(
                        user_id=user_id,
                        cognito_sub=cognito_sub,
                        status="created",
                    )
                )
            except Exception as e:
                logger.error(
                    "Failed to update Users table for %s: %s", user_id, e
                )
                results.append(
                    MigrationResult(
                        user_id=user_id,
                        cognito_sub=cognito_sub,
                        status="error",
                        error=f"Cognito user created but DynamoDB update failed: {e}",
                    )
                )

        # Handle pagination
        last_key = response.get("LastEvaluatedKey")
        if not last_key:
            break
        scan_kwargs["ExclusiveStartKey"] = last_key

    return results


def _create_cognito_user(
    cognito_client,
    user_pool_id: str,
    email: str,
    user_id: str,
    role: str = "member",
    family_id: str = "",
) -> str:
    """Create a Cognito user and return the cognito_sub (UUID).

    Sets custom attributes for family_id and app_role.
    """
    user_attributes = [
        {"Name": "email", "Value": email},
        {"Name": "email_verified", "Value": "true"},
        {"Name": "custom:app_role", "Value": role},
    ]
    if family_id:
        user_attributes.append({"Name": "custom:family_id", "Value": family_id})

    response = cognito_client.admin_create_user(
        UserPoolId=user_pool_id,
        Username=email,
        UserAttributes=user_attributes,
        MessageAction="SUPPRESS",  # Don't send welcome email during migration
    )

    # Extract the sub attribute
    attrs = response["User"]["Attributes"]
    for attr in attrs:
        if attr["Name"] == "sub":
            return attr["Value"]

    raise RuntimeError(f"Cognito user created but 'sub' attribute not found for {email}")


def main():
    """CLI entry point for the migration script."""
    parser = argparse.ArgumentParser(description="Migrate users to Cognito")
    parser.add_argument("--user-pool-id", required=True, help="Cognito User Pool ID")
    parser.add_argument("--region", default="us-east-1", help="AWS region")
    parser.add_argument("--dynamodb-endpoint", help="DynamoDB endpoint URL")
    parser.add_argument("--dry-run", action="store_true", help="Preview without changes")
    parser.add_argument("--verbose", action="store_true", help="Enable debug logging")

    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    results = migrate_users_to_cognito(
        user_pool_id=args.user_pool_id,
        region=args.region,
        dynamodb_endpoint=args.dynamodb_endpoint,
        dry_run=args.dry_run,
    )

    # Summary
    created = sum(1 for r in results if r.status == "created")
    skipped = sum(1 for r in results if r.status == "skipped")
    errors = sum(1 for r in results if r.status == "error")

    print(f"\nMigration complete: {created} created, {skipped} skipped, {errors} errors")
    if errors:
        for r in results:
            if r.status == "error":
                print(f"  ERROR: {r.user_id} — {r.error}")
        sys.exit(1)


if __name__ == "__main__":
    main()
