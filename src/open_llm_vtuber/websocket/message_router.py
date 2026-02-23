"""WebSocket message routing by type."""

from typing import Callable, Dict, Any, Optional, Awaitable
from fastapi import WebSocket, WebSocketDisconnect
import json
from loguru import logger

from ..message_handler import message_handler


MessageHandler = Callable[[str, Dict[str, Any]], Awaitable[None]]


class WebSocketMessageRouter:
    """메시지 타입별 핸들러 라우팅"""

    def __init__(self):
        self._handlers: Dict[str, MessageHandler] = {}
        self._default_handler: Optional[MessageHandler] = None

    def register(self, message_type: str, handler: MessageHandler) -> None:
        """메시지 타입에 핸들러 등록"""
        if message_type in self._handlers:
            logger.warning(f"Overwriting handler for message type: {message_type}")
        self._handlers[message_type] = handler
        logger.debug(f"Registered handler for message type: {message_type}")

    def register_many(self, handlers: Dict[str, MessageHandler]) -> None:
        """여러 핸들러를 한번에 등록"""
        for message_type, handler in handlers.items():
            self.register(message_type, handler)

    def set_default_handler(self, handler: MessageHandler) -> None:
        """알 수 없는 메시지 타입에 대한 기본 핸들러 설정"""
        self._default_handler = handler

    async def route(self, client_id: str, message: Dict[str, Any]) -> bool:
        """메시지를 적절한 핸들러로 라우팅"""
        message_type = message.get("type")

        if not message_type:
            logger.warning(f"Message from {client_id} has no type field")
            return False

        handler = self._handlers.get(message_type)

        if handler:
            try:
                await handler(client_id, message)
                return True
            except Exception as e:
                logger.error(f"Handler error for {message_type} from {client_id}: {e}")
                return False

        if self._default_handler:
            try:
                await self._default_handler(client_id, message)
                return True
            except Exception as e:
                logger.error(
                    f"Default handler error for {message_type} from {client_id}: {e}"
                )
                return False

        logger.warning(f"No handler for message type: {message_type} from {client_id}")
        return False

    def get_registered_types(self) -> list[str]:
        """등록된 모든 메시지 타입 목록"""
        return list(self._handlers.keys())

    def has_handler(self, message_type: str) -> bool:
        """특정 메시지 타입의 핸들러 존재 여부"""
        return message_type in self._handlers

    def unregister(self, message_type: str) -> bool:
        """메시지 타입의 핸들러 제거"""
        if message_type in self._handlers:
            del self._handlers[message_type]
            return True
        return False


class MessageRouter:
    """
    Routes WebSocket messages to appropriate handlers.

    Legacy class maintained for backward compatibility with existing handler.py.
    For new code, prefer using WebSocketMessageRouter.
    """

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
