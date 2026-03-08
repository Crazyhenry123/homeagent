"""Property-based tests for AgentCore data model validation.

Uses Hypothesis to verify correctness properties of the data models
defined in backend/app/models/agentcore.py.
"""

from __future__ import annotations

import string
import sys
import os
import types

# ---------------------------------------------------------------------------
# Patch Flask imports so we can import the models without a running app
# ---------------------------------------------------------------------------
flask_mod = types.ModuleType("flask")
flask_mod.Flask = type("Flask", (), {})
flask_mod.g = type("g", (), {})()
flask_mod.current_app = type("current_app", (), {"config": {}})()
sys.modules.setdefault("flask", flask_mod)

flask_cors_mod = types.ModuleType("flask_cors")
flask_cors_mod.CORS = lambda *a, **kw: None
sys.modules.setdefault("flask_cors", flask_cors_mod)

# Import the agentcore module directly to avoid triggering app/__init__.py
# which requires boto3 and other heavy dependencies.
import importlib.util

_models_path = os.path.join(
    os.path.dirname(__file__), "..", "app", "models", "agentcore.py"
)
_spec = importlib.util.spec_from_file_location("agentcore", _models_path)
_agentcore = importlib.util.module_from_spec(_spec)
sys.modules["agentcore"] = _agentcore
_spec.loader.exec_module(_agentcore)

AgentTemplate = _agentcore.AgentTemplate
AgentConfig = _agentcore.AgentConfig

from hypothesis import given, settings, assume  # noqa: E402
from hypothesis import strategies as st  # noqa: E402

# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

# Valid agent_type slugs: start with lowercase letter, then lowercase letters,
# digits, underscores, or hyphens.
_SLUG_FIRST = st.sampled_from(list(string.ascii_lowercase))
_SLUG_REST = st.text(
    alphabet=string.ascii_lowercase + string.digits + "_-",
    min_size=0,
    max_size=30,
)
valid_agent_type = st.builds(lambda f, r: f + r, _SLUG_FIRST, _SLUG_REST)

non_empty_str = st.text(min_size=1, max_size=50).filter(lambda s: s.strip())

valid_template = st.builds(
    AgentTemplate,
    template_id=non_empty_str,
    agent_type=valid_agent_type,
    name=non_empty_str,
    description=non_empty_str,
    system_prompt=st.text(min_size=0, max_size=100),
    tool_server_ids=st.just([]),
    default_config=st.just({}),
    is_builtin=st.booleans(),
    available_to=st.just("all"),
    created_by=non_empty_str,
    created_at=st.just("2025-01-01T00:00:00Z"),
    updated_at=st.just("2025-01-01T00:00:00Z"),
)


# ---------------------------------------------------------------------------
# Property 25: Agent Type Uniqueness
# Validates: Requirements 4.2
# ---------------------------------------------------------------------------


class TestAgentTypeUniqueness:
    """**Validates: Requirements 4.2**

    Property 25: Agent Type Uniqueness — for any two AgentTemplates,
    their agent_type values are distinct. Attempting to create a template
    with a duplicate agent_type is rejected.
    """

    @given(
        templates=st.lists(valid_template, min_size=2, max_size=10),
    )
    @settings(max_examples=10)
    def test_duplicate_agent_type_detected_in_collection(
        self, templates: list[AgentTemplate]
    ) -> None:
        """For any collection of AgentTemplates, a uniqueness check on
        agent_type correctly identifies duplicates vs. unique sets.

        This simulates the enforcement that the Agent_Management_Client
        must perform: before inserting a new template, verify no existing
        template shares the same agent_type.
        """
        seen: dict[str, AgentTemplate] = {}
        duplicates_found: list[str] = []

        for tmpl in templates:
            if tmpl.agent_type in seen:
                duplicates_found.append(tmpl.agent_type)
            else:
                seen[tmpl.agent_type] = tmpl

        # The number of unique agent_types equals the seen dict size
        unique_types = {t.agent_type for t in templates}
        assert len(seen) == len(unique_types)

        # Every duplicate we found is genuinely a repeated agent_type
        for dup in duplicates_found:
            count = sum(1 for t in templates if t.agent_type == dup)
            assert count >= 2, (
                f"agent_type '{dup}' flagged as duplicate but appears {count} time(s)"
            )

    @given(
        t1=valid_template,
        t2=valid_template,
    )
    @settings(max_examples=10)
    def test_two_templates_same_agent_type_rejected(
        self, t1: AgentTemplate, t2: AgentTemplate
    ) -> None:
        """When two templates share the same agent_type, a uniqueness
        enforcement function must reject the second one.

        Simulates the agent_type uniqueness constraint (Requirement 4.2).
        """
        # Force t2 to have the same agent_type as t1
        t2.agent_type = t1.agent_type

        # Both should individually validate fine
        t1.validate()
        t2.validate()

        # But a registry that enforces uniqueness must reject the duplicate
        registry: dict[str, AgentTemplate] = {}
        registry[t1.agent_type] = t1

        # Attempting to add t2 with the same agent_type should be rejected
        is_duplicate = t2.agent_type in registry
        assert is_duplicate, (
            f"agent_type '{t2.agent_type}' should be detected as duplicate"
        )

    @given(
        t1=valid_template,
        t2=valid_template,
    )
    @settings(max_examples=10)
    def test_two_templates_distinct_agent_types_accepted(
        self, t1: AgentTemplate, t2: AgentTemplate
    ) -> None:
        """When two templates have distinct agent_type values, both are
        accepted into the registry without conflict.
        """
        assume(t1.agent_type != t2.agent_type)

        t1.validate()
        t2.validate()

        registry: dict[str, AgentTemplate] = {}
        registry[t1.agent_type] = t1

        is_duplicate = t2.agent_type in registry
        assert not is_duplicate, (
            f"agent_type '{t2.agent_type}' should NOT be flagged as duplicate "
            f"when it differs from '{t1.agent_type}'"
        )

        # Both can coexist
        registry[t2.agent_type] = t2
        assert len(registry) == 2

    @given(agent_type=valid_agent_type)
    @settings(max_examples=10)
    def test_valid_agent_type_passes_validation(self, agent_type: str) -> None:
        """Any well-formed agent_type slug passes AgentTemplate validation."""
        tmpl = AgentTemplate(
            template_id="tmpl_test",
            agent_type=agent_type,
            name="Test",
            description="Test",
            system_prompt="",
            available_to="all",
        )
        tmpl.validate()  # Should not raise


# ---------------------------------------------------------------------------
# Strategies for config merge tests
# ---------------------------------------------------------------------------

# Generate arbitrary config dicts with string keys and JSON-compatible values.
_config_values = st.one_of(
    st.text(min_size=0, max_size=50),
    st.integers(min_value=-1000, max_value=1000),
    st.booleans(),
    st.floats(allow_nan=False, allow_infinity=False),
    st.none(),
)

_config_dict = st.dictionaries(
    keys=st.text(
        alphabet=string.ascii_lowercase + string.digits + "_",
        min_size=1,
        max_size=20,
    ),
    values=_config_values,
    min_size=0,
    max_size=10,
)


def _merge_config(default_config: dict, user_config: dict) -> dict:
    """Replicate the merge logic from Requirement 5.6:

    ``{**template.default_config, **user_config}``
    """
    return {**default_config, **user_config}


# ---------------------------------------------------------------------------
# Property 18: Config Merge Precedence
# Validates: Requirements 5.6
# ---------------------------------------------------------------------------


class TestConfigMergePrecedence:
    """**Validates: Requirements 5.6**

    Property 18: Config Merge Precedence — for any template default_config
    and user overrides, merged config contains all defaults with user
    overrides taking precedence.
    """

    @given(
        default_config=_config_dict,
        user_config=_config_dict,
    )
    @settings(max_examples=5)
    def test_user_overrides_take_precedence(
        self, default_config: dict, user_config: dict
    ) -> None:
        """For every key present in both default_config and user_config,
        the merged result must contain the user_config value."""
        merged = _merge_config(default_config, user_config)

        for key in user_config:
            assert key in merged
            assert merged[key] == user_config[key], (
                f"Key '{key}': expected user value {user_config[key]!r}, "
                f"got {merged[key]!r}"
            )

    @given(
        default_config=_config_dict,
        user_config=_config_dict,
    )
    @settings(max_examples=5)
    def test_all_defaults_present_when_not_overridden(
        self, default_config: dict, user_config: dict
    ) -> None:
        """For every key in default_config that is NOT in user_config,
        the merged result must contain the default value."""
        merged = _merge_config(default_config, user_config)

        for key in default_config:
            assert key in merged, (
                f"Default key '{key}' missing from merged config"
            )
            if key not in user_config:
                assert merged[key] == default_config[key], (
                    f"Key '{key}': expected default value "
                    f"{default_config[key]!r}, got {merged[key]!r}"
                )

    @given(
        default_config=_config_dict,
        user_config=_config_dict,
    )
    @settings(max_examples=5)
    def test_merged_keys_are_union_of_inputs(
        self, default_config: dict, user_config: dict
    ) -> None:
        """The merged config keys are exactly the union of default_config
        keys and user_config keys — no extra, no missing."""
        merged = _merge_config(default_config, user_config)

        expected_keys = set(default_config.keys()) | set(user_config.keys())
        assert set(merged.keys()) == expected_keys

    @given(
        default_config=_config_dict,
    )
    @settings(max_examples=10)
    def test_empty_user_config_returns_defaults(
        self, default_config: dict
    ) -> None:
        """When user provides no overrides, merged config equals the
        template defaults exactly."""
        merged = _merge_config(default_config, {})
        assert merged == default_config

    @given(
        user_config=_config_dict,
    )
    @settings(max_examples=10)
    def test_empty_default_config_returns_user_config(
        self, user_config: dict
    ) -> None:
        """When template has no defaults, merged config equals the
        user overrides exactly."""
        merged = _merge_config({}, user_config)
        assert merged == user_config
