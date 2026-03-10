"""Unit tests for the integrated chat isolation flow.
Validates: Requirements 1.4, 3.1, 8.1
"""
from __future__ import annotations
import json
from functools import wraps
from unittest.mock import MagicMock, patch
import pytest
from app.models.agentcore import CombinedSessionManager, IsolatedContext, MemoryConfig
from app.services.isolation_middleware import AccessDeniedError


def _fake_stream(*_a, **_kw):
    yield {"type": "text_delta", "content": "Hi"}
    yield {"type": "message_done", "content": "Hi"}


def _combined(sid="store-xyz"):
    return CombinedSessionManager(
        family_config=MemoryConfig(memory_id=sid, session_id="s1", actor_id="fam-abc"),
        member_config=MemoryConfig(memory_id="mem-store", session_id="s1", actor_id="u1"),
        family_id="fam-abc", member_id="u1", session_id="s1",
    )


_INIT_PATCHES = [
    "app.services.agentcore_runtime.AgentCoreRuntimeClient.__init__",
    "app.services.agent_management.AgentManagementClient.__init__",
    "app.services.agentcore_memory.AgentCoreMemoryManager.__init__",
]


def test_active_store_uses_isolated_config():
    """When family_id is set and the store is active,
    _get_agentcore_chat_stream passes a CombinedSessionManager with
    family_config.memory_id equal to the per-family store_id.

    Validates: Requirements 3.1, 8.1
    """
    ctx = IsolatedContext(
        family_id="fam-abc", member_id="u1", family_store_id="store-xyz",
        is_verified=True, store_status="active",
        verified_at="2025-01-01T00:00:00+00:00",
    )
    csm = _combined("store-xyz")
    mock_mw = MagicMock()
    mock_mw.validate_and_resolve.return_value = ctx
    mock_iso = MagicMock()
    mock_iso.safe_build_isolated_memory_config.return_value = csm

    # boto3 is lazily imported inside the function body, so we need
    # create=True to patch it on the module before it exists there.
    patches = (
        [
            patch("app.routes.chat.boto3", create=True),
            patch("app.services.family_memory_registry.FamilyMemoryStoreRegistry"),
            patch("app.services.memory_write_behind_buffer.MemoryWriteBehindBuffer"),
        ]
        + [patch(p, return_value=None) for p in _INIT_PATCHES]
        + [
            patch(
                "app.services.isolation_middleware.IsolationMiddleware",
                return_value=mock_mw,
            ),
            patch(
                "app.services.isolated_memory_manager.IsolatedMemoryManager",
                return_value=mock_iso,
            ),
            patch(
                "app.services.agentcore_integration.stream_agent_chat_v2",
                side_effect=_fake_stream,
            ),
        ]
    )
    mocks = [p.start() for p in patches]
    try:
        from app.routes.chat import _get_agentcore_chat_stream

        gen = _get_agentcore_chat_stream(
            messages=[{"role": "user", "content": "Hello"}],
            user_id="u1", family_id="fam-abc", conversation_id="conv-1",
        )
        list(gen)

        mock_mw.validate_and_resolve.assert_called_once_with("fam-abc", "u1")
        mock_iso.safe_build_isolated_memory_config.assert_called_once_with(
            ctx, "conv-1"
        )
        # stream_agent_chat_v2 is the last patch
        mock_stream = mocks[-1]
        mock_stream.assert_called_once()
        kw = mock_stream.call_args.kwargs
        assert kw["isolated_memory_config"] is csm
        assert kw["isolated_memory_config"].family_config.memory_id == "store-xyz"
    finally:
        for p in patches:
            p.stop()


def test_pending_store_proceeds_without_family_memory():
    """When store_status is 'pending', stream_agent_chat_v2 is called with
    isolated_memory_config=None and the chat proceeds normally.

    Validates: Requirement 8.1
    """
    ctx = IsolatedContext(
        family_id="fam-new", member_id="u1", family_store_id=None,
        is_verified=True, store_status="pending",
        verified_at="2025-01-01T00:00:00+00:00",
    )
    mock_mw = MagicMock()
    mock_mw.validate_and_resolve.return_value = ctx

    patches = (
        [
            patch("app.routes.chat.boto3", create=True),
            patch("app.services.family_memory_registry.FamilyMemoryStoreRegistry"),
            patch("app.services.memory_write_behind_buffer.MemoryWriteBehindBuffer"),
        ]
        + [patch(p, return_value=None) for p in _INIT_PATCHES]
        + [
            patch(
                "app.services.isolation_middleware.IsolationMiddleware",
                return_value=mock_mw,
            ),
            patch(
                "app.services.agentcore_integration.stream_agent_chat_v2",
                side_effect=_fake_stream,
            ),
        ]
    )
    mocks = [p.start() for p in patches]
    try:
        from app.routes.chat import _get_agentcore_chat_stream

        gen = _get_agentcore_chat_stream(
            messages=[{"role": "user", "content": "Hello"}],
            user_id="u1", family_id="fam-new", conversation_id="conv-2",
        )
        events = list(gen)

        assert len(events) == 2
        assert events[0]["type"] == "text_delta"

        mock_stream = mocks[-1]
        mock_stream.assert_called_once()
        kw = mock_stream.call_args.kwargs
        assert kw.get("isolated_memory_config") is None
    finally:
        for p in patches:
            p.stop()


def test_non_member_returns_403():
    """When IsolationMiddleware raises AccessDeniedError, the chat_v2 route
    returns HTTP 403 with the expected error message.

    Validates: Requirement 1.4
    """
    from flask import Flask, g
    from app.routes.chat import chat_bp

    app = Flask(__name__)
    app.config["TESTING"] = True
    app.config["AWS_REGION"] = "us-east-1"
    app.register_blueprint(chat_bp, url_prefix="/api")

    # Patch _try_device_auth to simulate a logged-in user with a family_id
    def _fake_device_auth(token):
        g.user_id = "user-xyz"
        g.user_name = "Test"
        g.user_role = "member"
        g.device_id = "dev-1"
        g.family_id = "family-abc"
        return True

    with (
        patch("app.auth._try_cognito_auth", return_value=False),
        patch("app.auth._try_device_auth", side_effect=_fake_device_auth),
        patch("app.auth._resolve_storage_provider"),
        patch(
            "app.routes.chat._get_agentcore_chat_stream",
            side_effect=AccessDeniedError("family-abc", "user-xyz"),
        ),
        patch("app.routes.chat.create_conversation", return_value={
            "conversation_id": "c1",
        }),
        patch("app.routes.chat.add_message"),
        patch("app.routes.chat.get_messages", return_value={
            "messages": [{"role": "user", "content": "Hi"}],
        }),
    ):
        with app.test_client() as tc:
            resp = tc.post(
                "/api/chat/v2",
                json={"message": "Hello"},
                headers={"Authorization": "Bearer fake-token"},
            )

    assert resp.status_code == 403
    body = resp.get_json()
    assert "Access denied" in body["error"]
    assert "not a member of this family" in body["error"]


def test_no_family_id_skips_isolation():
    """When family_id is None, the isolation path is skipped entirely.
    IsolationMiddleware is never instantiated and stream_agent_chat_v2
    is called without isolated_memory_config.

    Validates: Requirement 3.1
    """
    mw_patch = patch("app.services.isolation_middleware.IsolationMiddleware")
    stream_patch = patch(
        "app.services.agentcore_integration.stream_agent_chat_v2",
        side_effect=_fake_stream,
    )
    init_patches = [patch(p, return_value=None) for p in _INIT_PATCHES]

    all_patches = init_patches + [mw_patch, stream_patch]
    mocks = [p.start() for p in all_patches]
    try:
        from app.routes.chat import _get_agentcore_chat_stream

        gen = _get_agentcore_chat_stream(
            messages=[{"role": "user", "content": "Hello"}],
            user_id="u1", family_id=None, conversation_id="conv-3",
        )
        list(gen)

        # IsolationMiddleware was NOT instantiated
        mock_mw_cls = mocks[-2]
        mock_mw_cls.assert_not_called()

        # stream_agent_chat_v2 called without isolated_memory_config
        mock_stream = mocks[-1]
        mock_stream.assert_called_once()
        kw = mock_stream.call_args.kwargs
        assert "isolated_memory_config" not in kw
    finally:
        for p in all_patches:
            p.stop()
