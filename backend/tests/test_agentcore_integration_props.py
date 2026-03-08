"""Property-based tests for AgentCore Integration module.

**Property 2: Dynamic Sub-Agent Addition/Removal**
After add, next session includes routing tool; after remove, next session
excludes it; gateway tool not deleted on removal.

**Validates: Requirements 5.1, 5.3, 8.4, 27.2**

**Property 15: Migration Data Integrity**
After migration, each user's cognito_sub maps to exactly one Cognito user;
Users table updated; existing data preserved; no re-migration of
already-migrated users.

**Validates: Requirements 19.1, 19.2, 19.3, 19.4**
"""

from __future__ import annotations

import string

import boto3
import pytest
from hypothesis import given, settings, assume
from hypothesis import strategies as st
from moto import mock_aws

from app.models.dynamo import TABLE_DEFINITIONS
from app.services.agent_management import AgentManagementClient
from app.services.agentcore_gateway import AgentCoreGatewayManager
from app.services.agentcore_integration import (
    add_sub_agent_for_user,
    remove_sub_agent_for_user,
)

REGION = "us-east-1"

# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

_SLUG_FIRST = st.sampled_from(list(string.ascii_lowercase))
_SLUG_REST = st.text(
    alphabet=string.ascii_lowercase + string.digits + "_",
    min_size=1,
    max_size=15,
)
valid_agent_type = st.builds(lambda f, r: f + r, _SLUG_FIRST, _SLUG_REST)

user_id_strategy = st.builds(
    lambda prefix, suffix: f"user_{prefix}{suffix}",
    st.sampled_from(list(string.ascii_lowercase)),
    st.text(alphabet=string.ascii_lowercase + string.digits, min_size=1, max_size=8),
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _create_tables():
    """Create AgentTemplates and AgentConfigs tables in mocked DynamoDB."""
    dynamodb = boto3.resource("dynamodb", region_name=REGION)
    for table_name in ("AgentTemplates", "AgentConfigs"):
        schema = TABLE_DEFINITIONS[table_name]
        params = {
            "TableName": table_name,
            "KeySchema": schema["KeySchema"],
            "AttributeDefinitions": schema["AttributeDefinitions"],
            "BillingMode": "PAY_PER_REQUEST",
        }
        if "GlobalSecondaryIndexes" in schema:
            params["GlobalSecondaryIndexes"] = schema["GlobalSecondaryIndexes"]
        dynamodb.create_table(**params)


# ---------------------------------------------------------------------------
# Property 2: Dynamic Sub-Agent Addition/Removal
# ---------------------------------------------------------------------------


class TestDynamicSubAgentAddRemove:
    """Property 2: Dynamic Sub-Agent Addition/Removal.

    **Validates: Requirements 5.1, 5.3, 8.4, 27.2**
    """

    @settings(max_examples=10, deadline=None)
    @given(
        agent_type=valid_agent_type,
        user_id=user_id_strategy,
    )
    def test_add_then_resolve_includes_tool(self, agent_type: str, user_id: str):
        """After add_sub_agent_for_user, build_sub_agent_tool_ids includes
        the routing tool for the added agent_type."""
        with mock_aws():
            _create_tables()
            mgmt = AgentManagementClient(region=REGION)
            gw = AgentCoreGatewayManager(region=REGION)

            # Create a template for this agent_type
            mgmt.create_agent_template(
                name=f"Test {agent_type}",
                agent_type=agent_type,
                description="test agent",
                system_prompt="You are a test agent.",
                available_to="all",
            )

            # Add sub-agent for user
            add_sub_agent_for_user(
                agent_mgmt=mgmt,
                gateway=gw,
                user_id=user_id,
                agent_type=agent_type,
            )

            # Resolve tool IDs — should include the new agent
            tool_ids = mgmt.build_sub_agent_tool_ids(user_id)
            assert len(tool_ids) >= 1
            # The gateway_tool_id should be present
            config = mgmt.get_user_agent_config(user_id, agent_type)
            assert config is not None
            assert config.gateway_tool_id in tool_ids

    @settings(max_examples=10, deadline=None)
    @given(
        agent_type=valid_agent_type,
        user_id=user_id_strategy,
    )
    def test_remove_then_resolve_excludes_tool(self, agent_type: str, user_id: str):
        """After remove_sub_agent_for_user, build_sub_agent_tool_ids excludes
        the routing tool for the removed agent_type."""
        with mock_aws():
            _create_tables()
            mgmt = AgentManagementClient(region=REGION)
            gw = AgentCoreGatewayManager(region=REGION)

            # Create template and add sub-agent
            mgmt.create_agent_template(
                name=f"Test {agent_type}",
                agent_type=agent_type,
                description="test agent",
                system_prompt="You are a test agent.",
                available_to="all",
            )
            add_sub_agent_for_user(
                agent_mgmt=mgmt,
                gateway=gw,
                user_id=user_id,
                agent_type=agent_type,
            )

            # Verify it's there
            tool_ids_before = mgmt.build_sub_agent_tool_ids(user_id)
            assert len(tool_ids_before) >= 1

            # Remove sub-agent
            removed = remove_sub_agent_for_user(
                agent_mgmt=mgmt,
                user_id=user_id,
                agent_type=agent_type,
            )
            assert removed is True

            # Resolve tool IDs — should NOT include the removed agent
            tool_ids_after = mgmt.build_sub_agent_tool_ids(user_id)
            config = mgmt.get_user_agent_config(user_id, agent_type)
            assert config is None
            # The gateway_tool_id from before should not be in the list
            for tid in tool_ids_before:
                assert tid not in tool_ids_after

    @settings(max_examples=10, deadline=None)
    @given(
        agent_type=valid_agent_type,
        user_id=user_id_strategy,
    )
    def test_gateway_tool_not_deleted_on_removal(
        self, agent_type: str, user_id: str
    ):
        """Gateway routing tool is NOT deleted when a sub-agent is removed
        (other users may still reference it)."""
        with mock_aws():
            _create_tables()
            mgmt = AgentManagementClient(region=REGION)
            gw = AgentCoreGatewayManager(region=REGION)

            # Create template and add sub-agent
            mgmt.create_agent_template(
                name=f"Test {agent_type}",
                agent_type=agent_type,
                description="test agent",
                system_prompt="You are a test agent.",
                available_to="all",
            )
            add_sub_agent_for_user(
                agent_mgmt=mgmt,
                gateway=gw,
                user_id=user_id,
                agent_type=agent_type,
            )

            # Verify gateway has the routing tool
            routing_tools_before = gw.get_orchestrator_tools([agent_type])
            assert len(routing_tools_before) >= 1

            # Remove sub-agent
            remove_sub_agent_for_user(
                agent_mgmt=mgmt,
                user_id=user_id,
                agent_type=agent_type,
            )

            # Gateway routing tool should still exist
            routing_tools_after = gw.get_orchestrator_tools([agent_type])
            assert len(routing_tools_after) == len(routing_tools_before)


# ---------------------------------------------------------------------------
# Property 15: Migration Data Integrity
# ---------------------------------------------------------------------------

import sys
import os

# Add scripts directory to path for import
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

from migrate_to_cognito import migrate_users_to_cognito  # noqa: E402


class TestMigrationDataIntegrity:
    """Property 15: Migration Data Integrity.

    After migration, each user's cognito_sub maps to exactly one Cognito
    user; Users table updated; existing data preserved; no re-migration
    of already-migrated users.

    **Validates: Requirements 19.1, 19.2, 19.3, 19.4**
    """

    @settings(max_examples=10, deadline=None)
    @given(
        user_ids=st.lists(
            user_id_strategy,
            min_size=1,
            max_size=5,
            unique=True,
        ),
    )
    def test_migration_creates_cognito_users_and_updates_table(
        self, user_ids: list[str]
    ):
        """Each user without cognito_sub gets a Cognito user created and
        the Users table is updated with the cognito_sub."""
        with mock_aws():
            # Create Users table
            dynamodb = boto3.resource("dynamodb", region_name=REGION)
            schema = TABLE_DEFINITIONS["Users"]
            params = {
                "TableName": "Users",
                "KeySchema": schema["KeySchema"],
                "AttributeDefinitions": schema["AttributeDefinitions"],
                "BillingMode": "PAY_PER_REQUEST",
            }
            if "GlobalSecondaryIndexes" in schema:
                params["GlobalSecondaryIndexes"] = schema["GlobalSecondaryIndexes"]
            dynamodb.create_table(**params)

            # Create Cognito User Pool
            cognito_client = boto3.client("cognito-idp", region_name=REGION)
            pool = cognito_client.create_user_pool(
                PoolName="test-pool",
                Schema=[
                    {"Name": "email", "AttributeDataType": "String", "Required": True},
                ],
            )
            pool_id = pool["UserPool"]["Id"]

            # Insert users without cognito_sub
            users_table = dynamodb.Table("Users")
            for uid in user_ids:
                users_table.put_item(
                    Item={
                        "user_id": uid,
                        "name": f"User {uid}",
                        "email": f"{uid}@example.com",
                        "role": "member",
                    }
                )

            # Run migration
            results = migrate_users_to_cognito(
                user_pool_id=pool_id,
                region=REGION,
            )

            # Verify: each user should have status "created"
            created = [r for r in results if r.status == "created"]
            assert len(created) == len(user_ids)

            # Verify: Users table updated with cognito_sub
            for uid in user_ids:
                item = users_table.get_item(Key={"user_id": uid}).get("Item")
                assert item is not None
                assert "cognito_sub" in item
                assert item["cognito_sub"]  # non-empty

            # Verify: each cognito_sub is unique
            subs = [r.cognito_sub for r in created]
            assert len(set(subs)) == len(subs)

    @settings(max_examples=10, deadline=None)
    @given(
        user_id=user_id_strategy,
    )
    def test_already_migrated_users_not_re_migrated(self, user_id: str):
        """Users who already have a cognito_sub are skipped."""
        with mock_aws():
            # Create Users table
            dynamodb = boto3.resource("dynamodb", region_name=REGION)
            schema = TABLE_DEFINITIONS["Users"]
            params = {
                "TableName": "Users",
                "KeySchema": schema["KeySchema"],
                "AttributeDefinitions": schema["AttributeDefinitions"],
                "BillingMode": "PAY_PER_REQUEST",
            }
            if "GlobalSecondaryIndexes" in schema:
                params["GlobalSecondaryIndexes"] = schema["GlobalSecondaryIndexes"]
            dynamodb.create_table(**params)

            # Create Cognito User Pool
            cognito_client = boto3.client("cognito-idp", region_name=REGION)
            pool = cognito_client.create_user_pool(
                PoolName="test-pool",
                Schema=[
                    {"Name": "email", "AttributeDataType": "String", "Required": True},
                ],
            )
            pool_id = pool["UserPool"]["Id"]

            # Insert user WITH cognito_sub already set
            users_table = dynamodb.Table("Users")
            existing_sub = "existing-sub-12345"
            users_table.put_item(
                Item={
                    "user_id": user_id,
                    "name": f"User {user_id}",
                    "email": f"{user_id}@example.com",
                    "role": "member",
                    "cognito_sub": existing_sub,
                }
            )

            # Run migration
            results = migrate_users_to_cognito(
                user_pool_id=pool_id,
                region=REGION,
            )

            # Verify: user should be skipped
            assert len(results) == 1
            assert results[0].status == "skipped"
            assert results[0].cognito_sub == existing_sub

            # Verify: Users table unchanged
            item = users_table.get_item(Key={"user_id": user_id}).get("Item")
            assert item["cognito_sub"] == existing_sub

    @settings(max_examples=10, deadline=None)
    @given(
        user_id=user_id_strategy,
    )
    def test_existing_data_preserved_after_migration(self, user_id: str):
        """Existing conversations, profiles, and health records are preserved
        (only Users table is updated with cognito_sub)."""
        with mock_aws():
            # Create tables
            dynamodb = boto3.resource("dynamodb", region_name=REGION)
            for table_name in ("Users", "Conversations", "MemberProfiles"):
                schema = TABLE_DEFINITIONS[table_name]
                params = {
                    "TableName": table_name,
                    "KeySchema": schema["KeySchema"],
                    "AttributeDefinitions": schema["AttributeDefinitions"],
                    "BillingMode": "PAY_PER_REQUEST",
                }
                if "GlobalSecondaryIndexes" in schema:
                    params["GlobalSecondaryIndexes"] = schema["GlobalSecondaryIndexes"]
                dynamodb.create_table(**params)

            # Create Cognito User Pool
            cognito_client = boto3.client("cognito-idp", region_name=REGION)
            pool = cognito_client.create_user_pool(
                PoolName="test-pool",
                Schema=[
                    {"Name": "email", "AttributeDataType": "String", "Required": True},
                ],
            )
            pool_id = pool["UserPool"]["Id"]

            # Insert user
            users_table = dynamodb.Table("Users")
            users_table.put_item(
                Item={
                    "user_id": user_id,
                    "name": f"User {user_id}",
                    "email": f"{user_id}@example.com",
                    "role": "admin",
                }
            )

            # Insert a conversation
            conv_table = dynamodb.Table("Conversations")
            conv_id = f"conv_{user_id}_001"
            conv_table.put_item(
                Item={
                    "conversation_id": conv_id,
                    "user_id": user_id,
                    "title": "Test conversation",
                    "updated_at": "2025-01-01T00:00:00Z",
                }
            )

            # Insert a profile
            profile_table = dynamodb.Table("MemberProfiles")
            profile_table.put_item(
                Item={
                    "user_id": user_id,
                    "display_name": "Test User",
                }
            )

            # Run migration
            results = migrate_users_to_cognito(
                user_pool_id=pool_id,
                region=REGION,
            )
            assert results[0].status == "created"

            # Verify: conversation preserved
            conv = conv_table.get_item(Key={"conversation_id": conv_id}).get("Item")
            assert conv is not None
            assert conv["user_id"] == user_id
            assert conv["title"] == "Test conversation"

            # Verify: profile preserved
            profile = profile_table.get_item(Key={"user_id": user_id}).get("Item")
            assert profile is not None
            assert profile["display_name"] == "Test User"

            # Verify: user record preserved with cognito_sub added
            user = users_table.get_item(Key={"user_id": user_id}).get("Item")
            assert user["name"] == f"User {user_id}"
            assert user["role"] == "admin"
            assert "cognito_sub" in user
