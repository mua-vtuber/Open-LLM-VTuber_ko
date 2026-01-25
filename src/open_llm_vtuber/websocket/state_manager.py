"""Client state management for WebSocket connections."""
import asyncio
from typing import Dict, Optional, Any
import numpy as np
from loguru import logger

from ..service_context import ServiceContext


class ClientStateManager:
    """클라이언트별 상태 및 컨텍스트 관리"""

    def __init__(self):
        self.contexts: Dict[str, ServiceContext] = {}
        self.audio_buffers: Dict[str, np.ndarray] = {}
        self.conversation_tasks: Dict[str, Optional[asyncio.Task]] = {}
        self.profiles: Dict[str, Any] = {}

    def get_context(self, client_id: str) -> Optional[ServiceContext]:
        """클라이언트의 서비스 컨텍스트 조회"""
        return self.contexts.get(client_id)

    def set_context(self, client_id: str, context: ServiceContext) -> None:
        """클라이언트의 서비스 컨텍스트 설정"""
        self.contexts[client_id] = context

    def remove_context(self, client_id: str) -> Optional[ServiceContext]:
        """클라이언트의 서비스 컨텍스트 제거"""
        return self.contexts.pop(client_id, None)

    def get_audio_buffer(self, client_id: str) -> Optional[np.ndarray]:
        """클라이언트의 오디오 버퍼 조회"""
        return self.audio_buffers.get(client_id)

    def set_audio_buffer(self, client_id: str, buffer: np.ndarray) -> None:
        """클라이언트의 오디오 버퍼 설정"""
        self.audio_buffers[client_id] = buffer

    def clear_audio_buffer(self, client_id: str) -> None:
        """클라이언트의 오디오 버퍼 초기화"""
        self.audio_buffers.pop(client_id, None)

    def get_conversation_task(self, client_id: str) -> Optional[asyncio.Task]:
        """클라이언트의 현재 대화 태스크 조회"""
        return self.conversation_tasks.get(client_id)

    def set_conversation_task(
        self, client_id: str, task: Optional[asyncio.Task]
    ) -> None:
        """클라이언트의 현재 대화 태스크 설정"""
        self.conversation_tasks[client_id] = task

    def get_profile(self, client_id: str) -> Optional[Any]:
        """클라이언트의 방문자 프로필 조회"""
        return self.profiles.get(client_id)

    def set_profile(self, client_id: str, profile: Any) -> None:
        """클라이언트의 방문자 프로필 설정"""
        self.profiles[client_id] = profile

    def cleanup_client(self, client_id: str) -> None:
        """클라이언트의 모든 상태 정리"""
        self.contexts.pop(client_id, None)
        self.audio_buffers.pop(client_id, None)
        task = self.conversation_tasks.pop(client_id, None)
        if task and not task.done():
            task.cancel()
        self.profiles.pop(client_id, None)
        logger.debug(f"Cleaned up state for client {client_id}")

    def get_all_client_ids(self) -> list[str]:
        """모든 클라이언트 ID 목록 반환"""
        return list(self.contexts.keys())
