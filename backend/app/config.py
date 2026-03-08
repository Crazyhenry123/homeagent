import os


class Config:
    AWS_REGION: str = os.environ.get("AWS_REGION", "us-east-1")
    DYNAMODB_ENDPOINT: str | None = os.environ.get("DYNAMODB_ENDPOINT")
    TABLE_PREFIX: str = os.environ.get("TABLE_PREFIX", "")
    BEDROCK_MODEL_ID: str = os.environ.get(
        "BEDROCK_MODEL_ID", "us.anthropic.claude-opus-4-6-v1"
    )
    SYSTEM_PROMPT: str = os.environ.get(
        "SYSTEM_PROMPT",
        "You are a helpful family assistant. Be warm, friendly, and supportive.",
    )
    ADMIN_INVITE_CODE: str | None = os.environ.get("ADMIN_INVITE_CODE")
    USE_AGENT_ORCHESTRATOR: bool = (
        os.environ.get("USE_AGENT_ORCHESTRATOR", "false").lower() == "true"
    )
    AGENTCORE_MEMORY_ID: str | None = os.environ.get("AGENTCORE_MEMORY_ID")
    HEALTH_EXTRACTION_ENABLED: bool = (
        os.environ.get("HEALTH_EXTRACTION_ENABLED", "true").lower() == "true"
    )
    HEALTH_EXTRACTION_MODEL_ID: str = os.environ.get(
        "HEALTH_EXTRACTION_MODEL_ID", "us.anthropic.claude-haiku-4-5-20251001-v1:0"
    )
    S3_HEALTH_DOCUMENTS_BUCKET: str | None = os.environ.get(
        "S3_HEALTH_DOCUMENTS_BUCKET"
    )
    S3_ENDPOINT: str | None = os.environ.get("S3_ENDPOINT")

    # AgentCore configuration
    AGENTCORE_ORCHESTRATOR_AGENT_ID: str | None = os.environ.get(
        "AGENTCORE_ORCHESTRATOR_AGENT_ID"
    )
    AGENTCORE_RUNTIME_ENDPOINT: str | None = os.environ.get(
        "AGENTCORE_RUNTIME_ENDPOINT"
    )
    AGENTCORE_FAMILY_MEMORY_ID: str | None = os.environ.get(
        "AGENTCORE_FAMILY_MEMORY_ID"
    )
    AGENTCORE_MEMBER_MEMORY_ID: str | None = os.environ.get(
        "AGENTCORE_MEMBER_MEMORY_ID"
    )
    AGENTCORE_GATEWAY_ID: str | None = os.environ.get("AGENTCORE_GATEWAY_ID")
    HEALTH_MCP_ENDPOINT: str | None = os.environ.get("HEALTH_MCP_ENDPOINT")
    FAMILY_MCP_ENDPOINT: str | None = os.environ.get("FAMILY_MCP_ENDPOINT")
    COGNITO_USER_POOL_ID: str | None = os.environ.get("COGNITO_USER_POOL_ID")
    COGNITO_CLIENT_ID: str | None = os.environ.get("COGNITO_CLIENT_ID")
