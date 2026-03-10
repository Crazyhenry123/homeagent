"""Opaque cursor encoding for DynamoDB pagination.

Encodes LastEvaluatedKey dicts into URL-safe base64 strings so that
API consumers never see raw DynamoDB key structures.
"""

from __future__ import annotations

import base64
import json


class CursorCodec:
    """Stateless encoder/decoder for DynamoDB pagination cursors."""

    @staticmethod
    def encode(last_evaluated_key: dict | None) -> str | None:
        """Encode a LastEvaluatedKey dict into an opaque cursor string."""
        if last_evaluated_key is None:
            return None
        json_bytes = json.dumps(last_evaluated_key, sort_keys=True).encode("utf-8")
        return base64.urlsafe_b64encode(json_bytes).decode("ascii")

    @staticmethod
    def decode(cursor: str | None) -> dict | None:
        """Decode an opaque cursor string back to a LastEvaluatedKey dict.

        Raises:
            ValueError: If the cursor is malformed.
        """
        if cursor is None:
            return None
        try:
            json_bytes = base64.urlsafe_b64decode(cursor.encode("ascii"))
            result = json.loads(json_bytes)
        except (ValueError, json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise ValueError(f"Invalid cursor format: {exc}") from exc
        if not isinstance(result, dict):
            raise ValueError("Invalid cursor format: expected a JSON object")
        return result
