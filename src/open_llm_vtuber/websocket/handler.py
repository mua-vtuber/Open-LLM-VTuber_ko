"""
WebSocket Handler Facade - Integrates all specialized handlers.

This is the main entry point for WebSocket handling, composing
specialized handlers for different responsibilities.
"""

from typing import Dict, Optional, Any
from fastapi import WebSocket, WebSocketDisconnect
import asyncio
import json
import numpy as np
from loguru import logger

from ..service_context import ServiceContext
from ..chat_group import ChatGroupManager, handle_client_disconnect
from ..conversations.conversation_handler import (
    handle_conversation_trigger,
    handle_group_interrupt,
    handle_individual_interrupt,
)
from ..message_handler import message_handler
from ..obs import OBSService, SceneLayout

from .connection_manager import ConnectionManager
from .message_router import MessageRouter
from .group_handler import GroupHandler
from .history_handler import HistoryHandler
from .audio_handler import AudioHandler
from .config_handler import ConfigHandler
from .memory_handler import MemoryHandler
from ..input_queue import InputQueueManager
from ..queue_config import QueueConfig


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
    - InputQueueManager: Message queuing
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

        # Initialize OBS Service
        self._obs_service: Optional[OBSService] = None

        # Initialize specialized handlers
        self._init_handlers()
        self._register_message_handlers()

        # Initialize Queue Manager
        self._queue_config = QueueConfig()
        self._input_queue_manager = InputQueueManager(
            config=self._queue_config, message_handler=self._process_queued_message
        )
        logger.info("WebSocketHandler initialized with InputQueueManager")

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
        self.message_router.register_handlers(
            {
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
                # Priority rules operations
                "fetch-priority-rules": self._handle_fetch_priority_rules,
                "update-priority-rules": self._handle_update_priority_rules,
                # OBS operations
                "obs-connect": self._handle_obs_connect,
                "obs-disconnect": self._handle_obs_disconnect,
                "obs-get-layout": self._handle_obs_get_layout,
                # Utility
                "heartbeat": self._handle_heartbeat,
            }
        )

    # ==========================================================================
    # Public API - Connection Lifecycle
    # ==========================================================================

    async def handle_new_connection(
        self, websocket: WebSocket, client_uid: str
    ) -> None:
        """Handle new WebSocket connection setup."""
        # Start queue manager if not running
        if not self._input_queue_manager.is_running():
            await self._input_queue_manager.start()
            logger.info("InputQueueManager started")

        await self.connection_manager.handle_new_connection(
            websocket=websocket,
            client_uid=client_uid,
            send_group_update=self.send_group_update,
        )

    async def handle_websocket_communication(
        self, websocket: WebSocket, client_uid: str
    ) -> None:
        """Handle ongoing WebSocket communication with queue support."""
        try:
            while True:
                try:
                    data = await websocket.receive_json()

                    # Log message reception (optional, using existing handler)
                    message_handler.handle_message(client_uid, data)

                    # Add client_uid to message for processing
                    data["client_uid"] = client_uid

                    # Enqueue message
                    success = await self._input_queue_manager.enqueue(data)

                    if not success:
                        logger.warning(
                            f"Failed to enqueue message (client: {client_uid}, "
                            f"type: {data.get('type', 'unknown')})"
                        )
                    else:
                        logger.debug(
                            f"Message enqueued (client: {client_uid}, "
                            f"type: {data.get('type', 'unknown')})"
                        )

                except WebSocketDisconnect:
                    raise
                except json.JSONDecodeError:
                    logger.error("Invalid JSON received")
                    continue
                except Exception as e:
                    logger.error(f"Error processing message: {e}")
                    await websocket.send_text(
                        json.dumps(
                            {"type": "error", "message": "An internal error occurred"}
                        )
                    )
                    continue

        except WebSocketDisconnect:
            logger.info(f"Client {client_uid} disconnected (WebSocket)")
            raise
        except Exception as e:
            logger.error(f"Fatal error in WebSocket communication: {e}")
            raise

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
    # Private - Queue Processing
    # ==========================================================================

    async def _process_queued_message(self, message: Dict) -> None:
        """
        Process a message popped from the queue.

        Args:
            message: The message dictionary containing 'client_uid' and message data.
        """
        client_uid = message.get("client_uid")
        if not client_uid:
            logger.error("Message missing client_uid")
            return

        # Find websocket connection
        websocket = self.client_connections.get(client_uid)
        if not websocket:
            logger.warning(
                f"Connection not found for client {client_uid}. "
                f"Message type: {message.get('type', 'unknown')}"
            )
            return

        # Route the message
        try:
            await self.message_router.route_message(
                websocket=websocket,
                client_uid=client_uid,
                data=message,
                message_handlers=self.message_router.handlers,  # Using registered handlers
            )
        except Exception as e:
            logger.error(
                f"Error processing queued message (client: {client_uid}, "
                f"type: {message.get('type', 'unknown')}): {e}",
                exc_info=True,
            )

    def get_queue_status(self) -> Dict[str, Any]:
        """
        Get current status of the input queue.

        Returns:
            Dict[str, Any]: Queue status metrics.
        """
        status = self._input_queue_manager.get_status()

        return {
            "pending": status.get("queue_size", 0),
            "processing": 1 if status.get("current_message") else 0,
            "max_size": status.get("queue_max_size", 0),
            "total_received": status.get("total_received", 0),
            "total_processed": status.get("total_processed", 0),
            "total_dropped": status.get("total_dropped", 0),
            "running": status.get("running", False),
            "avg_processing_time": status.get("avg_processing_time", 0.0),
            "processing_rate": status.get("processing_rate", 0.0),
        }

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
        await self.group_handler.broadcast_to_group(group_members, message, exclude_uid)

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

    async def _handle_fetch_priority_rules(
        self, websocket: WebSocket, client_uid: str, data: dict
    ) -> None:
        """Handle request to fetch priority rules."""
        try:
            await websocket.send_json(
                {
                    "type": "priority-rules-data",
                    "priority_rules": self._queue_config.priority_rules.to_dict(),
                }
            )
        except Exception as e:
            logger.error(f"Error sending priority rules: {e}")
            await websocket.send_json(
                {"type": "priority-rules-error", "error": "An internal error occurred"}
            )

    async def _handle_update_priority_rules(
        self, websocket: WebSocket, client_uid: str, data: dict
    ) -> None:
        """Handle request to update priority rules."""
        try:
            priority_rules_data = data.get("priority_rules", {})

            # Update the priority rules
            success = self._queue_config.priority_rules.update_from_dict(
                priority_rules_data
            )

            if success:
                logger.info(f"Priority rules updated by client {client_uid}")
                # Broadcast the update to all clients
                await self.broadcast_priority_rules_update()
            else:
                await websocket.send_json(
                    {
                        "type": "priority-rules-update-error",
                        "error": "Invalid priority rules data",
                    }
                )

        except Exception as e:
            logger.error(f"Error updating priority rules: {e}")
            await websocket.send_json(
                {"type": "priority-rules-update-error", "error": "Operation failed"}
            )

    # ==========================================================================
    # Public API - Priority Rules
    # ==========================================================================

    def get_priority_rules(self) -> Dict[str, Any]:
        """
        Return priority rules as dictionary.

        Returns:
            Dict[str, Any]: Priority rules configuration.
        """
        return self._queue_config.priority_rules.to_dict()

    def get_priority_rules_instance(self):
        """
        Return PriorityRules instance for direct modification.

        Returns:
            PriorityRules: The priority rules instance.
        """
        return self._queue_config.priority_rules

    async def broadcast_priority_rules_update(self) -> None:
        """
        Broadcast priority rules update to all connected clients.

        Sends the current priority rules configuration to all connected
        WebSocket clients for synchronization.
        """
        message = {
            "type": "priority-rules-updated",
            "priority_rules": self._queue_config.priority_rules.to_dict(),
        }
        for client_uid, websocket in self.client_connections.items():
            try:
                await websocket.send_json(message)
            except Exception as e:
                logger.warning(
                    f"Failed to send priority rules update to {client_uid}: {e}"
                )

    def get_queue_metric_history(self, minutes: int = 5) -> list:
        """
        Get queue metric history for the specified period.

        Args:
            minutes: Number of minutes of history to retrieve.

        Returns:
            List[Dict[str, Any]]: Queue metric history.
        """
        return self._input_queue_manager.get_metric_history(minutes)

    # ==========================================================================
    # Private - OBS Integration Handlers
    # ==========================================================================

    async def _handle_obs_connect(
        self, websocket: WebSocket, client_uid: str, data: dict
    ) -> None:
        """Connect to OBS WebSocket server."""
        try:
            config = data.get("config", {})
            host = config.get("host", "localhost")
            port = config.get("port", 4455)
            password = config.get("password", "")
            poll_interval = config.get("layout_poll_interval", 2)

            if self._obs_service:
                self._obs_service.disconnect()

            self._obs_service = OBSService(host=host, port=port, password=password)
            connected = await asyncio.to_thread(self._obs_service.connect)

            if connected:
                # Start layout polling - broadcast to all connected clients
                await self._obs_service.start_layout_polling(
                    callback=self._broadcast_obs_layout,
                    interval=poll_interval,
                )

                await websocket.send_json(
                    {
                        "type": "obs-status",
                        "connected": True,
                        "message": "Connected to OBS",
                    }
                )

                # Send initial layout
                layout = await asyncio.to_thread(self._obs_service.get_layout)
                if layout:
                    await self._broadcast_obs_layout(layout)
            else:
                await websocket.send_json(
                    {
                        "type": "obs-status",
                        "connected": False,
                        "message": "Failed to connect to OBS",
                    }
                )
        except Exception as e:
            logger.error(f"OBS connect error: {e}")
            await websocket.send_json(
                {
                    "type": "obs-status",
                    "connected": False,
                    "message": "Failed to connect to OBS",
                }
            )

    async def _handle_obs_disconnect(
        self, websocket: WebSocket, client_uid: str, data: dict
    ) -> None:
        """Disconnect from OBS WebSocket server."""
        if self._obs_service:
            self._obs_service.stop_layout_polling()
            self._obs_service.disconnect()
            self._obs_service = None

        await websocket.send_json(
            {
                "type": "obs-status",
                "connected": False,
                "message": "Disconnected from OBS",
            }
        )

    async def _handle_obs_get_layout(
        self, websocket: WebSocket, client_uid: str, data: dict
    ) -> None:
        """Get current OBS layout on demand."""
        if not self._obs_service or not self._obs_service.is_connected:
            await websocket.send_json(
                {
                    "type": "obs-status",
                    "connected": False,
                    "message": "OBS not connected",
                }
            )
            return

        layout = await asyncio.to_thread(self._obs_service.get_layout)
        if layout:
            await websocket.send_json(
                {
                    "type": "obs-layout",
                    "regions": [
                        {
                            "name": r.name,
                            "x": r.x,
                            "y": r.y,
                            "width": r.width,
                            "height": r.height,
                        }
                        for r in layout.regions
                    ],
                    "canvasWidth": layout.canvas_width,
                    "canvasHeight": layout.canvas_height,
                }
            )

    async def _broadcast_obs_layout(self, layout: SceneLayout) -> None:
        """Broadcast OBS layout update to all connected clients."""
        message = {
            "type": "obs-layout",
            "regions": [
                {
                    "name": r.name,
                    "x": r.x,
                    "y": r.y,
                    "width": r.width,
                    "height": r.height,
                }
                for r in layout.regions
            ],
            "canvasWidth": layout.canvas_width,
            "canvasHeight": layout.canvas_height,
        }

        for uid, ws in self.client_connections.items():
            try:
                await ws.send_json(message)
            except Exception:
                pass  # Client may have disconnected
