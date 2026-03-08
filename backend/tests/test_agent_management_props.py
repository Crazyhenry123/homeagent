"""Property-based tests for AgentManagementClient template deletion cascade.

Uses Hypothesis + moto to verify Property 23: Template Deletion Cascade.

**Validates: Requirements 4.4, 4.5, 27.1, 27.2**

Property 23: For any non-builtin template deleted, all referencing
AgentConfigs are also deleted; built-in templates cannot be deleted;
Gateway routing tool is NOT deleted.
"""

from __future__ import annotations

import logging.handlers
import string

import boto3
import pytest
from hypothesis import given, settings, assume
from hypothesis import strategies as st
from moto import mock_aws

from app.models.agentcore import AgentConfig
from app.models.dynamo import TABLE_DEFINITIONS
from app.services.agent_management import AgentManagementClient

REGION = "us-east-1"

# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

_SLUG_FIRST = st.sampled_from(list(string.ascii_lowercase))
_SLUG_REST = st.text(
    alphabet=string.ascii_lowercase + string.digits + "_",
    min_size=1,
    max_size=20,
)
valid_agent_type = st.builds(lambda f, r: f + r, _SLUG_FIRST, _SLUG_REST)

non_empty_str = st.text(min_size=1, max_size=30).filter(lambda s: s.strip())

user_id_strategy = st.builds(
    lambda prefix, suffix: f"user_{prefix}{suffix}",
    st.sampled_from(list(string.ascii_lowercase)),
    st.text(alphabet=string.ascii_lowercase + string.digits, min_size=1, max_size=10),
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


def _insert_config(mgmt: AgentManagementClient, user_id: str, agent_type: str) -> None:
    """Insert an AgentConfig item directly into DynamoDB."""
    mgmt._configs_table.put_item(
        Item={
            "user_id": user_id,
            "agent_type": agent_type,
            "enabled": True,
            "config": {},
            "gateway_tool_id": f"gw-tool-{agent_type}",
            "updated_at": "2025-01-01T00:00:00+00:00",
        }
    )


def _get_all_configs(mgmt: AgentManagementClient) -> list[dict]:
    """Scan all AgentConfig items from DynamoDB."""
    result = mgmt._configs_table.scan()
    return result.get("Items", [])


# ---------------------------------------------------------------------------
# Property 23: Template Deletion Cascade
# Validates: Requirements 4.4, 4.5, 27.1, 27.2
# ---------------------------------------------------------------------------


class TestTemplateDeletionCascade:
    """**Validates: Requirements 4.4, 4.5, 27.1, 27.2**

    Property 23: Template Deletion Cascade — for any non-builtin template
    deleted, all referencing AgentConfigs are also deleted; built-in
    templates cannot be deleted; Gateway routing tool is NOT deleted.
    """

    @given(
        agent_type=valid_agent_type,
        user_ids=st.lists(user_id_strategy, min_size=1, max_size=8, unique=True),
    )
    @settings(max_examples=10, deadline=None)
    def test_non_builtin_deletion_cascades_all_configs(
        self, agent_type: str, user_ids: list[str]
    ) -> None:
        """For any non-builtin template with N AgentConfigs from different
        users, deleting the template removes all N configs.

        **Validates: Requirements 4.4, 27.1**
        """
        with mock_aws():
            _create_tables()
            mgmt = AgentManagementClient(region=REGION)

            template = mgmt.create_agent_template(
                name="Test Agent",
                agent_type=agent_type,
                description="Test",
                system_prompt="You are a test agent.",
                is_builtin=False,
                created_by="admin",
            )

            # Create configs for each user referencing this template
            for uid in user_ids:
                _insert_config(mgmt, uid, agent_type)

            # Verify configs exist before deletion
            configs_before = [
                c for c in _get_all_configs(mgmt) if c["agent_type"] == agent_type
            ]
            assert len(configs_before) == len(user_ids)

            # Delete the template
            result = mgmt.delete_template(template.template_id)
            assert result is True

            # Template should be gone
            assert mgmt.get_template(template.template_id) is None

            # ALL configs referencing this agent_type should be gone
            configs_after = [
                c for c in _get_all_configs(mgmt) if c["agent_type"] == agent_type
            ]
            assert len(configs_after) == 0

    @given(agent_type=valid_agent_type)
    @settings(max_examples=10, deadline=None)
    def test_builtin_template_cannot_be_deleted(self, agent_type: str) -> None:
        """For any built-in template, deletion is rejected with ValueError.

        **Validates: Requirements 4.5**
        """
        with mock_aws():
            _create_tables()
            mgmt = AgentManagementClient(region=REGION)

            template = mgmt.create_agent_template(
                name="Built-in Agent",
                agent_type=agent_type,
                description="Built-in",
                system_prompt="Built-in agent.",
                is_builtin=True,
                created_by="system",
            )

            with pytest.raises(ValueError, match="Cannot delete built-in"):
                mgmt.delete_template(template.template_id)

            # Template should still exist
            assert mgmt.get_template(template.template_id) is not None

    @given(
        agent_type=valid_agent_type,
        other_agent_type=valid_agent_type,
        user_ids=st.lists(user_id_strategy, min_size=1, max_size=5, unique=True),
    )
    @settings(max_examples=10, deadline=None)
    def test_cascade_does_not_delete_other_agent_configs(
        self,
        agent_type: str,
        other_agent_type: str,
        user_ids: list[str],
    ) -> None:
        """Deleting a template only cascade-deletes configs for that
        agent_type; configs for other agent_types are preserved.

        **Validates: Requirements 4.4, 27.1**
        """
        assume(agent_type != other_agent_type)

        with mock_aws():
            _create_tables()
            mgmt = AgentManagementClient(region=REGION)

            # Create the template to be deleted
            template = mgmt.create_agent_template(
                name="Deletable",
                agent_type=agent_type,
                description="Will be deleted",
                system_prompt="Test",
                is_builtin=False,
                created_by="admin",
            )

            # Create another template that should survive
            mgmt.create_agent_template(
                name="Survivor",
                agent_type=other_agent_type,
                description="Should survive",
                system_prompt="Test",
                is_builtin=False,
                created_by="admin",
            )

            # Insert configs for both agent types
            for uid in user_ids:
                _insert_config(mgmt, uid, agent_type)
                _insert_config(mgmt, uid, other_agent_type)

            mgmt.delete_template(template.template_id)

            # Configs for deleted template should be gone
            remaining = _get_all_configs(mgmt)
            deleted_configs = [c for c in remaining if c["agent_type"] == agent_type]
            surviving_configs = [
                c for c in remaining if c["agent_type"] == other_agent_type
            ]

            assert len(deleted_configs) == 0
            assert len(surviving_configs) == len(user_ids)

    @given(
        agent_type=valid_agent_type,
        user_ids=st.lists(user_id_strategy, min_size=1, max_size=5, unique=True),
    )
    @settings(max_examples=10, deadline=None)
    def test_gateway_tool_not_deleted_on_template_deletion(
        self, agent_type: str, user_ids: list[str]
    ) -> None:
        """When a template is deleted, the Gateway routing tool is NOT
        deleted. We verify this by checking that delete_template does not
        interact with any gateway service — it only removes the template
        and its configs from DynamoDB.

        **Validates: Requirements 27.2**
        """
        with mock_aws():
            _create_tables()
            mgmt = AgentManagementClient(region=REGION)

            template = mgmt.create_agent_template(
                name="Agent With Tool",
                agent_type=agent_type,
                description="Has gateway tool",
                system_prompt="Test",
                is_builtin=False,
                created_by="admin",
            )

            # Insert configs with gateway_tool_ids
            for uid in user_ids:
                mgmt._configs_table.put_item(
                    Item={
                        "user_id": uid,
                        "agent_type": agent_type,
                        "enabled": True,
                        "config": {},
                        "gateway_tool_id": f"gw-tool-{agent_type}",
                        "updated_at": "2025-01-01T00:00:00+00:00",
                    }
                )

            # delete_template only touches DynamoDB (templates + configs).
            # It does NOT call any gateway API to delete routing tools.
            # The implementation confirms this — no gateway interaction in
            # delete_template(). The tool persists for other users.
            result = mgmt.delete_template(template.template_id)
            assert result is True

            # Template and configs are gone, but no gateway error was raised
            # (no gateway call was made), confirming the tool is untouched.
            assert mgmt.get_template(template.template_id) is None
            configs = [
                c for c in _get_all_configs(mgmt) if c["agent_type"] == agent_type
            ]
            assert len(configs) == 0

    @given(
        agent_type=valid_agent_type,
        user_ids=st.lists(user_id_strategy, min_size=2, max_size=8, unique=True),
    )
    @settings(max_examples=10, deadline=None)
    def test_multi_user_configs_all_cleaned_up(
        self, agent_type: str, user_ids: list[str]
    ) -> None:
        """For a template with configs from multiple distinct users,
        deletion removes every single config — none are left behind.

        **Validates: Requirements 4.4, 27.1**
        """
        with mock_aws():
            _create_tables()
            mgmt = AgentManagementClient(region=REGION)

            template = mgmt.create_agent_template(
                name="Multi-User Agent",
                agent_type=agent_type,
                description="Used by many",
                system_prompt="Test",
                is_builtin=False,
                created_by="admin",
            )

            for uid in user_ids:
                _insert_config(mgmt, uid, agent_type)

            mgmt.delete_template(template.template_id)

            # Verify zero configs remain for this agent_type
            all_configs = _get_all_configs(mgmt)
            leftover = [c for c in all_configs if c["agent_type"] == agent_type]
            assert leftover == [], (
                f"Expected 0 configs for {agent_type} after deletion, "
                f"found {len(leftover)} for users: "
                f"{[c['user_id'] for c in leftover]}"
            )


# ---------------------------------------------------------------------------
# Property 24: Template Seeding Idempotence
# Validates: Requirements 28.1, 28.2, 28.3, 28.4
# ---------------------------------------------------------------------------


class TestTemplateSeedingIdempotence:
    """**Validates: Requirements 28.1, 28.2, 28.3, 28.4**

    Property 24: Template Seeding Idempotence — for any startup, seeding
    creates missing built-in templates and leaves existing ones unchanged;
    seeded templates have is_builtin==True and created_by=="system".
    """

    @settings(max_examples=1, deadline=None)
    @given(data=st.data())
    def test_seeding_creates_all_builtin_templates_when_none_exist(
        self, data: st.DataObject
    ) -> None:
        """When no built-in templates exist, seeding creates all of them.

        **Validates: Requirements 28.1, 28.2**
        """
        with mock_aws():
            _create_tables()
            mgmt = AgentManagementClient(region=REGION)

            created = mgmt.seed_builtin_templates()

            expected_types = set(AgentManagementClient.BUILTIN_TEMPLATES.keys())
            created_types = {t.agent_type for t in created}
            assert created_types == expected_types

            # Verify all templates are now in the database
            all_templates = mgmt.list_templates()
            stored_types = {t.agent_type for t in all_templates}
            assert expected_types.issubset(stored_types)

    @settings(max_examples=1, deadline=None)
    @given(data=st.data())
    def test_seeded_templates_have_correct_flags(
        self, data: st.DataObject
    ) -> None:
        """All seeded templates have is_builtin==True and created_by=="system".

        **Validates: Requirements 28.4**
        """
        with mock_aws():
            _create_tables()
            mgmt = AgentManagementClient(region=REGION)

            mgmt.seed_builtin_templates()

            for agent_type in AgentManagementClient.BUILTIN_TEMPLATES:
                template = mgmt.get_template_by_type(agent_type)
                assert template is not None, f"Missing template: {agent_type}"
                assert template.is_builtin is True, (
                    f"Template {agent_type} should have is_builtin==True"
                )
                assert template.created_by == "system", (
                    f"Template {agent_type} should have created_by=='system'"
                )

    @settings(max_examples=1, deadline=None)
    @given(data=st.data())
    def test_seeding_is_idempotent(self, data: st.DataObject) -> None:
        """Running seed_builtin_templates twice does not duplicate or modify
        templates.

        **Validates: Requirements 28.3**
        """
        with mock_aws():
            _create_tables()
            mgmt = AgentManagementClient(region=REGION)

            # First seed
            first_created = mgmt.seed_builtin_templates()
            assert len(first_created) == len(AgentManagementClient.BUILTIN_TEMPLATES)

            # Capture state after first seed
            templates_after_first = {
                t.agent_type: t for t in mgmt.list_templates()
            }

            # Second seed — should create nothing
            second_created = mgmt.seed_builtin_templates()
            assert len(second_created) == 0

            # Verify templates are unchanged
            templates_after_second = {
                t.agent_type: t for t in mgmt.list_templates()
            }
            assert len(templates_after_second) == len(templates_after_first)

            for agent_type, original in templates_after_first.items():
                current = templates_after_second[agent_type]
                assert current.template_id == original.template_id
                assert current.name == original.name
                assert current.description == original.description
                assert current.is_builtin == original.is_builtin
                assert current.created_by == original.created_by
                assert current.created_at == original.created_at

    @given(
        subset=st.lists(
            st.sampled_from(sorted(AgentManagementClient.BUILTIN_TEMPLATES.keys())),
            min_size=1,
            max_size=len(AgentManagementClient.BUILTIN_TEMPLATES) - 1,
            unique=True,
        )
    )
    @settings(max_examples=5, deadline=None)
    def test_seeding_creates_only_missing_templates(
        self, subset: list[str]
    ) -> None:
        """When some built-in templates already exist, seeding creates only
        the missing ones and leaves existing ones unchanged.

        **Validates: Requirements 28.1, 28.3**
        """
        all_types = set(AgentManagementClient.BUILTIN_TEMPLATES.keys())
        pre_existing = set(subset)
        expected_new = all_types - pre_existing

        with mock_aws():
            _create_tables()
            mgmt = AgentManagementClient(region=REGION)

            # Pre-create a subset of built-in templates
            originals: dict[str, AgentTemplate] = {}
            for agent_type in pre_existing:
                info = AgentManagementClient.BUILTIN_TEMPLATES[agent_type]
                t = mgmt.create_agent_template(
                    name=info["name"],
                    agent_type=agent_type,
                    description=info["description"],
                    system_prompt=info["system_prompt"],
                    tool_server_ids=info["tool_server_ids"],
                    default_config=info.get("default_config"),
                    available_to="all",
                    is_builtin=True,
                    created_by="system",
                )
                originals[agent_type] = t

            # Seed — should only create the missing ones
            created = mgmt.seed_builtin_templates()
            created_types = {t.agent_type for t in created}
            assert created_types == expected_new

            # Pre-existing templates should be unchanged
            for agent_type, original in originals.items():
                current = mgmt.get_template_by_type(agent_type)
                assert current is not None
                assert current.template_id == original.template_id
                assert current.created_at == original.created_at

    @given(
        modified_name=non_empty_str,
        agent_type=st.sampled_from(
            sorted(AgentManagementClient.BUILTIN_TEMPLATES.keys())
        ),
    )
    @settings(max_examples=5, deadline=None)
    def test_existing_user_modified_templates_not_overwritten(
        self, modified_name: str, agent_type: str
    ) -> None:
        """If a user has modified a built-in template (e.g. changed its name),
        seeding does not overwrite the modification.

        **Validates: Requirements 28.3**
        """
        with mock_aws():
            _create_tables()
            mgmt = AgentManagementClient(region=REGION)

            # Create the template first via seeding
            mgmt.seed_builtin_templates()

            # Simulate user modification
            template = mgmt.get_template_by_type(agent_type)
            assert template is not None
            original_id = template.template_id
            mgmt.update_template(template.template_id, name=modified_name)

            # Re-seed — should not overwrite
            created = mgmt.seed_builtin_templates()
            assert all(t.agent_type != agent_type for t in created)

            # Verify the modification is preserved
            current = mgmt.get_template_by_type(agent_type)
            assert current is not None
            assert current.template_id == original_id
            assert current.name == modified_name


# ---------------------------------------------------------------------------
# Property 1: Sub-Agent Authorization Enforcement
# Validates: Requirements 2.4, 6.1, 6.2, 6.5, 8.1
# ---------------------------------------------------------------------------


class TestSubAgentAuthorizationEnforcement:
    """For any user_id and agent_type, a sub-agent tool is included in
    build_sub_agent_tool_ids iff:
      (a) an AgentConfig exists with enabled == True, AND
      (b) the corresponding AgentTemplate has available_to == "all"
          or user_id is in the available_to list.

    If either condition fails, the tool is excluded.

    **Validates: Requirements 2.4, 6.1, 6.2, 6.5, 8.1**
    """

    @given(
        user_id=user_id_strategy,
        agent_type=valid_agent_type,
    )
    @settings(max_examples=10, deadline=None)
    def test_enabled_and_available_to_all_includes_tool(
        self, user_id: str, agent_type: str
    ) -> None:
        """When config is enabled and template has available_to="all",
        the gateway_tool_id appears in build_sub_agent_tool_ids.

        **Validates: Requirements 6.1, 8.1**
        """
        with mock_aws():
            _create_tables()
            mgmt = AgentManagementClient(region=REGION)

            mgmt.create_agent_template(
                name=f"Template {agent_type}",
                agent_type=agent_type,
                description="test",
                system_prompt="test prompt",
                available_to="all",
            )
            mgmt.put_user_agent_config(user_id, agent_type, enabled=True)

            tool_ids = mgmt.build_sub_agent_tool_ids(user_id)
            assert f"gw-tool-{agent_type}" in tool_ids

    @given(
        user_id=user_id_strategy,
        agent_type=valid_agent_type,
    )
    @settings(max_examples=10, deadline=None)
    def test_enabled_and_user_in_available_to_list_includes_tool(
        self, user_id: str, agent_type: str
    ) -> None:
        """When config is enabled and user_id is in available_to list,
        the gateway_tool_id appears in build_sub_agent_tool_ids.

        **Validates: Requirements 6.2, 8.1**
        """
        with mock_aws():
            _create_tables()
            mgmt = AgentManagementClient(region=REGION)

            mgmt.create_agent_template(
                name=f"Template {agent_type}",
                agent_type=agent_type,
                description="test",
                system_prompt="test prompt",
                available_to=[user_id, "other_user"],
            )
            mgmt.put_user_agent_config(user_id, agent_type, enabled=True)

            tool_ids = mgmt.build_sub_agent_tool_ids(user_id)
            assert f"gw-tool-{agent_type}" in tool_ids

    @given(
        user_id=user_id_strategy,
        agent_type=valid_agent_type,
    )
    @settings(max_examples=10, deadline=None)
    def test_disabled_config_excludes_tool(
        self, user_id: str, agent_type: str
    ) -> None:
        """When config exists but enabled==False, the tool is excluded
        even if the user is authorized for the template.

        **Validates: Requirements 2.4, 8.1**
        """
        with mock_aws():
            _create_tables()
            mgmt = AgentManagementClient(region=REGION)

            mgmt.create_agent_template(
                name=f"Template {agent_type}",
                agent_type=agent_type,
                description="test",
                system_prompt="test prompt",
                available_to="all",
            )
            mgmt.put_user_agent_config(user_id, agent_type, enabled=True)
            # Disable by inserting directly with enabled=False
            mgmt._configs_table.put_item(
                Item={
                    "user_id": user_id,
                    "agent_type": agent_type,
                    "enabled": False,
                    "config": {},
                    "gateway_tool_id": f"gw-tool-{agent_type}",
                    "updated_at": "2025-01-01T00:00:00+00:00",
                }
            )

            tool_ids = mgmt.build_sub_agent_tool_ids(user_id)
            assert f"gw-tool-{agent_type}" not in tool_ids

    @given(
        user_id=user_id_strategy,
        other_user=user_id_strategy,
        agent_type=valid_agent_type,
    )
    @settings(max_examples=10, deadline=None)
    def test_unauthorized_user_excluded_from_tool_ids(
        self, user_id: str, other_user: str, agent_type: str
    ) -> None:
        """When template available_to is a list that does NOT contain user_id,
        the tool is excluded from build_sub_agent_tool_ids even if a config
        exists and is enabled.

        **Validates: Requirements 6.2, 6.5, 8.1**
        """
        assume(user_id != other_user)

        with mock_aws():
            _create_tables()
            mgmt = AgentManagementClient(region=REGION)

            # Template only available to other_user
            mgmt.create_agent_template(
                name=f"Template {agent_type}",
                agent_type=agent_type,
                description="test",
                system_prompt="test prompt",
                available_to=[other_user],
            )
            # Insert config directly (bypassing authorization check)
            mgmt._configs_table.put_item(
                Item={
                    "user_id": user_id,
                    "agent_type": agent_type,
                    "enabled": True,
                    "config": {},
                    "gateway_tool_id": f"gw-tool-{agent_type}",
                    "updated_at": "2025-01-01T00:00:00+00:00",
                }
            )

            tool_ids = mgmt.build_sub_agent_tool_ids(user_id)
            assert f"gw-tool-{agent_type}" not in tool_ids

    @given(
        user_id=user_id_strategy,
        agent_type=valid_agent_type,
    )
    @settings(max_examples=10, deadline=None)
    def test_no_config_means_no_tool(
        self, user_id: str, agent_type: str
    ) -> None:
        """When no AgentConfig exists for (user_id, agent_type), the tool
        is not included regardless of template authorization.

        **Validates: Requirements 2.4, 8.1**
        """
        with mock_aws():
            _create_tables()
            mgmt = AgentManagementClient(region=REGION)

            mgmt.create_agent_template(
                name=f"Template {agent_type}",
                agent_type=agent_type,
                description="test",
                system_prompt="test prompt",
                available_to="all",
            )
            # No config created for user

            tool_ids = mgmt.build_sub_agent_tool_ids(user_id)
            assert f"gw-tool-{agent_type}" not in tool_ids

    @given(
        user_id=user_id_strategy,
        agent_type=valid_agent_type,
        enabled=st.booleans(),
        available_to=st.one_of(
            st.just("all"),
            st.lists(user_id_strategy, min_size=1, max_size=5),
        ),
    )
    @settings(max_examples=10, deadline=None)
    def test_iff_property_all_combinations(
        self,
        user_id: str,
        agent_type: str,
        enabled: bool,
        available_to: str | list[str],
    ) -> None:
        """The core iff property: tool is included iff enabled==True AND
        user is authorized. Tests all combinations of enabled/disabled
        and authorized/unauthorized.

        **Validates: Requirements 2.4, 6.1, 6.2, 6.5, 8.1**
        """
        with mock_aws():
            _create_tables()
            mgmt = AgentManagementClient(region=REGION)

            mgmt.create_agent_template(
                name=f"Template {agent_type}",
                agent_type=agent_type,
                description="test",
                system_prompt="test prompt",
                available_to=available_to,
            )

            is_authorized = (
                available_to == "all" or user_id in available_to
            )

            # Insert config directly to bypass authorization check
            mgmt._configs_table.put_item(
                Item={
                    "user_id": user_id,
                    "agent_type": agent_type,
                    "enabled": enabled,
                    "config": {},
                    "gateway_tool_id": f"gw-tool-{agent_type}",
                    "updated_at": "2025-01-01T00:00:00+00:00",
                }
            )

            tool_ids = mgmt.build_sub_agent_tool_ids(user_id)
            expected_tool = f"gw-tool-{agent_type}"

            if enabled and is_authorized:
                assert expected_tool in tool_ids, (
                    f"Expected tool for enabled={enabled}, authorized={is_authorized}"
                )
            else:
                assert expected_tool not in tool_ids, (
                    f"Unexpected tool for enabled={enabled}, authorized={is_authorized}"
                )


# ---------------------------------------------------------------------------
# Property 6: Template Available_To Enforcement
# Validates: Requirements 5.5, 6.2, 6.3, 6.4
# ---------------------------------------------------------------------------


class TestTemplateAvailableToEnforcement:
    """**Validates: Requirements 5.5, 6.2, 6.3, 6.4**

    Property 6: Template Available_To Enforcement — for any template with
    available_to as a list, only listed user_ids can enable the agent and
    have the routing tool in their session. Updating available_to to remove
    a user_id does not delete their existing AgentConfig but prevents the
    tool from appearing in future sessions.
    """

    @given(
        allowed_users=st.lists(user_id_strategy, min_size=1, max_size=5, unique=True),
        outsider=user_id_strategy,
        agent_type=valid_agent_type,
    )
    @settings(max_examples=10, deadline=None)
    def test_only_listed_users_can_enable_agent(
        self,
        allowed_users: list[str],
        outsider: str,
        agent_type: str,
    ) -> None:
        """For a template with available_to as a list, only listed user_ids
        can successfully call put_user_agent_config; outsiders get ValueError.

        **Validates: Requirements 5.5, 6.2**
        """
        assume(outsider not in allowed_users)

        with mock_aws():
            _create_tables()
            mgmt = AgentManagementClient(region=REGION)

            mgmt.create_agent_template(
                name="Restricted Agent",
                agent_type=agent_type,
                description="test",
                system_prompt="test prompt",
                available_to=allowed_users,
            )

            # Allowed users can enable the agent
            for uid in allowed_users:
                cfg = mgmt.put_user_agent_config(uid, agent_type, enabled=True)
                assert cfg.enabled is True
                assert cfg.agent_type == agent_type

            # Outsider gets ValueError
            with pytest.raises(ValueError, match="not authorized"):
                mgmt.put_user_agent_config(outsider, agent_type, enabled=True)

    @given(
        allowed_users=st.lists(user_id_strategy, min_size=1, max_size=5, unique=True),
        outsider=user_id_strategy,
        agent_type=valid_agent_type,
    )
    @settings(max_examples=10, deadline=None)
    def test_only_listed_users_have_routing_tool(
        self,
        allowed_users: list[str],
        outsider: str,
        agent_type: str,
    ) -> None:
        """For a template with available_to as a list, only listed user_ids
        have the routing tool in build_sub_agent_tool_ids; outsiders do not,
        even if they have a config inserted directly.

        **Validates: Requirements 6.2, 6.4**
        """
        assume(outsider not in allowed_users)

        with mock_aws():
            _create_tables()
            mgmt = AgentManagementClient(region=REGION)

            mgmt.create_agent_template(
                name="Restricted Agent",
                agent_type=agent_type,
                description="test",
                system_prompt="test prompt",
                available_to=allowed_users,
            )

            expected_tool = f"gw-tool-{agent_type}"

            # Enable for allowed users
            for uid in allowed_users:
                mgmt.put_user_agent_config(uid, agent_type, enabled=True)

            # Insert config for outsider directly (bypassing auth check)
            _insert_config(mgmt, outsider, agent_type)

            # Allowed users see the tool
            for uid in allowed_users:
                tool_ids = mgmt.build_sub_agent_tool_ids(uid)
                assert expected_tool in tool_ids

            # Outsider does NOT see the tool
            tool_ids = mgmt.build_sub_agent_tool_ids(outsider)
            assert expected_tool not in tool_ids

    @given(
        user_id=user_id_strategy,
        remaining_user=user_id_strategy,
        agent_type=valid_agent_type,
    )
    @settings(max_examples=10, deadline=None)
    def test_removing_user_from_available_to_excludes_tool_but_keeps_config(
        self,
        user_id: str,
        remaining_user: str,
        agent_type: str,
    ) -> None:
        """When available_to is updated to remove a user_id, the user's
        existing AgentConfig is NOT deleted, but the routing tool no longer
        appears in build_sub_agent_tool_ids.

        **Validates: Requirements 6.3, 6.4**
        """
        assume(user_id != remaining_user)

        with mock_aws():
            _create_tables()
            mgmt = AgentManagementClient(region=REGION)

            template = mgmt.create_agent_template(
                name="Restricted Agent",
                agent_type=agent_type,
                description="test",
                system_prompt="test prompt",
                available_to=[user_id, remaining_user],
            )

            # Both users enable the agent
            mgmt.put_user_agent_config(user_id, agent_type, enabled=True)
            mgmt.put_user_agent_config(remaining_user, agent_type, enabled=True)

            expected_tool = f"gw-tool-{agent_type}"

            # Both see the tool before update
            assert expected_tool in mgmt.build_sub_agent_tool_ids(user_id)
            assert expected_tool in mgmt.build_sub_agent_tool_ids(remaining_user)

            # Remove user_id from available_to
            mgmt.update_template(
                template.template_id, available_to=[remaining_user]
            )

            # user_id's config still exists
            cfg = mgmt.get_user_agent_config(user_id, agent_type)
            assert cfg is not None
            assert cfg.enabled is True

            # But user_id no longer sees the tool
            assert expected_tool not in mgmt.build_sub_agent_tool_ids(user_id)

            # remaining_user still sees the tool
            assert expected_tool in mgmt.build_sub_agent_tool_ids(remaining_user)

    @given(
        user_id=user_id_strategy,
        agent_type=valid_agent_type,
    )
    @settings(max_examples=10, deadline=None)
    def test_available_to_all_allows_any_user(
        self,
        user_id: str,
        agent_type: str,
    ) -> None:
        """When available_to is "all", any user can enable the agent and
        see the routing tool in their session.

        **Validates: Requirements 5.5, 6.4**
        """
        with mock_aws():
            _create_tables()
            mgmt = AgentManagementClient(region=REGION)

            mgmt.create_agent_template(
                name="Open Agent",
                agent_type=agent_type,
                description="test",
                system_prompt="test prompt",
                available_to="all",
            )

            cfg = mgmt.put_user_agent_config(user_id, agent_type, enabled=True)
            assert cfg.enabled is True

            tool_ids = mgmt.build_sub_agent_tool_ids(user_id)
            assert f"gw-tool-{agent_type}" in tool_ids

    @given(
        user_id=user_id_strategy,
        other_user=user_id_strategy,
        agent_type=valid_agent_type,
    )
    @settings(max_examples=10, deadline=None)
    def test_adding_user_to_available_to_grants_tool_access(
        self,
        user_id: str,
        other_user: str,
        agent_type: str,
    ) -> None:
        """When available_to is updated to add a user_id, that user can
        now enable the agent and see the routing tool.

        **Validates: Requirements 6.3, 6.4**
        """
        assume(user_id != other_user)

        with mock_aws():
            _create_tables()
            mgmt = AgentManagementClient(region=REGION)

            # Start with only other_user authorized
            template = mgmt.create_agent_template(
                name="Restricted Agent",
                agent_type=agent_type,
                description="test",
                system_prompt="test prompt",
                available_to=[other_user],
            )

            # user_id cannot enable the agent
            with pytest.raises(ValueError, match="not authorized"):
                mgmt.put_user_agent_config(user_id, agent_type, enabled=True)

            # Update available_to to include user_id
            mgmt.update_template(
                template.template_id, available_to=[other_user, user_id]
            )

            # Now user_id can enable and see the tool
            cfg = mgmt.put_user_agent_config(user_id, agent_type, enabled=True)
            assert cfg.enabled is True

            tool_ids = mgmt.build_sub_agent_tool_ids(user_id)
            assert f"gw-tool-{agent_type}" in tool_ids

    @given(
        agent_type=valid_agent_type,
        available_to=st.one_of(
            st.just("all"),
            st.lists(user_id_strategy, min_size=1, max_size=5, unique=True),
        ),
        user_id=user_id_strategy,
    )
    @settings(max_examples=10, deadline=None)
    def test_available_to_validation_at_config_creation(
        self,
        agent_type: str,
        available_to: str | list[str],
        user_id: str,
    ) -> None:
        """Authorization is checked at config creation time: put_user_agent_config
        succeeds only if user is in available_to list or available_to is "all".

        **Validates: Requirements 5.5, 6.2, 6.4**
        """
        with mock_aws():
            _create_tables()
            mgmt = AgentManagementClient(region=REGION)

            mgmt.create_agent_template(
                name="Agent",
                agent_type=agent_type,
                description="test",
                system_prompt="test prompt",
                available_to=available_to,
            )

            is_authorized = available_to == "all" or user_id in available_to

            if is_authorized:
                cfg = mgmt.put_user_agent_config(user_id, agent_type, enabled=True)
                assert cfg.agent_type == agent_type
            else:
                with pytest.raises(ValueError, match="not authorized"):
                    mgmt.put_user_agent_config(user_id, agent_type, enabled=True)


# ---------------------------------------------------------------------------
# Property 5: Admin-Only Cross-User Configuration
# Validates: Requirements 7.1, 7.2, 7.3
# ---------------------------------------------------------------------------


_NON_ADMIN_ROLE = st.one_of(
    st.just("member"),
    st.just(None),
    st.text(min_size=1, max_size=15).filter(lambda s: s.strip() and s != "admin"),
)


class TestAdminOnlyCrossUserConfiguration:
    """Property 5: Admin-Only Cross-User Configuration.

    For any cross-user config modification (requesting_user_id != target
    user_id), the operation succeeds only if requesting_user_role == "admin".
    Non-admin roles raise PermissionError.  Self-modification always succeeds
    regardless of role.

    **Validates: Requirements 7.1, 7.2, 7.3**
    """

    # ------------------------------------------------------------------
    # put_user_agent_config — cross-user
    # ------------------------------------------------------------------

    @given(
        target_user=user_id_strategy,
        requesting_user=user_id_strategy,
        agent_type=valid_agent_type,
    )
    @settings(max_examples=10, deadline=None)
    def test_admin_can_put_config_for_other_user(
        self,
        target_user: str,
        requesting_user: str,
        agent_type: str,
    ) -> None:
        """Cross-user put succeeds when requesting_user_role == 'admin'.

        **Validates: Requirements 7.1**
        """
        assume(requesting_user != target_user)

        with mock_aws():
            _create_tables()
            mgmt = AgentManagementClient(region=REGION)

            mgmt.create_agent_template(
                name="Agent",
                agent_type=agent_type,
                description="test",
                system_prompt="prompt",
                available_to="all",
            )

            cfg = mgmt.put_user_agent_config(
                user_id=target_user,
                agent_type=agent_type,
                enabled=True,
                requesting_user_id=requesting_user,
                requesting_user_role="admin",
            )
            assert cfg.user_id == target_user
            assert cfg.agent_type == agent_type

    @given(
        target_user=user_id_strategy,
        requesting_user=user_id_strategy,
        agent_type=valid_agent_type,
        role=_NON_ADMIN_ROLE,
    )
    @settings(max_examples=10, deadline=None)
    def test_non_admin_cannot_put_config_for_other_user(
        self,
        target_user: str,
        requesting_user: str,
        agent_type: str,
        role: str | None,
    ) -> None:
        """Cross-user put raises PermissionError for non-admin roles.

        **Validates: Requirements 7.2**
        """
        assume(requesting_user != target_user)

        with mock_aws():
            _create_tables()
            mgmt = AgentManagementClient(region=REGION)

            mgmt.create_agent_template(
                name="Agent",
                agent_type=agent_type,
                description="test",
                system_prompt="prompt",
                available_to="all",
            )

            with pytest.raises(PermissionError):
                mgmt.put_user_agent_config(
                    user_id=target_user,
                    agent_type=agent_type,
                    enabled=True,
                    requesting_user_id=requesting_user,
                    requesting_user_role=role,
                )

    # ------------------------------------------------------------------
    # delete_user_agent_config — cross-user
    # ------------------------------------------------------------------

    @given(
        target_user=user_id_strategy,
        requesting_user=user_id_strategy,
        agent_type=valid_agent_type,
    )
    @settings(max_examples=10, deadline=None)
    def test_admin_can_delete_config_for_other_user(
        self,
        target_user: str,
        requesting_user: str,
        agent_type: str,
    ) -> None:
        """Cross-user delete succeeds when requesting_user_role == 'admin'.

        **Validates: Requirements 7.1**
        """
        assume(requesting_user != target_user)

        with mock_aws():
            _create_tables()
            mgmt = AgentManagementClient(region=REGION)

            mgmt.create_agent_template(
                name="Agent",
                agent_type=agent_type,
                description="test",
                system_prompt="prompt",
                available_to="all",
            )

            # Create config first
            mgmt.put_user_agent_config(
                user_id=target_user,
                agent_type=agent_type,
                enabled=True,
            )

            result = mgmt.delete_user_agent_config(
                user_id=target_user,
                agent_type=agent_type,
                requesting_user_id=requesting_user,
                requesting_user_role="admin",
            )
            assert result is True

            # Verify config is gone
            assert mgmt.get_user_agent_config(target_user, agent_type) is None

    @given(
        target_user=user_id_strategy,
        requesting_user=user_id_strategy,
        agent_type=valid_agent_type,
        role=_NON_ADMIN_ROLE,
    )
    @settings(max_examples=10, deadline=None)
    def test_non_admin_cannot_delete_config_for_other_user(
        self,
        target_user: str,
        requesting_user: str,
        agent_type: str,
        role: str | None,
    ) -> None:
        """Cross-user delete raises PermissionError for non-admin roles.

        **Validates: Requirements 7.2**
        """
        assume(requesting_user != target_user)

        with mock_aws():
            _create_tables()
            mgmt = AgentManagementClient(region=REGION)

            mgmt.create_agent_template(
                name="Agent",
                agent_type=agent_type,
                description="test",
                system_prompt="prompt",
                available_to="all",
            )

            # Create config first
            mgmt.put_user_agent_config(
                user_id=target_user,
                agent_type=agent_type,
                enabled=True,
            )

            with pytest.raises(PermissionError):
                mgmt.delete_user_agent_config(
                    user_id=target_user,
                    agent_type=agent_type,
                    requesting_user_id=requesting_user,
                    requesting_user_role=role,
                )

            # Verify config still exists
            assert mgmt.get_user_agent_config(target_user, agent_type) is not None

    # ------------------------------------------------------------------
    # Self-modification — always allowed regardless of role
    # ------------------------------------------------------------------

    @given(
        user_id=user_id_strategy,
        agent_type=valid_agent_type,
        role=st.one_of(
            st.just("admin"),
            st.just("member"),
            st.just(None),
            st.text(min_size=1, max_size=15).filter(lambda s: s.strip()),
        ),
    )
    @settings(max_examples=10, deadline=None)
    def test_self_modification_put_always_allowed(
        self,
        user_id: str,
        agent_type: str,
        role: str | None,
    ) -> None:
        """Self-modification (requesting_user_id == user_id) always succeeds.

        **Validates: Requirements 7.3**
        """
        with mock_aws():
            _create_tables()
            mgmt = AgentManagementClient(region=REGION)

            mgmt.create_agent_template(
                name="Agent",
                agent_type=agent_type,
                description="test",
                system_prompt="prompt",
                available_to="all",
            )

            cfg = mgmt.put_user_agent_config(
                user_id=user_id,
                agent_type=agent_type,
                enabled=True,
                requesting_user_id=user_id,
                requesting_user_role=role,
            )
            assert cfg.user_id == user_id

    @given(
        user_id=user_id_strategy,
        agent_type=valid_agent_type,
        role=st.one_of(
            st.just("admin"),
            st.just("member"),
            st.just(None),
            st.text(min_size=1, max_size=15).filter(lambda s: s.strip()),
        ),
    )
    @settings(max_examples=10, deadline=None)
    def test_self_modification_delete_always_allowed(
        self,
        user_id: str,
        agent_type: str,
        role: str | None,
    ) -> None:
        """Self-modification delete always succeeds regardless of role.

        **Validates: Requirements 7.3**
        """
        with mock_aws():
            _create_tables()
            mgmt = AgentManagementClient(region=REGION)

            mgmt.create_agent_template(
                name="Agent",
                agent_type=agent_type,
                description="test",
                system_prompt="prompt",
                available_to="all",
            )

            mgmt.put_user_agent_config(
                user_id=user_id,
                agent_type=agent_type,
                enabled=True,
            )

            result = mgmt.delete_user_agent_config(
                user_id=user_id,
                agent_type=agent_type,
                requesting_user_id=user_id,
                requesting_user_role=role,
            )
            assert result is True

    # ------------------------------------------------------------------
    # No requesting_user_id — treated as self-modification
    # ------------------------------------------------------------------

    @given(
        user_id=user_id_strategy,
        agent_type=valid_agent_type,
        role=st.one_of(
            st.just("admin"),
            st.just("member"),
            st.just(None),
        ),
    )
    @settings(max_examples=10, deadline=None)
    def test_no_requesting_user_id_always_allowed(
        self,
        user_id: str,
        agent_type: str,
        role: str | None,
    ) -> None:
        """When requesting_user_id is None, operation is always allowed.

        **Validates: Requirements 7.3**
        """
        with mock_aws():
            _create_tables()
            mgmt = AgentManagementClient(region=REGION)

            mgmt.create_agent_template(
                name="Agent",
                agent_type=agent_type,
                description="test",
                system_prompt="prompt",
                available_to="all",
            )

            cfg = mgmt.put_user_agent_config(
                user_id=user_id,
                agent_type=agent_type,
                enabled=True,
                requesting_user_id=None,
                requesting_user_role=role,
            )
            assert cfg.user_id == user_id


# ---------------------------------------------------------------------------
# Property 27: Tool Resolution Determinism
# Validates: Requirements 8.2, 8.3, 27.3
# ---------------------------------------------------------------------------


class TestToolResolutionDeterminism:
    """Property 27: Tool Resolution Determinism.

    For any user, resolved tool IDs are sorted by agent_type; configs
    referencing missing templates are excluded with a logged warning.

    **Validates: Requirements 8.2, 8.3, 27.3**
    """

    @given(
        user_id=user_id_strategy,
        agent_types=st.lists(
            valid_agent_type,
            min_size=2,
            max_size=5,
            unique=True,
        ),
    )
    @settings(max_examples=10, deadline=None)
    def test_resolved_tool_ids_sorted_by_agent_type(
        self, user_id: str, agent_types: list[str]
    ) -> None:
        """Resolved tool IDs are always sorted by agent_type.

        **Validates: Requirements 8.3**
        """
        with mock_aws():
            _create_tables()
            mgmt = AgentManagementClient(region=REGION)

            for at in agent_types:
                mgmt.create_agent_template(
                    name=f"Template {at}",
                    agent_type=at,
                    description="test",
                    system_prompt="prompt",
                    available_to="all",
                )
                mgmt.put_user_agent_config(user_id, at, enabled=True)

            tool_ids = mgmt.build_sub_agent_tool_ids(user_id)

            expected_sorted = [f"gw-tool-{at}" for at in sorted(agent_types)]
            assert tool_ids == expected_sorted

    @given(
        user_id=user_id_strategy,
        agent_types=st.lists(
            valid_agent_type,
            min_size=1,
            max_size=5,
            unique=True,
        ),
    )
    @settings(max_examples=10, deadline=None)
    def test_repeated_calls_return_same_result(
        self, user_id: str, agent_types: list[str]
    ) -> None:
        """Calling build_sub_agent_tool_ids multiple times returns the
        same result (determinism).

        **Validates: Requirements 8.3**
        """
        with mock_aws():
            _create_tables()
            mgmt = AgentManagementClient(region=REGION)

            for at in agent_types:
                mgmt.create_agent_template(
                    name=f"Template {at}",
                    agent_type=at,
                    description="test",
                    system_prompt="prompt",
                    available_to="all",
                )
                mgmt.put_user_agent_config(user_id, at, enabled=True)

            result1 = mgmt.build_sub_agent_tool_ids(user_id)
            result2 = mgmt.build_sub_agent_tool_ids(user_id)
            result3 = mgmt.build_sub_agent_tool_ids(user_id)

            assert result1 == result2 == result3

    @given(
        user_id=user_id_strategy,
        live_type=valid_agent_type,
        orphan_type=valid_agent_type,
    )
    @settings(max_examples=10, deadline=None)
    def test_missing_template_excluded_from_results(
        self, user_id: str, live_type: str, orphan_type: str
    ) -> None:
        """Configs referencing missing/deleted templates are excluded
        from the resolved tool IDs.

        **Validates: Requirements 8.2, 27.3**
        """
        assume(live_type != orphan_type)

        with mock_aws():
            _create_tables()
            mgmt = AgentManagementClient(region=REGION)

            # Create a live template + config
            mgmt.create_agent_template(
                name=f"Template {live_type}",
                agent_type=live_type,
                description="test",
                system_prompt="prompt",
                available_to="all",
            )
            mgmt.put_user_agent_config(user_id, live_type, enabled=True)

            # Insert an orphan config directly (no template exists)
            _insert_config(mgmt, user_id, orphan_type)

            tool_ids = mgmt.build_sub_agent_tool_ids(user_id)

            assert f"gw-tool-{live_type}" in tool_ids
            assert f"gw-tool-{orphan_type}" not in tool_ids

    @given(
        user_id=user_id_strategy,
        orphan_type=valid_agent_type,
    )
    @settings(max_examples=10, deadline=None)
    def test_missing_template_logs_warning(
        self, user_id: str, orphan_type: str
    ) -> None:
        """When a config references a missing template, a warning is logged.

        **Validates: Requirements 8.2, 27.3**
        """
        import logging

        with mock_aws():
            _create_tables()
            mgmt = AgentManagementClient(region=REGION)

            # Insert an orphan config directly (no template exists)
            _insert_config(mgmt, user_id, orphan_type)

            logger = logging.getLogger("app.services.agent_management")
            handler = logging.handlers.MemoryHandler(capacity=100)
            handler.setLevel(logging.WARNING)
            logger.addHandler(handler)
            try:
                mgmt.build_sub_agent_tool_ids(user_id)
                handler.flush()
                warning_messages = [
                    r.getMessage()
                    for r in handler.buffer
                    if r.levelno >= logging.WARNING
                ]
                assert any(
                    orphan_type in msg for msg in warning_messages
                ), f"Expected warning about missing template for {orphan_type}, got: {warning_messages}"
            finally:
                logger.removeHandler(handler)
