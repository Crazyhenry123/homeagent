"""Tests for health observation extraction from chat — mocked Bedrock."""

import json
from unittest.mock import MagicMock, patch

from app.services.health_extraction import extract_health_observations


def _mock_converse_response(text: str) -> dict:
    return {
        "output": {"message": {"content": [{"text": text}]}},
    }


def test_extraction_valid_observations(app):
    """Valid JSON array of observations should be saved to DynamoDB."""
    observations = [
        {
            "category": "symptom",
            "summary": "User reported headache",
            "detail": "Mentioned having a headache since morning",
            "confidence": "high",
        },
        {
            "category": "diet",
            "summary": "Had salad for lunch",
            "detail": "",
            "confidence": "medium",
        },
    ]

    with app.app_context():
        mock_bedrock = MagicMock()
        mock_bedrock.converse.return_value = _mock_converse_response(
            json.dumps(observations)
        )

        with patch("boto3.client", return_value=mock_bedrock):
            with patch("boto3.resource") as mock_resource:
                mock_table = MagicMock()
                mock_resource.return_value.Table.return_value = mock_table

                extract_health_observations(
                    user_id="user1",
                    conversation_id="conv1",
                    user_message="I've had a headache all day",
                    assistant_response="I'm sorry to hear about your headache.",
                    region="us-east-1",
                    model_id="us.anthropic.claude-haiku-4-5-20251001-v1:0",
                )

                assert mock_table.put_item.call_count == 2
                # Verify first observation
                first_call = mock_table.put_item.call_args_list[0]
                item = first_call[1]["Item"]
                assert item["user_id"] == "user1"
                assert item["category"] == "symptom"
                assert item["source_conversation_id"] == "conv1"


def test_extraction_empty_array(app):
    """Empty array means no health observations — nothing saved."""
    with app.app_context():
        mock_bedrock = MagicMock()
        mock_bedrock.converse.return_value = _mock_converse_response("[]")

        with patch("boto3.client", return_value=mock_bedrock):
            with patch("boto3.resource") as mock_resource:
                mock_table = MagicMock()
                mock_resource.return_value.Table.return_value = mock_table

                extract_health_observations(
                    user_id="user1",
                    conversation_id="conv1",
                    user_message="Hello!",
                    assistant_response="Hi there!",
                    region="us-east-1",
                    model_id="us.anthropic.claude-haiku-4-5-20251001-v1:0",
                )

                mock_table.put_item.assert_not_called()


def test_extraction_malformed_json(app):
    """Malformed JSON should not raise — just log a warning."""
    with app.app_context():
        mock_bedrock = MagicMock()
        mock_bedrock.converse.return_value = _mock_converse_response(
            "This is not JSON at all"
        )

        with patch("boto3.client", return_value=mock_bedrock):
            # Should not raise
            extract_health_observations(
                user_id="user1",
                conversation_id="conv1",
                user_message="Hello!",
                assistant_response="Hi there!",
                region="us-east-1",
                model_id="us.anthropic.claude-haiku-4-5-20251001-v1:0",
            )


def test_extraction_bedrock_error(app):
    """Bedrock API error should not raise — just log the exception."""
    with app.app_context():
        mock_bedrock = MagicMock()
        mock_bedrock.converse.side_effect = Exception("Bedrock is down")

        with patch("boto3.client", return_value=mock_bedrock):
            # Should not raise
            extract_health_observations(
                user_id="user1",
                conversation_id="conv1",
                user_message="Hello!",
                assistant_response="Hi there!",
                region="us-east-1",
                model_id="us.anthropic.claude-haiku-4-5-20251001-v1:0",
            )


def test_extraction_invalid_category_defaults_to_general(app):
    """Invalid category in extraction output should default to 'general'."""
    observations = [
        {
            "category": "unknown_category",
            "summary": "Something happened",
            "confidence": "low",
        },
    ]

    with app.app_context():
        mock_bedrock = MagicMock()
        mock_bedrock.converse.return_value = _mock_converse_response(
            json.dumps(observations)
        )

        with patch("boto3.client", return_value=mock_bedrock):
            with patch("boto3.resource") as mock_resource:
                mock_table = MagicMock()
                mock_resource.return_value.Table.return_value = mock_table

                extract_health_observations(
                    user_id="user1",
                    conversation_id="conv1",
                    user_message="Something happened",
                    assistant_response="Tell me more.",
                    region="us-east-1",
                    model_id="us.anthropic.claude-haiku-4-5-20251001-v1:0",
                )

                item = mock_table.put_item.call_args[1]["Item"]
                assert item["category"] == "general"


def test_extraction_skips_empty_summary(app):
    """Observations with empty summary should be skipped."""
    observations = [
        {"category": "diet", "summary": "", "confidence": "low"},
        {"category": "diet", "summary": "Had breakfast", "confidence": "medium"},
    ]

    with app.app_context():
        mock_bedrock = MagicMock()
        mock_bedrock.converse.return_value = _mock_converse_response(
            json.dumps(observations)
        )

        with patch("boto3.client", return_value=mock_bedrock):
            with patch("boto3.resource") as mock_resource:
                mock_table = MagicMock()
                mock_resource.return_value.Table.return_value = mock_table

                extract_health_observations(
                    user_id="user1",
                    conversation_id="conv1",
                    user_message="I had breakfast",
                    assistant_response="Great!",
                    region="us-east-1",
                    model_id="us.anthropic.claude-haiku-4-5-20251001-v1:0",
                )

                # Only the second observation (with non-empty summary) saved
                assert mock_table.put_item.call_count == 1
