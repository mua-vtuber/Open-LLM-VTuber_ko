"""Message routing handler for WebSocket communication."""

from typing import Dict, Callable
from fastapi import WebSocket, WebSocketDisconnect
import json
from loguru import logger

from ..message_handler import message_handler


class MessageRouter:
    """Routes WebSocket messages to appropriate handlers."""

    def __init__(self):
        self._message_handlers: Dict[str, Callable] = {}

    def register_handler(self, msg_type: str, handler: Callable) -> None:
        """Register a handler for a specific message type."""
        self._message_handlers[msg_type] = handler

    def register_handlers(self, handlers: Dict[str, Callable]) -> None:
        """Register multiple handlers at once."""
        self._message_handlers.update(handlers)

    async def handle_websocket_communication(
        self, websocket: WebSocket, client_uid: str
    ) -> None:
        """
        Handle ongoing WebSocket communication.

        Args:
            websocket: The WebSocket connection
            client_uid: Unique identifier for the client
        """
        try:
            while True:
                try:
                    client_request = await websocket.receive_json()
                    message_handler.handle_message(client_uid, client_request)
                    await self._route_message(websocket, client_uid, client_request)
                except WebSocketDisconnect:
                    raise
                except json.JSONDecodeError:
                    logger.error("Invalid JSON received")
                    continue
                except Exception as e:
                    logger.error(f"Error processing message: {e}")
                    await websocket.send_text(
                        json.dumps({"type": "error", "message": str(e)})
                    )
                    continue

        except WebSocketDisconnect:
            logger.info(f"Client {client_uid} disconnected")
            raise
        except Exception as e:
            logger.error(f"Fatal error in WebSocket communication: {e}")
            raise

    async def _route_message(
        self, websocket: WebSocket, client_uid: str, data: dict
    ) -> None:
        """
        Route incoming message to appropriate handler.

        Args:
            websocket: The WebSocket connection
            client_uid: Client identifier
            data: Message data
        """
        msg_type = data.get("type")
        if not msg_type:
            logger.warning("Message received without type")
            return

        handler = self._message_handlers.get(msg_type)
        if handler:
            await handler(websocket, client_uid, data)
        else:
            if msg_type != "frontend-playback-complete":
                logger.warning(f"Unknown message type: {msg_type}")
