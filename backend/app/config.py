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
    CHAT_MEDIA_ALLOWED_TYPES: set = {
        "image/jpeg",
        "image/png",
        "image/gif",
        "image/webp",
        "audio/wav",
    }
    CHAT_MEDIA_MAX_SIZE: int = int(
        os.environ.get("CHAT_MEDIA_MAX_SIZE", str(5 * 1024 * 1024))
    )
    CHAT_MEDIA_AUDIO_MAX_SIZE: int = int(
        os.environ.get("CHAT_MEDIA_AUDIO_MAX_SIZE", str(25 * 1024 * 1024))
    )
    VOICE_ENABLED: bool = (
        os.environ.get("VOICE_ENABLED", "false").lower() == "true"
    )
    VOICE_MODEL_ID: str = os.environ.get(
        "VOICE_MODEL_ID", "amazon.nova-sonic-v1:0"
    )
    COGNITO_USER_POOL_ID: str | None = os.environ.get("COGNITO_USER_POOL_ID")
    COGNITO_CLIENT_ID: str | None = os.environ.get("COGNITO_CLIENT_ID")
    COGNITO_REGION: str = os.environ.get(
        "COGNITO_REGION", os.environ.get("AWS_REGION", "us-east-1")
    )
    SES_ENABLED: bool = os.environ.get("SES_ENABLED", "false").lower() == "true"
    SES_FROM_EMAIL: str = os.environ.get("SES_FROM_EMAIL", "")
    WEB_SEARCH_ENABLED: bool = (
        os.environ.get("WEB_SEARCH_ENABLED", "true").lower() != "false"
    )
