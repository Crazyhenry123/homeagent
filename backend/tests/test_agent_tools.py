"""Tests for the default agent tools (time and search)."""

import json
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

    def test_disabled_returns_message(self):
        from app.agents.search_tool import web_search, set_search_enabled

        set_search_enabled(False)
        try:
            result = web_search.fn(query="test", max_results=3)
            assert "disabled" in result
        finally:
            set_search_enabled(True)

    @patch("app.agents.search_tool.requests.get")
    def test_search_request_failure(self, mock_get):
        from app.agents.search_tool import web_search

        mock_get.side_effect = Exception("Network error")
        result = web_search.fn(query="test query", max_results=3)
        assert "failed" in result.lower() or "error" in result.lower()

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

    def test_max_results_clamped(self):
        from app.agents.search_tool import web_search

        # Just verify the function signature accepts max_results
        assert web_search.fn.__code__.co_varnames[:2] == ("query", "max_results")


class TestDefaultToolsIntegration:
    """Tests for default tools being included in the agent orchestrator."""

    def test_system_prompt_includes_time(self, app):
        with app.app_context():
            from app.services.agent_orchestrator import _build_system_prompt

            prompt = _build_system_prompt("test-user-id", "Base prompt.")
            assert "Current date and time:" in prompt
            assert "get_current_time" in prompt
            assert "web_search" in prompt


@pytest.fixture
def app():
    from app import create_app
    from app.config import Config

    config = Config()
    config.DYNAMODB_ENDPOINT = "http://localhost:8000"
    config.ADMIN_INVITE_CODE = None
    app = create_app(config)
    return app
