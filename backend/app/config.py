import os


class Config:
    AWS_REGION: str = os.environ.get("AWS_REGION", "us-east-1")
    DYNAMODB_ENDPOINT: str | None = os.environ.get("DYNAMODB_ENDPOINT")
    TABLE_PREFIX: str = os.environ.get("TABLE_PREFIX", "")
    BEDROCK_MODEL_ID: str = os.environ.get(
        "BEDROCK_MODEL_ID", "us.anthropic.claude-opus-4-0-20250514"
    )
    SYSTEM_PROMPT: str = os.environ.get(
        "SYSTEM_PROMPT",
        "You are a helpful family assistant. Be warm, friendly, and supportive.",
    )
    ADMIN_INVITE_CODE: str | None = os.environ.get("ADMIN_INVITE_CODE")
