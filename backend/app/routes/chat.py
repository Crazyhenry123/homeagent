import json

from flask import Blueprint, Response, g, jsonify, request, stream_with_context

from app.auth import require_auth
from app.services.bedrock import stream_chat
from app.services.conversation import (
    add_message,
    create_conversation,
    get_conversation,
    get_messages,
)

chat_bp = Blueprint("chat", __name__)


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

        for chunk in stream_chat(messages):
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

                event_data = json.dumps(
                    {
                        "type": "message_done",
                        "conversation_id": conversation_id,
                        "message_id": msg["message_id"],
                    }
                )
                yield f"data: {event_data}\n\n"

            elif chunk["type"] == "error":
                event_data = json.dumps(
                    {"type": "error", "content": chunk["content"]}
                )
                yield f"data: {event_data}\n\n"

    return Response(
        stream_with_context(generate()),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
