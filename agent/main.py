"""HomeAgent orchestrator — deployed to AgentCore Runtime.

Uses Strands Agent with Claude for family assistant orchestration.
Invoked via bedrock-agentcore:invoke_agent_runtime from the Flask backend.
"""

import os

from bedrock_agentcore.runtime import BedrockAgentCoreApp
from strands import Agent
from strands.models import BedrockModel

app = BedrockAgentCoreApp()

model = BedrockModel(
    model_id=os.environ.get("BEDROCK_MODEL_ID", "us.anthropic.claude-opus-4-6-v1"),
    region_name=os.environ.get("AWS_REGION", "us-east-1"),
)

SYSTEM_PROMPT = (
    "You are a helpful family assistant. Be warm, friendly, and supportive. "
    "You help family members with health tracking, daily planning, reminders, "
    "and general questions. Keep responses conversational and concise."
)

agent = Agent(
    model=model,
    system_prompt=SYSTEM_PROMPT,
)


@app.entrypoint
def invoke(payload: dict) -> dict:
    """Handle an invocation from the Flask backend.

    Expected payload:
        {"prompt": "user message text", "session_id": "..."}

    Returns:
        {"result": "assistant response text"}
    """
    user_message = payload.get("prompt", "Hello!")
    result = agent(user_message)
    try:
        text = result.message["content"][0]["text"]
    except (KeyError, IndexError, TypeError):
        text = str(result)
    return {"result": text}


if __name__ == "__main__":
    app.run()
