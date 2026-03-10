"""AgentCore data model classes for the HomeAgent platform migration.

Defines dataclasses for agent templates, configs, memory records,
identity context, streaming events, and session management.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class FamilyMemoryCategory(str, Enum):
    """Valid categories for family long-term memory records."""

    HEALTH = "health"
    PREFERENCES = "preferences"
    CONTEXT = "context"


class StreamEventType(str, Enum):
    """Valid types for streaming response events."""

    TEXT_DELTA = "text_delta"
    TOOL_USE = "tool_use"
    MESSAGE_DONE = "message_done"
    ERROR = "error"


# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------

_AGENT_TYPE_PATTERN = re.compile(r"^[a-z][a-z0-9_\-]*$")

_MEMORY_KEY_PATTERN = re.compile(r"^[a-z_]+/[a-z_]+/[a-zA-Z0-9_\-]+$")

CONTENT_MAX_LENGTH = 10_000


def _validate_non_empty_string(value: str, name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")


def _validate_agent_type(value: str) -> None:
    """Validate agent_type is a valid slug (lowercase, hyphens, underscores)."""
    if not _AGENT_TYPE_PATTERN.match(value):
        raise ValueError(
            f"agent_type must be a lowercase slug using letters, digits, "
            f"hyphens, and underscores; got '{value}'"
        )


# ---------------------------------------------------------------------------
# AgentTemplate
# ---------------------------------------------------------------------------


@dataclass
class AgentTemplate:
    """Definition of a sub-agent type.

    Replaces the AgentTemplates DynamoDB item structure with a typed
    dataclass that includes validation.
    """

    template_id: str
    agent_type: str
    name: str
    description: str
    system_prompt: str
    tool_server_ids: list[str] = field(default_factory=list)
    default_config: dict[str, Any] = field(default_factory=dict)
    is_builtin: bool = False
    available_to: str | list[str] = "all"
    created_by: str = ""
    created_at: str = ""
    updated_at: str = ""

    def validate(self) -> None:
        """Validate template fields.

        Raises ``ValueError`` on constraint violations.
        """
        _validate_non_empty_string(self.template_id, "template_id")
        _validate_non_empty_string(self.agent_type, "agent_type")
        _validate_agent_type(self.agent_type)
        _validate_non_empty_string(self.name, "name")
        self._validate_available_to()

    def _validate_available_to(self) -> None:
        if self.available_to == "all":
            return
        if isinstance(self.available_to, list):
            if len(self.available_to) == 0:
                raise ValueError(
                    "available_to must be 'all' or a non-empty list of user_ids"
                )
            for uid in self.available_to:
                _validate_non_empty_string(uid, "available_to entry")
            return
        raise ValueError(
            "available_to must be 'all' or a non-empty list of user_ids"
        )


# ---------------------------------------------------------------------------
# AgentConfig
# ---------------------------------------------------------------------------


@dataclass
class AgentConfig:
    """Per-user agent configuration record.

    Keyed by (user_id, agent_type). Tracks whether a sub-agent is enabled
    for a specific user and stores merged config overrides.
    """

    user_id: str
    agent_type: str
    enabled: bool = True
    config: dict[str, Any] = field(default_factory=dict)
    gateway_tool_id: str | None = None
    updated_at: str = ""

    def validate(self) -> None:
        _validate_non_empty_string(self.user_id, "user_id")
        _validate_non_empty_string(self.agent_type, "agent_type")
        _validate_agent_type(self.agent_type)


# ---------------------------------------------------------------------------
# SubAgentToolConfig
# ---------------------------------------------------------------------------


@dataclass
class SubAgentToolConfig:
    """Runtime resolution object for a sub-agent's tool configuration."""

    agent_type: str
    tool_name: str
    description: str
    sub_agent_runtime_id: str | None = None
    system_prompt: str = ""
    tool_server_ids: list[str] = field(default_factory=list)
    user_config: dict[str, Any] = field(default_factory=dict)

    def validate(self) -> None:
        _validate_non_empty_string(self.agent_type, "agent_type")
        _validate_non_empty_string(self.tool_name, "tool_name")


# ---------------------------------------------------------------------------
# FamilyMemoryRecord
# ---------------------------------------------------------------------------


@dataclass
class FamilyMemoryRecord:
    """A family-level long-term memory record (no TTL)."""

    family_id: str
    memory_key: str
    category: str
    content: str
    source_member_id: str = ""
    agentcore_memory_id: str = ""
    created_at: str = ""
    updated_at: str = ""
    ttl: int | None = None  # Always None for long-term family memory

    def validate(self) -> None:
        _validate_non_empty_string(self.family_id, "family_id")
        _validate_non_empty_string(self.memory_key, "memory_key")
        self._validate_category()
        self._validate_memory_key_format()
        self._validate_content_length()

    def _validate_category(self) -> None:
        try:
            FamilyMemoryCategory(self.category)
        except ValueError:
            valid = ", ".join(c.value for c in FamilyMemoryCategory)
            raise ValueError(
                f"category must be one of: {valid}; got '{self.category}'"
            )

    def _validate_memory_key_format(self) -> None:
        if not _MEMORY_KEY_PATTERN.match(self.memory_key):
            raise ValueError(
                "memory_key must follow the format "
                "'{category}/{subcategory}/{identifier}' using lowercase "
                f"letters, digits, underscores, and hyphens; got '{self.memory_key}'"
            )

    def _validate_content_length(self) -> None:
        if len(self.content) > CONTENT_MAX_LENGTH:
            raise ValueError(
                f"content exceeds maximum length of {CONTENT_MAX_LENGTH} characters "
                f"(got {len(self.content)})"
            )


# ---------------------------------------------------------------------------
# MemberMemoryRecord
# ---------------------------------------------------------------------------


@dataclass
class MemberMemoryRecord:
    """A member-level short-term memory record (30-day TTL)."""

    member_id: str
    session_id: str
    agentcore_memory_id: str = ""
    summary: str = ""
    message_count: int = 0
    created_at: str = ""
    updated_at: str = ""
    ttl: int | None = None  # 30-day TTL from creation

    def validate(self) -> None:
        _validate_non_empty_string(self.member_id, "member_id")
        _validate_non_empty_string(self.session_id, "session_id")


# ---------------------------------------------------------------------------
# IdentityContext
# ---------------------------------------------------------------------------


@dataclass
class IdentityContext:
    """Authenticated user identity extracted from a validated JWT."""

    user_id: str
    family_id: str | None
    role: str
    cognito_sub: str

    def validate(self) -> None:
        _validate_non_empty_string(self.user_id, "user_id")
        _validate_non_empty_string(self.cognito_sub, "cognito_sub")
        if self.role not in ("admin", "member"):
            raise ValueError(
                f"role must be 'admin' or 'member'; got '{self.role}'"
            )


# ---------------------------------------------------------------------------
# StreamEvent
# ---------------------------------------------------------------------------


@dataclass
class StreamEvent:
    """A server-sent event chunk emitted during agent response streaming."""

    type: str
    content: str = ""
    conversation_id: str | None = None
    data: dict[str, Any] = field(default_factory=dict)

    def validate(self) -> None:
        try:
            StreamEventType(self.type)
        except ValueError:
            valid = ", ".join(t.value for t in StreamEventType)
            raise ValueError(
                f"StreamEvent type must be one of: {valid}; got '{self.type}'"
            )


# ---------------------------------------------------------------------------
# MemoryConfig
# ---------------------------------------------------------------------------


@dataclass
class MemoryConfig:
    """Configuration for a single AgentCore Memory store tier."""

    memory_id: str
    session_id: str
    actor_id: str
    retrieval_namespaces: list[str] = field(default_factory=list)

    def validate(self) -> None:
        _validate_non_empty_string(self.memory_id, "memory_id")
        _validate_non_empty_string(self.session_id, "session_id")
        _validate_non_empty_string(self.actor_id, "actor_id")


# ---------------------------------------------------------------------------
# CombinedSessionManager
# ---------------------------------------------------------------------------


@dataclass
class CombinedSessionManager:
    """Merges family and member memory tiers into a single session config."""

    family_config: MemoryConfig
    member_config: MemoryConfig
    family_id: str = ""
    member_id: str = ""
    session_id: str = ""

    def validate(self) -> None:
        self.family_config.validate()
        self.member_config.validate()
        if self.family_config.memory_id == self.member_config.memory_id:
            raise ValueError(
                "family and member memory stores must use distinct memory_ids"
            )


# ---------------------------------------------------------------------------
# IsolatedContext (Request-Scoped)
# ---------------------------------------------------------------------------

_ISOLATED_CONTEXT_STORE_STATUSES = {"active", "pending"}


@dataclass
class IsolatedContext:
    """Request-scoped context for family memory isolation.

    Carries the verified family membership and resolved store information
    through the request lifecycle.  When ``store_status`` is ``"pending"``
    the ``family_store_id`` is ``None`` and memory operations are routed
    through the write-behind buffer.
    """

    family_id: str
    member_id: str
    family_store_id: str | None
    is_verified: bool
    store_status: str  # "active" | "pending"
    verified_at: str

    def validate(self) -> None:
        """Validate context fields.

        Raises ``ValueError`` on constraint violations.
        """
        if self.is_verified:
            _validate_non_empty_string(self.family_id, "family_id")
            _validate_non_empty_string(self.member_id, "member_id")
        if self.store_status not in _ISOLATED_CONTEXT_STORE_STATUSES:
            valid = ", ".join(sorted(_ISOLATED_CONTEXT_STORE_STATUSES))
            raise ValueError(
                f"store_status must be one of: {valid}; got '{self.store_status}'"
            )
        if self.store_status == "active":
            if not self.family_store_id or not self.family_store_id.strip():
                raise ValueError(
                    "family_store_id must be non-empty when store_status is 'active'"
                )


# ---------------------------------------------------------------------------
# FamilyMemoryStoresItem
# ---------------------------------------------------------------------------

_FAMILY_STORE_STATUSES = {"active", "migrating", "provisioning", "decommissioned"}


@dataclass
class FamilyMemoryStoresItem:
    """Persistent registry entry mapping a family to its dedicated AgentCore
    Memory store.

    Stored in the FamilyMemoryStores DynamoDB table with ``family_id`` as
    the partition key.
    """

    family_id: str
    store_id: str
    store_name: str
    created_at: str
    updated_at: str
    status: str  # "active" | "migrating" | "provisioning" | "decommissioned"
    event_expiry_days: int = 365

    def validate(self) -> None:
        """Validate registry entry fields.

        Raises ``ValueError`` on constraint violations.
        """
        _validate_non_empty_string(self.family_id, "family_id")
        _validate_non_empty_string(self.store_id, "store_id")
        if self.status not in _FAMILY_STORE_STATUSES:
            valid = ", ".join(sorted(_FAMILY_STORE_STATUSES))
            raise ValueError(
                f"status must be one of: {valid}; got '{self.status}'"
            )
        if self.event_expiry_days <= 0:
            raise ValueError(
                f"event_expiry_days must be a positive integer; got {self.event_expiry_days}"
            )
