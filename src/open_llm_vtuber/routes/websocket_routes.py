"""WebSocket connection routes.

WebSocket 연결 관리를 위한 API 라우트.
클라이언트 WebSocket 연결 및 프록시 연결을 처리합니다.
"""

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

    @router.websocket(
        "/client-ws",
        name="client_websocket",
    )
    async def websocket_endpoint(websocket: WebSocket):
        """
        클라이언트 WebSocket 연결 엔드포인트.

        AI VTuber와의 실시간 양방향 통신을 제공합니다.
        음성 데이터 전송, 텍스트 메시지, Live2D 제어 등을 처리합니다.

        ## 지원 메시지 타입
        - `audio-data`: 음성 데이터 전송
        - `text-input`: 텍스트 입력
        - `interrupt`: 현재 응답 중단
        - `config-update`: 설정 업데이트
        - `emotion-control`: 표정 제어

        Tags:
            websocket: WebSocket 연결
        """
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

    @router.websocket(
        "/proxy-ws",
        name="proxy_websocket",
    )
    async def proxy_endpoint(websocket: WebSocket):
        """
        프록시 WebSocket 연결 엔드포인트.

        외부 클라이언트를 위한 프록시 WebSocket 연결을 제공합니다.
        실제 서버로의 메시지 중계 역할을 수행합니다.

        Note:
            프록시 모드가 활성화된 경우에만 사용 가능합니다.
            (`system_config.enable_proxy: true`)

        Tags:
            websocket: WebSocket 연결
        """
        try:
            await proxy_handler.handle_client_connection(websocket)
        except Exception as e:
            logger.error(f"Error in proxy connection: {e}")
            raise

    return router
