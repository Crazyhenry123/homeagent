"""Tests for voice mode — VoiceSession service + route helpers.

WebSocket integration tests are not feasible with Flask's test client
(no built-in WS support), so we unit-test:
  1. _authenticate_ws() — token validation
  2. VoiceSession — start/send/receive/end lifecycle with mocked Bedrock
  3. Route registration — VOICE_ENABLED flag
  4. Voice disabled returns 404
"""

import base64
import json
from unittest.mock import MagicMock, patch

from app import create_app
from app.config import Config


def _register(client):
    """Register a user and return (user_id, device_token)."""
    resp = client.post(
        "/api/auth/register",
        json={
            "invite_code": "FAMILY",
            "device_name": "Test iPhone",
            "platform": "ios",
            "display_name": "Tester",
        },
    )
    data = resp.get_json()
    return data["user_id"], data["device_token"]


# ---------------------------------------------------------------------------
# 1. Authentication helper
# ---------------------------------------------------------------------------


def test_authenticate_ws_missing_token(client, app):
    """Empty token returns None."""
    from app.routes.voice import _authenticate_ws

    with app.app_context():
        assert _authenticate_ws("") is None
        assert _authenticate_ws(None) is None


def test_authenticate_ws_invalid_token(client, app):
    """Unknown token returns None."""
    from app.routes.voice import _authenticate_ws

    _register(client)  # ensure tables exist
    with app.app_context():
        assert _authenticate_ws("nonexistent-token-xyz") is None


def test_authenticate_ws_valid_token(client, app):
    """Valid device token returns user dict with user_id and name."""
    from app.routes.voice import _authenticate_ws

    user_id, token = _register(client)
    with app.app_context():
        user = _authenticate_ws(token)
        assert user is not None
        assert user["user_id"] == user_id
        assert user["name"] == "Tester"


# ---------------------------------------------------------------------------
# 2. VoiceSession lifecycle (mocked Bedrock)
# ---------------------------------------------------------------------------


@patch("app.services.voice_session.boto3")
def test_voice_session_start(mock_boto3, app):
    """VoiceSession.start() opens a bidirectional stream."""
    from app.services.voice_session import VoiceSession

    mock_client = MagicMock()
    mock_stream = {"body": MagicMock()}
    mock_client.invoke_model_with_bidirectional_stream.return_value = mock_stream
    mock_boto3.client.return_value = mock_client

    with app.app_context():
        session = VoiceSession(user_id="user-1")
        session.start()

        assert session._started is True
        mock_client.invoke_model_with_bidirectional_stream.assert_called_once()
        # Session start event should have been sent
        mock_stream["body"].send.assert_called_once()
        payload = json.loads(mock_stream["body"].send.call_args[0][0])
        assert "sessionStart" in payload["event"]


@patch("app.services.voice_session.boto3")
def test_voice_session_start_idempotent(mock_boto3, app):
    """Calling start() twice does not open a second stream."""
    from app.services.voice_session import VoiceSession

    mock_client = MagicMock()
    mock_client.invoke_model_with_bidirectional_stream.return_value = {"body": MagicMock()}
    mock_boto3.client.return_value = mock_client

    with app.app_context():
        session = VoiceSession(user_id="user-1")
        session.start()
        session.start()

        assert mock_client.invoke_model_with_bidirectional_stream.call_count == 1


@patch("app.services.voice_session.boto3")
def test_voice_session_send_audio(mock_boto3, app):
    """send_audio() encodes PCM data and sends it as audioInput event."""
    from app.services.voice_session import VoiceSession

    mock_client = MagicMock()
    mock_body = MagicMock()
    mock_client.invoke_model_with_bidirectional_stream.return_value = {"body": mock_body}
    mock_boto3.client.return_value = mock_client

    with app.app_context():
        session = VoiceSession(user_id="user-1")
        session.start()

        pcm_data = b"\x00\x01" * 160  # 320 bytes of fake PCM
        session.send_audio(pcm_data)

        # Second call (first was sessionStart)
        assert mock_body.send.call_count == 2
        payload = json.loads(mock_body.send.call_args[0][0])
        assert "audioInput" in payload["event"]
        audio_chunk = payload["event"]["audioInput"]["audio"]["audioChunk"]
        assert base64.b64decode(audio_chunk) == pcm_data


@patch("app.services.voice_session.boto3")
def test_voice_session_send_audio_noop_when_ended(mock_boto3, app):
    """send_audio() is a no-op after session has ended."""
    from app.services.voice_session import VoiceSession

    mock_client = MagicMock()
    mock_body = MagicMock()
    mock_client.invoke_model_with_bidirectional_stream.return_value = {"body": mock_body}
    mock_boto3.client.return_value = mock_client

    with app.app_context():
        session = VoiceSession(user_id="user-1")
        session.start()
        session.end()

        initial_count = mock_body.send.call_count
        session.send_audio(b"\x00" * 320)
        assert mock_body.send.call_count == initial_count  # no new call


@patch("app.services.voice_session.boto3")
def test_voice_session_send_audio_end(mock_boto3, app):
    """send_audio_end() sends audioInputEnd event."""
    from app.services.voice_session import VoiceSession

    mock_client = MagicMock()
    mock_body = MagicMock()
    mock_client.invoke_model_with_bidirectional_stream.return_value = {"body": mock_body}
    mock_boto3.client.return_value = mock_client

    with app.app_context():
        session = VoiceSession(user_id="user-1")
        session.start()
        session.send_audio_end()

        payload = json.loads(mock_body.send.call_args[0][0])
        assert "audioInputEnd" in payload["event"]


@patch("app.services.voice_session.boto3")
def test_voice_session_receive_transcript(mock_boto3, app):
    """receive() yields transcript events from Nova Sonic stream."""
    from app.services.voice_session import VoiceSession

    nova_events = [
        json.dumps({"event": {"textOutput": {"text": "Hello!", "role": "assistant"}}}).encode(),
        json.dumps({"event": {"sessionEnd": {}}}).encode(),
    ]

    mock_client = MagicMock()
    mock_body = MagicMock()
    mock_body.__iter__ = MagicMock(return_value=iter(nova_events))
    mock_client.invoke_model_with_bidirectional_stream.return_value = {"body": mock_body}
    mock_boto3.client.return_value = mock_client

    with app.app_context():
        session = VoiceSession(user_id="user-1")
        session.start()

        events = list(session.receive())

    assert len(events) == 2
    assert events[0]["type"] == "transcript"
    assert events[0]["content"] == "Hello!"
    assert events[0]["role"] == "assistant"
    assert events[1]["type"] == "session_end"


@patch("app.services.voice_session.boto3")
def test_voice_session_receive_audio(mock_boto3, app):
    """receive() yields audio_chunk events from Nova Sonic."""
    from app.services.voice_session import VoiceSession

    audio_b64 = base64.b64encode(b"\x00" * 480).decode()
    nova_events = [
        json.dumps({"event": {"audioOutput": {"audio": {"audioChunk": audio_b64}}}}).encode(),
        json.dumps({"event": {"sessionEnd": {}}}).encode(),
    ]

    mock_client = MagicMock()
    mock_body = MagicMock()
    mock_body.__iter__ = MagicMock(return_value=iter(nova_events))
    mock_client.invoke_model_with_bidirectional_stream.return_value = {"body": mock_body}
    mock_boto3.client.return_value = mock_client

    with app.app_context():
        session = VoiceSession(user_id="user-1")
        session.start()

        events = list(session.receive())

    assert events[0]["type"] == "audio_chunk"
    assert events[0]["data"] == audio_b64


@patch("app.services.voice_session.boto3")
def test_voice_session_receive_error(mock_boto3, app):
    """receive() yields error events from Nova Sonic."""
    from app.services.voice_session import VoiceSession

    nova_events = [
        json.dumps({"event": {"error": {"message": "Rate limit exceeded"}}}).encode(),
    ]

    mock_client = MagicMock()
    mock_body = MagicMock()
    mock_body.__iter__ = MagicMock(return_value=iter(nova_events))
    mock_client.invoke_model_with_bidirectional_stream.return_value = {"body": mock_body}
    mock_boto3.client.return_value = mock_client

    with app.app_context():
        session = VoiceSession(user_id="user-1")
        session.start()

        events = list(session.receive())

    assert len(events) == 1
    assert events[0]["type"] == "error"
    assert events[0]["content"] == "Rate limit exceeded"


@patch("app.services.voice_session.boto3")
def test_voice_session_receive_handles_stream_exception(mock_boto3, app):
    """receive() yields an error if the stream raises an exception."""
    from app.services.voice_session import VoiceSession

    def _exploding_iter():
        raise ConnectionError("Stream lost")

    mock_client = MagicMock()
    mock_body = MagicMock()
    mock_body.__iter__ = MagicMock(side_effect=_exploding_iter)
    mock_client.invoke_model_with_bidirectional_stream.return_value = {"body": mock_body}
    mock_boto3.client.return_value = mock_client

    with app.app_context():
        session = VoiceSession(user_id="user-1")
        session.start()

        events = list(session.receive())

    assert len(events) == 1
    assert events[0]["type"] == "error"
    assert "connection lost" in events[0]["content"].lower()


@patch("app.services.voice_session.boto3")
def test_voice_session_end(mock_boto3, app):
    """end() sends sessionEnd event and marks session as ended."""
    from app.services.voice_session import VoiceSession

    mock_client = MagicMock()
    mock_body = MagicMock()
    mock_client.invoke_model_with_bidirectional_stream.return_value = {"body": mock_body}
    mock_boto3.client.return_value = mock_client

    with app.app_context():
        session = VoiceSession(user_id="user-1")
        session.start()
        session.end()

        assert session._ended is True
        payload = json.loads(mock_body.send.call_args[0][0])
        assert "sessionEnd" in payload["event"]


@patch("app.services.voice_session.boto3")
def test_voice_session_end_idempotent(mock_boto3, app):
    """Calling end() twice does not send sessionEnd twice."""
    from app.services.voice_session import VoiceSession

    mock_client = MagicMock()
    mock_body = MagicMock()
    mock_client.invoke_model_with_bidirectional_stream.return_value = {"body": mock_body}
    mock_boto3.client.return_value = mock_client

    with app.app_context():
        session = VoiceSession(user_id="user-1")
        session.start()

        send_count_before = mock_body.send.call_count
        session.end()
        session.end()

        # Only one additional send (sessionEnd) beyond what start() did
        assert mock_body.send.call_count == send_count_before + 1


@patch("app.services.voice_session.boto3")
def test_voice_session_start_failure(mock_boto3, app):
    """start() raises when Bedrock call fails."""
    from app.services.voice_session import VoiceSession

    mock_client = MagicMock()
    mock_client.invoke_model_with_bidirectional_stream.side_effect = RuntimeError(
        "Service unavailable"
    )
    mock_boto3.client.return_value = mock_client

    with app.app_context():
        session = VoiceSession(user_id="user-1")
        try:
            session.start()
            assert False, "Expected RuntimeError"
        except RuntimeError as e:
            assert "Service unavailable" in str(e)
        assert session._started is False


def test_voice_session_receive_noop_without_start(app):
    """receive() returns immediately if stream was never started."""
    from app.services.voice_session import VoiceSession

    with app.app_context():
        session = VoiceSession(user_id="user-1")
        events = list(session.receive())
        assert events == []


# ---------------------------------------------------------------------------
# 3. Route registration — VOICE_ENABLED flag
# ---------------------------------------------------------------------------


def test_voice_route_registered_when_enabled(dynamo_client):
    """When VOICE_ENABLED=True, /api/voice route is registered."""
    config = Config()
    config.VOICE_ENABLED = True
    app = create_app(config)

    rules = [rule.rule for rule in app.url_map.iter_rules()]
    assert "/api/voice" in rules


def test_voice_route_not_registered_when_disabled(dynamo_client):
    """When VOICE_ENABLED=False, /api/voice route is NOT registered."""
    config = Config()
    config.VOICE_ENABLED = False
    app = create_app(config)

    rules = [rule.rule for rule in app.url_map.iter_rules()]
    assert "/api/voice" not in rules


def test_voice_disabled_returns_404(client, app):
    """GET /api/voice returns 404 when voice is disabled (default)."""
    resp = client.get("/api/voice")
    assert resp.status_code == 404
