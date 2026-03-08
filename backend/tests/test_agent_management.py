"""Tests for the AgentManagementClient class.

Uses moto to mock DynamoDB so tests run without DynamoDB Local.
"""

import boto3
import pytest
from moto import mock_aws

from app.models.dynamo import TABLE_DEFINITIONS
from app.services.agent_management import AgentManagementClient

REGION = "us-east-1"


def _create_tables():
    """Create the AgentTemplates and AgentConfigs tables in mocked DynamoDB."""
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


@pytest.fixture()
def mgmt():
    """Create an AgentManagementClient backed by moto-mocked DynamoDB."""
    with mock_aws():
        _create_tables()
        yield AgentManagementClient(region=REGION)


@pytest.fixture()
def sample_template(mgmt):
    """Create and return a sample non-builtin template."""
    return mgmt.create_agent_template(
        name="Meal Planner",
        agent_type="meal_planner",
        description="Plans weekly meals",
        system_prompt="You are a meal planning assistant.",
        tool_server_ids=["srv-1"],
        default_config={"draft_only": True},
        available_to="all",
        is_builtin=False,
        created_by="test_user",
    )


# ------------------------------------------------------------------
# create_agent_template
# ------------------------------------------------------------------


class TestCreateAgentTemplate:
    def test_creates_with_all_fields(self, mgmt):
        t = mgmt.create_agent_template(
            name="Health Advisor",
            agent_type="health_advisor",
            description="Health companion",
            system_prompt="You are a health advisor.",
            tool_server_ids=["srv-health"],
            default_config={"safety": True},
            available_to="all",
            is_builtin=True,
            created_by="system",
        )
        assert t.template_id
        assert t.agent_type == "health_advisor"
        assert t.name == "Health Advisor"
        assert t.description == "Health companion"
        assert t.system_prompt == "You are a health advisor."
        assert t.tool_server_ids == ["srv-health"]
        assert t.default_config == {"safety": True}
        assert t.available_to == "all"
        assert t.is_builtin is True
        assert t.created_by == "system"
        assert t.created_at
        assert t.updated_at

    def test_unique_agent_type_enforcement(self, mgmt, sample_template):
        with pytest.raises(ValueError, match="already exists"):
            mgmt.create_agent_template(
                name="Another Planner",
                agent_type="meal_planner",
                description="Duplicate",
                system_prompt="Dup",
            )

    def test_available_to_user_list(self, mgmt):
        t = mgmt.create_agent_template(
            name="VIP Agent",
            agent_type="vip_agent",
            description="VIP only",
            system_prompt="VIP",
            available_to=["user-1", "user-2"],
        )
        assert t.available_to == ["user-1", "user-2"]

    def test_defaults_for_optional_fields(self, mgmt):
        t = mgmt.create_agent_template(
            name="Simple",
            agent_type="simple_agent",
            description="Simple agent",
            system_prompt="Simple",
        )
        assert t.tool_server_ids == []
        assert t.default_config == {}
        assert t.available_to == "all"
        assert t.is_builtin is False
        assert t.created_by == ""

    def test_invalid_agent_type_rejected(self, mgmt):
        with pytest.raises(ValueError, match="agent_type"):
            mgmt.create_agent_template(
                name="Bad",
                agent_type="Bad Agent!",
                description="Invalid",
                system_prompt="Bad",
            )


# ------------------------------------------------------------------
# get_template / get_template_by_type
# ------------------------------------------------------------------


class TestGetTemplate:
    def test_get_by_id(self, mgmt, sample_template):
        result = mgmt.get_template(sample_template.template_id)
        assert result is not None
        assert result.template_id == sample_template.template_id
        assert result.agent_type == "meal_planner"

    def test_get_by_id_not_found(self, mgmt):
        assert mgmt.get_template("nonexistent") is None

    def test_get_by_type(self, mgmt, sample_template):
        result = mgmt.get_template_by_type("meal_planner")
        assert result is not None
        assert result.template_id == sample_template.template_id

    def test_get_by_type_not_found(self, mgmt):
        assert mgmt.get_template_by_type("nonexistent") is None


# ------------------------------------------------------------------
# list_templates
# ------------------------------------------------------------------


class TestListTemplates:
    def test_list_empty(self, mgmt):
        assert mgmt.list_templates() == []

    def test_list_returns_all(self, mgmt, sample_template):
        mgmt.create_agent_template(
            name="Second",
            agent_type="second_agent",
            description="Second",
            system_prompt="Second",
        )
        templates = mgmt.list_templates()
        assert len(templates) == 2
        types = {t.agent_type for t in templates}
        assert types == {"meal_planner", "second_agent"}


# ------------------------------------------------------------------
# get_available_templates
# ------------------------------------------------------------------


class TestGetAvailableTemplates:
    def test_all_available(self, mgmt, sample_template):
        result = mgmt.get_available_templates("any_user")
        assert len(result) == 1
        assert result[0].agent_type == "meal_planner"

    def test_restricted_to_specific_users(self, mgmt):
        mgmt.create_agent_template(
            name="VIP",
            agent_type="vip_agent",
            description="VIP",
            system_prompt="VIP",
            available_to=["user-1"],
        )
        assert len(mgmt.get_available_templates("user-1")) == 1
        assert len(mgmt.get_available_templates("user-2")) == 0

    def test_mixed_availability(self, mgmt, sample_template):
        mgmt.create_agent_template(
            name="VIP",
            agent_type="vip_agent",
            description="VIP",
            system_prompt="VIP",
            available_to=["user-1"],
        )
        assert len(mgmt.get_available_templates("user-1")) == 2
        result = mgmt.get_available_templates("user-2")
        assert len(result) == 1
        assert result[0].agent_type == "meal_planner"


# ------------------------------------------------------------------
# update_template
# ------------------------------------------------------------------


class TestUpdateTemplate:
    def test_update_fields(self, mgmt, sample_template):
        updated = mgmt.update_template(
            sample_template.template_id,
            name="Weekly Meal Planner",
            description="Plans weekly meals for the family",
        )
        assert updated is not None
        assert updated.name == "Weekly Meal Planner"
        assert updated.description == "Plans weekly meals for the family"
        assert updated.updated_at > sample_template.updated_at

    def test_update_not_found(self, mgmt):
        assert mgmt.update_template("nonexistent", name="X") is None

    def test_update_ignores_disallowed_fields(self, mgmt, sample_template):
        updated = mgmt.update_template(
            sample_template.template_id,
            agent_type="hacked",
            is_builtin=True,
        )
        # No allowed fields → returns original template unchanged
        assert updated is not None
        assert updated.template_id == sample_template.template_id
        assert updated.agent_type == "meal_planner"
        assert updated.is_builtin is False

    def test_update_timestamp_changes(self, mgmt, sample_template):
        import time
        time.sleep(0.01)
        updated = mgmt.update_template(
            sample_template.template_id, name="Updated"
        )
        assert updated.updated_at != sample_template.updated_at


# ------------------------------------------------------------------
# delete_template
# ------------------------------------------------------------------


class TestDeleteTemplate:
    def test_delete_non_builtin(self, mgmt, sample_template):
        assert mgmt.delete_template(sample_template.template_id) is True
        assert mgmt.get_template(sample_template.template_id) is None

    def test_delete_builtin_rejected(self, mgmt):
        t = mgmt.create_agent_template(
            name="Built-in",
            agent_type="builtin_agent",
            description="Built-in",
            system_prompt="Built-in",
            is_builtin=True,
            created_by="system",
        )
        with pytest.raises(ValueError, match="Cannot delete built-in"):
            mgmt.delete_template(t.template_id)

    def test_delete_not_found(self, mgmt):
        assert mgmt.delete_template("nonexistent") is False

    def test_delete_cascades_agent_configs(self, mgmt, sample_template):
        """Deleting a template cascade-deletes all referencing AgentConfigs."""
        mgmt._configs_table.put_item(
            Item={
                "user_id": "user-1",
                "agent_type": "meal_planner",
                "enabled": True,
                "config": {},
                "updated_at": "2025-01-01T00:00:00+00:00",
            }
        )
        mgmt._configs_table.put_item(
            Item={
                "user_id": "user-2",
                "agent_type": "meal_planner",
                "enabled": True,
                "config": {},
                "updated_at": "2025-01-01T00:00:00+00:00",
            }
        )
        # Config for a different agent_type — should NOT be deleted
        mgmt._configs_table.put_item(
            Item={
                "user_id": "user-1",
                "agent_type": "other_agent",
                "enabled": True,
                "config": {},
                "updated_at": "2025-01-01T00:00:00+00:00",
            }
        )

        mgmt.delete_template(sample_template.template_id)

        resp1 = mgmt._configs_table.get_item(
            Key={"user_id": "user-1", "agent_type": "meal_planner"}
        )
        assert "Item" not in resp1

        resp2 = mgmt._configs_table.get_item(
            Key={"user_id": "user-2", "agent_type": "meal_planner"}
        )
        assert "Item" not in resp2

        resp3 = mgmt._configs_table.get_item(
            Key={"user_id": "user-1", "agent_type": "other_agent"}
        )
        assert "Item" in resp3


# ------------------------------------------------------------------
# seed_builtin_templates
# ------------------------------------------------------------------


class TestSeedBuiltinTemplates:
    def test_seeds_all_three_builtin_templates(self, mgmt):
        """All three built-in templates are created when none exist."""
        created = mgmt.seed_builtin_templates()
        assert len(created) == 3
        agent_types = {t.agent_type for t in created}
        assert agent_types == {"health_advisor", "logistics_assistant", "shopping_assistant"}

    def test_seeded_templates_have_correct_flags(self, mgmt):
        """Seeded templates have is_builtin=True and created_by='system'."""
        mgmt.seed_builtin_templates()
        for agent_type in ("health_advisor", "logistics_assistant", "shopping_assistant"):
            t = mgmt.get_template_by_type(agent_type)
            assert t is not None
            assert t.is_builtin is True
            assert t.created_by == "system"
            assert t.available_to == "all"

    def test_seeded_templates_have_correct_content(self, mgmt):
        """Seeded templates match the BUILTIN_TEMPLATES definitions."""
        mgmt.seed_builtin_templates()
        for agent_type, info in AgentManagementClient.BUILTIN_TEMPLATES.items():
            t = mgmt.get_template_by_type(agent_type)
            assert t is not None
            assert t.name == info["name"]
            assert t.description == info["description"]
            assert t.system_prompt == info["system_prompt"]
            assert t.tool_server_ids == info["tool_server_ids"]
            assert t.default_config == info.get("default_config", {})

    def test_does_not_overwrite_existing_templates(self, mgmt):
        """Existing templates are left unchanged by seeding."""
        mgmt.create_agent_template(
            name="Custom Health",
            agent_type="health_advisor",
            description="My custom health agent",
            system_prompt="Custom prompt",
            is_builtin=True,
            created_by="system",
        )
        created = mgmt.seed_builtin_templates()
        # Only 2 should be created (logistics_assistant and shopping_assistant)
        assert len(created) == 2
        created_types = {t.agent_type for t in created}
        assert "health_advisor" not in created_types

        # Verify the existing template was not overwritten
        t = mgmt.get_template_by_type("health_advisor")
        assert t.name == "Custom Health"
        assert t.description == "My custom health agent"

    def test_idempotent_on_repeated_calls(self, mgmt):
        """Calling seed_builtin_templates twice creates templates only once."""
        first = mgmt.seed_builtin_templates()
        assert len(first) == 3
        second = mgmt.seed_builtin_templates()
        assert len(second) == 0

        # Still exactly 3 templates total
        all_templates = mgmt.list_templates()
        assert len(all_templates) == 3


# ------------------------------------------------------------------
# Per-User Agent Config: put_user_agent_config
# ------------------------------------------------------------------


class TestPutUserAgentConfig:
    def test_creates_config_with_merged_defaults(self, mgmt, sample_template):
        cfg = mgmt.put_user_agent_config(
            user_id="user-1",
            agent_type="meal_planner",
            enabled=True,
            config={"custom_key": "custom_val"},
        )
        assert cfg.user_id == "user-1"
        assert cfg.agent_type == "meal_planner"
        assert cfg.enabled is True
        # Merged: template default_config + user overrides
        assert cfg.config == {"draft_only": True, "custom_key": "custom_val"}
        assert cfg.gateway_tool_id == "gw-tool-meal_planner"
        assert cfg.updated_at

    def test_user_overrides_take_precedence(self, mgmt, sample_template):
        cfg = mgmt.put_user_agent_config(
            user_id="user-1",
            agent_type="meal_planner",
            config={"draft_only": False},
        )
        assert cfg.config["draft_only"] is False

    def test_no_user_config_uses_template_defaults(self, mgmt, sample_template):
        cfg = mgmt.put_user_agent_config(
            user_id="user-1",
            agent_type="meal_planner",
        )
        assert cfg.config == {"draft_only": True}

    def test_rejects_invalid_agent_type(self, mgmt):
        with pytest.raises(ValueError, match="No template found"):
            mgmt.put_user_agent_config(
                user_id="user-1",
                agent_type="nonexistent_agent",
            )

    def test_rejects_unauthorized_user(self, mgmt):
        mgmt.create_agent_template(
            name="VIP Agent",
            agent_type="vip_agent",
            description="VIP only",
            system_prompt="VIP",
            available_to=["user-1"],
        )
        with pytest.raises(ValueError, match="not authorized"):
            mgmt.put_user_agent_config(
                user_id="user-2",
                agent_type="vip_agent",
            )

    def test_authorized_user_succeeds(self, mgmt):
        mgmt.create_agent_template(
            name="VIP Agent",
            agent_type="vip_agent",
            description="VIP only",
            system_prompt="VIP",
            available_to=["user-1"],
        )
        cfg = mgmt.put_user_agent_config(
            user_id="user-1",
            agent_type="vip_agent",
        )
        assert cfg.agent_type == "vip_agent"

    def test_available_to_all_allows_any_user(self, mgmt, sample_template):
        cfg = mgmt.put_user_agent_config(
            user_id="any-user-id",
            agent_type="meal_planner",
        )
        assert cfg.user_id == "any-user-id"

    def test_updates_existing_config(self, mgmt, sample_template):
        mgmt.put_user_agent_config(
            user_id="user-1",
            agent_type="meal_planner",
            enabled=True,
        )
        updated = mgmt.put_user_agent_config(
            user_id="user-1",
            agent_type="meal_planner",
            enabled=False,
            config={"new_key": "new_val"},
        )
        assert updated.enabled is False
        assert updated.config == {"draft_only": True, "new_key": "new_val"}

    def test_gateway_tool_id_format(self, mgmt, sample_template):
        cfg = mgmt.put_user_agent_config(
            user_id="user-1",
            agent_type="meal_planner",
        )
        assert cfg.gateway_tool_id == "gw-tool-meal_planner"


# ------------------------------------------------------------------
# Per-User Agent Config: get_user_agent_configs / get_user_agent_config
# ------------------------------------------------------------------


class TestGetUserAgentConfigs:
    def test_returns_empty_for_no_configs(self, mgmt):
        assert mgmt.get_user_agent_configs("user-1") == []

    def test_returns_all_configs_for_user(self, mgmt):
        mgmt.create_agent_template(
            name="Agent A", agent_type="agent_a",
            description="A", system_prompt="A",
        )
        mgmt.create_agent_template(
            name="Agent B", agent_type="agent_b",
            description="B", system_prompt="B",
        )
        mgmt.put_user_agent_config(user_id="user-1", agent_type="agent_a")
        mgmt.put_user_agent_config(user_id="user-1", agent_type="agent_b")
        configs = mgmt.get_user_agent_configs("user-1")
        assert len(configs) == 2
        types = {c.agent_type for c in configs}
        assert types == {"agent_a", "agent_b"}

    def test_does_not_return_other_users_configs(self, mgmt, sample_template):
        mgmt.put_user_agent_config(user_id="user-1", agent_type="meal_planner")
        assert mgmt.get_user_agent_configs("user-2") == []


class TestGetUserAgentConfig:
    def test_returns_config_when_exists(self, mgmt, sample_template):
        mgmt.put_user_agent_config(user_id="user-1", agent_type="meal_planner")
        cfg = mgmt.get_user_agent_config("user-1", "meal_planner")
        assert cfg is not None
        assert cfg.user_id == "user-1"
        assert cfg.agent_type == "meal_planner"

    def test_returns_none_when_not_found(self, mgmt):
        assert mgmt.get_user_agent_config("user-1", "nonexistent") is None


# ------------------------------------------------------------------
# Per-User Agent Config: delete_user_agent_config
# ------------------------------------------------------------------


class TestDeleteUserAgentConfig:
    def test_deletes_existing_config(self, mgmt, sample_template):
        mgmt.put_user_agent_config(user_id="user-1", agent_type="meal_planner")
        assert mgmt.delete_user_agent_config("user-1", "meal_planner") is True
        assert mgmt.get_user_agent_config("user-1", "meal_planner") is None

    def test_returns_false_when_not_found(self, mgmt):
        assert mgmt.delete_user_agent_config("user-1", "nonexistent") is False

    def test_does_not_affect_other_configs(self, mgmt):
        mgmt.create_agent_template(
            name="Agent A", agent_type="agent_a",
            description="A", system_prompt="A",
        )
        mgmt.create_agent_template(
            name="Agent B", agent_type="agent_b",
            description="B", system_prompt="B",
        )
        mgmt.put_user_agent_config(user_id="user-1", agent_type="agent_a")
        mgmt.put_user_agent_config(user_id="user-1", agent_type="agent_b")
        mgmt.delete_user_agent_config("user-1", "agent_a")
        assert mgmt.get_user_agent_config("user-1", "agent_a") is None
        assert mgmt.get_user_agent_config("user-1", "agent_b") is not None


# ------------------------------------------------------------------
# Per-User Agent Config: enable/disable via put_user_agent_config
# ------------------------------------------------------------------


class TestEnableDisableAgentConfig:
    def test_disable_agent(self, mgmt, sample_template):
        mgmt.put_user_agent_config(
            user_id="user-1", agent_type="meal_planner", enabled=True,
        )
        updated = mgmt.put_user_agent_config(
            user_id="user-1", agent_type="meal_planner", enabled=False,
        )
        assert updated.enabled is False
        persisted = mgmt.get_user_agent_config("user-1", "meal_planner")
        assert persisted.enabled is False

    def test_re_enable_agent(self, mgmt, sample_template):
        mgmt.put_user_agent_config(
            user_id="user-1", agent_type="meal_planner", enabled=False,
        )
        updated = mgmt.put_user_agent_config(
            user_id="user-1", agent_type="meal_planner", enabled=True,
        )
        assert updated.enabled is True
        persisted = mgmt.get_user_agent_config("user-1", "meal_planner")
        assert persisted.enabled is True


# ------------------------------------------------------------------
# is_user_authorized_for_template
# ------------------------------------------------------------------


class TestIsUserAuthorizedForTemplate:
    def test_available_to_all_authorizes_any_user(self, mgmt, sample_template):
        assert mgmt.is_user_authorized_for_template("any-user", sample_template) is True

    def test_user_in_available_to_list_authorized(self, mgmt):
        t = mgmt.create_agent_template(
            name="VIP",
            agent_type="vip_agent",
            description="VIP",
            system_prompt="VIP",
            available_to=["user-1", "user-2"],
        )
        assert mgmt.is_user_authorized_for_template("user-1", t) is True
        assert mgmt.is_user_authorized_for_template("user-2", t) is True

    def test_user_not_in_available_to_list_rejected(self, mgmt):
        t = mgmt.create_agent_template(
            name="VIP",
            agent_type="vip_agent",
            description="VIP",
            system_prompt="VIP",
            available_to=["user-1"],
        )
        assert mgmt.is_user_authorized_for_template("user-99", t) is False

    def test_delegates_to_is_available(self, mgmt, sample_template):
        """Public method returns same result as internal _is_available."""
        assert mgmt.is_user_authorized_for_template("x", sample_template) == (
            AgentManagementClient._is_available(sample_template, "x")
        )


# ------------------------------------------------------------------
# available_to validation in create_agent_template
# ------------------------------------------------------------------


class TestAvailableToValidationOnCreate:
    def test_rejects_empty_list(self, mgmt):
        with pytest.raises(ValueError, match="non-empty list"):
            mgmt.create_agent_template(
                name="Bad",
                agent_type="bad_agent",
                description="Bad",
                system_prompt="Bad",
                available_to=[],
            )

    def test_rejects_non_string_entries(self, mgmt):
        with pytest.raises(ValueError, match="non-empty string"):
            mgmt.create_agent_template(
                name="Bad",
                agent_type="bad_agent",
                description="Bad",
                system_prompt="Bad",
                available_to=["user-1", ""],
            )

    def test_rejects_invalid_type(self, mgmt):
        with pytest.raises(ValueError, match="non-empty list"):
            mgmt.create_agent_template(
                name="Bad",
                agent_type="bad_agent",
                description="Bad",
                system_prompt="Bad",
                available_to=42,
            )

    def test_accepts_all_string(self, mgmt):
        t = mgmt.create_agent_template(
            name="OK",
            agent_type="ok_agent",
            description="OK",
            system_prompt="OK",
            available_to="all",
        )
        assert t.available_to == "all"

    def test_accepts_valid_user_list(self, mgmt):
        t = mgmt.create_agent_template(
            name="OK",
            agent_type="ok_agent",
            description="OK",
            system_prompt="OK",
            available_to=["user-1", "user-2"],
        )
        assert t.available_to == ["user-1", "user-2"]


# ------------------------------------------------------------------
# available_to validation in update_template
# ------------------------------------------------------------------


class TestAvailableToValidationOnUpdate:
    def test_rejects_empty_list_on_update(self, mgmt, sample_template):
        with pytest.raises(ValueError, match="non-empty list"):
            mgmt.update_template(sample_template.template_id, available_to=[])

    def test_rejects_invalid_type_on_update(self, mgmt, sample_template):
        with pytest.raises(ValueError, match="non-empty list"):
            mgmt.update_template(sample_template.template_id, available_to=123)

    def test_accepts_valid_update(self, mgmt, sample_template):
        updated = mgmt.update_template(
            sample_template.template_id, available_to=["user-1"]
        )
        assert updated.available_to == ["user-1"]


# ------------------------------------------------------------------
# build_sub_agent_tool_ids
# ------------------------------------------------------------------


class TestBuildSubAgentToolIds:
    def test_returns_empty_for_no_configs(self, mgmt):
        assert mgmt.build_sub_agent_tool_ids("user-1") == []

    def test_returns_tool_ids_for_enabled_authorized_configs(self, mgmt):
        mgmt.create_agent_template(
            name="A", agent_type="agent_a", description="A", system_prompt="A",
        )
        mgmt.create_agent_template(
            name="B", agent_type="agent_b", description="B", system_prompt="B",
        )
        mgmt.put_user_agent_config(user_id="user-1", agent_type="agent_a")
        mgmt.put_user_agent_config(user_id="user-1", agent_type="agent_b")
        tool_ids = mgmt.build_sub_agent_tool_ids("user-1")
        assert tool_ids == ["gw-tool-agent_a", "gw-tool-agent_b"]

    def test_excludes_disabled_configs(self, mgmt):
        mgmt.create_agent_template(
            name="A", agent_type="agent_a", description="A", system_prompt="A",
        )
        mgmt.put_user_agent_config(
            user_id="user-1", agent_type="agent_a", enabled=False,
        )
        assert mgmt.build_sub_agent_tool_ids("user-1") == []

    def test_excludes_unauthorized_configs(self, mgmt):
        """When available_to is updated to remove a user, their tool is excluded."""
        mgmt.create_agent_template(
            name="A",
            agent_type="agent_a",
            description="A",
            system_prompt="A",
            available_to=["user-1", "user-2"],
        )
        mgmt.put_user_agent_config(user_id="user-1", agent_type="agent_a")
        mgmt.put_user_agent_config(user_id="user-2", agent_type="agent_a")

        # Both users should have tool IDs
        assert len(mgmt.build_sub_agent_tool_ids("user-1")) == 1
        assert len(mgmt.build_sub_agent_tool_ids("user-2")) == 1

        # Update available_to to remove user-2
        template = mgmt.get_template_by_type("agent_a")
        mgmt.update_template(template.template_id, available_to=["user-1"])

        # user-1 still has tool, user-2 excluded (config still exists)
        assert mgmt.build_sub_agent_tool_ids("user-1") == ["gw-tool-agent_a"]
        assert mgmt.build_sub_agent_tool_ids("user-2") == []

        # Verify user-2's config still exists (not deleted)
        cfg = mgmt.get_user_agent_config("user-2", "agent_a")
        assert cfg is not None

    def test_skips_configs_with_missing_templates(self, mgmt, sample_template):
        """Configs referencing deleted templates are skipped."""
        mgmt.put_user_agent_config(user_id="user-1", agent_type="meal_planner")

        # Directly delete the template from DynamoDB (bypass cascade for test)
        mgmt._templates_table.delete_item(
            Key={"template_id": sample_template.template_id}
        )

        assert mgmt.build_sub_agent_tool_ids("user-1") == []

    def test_sorted_by_agent_type(self, mgmt):
        """Tool IDs are returned sorted by agent_type."""
        mgmt.create_agent_template(
            name="Z", agent_type="z_agent", description="Z", system_prompt="Z",
        )
        mgmt.create_agent_template(
            name="A", agent_type="a_agent", description="A", system_prompt="A",
        )
        mgmt.put_user_agent_config(user_id="user-1", agent_type="z_agent")
        mgmt.put_user_agent_config(user_id="user-1", agent_type="a_agent")
        tool_ids = mgmt.build_sub_agent_tool_ids("user-1")
        assert tool_ids == ["gw-tool-a_agent", "gw-tool-z_agent"]

    def test_mixed_enabled_disabled_authorized_unauthorized(self, mgmt):
        """Only enabled AND authorized configs produce tool IDs."""
        mgmt.create_agent_template(
            name="Public", agent_type="public_agent",
            description="Public", system_prompt="P", available_to="all",
        )
        mgmt.create_agent_template(
            name="VIP", agent_type="vip_agent",
            description="VIP", system_prompt="V", available_to=["user-1"],
        )
        # user-1: enabled public + enabled VIP
        mgmt.put_user_agent_config(user_id="user-1", agent_type="public_agent")
        mgmt.put_user_agent_config(user_id="user-1", agent_type="vip_agent")

        tool_ids = mgmt.build_sub_agent_tool_ids("user-1")
        assert tool_ids == ["gw-tool-public_agent", "gw-tool-vip_agent"]

        # user-2: enabled public only (not authorized for VIP)
        mgmt.put_user_agent_config(user_id="user-2", agent_type="public_agent")
        tool_ids = mgmt.build_sub_agent_tool_ids("user-2")
        assert tool_ids == ["gw-tool-public_agent"]

# ------------------------------------------------------------------
# Admin-only cross-user configuration (Requirement 7.1, 7.2, 7.3)
# ------------------------------------------------------------------


class TestAdminCrossUserPutConfig:
    """Cross-user put_user_agent_config requires admin role."""

    def test_self_modification_no_requesting_user(self, mgmt, sample_template):
        """Users can modify their own config when requesting_user_id is None."""
        cfg = mgmt.put_user_agent_config(
            user_id="user-1",
            agent_type="meal_planner",
        )
        assert cfg.user_id == "user-1"

    def test_self_modification_same_user(self, mgmt, sample_template):
        """Users can modify their own config when requesting_user_id == user_id."""
        cfg = mgmt.put_user_agent_config(
            user_id="user-1",
            agent_type="meal_planner",
            requesting_user_id="user-1",
            requesting_user_role="member",
        )
        assert cfg.user_id == "user-1"

    def test_admin_cross_user_succeeds(self, mgmt, sample_template):
        """Admin can modify another user's config."""
        cfg = mgmt.put_user_agent_config(
            user_id="user-2",
            agent_type="meal_planner",
            requesting_user_id="admin-1",
            requesting_user_role="admin",
        )
        assert cfg.user_id == "user-2"
        assert cfg.agent_type == "meal_planner"

    def test_non_admin_cross_user_rejected(self, mgmt, sample_template):
        """Non-admin cross-user modification raises PermissionError."""
        with pytest.raises(PermissionError, match="Admin role required"):
            mgmt.put_user_agent_config(
                user_id="user-2",
                agent_type="meal_planner",
                requesting_user_id="user-1",
                requesting_user_role="member",
            )

    def test_non_admin_cross_user_no_role(self, mgmt, sample_template):
        """Cross-user with no role raises PermissionError."""
        with pytest.raises(PermissionError, match="Admin role required"):
            mgmt.put_user_agent_config(
                user_id="user-2",
                agent_type="meal_planner",
                requesting_user_id="user-1",
                requesting_user_role=None,
            )

    def test_self_modification_any_role_allowed(self, mgmt, sample_template):
        """Self-modification works regardless of role."""
        for role in ("member", "admin", None):
            cfg = mgmt.put_user_agent_config(
                user_id="user-1",
                agent_type="meal_planner",
                requesting_user_id="user-1",
                requesting_user_role=role,
            )
            assert cfg.user_id == "user-1"


class TestAdminCrossUserDeleteConfig:
    """Cross-user delete_user_agent_config requires admin role."""

    def test_self_deletion_no_requesting_user(self, mgmt, sample_template):
        """Users can delete their own config when requesting_user_id is None."""
        mgmt.put_user_agent_config(user_id="user-1", agent_type="meal_planner")
        result = mgmt.delete_user_agent_config(
            user_id="user-1", agent_type="meal_planner"
        )
        assert result is True

    def test_self_deletion_same_user(self, mgmt, sample_template):
        """Users can delete their own config when requesting_user_id == user_id."""
        mgmt.put_user_agent_config(user_id="user-1", agent_type="meal_planner")
        result = mgmt.delete_user_agent_config(
            user_id="user-1",
            agent_type="meal_planner",
            requesting_user_id="user-1",
            requesting_user_role="member",
        )
        assert result is True

    def test_admin_cross_user_delete_succeeds(self, mgmt, sample_template):
        """Admin can delete another user's config."""
        mgmt.put_user_agent_config(user_id="user-2", agent_type="meal_planner")
        result = mgmt.delete_user_agent_config(
            user_id="user-2",
            agent_type="meal_planner",
            requesting_user_id="admin-1",
            requesting_user_role="admin",
        )
        assert result is True
        assert mgmt.get_user_agent_config("user-2", "meal_planner") is None

    def test_non_admin_cross_user_delete_rejected(self, mgmt, sample_template):
        """Non-admin cross-user deletion raises PermissionError."""
        mgmt.put_user_agent_config(user_id="user-2", agent_type="meal_planner")
        with pytest.raises(PermissionError, match="Admin role required"):
            mgmt.delete_user_agent_config(
                user_id="user-2",
                agent_type="meal_planner",
                requesting_user_id="user-1",
                requesting_user_role="member",
            )
        # Config should still exist
        assert mgmt.get_user_agent_config("user-2", "meal_planner") is not None

    def test_non_admin_cross_user_delete_no_role(self, mgmt, sample_template):
        """Cross-user delete with no role raises PermissionError."""
        mgmt.put_user_agent_config(user_id="user-2", agent_type="meal_planner")
        with pytest.raises(PermissionError, match="Admin role required"):
            mgmt.delete_user_agent_config(
                user_id="user-2",
                agent_type="meal_planner",
                requesting_user_id="user-1",
                requesting_user_role=None,
            )

    def test_self_deletion_any_role_allowed(self, mgmt, sample_template):
        """Self-deletion works regardless of role."""
        for role in ("member", "admin", None):
            mgmt.put_user_agent_config(
                user_id="user-1", agent_type="meal_planner"
            )
            result = mgmt.delete_user_agent_config(
                user_id="user-1",
                agent_type="meal_planner",
                requesting_user_id="user-1",
                requesting_user_role=role,
            )
            assert result is True


class TestBuildSubAgentToolIdsCache:
    """Tests for the 60-second TTL cache on build_sub_agent_tool_ids."""

    def test_cache_returns_same_result_on_second_call(self, mgmt, sample_template):
        """Second call within TTL returns cached result without recomputing."""
        mgmt.put_user_agent_config(user_id="user-1", agent_type="meal_planner")
        first = mgmt.build_sub_agent_tool_ids("user-1")
        second = mgmt.build_sub_agent_tool_ids("user-1")
        assert first == second

    def test_cache_hit_does_not_query_dynamo(self, mgmt, sample_template):
        """After caching, subsequent calls don't hit get_user_agent_configs."""
        mgmt.put_user_agent_config(user_id="user-1", agent_type="meal_planner")
        mgmt.build_sub_agent_tool_ids("user-1")

        # Replace get_user_agent_configs with a sentinel that would fail
        original = mgmt.get_user_agent_configs
        call_count = 0

        def counting_get(uid):
            nonlocal call_count
            call_count += 1
            return original(uid)

        mgmt.get_user_agent_configs = counting_get
        mgmt.build_sub_agent_tool_ids("user-1")
        assert call_count == 0, "Cache hit should not call get_user_agent_configs"

    def test_cache_expires_after_ttl(self, mgmt, sample_template):
        """After TTL expires, the cache recomputes."""
        import time as _time
        from unittest.mock import patch

        mgmt.put_user_agent_config(user_id="user-1", agent_type="meal_planner")

        # First call — populates cache
        base_time = _time.monotonic()
        with patch("time.monotonic", return_value=base_time):
            first = mgmt.build_sub_agent_tool_ids("user-1")

        # Advance time past TTL (61 seconds)
        with patch("time.monotonic", return_value=base_time + 61):
            second = mgmt.build_sub_agent_tool_ids("user-1")

        assert first == second  # same result, but recomputed

    def test_cache_invalidated_on_put_config(self, mgmt, sample_template):
        """put_user_agent_config invalidates the cache for that user."""
        mgmt.put_user_agent_config(user_id="user-1", agent_type="meal_planner")
        mgmt.build_sub_agent_tool_ids("user-1")
        assert "user-1" in mgmt._tool_cache

        # Disable the agent — this calls put_user_agent_config which invalidates
        mgmt.put_user_agent_config(
            user_id="user-1", agent_type="meal_planner", enabled=False
        )
        assert "user-1" not in mgmt._tool_cache

    def test_cache_invalidated_on_delete_config(self, mgmt, sample_template):
        """delete_user_agent_config invalidates the cache for that user."""
        mgmt.put_user_agent_config(user_id="user-1", agent_type="meal_planner")
        mgmt.build_sub_agent_tool_ids("user-1")
        assert "user-1" in mgmt._tool_cache

        mgmt.delete_user_agent_config(user_id="user-1", agent_type="meal_planner")
        assert "user-1" not in mgmt._tool_cache

    def test_invalidate_tool_cache_no_op_for_unknown_user(self, mgmt):
        """invalidate_tool_cache does not raise for a user not in cache."""
        mgmt.invalidate_tool_cache("nonexistent-user")  # should not raise

    def test_cache_is_per_user(self, mgmt, sample_template):
        """Cache entries are scoped per user_id."""
        mgmt.put_user_agent_config(user_id="user-1", agent_type="meal_planner")
        mgmt.put_user_agent_config(user_id="user-2", agent_type="meal_planner")

        mgmt.build_sub_agent_tool_ids("user-1")
        mgmt.build_sub_agent_tool_ids("user-2")

        assert "user-1" in mgmt._tool_cache
        assert "user-2" in mgmt._tool_cache

        # Invalidating user-1 doesn't affect user-2
        mgmt.invalidate_tool_cache("user-1")
        assert "user-1" not in mgmt._tool_cache
        assert "user-2" in mgmt._tool_cache

    def test_cache_returns_copy_not_reference(self, mgmt, sample_template):
        """Cached result is a copy so mutations don't corrupt the cache."""
        mgmt.put_user_agent_config(user_id="user-1", agent_type="meal_planner")
        first = mgmt.build_sub_agent_tool_ids("user-1")
        first.append("injected-tool")

        second = mgmt.build_sub_agent_tool_ids("user-1")
        assert "injected-tool" not in second

    def test_cache_reflects_config_changes_after_invalidation(
        self, mgmt, sample_template
    ):
        """After invalidation, next call reflects the updated config state."""
        mgmt.put_user_agent_config(user_id="user-1", agent_type="meal_planner")
        result_before = mgmt.build_sub_agent_tool_ids("user-1")
        assert len(result_before) == 1

        # Disable the agent (invalidates cache) then rebuild
        mgmt.put_user_agent_config(
            user_id="user-1", agent_type="meal_planner", enabled=False
        )
        result_after = mgmt.build_sub_agent_tool_ids("user-1")
        assert len(result_after) == 0
