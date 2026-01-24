"""
Route modules for the Open-LLM-VTuber web server.

This package organizes API routes by functionality:
- redirect_routes: Web tool redirects
- language_routes: I18n language API
- live_routes: Live streaming (Chzzk OAuth)
- model_routes: Live2D models info
- media_routes: ASR/TTS endpoints
- websocket_routes: WebSocket connections
- queue_routes: Queue status API
"""

from fastapi import APIRouter

from ..service_context import ServiceContext
from ..websocket_handler import WebSocketHandler
from .queue_routes import init_queue_routes
from .live_config_routes import init_live_config_routes
from .websocket_routes import init_client_ws_route, init_proxy_route
from .model_routes import init_model_routes


# 공유 WebSocketHandler 인스턴스
_ws_handler = None


def init_webtool_routes(default_context_cache: ServiceContext) -> APIRouter:
    """
    Create and return combined API routes for handling web tool interactions.

    Aggregates all sub-routers into a single router for backward compatibility.

    Args:
        default_context_cache: Default service context cache for new sessions.

    Returns:
        APIRouter: Configured router with all endpoints.
    """
    global _ws_handler

    # WebSocketHandler 인스턴스가 없으면 생성
    if _ws_handler is None:
        _ws_handler = WebSocketHandler(default_context_cache)

    router = APIRouter()

    # Include queue routes with shared ws_handler
    router.include_router(init_queue_routes(_ws_handler))

    # Include live config routes
    router.include_router(init_live_config_routes(default_context_cache))

    return router


def get_ws_handler() -> WebSocketHandler:
    """
    Get the shared WebSocketHandler instance.

    Returns:
        WebSocketHandler: Shared handler instance.
    """
    return _ws_handler


__all__ = [
    "init_webtool_routes",
    "init_queue_routes",
    "init_live_config_routes",
    "init_client_ws_route",
    "init_proxy_route",
    "init_model_routes",
    "get_ws_handler",
]
