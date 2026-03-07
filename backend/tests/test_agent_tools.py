"""Tests for the default agent tools (time and search)."""

from unittest.mock import patch, MagicMock

import pytest


class TestCurrentTimeTool:
    """Tests for the current_time tool re-export."""

    def test_import(self):
        from app.agents.time_tool import get_current_time

        assert get_current_time is not None

    def test_is_strands_tool(self):
        from app.agents.time_tool import get_current_time
        from strands.tools.decorator import DecoratedFunctionTool

        assert isinstance(get_current_time, DecoratedFunctionTool)


class TestWebSearchTool:
    """Tests for the web_search tool."""

    def test_import(self):
        from app.agents.search_tool import web_search

        assert web_search is not None

    @patch("app.agents.search_tool.requests.get")
    def test_search_request_failure_no_query_leak(self, mock_get):
        from app.agents.search_tool import web_search

        mock_get.side_effect = Exception("Network error")
        result = web_search.fn(query="sensitive health query", max_results=3)
        assert "temporarily unavailable" in result.lower()
        assert "sensitive health query" not in result

    @patch("app.agents.search_tool.requests.get")
    def test_search_no_results(self, mock_get):
        from app.agents.search_tool import web_search

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = "<html><body>No results</body></html>"
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        result = web_search.fn(query="xyznonexistent", max_results=3)
        assert "No results" in result

    @patch("app.agents.search_tool.requests.get")
    def test_search_parses_results(self, mock_get):
        from app.agents.search_tool import web_search

        html = """
        <html><body>
        <a class="result__a" href="https://example.com">Example Title</a>
        <a class="result__snippet">This is a snippet about the topic.</a>
        </body></html>
        """
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = html
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        result = web_search.fn(query="test", max_results=5)
        assert "Example Title" in result
        assert "snippet about the topic" in result


class TestDefaultToolsIntegration:
    """Tests for default tools being included in the agent orchestrator."""

    def test_system_prompt_includes_time_without_profile(self, app):
        with app.app_context():
            from app.services.agent_orchestrator import _build_system_prompt

            prompt = _build_system_prompt("nonexistent-user", "Base prompt.")
            assert "Current date and time:" in prompt
            assert "Base prompt." in prompt

    def test_system_prompt_includes_time_with_profile(self, app):
        with app.app_context():
            from app.services.profile import create_profile

            create_profile("tool-test-user", "TestUser")
            from app.services.agent_orchestrator import _build_system_prompt

            prompt = _build_system_prompt("tool-test-user", "Base prompt.")
            assert "Current date and time:" in prompt
            assert "TestUser" in prompt

    def test_web_search_disabled_excludes_from_tools(self, app):
        app.config["WEB_SEARCH_ENABLED"] = False
        with app.app_context():
            from app.agents.search_tool import web_search
            from app.agents.time_tool import get_current_time

            default_tools = [get_current_time]
            if app.config.get("WEB_SEARCH_ENABLED", True):
                default_tools.append(web_search)

            assert len(default_tools) == 1
            assert default_tools[0] is get_current_time
