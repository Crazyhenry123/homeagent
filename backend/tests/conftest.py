import os

import boto3
import pytest

# Use a SEPARATE DynamoDB Local instance for tests (port 8001) so that
# running the test suite does not wipe development data on port 8000.
# Start the test instance before running tests:
#   docker run --rm -p 8001:8000 amazon/dynamodb-local -jar DynamoDBLocal.jar -inMemory -sharedDb
_TEST_DYNAMODB_ENDPOINT = os.environ.get(
    "TEST_DYNAMODB_ENDPOINT", "http://localhost:8001"
)

os.environ["DYNAMODB_ENDPOINT"] = _TEST_DYNAMODB_ENDPOINT
os.environ["AWS_REGION"] = "us-east-1"
os.environ["AWS_ACCESS_KEY_ID"] = "testing"
os.environ["AWS_SECRET_ACCESS_KEY"] = "testing"
os.environ["ADMIN_INVITE_CODE"] = "FAMILY"
os.environ["COGNITO_USER_POOL_ID"] = "us-east-1_TestPool"
os.environ["COGNITO_CLIENT_ID"] = "testclientid123"
os.environ["COGNITO_REGION"] = "us-east-1"

from app import create_app  # noqa: E402
from app.config import Config  # noqa: E402


@pytest.fixture(scope="session")
def dynamo_client():
    return boto3.client(
        "dynamodb",
        endpoint_url=_TEST_DYNAMODB_ENDPOINT,
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
