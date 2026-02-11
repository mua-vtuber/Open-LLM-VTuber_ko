"""Configuration operations handler for WebSocket communication."""

from typing import Dict, Any
from fastapi import WebSocket
import json
from loguru import logger

from ..service_context import ServiceContext
from ..config_manager.utils import scan_config_alts_directory, scan_bg_directory


class ConfigHandler:
    """Handles configuration-related WebSocket operations."""

    def __init__(
        self,
        client_contexts: Dict[str, ServiceContext],
        default_context_cache: ServiceContext,
    ):
        self.client_contexts = client_contexts
        self.default_context_cache = default_context_cache

    def _get_context(self, client_uid: str) -> ServiceContext:
        """Get context for a client, falling back to default."""
        return self.client_contexts.get(client_uid, self.default_context_cache)

    async def handle_fetch_configs(
        self, websocket: WebSocket, client_uid: str, data: dict
    ) -> None:
        """Handle fetching available configurations."""
        context = self.client_contexts[client_uid]
        config_files = scan_config_alts_directory(context.system_config.config_alts_dir)
        await websocket.send_text(
            json.dumps({"type": "config-files", "configs": config_files})
        )

    async def handle_config_switch(
        self, websocket: WebSocket, client_uid: str, data: dict
    ) -> None:
        """Handle switching to a different configuration."""
        config_file_name = data.get("file")
        if config_file_name:
            context = self.client_contexts[client_uid]
            await context.handle_config_switch(websocket, config_file_name)

    async def handle_fetch_backgrounds(
        self, websocket: WebSocket, client_uid: str, data: dict
    ) -> None:
        """Handle fetching available background images."""
        bg_files = scan_bg_directory()
        await websocket.send_text(
            json.dumps({"type": "background-files", "files": bg_files})
        )

    async def handle_init_config_request(
        self, websocket: WebSocket, client_uid: str, data: dict
    ) -> None:
        """Handle request for initialization configuration."""
        context = self._get_context(client_uid)

        await websocket.send_text(
            json.dumps(
                {
                    "type": "set-model-and-conf",
                    "model_info": context.live2d_model.model_info,
                    "conf_name": context.character_config.conf_name,
                    "conf_uid": context.character_config.conf_uid,
                    "client_uid": client_uid,
                }
            )
        )

    async def handle_fetch_tts_config(
        self, websocket: WebSocket, client_uid: str, data: dict
    ) -> None:
        """Handle fetching TTS configuration."""
        context = self._get_context(client_uid)

        try:
            tts_config = context.character_config.tts_config
            tts_model = tts_config.tts_model

            # Get the active TTS engine config
            active_config = getattr(tts_config, tts_model, None)
            active_config_dict = {}
            if active_config:
                active_config_dict = active_config.model_dump()

            await websocket.send_text(
                json.dumps(
                    {
                        "type": "tts-config",
                        "tts_model": tts_model,
                        "config": active_config_dict,
                    }
                )
            )
        except Exception as e:
            logger.error(f"Error fetching TTS config: {e}")
            await websocket.send_text(
                json.dumps({"type": "tts-config-error", "error": str(e)})
            )

    async def handle_fetch_live_config(
        self, websocket: WebSocket, client_uid: str, data: dict
    ) -> None:
        """Handle fetching live streaming configuration."""
        context = self._get_context(client_uid)

        try:
            live_config = context.config.live_config
            config_dict = live_config.model_dump()

            await websocket.send_text(
                json.dumps({"type": "live-config", "config": config_dict})
            )
        except Exception as e:
            logger.error(f"Error fetching live config: {e}")
            await websocket.send_text(
                json.dumps({"type": "live-config-error", "error": str(e)})
            )
