import json
import threading

from flask import (
    Blueprint,
    Response,
    current_app,
    g,
    jsonify,
    request,
    stream_with_context,
)

from app.auth import require_auth
from app.services.bedrock import stream_chat
from app.services.chat_media import resolve_media_for_message
from app.services.transcribe import transcribe_audio
from app.services.conversation import (
    add_message,
    create_conversation,
    get_conversation,
    get_messages,
)

chat_bp = Blueprint("chat", __name__)


def _get_chat_stream(
    messages: list[dict],
    user_id: str,
    conversation_id: str | None = None,
    images: list[dict] | None = None,
    is_voice_message: bool = False,
):
    """Return the appropriate chat stream based on feature flag."""
    if current_app.config.get("USE_AGENT_ORCHESTRATOR"):
        from app.services.agent_orchestrator import stream_agent_chat

        return stream_agent_chat(
            messages,
            user_id=user_id,
            conversation_id=conversation_id,
            images=images,
            is_voice_message=is_voice_message,
        )
    return stream_chat(messages, images=images)


@chat_bp.route("/chat", methods=["POST"])
@require_auth
def chat():
    data = request.get_json()
    if not data:
        return jsonify({"error": "request body is required"}), 400
    # Allow empty message if media is present (e.g., voice-only or image-only)
    has_message = bool(data.get("message"))
    has_media = bool(data.get("media"))
    if not has_message and not has_media:
        return jsonify({"error": "message or media is required"}), 400

    user_message = data.get("message", "") or ""
    conversation_id = data.get("conversation_id")
    media_ids = data.get("media", [])

    # Client-side speech recognition sends is_voice=true
    is_voice_message = bool(data.get("is_voice"))

    # Resolve media attachments to S3 URIs
    images = None
    media_metadata = None
    if media_ids:
        try:
            all_media = resolve_media_for_message(media_ids, g.user_id)
            media_metadata = [
                {"media_id": mid, "content_type": m["content_type"]}
                for mid, m in zip(media_ids, all_media)
            ]

            # Transcribe audio items — send clean text (no wrapper)
            audio_items = [m for m in all_media if m["media_type"] == "audio"]
            if audio_items:
                is_voice_message = True
            for audio in audio_items:
                try:
                    transcription = transcribe_audio(audio["s3_uri"])
                    user_message = (
                        f"{transcription}\n\n{user_message}"
                        if user_message
                        else transcription
                    )
                except Exception:
                    import logging
                    logging.getLogger(__name__).warning(
                        "Audio transcription failed, sending as untranscribed",
                        exc_info=True,
                    )
                    if not user_message:
                        user_message = (
                            "I sent a voice message but it could not be "
                            "understood. Please ask me to repeat."
                        )

            # Only pass image media to Bedrock (Claude doesn't accept audio)
            images = [m for m in all_media if m["media_type"] == "image"] or None
        except ValueError as e:
            return jsonify({"error": str(e)}), 400

    # Create or validate conversation
    if conversation_id:
        conv = get_conversation(conversation_id)
        if not conv:
            return jsonify({"error": "Conversation not found"}), 404
        if conv["user_id"] != g.user_id:
            return jsonify({"error": "Not your conversation"}), 403
    else:
        # Auto-title from first message
        if is_voice_message and user_message:
            # Voice: use transcription as title (truncated)
            title = user_message[:50] + ("..." if len(user_message) > 50 else "")
        elif user_message:
            title = user_message[:50] + ("..." if len(user_message) > 50 else "")
        elif media_ids:
            has_audio = any(
                m.get("content_type", "").startswith("audio/")
                for m in (media_metadata or [])
            )
            title = "Voice message" if has_audio else "Image message"
        else:
            title = "New conversation"
        conv = create_conversation(user_id=g.user_id, title=title)
        conversation_id = conv["conversation_id"]

    # Store user message
    add_message(
        conversation_id=conversation_id,
        role="user",
        content=user_message,
        media=media_metadata,
    )

    # Build message history for Bedrock
    history = get_messages(conversation_id, limit=50)
    messages = [
        {"role": m["role"], "content": m["content"]} for m in history["messages"]
    ]

    def generate():
        full_content = ""
        total_tokens = 0

        for chunk in _get_chat_stream(messages, g.user_id, conversation_id, images, is_voice_message):
            if chunk["type"] == "text_delta":
                event_data = json.dumps(
                    {
                        "type": "text_delta",
                        "content": chunk["content"],
                        "conversation_id": conversation_id,
                    }
                )
                yield f"data: {event_data}\n\n"

            elif chunk["type"] == "message_done":
                full_content = chunk["content"]
                total_tokens = chunk.get("input_tokens", 0) + chunk.get(
                    "output_tokens", 0
                )

                # Store assistant message
                msg = add_message(
                    conversation_id=conversation_id,
                    role="assistant",
                    content=full_content,
                    model=request.json.get("model"),
                    tokens_used=total_tokens,
                )

                # Fire-and-forget health extraction
                if current_app.config.get("HEALTH_EXTRACTION_ENABLED"):
                    from app.services.health_extraction import (
                        extract_health_observations,
                    )

                    t = threading.Thread(
                        target=extract_health_observations,
                        kwargs={
                            "user_id": g.user_id,
                            "conversation_id": conversation_id,
                            "user_message": user_message,
                            "assistant_response": full_content,
                            "region": current_app.config["AWS_REGION"],
                            "model_id": current_app.config[
                                "HEALTH_EXTRACTION_MODEL_ID"
                            ],
                            "dynamodb_endpoint": current_app.config.get(
                                "DYNAMODB_ENDPOINT"
                            ),
                        },
                        daemon=True,
                    )
                    t.start()

                event_data = json.dumps(
                    {
                        "type": "message_done",
                        "conversation_id": conversation_id,
                        "message_id": msg["message_id"],
                    }
                )
                yield f"data: {event_data}\n\n"

            elif chunk["type"] == "error":
                event_data = json.dumps({"type": "error", "content": chunk["content"]})
                yield f"data: {event_data}\n\n"

    return Response(
        stream_with_context(generate()),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
