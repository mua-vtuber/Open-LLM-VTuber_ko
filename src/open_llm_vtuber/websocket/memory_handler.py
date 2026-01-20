"""Memory management handler for WebSocket communication."""

from typing import Dict
from fastapi import WebSocket
import json
from loguru import logger

from ..service_context import ServiceContext


class MemoryHandler:
    """Handles memory-related WebSocket operations."""

    def __init__(self, client_contexts: Dict[str, ServiceContext]):
        self.client_contexts = client_contexts

    async def handle_get_memories(
        self, websocket: WebSocket, client_uid: str, data: dict
    ) -> None:
        """
        Retrieve all memories for the user.

        Args:
            websocket: WebSocket connection
            client_uid: Client identifier
            data: Data from client (unused)

        Returns:
            Sends memories_list or error message via WebSocket
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

    async def handle_delete_memory(
        self, websocket: WebSocket, client_uid: str, data: dict
    ) -> None:
        """
        Delete a specific memory.

        Args:
            websocket: WebSocket connection
            client_uid: Client identifier
            data: {"memory_id": "mem_xxx"} format data

        Returns:
            Sends memory_deleted or error message via WebSocket
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

    async def handle_delete_all_memories(
        self, websocket: WebSocket, client_uid: str, data: dict
    ) -> None:
        """
        Delete all memories for the user.

        Args:
            websocket: WebSocket connection
            client_uid: Client identifier
            data: Data from client (unused)

        Returns:
            Sends all_memories_deleted or error message via WebSocket
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
