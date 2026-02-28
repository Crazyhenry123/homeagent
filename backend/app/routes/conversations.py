from flask import Blueprint, g, jsonify, request

from app.auth import require_auth
from app.services.conversation import (
    delete_conversation,
    get_conversation,
    get_messages,
    list_conversations,
)

conversations_bp = Blueprint("conversations", __name__)


@conversations_bp.route("/conversations", methods=["GET"])
@require_auth
def list_convos():
    limit = request.args.get("limit", 20, type=int)
    cursor = request.args.get("cursor")

    result = list_conversations(user_id=g.user_id, limit=limit, cursor=cursor)
    return jsonify(result)


@conversations_bp.route("/conversations/<conversation_id>/messages", methods=["GET"])
@require_auth
def get_conv_messages(conversation_id: str):
    conv = get_conversation(conversation_id)
    if not conv:
        return jsonify({"error": "Conversation not found"}), 404
    if conv["user_id"] != g.user_id:
        return jsonify({"error": "Not your conversation"}), 403

    limit = request.args.get("limit", 50, type=int)
    cursor = request.args.get("cursor")

    result = get_messages(conversation_id, limit=limit, cursor=cursor)
    return jsonify(result)


@conversations_bp.route("/conversations/<conversation_id>", methods=["DELETE"])
@require_auth
def delete_conv(conversation_id: str):
    conv = get_conversation(conversation_id)
    if not conv:
        return jsonify({"error": "Conversation not found"}), 404
    if conv["user_id"] != g.user_id:
        return jsonify({"error": "Not your conversation"}), 403

    delete_conversation(conversation_id)
    return jsonify({"success": True})
