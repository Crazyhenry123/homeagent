import asyncio
import logging
import queue
from concurrent.futures import ThreadPoolExecutor
from typing import Generator

from flask import current_app

from app.services.bedrock import build_image_content_block
from app.services.family_tree import build_family_context
from app.services.profile import get_profile

logger = logging.getLogger(__name__)

_executor = ThreadPoolExecutor(max_workers=4)


def _build_system_prompt(user_id: str, base_prompt: str) -> str:
    """Build a personalized system prompt by incorporating user profile data."""
    profile = get_profile(user_id)
    if not profile:
        return base_prompt

    parts = [base_prompt]

    display_name = profile.get("display_name", "")
    if display_name:
        parts.append(f"\nYou are speaking with {display_name}.")

    family_role = profile.get("family_role", "")
    if family_role:
        parts.append(f"Their family role is: {family_role}.")

    interests = profile.get("interests", [])
    if interests:
        parts.append(f"Their interests include: {', '.join(interests)}.")

    health_notes = profile.get("health_notes", "")
    if health_notes:
        parts.append(f"Health notes: {health_notes}.")

    preferences = profile.get("preferences", {})
    if preferences:
        pref_str = ", ".join(f"{k}: {v}" for k, v in preferences.items())
        parts.append(f"Preferences: {pref_str}.")

    family_ctx = build_family_context(user_id)
    if family_ctx:
        parts.append(family_ctx)

    return " ".join(parts)


def _format_messages_for_agent(messages: list[dict]) -> list[dict]:
    """Convert simple {role, content} messages to Bedrock converse format."""
    result = []
    for m in messages:
        content: list[dict] = [{"text": m["content"]}]
        result.append({"role": m["role"], "content": content})
    return result


def stream_agent_chat(
    messages: list[dict],
    user_id: str,
    conversation_id: str | None = None,
    system_prompt: str | None = None,
    tools: list | None = None,
    images: list[dict] | None = None,
) -> Generator[dict, None, None]:
    """Stream a chat response using Strands Agent with personalized prompt.

    Args:
        messages: Conversation history as [{role, content}, ...].
                  The last message should be the new user message.
        user_id: User ID for profile-based personalization.
        conversation_id: Conversation ID for memory session tracking.
        system_prompt: Optional base system prompt override.
        tools: Optional list of Strands tool functions for sub-agents.
        images: Optional list of {"s3_uri", "content_type", "format"} for images
                attached to the last user message.

    Yields:
        Dicts with type "text_delta", "message_done", or "error".
    """
    from strands import Agent
    from strands.models import BedrockModel

    from app.agents.personal import build_sub_agent_tools
    from app.services.memory import create_session_manager

    model_id = current_app.config["BEDROCK_MODEL_ID"]
    base_prompt = system_prompt or current_app.config["SYSTEM_PROMPT"]
    personalized_prompt = _build_system_prompt(user_id, base_prompt)

    # Split history from the new user message
    if not messages:
        yield {"type": "error", "content": "No messages provided"}
        return

    history = _format_messages_for_agent(messages[:-1])
    # For the user message, if images are attached, build multimodal content
    user_message = messages[-1]["content"]
    if images:
        user_content: list[dict] = [
            build_image_content_block(img) for img in images
        ]
        user_content.append({"text": user_message})
        user_message = user_content

    # Create Strands Agent with BedrockModel
    model = BedrockModel(
        model_id=model_id,
        streaming=True,
        max_tokens=4096,
        temperature=0.7,
    )

    # Build sub-agent tools from user's agent configs
    if tools is None:
        tools = build_sub_agent_tools(user_id=user_id, model_id=model_id)

    # Set up AgentCore Memory session manager if configured
    session_manager = None
    if conversation_id:
        session_manager = create_session_manager(user_id, conversation_id)

    q: queue.Queue[dict | None] = queue.Queue()

    async def _run_agent() -> None:
        try:
            agent_kwargs: dict = {
                "model": model,
                "system_prompt": personalized_prompt,
                "messages": list(history),
            }
            if session_manager is not None:
                agent_kwargs["session_manager"] = session_manager
            if tools:
                agent_kwargs["tools"] = tools

            agent = Agent(**agent_kwargs)
            async for event in agent.stream_async(user_message):
                if "data" in event:
                    q.put({"type": "text_delta", "content": event["data"]})
        except Exception:
            logger.exception("Agent streaming failed")
            q.put(
                {
                    "type": "error",
                    "content": "Failed to connect to AI service. Please try again.",
                }
            )
        finally:
            q.put(None)

    def _thread_run() -> None:
        loop = asyncio.new_event_loop()
        try:
            loop.run_until_complete(_run_agent())
        finally:
            loop.close()

    future = _executor.submit(_thread_run)

    full_text = ""
    input_tokens = 0
    output_tokens = 0

    while True:
        try:
            chunk = q.get(timeout=300)
        except queue.Empty:
            yield {"type": "error", "content": "Agent response timed out"}
            break

        if chunk is None:
            break

        if chunk["type"] == "text_delta":
            full_text += chunk["content"]
            yield chunk
        elif chunk["type"] == "error":
            yield chunk
            break

    # Wait for thread to finish and check for exceptions
    try:
        future.result(timeout=5)
    except Exception:
        logger.exception("Agent thread raised exception")

    if full_text:
        yield {
            "type": "message_done",
            "content": full_text,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
        }
