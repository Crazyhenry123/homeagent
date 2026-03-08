"""AgentCore Performance Optimizations.

Wires performance requirements:
- Parallel family + member memory retrieval (Req 30.1)
- JWKS caching with 1-hour TTL (Req 30.2) — wired in agentcore_identity.py
- Sub-agent tool ID caching with 60s TTL (Req 30.4) — wired in agent_management.py

Requirements: 30.1, 30.2, 30.3, 30.4
"""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

from app.services.agentcore_memory import AgentCoreMemoryManager

logger = logging.getLogger(__name__)

# Thread pool for parallel memory retrieval
_MEMORY_EXECUTOR = ThreadPoolExecutor(max_workers=4, thread_name_prefix="mem-retrieval")


def parallel_memory_retrieval(
    memory_manager: AgentCoreMemoryManager,
    family_id: str | None,
    member_id: str,
    session_id: str,
    query: str,
    family_top_k: int = 10,
    member_top_k: int = 5,
) -> dict[str, list[Any]]:
    """Execute family and member memory retrievals in parallel.

    Requirement 30.1: Combined retrieval latency should be under 200ms
    by running both retrievals concurrently.

    Returns a dict with keys 'family' and 'member', each containing
    a list of memory records. On failure, the corresponding list is empty.
    """
    results: dict[str, list[Any]] = {"family": [], "member": []}
    futures = {}

    if family_id:
        futures["family"] = _MEMORY_EXECUTOR.submit(
            memory_manager.safe_retrieve_family_memory,
            family_id=family_id,
            query=query,
            top_k=family_top_k,
        )

    futures["member"] = _MEMORY_EXECUTOR.submit(
        memory_manager.safe_retrieve_member_memory,
        member_id=member_id,
        session_id=session_id,
        query=query,
        top_k=member_top_k,
    )

    for key, future in futures.items():
        try:
            results[key] = future.result(timeout=5.0)
        except Exception:
            logger.warning(
                "Parallel %s memory retrieval failed, proceeding without",
                key,
                exc_info=True,
            )
            results[key] = []

    return results


# ---------------------------------------------------------------------------
# JWKS Caching (Req 30.2)
# ---------------------------------------------------------------------------
# The JWKS cache is implemented in agentcore_identity.py via _JWKSCache
# with a 1-hour TTL. This avoids per-request calls to Cognito for key
# retrieval. The cache is automatically refreshed when stale.
#
# See: backend/app/agentcore_identity.py, class _JWKSCache


# ---------------------------------------------------------------------------
# Sub-Agent Tool ID Caching (Req 30.4)
# ---------------------------------------------------------------------------
# The tool ID cache is implemented in agent_management.py via
# AgentManagementClient._tool_cache with a 60-second TTL. This avoids
# repeated DynamoDB lookups within rapid message sequences. The cache
# is invalidated automatically when configs are created, updated, or
# deleted.
#
# See: backend/app/services/agent_management.py, build_sub_agent_tool_ids()


def get_performance_config() -> dict[str, Any]:
    """Return the performance configuration summary.

    Documents the caching and parallelism settings used across the system.
    """
    return {
        "memory_retrieval": {
            "parallel": True,
            "max_workers": 4,
            "timeout_seconds": 5.0,
            "target_latency_ms": 200,
        },
        "jwks_cache": {
            "ttl_seconds": 3600,  # 1 hour
            "location": "agentcore_identity._JWKSCache",
        },
        "tool_id_cache": {
            "ttl_seconds": 60,
            "location": "agent_management.AgentManagementClient._tool_cache",
            "invalidation": "automatic on config change",
        },
    }
