"""
WebSocket Handler Facade - Integrates all specialized handlers.

This is the main entry point for WebSocket handling, composing
specialized handlers for different responsibilities.
"""

from typing import Dict, Optional
from fastapi import WebSocket
import asyncio
import numpy as np
from loguru import logger

from ..service_context import ServiceContext
from ..chat_group import ChatGroupManager, handle_client_disconnect
from ..conversations.conversation_handler import (
    handle_conversation_trigger,
    handle_group_interrupt,
    handle_individual_interrupt,
)

from .connection_manager import ConnectionManager
from .message_router import MessageRouter
from .group_handler import GroupHandler
from .history_handler import HistoryHandler
from .audio_handler import AudioHandler
from .config_handler import ConfigHandler
from .memory_handler import MemoryHandler


class WebSocketHandler:
    """
    Facade for WebSocket handling.

    Composes specialized handlers for clean separation of concerns:
    - ConnectionManager: Connection lifecycle
    - MessageRouter: Message routing
    - GroupHandler: Group operations
    - HistoryHandler: Chat history
    - AudioHandler: Audio processing
    - ConfigHandler: Configuration
    - MemoryHandler: Memory management
    """

    def __init__(self, default_context_cache: ServiceContext):
        """Initialize the WebSocket handler with default context."""
        # Shared state
        self.client_connections: Dict[str, WebSocket] = {}
        self.client_contexts: Dict[str, ServiceContext] = {}
        self.chat_group_manager = ChatGroupManager()
        self.current_conversation_tasks: Dict[str, Optional[asyncio.Task]] = {}
        self.default_context_cache = default_context_cache
        self.received_data_buffers: Dict[str, np.ndarray] = {}

        # Initialize specialized handlers
        self._init_handlers()
        self._register_message_handlers()

    def _init_handlers(self) -> None:
        """Initialize all specialized handlers."""
        self.connection_manager = ConnectionManager(
            default_context_cache=self.default_context_cache,
            client_connections=self.client_connections,
            client_contexts=self.client_contexts,
            received_data_buffers=self.received_data_buffers,
            current_conversation_tasks=self.current_conversation_tasks,
            chat_group_manager=self.chat_group_manager,
        )

        self.message_router = MessageRouter()

        self.group_handler = GroupHandler(
            chat_group_manager=self.chat_group_manager,
            client_connections=self.client_connections,
            client_contexts=self.client_contexts,
        )

        self.history_handler = HistoryHandler(
            client_contexts=self.client_contexts,
        )

        self.audio_handler = AudioHandler(
            client_contexts=self.client_contexts,
            received_data_buffers=self.received_data_buffers,
            chat_group_manager=self.chat_group_manager,
        )

        self.config_handler = ConfigHandler(
            client_contexts=self.client_contexts,
            default_context_cache=self.default_context_cache,
        )

        self.memory_handler = MemoryHandler(
            client_contexts=self.client_contexts,
        )

    def _register_message_handlers(self) -> None:
        """Register all message handlers with the router."""
        self.message_router.register_handlers({
            # Group operations
            "add-client-to-group": self._handle_group_operation,
            "remove-client-from-group": self._handle_group_operation,
            "request-group-info": self._handle_group_info,
            # History operations
            "fetch-history-list": self.history_handler.handle_history_list_request,
            "fetch-and-set-history": self.history_handler.handle_fetch_history,
            "create-new-history": self.history_handler.handle_create_history,
            "delete-history": self.history_handler.handle_delete_history,
            # Audio operations
            "mic-audio-data": self.audio_handler.handle_audio_data,
            "raw-audio-data": self.audio_handler.handle_raw_audio_data,
            "audio-play-start": self._handle_audio_play_start,
            # Conversation triggers
            "mic-audio-end": self._handle_conversation_trigger,
            "text-input": self._handle_conversation_trigger,
            "ai-speak-signal": self._handle_conversation_trigger,
            "interrupt-signal": self._handle_interrupt,
            # Config operations
            "fetch-configs": self.config_handler.handle_fetch_configs,
            "switch-config": self.config_handler.handle_config_switch,
            "fetch-backgrounds": self.config_handler.handle_fetch_backgrounds,
            "request-init-config": self.config_handler.handle_init_config_request,
            "fetch-tts-config": self.config_handler.handle_fetch_tts_config,
            "fetch-live-config": self.config_handler.handle_fetch_live_config,
            # Memory operations
            "get_memories": self.memory_handler.handle_get_memories,
            "delete_memory": self.memory_handler.handle_delete_memory,
            "delete_all_memories": self.memory_handler.handle_delete_all_memories,
            # Utility
            "heartbeat": self._handle_heartbeat,
        })

    # ==========================================================================
    # Public API - Connection Lifecycle
    # ==========================================================================

    async def handle_new_connection(
        self, websocket: WebSocket, client_uid: str
    ) -> None:
        """Handle new WebSocket connection setup."""
        await self.connection_manager.handle_new_connection(
            websocket=websocket,
            client_uid=client_uid,
            send_group_update=self.send_group_update,
        )

    async def handle_websocket_communication(
        self, websocket: WebSocket, client_uid: str
    ) -> None:
        """Handle ongoing WebSocket communication."""
        await self.message_router.handle_websocket_communication(
            websocket=websocket,
            client_uid=client_uid,
        )

    async def handle_disconnect(self, client_uid: str) -> None:
        """Handle client disconnection."""
        await self.connection_manager.handle_disconnect(
            client_uid=client_uid,
            handle_group_interrupt=handle_group_interrupt,
            handle_client_disconnect=handle_client_disconnect,
            broadcast_to_group=self.broadcast_to_group,
            send_group_update=self.send_group_update,
        )

    # ==========================================================================
    # Public API - Group Operations
    # ==========================================================================

    async def send_group_update(self, websocket: WebSocket, client_uid: str) -> None:
        """Sends group information to a client."""
        await self.group_handler.send_group_update(websocket, client_uid)

    async def broadcast_to_group(
        self, group_members: list[str], message: dict, exclude_uid: str = None
    ) -> None:
        """Broadcasts a message to group members."""
        await self.group_handler.broadcast_to_group(
            group_members, message, exclude_uid
        )

    # ==========================================================================
    # Private - Message Handler Wrappers (for handlers needing extra context)
    # ==========================================================================

    async def _handle_group_operation(
        self, websocket: WebSocket, client_uid: str, data: dict
    ) -> None:
        """Handle group-related operations."""
        await self.group_handler.handle_group_operation(
            websocket, client_uid, data, self.send_group_update
        )

    async def _handle_group_info(
        self, websocket: WebSocket, client_uid: str, data: dict
    ) -> None:
        """Handle group info request."""
        await self.group_handler.handle_group_info(
            websocket, client_uid, data, self.send_group_update
        )

    async def _handle_audio_play_start(
        self, websocket: WebSocket, client_uid: str, data: dict
    ) -> None:
        """Handle audio playback start notification."""
        await self.audio_handler.handle_audio_play_start(
            websocket, client_uid, data, self.broadcast_to_group
        )

    async def _handle_conversation_trigger(
        self, websocket: WebSocket, client_uid: str, data: dict
    ) -> None:
        """Handle triggers that start a conversation."""
        await handle_conversation_trigger(
            msg_type=data.get("type", ""),
            data=data,
            client_uid=client_uid,
            context=self.client_contexts[client_uid],
            websocket=websocket,
            client_contexts=self.client_contexts,
            client_connections=self.client_connections,
            chat_group_manager=self.chat_group_manager,
            received_data_buffers=self.received_data_buffers,
            current_conversation_tasks=self.current_conversation_tasks,
            broadcast_to_group=self.broadcast_to_group,
        )

    async def _handle_interrupt(
        self, websocket: WebSocket, client_uid: str, data: dict
    ) -> None:
        """Handle conversation interruption."""
        heard_response = data.get("text", "")
        context = self.client_contexts[client_uid]
        group = self.chat_group_manager.get_client_group(client_uid)

        if group and len(group.members) > 1:
            await handle_group_interrupt(
                group_id=group.group_id,
                heard_response=heard_response,
                current_conversation_tasks=self.current_conversation_tasks,
                chat_group_manager=self.chat_group_manager,
                client_contexts=self.client_contexts,
                broadcast_to_group=self.broadcast_to_group,
            )
        else:
            await handle_individual_interrupt(
                client_uid=client_uid,
                current_conversation_tasks=self.current_conversation_tasks,
                context=context,
                heard_response=heard_response,
            )

    async def _handle_heartbeat(
        self, websocket: WebSocket, client_uid: str, data: dict
    ) -> None:
        """Handle heartbeat messages from clients."""
        try:
            await websocket.send_json({"type": "heartbeat-ack"})
        except Exception as e:
            logger.error(f"Error sending heartbeat acknowledgment: {e}")
