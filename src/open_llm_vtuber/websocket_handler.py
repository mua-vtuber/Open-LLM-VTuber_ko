"""
WebSocket Handler - Backward compatibility re-export.

This module re-exports from the new websocket package for backward compatibility.
The actual implementation is now in the websocket/ package with clean separation of concerns.

New structure:
- websocket/connection_manager.py - Connection lifecycle management
- websocket/message_router.py - Message routing
- websocket/group_handler.py - Group operations
- websocket/history_handler.py - Chat history management
- websocket/audio_handler.py - Audio data processing
- websocket/config_handler.py - Configuration operations
- websocket/memory_handler.py - Memory management
- websocket/handler.py - Facade integrating all handlers
"""

# Re-export for backward compatibility
from .websocket import WebSocketHandler

__all__ = ["WebSocketHandler"]
