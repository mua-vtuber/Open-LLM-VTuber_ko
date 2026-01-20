"""Connection lifecycle management for WebSocket connections."""

from typing import Dict, Callable, Optional
from fastapi import WebSocket
import asyncio
import json
import numpy as np
from loguru import logger

from ..service_context import ServiceContext
from ..chat_group import ChatGroupManager
from ..message_handler import message_handler


class ConnectionManager:
    """Manages WebSocket connection lifecycle."""

    def __init__(
        self,
        default_context_cache: ServiceContext,
        client_connections: Dict[str, WebSocket],
        client_contexts: Dict[str, ServiceContext],
        received_data_buffers: Dict[str, np.ndarray],
        current_conversation_tasks: Dict[str, Optional[asyncio.Task]],
        chat_group_manager: ChatGroupManager,
    ):
        self.default_context_cache = default_context_cache
        self.client_connections = client_connections
        self.client_contexts = client_contexts
        self.received_data_buffers = received_data_buffers
        self.current_conversation_tasks = current_conversation_tasks
        self.chat_group_manager = chat_group_manager

    async def handle_new_connection(
        self,
        websocket: WebSocket,
        client_uid: str,
        send_group_update: Callable,
    ) -> None:
        """
        Handle new WebSocket connection setup.

        Args:
            websocket: The WebSocket connection
            client_uid: Unique identifier for the client
            send_group_update: Callback to send group updates

        Raises:
            Exception: If initialization fails
        """
        try:
            session_service_context = await self._init_service_context(
                websocket.send_text, client_uid
            )

            await self._store_client_data(
                websocket, client_uid, session_service_context, send_group_update
            )

            await self._send_initial_messages(
                websocket, client_uid, session_service_context, send_group_update
            )

            logger.info(f"Connection established for client {client_uid}")

        except Exception as e:
            logger.error(
                f"Failed to initialize connection for client {client_uid}: {e}"
            )
            await self.cleanup_failed_connection(client_uid)
            raise

    async def _init_service_context(
        self, send_text: Callable, client_uid: str
    ) -> ServiceContext:
        """Initialize service context for a new session by cloning the default context."""
        session_service_context = ServiceContext()
        await session_service_context.load_cache(
            config=self.default_context_cache.config.model_copy(deep=True),
            system_config=self.default_context_cache.system_config.model_copy(
                deep=True
            ),
            character_config=self.default_context_cache.character_config.model_copy(
                deep=True
            ),
            live2d_model=self.default_context_cache.live2d_model,
            asr_engine=self.default_context_cache.asr_engine,
            tts_engine=self.default_context_cache.tts_engine,
            vad_engine=self.default_context_cache.vad_engine,
            agent_engine=self.default_context_cache.agent_engine,
            translate_engine=self.default_context_cache.translate_engine,
            mcp_server_registery=self.default_context_cache.mcp_server_registery,
            tool_adapter=self.default_context_cache.tool_adapter,
            send_text=send_text,
            client_uid=client_uid,
        )
        return session_service_context

    async def _store_client_data(
        self,
        websocket: WebSocket,
        client_uid: str,
        session_service_context: ServiceContext,
        send_group_update: Callable,
    ) -> None:
        """Store client data and initialize group status."""
        self.client_connections[client_uid] = websocket
        self.client_contexts[client_uid] = session_service_context
        self.received_data_buffers[client_uid] = np.array([])

        self.chat_group_manager.client_group_map[client_uid] = ""
        await send_group_update(websocket, client_uid)

    async def _send_initial_messages(
        self,
        websocket: WebSocket,
        client_uid: str,
        session_service_context: ServiceContext,
        send_group_update: Callable,
    ) -> None:
        """Send initial connection messages to the client."""
        await websocket.send_text(
            json.dumps({"type": "full-text", "text": "Connection established"})
        )

        await websocket.send_text(
            json.dumps(
                {
                    "type": "set-model-and-conf",
                    "model_info": session_service_context.live2d_model.model_info,
                    "conf_name": session_service_context.character_config.conf_name,
                    "conf_uid": session_service_context.character_config.conf_uid,
                    "client_uid": client_uid,
                }
            )
        )

        # Send initial group status
        await send_group_update(websocket, client_uid)

        # Start microphone
        await websocket.send_text(json.dumps({"type": "control", "text": "start-mic"}))

    async def handle_disconnect(
        self,
        client_uid: str,
        handle_group_interrupt: Callable,
        handle_client_disconnect: Callable,
        broadcast_to_group: Callable,
        send_group_update: Callable,
    ) -> None:
        """Handle client disconnection."""
        group = self.chat_group_manager.get_client_group(client_uid)
        if group:
            await handle_group_interrupt(
                group_id=group.group_id,
                heard_response="",
                current_conversation_tasks=self.current_conversation_tasks,
                chat_group_manager=self.chat_group_manager,
                client_contexts=self.client_contexts,
                broadcast_to_group=broadcast_to_group,
            )

        await handle_client_disconnect(
            client_uid=client_uid,
            chat_group_manager=self.chat_group_manager,
            client_connections=self.client_connections,
            send_group_update=send_group_update,
        )

        # Call context close to clean up resources (e.g., MCPClient)
        context = self.client_contexts.get(client_uid)
        if context:
            await context.close()

        # Clean up other client data
        self.client_connections.pop(client_uid, None)
        self.client_contexts.pop(client_uid, None)
        self.received_data_buffers.pop(client_uid, None)
        if client_uid in self.current_conversation_tasks:
            task = self.current_conversation_tasks[client_uid]
            if task and not task.done():
                task.cancel()
            self.current_conversation_tasks.pop(client_uid, None)

        logger.info(f"Client {client_uid} disconnected")
        message_handler.cleanup_client(client_uid)

    async def cleanup_failed_connection(self, client_uid: str) -> None:
        """Clean up failed connection data."""
        self.client_connections.pop(client_uid, None)
        self.client_contexts.pop(client_uid, None)
        self.received_data_buffers.pop(client_uid, None)
        self.chat_group_manager.client_group_map.pop(client_uid, None)

        if client_uid in self.current_conversation_tasks:
            task = self.current_conversation_tasks[client_uid]
            if task and not task.done():
                task.cancel()
            self.current_conversation_tasks.pop(client_uid, None)

        message_handler.cleanup_client(client_uid)
