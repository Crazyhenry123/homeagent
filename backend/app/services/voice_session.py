"""VoiceSession — manages a bidirectional audio stream with Amazon Nova Sonic."""

import base64
import json
import logging
from typing import Generator

import boto3
from flask import current_app

logger = logging.getLogger(__name__)


class VoiceSession:
    """Manages a Nova Sonic bidirectional streaming session.

    Usage:
        session = VoiceSession(user_id, conversation_id)
        session.start()
        session.send_audio(pcm_bytes)
        for event in session.receive():
            ...
        session.end()
    """

    def __init__(
        self,
        user_id: str,
        conversation_id: str | None = None,
        system_prompt: str | None = None,
    ):
        self.user_id = user_id
        self.conversation_id = conversation_id
        self.system_prompt = system_prompt
        self._client = None
        self._stream = None
        self._started = False
        self._ended = False

    def _get_client(self):
        if self._client is None:
            self._client = boto3.client(
                "bedrock-runtime",
                region_name=current_app.config["AWS_REGION"],
            )
        return self._client

    def start(self) -> None:
        """Start the bidirectional stream with Nova Sonic."""
        if self._started:
            return

        model_id = current_app.config.get(
            "VOICE_MODEL_ID", "amazon.nova-sonic-v1:0"
        )
        client = self._get_client()

        system_prompt = self.system_prompt or current_app.config.get(
            "SYSTEM_PROMPT",
            "You are a helpful family assistant. Be warm, friendly, and supportive.",
        )

        try:
            self._stream = client.invoke_model_with_bidirectional_stream(
                modelId=model_id
            )
            self._started = True

            # Send session start event with configuration
            self._send_event(
                {
                    "event": {
                        "sessionStart": {
                            "inferenceConfiguration": {
                                "maxTokens": 1024,
                                "topP": 0.9,
                                "temperature": 0.7,
                            },
                            "systemPrompt": system_prompt,
                        }
                    }
                }
            )
        except Exception:
            logger.exception("Failed to start Nova Sonic stream")
            raise

    def _send_event(self, event: dict) -> None:
        """Send an event to the Nova Sonic stream."""
        if not self._stream:
            raise RuntimeError("Stream not started")
        self._stream["body"].send(json.dumps(event).encode())

    def send_audio(self, pcm_data: bytes) -> None:
        """Send an audio chunk (PCM 16-bit 16kHz mono) to Nova Sonic."""
        if not self._started or self._ended:
            return
        encoded = base64.b64encode(pcm_data).decode()
        self._send_event(
            {
                "event": {
                    "audioInput": {
                        "audio": {"audioChunk": encoded}
                    }
                }
            }
        )

    def send_audio_end(self) -> None:
        """Signal end of audio input."""
        if not self._started or self._ended:
            return
        self._send_event({"event": {"audioInputEnd": {}}})

    def receive(self) -> Generator[dict, None, None]:
        """Receive events from Nova Sonic. Yields dicts with type and data."""
        if not self._stream:
            return

        try:
            for event_bytes in self._stream["body"]:
                try:
                    event = json.loads(event_bytes)
                except (json.JSONDecodeError, TypeError):
                    continue

                evt = event.get("event", {})

                if "audioOutput" in evt:
                    audio_chunk = evt["audioOutput"]["audio"].get("audioChunk", "")
                    yield {
                        "type": "audio_chunk",
                        "data": audio_chunk,
                    }

                elif "textOutput" in evt:
                    text = evt["textOutput"].get("text", "")
                    role = evt["textOutput"].get("role", "assistant")
                    yield {
                        "type": "transcript",
                        "role": role,
                        "content": text,
                    }

                elif "sessionEnd" in evt:
                    yield {"type": "session_end"}
                    break

                elif "error" in evt:
                    yield {
                        "type": "error",
                        "content": evt["error"].get("message", "Unknown error"),
                    }
                    break
        except Exception:
            logger.exception("Error receiving from Nova Sonic stream")
            yield {"type": "error", "content": "Voice stream connection lost"}

    def end(self) -> None:
        """End the voice session."""
        if self._ended:
            return
        self._ended = True
        try:
            if self._stream:
                self._send_event({"event": {"sessionEnd": {}}})
        except Exception:
            logger.debug("Error sending session end", exc_info=True)
