"""AgentCore Security Controls.

Wires security requirements across the AgentCore migration:
- Member short-term memory scoped by member_id and session_id (Req 31.1)
- IAM authentication for Gateway-to-MCP-server communication (Req 31.2)
- MCP server endpoints within VPC (Req 31.3 — CDK config)
- Short-lived Cognito access tokens with refresh token rotation (Req 31.4)
- Family membership verification before family memory access (Req 31.6)

Requirements: 31.1, 31.2, 31.3, 31.4, 31.6
"""

from __future__ import annotations

import logging
from typing import Any

import boto3

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 31.1: Member short-term memory scoped by member_id and session_id
# ---------------------------------------------------------------------------


def validate_member_memory_scope(
    member_id: str,
    session_id: str,
    requesting_member_id: str,
) -> bool:
    """Verify that the requesting member can access the specified memory scope.

    Member short-term memory is scoped by both member_id and session_id.
    A member can only access their own short-term memory.

    Returns True if access is allowed, False otherwise.
    """
    if not member_id or not session_id:
        logger.warning("Empty member_id or session_id in memory scope check")
        return False

    if member_id != requesting_member_id:
        logger.warning(
            "Member %s attempted to access memory for member %s",
            requesting_member_id,
            member_id,
        )
        return False

    return True


# ---------------------------------------------------------------------------
# 31.2: IAM authentication for Gateway-to-MCP-server communication
# ---------------------------------------------------------------------------


def get_iam_auth_config() -> dict[str, str]:
    """Return IAM authentication configuration for MCP server registration.

    All Gateway-to-MCP-server communication uses IAM authentication.
    """
    return {"type": "iam", "service": "execute-api"}


def validate_iam_auth_config(auth_config: dict | None) -> bool:
    """Validate that an MCP server registration uses IAM authentication.

    Returns True if the auth config specifies IAM authentication.
    """
    if auth_config is None:
        return False
    return auth_config.get("type") == "iam"


# ---------------------------------------------------------------------------
# 31.3: MCP server endpoints within VPC (CDK configuration helper)
# ---------------------------------------------------------------------------


def get_vpc_security_config() -> dict[str, Any]:
    """Return VPC security configuration for MCP server endpoints.

    MCP server endpoints must run within the VPC and not be publicly
    accessible. This config is used by the CDK stack.
    """
    return {
        "vpc_enabled": True,
        "public_access": False,
        "security_group_rules": {
            "ingress": [
                {
                    "protocol": "tcp",
                    "port": 443,
                    "source": "vpc",
                    "description": "HTTPS from within VPC only",
                }
            ],
            "egress": [
                {
                    "protocol": "tcp",
                    "port": 443,
                    "destination": "0.0.0.0/0",
                    "description": "HTTPS outbound for AWS services",
                }
            ],
        },
    }


# ---------------------------------------------------------------------------
# 31.4: Short-lived Cognito access tokens with refresh token rotation
# ---------------------------------------------------------------------------


def get_cognito_token_config() -> dict[str, Any]:
    """Return Cognito token configuration.

    Access tokens: 1-hour expiry.
    Refresh tokens: 30-day validity with rotation enabled.
    """
    return {
        "access_token_validity_hours": 1,
        "id_token_validity_hours": 1,
        "refresh_token_validity_days": 30,
        "enable_token_revocation": True,
    }


def validate_token_expiry(token_claims: dict) -> bool:
    """Validate that a token has appropriate short-lived expiry.

    Access tokens should expire within 1 hour (3600 seconds).
    """
    import time

    exp = token_claims.get("exp")
    iat = token_claims.get("iat")

    if exp is None or iat is None:
        return False

    token_lifetime = exp - iat
    max_lifetime = 3600  # 1 hour in seconds

    if token_lifetime > max_lifetime:
        logger.warning(
            "Token lifetime %d exceeds maximum %d seconds",
            token_lifetime,
            max_lifetime,
        )
        return False

    return True


# ---------------------------------------------------------------------------
# 31.6: Family membership verification
# ---------------------------------------------------------------------------


def verify_family_membership(
    family_id: str,
    member_id: str,
    region: str = "us-east-1",
    endpoint_url: str | None = None,
) -> bool:
    """Verify that a member belongs to the specified family.

    Checks the FamilyGroups table for a (family_id, member_id) entry.
    Blocks cross-family access at the application layer.

    Returns True if the member belongs to the family, False otherwise.
    """
    if not family_id or not member_id:
        return False

    try:
        kwargs: dict = {"region_name": region}
        if endpoint_url:
            kwargs["endpoint_url"] = endpoint_url
        dynamodb = boto3.resource("dynamodb", **kwargs)
        table = dynamodb.Table("FamilyGroups")

        response = table.get_item(
            Key={"family_id": family_id, "member_id": member_id}
        )
        item = response.get("Item")

        if item is None:
            logger.warning(
                "Member %s is not in family %s — blocking family memory access",
                member_id,
                family_id,
            )
            return False

        return True
    except Exception:
        logger.error(
            "Failed to verify family membership for %s in %s",
            member_id,
            family_id,
            exc_info=True,
        )
        return False


def verify_family_memory_access(
    family_id: str,
    requesting_member_id: str,
    region: str = "us-east-1",
    endpoint_url: str | None = None,
) -> bool:
    """Verify that the requesting user can access family memory.

    Combines family membership verification with the requirement that
    only family members can access family-level memory.

    Returns True if access is allowed, False otherwise.
    """
    return verify_family_membership(
        family_id=family_id,
        member_id=requesting_member_id,
        region=region,
        endpoint_url=endpoint_url,
    )
