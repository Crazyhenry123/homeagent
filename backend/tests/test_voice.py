"""Tests for voice mode — VoiceSession service + route helpers.

WebSocket integration tests are not feasible with Flask's test client
(no built-in WS support), so we unit-test:
  1. _authenticate_ws() — token validation
  2. VoiceSession — start/send/receive/end lifecycle with mocked SDK
  3. Route registration — VOICE_ENABLED flag
  4. Voice disabled returns 404
"""

import base64
import json
import sys
from contextlib import contextmanager
from unittest.mock import AsyncMock, MagicMock, patch

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
# Mock helper for aws_sdk_bedrock_runtime
# ---------------------------------------------------------------------------


@contextmanager
def mock_nova_sonic_sdk(receive_events=None, start_error=None):
    """Mock the aws_sdk_bedrock_runtime SDK for VoiceSession tests.

    Args:
        receive_events: List of event dicts that Nova Sonic sends back.
            Use Exception instances to simulate stream errors.
            If None, the receive stream ends immediately.
        start_error: If set, invoke_model_with_bidirectional_stream raises this.

    Yields:
        (sent_events, mock_client_cls) where sent_events captures all events
        sent to the stream as parsed dicts.
    """
    sent_events = []
    mock_stream = MagicMock()

    async def _capture_send(chunk):
        payload = json.loads(chunk.value.bytes_.decode("utf-8"))
        sent_events.append(payload)

    mock_stream.input_stream.send = _capture_send

    # Set up receive side
    if receive_events:
        event_iter = iter(receive_events)

        async def _mock_await_output():
            try:
                event_data = next(event_iter)
            except StopIteration:
                raise StopAsyncIteration()
            if isinstance(event_data, Exception):
                raise event_data

            result = MagicMock()
            result.value.bytes_ = json.dumps(event_data).encode("utf-8")
            receiver = MagicMock()
            receiver.receive = AsyncMock(return_value=result)
            return (MagicMock(), receiver)

        mock_stream.await_output = _mock_await_output
    else:

        async def _immediate_stop():
            raise StopAsyncIteration()

        mock_stream.await_output = _immediate_stop

    # Mock client
    mock_client = MagicMock()
    if start_error:
        mock_client.invoke_model_with_bidirectional_stream = AsyncMock(
            side_effect=start_error
        )
    else:
        mock_client.invoke_model_with_bidirectional_stream = AsyncMock(
            return_value=mock_stream
        )
    mock_client_cls = MagicMock(return_value=mock_client)

    # Lightweight stand-ins for SDK model classes
    class FakeInput:
        def __init__(self, model_id=None):
            self.model_id = model_id

    class FakePayloadPart:
        def __init__(self, bytes_=None):
            self.bytes_ = bytes_

    class FakeInputChunk:
        def __init__(self, value=None):
            self.value = value

    mock_client_mod = MagicMock()
    mock_client_mod.BedrockRuntimeClient = mock_client_cls

    mock_model_mod = MagicMock()
    mock_model_mod.InvokeModelWithBidirectionalStreamOperationInput = FakeInput
    mock_model_mod.BidirectionalInputPayloadPart = FakePayloadPart
    mock_model_mod.InvokeModelWithBidirectionalStreamInputChunk = FakeInputChunk

    with patch.dict(
        sys.modules,
        {
            "aws_sdk_bedrock_runtime": MagicMock(),
            "aws_sdk_bedrock_runtime.client": mock_client_mod,
            "aws_sdk_bedrock_runtime.model": mock_model_mod,
        },
    ):
        yield sent_events, mock_client_cls


def _cleanup_session(session):
    """Stop a VoiceSession's background thread to prevent test hangs."""
    session._ended = True
    if session._thread:
        session._thread.join(timeout=2)


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
# 2. VoiceSession lifecycle (mocked aws_sdk_bedrock_runtime)
# ---------------------------------------------------------------------------


def test_voice_session_start(app):
    """VoiceSession.start() opens a bidirectional stream and sends setup events."""
    with mock_nova_sonic_sdk() as (sent_events, mock_client_cls):
        from app.services.voice_session import VoiceSession

        with app.app_context():
            session = VoiceSession(user_id="user-1")
            session.start()

            assert session._started is True
            mock_client_cls.return_value.invoke_model_with_bidirectional_stream.assert_called_once()

            # start() sends: sessionStart, promptStart, contentStart(system),
            # textInput(system), contentEnd(system), contentStart(audio)
            assert len(sent_events) == 6
            assert "sessionStart" in sent_events[0]["event"]
            assert "promptStart" in sent_events[1]["event"]
            assert "contentStart" in sent_events[2]["event"]
            assert "textInput" in sent_events[3]["event"]
            assert "contentEnd" in sent_events[4]["event"]
            assert "contentStart" in sent_events[5]["event"]

            _cleanup_session(session)


def test_voice_session_start_idempotent(app):
    """Calling start() twice does not open a second stream."""
    with mock_nova_sonic_sdk() as (sent_events, mock_client_cls):
        from app.services.voice_session import VoiceSession

        with app.app_context():
            session = VoiceSession(user_id="user-1")
            session.start()
            event_count = len(sent_events)
            session.start()

            assert (
                mock_client_cls.return_value.invoke_model_with_bidirectional_stream.call_count
                == 1
            )
            assert len(sent_events) == event_count  # no new events

            _cleanup_session(session)


def test_voice_session_send_audio(app):
    """send_audio() encodes PCM data and sends it as audioInput event."""
    with mock_nova_sonic_sdk() as (sent_events, _):
        from app.services.voice_session import VoiceSession

        with app.app_context():
            session = VoiceSession(user_id="user-1")
            session.start()

            pcm_data = b"\x00\x01" * 160  # 320 bytes of fake PCM
            session.send_audio(pcm_data)

            # Last event should be audioInput
            last = sent_events[-1]
            assert "audioInput" in last["event"]
            content = last["event"]["audioInput"]["content"]
            assert base64.b64decode(content) == pcm_data

            _cleanup_session(session)


def test_voice_session_send_audio_noop_when_ended(app):
    """send_audio() is a no-op after session has ended."""
    with mock_nova_sonic_sdk() as (sent_events, _):
        from app.services.voice_session import VoiceSession

        with app.app_context():
            session = VoiceSession(user_id="user-1")
            session.start()
            session.end()

            count_after_end = len(sent_events)
            session.send_audio(b"\x00" * 320)
            assert len(sent_events) == count_after_end  # no new event

            _cleanup_session(session)


def test_voice_session_send_audio_end(app):
    """send_audio_end() sends contentEnd event for the audio stream."""
    with mock_nova_sonic_sdk() as (sent_events, _):
        from app.services.voice_session import VoiceSession

        with app.app_context():
            session = VoiceSession(user_id="user-1")
            session.start()
            session.send_audio_end()

            last = sent_events[-1]
            assert "contentEnd" in last["event"]
            assert last["event"]["contentEnd"]["contentName"] == "user_audio"

            _cleanup_session(session)


def test_voice_session_receive_transcript(app):
    """receive() yields transcript events from Nova Sonic stream."""
    events_from_nova = [
        {"event": {"textOutput": {"content": "Hello!", "role": "assistant"}}},
        {"event": {"sessionEnd": {}}},
    ]

    with mock_nova_sonic_sdk(receive_events=events_from_nova) as (sent_events, _):
        from app.services.voice_session import VoiceSession

        with app.app_context():
            session = VoiceSession(user_id="user-1")
            session.start()

            events = list(session.receive())

        assert len(events) == 2
        assert events[0]["type"] == "transcript"
        assert events[0]["content"] == "Hello!"
        assert events[0]["role"] == "assistant"
        assert events[1]["type"] == "session_end"


def test_voice_session_receive_audio(app):
    """receive() yields audio_chunk events from Nova Sonic."""
    audio_b64 = base64.b64encode(b"\x00" * 480).decode()
    events_from_nova = [
        {"event": {"audioOutput": {"content": audio_b64}}},
        {"event": {"sessionEnd": {}}},
    ]

    with mock_nova_sonic_sdk(receive_events=events_from_nova) as (sent_events, _):
        from app.services.voice_session import VoiceSession

        with app.app_context():
            session = VoiceSession(user_id="user-1")
            session.start()

            events = list(session.receive())

        assert events[0]["type"] == "audio_chunk"
        assert events[0]["data"] == audio_b64


def test_voice_session_receive_error(app):
    """receive() yields error events from Nova Sonic."""
    events_from_nova = [
        {"event": {"error": {"message": "Rate limit exceeded"}}},
    ]

    with mock_nova_sonic_sdk(receive_events=events_from_nova) as (sent_events, _):
        from app.services.voice_session import VoiceSession

        with app.app_context():
            session = VoiceSession(user_id="user-1")
            session.start()

            events = list(session.receive())

        assert len(events) == 1
        assert events[0]["type"] == "error"
        assert events[0]["content"] == "Rate limit exceeded"


def test_voice_session_receive_handles_stream_exception(app):
    """receive() yields an error if the stream raises an exception."""
    events_from_nova = [
        ConnectionError("Stream lost"),
    ]

    with mock_nova_sonic_sdk(receive_events=events_from_nova) as (sent_events, _):
        from app.services.voice_session import VoiceSession

        with app.app_context():
            session = VoiceSession(user_id="user-1")
            session.start()

            events = list(session.receive())

        assert len(events) == 1
        assert events[0]["type"] == "error"
        assert "stream lost" in events[0]["content"].lower()


def test_voice_session_end(app):
    """end() sends promptEnd + sessionEnd events and marks session as ended."""
    with mock_nova_sonic_sdk() as (sent_events, _):
        from app.services.voice_session import VoiceSession

        with app.app_context():
            session = VoiceSession(user_id="user-1")
            session.start()
            session.end()

            assert session._ended is True

            # Last two events should be promptEnd and sessionEnd
            assert "promptEnd" in sent_events[-2]["event"]
            assert "sessionEnd" in sent_events[-1]["event"]

            _cleanup_session(session)


def test_voice_session_end_idempotent(app):
    """Calling end() twice does not send sessionEnd twice."""
    with mock_nova_sonic_sdk() as (sent_events, _):
        from app.services.voice_session import VoiceSession

        with app.app_context():
            session = VoiceSession(user_id="user-1")
            session.start()

            count_before = len(sent_events)
            session.end()
            session.end()

            # Only 2 new events (promptEnd + sessionEnd), not 4
            assert len(sent_events) == count_before + 2

            _cleanup_session(session)


def test_voice_session_start_failure(app):
    """start() raises when Bedrock call fails."""
    with mock_nova_sonic_sdk(
        start_error=RuntimeError("Service unavailable")
    ) as (sent_events, _):
        from app.services.voice_session import VoiceSession

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
    with mock_nova_sonic_sdk() as (sent_events, _):
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
