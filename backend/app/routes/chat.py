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
from app.services.conversation import (
    add_message,
    create_conversation,
    get_conversation,
    get_messages,
)

chat_bp = Blueprint("chat", __name__)


def _get_chat_stream(
    messages: list[dict], user_id: str, conversation_id: str | None = None
):
    """Return the appropriate chat stream based on feature flag."""
    if current_app.config.get("USE_AGENT_ORCHESTRATOR"):
        from app.services.agent_orchestrator import stream_agent_chat

        return stream_agent_chat(
            messages, user_id=user_id, conversation_id=conversation_id
        )
    return stream_chat(messages)


def _get_agentcore_chat_stream(
    messages: list[dict],
    user_id: str,
    family_id: str | None,
    conversation_id: str,
):
    """Return the AgentCore-based chat stream (v2)."""
    from app.config import Config
    from app.services.agentcore_integration import stream_agent_chat_v2
    from app.services.agentcore_memory import AgentCoreMemoryManager
    from app.services.agentcore_runtime import AgentCoreRuntimeClient
    from app.services.agent_management import AgentManagementClient

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
def chat_v2():
    """AgentCore-migrated chat endpoint.

    Uses AgentCoreRuntimeClient for session management, AgentManagementClient
    for sub-agent tool resolution, and AgentCoreMemoryManager for dual-tier
    memory. Requires AgentCore Identity authentication (set via middleware).

    Replaces @require_auth with @agentcore_require_auth.
    """
    # Auth is handled by the agentcore identity middleware registered on the app
    # The middleware sets g.user_id, g.family_id, g.user_role, g.cognito_sub
    if not hasattr(g, "user_id") or not g.user_id:
        return jsonify({"error": "Authentication required"}), 401

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

    def generate():
        for chunk in _get_agentcore_chat_stream(
            messages, g.user_id, family_id, conversation_id
        ):
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
        # Auto-title from first message
        title = user_message[:50] + ("..." if len(user_message) > 50 else "")
        conv = create_conversation(user_id=g.user_id, title=title)
        conversation_id = conv["conversation_id"]

    # Store user message
    add_message(conversation_id=conversation_id, role="user", content=user_message)

    # Build message history for Bedrock
    history = get_messages(conversation_id, limit=50)
    messages = [
        {"role": m["role"], "content": m["content"]} for m in history["messages"]
    ]

    def generate():
        full_content = ""
        total_tokens = 0

        for chunk in _get_chat_stream(messages, g.user_id, conversation_id):
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
