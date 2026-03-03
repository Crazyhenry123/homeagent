"""Health Advisor sub-agent — provides health and wellness guidance.

Always includes safety disclaimers. Uses web search when enabled.
"""

import logging

from strands import Agent, tool
from strands.models import BedrockModel

from app.agents.registry import register_agent

logger = logging.getLogger(__name__)

HEALTH_SYSTEM_PROMPT = """You are a Health & Wellness Advisor for a family.
You provide general health information, wellness tips, nutrition guidance,
exercise suggestions, and mental health support.

IMPORTANT SAFETY DISCLAIMERS — you MUST include these when relevant:
- Always remind users that you are an AI assistant, not a medical professional.
- For serious symptoms, always recommend consulting a healthcare provider.
- Never diagnose conditions or prescribe medications.
- For emergencies, advise calling emergency services immediately.
- Clearly state when information is general guidance vs. personalized advice.

Be warm, supportive, and encouraging. Tailor advice to the user's known
health notes and preferences when available."""


@register_agent("health_advisor")
def create_health_advisor_tool(
    config: dict,
    user_id: str,
    model_id: str,
) -> callable:
    """Factory that returns a @tool function for health advisor queries."""

    @tool(
        name="ask_health_advisor",
        description=(
            "Ask the Health & Wellness Advisor for guidance on health topics, "
            "nutrition, exercise, mental wellness, or general medical questions. "
            "Use this when the user asks about health-related topics."
        ),
    )
    def ask_health_advisor(query: str) -> str:
        """Get health and wellness guidance.

        Args:
            query: The health-related question or topic to get advice on.
        """
        model = BedrockModel(
            model_id=model_id,
            streaming=False,
            max_tokens=2048,
            temperature=0.5,
        )

        agent_tools = []

        agent = Agent(
            model=model,
            system_prompt=HEALTH_SYSTEM_PROMPT,
            tools=agent_tools,
        )

        try:
            result = agent(query)
            return str(result.message)
        except Exception:
            logger.exception("Health advisor agent failed")
            return (
                "I'm sorry, I wasn't able to process your health question "
                "right now. Please try again."
            )

    return ask_health_advisor
