"""WebSocket route for voice mode using Amazon Nova Sonic."""

import json
import logging

from flask import Blueprint, request
from flask_sock import Sock

from app.models.dynamo import get_table
from app.services.conversation import add_message
from app.services.voice_session import VoiceSession

logger = logging.getLogger(__name__)

voice_bp = Blueprint("voice", __name__)
sock = Sock()


def _authenticate_ws(token: str) -> dict | None:
    """Authenticate a WebSocket connection via device token. Returns user dict or None."""
    if not token:
        return None

    devices_table = get_table("Devices")
    result = devices_table.query(
        IndexName="device_token-index",
        KeyConditionExpression="device_token = :token",
        ExpressionAttributeValues={":token": token},
        Limit=1,
    )
    items = result.get("Items", [])
    if not items:
        return None

    device = items[0]
    users_table = get_table("Users")
    user = users_table.get_item(Key={"user_id": device["user_id"]}).get("Item")
    if not user:
        return None

    return {"user_id": user["user_id"], "name": user["name"]}


@sock.route("/voice", bp=voice_bp)
def voice_ws(ws):
    """WebSocket endpoint for bidirectional voice streaming.

    Query params:
        token: Device authentication token
        conversation_id: Optional conversation ID to save transcripts to
    """
    token = request.args.get("token", "")
    conversation_id = request.args.get("conversation_id")

    # Authenticate
    user = _authenticate_ws(token)
    if not user:
        ws.send(json.dumps({"type": "error", "content": "Authentication failed"}))
        ws.close()
        return

    user_id = user["user_id"]
    session = VoiceSession(user_id=user_id, conversation_id=conversation_id)

    try:
        session.start()
    except Exception:
        logger.exception("Failed to start voice session")
        ws.send(json.dumps({"type": "error", "content": "Failed to start voice session"}))
        ws.close()
        return

    import gevent

    def _receive_from_nova():
        """Greenlet: read from Nova Sonic and forward to client."""
        try:
            for event in session.receive():
                ws.send(json.dumps(event))

                # Save transcripts to conversation history
                if event["type"] == "transcript" and conversation_id:
                    add_message(
                        conversation_id=conversation_id,
                        role=event.get("role", "assistant"),
                        content=event.get("content", ""),
                    )
        except Exception:
            logger.debug("Nova receive greenlet ended", exc_info=True)

    # Start receiving from Nova Sonic in a separate greenlet
    receiver = gevent.spawn(_receive_from_nova)

    try:
        while True:
            raw = ws.receive()
            if raw is None:
                break

            try:
                msg = json.loads(raw)
            except (json.JSONDecodeError, TypeError):
                continue

            msg_type = msg.get("type")

            if msg_type == "audio_start":
                # Client signals start of audio — session already started
                pass

            elif msg_type == "audio_chunk":
                import base64

                data = msg.get("data", "")
                if data:
                    pcm = base64.b64decode(data)
                    session.send_audio(pcm)

            elif msg_type == "audio_end":
                session.send_audio_end()

            elif msg_type == "text":
                # Optional text alongside voice
                content = msg.get("content", "")
                if content and conversation_id:
                    add_message(
                        conversation_id=conversation_id,
                        role="user",
                        content=content,
                    )

    except Exception:
        logger.debug("WebSocket receive loop ended", exc_info=True)
    finally:
        session.end()
        receiver.join(timeout=5)
        ws.send(json.dumps({"type": "session_end"}))
