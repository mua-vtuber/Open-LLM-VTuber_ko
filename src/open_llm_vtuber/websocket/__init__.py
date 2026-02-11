"""
WebSocket module - Separated handlers for WebSocket communication

This module provides a clean separation of concerns for WebSocket handling:
- WebSocketConnectionManager: Connection lifecycle management (connect/disconnect/broadcast)
- ConnectionManager: Legacy connection manager with ServiceContext (for handler.py compatibility)
- MessageRouter: Message routing to appropriate handlers (legacy)
- WebSocketMessageRouter: Type-based message routing with handler registration
- GroupHandler: Group/session operations
- HistoryHandler: Chat history management
- AudioHandler: Audio data processing
- ConfigHandler: Configuration operations
- MemoryHandler: Memory management operations
- WebSocketHandler: Facade that integrates all handlers
- ClientStateManager: Client state and context management
"""

from .connection_manager import WebSocketConnectionManager, ConnectionManager
from .message_router import MessageRouter, WebSocketMessageRouter
from .group_handler import GroupHandler
from .history_handler import HistoryHandler
from .audio_handler import AudioHandler
from .config_handler import ConfigHandler
from .memory_handler import MemoryHandler
from .handler import WebSocketHandler
from .state_manager import ClientStateManager

__all__ = [
    "WebSocketConnectionManager",
    "ConnectionManager",
    "MessageRouter",
    "WebSocketMessageRouter",
    "GroupHandler",
    "HistoryHandler",
    "AudioHandler",
    "ConfigHandler",
    "MemoryHandler",
    "WebSocketHandler",
    "ClientStateManager",
]
