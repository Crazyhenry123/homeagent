"""HomeAgent orchestrator — deployed to AgentCore Runtime.

Uses Strands Agent with Claude for family assistant orchestration.
Invoked via bedrock-agentcore:invoke_agent_runtime from the Flask backend.

The backend builds personalized family context (system prompt, conversation
history, user profile) and passes it in the invocation payload. This runtime
is a shared execution engine — one instance serves all families.
"""

import os

from bedrock_agentcore.runtime import BedrockAgentCoreApp
from strands import Agent
from strands.models import BedrockModel

app = BedrockAgentCoreApp()

DEFAULT_SYSTEM_PROMPT = (
    "You are a helpful family assistant. Be warm, friendly, and supportive. "
    "You help family members with health tracking, daily planning, reminders, "
    "and general questions. Keep responses conversational and concise."
)


@app.entrypoint
def invoke(payload: dict) -> dict:
    """Handle an invocation from the Flask backend.

    Expected payload:
        {
            "prompt": "user message text",
            "system_prompt": "personalized system prompt with family context",
            "messages": [{"role": "user", "content": [{"text": "..."}]}, ...],
            "model_id": "us.anthropic.claude-opus-4-6-v1",
            "max_tokens": 4096,
            "temperature": 0.7,
        }

    The backend is responsible for building the personalized system prompt
    (user profile, family tree, shared memory, time) and conversation history.
    This runtime just executes the agent with the provided context.

    Returns:
        {"result": "assistant response text"}
    """
    user_message = payload.get("prompt", "Hello!")
    system_prompt = payload.get("system_prompt", DEFAULT_SYSTEM_PROMPT)
    messages = payload.get("messages", [])
    model_id = payload.get(
        "model_id",
        os.environ.get("BEDROCK_MODEL_ID", "us.anthropic.claude-opus-4-6-v1"),
    )
    max_tokens = payload.get("max_tokens", 4096)
    temperature = payload.get("temperature", 0.7)

    model = BedrockModel(
        model_id=model_id,
        region_name=os.environ.get("AWS_REGION", "us-east-1"),
        max_tokens=max_tokens,
        temperature=temperature,
    )

    agent_kwargs = {
        "model": model,
        "system_prompt": system_prompt,
    }
    if messages:
        agent_kwargs["messages"] = messages

    agent = Agent(**agent_kwargs)
    result = agent(user_message)

    try:
        text = result.message["content"][0]["text"]
    except (KeyError, IndexError, TypeError):
        text = str(result)

    return {"result": text}


if __name__ == "__main__":
    app.run()
