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


def _get_agentcore_chat_stream(
    messages: list[dict],
    user_id: str,
    family_id: str | None,
    conversation_id: str,
):
    """Return the AgentCore-based chat stream (v2).

    When *family_id* is provided, initialises the isolation components
    (IsolationMiddleware, FamilyMemoryStoreRegistry, IsolatedMemoryManager,
    MemoryWriteBehindBuffer) and routes memory through the per-family
    isolated store.  Falls back to the global AgentCoreMemoryManager when
    *family_id* is ``None``.

    Raises
    ------
    AccessDeniedError
        If the user is not a member of the requested family.
    """
    import logging

    import boto3

    from app.config import Config
    from app.services.agentcore_integration import stream_agent_chat_v2
    from app.services.agentcore_memory import AgentCoreMemoryManager
    from app.services.agentcore_runtime import AgentCoreRuntimeClient
    from app.services.agent_management import AgentManagementClient

    logger = logging.getLogger(__name__)
    cfg = Config()

    runtime_client = AgentCoreRuntimeClient(
        agent_id=cfg.AGENTCORE_ORCHESTRATOR_AGENT_ID or "orchestrator",
        region=cfg.AWS_REGION,
    )
    agent_mgmt = AgentManagementClient(region=cfg.AWS_REGION)
    memory_manager = AgentCoreMemoryManager(
        family_memory_id=cfg.AGENTCORE_FAMILY_MEMORY_ID or "family-mem",
        member_memory_id=cfg.AGENTCORE_MEMBER_MEMORY_ID or "member-mem",
    )

    # --- Per-family isolation path ---
    if family_id:
        from app.services.family_memory_registry import FamilyMemoryStoreRegistry
        from app.services.isolated_memory_manager import IsolatedMemoryManager
        from app.services.isolation_middleware import IsolationMiddleware
        from app.services.memory_write_behind_buffer import MemoryWriteBehindBuffer

        # Build DynamoDB resource
        dynamodb_kwargs: dict = {"region_name": cfg.AWS_REGION}
        if cfg.DYNAMODB_ENDPOINT:
            dynamodb_kwargs["endpoint_url"] = cfg.DYNAMODB_ENDPOINT
        dynamodb = boto3.resource("dynamodb", **dynamodb_kwargs)

        # Build AgentCore client for store provisioning
        agentcore_client = boto3.client(
            "bedrock-agent-runtime", region_name=cfg.AWS_REGION
        )

        # Initialise isolation components
        registry = FamilyMemoryStoreRegistry(
            dynamodb_resource=dynamodb,
            agentcore_client=agentcore_client,
        )

        # Write-behind buffer — execute_fn is a no-op placeholder;
        # actual memory operations are handled by the runtime session.
        def _execute_memory_op(store_id: str, operation: str, payload: dict):
            logger.debug(
                "Executing buffered memory op: store=%s op=%s", store_id, operation
            )

        buffer = MemoryWriteBehindBuffer(
            registry=registry,
            execute_fn=_execute_memory_op,
        )

        middleware = IsolationMiddleware(
            dynamodb_resource=dynamodb,
            registry=registry,
            buffer=buffer,
        )

        # Validate membership and resolve store — may raise AccessDeniedError
        context = middleware.validate_and_resolve(family_id, user_id)

        isolated_memory_config = None
        if context.store_status == "active":
            # Build isolated memory config using the per-family store
            iso_manager = IsolatedMemoryManager(
                member_memory_id=cfg.AGENTCORE_MEMBER_MEMORY_ID or "member-mem",
                registry=registry,
            )
            isolated_memory_config = iso_manager.safe_build_isolated_memory_config(
                context, conversation_id
            )
        else:
            # store_status == "pending": chat proceeds without family memory;
            # the write-behind buffer handles deferred writes.
            logger.info(
                "Family %s store is pending; proceeding without family memory",
                family_id,
            )

        return stream_agent_chat_v2(
            runtime_client=runtime_client,
            agent_mgmt=agent_mgmt,
            memory_manager=memory_manager,
            messages=messages,
            user_id=user_id,
            family_id=family_id,
            conversation_id=conversation_id,
            isolated_memory_config=isolated_memory_config,
        )

    # --- Global fallback (no family_id) ---
    return stream_agent_chat_v2(
        runtime_client=runtime_client,
        agent_mgmt=agent_mgmt,
        memory_manager=memory_manager,
        messages=messages,
        user_id=user_id,
        family_id=family_id,
        conversation_id=conversation_id,
    )


@chat_bp.route("/chat/v2", methods=["POST"])
@require_auth
def chat_v2():
    """AgentCore-migrated chat endpoint.

    Uses AgentCoreRuntimeClient for session management, AgentManagementClient
    for sub-agent tool resolution, and AgentCoreMemoryManager for dual-tier
    memory. Uses standard auth (Cognito JWT + device-token fallback).
    """

    data = request.get_json()
    if not data or not data.get("message"):
        return jsonify({"error": "message is required"}), 400

    user_message = data["message"]
    conversation_id = data.get("conversation_id")

    # Create or validate conversation
    if conversation_id:
        conv = get_conversation(conversation_id)
        if not conv:
            return jsonify({"error": "Conversation not found"}), 404
        if conv["user_id"] != g.user_id:
            return jsonify({"error": "Not your conversation"}), 403
    else:
        title = user_message[:50] + ("..." if len(user_message) > 50 else "")
        conv = create_conversation(user_id=g.user_id, title=title)
        conversation_id = conv["conversation_id"]

    add_message(conversation_id=conversation_id, role="user", content=user_message)

    history = get_messages(conversation_id, limit=50)
    messages = [
        {"role": m["role"], "content": m["content"]} for m in history["messages"]
    ]

    family_id = getattr(g, "family_id", None)

    # Eagerly create the stream generator so that AccessDeniedError
    # (raised during validate_and_resolve) surfaces before we enter
    # the streaming Response.  This lets us return a clean HTTP 403.
    from app.services.isolation_middleware import AccessDeniedError

    try:
        chat_stream = _get_agentcore_chat_stream(
            messages, g.user_id, family_id, conversation_id
        )
    except AccessDeniedError:
        return jsonify({"error": "Access denied: not a member of this family"}), 403

    def generate():
        for chunk in chat_stream:
            yield f"data: {json.dumps(chunk)}\n\n"

    return Response(
        stream_with_context(generate()),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


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
