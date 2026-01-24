from typing import Dict, List, Optional, Callable, TypedDict, Any
from fastapi import WebSocket, WebSocketDisconnect
import asyncio
import json
from datetime import datetime
from enum import Enum
import numpy as np
from loguru import logger

from .service_context import ServiceContext

# Memory System
from .memory import (
    ProfileManager,
    ProfileCache,
    JsonProfileStore,
    VisitorProfile,
)
from .chat_group import (
    ChatGroupManager,
    handle_group_operation,
    handle_client_disconnect,
    broadcast_to_group,
)
from .message_handler import message_handler
from .utils.stream_audio import prepare_audio_payload
from .chat_history_manager import (
    create_new_history,
    get_history,
    delete_history,
    get_history_list,
)
from .config_manager.utils import scan_config_alts_directory, scan_bg_directory
from .config_manager import validate_config
from .context.service_context import deep_merge
from .conversations.conversation_handler import (
    handle_conversation_trigger,
    handle_group_interrupt,
    handle_individual_interrupt,
)
from .input_queue import InputQueueManager
from .queue_config import QueueConfig


class MessageType(Enum):
    """Enum for WebSocket message types"""

    GROUP = ["add-client-to-group", "remove-client-from-group"]
    HISTORY = [
        "fetch-history-list",
        "fetch-and-set-history",
        "create-new-history",
        "delete-history",
    ]
    CONVERSATION = ["mic-audio-end", "text-input", "ai-speak-signal"]
    CONFIG = ["fetch-configs", "switch-config"]
    CONTROL = ["interrupt-signal", "audio-play-start"]
    DATA = ["mic-audio-data"]


class WSMessage(TypedDict, total=False):
    """Type definition for WebSocket messages"""

    type: str
    action: Optional[str]
    text: Optional[str]
    audio: Optional[List[float]]
    images: Optional[List[str]]
    history_uid: Optional[str]
    file: Optional[str]
    display_text: Optional[dict]


class WebSocketHandler:
    """Handles WebSocket connections and message routing"""

    def __init__(self, default_context_cache: ServiceContext):
        """Initialize the WebSocket handler with default context"""
        self.client_connections: Dict[str, WebSocket] = {}
        self.client_contexts: Dict[str, ServiceContext] = {}
        self.chat_group_manager = ChatGroupManager()
        self.current_conversation_tasks: Dict[str, Optional[asyncio.Task]] = {}
        self.default_context_cache = default_context_cache
        self.received_data_buffers: Dict[str, np.ndarray] = {}

        # Message handlers mapping
        self._message_handlers = self._init_message_handlers()

        # 입력 큐 매니저 초기화
        self._queue_config = QueueConfig()
        self._input_queue_manager = InputQueueManager(
            config=self._queue_config,
            message_handler=self._process_queued_message,
            alert_callback=self._handle_queue_alert
        )
        logger.info("WebSocketHandler에 입력 큐 시스템 통합 완료")

        # 상태 브로드캐스트 태스크
        self._status_broadcast_task: Optional[asyncio.Task] = None

        # 방문자 프로필 관리자 초기화
        self._profile_store = JsonProfileStore("visitor_profiles")
        self._profile_cache = ProfileCache(maxsize=1000, ttl_seconds=300)
        self._profile_manager = ProfileManager(
            store=self._profile_store,
            cache=self._profile_cache,
            auto_create=True,
        )
        # 클라이언트별 프로필 정보 (client_uid -> VisitorProfile)
        self._client_profiles: Dict[str, VisitorProfile] = {}
        logger.info("WebSocketHandler에 방문자 프로필 관리 시스템 통합 완료")

    async def _handle_queue_alert(
        self,
        alert_type: str,
        message: str,
        severity: str
    ) -> None:
        """
        큐 알림을 처리합니다 (PriorityQueue에서 호출됨)

        Args:
            alert_type: 알림 타입
            message: 알림 메시지
            severity: 심각도
        """
        await self.send_queue_alert(alert_type, message, severity)

    def _init_message_handlers(self) -> Dict[str, Callable]:
        """Initialize message type to handler mapping"""
        return {
            "add-client-to-group": self._handle_group_operation,
            "remove-client-from-group": self._handle_group_operation,
            "request-group-info": self._handle_group_info,
            "fetch-history-list": self._handle_history_list_request,
            "fetch-and-set-history": self._handle_fetch_history,
            "create-new-history": self._handle_create_history,
            "delete-history": self._handle_delete_history,
            "interrupt-signal": self._handle_interrupt,
            "mic-audio-data": self._handle_audio_data,
            "mic-audio-end": self._handle_conversation_trigger,
            "raw-audio-data": self._handle_raw_audio_data,
            "text-input": self._handle_conversation_trigger,
            "ai-speak-signal": self._handle_conversation_trigger,
            "fetch-configs": self._handle_fetch_configs,
            "switch-config": self._handle_config_switch,
            "update-config": self._handle_update_config,
            "fetch-backgrounds": self._handle_fetch_backgrounds,
            "audio-play-start": self._handle_audio_play_start,
            "request-init-config": self._handle_init_config_request,
            "heartbeat": self._handle_heartbeat,
            # Memory Management Handlers (Mem0)
            "get_memories": self._handle_get_memories,
            "delete_memory": self._handle_delete_memory,
            "delete_all_memories": self._handle_delete_all_memories,
            # Visitor Profile Handlers
            "get-visitor-profile": self._handle_get_visitor_profile,
            "update-visitor-profile": self._handle_update_visitor_profile,
            "list-visitor-profiles": self._handle_list_visitor_profiles,
            "delete-visitor-profile": self._handle_delete_visitor_profile,
        }

    async def handle_new_connection(
        self, websocket: WebSocket, client_uid: str
    ) -> None:
        """
        Handle new WebSocket connection setup

        Args:
            websocket: The WebSocket connection
            client_uid: Unique identifier for the client

        Raises:
            Exception: If initialization fails
        """
        try:
            # 첫 연결 시 입력 큐 매니저 및 상태 브로드캐스트 시작
            if not self._input_queue_manager.is_running():
                await self._input_queue_manager.start()
                logger.info("입력 큐 매니저 시작됨")
                # 상태 브로드캐스트 시작
                await self.start_status_broadcast(interval=1.0)

            session_service_context = await self._init_service_context(
                websocket.send_text, client_uid
            )

            await self._store_client_data(
                websocket, client_uid, session_service_context
            )

            await self._send_initial_messages(
                websocket, client_uid, session_service_context
            )

            # 방문자 프로필 기록 (기본 플랫폼: direct)
            profile = await self._profile_manager.record_visit(
                identifier=client_uid,
                platform="direct",
            )
            self._client_profiles[client_uid] = profile
            is_new_visitor = profile.visit_count == 1
            logger.info(
                f"Visitor profile recorded: {client_uid} "
                f"(visit #{profile.visit_count}, new={is_new_visitor})"
            )

            logger.info(f"Connection established for client {client_uid}")

        except Exception as e:
            logger.error(
                f"Failed to initialize connection for client {client_uid}: {e}"
            )
            await self._cleanup_failed_connection(client_uid)
            raise

    async def _store_client_data(
        self,
        websocket: WebSocket,
        client_uid: str,
        session_service_context: ServiceContext,
    ):
        """Store client data and initialize group status"""
        self.client_connections[client_uid] = websocket
        self.client_contexts[client_uid] = session_service_context
        self.received_data_buffers[client_uid] = np.array([])

        self.chat_group_manager.client_group_map[client_uid] = ""
        await self.send_group_update(websocket, client_uid)

    async def _send_initial_messages(
        self,
        websocket: WebSocket,
        client_uid: str,
        session_service_context: ServiceContext,
    ):
        """Send initial connection messages to the client"""
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
        await self.send_group_update(websocket, client_uid)

        # Start microphone
        await websocket.send_text(json.dumps({"type": "control", "text": "start-mic"}))

    async def _init_service_context(
        self, send_text: Callable, client_uid: str
    ) -> ServiceContext:
        """Initialize service context for a new session by cloning the default context"""
        session_service_context = ServiceContext()
        await session_service_context.load_cache(
            config=self.default_context_cache.config.model_copy(deep=True),
            system_config=self.default_context_cache.system_config.model_copy(
                deep=True
            ),
            character_config=self.default_context_cache.character_config.model_copy(
                deep=True
            ),
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

    async def handle_websocket_communication(
        self, websocket: WebSocket, client_uid: str
    ) -> None:
        """
        Handle ongoing WebSocket communication

        Args:
            websocket: The WebSocket connection
            client_uid: Unique identifier for the client
        """
        try:
            while True:
                try:
                    data = await websocket.receive_json()
                    message_handler.handle_message(client_uid, data)

                    # 메시지에 client_uid 추가
                    data['client_uid'] = client_uid

                    # 메시지를 큐에 추가
                    success = await self._input_queue_manager.enqueue(data)

                    if not success:
                        logger.warning(
                            f"메시지가 큐에 추가되지 못했습니다 (클라이언트: {client_uid}, "
                            f"타입: {data.get('type', 'unknown')})"
                        )
                    else:
                        logger.debug(
                            f"메시지가 큐에 추가됨 (클라이언트: {client_uid}, "
                            f"타입: {data.get('type', 'unknown')})"
                        )

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
        self, websocket: WebSocket, client_uid: str, data: WSMessage
    ) -> None:
        """
        Route incoming message to appropriate handler

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

    async def _process_queued_message(self, message: Dict) -> None:
        """
        큐에서 가져온 메시지를 처리합니다.

        Args:
            message: 처리할 메시지 (client_uid 포함)
        """
        client_uid = message.get('client_uid')
        if not client_uid:
            logger.error("메시지에 client_uid가 없습니다")
            return

        # client_uid로 WebSocket 연결 찾기
        websocket = self.client_connections.get(client_uid)
        if not websocket:
            logger.warning(
                f"클라이언트 {client_uid}의 WebSocket 연결을 찾을 수 없습니다. "
                f"메시지 타입: {message.get('type', 'unknown')}"
            )
            return

        # 메시지 라우팅
        try:
            await self._route_message(websocket, client_uid, message)
        except Exception as e:
            logger.error(
                f"큐 메시지 처리 중 오류 발생 (클라이언트: {client_uid}, "
                f"타입: {message.get('type', 'unknown')}): {e}",
                exc_info=True
            )

    async def _handle_group_operation(
        self, websocket: WebSocket, client_uid: str, data: dict
    ) -> None:
        """Handle group-related operations"""
        operation = data.get("type")
        target_uid = data.get(
            "invitee_uid" if operation == "add-client-to-group" else "target_uid"
        )

        await handle_group_operation(
            operation=operation,
            client_uid=client_uid,
            target_uid=target_uid,
            chat_group_manager=self.chat_group_manager,
            client_connections=self.client_connections,
            send_group_update=self.send_group_update,
        )

    async def handle_disconnect(self, client_uid: str) -> None:
        """Handle client disconnection"""
        group = self.chat_group_manager.get_client_group(client_uid)
        if group:
            await handle_group_interrupt(
                group_id=group.group_id,
                heard_response="",
                current_conversation_tasks=self.current_conversation_tasks,
                chat_group_manager=self.chat_group_manager,
                client_contexts=self.client_contexts,
                broadcast_to_group=self.broadcast_to_group,
            )

        await handle_client_disconnect(
            client_uid=client_uid,
            chat_group_manager=self.chat_group_manager,
            client_connections=self.client_connections,
            send_group_update=self.send_group_update,
        )

        # Clean up other client data
        self.client_connections.pop(client_uid, None)
        self.client_contexts.pop(client_uid, None)
        self.received_data_buffers.pop(client_uid, None)
        self._client_profiles.pop(client_uid, None)  # 프로필 캐시 정리
        if client_uid in self.current_conversation_tasks:
            task = self.current_conversation_tasks[client_uid]
            if task and not task.done():
                task.cancel()
            self.current_conversation_tasks.pop(client_uid, None)

        # Call context close to clean up resources (e.g., MCPClient)
        context = self.client_contexts.get(client_uid)
        if context:
            await context.close()

        logger.info(f"Client {client_uid} disconnected")
        message_handler.cleanup_client(client_uid)

    async def _cleanup_failed_connection(self, client_uid: str) -> None:
        """Clean up failed connection data"""
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

    async def broadcast_to_group(
        self, group_members: list[str], message: dict, exclude_uid: str = None
    ) -> None:
        """Broadcasts a message to group members"""
        await broadcast_to_group(
            group_members=group_members,
            message=message,
            client_connections=self.client_connections,
            exclude_uid=exclude_uid,
        )

    async def send_group_update(self, websocket: WebSocket, client_uid: str):
        """Sends group information to a client"""
        group = self.chat_group_manager.get_client_group(client_uid)
        if group:
            current_members = self.chat_group_manager.get_group_members(client_uid)
            await websocket.send_text(
                json.dumps(
                    {
                        "type": "group-update",
                        "members": current_members,
                        "is_owner": group.owner_uid == client_uid,
                    }
                )
            )
        else:
            await websocket.send_text(
                json.dumps(
                    {
                        "type": "group-update",
                        "members": [],
                        "is_owner": False,
                    }
                )
            )

    async def _handle_interrupt(
        self, websocket: WebSocket, client_uid: str, data: WSMessage
    ) -> None:
        """Handle conversation interruption"""
        heard_response = data.get("text", "")
        context = self.client_contexts[client_uid]
        group = self.chat_group_manager.get_client_group(client_uid)

        if group and len(group.members) > 1:
            await handle_group_interrupt(
                group_id=group.group_id,
                heard_response=heard_response,
                current_conversation_tasks=self.current_conversation_tasks,
                chat_group_manager=self.chat_group_manager,
                client_contexts=self.client_contexts,
                broadcast_to_group=self.broadcast_to_group,
            )
        else:
            await handle_individual_interrupt(
                client_uid=client_uid,
                current_conversation_tasks=self.current_conversation_tasks,
                context=context,
                heard_response=heard_response,
            )

    async def _handle_history_list_request(
        self, websocket: WebSocket, client_uid: str, data: WSMessage
    ) -> None:
        """Handle request for chat history list"""
        context = self.client_contexts[client_uid]
        histories = get_history_list(context.character_config.conf_uid)
        await websocket.send_text(
            json.dumps({"type": "history-list", "histories": histories})
        )

    async def _handle_fetch_history(
        self, websocket: WebSocket, client_uid: str, data: dict
    ):
        """Handle fetching and setting specific chat history"""
        history_uid = data.get("history_uid")
        if not history_uid:
            return

        context = self.client_contexts[client_uid]
        # Update history_uid in service context
        context.history_uid = history_uid
        context.agent_engine.set_memory_from_history(
            conf_uid=context.character_config.conf_uid,
            history_uid=history_uid,
        )

        messages = [
            msg
            for msg in get_history(
                context.character_config.conf_uid,
                history_uid,
            )
            if msg["role"] != "system"
        ]
        await websocket.send_text(
            json.dumps({"type": "history-data", "messages": messages})
        )

    async def _handle_create_history(
        self, websocket: WebSocket, client_uid: str, data: WSMessage
    ) -> None:
        """Handle creation of new chat history"""
        context = self.client_contexts[client_uid]
        history_uid = create_new_history(context.character_config.conf_uid)
        if history_uid:
            context.history_uid = history_uid
            context.agent_engine.set_memory_from_history(
                conf_uid=context.character_config.conf_uid,
                history_uid=history_uid,
            )
            await websocket.send_text(
                json.dumps(
                    {
                        "type": "new-history-created",
                        "history_uid": history_uid,
                    }
                )
            )

    async def _handle_delete_history(
        self, websocket: WebSocket, client_uid: str, data: dict
    ):
        """Handle deletion of chat history"""
        history_uid = data.get("history_uid")
        if not history_uid:
            return

        context = self.client_contexts[client_uid]
        success = delete_history(
            context.character_config.conf_uid,
            history_uid,
        )
        await websocket.send_text(
            json.dumps(
                {
                    "type": "history-deleted",
                    "success": success,
                    "history_uid": history_uid,
                }
            )
        )
        if history_uid == context.history_uid:
            context.history_uid = None

    async def _handle_audio_data(
        self, websocket: WebSocket, client_uid: str, data: WSMessage
    ) -> None:
        """Handle incoming audio data"""
        audio_data = data.get("audio", [])
        if audio_data:
            self.received_data_buffers[client_uid] = np.append(
                self.received_data_buffers[client_uid],
                np.array(audio_data, dtype=np.float32),
            )

    async def _handle_raw_audio_data(
        self, websocket: WebSocket, client_uid: str, data: WSMessage
    ) -> None:
        """Handle incoming raw audio data for VAD processing"""
        context = self.client_contexts[client_uid]
        chunk = data.get("audio", [])
        if chunk:
            for audio_bytes in context.vad_engine.detect_speech(chunk):
                if audio_bytes == b"<|PAUSE|>":
                    await websocket.send_text(
                        json.dumps({"type": "control", "text": "interrupt"})
                    )
                elif audio_bytes == b"<|RESUME|>":
                    pass
                elif len(audio_bytes) > 1024:
                    # Detected audio activity (voice)
                    self.received_data_buffers[client_uid] = np.append(
                        self.received_data_buffers[client_uid],
                        np.frombuffer(audio_bytes, dtype=np.int16).astype(np.float32),
                    )
                    await websocket.send_text(
                        json.dumps({"type": "control", "text": "mic-audio-end"})
                    )

    async def _handle_conversation_trigger(
        self, websocket: WebSocket, client_uid: str, data: WSMessage
    ) -> None:
        """Handle triggers that start a conversation"""
        await handle_conversation_trigger(
            msg_type=data.get("type", ""),
            data=data,
            client_uid=client_uid,
            context=self.client_contexts[client_uid],
            websocket=websocket,
            client_contexts=self.client_contexts,
            client_connections=self.client_connections,
            chat_group_manager=self.chat_group_manager,
            received_data_buffers=self.received_data_buffers,
            current_conversation_tasks=self.current_conversation_tasks,
            broadcast_to_group=self.broadcast_to_group,
        )

    async def _handle_fetch_configs(
        self, websocket: WebSocket, client_uid: str, data: WSMessage
    ) -> None:
        """Handle fetching available configurations"""
        context = self.client_contexts[client_uid]
        config_files = scan_config_alts_directory(context.system_config.config_alts_dir)
        await websocket.send_text(
            json.dumps({"type": "config-files", "configs": config_files})
        )

    async def _handle_config_switch(
        self, websocket: WebSocket, client_uid: str, data: dict
    ):
        """Handle switching to a different configuration"""
        config_file_name = data.get("file")
        if config_file_name:
            context = self.client_contexts[client_uid]
            await context.handle_config_switch(websocket, config_file_name)

    async def _handle_update_config(
        self, websocket: WebSocket, client_uid: str, data: dict
    ):
        """
        Handle partial configuration update from frontend.

        Receives partial config updates, deep merges with current config,
        validates, and reloads engines.

        Args:
            websocket: WebSocket connection
            client_uid: Client unique identifier
            data: Message data containing 'config' key with partial updates
        """
        config_updates = data.get("config")

        if not config_updates:
            await websocket.send_text(
                json.dumps({
                    "type": "config-update-error",
                    "error": "No config provided"
                })
            )
            return

        try:
            context = self.client_contexts[client_uid]

            # Deep merge with current character config
            current_config = context.character_config.model_dump()
            merged_config = deep_merge(current_config, config_updates)

            # Validate merged config with Pydantic
            new_config = {
                "system_config": context.system_config.model_dump(),
                "character_config": merged_config,
            }
            validated = validate_config(new_config)

            # Reload engines with new config
            await context.load_from_config(validated)

            logger.info(f"Config updated for client {client_uid}")

            await websocket.send_text(
                json.dumps({
                    "type": "config-updated",
                    "message": "Settings applied successfully"
                })
            )

        except Exception as e:
            logger.error(f"Error updating config for client {client_uid}: {e}")
            await websocket.send_text(
                json.dumps({
                    "type": "config-update-error",
                    "error": str(e)
                })
            )

    async def _handle_fetch_backgrounds(
        self, websocket: WebSocket, client_uid: str, data: WSMessage
    ) -> None:
        """Handle fetching available background images"""
        bg_files = scan_bg_directory()
        await websocket.send_text(
            json.dumps({"type": "background-files", "files": bg_files})
        )

    async def _handle_audio_play_start(
        self, websocket: WebSocket, client_uid: str, data: WSMessage
    ) -> None:
        """
        Handle audio playback start notification
        """
        group_members = self.chat_group_manager.get_group_members(client_uid)
        if len(group_members) > 1:
            display_text = data.get("display_text")
            if display_text:
                silent_payload = prepare_audio_payload(
                    audio_path=None,
                    display_text=display_text,
                    actions=None,
                    forwarded=True,
                )
                await self.broadcast_to_group(
                    group_members, silent_payload, exclude_uid=client_uid
                )

    async def _handle_group_info(
        self, websocket: WebSocket, client_uid: str, data: WSMessage
    ) -> None:
        """Handle group info request"""
        await self.send_group_update(websocket, client_uid)

    async def _handle_init_config_request(
        self, websocket: WebSocket, client_uid: str, data: WSMessage
    ) -> None:
        """Handle request for initialization configuration"""
        context = self.client_contexts.get(client_uid)
        if not context:
            context = self.default_context_cache

        await websocket.send_text(
            json.dumps(
                {
                    "type": "set-model-and-conf",
                    "model_info": context.live2d_model.model_info,
                    "conf_name": context.character_config.conf_name,
                    "conf_uid": context.character_config.conf_uid,
                    "client_uid": client_uid,
                }
            )
        )

    async def _handle_heartbeat(
        self, websocket: WebSocket, client_uid: str, data: WSMessage
    ) -> None:
        """Handle heartbeat messages from clients"""
        try:
            await websocket.send_json({"type": "heartbeat-ack"})
        except Exception as e:
            logger.error(f"Error sending heartbeat acknowledgment: {e}")

    async def _handle_get_memories(
        self, websocket: WebSocket, client_uid: str, data: dict
    ) -> None:
        """
        사용자의 모든 메모리를 조회하여 반환.

        Args:
            websocket: WebSocket connection
            client_uid: Client identifier
            data: 클라이언트로부터 받은 데이터 (사용하지 않음)

        Returns:
            WebSocket으로 memories_list 또는 error 메시지 전송
        """
        context = self.client_contexts.get(client_uid)
        if not context:
            await websocket.send_text(
                json.dumps(
                    {
                        "type": "error",
                        "message": "클라이언트 컨텍스트를 찾을 수 없습니다",
                    }
                )
            )
            return

        if hasattr(context.agent_engine, "get_all_memories"):
            try:
                memories = context.agent_engine.get_all_memories()
                await websocket.send_text(
                    json.dumps({"type": "memories_list", "memories": memories})
                )
            except Exception as e:
                logger.error(f"메모리 조회 실패: {e}")
                await websocket.send_text(
                    json.dumps(
                        {
                            "type": "error",
                            "message": f"메모리 조회 중 오류가 발생했습니다: {str(e)}",
                        }
                    )
                )
        else:
            await websocket.send_text(
                json.dumps(
                    {
                        "type": "error",
                        "message": "현재 agent는 메모리 관리를 지원하지 않습니다",
                    }
                )
            )

    async def _handle_delete_memory(
        self, websocket: WebSocket, client_uid: str, data: dict
    ) -> None:
        """
        특정 메모리를 삭제.

        Args:
            websocket: WebSocket connection
            client_uid: Client identifier
            data: {"memory_id": "mem_xxx"} 형식의 데이터

        Returns:
            WebSocket으로 memory_deleted 또는 error 메시지 전송
        """
        memory_id = data.get("memory_id")

        if not memory_id:
            await websocket.send_text(
                json.dumps({"type": "error", "message": "memory_id가 필요합니다"})
            )
            return

        context = self.client_contexts.get(client_uid)
        if not context:
            await websocket.send_text(
                json.dumps(
                    {
                        "type": "error",
                        "message": "클라이언트 컨텍스트를 찾을 수 없습니다",
                    }
                )
            )
            return

        if hasattr(context.agent_engine, "delete_memory"):
            try:
                success = context.agent_engine.delete_memory(memory_id)
                await websocket.send_text(
                    json.dumps(
                        {
                            "type": "memory_deleted",
                            "success": success,
                            "memory_id": memory_id,
                        }
                    )
                )
            except Exception as e:
                logger.error(f"메모리 삭제 실패: {e}")
                await websocket.send_text(
                    json.dumps(
                        {
                            "type": "error",
                            "message": f"메모리 삭제 중 오류가 발생했습니다: {str(e)}",
                        }
                    )
                )
        else:
            await websocket.send_text(
                json.dumps(
                    {
                        "type": "error",
                        "message": "현재 agent는 메모리 관리를 지원하지 않습니다",
                    }
                )
            )

    async def _handle_delete_all_memories(
        self, websocket: WebSocket, client_uid: str, data: dict
    ) -> None:
        """
        사용자의 모든 메모리를 삭제.

        Args:
            websocket: WebSocket connection
            client_uid: Client identifier
            data: 클라이언트로부터 받은 데이터 (사용하지 않음)

        Returns:
            WebSocket으로 all_memories_deleted 또는 error 메시지 전송
        """
        context = self.client_contexts.get(client_uid)
        if not context:
            await websocket.send_text(
                json.dumps(
                    {
                        "type": "error",
                        "message": "클라이언트 컨텍스트를 찾을 수 없습니다",
                    }
                )
            )
            return

        if hasattr(context.agent_engine, "delete_all_memories"):
            try:
                success = context.agent_engine.delete_all_memories()
                await websocket.send_text(
                    json.dumps({"type": "all_memories_deleted", "success": success})
                )
            except Exception as e:
                logger.error(f"모든 메모리 삭제 실패: {e}")
                await websocket.send_text(
                    json.dumps(
                        {
                            "type": "error",
                            "message": f"모든 메모리 삭제 중 오류가 발생했습니다: {str(e)}",
                        }
                    )
                )
        else:
            await websocket.send_text(
                json.dumps(
                    {
                        "type": "error",
                        "message": "현재 agent는 메모리 관리를 지원하지 않습니다",
                    }
                )
            )

    def get_queue_status(self) -> Dict[str, any]:
        """
        입력 큐의 현재 상태를 반환합니다.

        Returns:
            Dict[str, any]: 큐 상태 정보
                - pending: 대기 중인 메시지 수
                - processing: 처리 중인 메시지 (0 또는 1)
                - max_size: 최대 큐 크기
                - total_received: 총 수신 메시지 수
                - total_processed: 총 처리 완료 메시지 수
                - total_dropped: 드롭된 메시지 수
                - running: 큐 매니저 실행 상태
        """
        status = self._input_queue_manager.get_status()

        return {
            'pending': status.get('queue_size', 0),
            'processing': 1 if status.get('current_message') else 0,
            'max_size': status.get('queue_max_size', 0),
            'total_received': status.get('total_received', 0),
            'total_processed': status.get('total_processed', 0),
            'total_dropped': status.get('total_dropped', 0),
            'running': status.get('running', False),
            'avg_processing_time': status.get('avg_processing_time', 0.0),
            'processing_rate': status.get('processing_rate', 0.0)
        }

    def get_priority_rules(self) -> Dict[str, any]:
        """
        입력 큐의 우선순위 규칙을 반환합니다.

        Returns:
            Dict[str, any]: 우선순위 규칙 정보
                - priority_mode: 우선순위 모드
                - wait_time: 대기 시간
                - allow_interruption: 중단 허용 여부
                - superchat_always_priority: 슈퍼챗 항상 우선
                - voice_active_chat_delay: 음성 활성 시 채팅 지연
                - chat_active_voice_delay: 채팅 활성 시 음성 지연
        """
        return self._queue_config.priority_rules.to_dict()

    def get_priority_rules_instance(self):
        """
        PriorityRules 인스턴스를 반환합니다.

        Returns:
            PriorityRules: 우선순위 규칙 인스턴스
        """
        return self._queue_config.priority_rules

    async def broadcast_priority_rules_update(self) -> None:
        """
        우선순위 규칙 변경을 모든 연결된 클라이언트에 브로드캐스트합니다.
        """
        message = {
            "type": "priority-rules-updated",
            "priority_rules": self._queue_config.priority_rules.to_dict()
        }

        disconnected_clients = []

        for client_uid, websocket in self.client_connections.items():
            try:
                await websocket.send_json(message)
            except Exception as e:
                logger.warning(
                    f"Failed to send priority rules update to {client_uid}: {e}"
                )
                disconnected_clients.append(client_uid)

        # 연결이 끊긴 클라이언트 정리는 별도 처리
        # (이미 handle_disconnect에서 처리됨)

    # ============================================================
    # 큐 모니터링 및 실시간 브로드캐스트
    # ============================================================

    async def start_status_broadcast(self, interval: float = 1.0) -> None:
        """
        상태 브로드캐스트를 시작합니다.

        Args:
            interval: 브로드캐스트 간격 (초)
        """
        if self._status_broadcast_task and not self._status_broadcast_task.done():
            logger.warning("상태 브로드캐스트가 이미 실행 중입니다")
            return

        self._status_broadcast_task = asyncio.create_task(
            self._status_broadcast_loop(interval)
        )
        logger.info(f"상태 브로드캐스트 시작됨 (간격: {interval}초)")

    async def stop_status_broadcast(self) -> None:
        """상태 브로드캐스트를 중지합니다."""
        if self._status_broadcast_task:
            self._status_broadcast_task.cancel()
            try:
                await self._status_broadcast_task
            except asyncio.CancelledError:
                pass
            self._status_broadcast_task = None
            logger.info("상태 브로드캐스트 중지됨")

    async def _status_broadcast_loop(self, interval: float) -> None:
        """
        주기적 상태 브로드캐스트 (변경 감지 최적화)

        Args:
            interval: 브로드캐스트 간격 (초)
        """
        last_status_hash: Optional[int] = None

        while True:
            try:
                status = self.get_queue_status()

                # 해시 기반 변경 감지
                # dict를 튜플로 변환하여 해시 가능하게 만듦
                status_tuple = tuple(sorted(status.items()))
                current_hash = hash(status_tuple)

                # 변경된 경우에만 브로드캐스트
                if current_hash != last_status_hash:
                    message = {
                        "type": "queue-status-update",
                        "status": status,
                        "timestamp": datetime.now().isoformat()
                    }
                    await self._broadcast_to_all(message)
                    last_status_hash = current_hash

                await asyncio.sleep(interval)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"상태 브로드캐스트 오류: {e}")
                await asyncio.sleep(interval)

    async def _broadcast_to_all(self, message: dict) -> None:
        """
        모든 연결된 클라이언트에 메시지를 전송합니다.

        Args:
            message: 전송할 메시지
        """
        if not self.client_connections:
            return

        disconnected = []

        for client_uid, websocket in self.client_connections.items():
            try:
                await websocket.send_json(message)
            except Exception:
                disconnected.append(client_uid)

        # 연결이 끊긴 클라이언트는 별도 처리됨
        # (handle_disconnect에서 처리)

    async def send_queue_alert(
        self,
        alert_type: str,
        message: str,
        severity: str = "warning"
    ) -> None:
        """
        큐 알림을 모든 클라이언트에 전송합니다.

        Args:
            alert_type: 알림 타입 (overflow, slow_processing, error 등)
            message: 알림 메시지
            severity: 심각도 (info, warning, error)
        """
        alert = {
            "type": "queue-alert",
            "alert_type": alert_type,
            "message": message,
            "severity": severity,
            "timestamp": datetime.now().isoformat()
        }
        await self._broadcast_to_all(alert)

    def get_queue_metric_history(self, minutes: int = 5) -> List[dict]:
        """
        큐 메트릭 히스토리를 반환합니다.

        Args:
            minutes: 조회할 기간 (분)

        Returns:
            List[dict]: 메트릭 히스토리 리스트
        """
        return self._input_queue_manager.get_metric_history(minutes)

    # ============================================================
    # 방문자 프로필 핸들러
    # ============================================================

    async def _handle_get_visitor_profile(
        self, websocket: WebSocket, client_uid: str, data: dict
    ) -> None:
        """
        클라이언트의 방문자 프로필을 조회합니다.

        Args:
            websocket: WebSocket connection
            client_uid: Client identifier
            data: 요청 데이터 (선택적으로 identifier, platform 포함 가능)
        """
        try:
            # 요청에 identifier/platform이 있으면 해당 프로필 조회
            # 없으면 현재 클라이언트의 프로필 조회
            identifier = data.get("identifier", client_uid)
            platform = data.get("platform", "direct")

            profile = await self._profile_manager.load_profile(identifier, platform)

            if profile:
                await websocket.send_text(
                    json.dumps({
                        "type": "visitor-profile",
                        "profile": profile.to_dict(),
                        "summary": profile.get_summary_text(),
                    })
                )
            else:
                await websocket.send_text(
                    json.dumps({
                        "type": "visitor-profile",
                        "profile": None,
                        "message": f"프로필을 찾을 수 없습니다: {platform}:{identifier}",
                    })
                )
        except Exception as e:
            logger.error(f"방문자 프로필 조회 실패: {e}")
            await websocket.send_text(
                json.dumps({
                    "type": "error",
                    "message": f"방문자 프로필 조회 중 오류가 발생했습니다: {str(e)}",
                })
            )

    async def _handle_update_visitor_profile(
        self, websocket: WebSocket, client_uid: str, data: dict
    ) -> None:
        """
        방문자 프로필을 업데이트합니다.

        Args:
            websocket: WebSocket connection
            client_uid: Client identifier
            data: 업데이트 데이터
                - identifier: 사용자 식별자 (기본: client_uid)
                - platform: 플랫폼 (기본: "direct")
                - action: 업데이트 타입 (add_fact, add_preference, update_affinity)
                - value: 업데이트 값
        """
        try:
            identifier = data.get("identifier", client_uid)
            platform = data.get("platform", "direct")
            action = data.get("action")
            value = data.get("value")

            if not action:
                await websocket.send_text(
                    json.dumps({
                        "type": "error",
                        "message": "action 필드가 필요합니다",
                    })
                )
                return

            result = None
            if action == "add_fact":
                if not value:
                    await websocket.send_text(
                        json.dumps({
                            "type": "error",
                            "message": "add_fact에는 value가 필요합니다",
                        })
                    )
                    return
                result = await self._profile_manager.add_known_fact(
                    identifier, platform, value
                )

            elif action == "add_preference":
                category = data.get("category", "likes")  # likes or dislikes
                if not value:
                    await websocket.send_text(
                        json.dumps({
                            "type": "error",
                            "message": "add_preference에는 value가 필요합니다",
                        })
                    )
                    return
                result = await self._profile_manager.add_preference(
                    identifier, platform, category, value
                )

            elif action == "update_affinity":
                delta = data.get("delta", 0)
                result = await self._profile_manager.update_affinity(
                    identifier, platform, delta
                )

            elif action == "record_message":
                count = data.get("count", 1)
                await self._profile_manager.record_message(
                    identifier, platform, count
                )
                result = True

            else:
                await websocket.send_text(
                    json.dumps({
                        "type": "error",
                        "message": f"알 수 없는 action: {action}",
                    })
                )
                return

            # 업데이트된 프로필 반환
            profile = await self._profile_manager.load_profile(identifier, platform)
            await websocket.send_text(
                json.dumps({
                    "type": "visitor-profile-updated",
                    "action": action,
                    "success": result is not None and result is not False,
                    "profile": profile.to_dict() if profile else None,
                })
            )

        except Exception as e:
            logger.error(f"방문자 프로필 업데이트 실패: {e}")
            await websocket.send_text(
                json.dumps({
                    "type": "error",
                    "message": f"방문자 프로필 업데이트 중 오류가 발생했습니다: {str(e)}",
                })
            )

    async def _handle_list_visitor_profiles(
        self, websocket: WebSocket, client_uid: str, data: dict
    ) -> None:
        """
        시청자 프로필 목록을 조회합니다.

        Args:
            websocket: WebSocket connection
            client_uid: Client identifier
            data: 요청 데이터
                - platform: 플랫폼 필터 (선택적, null이면 전체)
        """
        try:
            platform = data.get("platform")  # None이면 전체

            # 프로필 목록 조회
            profile_list = await self._profile_manager.list_profiles(platform)

            # 각 프로필의 상세 정보 로드
            profiles = []
            for identifier, plat in profile_list:
                profile = await self._profile_manager.load_profile(identifier, plat)
                if profile:
                    profiles.append(profile.to_dict())

            await websocket.send_text(
                json.dumps({
                    "type": "visitor-profiles-list",
                    "profiles": profiles,
                    "count": len(profiles),
                    "platform_filter": platform,
                })
            )

            logger.info(
                f"시청자 프로필 목록 조회: {len(profiles)}개 "
                f"(platform={platform or 'all'})"
            )

        except Exception as e:
            logger.error(f"시청자 프로필 목록 조회 실패: {e}")
            await websocket.send_text(
                json.dumps({
                    "type": "error",
                    "message": f"시청자 프로필 목록 조회 중 오류가 발생했습니다: {str(e)}",
                })
            )

    async def _handle_delete_visitor_profile(
        self, websocket: WebSocket, client_uid: str, data: dict
    ) -> None:
        """
        시청자 프로필을 삭제합니다.

        Args:
            websocket: WebSocket connection
            client_uid: Client identifier
            data: 삭제 요청 데이터
                - identifier: 사용자 식별자
                - platform: 플랫폼
        """
        try:
            identifier = data.get("identifier")
            platform = data.get("platform")

            if not identifier or not platform:
                await websocket.send_text(
                    json.dumps({
                        "type": "error",
                        "message": "identifier와 platform 필드가 필요합니다",
                    })
                )
                return

            # 프로필 삭제
            success = await self._profile_manager.delete_profile(identifier, platform)

            await websocket.send_text(
                json.dumps({
                    "type": "visitor-profile-deleted",
                    "success": success,
                    "identifier": identifier,
                    "platform": platform,
                })
            )

            if success:
                logger.info(f"시청자 프로필 삭제됨: {platform}:{identifier}")
            else:
                logger.warning(f"시청자 프로필 삭제 실패 (존재하지 않음): {platform}:{identifier}")

        except Exception as e:
            logger.error(f"시청자 프로필 삭제 실패: {e}")
            await websocket.send_text(
                json.dumps({
                    "type": "error",
                    "message": f"시청자 프로필 삭제 중 오류가 발생했습니다: {str(e)}",
                })
            )

    def get_profile_manager(self) -> ProfileManager:
        """ProfileManager 인스턴스 반환 (외부 접근용)"""
        return self._profile_manager

    def get_client_profile(self, client_uid: str) -> Optional[VisitorProfile]:
        """현재 연결된 클라이언트의 프로필 반환"""
        return self._client_profiles.get(client_uid)

    def get_profile_cache_stats(self) -> Dict[str, Any]:
        """프로필 캐시 통계 반환"""
        return self._profile_manager.get_cache_stats()
