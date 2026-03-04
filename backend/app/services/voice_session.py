"""VoiceSession — manages a bidirectional audio stream with Amazon Nova Sonic."""

import asyncio
import base64
import json
import logging
import queue
import struct
import threading
from typing import Generator

from flask import current_app

logger = logging.getLogger(__name__)

PROMPT_NAME = "voice_chat"
AUDIO_CONTENT_NAME = "user_audio"


def _make_wav_header(
    pcm_length: int, sample_rate: int = 24000, bits: int = 16, channels: int = 1
) -> bytes:
    """Build a 44-byte WAV header for raw PCM data."""
    byte_rate = sample_rate * channels * bits // 8
    block_align = channels * bits // 8
    return struct.pack(
        "<4sI4s4sIHHIIHH4sI",
        b"RIFF",
        36 + pcm_length,
        b"WAVE",
        b"fmt ",
        16,  # fmt chunk size
        1,  # PCM format
        channels,
        sample_rate,
        byte_rate,
        block_align,
        bits,
        b"data",
        pcm_length,
    )


class VoiceSession:
    """Manages a Nova Sonic bidirectional streaming session.

    Uses the aws_sdk_bedrock_runtime Smithy SDK which provides the
    invoke_model_with_bidirectional_stream API required by Nova Sonic.
    A single persistent asyncio event loop runs in a background thread.
    All async operations go through asyncio.run_coroutine_threadsafe().

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
    ) -> None:
        self.user_id = user_id
        self.conversation_id = conversation_id
        self.system_prompt = system_prompt
        self._stream = None
        self._started = False
        self._ended = False
        self._output_queue: queue.Queue[dict | None] = queue.Queue()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        """Start the bidirectional stream with Nova Sonic."""
        if self._started:
            return

        region = current_app.config["AWS_REGION"]
        model_id = current_app.config.get("VOICE_MODEL_ID", "amazon.nova-sonic-v1:0")
        system_prompt = self.system_prompt or current_app.config.get(
            "SYSTEM_PROMPT",
            "You are a helpful family assistant. Be warm, friendly, and supportive.",
        )

        # Store config for the background thread (Flask app context won't be available)
        self._model_id = model_id
        self._region = region
        self._system_prompt_text = system_prompt

        # Create a persistent event loop on a background thread
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self._loop.run_forever, daemon=True)
        self._thread.start()

        try:
            # Run all async setup on the persistent loop
            future = asyncio.run_coroutine_threadsafe(self._async_setup(), self._loop)
            future.result(timeout=30)
        except Exception:
            logger.exception("Failed to start Nova Sonic stream")
            # Clean up the loop and thread on failure
            self._loop.call_soon_threadsafe(self._loop.stop)
            self._thread.join(timeout=5)
            raise

        # Schedule the receive coroutine on the persistent loop
        asyncio.run_coroutine_threadsafe(self._async_receive(), self._loop)

    async def _async_setup(self) -> None:
        """Create client, open stream, and send all 6 setup events."""
        from aws_sdk_bedrock_runtime.client import BedrockRuntimeClient
        from aws_sdk_bedrock_runtime.config import Config as BedrockConfig
        from aws_sdk_bedrock_runtime.models import (
            InvokeModelWithBidirectionalStreamOperationInput,
        )

        client = BedrockRuntimeClient(config=BedrockConfig(region=self._region))
        self._stream = await client.invoke_model_with_bidirectional_stream(
            InvokeModelWithBidirectionalStreamOperationInput(model_id=self._model_id)
        )

        # Send session start
        await self._async_send_event(
            {
                "event": {
                    "sessionStart": {
                        "inferenceConfiguration": {
                            "maxTokens": 1024,
                            "topP": 0.9,
                            "temperature": 0.7,
                        },
                    }
                }
            }
        )

        # Send prompt start with audio config and system prompt
        await self._async_send_event(
            {
                "event": {
                    "promptStart": {
                        "promptName": PROMPT_NAME,
                        "textInputConfiguration": {"mediaType": "text/plain"},
                        "audioInputConfiguration": {
                            "mediaType": "audio/lpcm",
                            "sampleRateHertz": 16000,
                            "sampleSizeBits": 16,
                            "channelCount": 1,
                            "audioType": "SPEECH",
                            "encoding": "base64",
                        },
                        "audioOutputConfiguration": {
                            "mediaType": "audio/lpcm",
                            "sampleRateHertz": 24000,
                            "sampleSizeBits": 16,
                            "channelCount": 1,
                            "voiceId": "tiffany",
                        },
                        "textOutputConfiguration": {
                            "mediaType": "text/plain",
                        },
                    }
                }
            }
        )

        # Send system prompt as text content
        await self._async_send_event(
            {
                "event": {
                    "contentStart": {
                        "promptName": PROMPT_NAME,
                        "contentName": "system_prompt",
                        "type": "TEXT",
                        "interactive": False,
                    }
                }
            }
        )
        await self._async_send_event(
            {
                "event": {
                    "textInput": {
                        "promptName": PROMPT_NAME,
                        "contentName": "system_prompt",
                        "content": self._system_prompt_text,
                    }
                }
            }
        )
        await self._async_send_event(
            {
                "event": {
                    "contentEnd": {
                        "promptName": PROMPT_NAME,
                        "contentName": "system_prompt",
                    }
                }
            }
        )

        # Start audio content stream
        await self._async_send_event(
            {
                "event": {
                    "contentStart": {
                        "promptName": PROMPT_NAME,
                        "contentName": AUDIO_CONTENT_NAME,
                        "type": "AUDIO",
                        "interactive": True,
                    }
                }
            }
        )

        self._started = True

    async def _async_send_event(self, event: dict) -> None:
        """Send an event to the Nova Sonic stream."""
        from aws_sdk_bedrock_runtime.models import (
            BidirectionalInputPayloadPart,
            InvokeModelWithBidirectionalStreamInputChunk,
        )

        chunk = InvokeModelWithBidirectionalStreamInputChunk(
            value=BidirectionalInputPayloadPart(
                bytes_=json.dumps(event).encode("utf-8")
            )
        )
        await self._stream.input_stream.send(chunk)

    def _send_event_sync(self, event: dict) -> None:
        """Send an event synchronously via the persistent event loop."""
        future = asyncio.run_coroutine_threadsafe(
            self._async_send_event(event), self._loop
        )
        future.result(timeout=10)

    async def _async_receive(self) -> None:
        """Async receive from the Nova Sonic stream."""
        try:
            while self._started and not self._ended:
                try:
                    output = await self._stream.await_output()
                    result = await output[1].receive()

                    if result.value and result.value.bytes_:
                        data = json.loads(result.value.bytes_.decode("utf-8"))
                        evt = data.get("event", {})
                        logger.info("Nova event keys: %s", list(evt.keys()))

                        if "audioOutput" in evt:
                            content = evt["audioOutput"].get("content", "")
                            if content:
                                # Wrap raw LPCM in a WAV container for mobile playback
                                pcm = base64.b64decode(content)
                                wav_header = _make_wav_header(len(pcm))
                                wav_b64 = base64.b64encode(wav_header + pcm).decode()
                                self._output_queue.put(
                                    {
                                        "type": "audio_chunk",
                                        "data": wav_b64,
                                    }
                                )

                        elif "textOutput" in evt:
                            text = evt["textOutput"].get("content", "")
                            role = evt["textOutput"].get("role", "assistant")
                            if text:
                                self._output_queue.put(
                                    {
                                        "type": "transcript",
                                        "role": role,
                                        "content": text,
                                    }
                                )

                        elif "sessionEnd" in evt:
                            self._output_queue.put({"type": "session_end"})
                            break

                        elif "error" in evt:
                            self._output_queue.put(
                                {
                                    "type": "error",
                                    "content": evt["error"].get(
                                        "message", "Unknown error"
                                    ),
                                }
                            )
                            break

                except StopAsyncIteration:
                    break
                except Exception as exc:
                    logger.debug("Receive iteration ended", exc_info=True)
                    self._output_queue.put(
                        {
                            "type": "error",
                            "content": str(exc) or "Voice stream connection lost",
                        }
                    )
                    break
        except Exception:
            logger.exception("Error in Nova Sonic receive loop")
            self._output_queue.put(
                {"type": "error", "content": "Voice stream connection lost"}
            )
        finally:
            self._output_queue.put(None)

    def send_audio(self, pcm_data: bytes) -> None:
        """Send an audio chunk (PCM 16-bit 16kHz mono) to Nova Sonic."""
        if not self._started or self._ended:
            return
        encoded = base64.b64encode(pcm_data).decode()
        self._send_event_sync(
            {
                "event": {
                    "audioInput": {
                        "promptName": PROMPT_NAME,
                        "contentName": AUDIO_CONTENT_NAME,
                        "content": encoded,
                    }
                }
            }
        )

    def send_audio_end(self) -> None:
        """Signal end of audio input and close the content stream."""
        if not self._started or self._ended:
            return
        self._send_event_sync(
            {
                "event": {
                    "contentEnd": {
                        "promptName": PROMPT_NAME,
                        "contentName": AUDIO_CONTENT_NAME,
                    }
                }
            }
        )

    def receive(self) -> Generator[dict, None, None]:
        """Receive events from Nova Sonic. Yields dicts with type and data."""
        if not self._started:
            return
        while True:
            try:
                event = self._output_queue.get(timeout=300)
            except queue.Empty:
                yield {"type": "error", "content": "Voice session timed out"}
                break

            if event is None:
                break
            yield event

    def end(self) -> None:
        """End the voice session."""
        if self._ended:
            return
        self._ended = True
        try:
            self._send_event_sync(
                {
                    "event": {
                        "promptEnd": {
                            "promptName": PROMPT_NAME,
                        }
                    }
                }
            )
            self._send_event_sync({"event": {"sessionEnd": {}}})
        except Exception:
            logger.debug("Error sending session end", exc_info=True)

        if self._loop:
            self._loop.call_soon_threadsafe(self._loop.stop)
        if self._thread:
            self._thread.join(timeout=5)
