"""WebSocket connection lifecycle management."""
from typing import Dict, Optional, Set, Callable
from fastapi import WebSocket
import asyncio
import json
import numpy as np
from loguru import logger

from ..service_context import ServiceContext
from ..chat_group import ChatGroupManager
from ..message_handler import message_handler


class WebSocketConnectionManager:
    """WebSocket 연결 수명 주기 관리자"""

    def __init__(self):
        self.active_connections: Dict[str, WebSocket] = {}
        self._connection_groups: Dict[str, Set[str]] = {}  # group_id -> client_ids

    async def connect(self, client_id: str, websocket: WebSocket) -> bool:
        """새 클라이언트 연결 승인"""
        try:
            await websocket.accept()
            self.active_connections[client_id] = websocket
            logger.info(f"Client {client_id} connected. Total connections: {len(self.active_connections)}")
            return True
        except Exception as e:
            logger.error(f"Failed to accept connection for {client_id}: {e}")
            return False

    async def disconnect(self, client_id: str) -> None:
        """클라이언트 연결 해제"""
        websocket = self.active_connections.pop(client_id, None)
        if websocket:
            try:
                await websocket.close()
            except Exception:
                pass  # 이미 닫힌 연결
            logger.info(f"Client {client_id} disconnected. Total connections: {len(self.active_connections)}")

    def get_connection(self, client_id: str) -> Optional[WebSocket]:
        """클라이언트 연결 객체 조회"""
        return self.active_connections.get(client_id)

    def is_connected(self, client_id: str) -> bool:
        """클라이언트 연결 여부 확인"""
        return client_id in self.active_connections

    async def send_json(self, client_id: str, data: dict) -> bool:
        """특정 클라이언트에게 JSON 메시지 전송"""
        websocket = self.active_connections.get(client_id)
        if not websocket:
            return False
        try:
            await websocket.send_json(data)
            return True
        except Exception as e:
            logger.warning(f"Failed to send message to {client_id}: {e}")
            return False

    async def broadcast(self, data: dict, exclude: Optional[Set[str]] = None) -> int:
        """모든 클라이언트에게 메시지 브로드캐스트"""
        exclude = exclude or set()
        sent_count = 0

        for client_id, websocket in list(self.active_connections.items()):
            if client_id in exclude:
                continue
            try:
                await websocket.send_json(data)
                sent_count += 1
            except Exception as e:
                logger.warning(f"Failed to broadcast to {client_id}: {e}")

        return sent_count

    async def broadcast_to_group(self, group_id: str, data: dict, exclude: Optional[Set[str]] = None) -> int:
        """특정 그룹 멤버들에게 메시지 전송"""
        exclude = exclude or set()
        client_ids = self._connection_groups.get(group_id, set())
        sent_count = 0

        for client_id in client_ids:
            if client_id in exclude:
                continue
            if await self.send_json(client_id, data):
                sent_count += 1

        return sent_count

    def add_to_group(self, client_id: str, group_id: str) -> None:
        """클라이언트를 그룹에 추가"""
        if group_id not in self._connection_groups:
            self._connection_groups[group_id] = set()
        self._connection_groups[group_id].add(client_id)

    def remove_from_group(self, client_id: str, group_id: str) -> None:
        """클라이언트를 그룹에서 제거"""
        if group_id in self._connection_groups:
            self._connection_groups[group_id].discard(client_id)

    def get_connection_count(self) -> int:
        """현재 연결된 클라이언트 수 반환"""
        return len(self.active_connections)


class ConnectionManager:
    """
    Legacy Connection Manager for compatibility with WebSocketHandler.
    Integrates ServiceContext management.
    """

    def __init__(
        self,
        default_context_cache: ServiceContext,
        client_connections: Dict[str, WebSocket],
        client_contexts: Dict[str, ServiceContext],
        received_data_buffers: Dict[str, np.ndarray],
        current_conversation_tasks: Dict[str, Optional[asyncio.Task]],
        chat_group_manager: ChatGroupManager,
    ):
        self.default_context_cache = default_context_cache
        self.client_connections = client_connections
        self.client_contexts = client_contexts
        self.received_data_buffers = received_data_buffers
        self.current_conversation_tasks = current_conversation_tasks
        self.chat_group_manager = chat_group_manager

    async def handle_new_connection(
        self,
        websocket: WebSocket,
        client_uid: str,
        send_group_update: Callable,
    ) -> None:
        """Handle new WebSocket connection setup."""
        try:
            session_service_context = await self._init_service_context(
                websocket.send_text, client_uid
            )

            await self._store_client_data(
                websocket, client_uid, session_service_context, send_group_update
            )

            await self._send_initial_messages(
                websocket, client_uid, session_service_context, send_group_update
            )

            logger.info(f"Connection established for client {client_uid}")

        except Exception as e:
            logger.error(f"Failed to initialize connection for client {client_uid}: {e}")
            await self._cleanup_failed_connection(client_uid)
            raise

    async def handle_disconnect(
        self,
        client_uid: str,
        handle_group_interrupt: Callable,
        handle_client_disconnect: Callable,
        broadcast_to_group: Callable,
        send_group_update: Callable,
    ) -> None:
        """Handle client disconnection."""
        group = self.chat_group_manager.get_client_group(client_uid)
        if group:
            await handle_group_interrupt(
                group_id=group.group_id,
                heard_response="",
                current_conversation_tasks=self.current_conversation_tasks,
                chat_group_manager=self.chat_group_manager,
                client_contexts=self.client_contexts,
                broadcast_to_group=broadcast_to_group,
            )

        await handle_client_disconnect(
            client_uid=client_uid,
            chat_group_manager=self.chat_group_manager,
            client_connections=self.client_connections,
            send_group_update=send_group_update,
        )

        # Clean up other client data
        self.client_connections.pop(client_uid, None)
        context = self.client_contexts.pop(client_uid, None)
        self.received_data_buffers.pop(client_uid, None)
        
        if client_uid in self.current_conversation_tasks:
            task = self.current_conversation_tasks[client_uid]
            if task and not task.done():
                task.cancel()
            self.current_conversation_tasks.pop(client_uid, None)

        if context:
            await context.close()

        logger.info(f"Client {client_uid} disconnected")
        message_handler.cleanup_client(client_uid)

    async def _cleanup_failed_connection(self, client_uid: str) -> None:
        """Clean up failed connection data."""
        self.client_connections.pop(client_uid, None)
        self.client_contexts.pop(client_uid, None)
        self.received_data_buffers.pop(client_uid, None)
        self.chat_group_manager.client_group_map.pop(client_uid, None)

        if client_uid in self.current_conversation_tasks:
            task = self.current_conversation_tasks[client_uid]
            if task and not task.done():
                task.cancel()
            self.current_conversation_tasks.pop(client_uid, None)

        message_handler.cleanup_client(client_uid)

    async def _init_service_context(
        self, send_text: Callable, client_uid: str
    ) -> ServiceContext:
        """Initialize service context for a new session by cloning the default context."""
        session_service_context = ServiceContext()
        await session_service_context.load_cache(
            config=self.default_context_cache.config.model_copy(deep=True),
            system_config=self.default_context_cache.system_config.model_copy(deep=True),
            character_config=self.default_context_cache.character_config.model_copy(deep=True),
            live2d_model=self.default_context_cache.live2d_model,
            asr_engine=self.default_context_cache.asr_engine,
            tts_engine=self.default_context_cache.tts_engine,
            vad_engine=self.default_context_cache.vad_engine,
            agent_engine=self.default_context_cache.agent_engine,
            translate_engine=self.default_context_cache.translate_engine,
            mcp_server_registery=self.default_context_cache.mcp_server_registery,
            tool_adapter=self.default_context_cache.tool_adapter,
            send_text=send_text,
            client_uid=client_uid,
        )
        return session_service_context

    async def _store_client_data(
        self,
        websocket: WebSocket,
        client_uid: str,
        session_service_context: ServiceContext,
        send_group_update: Callable,
    ):
        """Store client data and initialize group status."""
        self.client_connections[client_uid] = websocket
        self.client_contexts[client_uid] = session_service_context
        self.received_data_buffers[client_uid] = np.array([])

        self.chat_group_manager.client_group_map[client_uid] = ""
        await send_group_update(websocket, client_uid)

    async def _send_initial_messages(
        self,
        websocket: WebSocket,
        client_uid: str,
        session_service_context: ServiceContext,
        send_group_update: Callable,
    ):
        """Send initial connection messages to the client."""
        await websocket.send_text(
            json.dumps({"type": "full-text", "text": "Connection established"})
        )

        await websocket.send_text(
            json.dumps(
                {
                    "type": "set-model-and-conf",
                    "model_info": session_service_context.live2d_model.model_info,
                    "conf_name": session_service_context.character_config.conf_name,
                    "conf_uid": session_service_context.character_config.conf_uid,
                    "client_uid": client_uid,
                }
            )
        )

        # Send initial group status
        await send_group_update(websocket, client_uid)

        # Start microphone
        await websocket.send_text(json.dumps({"type": "control", "text": "start-mic"}))