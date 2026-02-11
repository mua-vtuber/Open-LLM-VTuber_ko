"""
Route modules for the Open-LLM-VTuber web server.

API 라우트 모듈 패키지.
기능별로 분리된 FastAPI 라우터를 제공합니다.

## 라우트 모듈

- **model_routes**: Live2D 모델 관리
    - `/live2d-models/info`: 모델 목록 조회
    - `/live2d-models/add-folder`: 외부 모델 폴더 추가
    - `/live2d-models/remove-folder`: 외부 모델 폴더 제거

- **queue_routes**: 메시지 대기열 상태
    - `/api/queue/status`: 큐 상태 조회
    - `/api/queue/history`: 메트릭 히스토리
    - `/api/queue/priority-rules`: 우선순위 규칙 관리

- **live_config_routes**: 라이브 설정 관리
    - `/api/live-config`: 라이브 스트리밍 설정

- **live_routes**: 라이브 스트리밍 연동
    - `/chzzk/auth`: Chzzk OAuth 인증
    - `/chzzk/callback`: OAuth 콜백

- **language_routes**: 다국어 지원
    - `/api/languages`: 사용 가능한 언어 목록

- **media_routes**: 오디오/미디어 처리
    - `/asr`: 음성 인식
    - `/tts-ws`: TTS WebSocket

- **websocket_routes**: WebSocket 연결
    - `/client-ws`: 클라이언트 WebSocket
    - `/proxy-ws`: 프록시 WebSocket

## OpenAPI 태그

모든 라우트는 OpenAPI 문서화를 위해 태그가 지정되어 있습니다.
Swagger UI (`/docs`) 및 ReDoc (`/redoc`)에서 확인할 수 있습니다.
"""

from fastapi import APIRouter

from ..service_context import ServiceContext
from ..websocket.handler import WebSocketHandler
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
