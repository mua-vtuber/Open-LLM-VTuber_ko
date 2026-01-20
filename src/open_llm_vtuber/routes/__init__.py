"""
Route modules for the Open-LLM-VTuber web server.

This package organizes API routes by functionality:
- redirect_routes: Web tool redirects
- language_routes: I18n language API
- live_routes: Live streaming (Chzzk OAuth)
- model_routes: Live2D models info
- media_routes: ASR/TTS endpoints
- websocket_routes: WebSocket connections
"""

from fastapi import APIRouter

from ..service_context import ServiceContext
from .redirect_routes import init_redirect_routes
from .language_routes import init_language_routes
from .live_routes import init_live_routes
from .model_routes import init_model_routes
from .media_routes import init_media_routes
from .websocket_routes import init_client_ws_route, init_proxy_route


def init_webtool_routes(default_context_cache: ServiceContext) -> APIRouter:
    """
    Create and return combined API routes for handling web tool interactions.

    Aggregates all sub-routers into a single router for backward compatibility.

    Args:
        default_context_cache: Default service context cache for new sessions.

    Returns:
        APIRouter: Configured router with all endpoints.
    """
    router = APIRouter()

    # Include all sub-routers
    router.include_router(init_redirect_routes())
    router.include_router(init_language_routes())
    router.include_router(init_live_routes(default_context_cache))
    router.include_router(init_model_routes())
    router.include_router(init_media_routes(default_context_cache))

    return router


__all__ = [
    "init_webtool_routes",
    "init_client_ws_route",
    "init_proxy_route",
]
