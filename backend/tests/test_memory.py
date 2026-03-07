"""Tests for memory sharing configuration and family shared context."""

import pytest
from unittest.mock import patch, MagicMock


@pytest.fixture
def app():
    from app import create_app
    from app.config import Config

    config = Config()
    config.DYNAMODB_ENDPOINT = "http://localhost:8000"
    config.ADMIN_INVITE_CODE = None
    app = create_app(config)
    return app


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def auth_headers():
    return {"Authorization": "Bearer test-token"}


class TestSharingConfigService:
    """Tests for family_memory service functions."""

    def test_get_default_sharing_config(self, app):
        with app.app_context():
            from app.services.family_memory import get_sharing_config

            config = get_sharing_config("nonexistent-user")
            assert config["user_id"] == "nonexistent-user"
            assert config["share_profile"] is True
            assert config["share_interests"] is True
            assert config["share_health_notes"] is False
            assert config["sharing_level"] == "basic"

    def test_update_sharing_config(self, app):
        with app.app_context():
            from app.services.family_memory import (
                get_sharing_config,
                update_sharing_config,
            )

            result = update_sharing_config("test-user", {
                "share_health_notes": True,
                "sharing_level": "full",
            })
            assert result["share_health_notes"] is True
            assert result["sharing_level"] == "full"

            # Verify persistence
            fetched = get_sharing_config("test-user")
            assert fetched["share_health_notes"] is True

    def test_update_invalid_sharing_level(self, app):
        with app.app_context():
            from app.services.family_memory import update_sharing_config

            with pytest.raises(ValueError, match="sharing_level"):
                update_sharing_config("test-user", {"sharing_level": "invalid"})

    def test_update_ignores_unknown_fields(self, app):
        with app.app_context():
            from app.services.family_memory import update_sharing_config

            result = update_sharing_config("test-user", {
                "unknown_field": "value",
                "share_profile": False,
            })
            assert result["share_profile"] is False
            assert "unknown_field" not in result


class TestFamilySharedContext:
    """Tests for family shared context building."""

    def test_no_family_returns_empty(self, app):
        with app.app_context():
            from app.services.family_memory import get_family_shared_context

            result = get_family_shared_context("orphan-user")
            assert result == ""

    @patch("app.services.family_memory._get_family_member_ids")
    @patch("app.services.family_memory.get_profile")
    def test_builds_context_from_shared_profiles(
        self, mock_profile, mock_members, app
    ):
        mock_members.return_value = ["member-2", "member-3"]
        mock_profile.side_effect = lambda uid: {
            "member-2": {
                "display_name": "Alice",
                "family_role": "Mother",
                "interests": ["cooking", "yoga"],
                "health_notes": "Allergic to peanuts",
            },
            "member-3": {
                "display_name": "Bob",
                "family_role": "Father",
                "interests": ["running"],
                "health_notes": "",
            },
        }.get(uid)

        with app.app_context():
            from app.services.family_memory import (
                get_family_shared_context,
                update_sharing_config,
            )

            # Set Alice to share everything
            update_sharing_config("member-2", {
                "share_profile": True,
                "share_interests": True,
                "share_health_notes": True,
                "sharing_level": "full",
            })
            # Bob shares basic
            update_sharing_config("member-3", {
                "share_profile": True,
                "share_interests": True,
                "sharing_level": "basic",
            })

            context = get_family_shared_context("member-1")
            assert "Alice" in context
            assert "Mother" in context
            assert "cooking" in context
            assert "Bob" in context
            assert "running" in context

    @patch("app.services.family_memory._get_family_member_ids")
    @patch("app.services.family_memory.get_profile")
    def test_respects_none_sharing_level(
        self, mock_profile, mock_members, app
    ):
        mock_members.return_value = ["member-2"]
        mock_profile.return_value = {
            "display_name": "Alice",
            "family_role": "Mother",
            "interests": ["cooking"],
        }

        with app.app_context():
            from app.services.family_memory import (
                get_family_shared_context,
                update_sharing_config,
            )

            update_sharing_config("member-2", {"sharing_level": "none"})
            context = get_family_shared_context("member-1")
            assert context == ""


class TestMemoryRetrieval:
    """Tests for AgentCore memory retrieval (graceful degradation)."""

    def test_returns_empty_when_no_memory_id(self, app):
        with app.app_context():
            from app.services.memory import retrieve_long_term_memories

            app.config["AGENTCORE_MEMORY_ID"] = None
            result = retrieve_long_term_memories("user-1", "test query")
            assert result == ""

    @patch("app.services.memory.current_app")
    def test_returns_empty_when_import_fails(self, mock_app):
        mock_app.config = {"AGENTCORE_MEMORY_ID": "mem-123", "AWS_REGION": "us-east-1"}
        from app.services.memory import retrieve_long_term_memories

        # bedrock_agentcore is not installed, should gracefully return empty
        result = retrieve_long_term_memories("user-1", "test query")
        assert result == ""
