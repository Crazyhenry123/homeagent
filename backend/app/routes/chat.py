import json
import threading
from typing import Generator

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
    """Return the appropriate chat stream based on feature flag.

    When AGENTCORE_RUNTIME_ARN is configured, routes through AgentCore
    Runtime for orchestration. Otherwise falls back to the local agent
    orchestrator or direct Bedrock.
    """
    if current_app.config.get("AGENTCORE_RUNTIME_ARN"):
        return _stream_via_agentcore(messages, user_id, conversation_id)

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


def _stream_via_agentcore(
    messages: list[dict],
    user_id: str,
    conversation_id: str | None,
) -> Generator[dict, None, None]:
    """Stream a chat response through AgentCore Runtime.

    Yields the same event format as stream_chat (text_delta, message_done,
    error) so the v1 /api/chat generator can handle persistence and health
    extraction unchanged.
    """
    import logging

    from app.config import Config
    from app.services.agentcore_memory import AgentCoreMemoryManager
    from app.services.agentcore_runtime import AgentCoreRuntimeClient
    from app.services.agent_management import AgentManagementClient
    from app.services.agent_orchestrator import _build_system_prompt

    logger = logging.getLogger(__name__)
    cfg = Config()

    runtime_client = AgentCoreRuntimeClient(
        agent_id=cfg.AGENTCORE_ORCHESTRATOR_AGENT_ID or "orchestrator",
        region=cfg.AWS_REGION,
        agent_runtime_arn=cfg.AGENTCORE_RUNTIME_ARN,
        model_id=cfg.BEDROCK_MODEL_ID,
    )
    agent_mgmt = AgentManagementClient(region=cfg.AWS_REGION)
    memory_manager = AgentCoreMemoryManager(
        family_memory_id=cfg.AGENTCORE_FAMILY_MEMORY_ID or "family-mem",
        member_memory_id=cfg.AGENTCORE_MEMBER_MEMORY_ID or "member-mem",
        region=cfg.AWS_REGION,
    )

    # Resolve sub-agent tools
    sub_agent_tool_ids = agent_mgmt.build_sub_agent_tool_ids(user_id)

    # Build memory config
    family_id = getattr(g, "family_id", None)
    memory_config = None
    if family_id:
        try:
            memory_config = memory_manager.create_combined_session_manager(
                family_id=family_id,
                member_id=user_id,
                session_id=conversation_id or "",
            )
        except Exception:
            logger.warning(
                "Failed to create combined session manager for user %s, "
                "proceeding without memory",
                user_id,
                exc_info=True,
            )

    # Create or resume session
    session_id = conversation_id or "ephemeral"
    session = runtime_client.get_session(session_id)
    if session is None:
        base_prompt = current_app.config.get(
            "SYSTEM_PROMPT",
            "You are a helpful family assistant. Be warm, friendly, and supportive.",
        )
        personalized_prompt = _build_system_prompt(user_id, base_prompt)
        session = runtime_client.create_session(
            session_id=session_id,
            user_id=user_id,
            family_id=family_id or "",
            system_prompt=personalized_prompt,
            memory_config=memory_config,
            sub_agent_tool_ids=sub_agent_tool_ids,
        )

    # Invoke and stream — yield same format as stream_chat
    user_message = messages[-1]["content"] if messages else ""
    full_text = ""

    for event in runtime_client.invoke_session(
        session_id=session_id,
        message=user_message,
        stream=True,
    ):
        if event.type == "text_delta":
            full_text += event.content
            yield {"type": "text_delta", "content": event.content}
        elif event.type == "error":
            yield {"type": "error", "content": event.content}
            return

    yield {
        "type": "message_done",
        "content": full_text,
        "input_tokens": 0,
        "output_tokens": 0,
    }


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

        for chunk in _get_chat_stream(
            messages, g.user_id, conversation_id, images, is_voice_message
        ):
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

                    # Resolve storage provider type for background thread
                    storage_type = "local"
                    try:
                        from app.services.storage_config import (
                            get_storage_config,
                        )

                        sc = get_storage_config(g.user_id)
                        if sc:
                            storage_type = sc.get("provider", "local")
                    except (ImportError, Exception):
                        pass

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
                            "storage_provider_type": storage_type,
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
