"""Health advisor tools — 7 @tool functions the health advisor agent can call.

build_health_tools(user_id, config, storage) returns a list of Strands tool
functions. All tools use closures capturing user_id and optional storage provider.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from strands import tool

if TYPE_CHECKING:
    from app.storage.base import StorageProvider

logger = logging.getLogger(__name__)


def build_health_tools(
    user_id: str,
    config: dict,
    storage: StorageProvider | None = None,
) -> list:
    """Build and return health advisor tools for the given user.

    Args:
        user_id: The user requesting health advice.
        config: Agent config dict (controls feature flags).
        storage: Optional storage provider for the user's data.
    """
    tools = []

    # ── Tool 1: get_family_health_records ────────────────────────

    @tool(
        name="get_family_health_records",
        description=(
            "Read health records for a family member. Provide the target "
            "member's user_id and optionally filter by record_type "
            "(condition/medication/allergy/appointment/vital/immunization/growth)."
        ),
    )
    def get_family_health_records(
        target_user_id: str, record_type: str = ""
    ) -> str:
        """Get health records for a family member.

        Args:
            target_user_id: The user_id of the family member.
            record_type: Optional filter by record type.
        """
        from app.services.family_tree import get_relationships
        from app.services.health_records import list_health_records

        # Validate family access: user can access own records or family members'
        if target_user_id != user_id:
            relationships = get_relationships(user_id)
            family_ids = {r["related_user_id"] for r in relationships}
            if target_user_id not in family_ids:
                return "Access denied: the target user is not in your family."

        records = list_health_records(
            target_user_id, record_type=record_type or None, storage=storage
        )
        if not records:
            return f"No health records found for user {target_user_id}."

        lines = []
        for r in records:
            lines.append(
                f"- [{r['record_type']}] {r['data']} "
                f"(updated: {r['updated_at']})"
            )
        return f"Health records for {target_user_id}:\n" + "\n".join(lines)

    tools.append(get_family_health_records)

    # ── Tool 2: get_health_summary ───────────────────────────────

    @tool(
        name="get_health_summary",
        description=(
            "Get a structured health summary grouped by record type for a user."
        ),
    )
    def get_health_summary_tool(target_user_id: str) -> str:
        """Get a structured health summary.

        Args:
            target_user_id: The user_id to get the summary for.
        """
        from app.services.family_tree import get_relationships
        from app.services.health_records import get_health_summary

        if target_user_id != user_id:
            relationships = get_relationships(user_id)
            family_ids = {r["related_user_id"] for r in relationships}
            if target_user_id not in family_ids:
                return "Access denied: the target user is not in your family."

        summary = get_health_summary(target_user_id, storage=storage)
        if summary["record_count"] == 0:
            return f"No health records found for user {target_user_id}."

        parts = [f"Health summary for {target_user_id} ({summary['record_count']} records):"]
        for rtype, records in summary["by_type"].items():
            parts.append(f"\n## {rtype.title()} ({len(records)})")
            for r in records:
                parts.append(f"  - {r['data']}")
        return "\n".join(parts)

    tools.append(get_health_summary_tool)

    # ── Tool 3: get_family_health_context ────────────────────────

    @tool(
        name="get_family_health_context",
        description=(
            "Get family composition, roles, and health notes for context. "
            "Call this first to understand the family structure."
        ),
    )
    def get_family_health_context() -> str:
        """Get family context including roles and health notes."""
        from app.services.family_tree import get_relationships
        from app.services.profile import get_profile

        profile = get_profile(user_id)
        relationships = get_relationships(user_id)

        parts = []
        if profile:
            parts.append(
                f"Current user: {profile.get('display_name', user_id)} "
                f"(role: {profile.get('family_role', 'unknown')})"
            )
            health_notes = profile.get("health_notes", "")
            if health_notes:
                parts.append(f"Health notes: {health_notes}")

        if relationships:
            parts.append("\nFamily members:")
            for rel in relationships:
                related_profile = get_profile(rel["related_user_id"])
                name = (
                    related_profile.get("display_name", rel["related_user_id"])
                    if related_profile
                    else rel["related_user_id"]
                )
                rel_type = rel["relationship_type"]
                health = ""
                if related_profile and related_profile.get("health_notes"):
                    health = f" | Health: {related_profile['health_notes']}"
                parts.append(
                    f"  - {name} ({rel_type}, id: {rel['related_user_id']}){health}"
                )
        else:
            parts.append("No family relationships found.")

        return "\n".join(parts)

    tools.append(get_family_health_context)

    # ── Tool 4: save_health_observation ──────────────────────────

    if config.get("observation_tracking_enabled", True):

        @tool(
            name="save_health_observation",
            description=(
                "Save a health observation or insight from the conversation. "
                "Categories: diet, exercise, sleep, symptom, mood, general. "
                "Use this to track patterns over time."
            ),
        )
        def save_health_observation(
            target_user_id: str,
            category: str,
            summary: str,
            detail: str = "",
            confidence: str = "medium",
        ) -> str:
            """Save a health observation.

            Args:
                target_user_id: The user_id this observation is about.
                category: One of: diet, exercise, sleep, symptom, mood, general.
                summary: Short summary of the observation.
                detail: Optional longer detail.
                confidence: low, medium, or high.
            """
            from app.services.health_observations import create_observation

            try:
                obs = create_observation(
                    user_id=target_user_id,
                    category=category,
                    summary=summary,
                    detail=detail,
                    confidence=confidence,
                    storage=storage,
                )
                return f"Observation saved (id: {obs['observation_id']})."
            except ValueError as e:
                return f"Error: {e}"

        tools.append(save_health_observation)

    # ── Tool 5: get_health_observations ──────────────────────────

    @tool(
        name="get_health_observations",
        description=(
            "Read past health observations and trends for a family member. "
            "Optionally filter by category (diet/exercise/sleep/symptom/mood/general)."
        ),
    )
    def get_health_observations(
        target_user_id: str, category: str = ""
    ) -> str:
        """Get health observations.

        Args:
            target_user_id: The user_id to get observations for.
            category: Optional category filter.
        """
        from app.services.family_tree import get_relationships
        from app.services.health_observations import list_observations

        if target_user_id != user_id:
            relationships = get_relationships(user_id)
            family_ids = {r["related_user_id"] for r in relationships}
            if target_user_id not in family_ids:
                return "Access denied: the target user is not in your family."

        observations = list_observations(
            target_user_id, category=category or None, storage=storage
        )
        if not observations:
            return f"No health observations found for user {target_user_id}."

        lines = []
        for obs in observations:
            lines.append(
                f"- [{obs['category']}] {obs['summary']} "
                f"(confidence: {obs.get('confidence', 'medium')}, "
                f"observed: {obs.get('observed_at', '')})"
            )
        return f"Health observations for {target_user_id}:\n" + "\n".join(lines)

    tools.append(get_health_observations)

    # ── Tool 6: search_health_conversations ──────────────────────

    if config.get("conversation_mining_enabled", True):

        @tool(
            name="search_health_conversations",
            description=(
                "Search past conversations for health-related topics. "
                "Scans recent conversations for keyword matches. "
                "Use to find past discussions about symptoms, diet, exercise, etc."
            ),
        )
        def search_health_conversations(keywords: str) -> str:
            """Search past conversations for health keywords.

            Args:
                keywords: Comma-separated keywords to search for.
            """
            from app.services.conversation import (
                get_messages,
                list_conversations,
            )

            keyword_list = [k.strip().lower() for k in keywords.split(",") if k.strip()]
            if not keyword_list:
                return "No keywords provided."

            convos = list_conversations(user_id, limit=20)
            matches = []

            for convo in convos.get("conversations", []):
                cid = convo["conversation_id"]
                msgs = get_messages(cid, limit=50)
                for msg in msgs.get("messages", []):
                    content = msg.get("content", "").lower()
                    matched_kw = [kw for kw in keyword_list if kw in content]
                    if matched_kw:
                        snippet = msg["content"][:200]
                        matches.append(
                            f"- [{', '.join(matched_kw)}] "
                            f"(conv: {cid[:8]}..., {msg.get('created_at', '')}): "
                            f"{snippet}"
                        )

            if not matches:
                return f"No conversations found matching: {', '.join(keyword_list)}"

            # Limit results to avoid overwhelming context
            return (
                f"Found {len(matches)} matches:\n"
                + "\n".join(matches[:20])
            )

        tools.append(search_health_conversations)

    # ── Tool 7: search_health_info (placeholder) ─────────────────

    if config.get("web_search_enabled", False):

        @tool(
            name="search_health_info",
            description=(
                "Search the web for general health information. "
                "Use for evidence-based health guidance, medication info, "
                "or condition details. Always verify with professional sources."
            ),
        )
        def search_health_info(query: str) -> str:
            """Search for health information online.

            Args:
                query: The health topic to search for.
            """
            return (
                f"Web search is not yet configured. "
                f"Please consult a healthcare provider or trusted medical "
                f"website for information about: {query}"
            )

        tools.append(search_health_info)

    return tools
