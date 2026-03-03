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
