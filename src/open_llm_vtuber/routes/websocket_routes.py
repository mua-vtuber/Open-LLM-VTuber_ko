"""WebSocket connection routes."""

from uuid import uuid4

from fastapi import APIRouter, WebSocket
from starlette.websockets import WebSocketDisconnect
from loguru import logger

from ..service_context import ServiceContext
from ..websocket_handler import WebSocketHandler
from ..proxy_handler import ProxyHandler


# 공유 WebSocketHandler 인스턴스
_ws_handler = None


def get_ws_handler() -> WebSocketHandler:
    """
    Get the shared WebSocketHandler instance.

    Returns:
        WebSocketHandler: Shared handler instance.
    """
    return _ws_handler


def init_client_ws_route(default_context_cache: ServiceContext) -> APIRouter:
    """
    Create and return API routes for handling the `/client-ws` WebSocket connections.

    Args:
        default_context_cache: Default service context cache for new sessions.

    Returns:
        APIRouter: Configured router with WebSocket endpoint.
    """
    global _ws_handler
    
    router = APIRouter()
    
    # WebSocketHandler 인스턴스가 없으면 생성
    if _ws_handler is None:
        _ws_handler = WebSocketHandler(default_context_cache)

    @router.websocket("/client-ws")
    async def websocket_endpoint(websocket: WebSocket):
        """WebSocket endpoint for client connections."""
        await websocket.accept()
        client_uid = str(uuid4())

        try:
            await _ws_handler.handle_new_connection(websocket, client_uid)
            await _ws_handler.handle_websocket_communication(websocket, client_uid)
        except WebSocketDisconnect:
            await _ws_handler.handle_disconnect(client_uid)
        except Exception as e:
            logger.error(f"Error in WebSocket connection: {e}")
            await _ws_handler.handle_disconnect(client_uid)
            raise

    return router


def init_proxy_route(server_url: str) -> APIRouter:
    """
    Create and return API routes for handling proxy connections.

    Args:
        server_url: The WebSocket URL of the actual server.

    Returns:
        APIRouter: Configured router with proxy WebSocket endpoint.
    """
    router = APIRouter()
    proxy_handler = ProxyHandler(server_url)

    @router.websocket("/proxy-ws")
    async def proxy_endpoint(websocket: WebSocket):
        """WebSocket endpoint for proxy connections."""
        try:
            await proxy_handler.handle_client_connection(websocket)
        except Exception as e:
            logger.error(f"Error in proxy connection: {e}")
            raise

    return router
