import os

import boto3
import pytest

# Point to DynamoDB Local before importing app
os.environ["DYNAMODB_ENDPOINT"] = "http://localhost:8000"
os.environ["AWS_REGION"] = "us-east-1"
os.environ["AWS_ACCESS_KEY_ID"] = "testing"
os.environ["AWS_SECRET_ACCESS_KEY"] = "testing"
os.environ["ADMIN_INVITE_CODE"] = "FAMILY"

from app import create_app  # noqa: E402
from app.config import Config  # noqa: E402


@pytest.fixture(scope="session")
def dynamo_client():
    return boto3.client(
        "dynamodb",
        endpoint_url="http://localhost:8000",
        region_name="us-east-1",
    )


@pytest.fixture()
def app(dynamo_client):
    """Create a fresh Flask app with clean tables for each test."""
    # Clean up tables
    existing = dynamo_client.list_tables()["TableNames"]
    for table_name in existing:
        dynamo_client.delete_table(TableName=table_name)

    config = Config()
    application = create_app(config)
    application.config["TESTING"] = True

    yield application


@pytest.fixture()
def client(app):
    return app.test_client()
