"""Audio data processing handler for WebSocket communication."""

from typing import Dict, Callable
from fastapi import WebSocket
import json
import numpy as np

from ..service_context import ServiceContext
from ..chat_group import ChatGroupManager
from ..utils.stream_audio import prepare_audio_payload


class AudioHandler:
    """Handles audio-related WebSocket operations."""

    def __init__(
        self,
        client_contexts: Dict[str, ServiceContext],
        received_data_buffers: Dict[str, np.ndarray],
        chat_group_manager: ChatGroupManager,
    ):
        self.client_contexts = client_contexts
        self.received_data_buffers = received_data_buffers
        self.chat_group_manager = chat_group_manager

    async def handle_audio_data(
        self, websocket: WebSocket, client_uid: str, data: dict
    ) -> None:
        """Handle incoming audio data."""
        audio_data = data.get("audio", [])
        if audio_data:
            self.received_data_buffers[client_uid] = np.append(
                self.received_data_buffers[client_uid],
                np.array(audio_data, dtype=np.float32),
            )

    async def handle_raw_audio_data(
        self, websocket: WebSocket, client_uid: str, data: dict
    ) -> None:
        """Handle incoming raw audio data for VAD processing."""
        context = self.client_contexts[client_uid]
        chunk = data.get("audio", [])
        if chunk:
            for audio_bytes in context.vad_engine.detect_speech(chunk):
                if audio_bytes == b"<|PAUSE|>":
                    await websocket.send_text(
                        json.dumps({"type": "control", "text": "interrupt"})
                    )
                elif audio_bytes == b"<|RESUME|>":
                    pass
                elif len(audio_bytes) > 1024:
                    # Detected audio activity (voice)
                    self.received_data_buffers[client_uid] = np.append(
                        self.received_data_buffers[client_uid],
                        np.frombuffer(audio_bytes, dtype=np.int16).astype(np.float32),
                    )
                    await websocket.send_text(
                        json.dumps({"type": "control", "text": "mic-audio-end"})
                    )

    async def handle_audio_play_start(
        self,
        websocket: WebSocket,
        client_uid: str,
        data: dict,
        broadcast_to_group: Callable,
    ) -> None:
        """Handle audio playback start notification."""
        group_members = self.chat_group_manager.get_group_members(client_uid)
        if len(group_members) > 1:
            display_text = data.get("display_text")
            if display_text:
                silent_payload = prepare_audio_payload(
                    audio_path=None,
                    display_text=display_text,
                    actions=None,
                    forwarded=True,
                )
                await broadcast_to_group(
                    group_members, silent_payload, exclude_uid=client_uid
                )
