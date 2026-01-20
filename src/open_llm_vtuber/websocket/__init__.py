"""
WebSocket module - Separated handlers for WebSocket communication

This module provides a clean separation of concerns for WebSocket handling:
- ConnectionManager: Connection lifecycle management
- MessageRouter: Message routing to appropriate handlers
- GroupHandler: Group/session operations
- HistoryHandler: Chat history management
- AudioHandler: Audio data processing
- ConfigHandler: Configuration operations
- MemoryHandler: Memory management operations
- WebSocketHandler: Facade that integrates all handlers
"""

from .connection_manager import ConnectionManager
from .message_router import MessageRouter
from .group_handler import GroupHandler
from .history_handler import HistoryHandler
from .audio_handler import AudioHandler
from .config_handler import ConfigHandler
from .memory_handler import MemoryHandler
from .handler import WebSocketHandler

__all__ = [
    "ConnectionManager",
    "MessageRouter",
    "GroupHandler",
    "HistoryHandler",
    "AudioHandler",
    "ConfigHandler",
    "MemoryHandler",
    "WebSocketHandler",
]
